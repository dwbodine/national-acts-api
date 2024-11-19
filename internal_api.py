"""
Internal API routes
"""

import os
from datetime import datetime
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common_api import get_user_from_jwt

from common.daily_order_service import DailyOrderService
from common.order_service import OrderService
from common.data_refresh_service import DataRefreshService
from common.ticket_socket_service import TicketSocketService, get_all_accounts
from common.user_activity_service import UserActivityService
from common.models.national_acts import VipOrder
from common.utility import (
    convert_to_json,
    send_email,
)

internal_api = Blueprint("internal_api", __name__)


# BEGIN INTERNAL ROUTES
@internal_api.route("/internal/accounts")
def get_accounts():
    """
    API method to fetch account
    """
    accounts = get_all_accounts()
    return convert_to_json(accounts)


@internal_api.route("/internal/<int:ticket_socket_id>/categories")
def get_categories(ticket_socket_id: int):
    """
    API method to fetch categories
    """
    service = TicketSocketService(ticket_socket_id)
    categories = service.get_categories()
    return convert_to_json(categories)


@internal_api.route("/internal/getEventsFromService/<int:seller_id>")
def get_events_from_service(seller_id: int = None):
    """
    API method to fetch methods from TicketSocket by sellerId
    """
    service = DataRefreshService()
    start: int = None
    end: int = None
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))

    if seller_id is not None:
        results = service.retrieve_ticket_socket_events_for_update(
            seller_id, start, end
        )
    else:
        results = None
    return convert_to_json(results)


@internal_api.route("/internal/getUpdateHistory")
@jwt_required()
def get_update_history():
    """
    API method to fetch TS refresh history
    """
    user = get_user_from_jwt()
    if user is None or user.is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = DataRefreshService()
    logs = service.get_ticket_socket_refresh_history()
    return convert_to_json(logs)


@internal_api.route("/internal/logUserActivity", methods=["POST"])
@jwt_required()
def log_user_activity():
    """
    API method to log user activity
    """
    success: bool = False
    user = get_user_from_jwt()
    activity_type = request.json.get("activityType")
    activity_data = request.json.get("activityData")

    if user is not None and activity_type is not None:
        user_id = user.user_id

        service = UserActivityService()
        data: str = str(activity_data) if activity_data is not None else ""
        success = service.log_user_activity(user_id, int(activity_type), data)
    return convert_to_json(success)


@internal_api.route("/internal/mail", methods=["POST"])
def send_mail():
    """
    API to send mail via Twilio
    """
    # secured by mail api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("MAIL_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    to_email = request.json.get("toEmail", None)
    to_name = request.json.get("toName", None)
    subject = request.json.get("subject", None)
    html_content = request.json.get("htmlContent", None)
    cc_emails = request.json.get("ccEmails", None)

    if (
        to_email is None
        or to_email == ""
        or subject is None
        or subject == ""
        or html_content is None
        or html_content == ""
    ):
        return {"msg": "Bad Request"}, 200

    result = send_email(to_email, subject, html_content, to_name, cc_emails)

    return convert_to_json(result)


@internal_api.route("/internal/refreshEventsFromService/<int:seller_id>")
@jwt_required()
def refresh_events_from_service(seller_id: int = None):
    """
    API method to refresh TS events from the admin
    """
    user = get_user_from_jwt()
    if user is None or user.is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = DataRefreshService()
    start: int = None
    end: int = None
    user_id: int = user.user_id
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))

    if seller_id is not None:
        results = service.refresh_database_from_ticket_socket(
            seller_id, start, end, user_id
        )

        if results is not None and results.succeeded is True:
            # update rollup data
            year = 0
            if start is not None:
                year = datetime.fromtimestamp(start).year
                now_year = datetime.now().year
                if year >= now_year or year < 2022:
                    year = 0

            order_service = OrderService()
            month: int = 0
            day: int = 0
            current_year: int = 0

            if year > 0:
                current_year = year
                month = 12
                day = 31
            else:
                current_year = datetime.now().year
                month = datetime.now().month
                day = datetime.now().day

            start = datetime.strptime(
                f"{current_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
            ).timestamp()
            end = datetime(current_year, month, day).timestamp()
            orders: list[VipOrder] = order_service.get_orders(
                seller_id=seller_id, start=start, end=end
            )

            daily_order_service = DailyOrderService()
            results = daily_order_service.update_daily_order_data(
                orders, start, end, results
            )
    else:
        results = None
    return convert_to_json(results)


@internal_api.route("/internal/updateDailyOrderData/<int:year>")
def update_daily_order_data(year: int):
    """
    API method to refresh daily order data directly for an entire year
    """

    # secured by internal api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("INTERNAL_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if year < 2022:
        return {"msg": "Bad Request"}, 400

    month: int = 0
    day: int = 0
    current_year: int = 0

    if year > 0:
        current_year = year
        month = 12
        day = 31
    else:
        current_year = datetime.now().year
        month = datetime.now().month
        day = datetime.now().day

    start = datetime.strptime(
        f"{current_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
    ).timestamp()
    end = datetime(current_year, month, day).timestamp()
    order_service = OrderService()
    orders: list[VipOrder] = order_service.get_orders(start=start, end=end)

    service = DailyOrderService()
    results = service.update_daily_order_data(orders, start, end, None)
    return convert_to_json(results)


# END INTERNAL ROUTES
