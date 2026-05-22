"""
Orders API routes
"""

from flask import Blueprint
from flask_jwt_extended import jwt_required

from common.admin_service import AdminService
from common.common_api import is_admin_logged_in
from common.utility import convert_to_json

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

    # show_fulfilled: bool = get_override_bool_value_or_default(
    #    request.args.get("fulfilled")
    # )
    # show_paid: bool = get_override_bool_value_or_default(request.args.get("paid"))

    service = AdminService()
    countries = service.get_all_countries()
    return convert_to_json(countries)
