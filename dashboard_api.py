"""
Dashboard API routes
"""

from datetime import datetime

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from common_api import is_admin_logged_in

from common.dashboard_service import DashboardService
from common.user_activity_service import UserActivityService
from common.models.user import UserActivity
from common.utility import convert_to_json

dashboard_api = Blueprint("dashboard_api", __name__)


# BEGIN DASHBOARD ROUTES
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
    if year >= current_year or year < 2022:
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

    start = request.json.get("start")
    end = request.json.get("end")
    user_id = request.json.get("userId")
    activity_type = request.json.get("activityType")
    filter_admins = request.json.get("filterAdmins")

    if start is None or end is None:
        return {"msg": "Bad Request"}, 400

    service = UserActivityService()
    activities: list[UserActivity] = []
    filter_admin_val: bool = True if filter_admins is not None else False
    if user_id is not None and activity_type is not None:
        activities = service.get_user_activity(
            start, end, int(user_id), int(activity_type), filter_admins=filter_admin_val
        )
    elif user_id is not None:
        activities = service.get_user_activity(
            start, end, int(user_id), filter_admins=filter_admin_val
        )
    elif activity_type is not None:
        activities = service.get_user_activity(
            start, end, activity_type=int(activity_type), filter_admins=filter_admin_val
        )
    else:
        activities = service.get_user_activity(
            start, end, filter_admins=filter_admin_val
        )
    return convert_to_json(activities)


# END DASHBOARD ROUTES
