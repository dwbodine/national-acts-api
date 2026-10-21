"""
Stripe API routes
"""

import logging
import csv
import os
from datetime import date, datetime, time, timezone
import stripe
import requests
from flask import Blueprint, request

from common.stripe_service import FeeReportNotReady, StripeService
from common.utility import (
    convert_to_json,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)

stripe_api = Blueprint("stripe_api", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@stripe_api.route("/stripe/fees/report", methods=["POST"])
def stripe_fee_report():
    """Start a fee report for midnight UTC through the following midnight."""
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(
        os.environ.get("STRIPE_API_PUBLIC_KEY")
    )
    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401
    payload = request.get_json(silent=True)
    start_date = payload.get("start_date") if isinstance(payload, dict) else None
    try:
        if not isinstance(start_date, str):
            raise ValueError("Missing start date")
        parsed = date.fromisoformat(start_date)
        if parsed.isoformat() != start_date:
            raise ValueError("Invalid date format")
    except ValueError:
        return {"msg": "start_date must be YYYY-MM-DD (midnight UTC)"}, 400
    if not os.environ.get("STRIPE_API_SECRET_KEY"):
        return {"msg": "Stripe API key is not configured"}, 503
    try:
        report = StripeService().create_fee_report(
            datetime.combine(parsed, time.min, tzinfo=timezone.utc)
        )
    except FeeReportNotReady as error:
        return {"msg": str(error), "available_until": error.available_until}, 409
    except stripe.StripeError:
        logger.exception("Error creating Stripe fee report")
        return {"msg": "Stripe could not create the fee report"}, 502
    return report.to_dict(), 202


@stripe_api.route("/stripe/fees/report/<report_id>", methods=["GET"])
def get_stripe_fee_report(report_id):
    """Import completed reports and return their status and imported row count."""
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(
        os.environ.get("STRIPE_API_PUBLIC_KEY")
    )
    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401
    if not report_id.startswith("frr_"):
        return {"msg": "Invalid report ID"}, 400
    if not os.environ.get("STRIPE_API_SECRET_KEY"):
        return {"msg": "Stripe API key is not configured"}, 503
    try:
        service = StripeService()
        result = service.get_fee_report(report_id)
    except (
        stripe.StripeError,
        requests.RequestException,
        ValueError,
        csv.Error,
    ) as error:
        if isinstance(error, stripe.InvalidRequestError) and (
            error.http_status == 404 or error.code == "resource_missing"
        ):
            return {"msg": "Report not found"}, 404
        logger.exception("Error retrieving Stripe fee report")
        return {"msg": "Stripe could not retrieve the fee report"}, 502
    return result, 200


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

    result = service.get_transactions(start=start, end=end)

    return convert_to_json(result)
