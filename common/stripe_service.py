"""
Stripe API module
"""

from datetime import datetime, timedelta, timezone
import csv
from decimal import Decimal, InvalidOperation
import hashlib
from io import StringIO
import json
import logging
import os
from urllib.parse import quote

import stripe
import requests
from stripe.params import (
    PaymentIntentListParams,
    PaymentIntentListParamsCreated,
    RefundListParams,
    RefundListParamsCreated,
)

from common.db import db_insert, db_query_all, db_update
from common.models.stripe import StripeRefund, StripeTransaction
from common.stripe_reconciliation_service import ELIGIBLE_EVENTS_SQL

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FEE_COLUMNS = {
    "suite": "Suite",
    "product": "Product",
    "feature_name": "FeatureName",
    "balance_transaction_created": "BalanceTransactionCreated",
    "balance_transaction_id": "BalanceTransactionId",
    "balance_transaction_description": "BalanceTransactionDescription",
    "fee_description": "FeeDescription",
    "incurred_by": "IncurredBy",
    "incurred_by_type": "IncurredByType",
    "amount": "Amount",
    "tax": "Tax",
    "currency": "Currency",
    "invoice_number": "InvoiceNumber",
    "credit_note_number": "CreditNoteNumber",
    "incurred_at": "IncurredAt",
    "feature_description": "FeatureDescription",
    "fee_transaction_id": "FeeTransactionId",
    "fee_transaction_created": "FeeTransactionCreated",
    "pricing_tier": "PricingTier",
    "fee_category": "FeeCategory",
    "settled_at": "SettledAt",
    "settled_via": "SettledVia",
}


class FeeReportNotReady(ValueError):
    """The requested day's fees are not available from Stripe yet."""

    def __init__(self, available_until):
        super().__init__(
            "Stripe fee data is not available for the entire requested day"
        )
        self.available_until = available_until


