"""
Internal API routes - used by legacy PHP admin code
"""

from flask import Blueprint
from common.admin_service import AdminService
from common.ticket_socket_service import TicketSocketService
from common.update_service import UpdateService
from common.utility import convert_to_json

internal_api = Blueprint("internal_api", __name__)


@internal_api.route("/internal/accounts")
def get_accounts():
    """
    API method to fetch account
    """
    service = AdminService()
    accounts = service.get_all_accounts()
    return convert_to_json(accounts)


@internal_api.route("/internal/<int:ticket_socket_id>/categories")
def get_categories(ticket_socket_id: int):
    """
    API method to fetch categories
    """
    service = TicketSocketService(ticket_socket_id)
    categories = service.get_categories()
    return convert_to_json(categories)


@internal_api.route("/internal/dailyorder/rebuild/<int:year>/<int:month>")
def rebuild_daily_order_data(year: int, month: int):
    """
    API method to rebuild daily order data for an entire month
    """
    service = UpdateService()
    success = service.rebuild_daily_order_data_for_year(year, month)
    return convert_to_json(success)
