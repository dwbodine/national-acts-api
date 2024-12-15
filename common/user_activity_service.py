"""
User activity service module
"""

from datetime import datetime

from common.models.user import UserActivity
from common.db import db_query_all, db_update


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
        if len(activity_data) > 0:
            sql = """INSERT INTO UserActivity
                        (UserId, ActivityId, ActivityData, Timestamp)
                         VALUES (%(userId)s, %(activityId)s, %(activityData)s,
                         CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
            data["activityData"] = activity_data
        else:
            sql = """INSERT INTO UserActivity (UserId, ActivityId, Timestamp)
                         VALUES (%(userId)s, %(activityId)s,
                         CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

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
            activity_user_id = int(row["UserId"])
            activity_type = int(row["ActivityId"])
            activity_name = str(row["ActivityName"])
            username = str(row["Username"])
            activity_data = str(row["ActivityData"])
            activity_time = str(row["Timestamp"])
            full_name = str(row["UserFullName"])
            seller_name = str(row["SellerName"])
            activity = UserActivity(
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
