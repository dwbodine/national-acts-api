"""
Orders API routes
"""

from types import SimpleNamespace
import json
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common.admin_service import AdminService
from common.calendar_service import CalendarService
from common.common_api import is_admin_logged_in
from common.event_service import EventService
from common.faq_service import FaqService
from common.models.admin import ExternalVenue, Faq, Page, SiteSetting
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

ticket_orders_api = Blueprint("ticket_orders_api", __name__)

@ticket_orders_api.route("/ticket_orders")
@jwt_required()
def get_ticket_orders():
    """
    API method to fetch all orders
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401
    
    
    show_fulfilled: bool = get_override_bool_value_or_default(
        request.args.get("fulfilled")
    )
    show_paid: bool = get_override_bool_value_or_default(
        request.args.get("paid")
    )

    service = AdminService()
    countries = service.get_all_countries()
    return convert_to_json(countries)