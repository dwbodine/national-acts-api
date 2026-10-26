"""
Stripe API routes
"""

import logging
import csv
import os
from io import StringIO
from datetime import date, datetime, time, timezone
import stripe
import requests
from flask import Blueprint, Response, request
from flask_jwt_extended import jwt_required

from common.stripe_service import FeeReportNotReady, StripeService
from common.common_api import is_admin_logged_in
from common.stripe_reconciliation_service import StripeReconciliationService
from common.stripe_payment_intent_service import PaymentIntentConflict, StripePaymentIntentService
from common.utility import (
    convert_to_json,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)

stripe_api = Blueprint("stripe_api", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@stripe_api.route("/stripe/payment-intents/update", methods=["POST"])
@jwt_required()
def update_payment_intent():
    """Explicitly save one local payment intent, allowing administrator reconciliation."""
    if not is_admin_logged_in():
        return {"msg": "Unauthorized"}, 401
    try:
        result = StripePaymentIntentService().save(request.get_json(silent=True))
    except PaymentIntentConflict as error:
        return {"msg": str(error)}, 409
    except (TypeError, ValueError) as error:
        return {"msg": str(error)}, 400
    return result, 201 if result["created"] else 200


@stripe_api.route("/stripe/payment-intents/missing", methods=["GET"])
@jwt_required()
def missing_payment_intents():
    """Return internal missing-payment details as paged JSON or a CSV download."""
    if not is_admin_logged_in():
        return {"msg": "Unauthorized"}, 401
    try:
        start_value = request.args.get("startDate", request.args.get("start_date"))
        end_value = request.args.get("endDate", request.args.get("end_date"))
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
        if (start >= end or start.isoformat() != start_value
                or end.isoformat() != end_value):
            raise ValueError("Invalid date range")
        account_value = request.args.get("ticketSocketId", request.args.get("ticket_socket_id"))
        account = int(account_value) if account_value is not None else None
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
        output_format = request.args.get("format", "json")
        if (account is not None and account <= 0 or not 1 <= limit <= 1000
                or offset < 0 or output_format not in ("json", "csv")):
            raise ValueError("Invalid report options")
    except (KeyError, TypeError, ValueError):
        return {"msg": "Provide YYYY-MM-DD start_date/end_date (end exclusive), "
                "(startDate/endDate also accepted), positive ticket_socket_id, "
                "limit 1-1000, offset >= 0, format json/csv"}, 400
    report = StripeReconciliationService().get_missing_payments(
        start, end, account, None if output_format == "csv" else limit,
        0 if output_format == "csv" else offset,
    )
    if output_format == "json":
        return report
    columns = ["TicketSocketOrderId", "NativeOrderId", "NativeEventId", "TicketSocketId",
               "AccountName", "TicketPartnerOrderId", "EventId", "EventTitle", "EventDate",
               "SellerId", "Venue", "City", "State", "PurchaseDate", "IsManualTransfer",
               "CustomerName", "CustomerEmail",
               "CustomerProcessingFee"]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for order in report["orders"]:
        # Customer/event text is untrusted when opened in a spreadsheet.
        safe = {key: "'" + value if isinstance(value, str)
                and value.lstrip().startswith(("=", "+", "-", "@")) else value
                for key, value in order.items()}
        writer.writerow(safe)
    return Response(output.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="missing-payments-{start}-{end}.csv"',
    })


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
