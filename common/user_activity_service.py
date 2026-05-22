"""
User activity service module
"""

from datetime import datetime

from common.models.user import UserActivity
from common.db import db_query_all, db_update
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class UserActivityService:
    """
    Service to deal with user operations
    """

    # PUBLIC METHODS
    def log_user_activity(self, user_id: int, activity_id: int, activity_data: str):
        """
        Log user activity from the UI
        """
        sql = ""
        data = {"userId": user_id, "activityId": activity_id}
        if activity_data is not None and len(activity_data) > 0:
            sql = """INSERT INTO UserActivity
                        (UserId, ActivityId, ActivityData, Timestamp)
                         VALUES (%(userId)s, %(activityId)s, %(activityData)s,
                         CURRENT_TIMESTAMP)"""
            data["activityData"] = activity_data
        else:
            sql = """INSERT INTO UserActivity (UserId, ActivityId, Timestamp)
                         VALUES (%(userId)s, %(activityId)s,
                         CURRENT_TIMESTAMP)"""

        success = db_update(sql, data)
        return success

    def get_user_activity(
        self,
        start: int,
        end: int,
        user_id: int = None,
        activity_type: int = None,
        filter_admins: bool = False,
    ):
        """
        Get a report of user activity
        """
        activities: list[UserActivity] = []
        sql = """
                WITH
                UserSellerCount AS(
                SELECT
                    Users.UserId,
                    COUNT(*) AS NumAccounts
                FROM
                    Users
                JOIN UserSeller ON Users.UserId = UserSeller.UserId
                GROUP BY
                    Users.UserId
            )
            SELECT
                UserActivity.*,
                Activity.ActivityName,
                Users.Username,
                CONCAT(
                    Users.FirstName,
                    ' ',
                    Users.LastName
                ) AS UserFullName,
                CASE
                    WHEN Users.IsAdmin = 1 THEN 'Admin'
                    WHEN UserSellerCount.NumAccounts > 1 THEN 'Multiple'
                    WHEN UserSellerCount.NumAccounts = 1 THEN(
                            SELECT NAME
                        FROM
                            Sellers
                        JOIN UserSeller ON UserSeller.SellerId = Sellers.SellerId
                        WHERE
                            UserSeller.UserId = Users.UserId
                        )
                    ELSE 'None'
                END AS SellerName
            FROM
                UserActivity
            JOIN Activity ON Activity.ActivityId = UserActivity.ActivityId
            JOIN Users ON Users.UserId = UserActivity.UserId
            LEFT JOIN UserSellerCount ON UserSellerCount.UserId = Users.UserId
                    WHERE UserActivity.Timestamp BETWEEN %(startDate)s AND %(endDate)s"""
        data = {
            "startDate": datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S"),
            "endDate": datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M:%S"),
        }

        where_clause: list[str] = []

        if user_id is not None:
            where_clause.append("UserActivity.UserId = %(userId)s")
            data["userId"] = user_id

        if activity_type is not None:
            where_clause.append("UserActivity.ActivityId = %(activityId)s")
            data["activityId"] = activity_type

        if filter_admins is True:
            where_clause.append("Users.IsAdmin <> 1")

        if len(where_clause) > 0:
            sql += " AND "
            sql += " AND ".join(where_clause)

        sql += " ORDER BY UserActivity.Timestamp DESC, Username ASC"

        rows = db_query_all(sql, data)
        for row in rows:
            user_activity_id = get_override_int_value_or_default(row["UserActivityId"])
            activity_user_id = get_override_int_value_or_default(row["UserId"])
            activity_type = get_override_int_value_or_default(row["ActivityId"])
            activity_name = get_override_string_value_or_default(row["ActivityName"])
            username = get_override_string_value_or_default(row["Username"])
            activity_data = get_override_string_value_or_default(row["ActivityData"])
            activity_time = get_override_string_value_or_default(row["Timestamp"])
            full_name = get_override_string_value_or_default(row["UserFullName"])
            seller_name = get_override_string_value_or_default(row["SellerName"])
            activity = UserActivity(
                user_activity_id,
                activity_user_id,
                activity_type,
                activity_data,
                activity_time,
                activity_name,
                username,
                full_name,
                seller_name,
            )
            activities.append(activity)

        return activities
