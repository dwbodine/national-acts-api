"""
Models for Stripe API
"""

import stripe


class StripeTransaction:
    """
    Transaction model
    """

    def __init__(
        self,
        order_id: str,
        payment_intent: stripe.PaymentIntent,
    ):
        self.stripe_id = payment_intent.id
        self.order_id = order_id
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
        self.insurance = (
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
        self.source_url = (
            payment_intent.metadata["domain"]
            if "domain" in payment_intent.metadata
            else ""
        )
        
        self.processing_fee = (
            (payment_intent.latest_charge.balance_transaction.fee / 100)
            if payment_intent.latest_charge
            and payment_intent.latest_charge.balance_transaction
            else 0.0
        )
        self.exchange_rate = (
            (payment_intent.latest_charge.balance_transaction.exchange_rate / 100)
            if payment_intent.latest_charge
            and payment_intent.latest_charge.balance_transaction
            and payment_intent.latest_charge.balance_transaction.exchange_rate is not None
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
    insurance: float = 0.0
    processing_fee: float = 0.0
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    source_url: str = ""
    exchange_rate: float = 0.0
