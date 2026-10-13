"""
External API routes - used by external systems to access/update data in the system.
This is a separate API from the public API, which is used by the front-end web application.
"""

import json
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

    headers = request.headers
    if not headers:
        logger.info("TicketSocket check-in received no headers")
    else:
        logger.info(
            "TicketSocket check-in headers: %s",
            list(headers.items()),
        )

    form = request.form
    if not form:
        logger.info("TicketSocket check-in received no form fields")
    else:
        logger.info(
            "TicketSocket check-in POST fields: %s",
            form.to_dict(flat=False),
        )

    payload = request.get_json(silent=True)
    if payload is not None:
        logger.info(
            "TicketSocket check-in JSON payload: %s",
            json.dumps(payload),
        )

    return Response("ok", mimetype="text/plain")
