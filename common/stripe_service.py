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
)

from common.models.stripe import StripeTransaction

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class StripeService:
    """
    Service to interact with Stripe API
    """

    def get_payment_intents(self, start: int = None, end: int = None):
        """
        Get payment intents from Stripe API within the specified date range.
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

                order_id = payment_intent.metadata["orderId"]

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
                    order_id=order_id, payment_intent=payment_intent
                )
                transactions.append(transaction)

                # Upsert into your database here

            logger.info(
                "Fetched %s Stripe payment intents; %s contained an order ID",
                transaction_count,
                order_count,
            )
            return transactions
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Error fetching payment intents")
            return None
