# pylint: disable=too-many-lines
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
from common.faq_service import FaqService
from common.models.admin import (
    ExternalVenue,
    FanMoment,
    Faq,
    FanMomentKey,
    FeaturedArtist,
    Page,
    SiteSetting,
)
from common.moments_service import MomentsService
from common.order_service import OrderService
from common.page_service import PageService
from common.role_service import RoleService
from common.seller_service import SellerService
from common.tour_service import TourService
from common.user_service import UserService
from common.utility import (
    convert_to_json,
    convert_json_to_snake_case_object,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)
from common.models.national_acts import (
    Seller,
    Tour,
    VipEvent,
    VipOrder,
)
from common.models.user import User, Role

admin_api = Blueprint("admin_api", __name__)


def _build_fan_moment_key(
    moment_date: str, seller_id: int, event_id: int
) -> FanMomentKey:
    """
    Build a fan moment key object without requiring a model constructor.
    """
    fm_key = FanMomentKey()
    fm_key.moment_date = moment_date
    fm_key.seller_id = seller_id
    fm_key.event_id = event_id
    return fm_key


@admin_api.route("/admin/countries")
@jwt_required()
def get_countries():
    """
    API method to fetch all country data
    """
    service = AdminService()
    countries = service.get_all_countries()
    return convert_to_json(countries)


@admin_api.route("/admin/events/cancel", methods=["POST"])
@jwt_required()
def cancel_event():
    """
    API method to cancel an event
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_ids: list[int] = request.json.get("eventIdList", [])

    if event_ids is None or len(event_ids) == 0:
        return {"msg": "Bad Request"}, 400

    cancelled: bool = get_override_bool_value_or_default(
        request.json.get("cancelled", None)
    )

    service = AdminService()
    success = service.cancel_event(event_ids, cancelled)
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

    event_id = get_override_int_value_or_default(request.json.get("eventId", None))

    if event_id is None or event_id <= 0:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    mark_cancelled_str = request.json.get("markCancelled", None)
    refund_service_fees: bool = get_override_bool_value_or_default(
        refund_service_fees_str
    )
    mark_cancelled: bool = get_override_bool_value_or_default(mark_cancelled_str)

    service = AdminService()
    success = service.refund_all_event_orders(
        event_id, refund_service_fees, mark_cancelled
    )
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

    event_id = get_override_int_value_or_default(request.json.get("eventId", None))
    if event_id is None or event_id <= 0:
        return {"msg": "Bad Request"}, 400

    is_sent = get_override_bool_value_or_default(request.json.get("isSent", None))

    service = AdminService()
    updated_event = service.send_list_to_band(event_id, is_sent)
    return convert_to_json(updated_event)


@admin_api.route("/admin/events/ticketSocketOnly")
@jwt_required()
def get_only_ts_events():
    """
    API method to fetch only TS events
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    seller_id: int = 0
    if request.args.get("sellerId") is not None:
        seller_id = get_override_int_value_or_default(request.args.get("sellerId"))

    if seller_id <= 0:
        return {"msg": "Bad Request"}, 400

    service = AdminService()
    events = service.get_ticket_socket_events_only(seller_id)
    return convert_to_json(events)


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

    service = AdminService()
    success = service.update_event(event)
    return convert_to_json(success)


@admin_api.route("/admin/faq/delete", methods=["POST"])
@jwt_required()
def delete_faq():
    """
    API method to delete faq
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    faq_id = get_override_string_value_or_default(request.json.get("faqId", None))

    service = FaqService()
    success = service.delete_faq(faq_id)
    return convert_to_json(success)


@admin_api.route("/admin/faq/movedown", methods=["POST"])
@jwt_required()
def move_faq_up():
    """
    API method to move faq down
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    faq_id = get_override_string_value_or_default(request.json.get("faqId", None))

    service = FaqService()
    success = service.move_down(faq_id)
    return convert_to_json(success)


@admin_api.route("/admin/faq/moveup", methods=["POST"])
@jwt_required()
def move_faq_down():
    """
    API method to move faq up
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    faq_id = get_override_string_value_or_default(request.json.get("faqId", None))

    service = FaqService()
    success = service.move_up(faq_id)
    return convert_to_json(success)


@admin_api.route("/admin/faq/update", methods=["POST"])
@jwt_required()
def update_faq():
    """
    API method to update faq
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    faq = convert_json_to_snake_case_object(request.get_json(), Faq())

    service = FaqService()
    success = service.update_faq(faq)
    return convert_to_json(success)


