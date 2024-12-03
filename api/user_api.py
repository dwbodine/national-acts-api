"""
User API routes
"""

import os
from types import SimpleNamespace
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    unset_jwt_cookies,
    jwt_required,
)

from common.event_service import EventService
from common.order_service import OrderService
from common.seller_service import SellerService
from common.user_service import UserService
from common.utility import convert_to_json
from common.models.user import User

user_api = Blueprint("user_api", __name__)


# BEGIN USER ROUTES
@user_api.route("/user/eventsAndOrdersSecured")
@jwt_required()
def get_events_and_orders_secured():
    """
    API method to fetch events and orders for Sellers
    """
    service = EventService()
    seller_id: int = None
    start: int = None
    end: int = None
    exclude_start: int = None
    exclude_end: int = None
    search_term: str = None
    show_inactive: bool = False
    show_deleted: bool = False
    show_hidden: bool = False
    show_cancelled: bool = False
    ts_event_id: int = None
    exclude_external: bool = False
    ignore_flags: bool = False
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))
    if request.args.get("excludeStart") is not None:
        exclude_start = int(request.args.get("excludeStart"))
    if request.args.get("excludeEnd") is not None:
        exclude_end = int(request.args.get("excludeEnd"))
    if request.args.get("inactive") is not None:
        show_inactive = True if int(request.args.get("inactive")) == 1 else False
    if request.args.get("deleted") is not None:
        show_deleted = True if int(request.args.get("deleted")) == 1 else False
    if request.args.get("hidden") is not None:
        show_hidden = True if int(request.args.get("hidden")) == 1 else False
    if request.args.get("search") is not None:
        search_term = str(request.args.get("search"))
    if request.args.get("tsEventId") is not None:
        ts_event_id = int(request.args.get("tsEventId"))
    if request.args.get("excludeExternal") is not None:
        exclude_external = (
            True if int(request.args.get("excludeExternal")) == 1 else False
        )
    if request.args.get("ignoreFlags") is not None:
        ignore_flags = True if int(request.args.get("ignoreFlags")) == 1 else False
    if request.args.get("cancelled") is not None:
        show_cancelled = True if int(request.args.get("cancelled")) == 1 else False
    results = service.get_events_and_orders(
        True,
        seller_id,
        start,
        end,
        show_inactive,
        search_term,
        ts_event_id,
        show_deleted,
        exclude_start,
        exclude_end,
        exclude_external,
        show_hidden,
        ignore_flags,
        show_cancelled,
    )
    return convert_to_json(results)


@user_api.route("/user/getUserSellerFromEventId/<int:user_id>/<int:event_id>")
@jwt_required()
def get_user_seller_from_event_id(user_id: int, event_id: int):
    """
    API method to get user seller from event by event and user id's
    """
    if user_id is None or user_id == 0 or event_id is None or event_id == 0:
        return {"msg", "Bad request"}, 400
    service = UserService()
    results = service.get_user_seller_by_event_id(user_id, event_id)
    return convert_to_json(results)


@user_api.route("/user/login", methods=["POST"])
def create_token():
    """
    API to log in user and create token
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    password = request.json.get("password", None)

    if username is None or password is None:
        return {"msg", "Bad request"}, 400

    service = UserService()
    login_response = service.login(username, password)

    if login_response.error_message is not None:
        return {"msg": login_response.error_message}, 401
    elif login_response.user is None or login_response.user.is_authenticated is False:
        return {"msg": "Invalid username or password"}, 401

    access_token = create_access_token(identity=username)

    if access_token is None:
        return {"msg": "Unable to create access token"}, 500

    user: User = login_response.user
    user.token = access_token
    user.is_authenticated = True

    return convert_to_json(user)


@user_api.route("/user/logout", methods=["POST"])
def logout():
    """
    API method to log out user and retire token
    """
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response


@user_api.route("/user/ordersSecured")
@jwt_required()
def orders_secured():
    """
    API method to fetch orders for seller
    """
    service = OrderService()
    seller_id: int = None
    start: int = None
    end: int = None
    show_inactive: bool = False
    show_deleted: bool = False
    show_cancelled: bool = False
    ignore_flags: bool = False
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))
    if request.args.get("inactive") is not None:
        show_inactive = True if int(request.args.get("inactive")) == 1 else False
    if request.args.get("deleted") is not None:
        show_deleted = True if int(request.args.get("deleted")) == 1 else False
    if request.args.get("cancelled") is not None:
        show_cancelled = True if int(request.args.get("cancelled")) == 1 else False
    if request.args.get("ignoreFlags") is not None:
        ignore_flags = True if int(request.args.get("ignoreFlags")) == 1 else False

    results = service.get_orders(
        seller_id,
        start,
        end,
        show_inactive,
        show_deleted,
        ignore_flags,
        show_cancelled,
    )
    return convert_to_json(results)


@user_api.route("/user/orderById")
@jwt_required()
def order_by_id():
    """
    API method to fetch an order by id
    """
    service = OrderService()
    order_id: int = None
    if request.args.get("tsOrderId") is not None:
        order_id = int(request.args.get("tsOrderId"))

    if order_id is None:
        return {"msg": "Bad Request"}, 400

    results = service.get_orders(ts_order_id=order_id)
    return convert_to_json(results)


@user_api.route("/user/profile/<int:user_id>")
@jwt_required()
def get_user_profile(user_id: int):
    """
    API method to get user profile
    """
    if user_id is None or user_id <= 0:
        return {"msg": "Bad Request"}, 400
    service = UserService()
    user = service.get_user_by_id(user_id, True)
    return convert_to_json(user)


@user_api.route("/user/register", methods=["POST"])
def register():
    """
    API method to register new user
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    first_name = request.json.get("firstName", None)
    last_name = request.json.get("lastName", None)
    seller_id = request.json.get("sellerId", None)
    password = request.json.get("password", None)
    confirm_password = request.json.get("confirmPassword", None)
    notes = request.json.get("notes", None)
    service = UserService()
    if (
        username is None
        or password is None
        or confirm_password is None
        or first_name is None
        or last_name is None
        or seller_id is None
    ):
        return {"msg", "Bad request"}, 400
    result = service.register(
        username, first_name, last_name, seller_id, password, confirm_password, notes
    )
    return convert_to_json(result)