class StripeService:
    """
    Service to interact with Stripe API
    """

    refresh_financials = False

    def get_transactions(self, start: int = None, end: int = None):
        """
        Get payment intents and refunds from Stripe API within the specified date range.
        """
        try:
            stripe_api_key = os.environ.get("STRIPE_API_SECRET_KEY")
            if not stripe_api_key:
                logger.error("Stripe API key is not set in environment variables.")
                return None

            client = stripe.StripeClient(api_key=stripe_api_key)

            if end is None:
                end = int(datetime.now(timezone.utc).timestamp())
            if start is None:
                start = end - (24 * 60 * 60)  # default to last 24 hours

            created = PaymentIntentListParamsCreated(gte=start, lt=end)
            params = PaymentIntentListParams(
                created=created,
                limit=100,
                expand=["data.latest_charge.balance_transaction"],
            )

            payment_intents = client.v1.payment_intents.list(params)
            transaction_count = 0
            order_count = 0

            transactions: list[StripeTransaction] = []
            for payment_intent in payment_intents.auto_paging_iter():
                transaction_count += 1

                metadata = payment_intent.metadata

                event_id = metadata["eventIds"] if "eventIds" in metadata else None

                order_id = metadata["orderId"] if "orderId" in metadata else None

                if not order_id:
                    logger.warning(
                        "Payment intent %s for event %s has no order ID",
                        payment_intent.id,
                        event_id,
                    )

                if not order_id:
                    continue

                status = payment_intent.status

                if status != "succeeded":
                    continue

                order_count += 1

                transaction = StripeTransaction(
                    order_id=order_id,
                    event_id=event_id,
                    status=status,
                    payment_intent=payment_intent,
                )
                transactions.append(transaction)

                self._upsert_transaction(transaction)

            logger.info(
                "Fetched %s Stripe payment intents; %s contained an order ID",
                transaction_count,
                order_count,
            )
            refund_params = RefundListParams(
                created=RefundListParamsCreated(gte=start, lt=end),
                limit=100,
                expand=[
                    "data.payment_intent",
                    "data.balance_transaction",
                ],
            )
            stripe_refunds = client.v1.refunds.list(refund_params)
            refund_count = 0
            refunds: list[StripeRefund] = []
            for refund in stripe_refunds.auto_paging_iter():
                refund_model = StripeRefund(refund=refund)
                self._upset_refund(refund_model)
                refunds.append(refund_model)
                refund_count += 1
            logger.info("Fetched %s Stripe refunds", refund_count)
            return refunds
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error fetching Stripe transactions and refunds")
            return None

    def create_fee_report(self, start: datetime):
        """Create an asynchronous itemized fee report for one UTC calendar day."""
        if start.tzinfo is None or start.utcoffset() != timedelta(0):
            raise ValueError("Report start must be in UTC")
        if any((start.hour, start.minute, start.second, start.microsecond)):
            raise ValueError("Report start must be midnight UTC")
        api_key = os.environ.get("STRIPE_API_SECRET_KEY")
        if not api_key:
            raise RuntimeError("Stripe API key is not configured")
        client = stripe.StripeClient(api_key=api_key)
        report_type = client.v1.reporting.report_types.retrieve(
            "all_fees.incurred_at.itemized.2"
        )
        if (
            int((start + timedelta(days=1)).timestamp())
            > report_type.data_available_end
        ):
            raise FeeReportNotReady(report_type.data_available_end)
        return client.v1.reporting.report_runs.create(
            {
                "report_type": "all_fees.incurred_at.itemized.2",
                "parameters": {
                    "interval_start": int(start.timestamp()),
                    "interval_end": int((start + timedelta(days=1)).timestamp()),
                },
            }
        )

    def get_fee_report(self, report_id: str):
        """Import completed fee reports and return their status and import count."""
        api_key = os.environ.get("STRIPE_API_SECRET_KEY")
        if not api_key:
            raise RuntimeError("Stripe API key is not configured")
        client = stripe.StripeClient(api_key=api_key)
        report = client.v1.reporting.report_runs.retrieve(report_id)
        result = report.to_dict()
        account = client.v1.accounts.retrieve_current().id
        parameters = result["parameters"]
        audit = {
            "report_id": report_id, "account": account,
            "start": datetime.fromtimestamp(
                parameters["interval_start"], timezone.utc).replace(tzinfo=None),
            "end": datetime.fromtimestamp(
                parameters["interval_end"], timezone.utc).replace(tzinfo=None),
            "status": report.status, "read": 0, "imported": 0, "skipped": 0,
            "unresolved": 0, "error": None,
        }
        if report.status == "succeeded":
            audit["status"] = "importing"
        self._record_fee_import(audit)
        try:
            if report.status == "succeeded":
                result["rows_upserted"] = self._upsert_fee_report(
                    self.get_fee_report_csv(report.result.id), client, account, audit
                )
                audit["status"] = "succeeded"
                result["import_counts"] = {
                    key: audit[key] for key in ("read", "imported", "skipped", "unresolved")
                }
            elif report.status == "failed":
                audit["error"] = str(result.get("error") or "Stripe report failed")
        except Exception as error:
            audit.update(status="failed", error=str(error))
            self._record_fee_import(audit)
            raise
        self._record_fee_import(audit)
        return result

    @staticmethod
    def _record_fee_import(data):
        """Persist import outcome separately from Stripe's report generation status."""
        db_update("""INSERT INTO StripeFeeReportImports
            (ReportId, StripeAccount, IntervalStart, IntervalEnd, Status,
             RowsRead, RowsImported, RowsSkipped, RowsUnresolved, Error, ImportedAt)
            VALUES (%(report_id)s, %(account)s, %(start)s, %(end)s, %(status)s,
                    %(read)s, %(imported)s, %(skipped)s, %(unresolved)s, %(error)s,
                    IF(%(status)s='succeeded', UTC_TIMESTAMP(), NULL))
            ON DUPLICATE KEY UPDATE Status=VALUES(Status), RowsRead=VALUES(RowsRead),
                RowsImported=VALUES(RowsImported), RowsSkipped=VALUES(RowsSkipped),
                RowsUnresolved=VALUES(RowsUnresolved), Error=VALUES(Error),
                ImportedAt=VALUES(ImportedAt), LastUpdated=UTC_TIMESTAMP()""", data)

    def _upsert_fee_report(self, content: bytes, client=None, account=None, counts=None):
        """Import decimal fee amounts and preserve distinct rows with shared Stripe IDs."""
        reader = csv.DictReader(StringIO(content.decode("utf-8-sig")), strict=True)
        if not set(FEE_COLUMNS).issubset(reader.fieldnames or []):
            raise ValueError("Stripe fee report is missing required columns")
        rows = {}
        counts = counts if counts is not None else {}
        counts.update(read=0, imported=0, skipped=0, unresolved=0)
        for row in reader:
            counts["read"] += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed Stripe fee report row")
            data = {
                column: row[header] or None for header, column in FEE_COLUMNS.items()
            }
            try:
                for column in ("Amount", "Tax"):
                    data[column] = Decimal(data[column] or "0")
                    if not data[column].is_finite():
                        raise ValueError("Non-finite fee amount")
                if not row["amount"] or not data["Currency"]:
                    raise ValueError("Missing fee amount or currency")
                for column in (
                    "BalanceTransactionCreated",
                    "IncurredAt",
                    "FeeTransactionCreated",
                    "SettledAt",
                ):
                    if data[column]:
                        data[column] = datetime.strptime(
                            data[column], "%Y-%m-%d %H:%M:%S"
                        )
            except (ValueError, InvalidOperation) as error:
                raise ValueError("Invalid Stripe fee report value") from error
            # Stripe's fee/balance IDs can represent many itemized fees. Hash the
            # full normalized row so identical rows share one database key.
            canonical = {
                key: (
                    (
                        format(value, "f").rstrip("0").rstrip(".")
                        if value.as_tuple().exponent < 0
                        else format(value, "f")
                    )
                    if isinstance(value, Decimal)
                    else value
                )
                for key, value in data.items()
            }
            signature = json.dumps(canonical, sort_keys=True, default=str)
            data["FeeRowKey"] = hashlib.sha256(
                json.dumps([signature, 0]).encode("utf-8")
            ).hexdigest()
            rows[data["FeeRowKey"]] = data
        counts["skipped"] = counts["read"] - len(rows)
        resolved = {}
        for data in rows.values():
            attribution = (data["IncurredByType"], data["IncurredBy"])
            if attribution not in resolved:
                kind, source_id = attribution
                payment_id = source_id if kind == "payment_intent" else None
                if source_id and client and kind in ("charge", "refund"):
                    resource = (client.v1.charges if kind == "charge" else client.v1.refunds)
                    source = resource.retrieve(source_id)
                    payment_id = source.payment_intent
                    if payment_id is not None and not isinstance(payment_id, str):
                        payment_id = payment_id.id
                resolved[attribution] = payment_id
            data["PaymentIntentId"] = resolved[attribution]
            data["StripeAccount"] = account
            if not data["PaymentIntentId"]:
                counts["unresolved"] += 1
            columns = ", ".join(data)
            placeholders = ", ".join(f"%({column})s" for column in data)
            updates = ", ".join(
                f"{column}=VALUES({column})" for column in data if column != "FeeRowKey"
            )
            db_insert(
                f"INSERT INTO StripeFees ({columns}) VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {updates}, LastUpdated=CURRENT_TIMESTAMP",
                data,
            )
            counts["imported"] += 1
        for payment_intent_id in sorted({
            row["PaymentIntentId"] for row in rows.values() if row["PaymentIntentId"]
        }):
            # Recalculate from all stored reports, including overlapping imports.
            # No matching Radar rows leaves the existing unknown value untouched.
            db_update("""UPDATE StripePaymentIntents pi
                JOIN (
                    SELECT PaymentIntentId, SUM(Amount + Tax) AS RadarFee
                    FROM StripeFees
                    WHERE IncurredByType IN ('payment_intent', 'charge')
                        AND PaymentIntentId = %(payment_intent_id)s
                        AND (LOCATE('radar', LOWER(FeatureName)) > 0
                             OR LOWER(Product) = 'radar')
                    GROUP BY PaymentIntentId
                ) fees ON fees.PaymentIntentId = pi.PaymentIntentId
                SET pi.RadarFee = fees.RadarFee""",
                {"payment_intent_id": payment_intent_id})
        return len(rows)

    def get_fee_report_csv(self, file_id: str):
        """Download a generated report without exposing Stripe credentials to callers."""
        api_key = os.environ.get("STRIPE_API_SECRET_KEY")
        if not api_key:
            raise RuntimeError("Stripe API key is not configured")
        # Use Stripe's fixed file host rather than forwarding credentials to a URL.
        with requests.get(
            f"https://files.stripe.com/v1/files/{quote(file_id, safe='')}/contents",
            auth=(api_key, ""),
            timeout=60,
            allow_redirects=False,
        ) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise requests.HTTPError("Unexpected Stripe file response")
            return response.content

    def _upset_refund(self, refund: StripeRefund):
        """Persist refund details, refreshing status and metadata on repeat imports."""
        data = {
            "StripeRefundId": refund.stripe_id,
            "PaymentIntentId": refund.payment_intent_id or "",
            "Amount": refund.amount,
            "Currency": refund.currency,
            "Status": refund.status or "",
            "Reason": refund.reason,
            "CreatedAt": datetime.fromtimestamp(
                refund.created_at, timezone.utc
            ).replace(tzinfo=None),
            "OrderId": refund.order_id or "",
            "CustomerName": refund.customer_name or "",
            "CustomerEmail": refund.customer_email or "",
            "CustomerPhone": refund.customer_phone or "",
            "SourceUrl": refund.source_url or "",
            "EventId": refund.event_id or "",
            "EventName": refund.event_name or "",
            "OriginalAmount": refund.original_amount,
            "ExchangeRate": refund.exchange_rate,
        }
        # Identifiers come only from the fixed mapping above, never Stripe input.
        columns = ", ".join(data)
        placeholders = ", ".join(f"%({column})s" for column in data)
        updates = ", ".join(
            f"{column}=VALUES({column})"
            for column in data
            if column != "StripeRefundId"
        )
        db_insert(
            f"INSERT INTO StripeRefunds ({columns}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {updates}, LastUpdated=CURRENT_TIMESTAMP",
            data,
        )

    def _upsert_transaction(self, transaction: StripeTransaction):
        """Resolve the native order within its account and insert a successful intent."""
        orders = db_query_all(
            """SELECT DISTINCT tso.Id, tso.OrderId, tso.EventId, tpo.TicketPartnerOrderId
            FROM TicketSocketOrders tso
            JOIN TicketSocketEvents tse ON tse.Id=tso.TicketSocketEventId
            JOIN SellerEventCategory sec
                ON sec.SellerEventCategoryId=tse.SellerEventCategoryId
            LEFT JOIN TicketPartnerEvents tpe
                ON tpe.TicketPartnerId=2
                AND tpe.PartnerEventId=tso.TicketSocketEventId
            JOIN Events ev ON ev.EventId=tpe.EventId
            LEFT JOIN TicketPartnerOrders tpo
                ON tpo.TicketPartnerEventId=tpe.TicketPartnerEventId
                AND tpo.PartnerOrderId=tso.Id
            WHERE tso.OrderId=%(order_id)s AND sec.TicketSocketId=%(ticket_socket_id)s
                AND """
            + ELIGIBLE_EVENTS_SQL,
            {
                "order_id": transaction.order_id,
                "ticket_socket_id": transaction.ticket_socket_id,
            },
        )
        # Keep unmatched/ambiguous transactions without assigning the wrong order.
        partner_order_id = (
            orders[0]["TicketPartnerOrderId"] if len(orders) == 1 else None
        )
        if partner_order_id is None:
            logger.warning(
                "Stripe transaction %s matched %s order rows for order %s in TicketSocket %s",
                transaction.stripe_id,
                len(orders),
                transaction.order_id,
                transaction.ticket_socket_id,
            )
            return
        transaction.event_id = orders[0]["EventId"]

        data = {
            "stripe_id": transaction.stripe_id,
            "partner_order_id": partner_order_id,
            "event_name": transaction.event_name or "",
            "description": transaction.description or "",
            "date_received": datetime.fromtimestamp(
                transaction.date_received, timezone.utc
            ).replace(tzinfo=None),
            "total": transaction.total,
            "insurance": transaction.insurance,
            "processing_fee": transaction.processing_fee,
            "customer_name": transaction.customer_name or "",
            "customer_email": transaction.customer_email or "",
            "customer_phone": transaction.customer_phone or "",
            "currency": transaction.currency,
            "source_url": transaction.source_url or "",
            "exchange_rate": transaction.exchange_rate,
            "status": transaction.status,
            "payment_method": transaction.payment_method or "",
            "stripe_account": transaction.stripe_account or "",
            "application_fee": transaction.application_fee,
            "insurance_verified": int(transaction.insurance_verified),
            "processing_fee_currency": transaction.processing_fee_currency,
            "native_event_id": transaction.event_id,
            "native_order_id": transaction.order_id,
        }
        # Ordinary imports preserve successful rows, including concurrent imports.
        # Explicit reconciliation refreshes only fee metadata and payment method.
        duplicate_update = "PaymentIntentId=PaymentIntentId"
        if self.refresh_financials:
            duplicate_update = """ProcessingFee=VALUES(ProcessingFee),
                ProcessingFeeCurrency=VALUES(ProcessingFeeCurrency),
                ApplicationFee=VALUES(ApplicationFee), Insurance=VALUES(Insurance),
                InsuranceVerified=VALUES(InsuranceVerified), PaymentMethod=VALUES(PaymentMethod)"""
        db_insert(
            """INSERT INTO StripePaymentIntents (
                PaymentIntentId, TicketPartnerOrderId, EventName, Description,
                DateReceived, Total, Insurance, ProcessingFee, CustomerName,
                CustomerEmail, CustomerPhone, Currency, SourceUrl, ExchangeRate,
                Status, PaymentMethod, StripeAccount, ApplicationFee,
                InsuranceVerified, ProcessingFeeCurrency, NativeEventId, NativeOrderId
            ) VALUES (
                %(stripe_id)s, %(partner_order_id)s, %(event_name)s, %(description)s,
                %(date_received)s, %(total)s, %(insurance)s, %(processing_fee)s,
                %(customer_name)s, %(customer_email)s, %(customer_phone)s,
                %(currency)s, %(source_url)s, %(exchange_rate)s,
                %(status)s, %(payment_method)s, %(stripe_account)s, %(application_fee)s,
                %(insurance_verified)s, %(processing_fee_currency)s, %(native_event_id)s,
                %(native_order_id)s
            ) ON DUPLICATE KEY UPDATE """ + duplicate_update,
            data,
        )
