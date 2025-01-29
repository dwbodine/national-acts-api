"""
Event API routes
"""

from datetime import datetime
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common.common_api import get_user_from_jwt
from common.daily_order_service import DailyOrderService
from common.event_service import EventService
from common.order_service import OrderService
from common.data_refresh_service import DataRefreshService
from common.models.national_acts import VipOrder
from common.utility import convert_to_json

event_api = Blueprint("event_api", __name__)


@event_api.route("/events/getEventsAndOrders")
@jwt_required()
def get_events_and_orders_secured():
    """
    API method to fetch events and orders for Sellers
    """
    service = EventService()
    seller_id: int = None
    seller_ids: list[int] = None
    start: int = None
    end: int = None
    exclude_start: int = None
    exclude_end: int = None
    search_term: str = None
    show_inactive: bool = False
    show_deleted: bool = False
    show_hidden: bool = False
    ts_event_id: int = None
    tour_id: int = None
    exclude_external: bool = False
    ignore_flags: bool = False
    get_orders: bool = True
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("sellerIds") is not None:
        seller_ids = [int(x) for x in str(request.args.get("sellerIds")).split(",")]
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
    if request.args.get("tourId") is not None:
        tour_id = int(request.args.get("tourId"))
    if request.args.get("excludeExternal") is not None:
        exclude_external = (
            True if int(request.args.get("excludeExternal")) == 1 else False
        )
    if request.args.get("ignoreFlags") is not None:
        ignore_flags = True if int(request.args.get("ignoreFlags")) == 1 else False
    if request.args.get("omitOrders") is not None:
        get_orders = False if int(request.args.get("omitOrders")) == 1 else True

    results = service.get_events_and_orders(
        get_orders=get_orders,
        seller_id=seller_id,
        start=start,
        end=end,
        show_inactive=show_inactive,
        search_term=search_term,
        ts_event_id=ts_event_id,
        show_deleted=show_deleted,
        exclude_start=exclude_start,
        exclude_end=exclude_end,
        exclude_external=exclude_external,
        show_hidden=show_hidden,
        ignore_flags=ignore_flags,
        show_cancelled=True,
        seller_ids=seller_ids,
        tour_id=tour_id
    )
    return convert_to_json(results)


@event_api.route("/events/getOrderById")
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


@event_api.route("/events/getOrders")
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
    if request.args.get("ignoreFlags") is not None:
        ignore_flags = True if int(request.args.get("ignoreFlags")) == 1 else False

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

    service = DataRefreshService()
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


@event_api.route("/events/setEventsDeleted", methods=["POST"])
@jwt_required()
def set_event_deleted_secured():
    """
    API method to mark event(s) as deleted
    """
    event_ids: list[int] = request.json.get("eventIdList", None)
    is_deleted = request.json.get("isDeleted", None)

    if event_ids is None or len(event_ids) == 0 or is_deleted is None:
        return {"msg": "Bad Request"}, 400

    deleted: bool = True if int(is_deleted) == 1 else False

    service = EventService()
    if len(event_ids) > 0:
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
    event_ids: list[int] = request.json.get("eventIdList", None)
    is_hidden = request.json.get("isHidden", None)

    if event_ids is None or len(event_ids) == 0 or is_hidden is None:
        return {"msg": "Bad Request"}, 400

    hidden: bool = True if int(is_hidden) == 1 else False
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
    event_ids: list[int] = request.json.get("eventIdList", None)
    is_active = request.json.get("isActive", None)

    if event_ids is None or len(event_ids) == 0 or is_active is None:
        return {"msg": "Bad Request"}, 400

    disabled: bool = True if int(is_active) == 0 else False
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
    is_deleted = request.json.get("isDeleted", None)

    if order_ids is None or len(order_ids) == 0 or is_deleted is None:
        return {"msg": "Bad Request"}, 400

    deleted: bool = True if int(is_deleted) == 1 else False
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
    is_active = request.json.get("isActive", None)

    if order_ids is None or len(order_ids) == 0 or is_active is None:
        return {"msg": "Bad Request"}, 400

    disabled: bool = True if int(is_active) == 0 else False
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
    is_checked_in = request.json.get("isCheckedIn", None)

    if ticket_ids is None or len(ticket_ids) == 0 or is_checked_in is None:
        return {"msg": "Bad Request"}, 400

    checked_in: bool = True if int(is_checked_in) == 1 else False
    service = OrderService()
    if len(ticket_ids) > 0:
        result = service.check_in_tickets(ticket_ids, checked_in)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convert_to_json(result)
