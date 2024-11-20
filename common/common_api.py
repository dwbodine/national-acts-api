"""
Common API tasks
"""

from flask import request
from flask_jwt_extended import get_jwt
from common.user_service import UserService
from common.models.user import User


def is_admin_logged_in():
    """Check if logged in user is an admin"""
    is_admin: bool = False
    user = get_user_from_jwt()
    if user is not None:
        is_admin = user.is_admin
    return is_admin


def get_user_from_jwt():
    """Get user data from JWT"""
    user: User = None
    try:
        # put this line here to prevent exceptions when there is no auth header
        if request.headers.get("Authorization") is not None:
            username = get_jwt()["sub"]
            service = UserService()
            user = service.get_user_by_user_name(username)
    except (RuntimeError, KeyError):
        user = None
    return user
