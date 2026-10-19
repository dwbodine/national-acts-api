"""
Stripe API module
"""

from datetime import datetime, timezone
import logging
import os

import stripe
from stripe.params import (
    PaymentIntentListParams,
    PaymentIntentListParamsCreated,
    RefundListParams,
    RefundListParamsCreated,
)

from common.db import db_insert, db_query_all
from common.models.stripe import StripeRefund, StripeTransaction

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class StripeService:
    """
    Service to interact with Stripe API
    """

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
                order_id = metadata["orderId"] if "orderId" in metadata else None

                if not order_id:
                    continue

                status = payment_intent.status

                if status != "succeeded":
                    logger.warning(
                        "Payment intent %s for order %s has status %s",
                        payment_intent.id,
                        order_id,
                        status,
                    )
                    continue

                order_count += 1

                transaction = StripeTransaction(
                    order_id=order_id, status=status, payment_intent=payment_intent
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
                expand=["data.payment_intent", "data.balance_transaction", "data.charge.balance_transaction"],
            )
            stripe_refunds = client.v1.refunds.list(refund_params)
            refund_count = 0
            refunds: list[StripeRefund] = []
            for refund in stripe_refunds.auto_paging_iter():
                refunds.append(StripeRefund(refund=refund))
                refund_count += 1
            logger.info("Fetched %s Stripe refunds", refund_count)
            return refunds
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error fetching Stripe transactions and refunds")
            return None

    def _upsert_transaction(self, transaction: StripeTransaction):
        """Insert a successful intent, preserving any previously stored transaction."""
        orders = db_query_all(
            """SELECT DISTINCT tpo.TicketPartnerOrderId
            FROM TicketSocketOrders tso
            JOIN TicketPartnerEvents tpe
                ON tpe.TicketPartnerId=2
                AND tpe.PartnerEventId=tso.TicketSocketEventId
            JOIN TicketPartnerOrders tpo
                ON tpo.TicketPartnerEventId=tpe.TicketPartnerEventId
                AND tpo.PartnerOrderId=tso.Id
            WHERE tso.OrderId=%(order_id)s""",
            {"order_id": transaction.order_id},
        )
        # Keep unmatched/ambiguous transactions without assigning the wrong order.
        partner_order_id = (
            orders[0]["TicketPartnerOrderId"] if len(orders) == 1 else None
        )
        if partner_order_id is None:
            logger.warning(
                "Stripe transaction %s matched %s partner orders for order %s",
                transaction.stripe_id,
                len(orders),
                transaction.order_id,
            )

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
        }
        # All stored rows are successful. The duplicate branch must not refresh
        # amounts, order links, or LastUpdated, including concurrent imports.
        db_insert(
            """INSERT INTO StripeTransactions (
                StripeTransactionId, TicketPartnerOrderId, EventName, Description,
                DateReceived, Total, Insurance, ProcessingFee, CustomerName,
                CustomerEmail, CustomerPhone, Currency, SourceUrl, ExchangeRate,
                Status, PaymentMethod, StripeAccount
            ) VALUES (
                %(stripe_id)s, %(partner_order_id)s, %(event_name)s, %(description)s,
                %(date_received)s, %(total)s, %(insurance)s, %(processing_fee)s,
                %(customer_name)s, %(customer_email)s, %(customer_phone)s,
                %(currency)s, %(source_url)s, %(exchange_rate)s,
                %(status)s, %(payment_method)s, %(stripe_account)s
            ) ON DUPLICATE KEY UPDATE StripeTransactionId=StripeTransactionId""",
            data,
        )