@admin_api.route("/admin/featured-artists/order", methods=["POST"])
@jwt_required()
def update_featured_artist_order():
    """
    API method to update featured artist orders
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = request.get_json()

    if data is None or len(data) == 0:
        return {"msg": "Bad Request"}, 400

    save_success: bool = False
    featured_artists: list[FeaturedArtist] = []
    for item in data:
        fa = convert_json_to_snake_case_object(item, FeaturedArtist())
        if fa is not None:
            featured_artists.append(fa)

    if len(featured_artists) > 0:
        service = PageService()
        save_success = service.update_featured_artist_order(featured_artists)

    return convert_to_json(save_success)


@admin_api.route("/admin/featured-artists/page-sellers")
@jwt_required()
def get_featured_artist_page_sellers():
    """
    API method to get featured artist page sellers
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = PageService()
    page_sellers = service.get_page_sellers()

    return convert_to_json(page_sellers)


@admin_api.route("/admin/featured-artists/update", methods=["POST"])
@jwt_required()
def update_featured_artist():
    """
    API method to update featured artist
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    featured_artist = convert_json_to_snake_case_object(
        request.get_json(), FeaturedArtist()
    )

    service = PageService()
    updated_artist = service.update_featured_artist(featured_artist)
    return convert_to_json(updated_artist)


@admin_api.route("/admin/notes/add", methods=["POST"])
@jwt_required()
def add_note():
    """
    API method to add a note to an event or calendar date
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    note = get_override_string_value_or_default(request.json.get("note", None))

    if note is None:
        return {"msg": "Bad Request"}, 400

    event_id: int = get_override_int_value_or_default(
        request.json.get("eventId", None), default=None
    )

    calendar_date: str = None
    note_title: str = None
    if event_id is None or event_id <= 0:
        calendar_date = get_override_string_value_or_default(
            request.json.get("calendarDate", None)
        )
        note_title = get_override_string_value_or_default(
            request.json.get("noteTitle", None)
        )

    if (event_id is None or event_id <= 0) and calendar_date is None:
        return {"msg": "Bad Request"}, 400

    service = CalendarService()
    success = service.add_note(note, event_id, calendar_date, note_title)
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

    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)

    if start is None or end is None or start <= 0 or end <= 0:
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

    note_id = get_override_int_value_or_default(
        request.json.get("noteId", None), default=None
    )

    if note_id is None or note_id <= 0:
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

    note_id = get_override_int_value_or_default(
        request.json.get("noteId", None), default=None
    )
    note_date = get_override_string_value_or_default(request.json.get("noteDate"))

    if (note_id is None or note_id <= 0) or note_date is None:
        return {"msg": "Bad Request"}, 400

    note = get_override_string_value_or_default(request.json.get("note", None))
    note_title = get_override_string_value_or_default(
        request.json.get("noteTitle", None)
    )
    is_completed = get_override_bool_value_or_default(
        request.json.get("isCompleted", None)
    )

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

    event_id = get_override_int_value_or_default(
        request.json.get("eventId", None), default=None
    )
    num_tickets = get_override_int_value_or_default(
        request.json.get("numTickets", None), default=None
    )

    if (event_id is None or event_id <= 0) or (num_tickets is None or num_tickets <= 0):
        return {"msg": "Bad Request"}, 400

    service = OrderService()
    success = service.add_comped_order(event_id, num_tickets)
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

    order_id = get_override_int_value_or_default(
        request.json.get("orderId", None), default=None
    )

    if order_id is None or order_id <= 0:
        return {"msg": "Bad Request"}, 400

    refund_service_fees = get_override_bool_value_or_default(
        request.json.get("refundServiceFees", None)
    )
    mark_chargeback = get_override_bool_value_or_default(
        request.json.get("markChargeback", None)
    )

    service = OrderService()
    success = service.refund_order(order_id, refund_service_fees, mark_chargeback)
    return convert_to_json(success)


