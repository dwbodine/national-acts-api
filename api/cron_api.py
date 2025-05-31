"""
Cron API routes
"""

import os
from datetime import datetime

from flask import Blueprint, request

from common.update_service import UpdateService
from common.sender_api_service import SenderApiService
from common.utility import (
    convert_to_json,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)

cron_api = Blueprint("cron_api", __name__)


# BEGIN CRON JOB ROUTES
@cron_api.route("/cron/updateAllEventsFromService")
def update_all_events_from_service():
    """
    API for cron to update events/orders/tickets from TicketSocket
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = UpdateService()
    results = service.update_all_events_from_ticket_socket()
    return convert_to_json(results)


@cron_api.route("/cron/updateAllExchangeRates")
def update_all_exchange_rates():
    """
    API for cron to update exchange rates from Stripe
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = UpdateService()
    rates = service.update_all_exchange_rates_from_stripe()
    return convert_to_json(rates)


@cron_api.route("/cron/updateHistoricalExchangeRate/<string:exchange_date_str>")
def update_historical_exchange_rate(exchange_date_str: str):
    """
    API for cron to update historical exchange rate from Stripe
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if exchange_date_str is None or len(exchange_date_str) == 0:
        return {"msg": "Bad Request"}, 400

    exchange_date: datetime = datetime.strptime(exchange_date_str, "%Y-%m-%d")
    unix_time: int = int(exchange_date.timestamp())

    service = UpdateService()
    rates = service.update_all_exchange_rates_from_stripe(unix_time, True)
    return convert_to_json(rates)


@cron_api.route("/cron/updateHistoricalEventData")
def update_historical_event_data():
    """
    API for cron to update historical event data from TS
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)

    if start is None or end is None or start <= 0 or end <= 0:
        return {"msg": "Bad Request"}, 400

    service = UpdateService()
    results = service.update_historical_events_from_ticket_socket(start, end)
    return convert_to_json(results)


@cron_api.route("/cron/updateSenderApiSubscribers")
def update_subscribers():
    """
    API for cron to update subscriber data in Sender API
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SenderApiService()
    result = service.update_sender_subscribers()
    return convert_to_json(result)


@cron_api.route("/cron/getSenderApiSubscribersCsv")
def get_subscribers_from_database():
    """
    API for cron to get subscriber data in Sender API in CSV form
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SenderApiService()
    result = service.get_sender_subscribers_csv()
    return convert_to_json(result)


@cron_api.route("/cron/getMissingSenderApiSubscribersCsv")
def get_missing_subscribers():
    """
    API for cron to get subscribers that are missing in Sender API
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SenderApiService()
    result = service.get_missing_subscribers_csv()
    return convert_to_json(result)


@cron_api.route("/cron/formatAllPhoneNumbers")
def format_phones():
    """
    API for cron to format all existing phone numbers
    """
    # secured by internal api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("CRON_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = UpdateService()
    result = service.format_all_phone_numbers()
    return convert_to_json(result)
