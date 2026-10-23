"""
Models for Stripe API
"""

from decimal import Decimal

import stripe

# Merchant confirmed this TicketSocket Connect application's fees are insurance.
TICKETSOCKET_INSURANCE_APPLICATION = "ca_AagDRnyDZMGwD09hWMO5LGWU3ASOyea3"


class StripeTransaction:
    """
    Transaction model
    """

    def __init__(
        self,
        order_id: str,
        status: str,
        payment_intent: stripe.PaymentIntent,
    ):
        self.stripe_id = payment_intent.id
        self.order_id = order_id
        self.status = status
        charge = payment_intent.latest_charge
        method_details = getattr(charge, "payment_method_details", None)
        self.payment_method = getattr(method_details, "type", None)
        if (
            not self.payment_method
            and len(payment_intent.payment_method_types or []) == 1
        ):
            self.payment_method = payment_intent.payment_method_types[0]
        self.stripe_account = (
            payment_intent.metadata["stripeAccount"]
            if "stripeAccount" in payment_intent.metadata
            else ""
        )
        self.event_id = (
            payment_intent.metadata["eventIds"]
            if "eventIds" in payment_intent.metadata
            else ""
        )
        self.event_name = (
            payment_intent.metadata["eventNames"]
            if "eventNames" in payment_intent.metadata
            else ""
        )
        self.description = payment_intent.description
        self.date_received = payment_intent.created
        self.total = payment_intent.amount / 100
        self.currency = payment_intent.currency
        self.application_fee = (
            (payment_intent.application_fee_amount / 100)
            if payment_intent.application_fee_amount is not None
            else 0.0
        )
        self.customer_name = (
            payment_intent.metadata["customerName"]
            if "customerName" in payment_intent.metadata
            else ""
        )
        self.customer_email = (
            payment_intent.metadata["customerEmail"]
            if "customerEmail" in payment_intent.metadata
            else ""
        )
        self.customer_phone = (
            payment_intent.metadata["customerPhone"]
            if "customerPhone" in payment_intent.metadata
            else ""
        )
        source_url = (
            payment_intent.metadata["domain"]
            if "domain" in payment_intent.metadata
            else ""
        )

        match source_url:
            case str() as url if url.startswith("europe"):
                self.source_url = "europe.nationalactsvip.com"
            case str() as url if url.startswith("tickets"):
                self.source_url = "tickets.nationalactsvip.com"
            case str() as url if url.startswith("australia"):
                self.source_url = "australia.nationalactsvip.com"
            case str() as url if url.startswith("japan"):
                self.source_url = "japan.nationalactsvip.com"
            case str() as url if url.find("savingabel") != -1:
                self.source_url = "secure.savingabelvip.com"
            case _:
                self.source_url = "secure.nationalactsvip.com"

        self.processing_fee = (
            (payment_intent.latest_charge.balance_transaction.fee / 100)
            if payment_intent.latest_charge
            and payment_intent.latest_charge.balance_transaction
            else 0.0
        )
        balance = getattr(charge, "balance_transaction", None)
        self.processing_fee_currency = getattr(balance, "currency", None)
        details = getattr(balance, "fee_details", None)
        application_details = [
            fee for fee in details or [] if fee.type == "application_fee"
        ]
        self.insurance_verified = (
            self.application_fee == 0
            or bool(application_details)
            and all(
                fee.application == TICKETSOCKET_INSURANCE_APPLICATION
                for fee in application_details
            )
        )
        self.insurance = self.application_fee if self.insurance_verified else None
        if details is not None:
            self.processing_fee = sum(
                (
                    Decimal(str(fee.amount)) / 100
                    for fee in details
                    if fee.type == "stripe_fee"
                ),
                Decimal(0),
            )
        elif self.processing_fee >= self.application_fee:
            self.processing_fee -= self.application_fee
        self.exchange_rate = (
            payment_intent.latest_charge.balance_transaction.exchange_rate
            if payment_intent.latest_charge
            and payment_intent.latest_charge.balance_transaction
            and payment_intent.latest_charge.balance_transaction.exchange_rate
            is not None
            else 0.0
        )

    stripe_id: str = ""
    order_id: str = ""
    event_id: str = ""
    event_name: str = ""
    description: str = ""
    date_received: str = ""
    total: float = 0.0
    currency: str = ""
    insurance: float | None = None
    application_fee: float = 0.0
    insurance_verified: bool = False
    processing_fee_currency: str | None = None
    processing_fee: float = 0.0
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    source_url: str = ""
    exchange_rate: float = 0.0
    status: str = ""
    payment_method: str = ""
    stripe_account: str = ""


class StripeRefund:
    """
    Refund model
    """

    def __init__(
        self,
        refund: stripe.Refund,
    ):
        self.stripe_id = refund.id
        self.amount = refund.amount / 100
        self.currency = refund.currency
        self.status = refund.status
        self.reason = refund.reason
        self.created_at = refund.created
        payment_intent = refund.payment_intent
        if isinstance(payment_intent, str):
            self.payment_intent_id = payment_intent
        elif payment_intent is not None:
            self.payment_intent_id = (
                payment_intent.id if payment_intent is not None else ""
            )
            self.original_amount = payment_intent.amount / 100
            self.order_id = (
                payment_intent.metadata["orderId"]
                if "orderId" in payment_intent.metadata
                else ""
            )
            self.customer_name = (
                payment_intent.metadata["customerName"]
                if "customerName" in payment_intent.metadata
                else ""
            )
            self.customer_email = (
                payment_intent.metadata["customerEmail"]
                if "customerEmail" in payment_intent.metadata
                else ""
            )
            self.customer_phone = (
                payment_intent.metadata["customerPhone"]
                if "customerPhone" in payment_intent.metadata
                else ""
            )
            self.source_url = (
                payment_intent.metadata["domain"]
                if "domain" in payment_intent.metadata
                else ""
            )
            self.event_id = (
                payment_intent.metadata["eventIds"]
                if "eventIds" in payment_intent.metadata
                else ""
            )
            self.event_name = (
                payment_intent.metadata["eventNames"]
                if "eventNames" in payment_intent.metadata
                else ""
            )
        balance_transaction = refund.balance_transaction
        if balance_transaction is not None and not isinstance(balance_transaction, str):
            self.exchange_rate = (
                balance_transaction.exchange_rate
                if balance_transaction.exchange_rate is not None
                else 0.0
            )

    stripe_id: str = ""
    payment_intent_id: str = ""
    amount: float = 0.0
    currency: str = ""
    status: str = ""
    reason: str = ""
    created_at: str = ""
    order_id: str = ""
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    source_url: str = ""
    event_id: str = ""
    event_name: str = ""
    original_amount: float = 0.0
    exchange_rate: float = 0.0