@admin_api.route("/admin/orders/search")
@jwt_required()
def search_orders():
    """
    API method to search all orders
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    search_term: str = get_override_string_value_or_default(request.args.get("sTerm"))

    if search_term is None or len(search_term) < 3:
        return {"msg": "Bad Request"}, 400

    service = OrderService()
    orders = service.get_orders(ignore_flags=True, search_term=search_term)
    return convert_to_json(orders)


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


@admin_api.route("/admin/pages")
@jwt_required()
def get_all_pages():
    """
    API method to fetch all pages
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = PageService()
    pages = service.get_all_pages()
    return convert_to_json(pages)


@admin_api.route("/admin/pages/order", methods=["POST"])
@jwt_required()
def update_page_order():
    """
    API method to update client page orders
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = request.get_json()

    if data is None or len(data) == 0:
        return {"msg": "Bad Request"}, 400

    save_success: bool = False
    pages: list[Page] = []
    for item in data:
        page = convert_json_to_snake_case_object(item, Page())
        if page is not None:
            pages.append(page)

    if len(pages) > 0:
        service = PageService()
        save_success = service.update_seller_page_order(pages)

    return convert_to_json(save_success)


@admin_api.route("/admin/pages/update", methods=["POST"])
@jwt_required()
def update_page():
    """
    API method to update page
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    page = convert_json_to_snake_case_object(request.get_json(), Page())

    service = PageService()
    success = service.update_page(page)
    return convert_to_json(success)


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

    if len(role_ids) == 0:
        return {"msg": "Bad Request"}, 400

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


@admin_api.route("/admin/sellers")
@jwt_required()
def get_admin_sellers():
    """
    API method to fetch all sellers for admin site
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = SellerService()
    results = service.get_all_sellers(show_inactive=True)
    return convert_to_json(results)


@admin_api.route("/admin/seller/update", methods=["POST"])
@jwt_required()
def update_seller():
    """
    API method to update seller data
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    seller = convert_json_to_snake_case_object(request.get_json(), Seller())

    service = SellerService()
    updated_seller = service.update_seller(seller)
    return convert_to_json(updated_seller)


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

    ticket_id = get_override_int_value_or_default(
        request.json.get("ticketId", None), default=None
    )

    if ticket_id is None or ticket_id <= 0:
        return {"msg": "Bad Request"}, 400

    refund_service_fees = get_override_bool_value_or_default(
        request.json.get("refundServiceFees", None)
    )

    service = OrderService()
    success = service.refund_ticket(ticket_id, refund_service_fees)
    return convert_to_json(success)


@admin_api.route("/admin/ticketSocketAccounts")
@jwt_required()
def get_ticket_socket_accounts():
    """
    API method to fetch current TS account data
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = AdminService()
    accounts = service.get_ticket_socket_accounts()
    return convert_to_json(accounts)


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

    user_id = get_override_int_value_or_default(
        request.json.get("userId", None), default=None
    )

    if user_id is None or user_id <= 0:
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

    search_term: str = get_override_string_value_or_default(request.args.get("search"))

    service = AdminService()
    venues = service.get_external_venues(search_term)
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

    venue_id = get_override_int_value_or_default(
        request.json.get("venueId", None), default=None
    )

    if venue_id is None or venue_id <= 0:
        return {"msg": "Bad Request"}, 400

    service = AdminService()
    success = service.delete_external_venue(venue_id)
    return convert_to_json(success)


@admin_api.route("/admin/moments/update", methods=["POST"])
@jwt_required()
def update_moment():
    """
    API method to update moment
    """
    moment = convert_json_to_snake_case_object(request.get_json(), FanMoment())

    service = MomentsService()
    success = service.update_moment(moment)
    return convert_to_json(success)


@admin_api.route("/admin/moments/delete", methods=["POST"])
@jwt_required()
def delete_fan_moments():
    """
    API method to delete fan moments
    """
    moment_date: str = get_override_string_value_or_default(
        request.json.get("momentDate", None), default=None
    )

    seller_id: int = get_override_int_value_or_default(
        request.json.get("sellerId", None), default=None
    )

    event_id: int = get_override_int_value_or_default(
        request.json.get("eventId", None), default=None
    )

    if (
        seller_id is None
        or seller_id <= 0
        or event_id is None
        or event_id <= 0
        or moment_date is None
        or len(moment_date) == 0
    ):
        return {"msg": "Bad Request"}, 400

    service = MomentsService()
    success = service.delete_moments(
        _build_fan_moment_key(moment_date, seller_id, event_id)
    )
    return convert_to_json(success)
