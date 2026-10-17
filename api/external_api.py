"""
External API routes - used by external systems to access/update data in the system.
This is a separate API from the public API, which is used by the front-end web application.
"""

import logging
from flask import Blueprint, Response, request

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

    return Response("ok", mimetype="text/plain")
