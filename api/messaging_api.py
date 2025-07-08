"""
Messaging API routes
"""

import os
from flask import Blueprint, request

from common.messaging_service import MessagingService
from common.utility import (
    convert_to_json,
    get_override_string_value_or_default,
)

messaging_api = Blueprint("messaging_api", __name__)


@messaging_api.route("/messaging/email", methods=["POST"])
def send_email_from_web():
    """
    API method to send email from web
    """

    # secured by mail api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("MAIL_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    to_email_address = request.json.get("to", None)
    to_name = request.json.get("toName", None)
    subject = request.json.get("subject", None)
    html_content = request.json.get("html", None)

    if (
        to_email_address is None
        or len(to_email_address.strip()) == 0
        or to_name is None
        or len(to_name.strip()) == 0
        or subject is None
        or len(subject.strip()) == 0
        or html_content is None
        or len(html_content.strip()) == 0
    ):
        return {"msg": "Bad Request"}, 400

    service = MessagingService()
    result = service.send_email(to_email_address, subject, html_content, to_name)
    return convert_to_json(result)


@messaging_api.route("/messaging/token", methods=["POST"])
def get_token():
    """
    API method to get google token
    """

    # secured by mail api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    google_id: str = request.json.get("gId", None)

    if google_id is None or len(google_id.strip()) == 0:
        return {"msg": "Bad Request"}, 400

    service = MessagingService()
    token = service.generate_google_auth_token(google_id)
    return convert_to_json(token)


@messaging_api.route("/messaging/token/validate", methods=["POST"])
def validate_token():
    """
    API method to validate google token
    """

    # secured by mail api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("MAIL_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    google_id: str = request.json.get("gId", None)
    token_id: int = request.json.get("tId", None)

    if (
        google_id is None
        or len(str(google_id).strip()) == 0
        or token_id is None
        or token_id == 0
    ):
        return {"msg": "Bad Request"}, 400

    service = MessagingService()
    result = service.validate_google_auth_token(google_id, token_id)
    return convert_to_json(result)
