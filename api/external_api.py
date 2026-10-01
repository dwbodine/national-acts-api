"""
External API routes - used by external systems to access/update data in the system.
This is a separate API from the public API, which is used by the front-end web application.
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, Response, request
import stripe

from common.utility import convert_to_json

external_api = Blueprint("external_api", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@external_api.route("/external/ticketsocket/checkin", methods=["POST"])
def ticketsocket_checkin():
    """
    Handle ticket socket check-in requests.
    """

    logger.info(
        "TicketSocket check-in POST fields: %s",
        request.form.to_dict(flat=False),
    )

    return Response("ok", mimetype="text/plain")



