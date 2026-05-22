"""
Unit tests for common.user_activity_service helpers.
"""

from datetime import datetime

from common import user_activity_service


def build_activity_row(**overrides):
    """
    Create a user-activity row with sensible defaults for mapping tests.
    """
    row = {
        "UserActivityId": 11,
        "UserId": 7,
        "ActivityId": 3,
        "ActivityName": "Logged In",
        "Username": "ada@example.com",
        "ActivityData": "dashboard",
        "Timestamp": "2026-04-23 11:00:00",
        "UserFullName": "Ada Lovelace",
        "SellerName": "National Acts",
    }
    row.update(overrides)
    return row


def test_log_user_activity_inserts_activity_with_data(monkeypatch):
    """
    Test that log_user_activity includes ActivityData when it is provided.
    """
    calls = []
    monkeypatch.setattr(
        user_activity_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = user_activity_service.UserActivityService().log_user_activity(
        7,
        3,
        "dashboard",
    )

    assert success is True
    assert "ActivityData" in calls[0][0]
    assert calls[0][1] == {
        "userId": 7,
        "activityId": 3,
        "activityData": "dashboard",
    }


def test_log_user_activity_inserts_activity_without_data_when_blank(monkeypatch):
    """
    Test that log_user_activity omits ActivityData when it is blank.
    """
    calls = []
    monkeypatch.setattr(
        user_activity_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = user_activity_service.UserActivityService().log_user_activity(
        8,
        4,
        "",
    )

    assert success is True
    assert "ActivityData" not in calls[0][0]
    assert calls[0][1] == {
        "userId": 8,
        "activityId": 4,
    }


def test_get_user_activity_maps_rows_without_optional_filters(monkeypatch):
    """
    Test that get_user_activity maps rows into UserActivity objects with the base query.
    """
    calls = []
    monkeypatch.setattr(
        user_activity_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [build_activity_row(), build_activity_row(UserActivityId=12, UserId=8)],
    )

    activities = user_activity_service.UserActivityService().get_user_activity(
        start=1745406000,
        end=1745413200,
    )

    assert len(activities) == 2
    assert activities[0].user_activity_id == 11
    assert activities[0].user_id == 7
    assert activities[0].activity_type == 3
    assert activities[0].activity_name == "Logged In"
    assert activities[0].username == "ada@example.com"
    assert activities[0].activity_data == "dashboard"
    assert activities[0].activity_time == "2026-04-23 11:00:00"
    assert activities[0].full_name == "Ada Lovelace"
    assert activities[0].seller_name == "National Acts"
    assert (
        "WHERE UserActivity.Timestamp BETWEEN %(startDate)s AND %(endDate)s"
        in calls[0][0]
    )
    assert "ORDER BY UserActivity.Timestamp DESC, Username ASC" in calls[0][0]
    assert calls[0][1] == {
        "startDate": datetime.fromtimestamp(1745406000).strftime("%Y-%m-%d %H:%M:%S"),
        "endDate": datetime.fromtimestamp(1745413200).strftime("%Y-%m-%d %H:%M:%S"),
    }


def test_get_user_activity_adds_user_activity_and_admin_filters(monkeypatch):
    """
    Test that get_user_activity appends user, activity, and non-admin filters when requested.
    """
    calls = []
    monkeypatch.setattr(
        user_activity_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    activities = user_activity_service.UserActivityService().get_user_activity(
        start=1745406000,
        end=1745413200,
        user_id=7,
        activity_type=3,
        filter_admins=True,
    )

    assert not activities
    assert "UserActivity.UserId = %(userId)s" in calls[0][0]
    assert "UserActivity.ActivityId = %(activityId)s" in calls[0][0]
    assert "Users.IsAdmin <> 1" in calls[0][0]
    assert calls[0][1] == {
        "startDate": datetime.fromtimestamp(1745406000).strftime("%Y-%m-%d %H:%M:%S"),
        "endDate": datetime.fromtimestamp(1745413200).strftime("%Y-%m-%d %H:%M:%S"),
        "userId": 7,
        "activityId": 3,
    }


def test_get_user_activity_returns_empty_list_when_no_rows(monkeypatch):
    """
    Test that get_user_activity returns an empty list when no rows are found.
    """
    monkeypatch.setattr(user_activity_service, "db_query_all", lambda sql, data: [])

    activities = user_activity_service.UserActivityService().get_user_activity(
        start=1745406000,
        end=1745413200,
    )

    assert not activities
