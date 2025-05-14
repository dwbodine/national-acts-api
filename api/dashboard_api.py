"""
Dashboard API routes
"""

from datetime import datetime

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common.common_api import is_admin_logged_in
from common.dashboard_service import DashboardService
from common.user_activity_service import UserActivityService
from common.models.user import UserActivity
from common.utility import (
    convert_to_json,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
)

dashboard_api = Blueprint("dashboard_api", __name__)


@dashboard_api.route("/dashboard/getDashboardDataSecured/<int:year>")
@jwt_required()
def get_dashboard_data_secured(year: int):
    """
    API method to fetch data for dashboard
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    current_year = datetime.now().year
    if year is None or year >= current_year or year < 2022:
        year = 0

    service = DashboardService()
    dash_data = service.get_dashboard_data(year)
    return convert_to_json(dash_data)


@dashboard_api.route("/dashboard/getUserActivity", methods=["POST"])
@jwt_required()
def get_user_activity():
    """
    API method to fetch user activity
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    start = get_override_int_value_or_default(request.json.get("start"), default=None)
    end = get_override_int_value_or_default(request.json.get("end"), default=None)
    user_id = get_override_int_value_or_default(
        request.json.get("userId"), default=None
    )
    activity_type = get_override_int_value_or_default(
        request.json.get("activityType"), default=None
    )
    filter_admins = get_override_bool_value_or_default(request.json.get("filterAdmins"))

    if start is None or start <= 0 or end is None or end <= 0:
        return {"msg": "Bad Request"}, 400

    service = UserActivityService()
    activities: list[UserActivity] = []

    if user_id is not None and activity_type is not None:
        activities = service.get_user_activity(
            start, end, int(user_id), int(activity_type), filter_admins=filter_admins
        )
    elif user_id is not None:
        activities = service.get_user_activity(
            start, end, int(user_id), filter_admins=filter_admins
        )
    elif activity_type is not None:
        activities = service.get_user_activity(
            start, end, activity_type=int(activity_type), filter_admins=filter_admins
        )
    else:
        activities = service.get_user_activity(start, end, filter_admins=filter_admins)
    return convert_to_json(activities)
