"""
Event API routes
"""

from datetime import datetime
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common.admin_service import AdminService
from common.common_api import get_user_from_jwt
from common.daily_order_service import DailyOrderService
from common.event_service import EventService
from common.order_service import OrderService
from common.tour_service import TourService
from common.data_refresh_service import DataRefreshService
from common.models.national_acts import VipOrder
from common.utility import (
    convert_to_json,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)

event_api = Blueprint("event_api", __name__)


@event_api.route("/events/getEventsAndOrders")
@jwt_required()
def get_events_and_orders_secured():
    """
    API method to fetch events and orders for Sellers
    """
    service = EventService()
    seller_id: int = get_override_int_value_or_default(
        request.args.get("sellerId"), default=None
    )
    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)
    exclude_start: int = get_override_int_value_or_default(
        request.args.get("excludeStart"), default=None
    )
    exclude_end: int = get_override_int_value_or_default(
        request.args.get("excludeEnd"), default=None
    )
    search_term: str = get_override_string_value_or_default(request.args.get("search"))
    show_inactive: bool = get_override_bool_value_or_default(
        request.args.get("deleted")
    )
    show_deleted: bool = get_override_bool_value_or_default(
        request.args.get("inactive")
    )
    show_hidden: bool = get_override_bool_value_or_default(request.args.get("hidden"))
    event_id: int = get_override_int_value_or_default(
        request.args.get("eventId"), default=None
    )
    tour_id: int = get_override_int_value_or_default(
        request.args.get("tourId"), default=None
    )
    exclude_external: bool = get_override_bool_value_or_default(
        request.args.get("excludeExternal")
    )
    ignore_flags: bool = get_override_bool_value_or_default(
        request.args.get("ignoreFlags")
    )
    omit_orders: bool = get_override_bool_value_or_default(
        request.args.get("omitOrders")
    )

    seller_ids: list[int] = None
    if request.args.get("sellerIds") is not None:
        seller_ids = [int(x) for x in str(request.args.get("sellerIds")).split(",")]

    results = service.get_events_and_orders(
        get_orders=(not omit_orders),
        seller_id=seller_id,
        start=start,
        end=end,
        show_inactive=show_inactive,
        search_term=search_term,
        event_id=event_id,
        show_deleted=show_deleted,
        exclude_start=exclude_start,
        exclude_end=exclude_end,
        exclude_external=exclude_external,
        show_hidden=show_hidden,
        ignore_flags=ignore_flags,
        show_cancelled=True,
        seller_ids=seller_ids,
        tour_id=tour_id,
    )
    return convert_to_json(results)


@event_api.route("/events/getOrderById")
@jwt_required()
def order_by_id():
    """
    API method to fetch an order by id
    """
    service = OrderService()
    order_id: int = get_override_int_value_or_default(
        request.args.get("tsOrderId"), default=None
    )

    if order_id is None or order_id <= 0:
        return {"msg": "Bad Request"}, 400

    results = service.get_orders(ts_order_id=order_id)
    return convert_to_json(results)


@event_api.route("/events/getOrders")
@jwt_required()
def orders_secured():
    """
    API method to fetch orders for seller
    """
    service = OrderService()
    seller_id: int = get_override_int_value_or_default(
        request.args.get("sellerId"), default=None
    )
    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)
    show_inactive: bool = get_override_bool_value_or_default(
        request.args.get("inactive")
    )
    show_deleted: bool = get_override_bool_value_or_default(request.args.get("deleted"))
    ignore_flags: bool = get_override_bool_value_or_default(
        request.args.get("ignoreFlags")
    )

    results = service.get_orders(
        seller_id,
        start,
        end,
        show_inactive,
        show_deleted,
        ignore_flags,
    )
    return convert_to_json(results)


@event_api.route("/events/getRefreshHistory")
@jwt_required()
def get_update_history():
    """
    API method to fetch TS refresh history
    """
    user = get_user_from_jwt()
    if user is None or user.is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = AdminService()
    logs = service.get_ticket_socket_refresh_history()
    return convert_to_json(logs)


