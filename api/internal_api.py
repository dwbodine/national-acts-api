"""
Internal API routes - used by legacy PHP admin code
"""

from flask import Blueprint
from common.ticket_socket_service import TicketSocketService, get_all_accounts
from common.utility import convert_to_json

internal_api = Blueprint("internal_api", __name__)


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
