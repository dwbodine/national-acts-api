"""
User API routes
"""

import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    unset_jwt_cookies,
    jwt_required,
)

from common.common_api import get_user_from_jwt
from common.seller_service import SellerService
from common.user_activity_service import UserActivityService
from common.user_service import UserService
from common.utility import (
    convert_to_json,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)
from common.models.user import User

user_api = Blueprint("user_api", __name__)


@user_api.route("/user/getUserSellerFromEventId/<int:user_id>/<int:event_id>")
@jwt_required()
def get_user_seller_from_event_id(user_id: int, event_id: int):
    """
    API method to get user seller from event by event and user id's
    """
    if user_id is None or user_id == 0 or event_id is None or event_id == 0:
        return {"msg", "Bad request"}, 400
    service = UserService()
    results = service.get_user_seller_by_event_id(user_id, event_id)
    return convert_to_json(results)


@user_api.route("/user/logUserActivity", methods=["POST"])
@jwt_required()
def log_user_activity():
    """
    API method to log user activity
    """
    success: bool = False
    user = get_user_from_jwt()
    activity_type = get_override_int_value_or_default(
        request.json.get("activityType"), default=None
    )

    if user is not None and activity_type is not None and activity_type > 0:
        user_id = user.user_id
        activity_data = get_override_string_value_or_default(
            request.json.get("activityData"), default=""
        )

        service = UserActivityService()
        success = service.log_user_activity(user_id, activity_type, activity_data)
    return convert_to_json(success)


@user_api.route("/user/login", methods=["POST"])
def create_token():
    """
    API to log in user and create token
    """
    # secured by user api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("USER_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = get_override_string_value_or_default(request.json.get("username", None))
    password = get_override_string_value_or_default(request.json.get("password", None))

    if username is None or password is None:
        return {"msg", "Bad request"}, 400

    service = UserService()
    login_response = service.login(username, password)

    if login_response.error_message is not None:
        return {"msg": login_response.error_message}, 401
    elif login_response.user is None or login_response.user.is_authenticated is False:
        return {"msg": "Invalid username or password"}, 401

    access_token = create_access_token(identity=username)

    if access_token is None:
        return {"msg": "Unable to create access token"}, 500

    user: User = login_response.user
    user.token = access_token
    user.is_authenticated = True

    return convert_to_json(user)


@user_api.route("/user/logout", methods=["POST"])
def logout():
    """
    API method to log out user and retire token
    """
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response


@user_api.route("/user/profile/<int:user_id>")
@jwt_required()
def get_user_profile(user_id: int):
    """
    API method to get user profile
    """
    if user_id is None or user_id <= 0:
        return {"msg": "Bad Request"}, 400
    service = UserService()
    user = service.get_user_by_id(user_id, True)
    return convert_to_json(user)


@user_api.route("/user/register", methods=["POST"])
def register():
    """
    API method to register new user
    """
    # secured by user api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("USER_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = get_override_string_value_or_default(request.json.get("username", None))
    first_name = get_override_string_value_or_default(
        request.json.get("firstName", None)
    )
    last_name = get_override_string_value_or_default(request.json.get("lastName", None))
    seller_id = get_override_string_value_or_default(request.json.get("sellerId", None))
    password = get_override_string_value_or_default(request.json.get("password", None))
    confirm_password = get_override_string_value_or_default(
        request.json.get("confirmPassword", None)
    )
    notes = get_override_string_value_or_default(request.json.get("notes", None))
    service = UserService()
    if (
        username is None
        or password is None
        or confirm_password is None
        or first_name is None
        or last_name is None
        or seller_id is None
    ):
        return {"msg", "Bad request"}, 400
    result = service.register(
        username, first_name, last_name, seller_id, password, confirm_password, notes
    )
    return convert_to_json(result)


@user_api.route("/user/resetPassword", methods=["POST"])
def reset_password():
    """
    API method to reset password (not logged in)
    """
    # secured by user api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("USER_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = get_override_string_value_or_default(request.json.get("username", None))
    password = get_override_string_value_or_default(request.json.get("password", None))
    confirm_password = get_override_string_value_or_default(
        request.json.get("confirmPassword", None)
    )
    code = get_override_int_value_or_default(
        request.json.get("code", None), default=None
    )
    service = UserService()
    if (
        username is None
        or password is None
        or confirm_password is None
        or code is None
        or code <= 0
    ):
        return {"msg", "Bad request"}, 400
    result = service.reset_password(username, code, password, confirm_password)
    return convert_to_json(result)


@user_api.route("/user/resetPasswordSecured", methods=["POST"])
@jwt_required()
def reset_password_secured():
    """
    API method to reset password (logged in)
    """
    username = get_override_string_value_or_default(request.json.get("username", None))
    password = get_override_string_value_or_default(request.json.get("password", None))
    confirm_password = get_override_string_value_or_default(
        request.json.get("confirmPassword", None)
    )
    service = UserService()
    if username is None or password is None or confirm_password is None:
        return {"msg", "Bad request"}, 400
    result = service.reset_password_secured(username, password, confirm_password)
    return convert_to_json(result)


@user_api.route("/user/sellers/<int:user_id>")
def get_user_sellers(user_id: int):
    """
    API method to get all sellers by user_id
    """
    # secured by user api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("USER_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if user_id is None or user_id <= 0:
        return {"msg", "Bad request"}, 400

    service = SellerService()
    results = service.get_user_sellers(user_id)
    return convert_to_json(results)


@user_api.route("/user/sendPasswordReset", methods=["POST"])
def send_password_reset():
    """
    API method to send password reset email with code (not logged in)
    """
    # secured by user api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("USER_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = get_override_string_value_or_default(request.json.get("username", None))
    if username is None:
        return {"msg", "Bad request"}, 400
    service = UserService()
    success = service.send_password_reset_email(username)
    return convert_to_json(success)


@user_api.route("/user/validateResetCode", methods=["POST"])
def validate_reset_code():
    """
    API method to validate code sent for password reset
    """
    # secured by user api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("USER_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = get_override_string_value_or_default(request.json.get("username", None))
    code = get_override_int_value_or_default(
        request.json.get("code", None), default=None
    )
    if username is None or code is None or code <= 0:
        return {"msg", "Bad request"}, 400
    service = UserService()
    success = service.validate_password_reset_code(str(username), int(code))
    return convert_to_json(success)