@event_api.route("/events/refreshEventsFromService/<int:seller_id>")
@jwt_required()
def refresh_events_from_service(seller_id: int = None):
    """
    API method to refresh TS events from the admin
    """
    user = get_user_from_jwt()
    if user is None or user.is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = DataRefreshService()
    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)
    user_id: int = user.user_id

    if seller_id is not None and seller_id > 0:
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


@event_api.route("/events/setEventsDeleted", methods=["POST"])
@jwt_required()
def set_event_deleted_secured():
    """
    API method to mark event(s) as deleted
    """
    event_ids: list[int] = request.json.get("eventIdList", [])

    if event_ids is None or len(event_ids) == 0:
        return {"msg": "Bad Request"}, 400

    deleted = get_override_bool_value_or_default(request.json.get("isDeleted", None))

    service = EventService()

    result = service.delete_events(event_ids, deleted)
    if result is False:
        return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@event_api.route("/events/setEventsHidden", methods=["POST"])
@jwt_required()
def set_event_hidden_secured():
    """
    API method to mark event(s) as hidden
    """
    event_ids: list[int] = request.json.get("eventIdList", [])

    if event_ids is None or len(event_ids) == 0:
        return {"msg": "Bad Request"}, 400

    hidden = get_override_bool_value_or_default(request.json.get("isHidden", None))
    service = EventService()
    if len(event_ids) > 0:
        result = service.hide_events(event_ids, hidden)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@event_api.route("/events/setEventsInactive", methods=["POST"])
@jwt_required()
def set_event_inactive_secured():
    """
    API method to mark event(s) as inactive
    """
    event_ids: list[int] = request.json.get("eventIdList", [])

    if event_ids is None or len(event_ids) == 0:
        return {"msg": "Bad Request"}, 400

    disabled = not get_override_bool_value_or_default(
        request.json.get("isActive", None)
    )
    service = EventService()
    if len(event_ids) > 0:
        result = service.disable_events(event_ids, disabled)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@event_api.route("/events/setOrdersDeleted", methods=["POST"])
@jwt_required()
def set_order_deleted_secured():
    """
    API method to mark order(s) as deleted
    """
    order_ids: list[int] = request.json.get("orderIdList", None)

    if order_ids is None or len(order_ids) == 0:
        return {"msg": "Bad Request"}, 400

    deleted = get_override_bool_value_or_default(request.json.get("isDeleted", None))
    service = OrderService()
    if len(order_ids) > 0:
        result = service.delete_orders(order_ids, deleted)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@event_api.route("/events/setOrdersInactive", methods=["POST"])
@jwt_required()
def set_order_inactive_secured():
    """
    API method to mark order(s) as inactive
    """
    order_ids: list[int] = request.json.get("orderIdList", None)

    if order_ids is None or len(order_ids) == 0:
        return {"msg": "Bad Request"}, 400

    disabled = not get_override_bool_value_or_default(
        request.json.get("isActive", None)
    )
    service = OrderService()
    if len(order_ids) > 0:
        result = service.disable_orders(order_ids, disabled)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@event_api.route("/events/setTicketsCheckin", methods=["POST"])
@jwt_required()
def set_ticket_checkin_secured():
    """
    API method to mark ticket(s) as checked-in
    """
    ticket_ids: list[int] = request.json.get("ticketIdList", None)

    if ticket_ids is None or len(ticket_ids) == 0:
        return {"msg": "Bad Request"}, 400

    checked_in = get_override_bool_value_or_default(
        request.json.get("isCheckedIn", None)
    )
    service = OrderService()
    if len(ticket_ids) > 0:
        result = service.check_in_tickets(ticket_ids, checked_in)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)


@event_api.route("/events/tours/<int:seller_id>")
@jwt_required()
def get_all_tours(seller_id: int):
    """
    API method to fetch all tours
    """
    if seller_id is None or seller_id <= 0:
        return {"msg": "Bad Request"}, 400

    service = TourService()
    tours = service.get_all_tours(seller_id)
    return convert_to_json(tours)