@user_api.route("/user/resetPassword", methods=["POST"])
def reset_password():
    """
    API method to reset password (not logged in)
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    password = request.json.get("password", None)
    confirm_password = request.json.get("confirmPassword", None)
    code = request.json.get("code", None)
    service = UserService()
    if username is None or password is None or confirm_password is None or code is None:
        return {"msg", "Bad request"}, 400
    result = service.reset_password(username, code, password, confirm_password)
    return convert_to_json(result)


@user_api.route("/user/resetPasswordSecured", methods=["POST"])
@jwt_required()
def reset_password_secured():
    """
    API method to reset password (logged in)
    """
    username = request.json.get("username", None)
    password = request.json.get("password", None)
    confirm_password = request.json.get("confirmPassword", None)
    service = UserService()
    if username is None or password is None or confirm_password is None:
        return {"msg", "Bad request"}, 400
    result = service.reset_password_secured(username, password, confirm_password)
    return convert_to_json(result)


@user_api.route("/user/sellers/<int:user_id>")
def get_user_sellers(user_id: int):
    """
    API method to get all sellers by user_id
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SellerService()
    results = service.get_user_sellers(user_id)
    return convert_to_json(results)


@user_api.route("/user/sendPasswordReset", methods=["POST"])
def send_password_reset():
    """
    API method to send password reset email with code (not logged in)
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    if username is None:
        return {"msg", "Bad request"}, 400
    service = UserService()
    success = service.send_password_reset_email(username)
    return convert_to_json(success)


@user_api.route("/user/setEventDeletedSecured", methods=["POST"])
@jwt_required()
def set_event_deleted_secured():
    """
    API method to mark event(s) as deleted
    """
    ticket_socket_event_id = request.json.get("eventId", None)
    ticket_socket_event_id_list = request.json.get("eventIdList", None)
    is_deleted = request.json.get("isDeleted", None)

    if (
        ticket_socket_event_id is None and ticket_socket_event_id_list is None
    ) or is_deleted is None:
        return {"msg": "Bad Request"}, 400

    event_ids: list[int] = []
    deleted: bool = True if int(is_deleted) == 1 else False
    if ticket_socket_event_id_list is not None:
        event_ids = json.loads(
            ticket_socket_event_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(event_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_event_id is not None:
        event_ids.append(int(ticket_socket_event_id))

    service = EventService()
    if len(event_ids) > 0:
        result = service.delete_events(event_ids, deleted)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@user_api.route("/user/setEventHiddenSecured", methods=["POST"])
@jwt_required()
def set_event_hidden_secured():
    """
    API method to mark event(s) as hidden
    """
    ticket_socket_event_id = request.json.get("eventId", None)
    ticket_socket_event_id_list = request.json.get("eventIdList", None)
    is_hidden = request.json.get("isHidden", None)

    if (
        ticket_socket_event_id is None and ticket_socket_event_id_list is None
    ) or is_hidden is None:
        return {"msg": "Bad Request"}, 400

    event_ids: list[int] = []
    if ticket_socket_event_id_list is not None:
        event_ids = json.loads(
            ticket_socket_event_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(event_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_event_id is not None:
        event_ids.append(int(ticket_socket_event_id))

    hidden: bool = True if int(is_hidden) == 1 else False
    service = EventService()
    if len(event_ids) > 0:
        result = service.hide_events(event_ids, hidden)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@user_api.route("/user/setEventInactiveSecured", methods=["POST"])
@jwt_required()
def set_event_inactive_secured():
    """
    API method to mark event(s) as inactive
    """
    ticket_socket_event_id = request.json.get("eventId", None)
    ticket_socket_event_id_list = request.json.get("eventIdList", None)
    is_active = request.json.get("isActive", None)

    if (
        ticket_socket_event_id is None and ticket_socket_event_id_list is None
    ) or is_active is None:
        return {"msg": "Bad Request"}, 400

    event_ids: list[int] = []
    if ticket_socket_event_id_list is not None:
        event_ids = json.loads(
            ticket_socket_event_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(event_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_event_id is not None:
        event_ids.append(int(ticket_socket_event_id))

    disabled: bool = True if int(is_active) == 0 else False
    service = EventService()
    if len(event_ids) > 0:
        result = service.disable_events(event_ids, disabled)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@user_api.route("/user/setOrderDeletedSecured", methods=["POST"])
@jwt_required()
def set_order_deleted_secured():
    """
    API method to mark order(s) as deleted
    """
    ticket_socket_order_id = request.json.get("orderId", None)
    ticket_socket_order_id_list = request.json.get("orderIdList", None)
    is_deleted = request.json.get("isDeleted", None)

    if (
        ticket_socket_order_id is None and ticket_socket_order_id_list is None
    ) or is_deleted is None:
        return {"msg": "Bad Request"}, 400

    order_ids: list[int] = []
    if ticket_socket_order_id_list is not None:
        order_ids = json.loads(
            ticket_socket_order_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(order_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_id is not None:
        order_ids.append(int(ticket_socket_order_id))

    deleted: bool = True if int(is_deleted) == 1 else False
    service = OrderService()
    if len(order_ids) > 0:
        result = service.delete_orders(order_ids, deleted)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@user_api.route("/user/setOrderInactiveSecured", methods=["POST"])
@jwt_required()
def set_order_inactive_secured():
    """
    API method to mark order(s) as inactive
    """
    ticket_socket_order_id = request.json.get("orderId", None)
    ticket_socket_order_id_list = request.json.get("orderIdList", None)
    is_active = request.json.get("isActive", None)

    if (
        ticket_socket_order_id is None and ticket_socket_order_id_list is None
    ) or is_active is None:
        return {"msg": "Bad Request"}, 400

    order_ids: list[int] = []
    if ticket_socket_order_id_list is not None:
        order_ids = json.loads(
            ticket_socket_order_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(order_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_id is not None:
        order_ids.append(int(ticket_socket_order_id))

    disabled: bool = True if int(is_active) == 0 else False
    service = OrderService()
    if len(order_ids) > 0:
        result = service.disable_orders(order_ids, disabled)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@user_api.route("/user/setTicketCheckinSecured", methods=["POST"])
@jwt_required()
def set_ticket_checkin_secured():
    """
    API method to mark ticket(s) as checked-in
    """
    ticket_socket_order_ticket_id = request.json.get("ticketId", None)
    ticket_socket_order_ticket_id_list = request.json.get("ticketIdList", None)
    is_checked_in = request.json.get("isCheckedIn", None)

    if (
        ticket_socket_order_ticket_id is None
        and ticket_socket_order_ticket_id_list is None
    ) or is_checked_in is None:
        return {"msg": "Bad Request"}, 400

    ticket_ids: list[int] = []
    if ticket_socket_order_ticket_id_list is not None:
        ticket_ids = json.loads(
            ticket_socket_order_ticket_id_list,
            object_hook=lambda d: SimpleNamespace(**d),
        )
        if len(ticket_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_ticket_id is not None:
        ticket_ids.append(int(ticket_socket_order_ticket_id))

    checked_in: bool = True if int(is_checked_in) == 1 else False
    service = OrderService()
    if len(ticket_ids) > 0:
        result = service.check_in_tickets(ticket_ids, checked_in)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@user_api.route("/user/validateResetCode", methods=["POST"])
def validate_reset_code():
    """
    API method to validate code sent for password reset
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    code = request.json.get("code", None)
    if username is None or code is None:
        return {"msg", "Bad request"}, 400
    service = UserService()
    success = service.validate_password_reset_code(str(username), int(code))
    return convert_to_json(success)


# END USER ROUTES
