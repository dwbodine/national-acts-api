"""
Mobile API routes - used by the mobile app to access/update data in the system.
"""

import json
import logging
from flask import Blueprint, Response, request

mobile_api = Blueprint("mobile_api", __name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@mobile_api.route("/mobile/ticket/checkin/<string:ticket_id>", methods=["POST"])
def mobile_checkin(ticket_id: str):
    """
    Handle ticket socket check-in requests.
    """

    headers = request.headers
    if not headers:
        logger.info("Mobile check-in received no headers")
    else:
        logger.info(
            "Mobile check-in headers: %s",
            list(headers.items()),
        )

    form = request.form
    if not form:
        logger.info("Mobile check-in received no form fields")
    else:
        logger.info(
            "Mobile check-in POST fields: %s",
            form.to_dict(flat=False),
        )

    payload = request.get_json(silent=True)
    if payload is not None:
        logger.info(
            "Mobile check-in JSON payload: %s",
            json.dumps(payload),
        )
        
    if ticket_id is not None:
        logger.info("Mobile check-in for ticket ID: %s", ticket_id)
    else:
        logger.info("Mobile check-in received no ticket ID")

    return Response("ok", mimetype="text/plain")
