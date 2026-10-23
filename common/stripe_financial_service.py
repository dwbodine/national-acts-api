"""Bulk local Stripe financial enrichment without changing ticket accounting."""

from datetime import date, datetime
from decimal import Context, Decimal

from common.db import db_convert_list_to_parameters, db_query_all

MONEY_CONTEXT = Context(prec=50)


def json_row(row):
    """Preserve database precision and serialize dates for existing JSON encoders."""
    return {
        key: str(value) if isinstance(value, Decimal) else
        value.isoformat() if isinstance(value, (date, datetime)) else value
        for key, value in row.items()
    }


def attach_financials(target, payments, refunds, fees):
    """Keep ticket totals untouched and calculate Stripe amounts per currency."""
    target.stripe_payments = [json_row(row) for row in payments]
    target.stripe_refunds = [json_row(row) for row in refunds]
    target.stripe_fees = [json_row(row) for row in fees]
    buckets = {}
    payment_currencies = set()
    for rows, field, amount_field in (
        (payments, "gross", "Total"), (refunds, "refunded", "Amount"),
        (fees, "reported_fees", "Amount"),
    ):
        for row in rows:
            if field != "reported_fees" and row.get("Status") != "succeeded":
                continue
            currency = row["Currency"].lower()
            totals = buckets.setdefault(currency, {
                "gross": Decimal(0), "refunded": Decimal(0), "reported_fees": Decimal(0),
            })
            value = Decimal(str(row[amount_field]))
            if field == "reported_fees":
                value = MONEY_CONTEXT.add(value, Decimal(str(row.get("Tax") or 0)))
            elif field == "gross":
                payment_currencies.add(currency)
            totals[field] = MONEY_CONTEXT.add(totals[field], value)
    payment_currency_by_id = {row["PaymentIntentId"]: row["Currency"].lower() for row in payments}
    mismatch = any(
        row["Currency"].lower() != payment_currency_by_id.get(row[key])
        for rows, key in ((refunds, "PaymentIntentId"), (fees, "IncurredBy"))
        for row in rows
        if key == "IncurredBy" or row.get("Status") == "succeeded"
    )
    target.stripe_totals_by_currency = {}
    for currency, totals in buckets.items():
        net = MONEY_CONTEXT.subtract(
            MONEY_CONTEXT.subtract(totals["gross"], totals["refunded"]), totals["reported_fees"]
        )
        target.stripe_totals_by_currency[currency] = {
            **{key: str(value) for key, value in totals.items()},
            "net": str(net) if not mismatch and currency in payment_currencies else None,
        }
    single = next(iter(target.stripe_totals_by_currency.values())) if len(buckets) == 1 else {}
    target.stripe_currency = next(iter(buckets)) if len(buckets) == 1 else None
    target.stripe_gross = single.get("gross")
    target.stripe_refunded = single.get("refunded")
    target.stripe_reported_fees = single.get("reported_fees")
    target.stripe_net = single.get("net")
    target.stripe_currency_mismatch = mismatch
    target.stripe_fees_available = bool(fees)
    # The report importer currently stores only payment-intent-attributed fees,
    # and Stripe can publish additional fee rows later.
    target.stripe_net_is_provisional = True
    target.stripe_financials_loaded = True


class StripeFinancialService:
    """Read the three Stripe tables independently to avoid multiplying child rows."""

    def get_financials(self, partner_order_ids=None):
        """Return payment rows with nullable mappings; optionally scope to known orders."""
        data = {}
        where = ""
        if partner_order_ids is not None:
            if not partner_order_ids:
                return [], [], []
            placeholders = db_convert_list_to_parameters(partner_order_ids, data, "order")
            where = " WHERE pi.TicketPartnerOrderId IN " + placeholders
        source = """ FROM StripePaymentIntents pi
            LEFT JOIN TicketPartnerOrders po
                ON po.TicketPartnerOrderId=pi.TicketPartnerOrderId"""
        payments = db_query_all("SELECT pi.*" + source + where, data)
        refunds = db_query_all(
            "SELECT r.* FROM StripeRefunds r LEFT JOIN StripePaymentIntents pi "
            "ON pi.PaymentIntentId=r.PaymentIntentId" + where, data,
        )
        fees = db_query_all(
            "SELECT f.* FROM StripeFees f LEFT JOIN StripePaymentIntents pi "
            "ON pi.PaymentIntentId=f.IncurredBy AND f.IncurredByType='payment_intent'"
            + (where + " AND " if where else " WHERE ")
            + "f.IncurredByType='payment_intent'", data,
        )
        return payments, refunds, fees

    def enrich_events(self, events):
        """Attach financials to all loaded orders using three database queries total."""
        ids = sorted({
            order.ticket_partner_order_id for event in events for order in event.orders
            if order.ticket_partner_order_id
        })
        payments, refunds, fees = self.get_financials(ids)
        by_order = {}
        by_payment = {}
        for payment in payments:
            order_id = payment["TicketPartnerOrderId"]
            by_order.setdefault(order_id, [[], [], []])[0].append(payment)
            by_payment[payment["PaymentIntentId"]] = order_id
        for rows, key, position in ((refunds, "PaymentIntentId", 1), (fees, "IncurredBy", 2)):
            for row in rows:
                order_id = by_payment.get(row[key])
                if order_id is not None:
                    by_order[order_id][position].append(row)
        for event in events:
            event_rows = [[], [], []]
            seen = set()
            for order in event.orders:
                rows = by_order.get(order.ticket_partner_order_id, [[], [], []])
                attach_financials(order, *rows)
                if order.ticket_partner_order_id not in seen:
                    for aggregate, children in zip(event_rows, rows):
                        aggregate.extend(children)
                    seen.add(order.ticket_partner_order_id)
            attach_financials(event, *event_rows)
