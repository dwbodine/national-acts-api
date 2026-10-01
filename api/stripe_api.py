"""
Stripe API routes
"""

import logging
import os
from flask import Blueprint, request

from common.stripe_service import StripeService
from common.utility import (
    convert_to_json,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)

stripe_api = Blueprint("stripe_api", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@stripe_api.route("/stripe/transactions")
def stripe_transactions():
    """
    Handle Stripe transaction requests.
    """

    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(
        os.environ.get("STRIPE_API_PUBLIC_KEY")
    )

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    logger.info(
        "Stripe transactions GET fields: %s",
        request.args.to_dict(flat=False),
    )

    service = StripeService()

    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)

    result = service.get_payment_intents(start=start, end=end)

    return convert_to_json(result)
