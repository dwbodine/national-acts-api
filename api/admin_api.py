"""
Admin API routes
"""

from types import SimpleNamespace
import json
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common.admin_service import AdminService
from common.calendar_service import CalendarService
from common.common_api import is_admin_logged_in
from common.event_service import EventService
from common.external_event_service import ExternalEventService
from common.models.admin import ExternalVenue, SiteSetting
from common.order_service import OrderService
from common.role_service import RoleService
from common.tour_service import TourService
from common.user_service import UserService
from common.utility import (
    convert_to_json,
    convert_json_to_snake_case_object,
)
from common.models.national_acts import Tour, VipEvent, VipOrder
from common.models.user import User, Role

admin_api = Blueprint("admin_api", __name__)


@admin_api.route("/admin/events/cancel", methods=["POST"])
@jwt_required()
def cancel_event():
    """
    API method to cancel an event
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_id = request.json.get("eventId", None)

    if event_id is None:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    refund_service_fees: bool = True if refund_service_fees_str == 1 else False

    service = EventService()
    success = service.cancel_event(int(event_id), refund_service_fees)
    return convert_to_json(success)


@admin_api.route("/admin/events/refund", methods=["POST"])
@jwt_required()
def refund_event():
    """
    API method to refund an event
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_id = request.json.get("eventId", None)

    if event_id is None:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    refund_service_fees: bool = True if refund_service_fees_str == 1 else False

    service = EventService()
    success = service.refund_all_event_orders(int(event_id), refund_service_fees)
    return convert_to_json(success)


@admin_api.route("/admin/events/sendListToBand", methods=["POST"])
@jwt_required()
def send_list_to_band():
    """
    API method to mark the event VIP list as sent to the band
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_id = request.json.get("eventId", None)
    if event_id is None:
        return {"msg": "Bad Request"}, 400

    is_sent_str = request.json.get("isSent", None)
    is_sent = True if is_sent_str == 1 else False

    service = EventService()
    updated_event = service.send_list_to_band(int(event_id), is_sent)
    return convert_to_json(updated_event)


@admin_api.route("/admin/events/update", methods=["POST"])
@jwt_required()
def update_event():
    """
    API method to update event
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event = convert_json_to_snake_case_object(request.get_json(), VipEvent())

    service = EventService()
    success = service.update_event(event)
    return convert_to_json(success)


@admin_api.route("/admin/external_events/<int:seller_id>")
@jwt_required()
def get_external_events(seller_id: int):
    """
    API method to fetch all external events for seller_id
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    if seller_id is None:
        return {"msg": "Bad Request"}, 400

    service = ExternalEventService()
    events = service.get_external_events_by_seller(seller_id)
    return convert_to_json(events)


@admin_api.route("/admin/external_events/update/<int:seller_id>", methods=["POST"])
@jwt_required()
def update_external_event(seller_id: int):
    """
    API method to delete note by Id
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    if seller_id is None:
        return {"msg": "Bad Request"}, 400

    event = convert_json_to_snake_case_object(request.get_json(), VipEvent())

    service = ExternalEventService()
    success = service.update_external_event(event)
    return convert_to_json(success)


@admin_api.route("/admin/notes/add", methods=["POST"])
@jwt_required()
def add_note():
    """
    API method to add a note to an event or calendar date
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    note = request.json.get("note", None)

    if note is None:
        return {"msg": "Bad Request"}, 400

    event_id_str = request.json.get("eventId", None)
    ticket_socket_event_id: int = (
        int(event_id_str) if event_id_str is not None else None
    )

    calendar_date: str = None
    note_title: str = None
    if ticket_socket_event_id is None:
        calendar_date_str = request.json.get("calendarDate", None)
        note_title_str = request.json.get("noteTitle", None)
        calendar_date = (
            str(calendar_date_str) if calendar_date_str is not None else None
        )
        note_title = str(note_title_str) if note_title_str is not None else None

    if ticket_socket_event_id is None and calendar_date is None:
        return {"msg": "Bad Request"}, 400

    service = CalendarService()
    success = service.add_note(
        str(note), ticket_socket_event_id, calendar_date, note_title
    )
    return convert_to_json(success)


@admin_api.route("/admin/notes/calendar")
@jwt_required()
def get_calendar_notes():
    """
    API method to fetch all calendar notes
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    start: int = None
    end: int = None
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))

    if start is None or end is None:
        return {"msg": "Bad Request"}, 400

    service = CalendarService()
    notes = service.get_calendar_notes(start, end)
    return convert_to_json(notes)


@admin_api.route("/admin/notes/delete", methods=["POST"])
@jwt_required()
def delete_note():
    """
    API method to delete note by Id
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    note_id = request.json.get("noteId", None)

    if note_id is None:
        return {"msg": "Bad Request"}, 400

    service = CalendarService()
    success = service.delete_note(note_id)
    return convert_to_json(success)


@admin_api.route("/admin/notes/edit", methods=["POST"])
@jwt_required()
def edit_note():
    """
    API method to edit note by Id
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    note_id = request.json.get("noteId", None)
    note_date = request.json.get("noteDate")

    if note_id is None or note_date is None:
        return {"msg": "Bad Request"}, 400

    note = request.json.get("note", None)
    note_title = request.json.get("noteTitle", None)
    is_completed_str = request.json.get("isCompleted", None)
    is_completed = True if is_completed_str == 1 else False

    service = CalendarService()
    success = service.edit_note(note_id, note, note_date, note_title, is_completed)
    return convert_to_json(success)


