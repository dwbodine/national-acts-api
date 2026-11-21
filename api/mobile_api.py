"""
Mobile API routes - used by the mobile app to access/update data in the system.
"""

import json
import logging
import os
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common.constants import TicketCheckInStatus
from common.models.national_acts import TicketCheckIn
from common.ticket_order_service import TicketOrdersService
from common.utility import convert_to_json, get_override_string_value_or_default

mobile_api = Blueprint("mobile_api", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@mobile_api.route("/mobile/ticket/checkin/<string:ticket_id>", methods=["POST"])
@jwt_required()
def mobile_checkin(ticket_id: str):
    """
    Handle ticket socket check-in requests.
    """

    # secured by api key as well as JWT
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(
        os.environ.get("EXPO_PUBLIC_USER_API_KEY")
    )

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    payload = request.get_json(silent=True)
    event_id = payload.get("eventId") if isinstance(payload, dict) else None

    if not isinstance(event_id, int):
        return {"msg": "Invalid event ID"}, 400

    service = TicketOrdersService()
    response = service.check_in_ticket(ticket_id, event_id)

    return convert_to_json(response)