@admin_api.route("/admin/orders/comp", methods=["POST"])
@jwt_required()
def comp_order():
    """
    API method to add a comped order
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_id = request.json.get("eventId", None)
    num_tickets = request.json.get("numTickets", None)

    if event_id is None or num_tickets is None:
        return {"msg": "Bad Request"}, 400

    service = OrderService()
    success = service.add_comped_order(int(event_id), int(num_tickets))
    return convert_to_json(success)


@admin_api.route("/admin/orders/refund", methods=["POST"])
@jwt_required()
def refund_order():
    """
    API method to refund order
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    order_id = request.json.get("orderId", None)

    if order_id is None:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    refund_service_fees: bool = True if refund_service_fees_str == 1 else False

    mark_chargeback_str = request.json.get("markChargeback", None)
    mark_chargeback: bool = True if mark_chargeback_str == 1 else False

    service = OrderService()
    success = service.refund_order(int(order_id), refund_service_fees, mark_chargeback)
    return convert_to_json(success)


@admin_api.route("/admin/orders/update", methods=["POST"])
@jwt_required()
def update_order():
    """
    API method to update order
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    order = convert_json_to_snake_case_object(request.get_json(), VipOrder())

    service = OrderService()
    success = service.update_order(order)
    return convert_to_json(success)


@admin_api.route("/admin/permissions")
@jwt_required()
def get_all_permissions():
    """
    API method to fetch all permissions
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = RoleService()
    permissions = service.get_all_permissions()
    return convert_to_json(permissions)


@admin_api.route("/admin/roles")
@jwt_required()
def get_all_roles():
    """
    API method to fetch all role
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = RoleService()
    roles = service.get_all_roles()
    return convert_to_json(roles)


@admin_api.route("/admin/roles/<int:role_id>")
@jwt_required()
def get_role_by_id(role_id: int):
    """
    API method to get role by id
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    if role_id is None or role_id <= 1:
        return {"msg": "Bad Request"}, 400

    service = RoleService()
    role = service.get_role_by_id(role_id)
    return convert_to_json(role)


@admin_api.route("/admin/roles/delete", methods=["POST"])
@jwt_required()
def delete_roles():
    """
    API method to delete multiple roles
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = convert_to_json(request.get_json())

    role_ids: list[int] = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    service = RoleService()
    success = service.delete_roles(role_ids)
    return convert_to_json(success)


@admin_api.route("/admin/roles/update", methods=["POST"])
@jwt_required()
def update_role():
    """
    API method to update role
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    role = convert_json_to_snake_case_object(request.get_json(), Role())

    service = RoleService()
    success = service.update_role(role)
    return convert_to_json(success)


@admin_api.route("/admin/settings/update", methods=["POST"])
@jwt_required()
def update_setting():
    """
    API method to add or update a site setting
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = request.get_json()

    if data is None or len(data) == 0:
        return {"msg": "Bad Request"}, 400

    save_success: bool = True
    service = AdminService()
    for item in data:
        setting = convert_json_to_snake_case_object(item, SiteSetting())
        success = service.update_setting(setting)
        save_success = save_success and success

    return convert_to_json(save_success)


@admin_api.route("/admin/tickets/refund", methods=["POST"])
@jwt_required()
def refund_ticket():
    """
    API method to refund single ticket
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    ticket_id = request.json.get("ticketId", None)

    if ticket_id is None:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    refund_service_fees: bool = True if refund_service_fees_str == 1 else False

    service = OrderService()
    success = service.refund_ticket(int(ticket_id), refund_service_fees)
    return convert_to_json(success)


@admin_api.route("/admin/tours/update", methods=["POST"])
@jwt_required()
def update_tour():
    """
    API method to add or update a tour
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    tour = convert_json_to_snake_case_object(request.get_json(), Tour())

    if tour is None:
        return {"msg": "Bad Request"}, 400

    service = TourService()
    success: bool = False
    if tour.tour_id > 0:
        success = service.update_tour(tour)
    else:
        success = service.add_tour(tour)

    return convert_to_json(success)


@admin_api.route("/admin/users")
@jwt_required()
def get_all_users():
    """
    API method to fetch all users
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = UserService()
    users = service.get_all_users()
    return convert_to_json(users)


@admin_api.route("/admin/users/delete", methods=["POST"])
@jwt_required()
def delete_user():
    """
    API method to delete user
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    user_id = request.json.get("userId", None)

    if user_id is None:
        return {"msg": "Bad Request"}, 400

    service = UserService()
    success = service.delete_user(user_id)
    return convert_to_json(success)


@admin_api.route("/admin/users/update", methods=["POST"])
@jwt_required()
def update_user():
    """
    API method to update user
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    user = convert_json_to_snake_case_object(request.get_json(), User())

    service = UserService()
    success = service.update_user(user)
    return convert_to_json(success)


@admin_api.route("/admin/venues")
@jwt_required()
def get_all_venues():
    """
    API method to fetch all external event venues
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = AdminService()
    venues = service.get_external_venues()
    return convert_to_json(venues)


@admin_api.route("/admin/venues/edit", methods=["POST"])
@jwt_required()
def update_venue():
    """
    API method to add/edit single venue
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    venue = convert_json_to_snake_case_object(request.get_json(), ExternalVenue())

    service = AdminService()
    venue = service.update_external_venue(venue)
    return convert_to_json(venue)


@admin_api.route("/admin/venues/delete", methods=["POST"])
@jwt_required()
def delete_venue():
    """
    API method to add/edit single venue
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    venue_id = request.json.get("venueId", None)

    if venue_id is None:
        return {"msg": "Bad Request"}, 400

    service = AdminService()
    success = service.delete_external_venue(int(venue_id))
    return convert_to_json(success)
