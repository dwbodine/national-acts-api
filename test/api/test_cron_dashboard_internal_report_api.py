"""
Route tests for cron, dashboard, internal, and report APIs.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app import app
from api import cron_api, dashboard_api, internal_api, report_api


def build_service(**methods):
    """
    Create a simple service object for route tests.
    """
    return lambda: SimpleNamespace(**methods)


def test_cron_update_all_events_requires_api_key(client):
    """
    Return 401 when the cron event-refresh route is missing the API key.
    """
    response = client.get("/cron/updateAllEventsFromService")

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_cron_update_all_events_starts_background_thread(
    monkeypatch, client, parse_json_response
):
    """
    Start a background thread when the cron refresh route is invoked successfully.
    """
    started = {}

    class FakeUpdateService:
        """
        Fake update service for cron refresh routes.
        """

        def update_all_events_from_ticket_socket(self):
            """
            Stand in for the background refresh target.
            """
            started["target_ran"] = True

    class FakeThread:
        """
        Fake thread object that records start requests.
        """

        def __init__(self, target, daemon):
            """
            Capture the thread target and daemon flag.
            """
            started["target"] = target
            started["daemon"] = daemon

        def start(self):
            """
            Record that the thread was started.
            """
            started["started"] = True

    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    monkeypatch.setattr(cron_api, "UpdateService", FakeUpdateService)
    monkeypatch.setattr(cron_api, "Thread", FakeThread)

    response = client.get(
        "/cron/updateAllEventsFromService",
        headers={"x-api-key": "cron-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"status": "started"}
    assert started["daemon"] is True
    assert started["started"] is True


def test_cron_historical_exchange_rate_converts_date_to_unix_time(
    monkeypatch, client, parse_json_response
):
    """
    Convert the provided historical date into a unix timestamp before refreshing.
    """
    captured = {}

    class FakeUpdateService:
        """
        Fake update service for exchange-rate refreshes.
        """

        def update_all_exchange_rates_from_stripe(self, unix_time, force_update):
            """
            Record exchange-rate refresh arguments.
            """
            captured["args"] = (unix_time, force_update)
            return [{"exchangeRate": 1.23}]

    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    monkeypatch.setattr(cron_api, "UpdateService", FakeUpdateService)

    response = client.get(
        "/cron/updateHistoricalExchangeRate/2024-05-01",
        headers={"x-api-key": "cron-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"exchangeRate": 1.23}]
    assert captured["args"] == (
        int(datetime.strptime("2024-05-01", "%Y-%m-%d").timestamp()),
        True,
    )


def test_cron_historical_event_data_requires_valid_range(monkeypatch, client):
    """
    Return 400 when the historical event refresh route is missing timestamps.
    """
    monkeypatch.setenv("CRON_API_KEY", "cron-key")

    response = client.get(
        "/cron/updateHistoricalEventData",
        headers={"x-api-key": "cron-key"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


@pytest.mark.parametrize(
    ("route", "method", "json_body"),
    [
        ("/cron/updateAllExchangeRates", "get", None),
        ("/cron/updateHistoricalExchangeRate/2024-05-01", "get", None),
        ("/cron/updateHistoricalEventData?start=1&end=2", "get", None),
        ("/cron/updateSenderApiSubscribers", "get", None),
        ("/cron/getSenderApiSubscribersCsv", "get", None),
        ("/cron/getMissingSenderApiSubscribersCsv", "get", None),
        ("/cron/formatAllPhoneNumbers", "get", None),
        ("/cron/removeMissingThumbnails", "get", None),
        ("/cron/cleanHtml", "get", None),
    ],
)
def test_cron_routes_require_api_key(client, route, method, json_body):
    """
    Return 401 for all secured cron routes when the API key is missing.
    """
    response = getattr(client, method)(route, json=json_body)

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_cron_update_all_exchange_rates_returns_service_data(
    monkeypatch, client, parse_json_response
):
    """
    Return exchange-rate refresh data from the update service.
    """
    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    monkeypatch.setattr(
        cron_api,
        "UpdateService",
        build_service(
            update_all_exchange_rates_from_stripe=lambda: [{"currency": "USD"}]
        ),
    )

    response = client.get(
        "/cron/updateAllExchangeRates",
        headers={"x-api-key": "cron-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"currency": "USD"}]


def test_cron_historical_exchange_rate_directly_handles_blank_date(monkeypatch):
    """
    Return 400 when the historical exchange-rate handler receives a blank date directly.
    """
    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    with app.test_request_context(
        "/cron/updateHistoricalExchangeRate/",
        headers={"x-api-key": "cron-key"},
    ):
        response, status_code = cron_api.update_historical_exchange_rate("")

    assert status_code == 400
    assert response == {"msg": "Bad Request"}


def test_cron_historical_event_data_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Return historical event refresh results from the update service.
    """
    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    monkeypatch.setattr(
        cron_api,
        "UpdateService",
        build_service(
            update_historical_events_from_ticket_socket=lambda start, end: [
                {"start": start, "end": end}
            ]
        ),
    )

    response = client.get(
        "/cron/updateHistoricalEventData?start=10&end=20",
        headers={"x-api-key": "cron-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"start": 10, "end": 20}]


def test_cron_sender_routes_return_service_results(
    monkeypatch, client, parse_json_response
):
    """
    Return sender API sync and CSV data from the sender service.
    """
    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    monkeypatch.setattr(
        cron_api,
        "SenderApiService",
        build_service(
            update_sender_subscribers=lambda: {"updated": True},
            get_sender_subscribers_csv=lambda: "csv-data",
            get_missing_subscribers_csv=lambda: "missing-csv",
        ),
    )

    update_response = client.get(
        "/cron/updateSenderApiSubscribers",
        headers={"x-api-key": "cron-key"},
    )
    subscribers_response = client.get(
        "/cron/getSenderApiSubscribersCsv",
        headers={"x-api-key": "cron-key"},
    )
    missing_response = client.get(
        "/cron/getMissingSenderApiSubscribersCsv",
        headers={"x-api-key": "cron-key"},
    )

    assert update_response.status_code == 200
    assert parse_json_response(update_response) == {"updated": True}
    assert subscribers_response.status_code == 200
    assert parse_json_response(subscribers_response) == "csv-data"
    assert missing_response.status_code == 200
    assert parse_json_response(missing_response) == "missing-csv"


def test_cron_update_cleanup_routes_return_service_results(
    monkeypatch, client, parse_json_response
):
    """
    Return cleanup results from the update service routes.
    """
    monkeypatch.setenv("CRON_API_KEY", "cron-key")
    monkeypatch.setattr(
        cron_api,
        "UpdateService",
        build_service(
            format_all_phone_numbers=lambda: {"formatted": 5},
            clear_out_missing_thumbnails=lambda: {"cleared": 2},
            clean_up_html=lambda: {"cleaned": 3},
        ),
    )

    phones_response = client.get(
        "/cron/formatAllPhoneNumbers",
        headers={"x-api-key": "cron-key"},
    )
    thumbnails_response = client.get(
        "/cron/removeMissingThumbnails",
        headers={"x-api-key": "cron-key"},
    )
    clean_html_response = client.get(
        "/cron/cleanHtml",
        headers={"x-api-key": "cron-key"},
    )

    assert phones_response.status_code == 200
    assert parse_json_response(phones_response) == {"formatted": 5}
    assert thumbnails_response.status_code == 200
    assert parse_json_response(thumbnails_response) == {"cleared": 2}
    assert clean_html_response.status_code == 200
    assert parse_json_response(clean_html_response) == {"cleaned": 3}


def test_dashboard_data_requires_admin(monkeypatch, client, auth_headers):
    """
    Return 401 when a non-admin requests secured dashboard data.
    """
    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: False)

    response = client.get(
        "/dashboard/getDashboardDataSecured/2025",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_dashboard_data_clamps_out_of_range_year(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Replace unsupported dashboard years with zero before loading data.
    """
    captured = {}

    class FakeDashboardService:
        """
        Fake dashboard service for secured dashboard data.
        """

        def get_dashboard_data(self, year):
            """
            Record the requested dashboard year.
            """
            captured["year"] = year
            return {"totalRevenue": 10}

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(dashboard_api, "DashboardService", FakeDashboardService)

    response = client.get(
        "/dashboard/getDashboardDataSecured/2100",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"totalRevenue": 10}
    assert captured["year"] == 0


def test_dashboard_data_uses_in_range_year(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Keep valid dashboard years unchanged before loading data.
    """
    captured = {}

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        dashboard_api,
        "DashboardService",
        build_service(
            get_dashboard_data=lambda year: captured.update({"year": year})
            or {"year": year}
        ),
    )

    response = client.get(
        "/dashboard/getDashboardDataSecured/2024",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"year": 2024}
    assert captured["year"] == 2024


def test_dashboard_data_clamps_old_years(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Replace years before 2022 with zero before loading dashboard data.
    """
    captured = {}

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        dashboard_api,
        "DashboardService",
        build_service(
            get_dashboard_data=lambda year: captured.update({"year": year})
            or {"year": year}
        ),
    )

    response = client.get(
        "/dashboard/getDashboardDataSecured/2020",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"year": 0}
    assert captured["year"] == 0


def test_dashboard_user_activity_requires_valid_start_and_end(
    monkeypatch, client, auth_headers
):
    """
    Return 400 when the user-activity route is missing a valid range.
    """
    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)

    response = client.post(
        "/dashboard/getUserActivity",
        headers=auth_headers(),
        json={"start": 0, "end": 5},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_dashboard_user_activity_requires_admin(monkeypatch, client, auth_headers):
    """
    Return 401 when a non-admin requests dashboard user activity.
    """
    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: False)

    response = client.post(
        "/dashboard/getUserActivity",
        headers=auth_headers(role="user"),
        json={"start": 10, "end": 20},
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_dashboard_user_activity_passes_optional_filters(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward optional user and activity filters to the activity service.
    """
    captured = {}

    class FakeUserActivityService:
        """
        Fake activity service for dashboard queries.
        """

        def get_user_activity(
            self,
            start,
            end,
            user_id=None,
            activity_type=None,
            filter_admins=False,
        ):
            """
            Record dashboard activity query filters.
            """
            captured["args"] = (start, end, user_id, activity_type, filter_admins)
            return [{"userId": user_id, "activityType": activity_type}]

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        dashboard_api,
        "UserActivityService",
        FakeUserActivityService,
    )

    response = client.post(
        "/dashboard/getUserActivity",
        headers=auth_headers(),
        json={
            "start": 10,
            "end": 20,
            "userId": 7,
            "activityType": 3,
            "filterAdmins": True,
        },
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"userId": 7, "activityType": 3}]
    assert captured["args"] == (10, 20, 7, 3, True)


def test_dashboard_user_activity_passes_user_only_filter(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward only the user id when activity type is omitted.
    """
    captured = {}

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        dashboard_api,
        "UserActivityService",
        build_service(
            get_user_activity=lambda start, end, user_id=None, activity_type=None, filter_admins=False: (
                captured.update(
                    {"args": (start, end, user_id, activity_type, filter_admins)}
                )
                or [{"userId": user_id}]
            )
        ),
    )

    response = client.post(
        "/dashboard/getUserActivity",
        headers=auth_headers(),
        json={"start": 10, "end": 20, "userId": 7},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"userId": 7}]
    assert captured["args"] == (10, 20, 7, None, False)


def test_dashboard_user_activity_passes_activity_only_filter(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward only the activity type when user id is omitted.
    """
    captured = {}

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        dashboard_api,
        "UserActivityService",
        build_service(
            get_user_activity=lambda start, end, user_id=None, activity_type=None, filter_admins=False: (
                captured.update(
                    {"args": (start, end, user_id, activity_type, filter_admins)}
                )
                or [{"activityType": activity_type}]
            )
        ),
    )

    response = client.post(
        "/dashboard/getUserActivity",
        headers=auth_headers(),
        json={"start": 10, "end": 20, "activityType": 4},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"activityType": 4}]
    assert captured["args"] == (10, 20, None, 4, False)


def test_dashboard_user_activity_without_optional_filters(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Request user activity without any optional filters.
    """
    captured = {}

    monkeypatch.setattr(dashboard_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(
        dashboard_api,
        "UserActivityService",
        build_service(
            get_user_activity=lambda start, end, filter_admins=False: (
                captured.update({"args": (start, end, filter_admins)})
                or [{"all": True}]
            )
        ),
    )

    response = client.post(
        "/dashboard/getUserActivity",
        headers=auth_headers(),
        json={"start": 10, "end": 20},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"all": True}]
    assert captured["args"] == (10, 20, False)


def test_internal_accounts_returns_admin_accounts(
    monkeypatch, client, parse_json_response
):
    """
    Return account data from the admin service on the internal accounts route.
    """

    class FakeAdminService:
        """
        Fake admin service for internal account lookups.
        """

        def get_all_accounts(self):
            """
            Return fake internal account data.
            """
            return [{"ticketSocketId": 5}]

    monkeypatch.setattr(internal_api, "AdminService", FakeAdminService)

    response = client.get("/internal/accounts")

    assert response.status_code == 200
    assert parse_json_response(response) == [{"ticketSocketId": 5}]


def test_internal_categories_uses_ticket_socket_id_constructor(
    monkeypatch, client, parse_json_response
):
    """
    Construct the ticket-socket service with the requested account id.
    """
    captured = {}

    class FakeTicketSocketService:
        """
        Fake ticket-socket service for category lookups.
        """

        def __init__(self, ticket_socket_id):
            """
            Capture the requested ticket-socket account id.
            """
            captured["ticket_socket_id"] = ticket_socket_id

        def get_categories(self):
            """
            Return fake category data.
            """
            return [{"categoryId": 8}]

    monkeypatch.setattr(internal_api, "TicketSocketService", FakeTicketSocketService)

    response = client.get("/internal/99/categories")

    assert response.status_code == 200
    assert parse_json_response(response) == [{"categoryId": 8}]
    assert captured["ticket_socket_id"] == 99


def test_internal_daily_order_rebuild_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Return the yearly daily-order rebuild result from the update service.
    """
    captured = {}

    class FakeUpdateService:
        """
        Fake update service for daily-order rebuilds.
        """

        def rebuild_daily_order_data_for_year(self, year, month):
            """
            Record daily-order rebuild parameters.
            """
            captured["args"] = (year, month)
            return True

    monkeypatch.setattr(internal_api, "UpdateService", FakeUpdateService)

    response = client.get("/internal/dailyorder/rebuild/2024/3")

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["args"] == (2024, 3)


def test_report_missing_venues_requires_admin(monkeypatch, client, auth_headers):
    """
    Return 401 when a non-admin user requests the missing-venues report.
    """
    monkeypatch.setattr(
        report_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=7, is_admin=False),
    )

    response = client.get("/reports/getMissingVenueEvents", headers=auth_headers())

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_report_missing_venues_returns_service_data(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return missing-venue events for admin users.
    """

    class FakeReportService:
        """
        Fake report service for missing venues.
        """

        def get_missing_venue_events(self):
            """
            Return fake missing-venue data.
            """
            return [{"eventId": 12}]

    monkeypatch.setattr(
        report_api,
        "get_user_from_jwt",
        lambda: SimpleNamespace(user_id=7, is_admin=True),
    )
    monkeypatch.setattr(report_api, "ReportService", FakeReportService)

    response = client.get("/reports/getMissingVenueEvents", headers=auth_headers())

    assert response.status_code == 200
    assert parse_json_response(response) == [{"eventId": 12}]


def test_report_header_images_is_public(monkeypatch, client, parse_json_response):
    """
    Return header-image report data without requiring authentication.
    """

    class FakeReportService:
        """
        Fake report service for public image reports.
        """

        def get_orphaned_and_missing_header_images(self):
            """
            Return fake header-image report data.
            """
            return [{"filename": "hero.jpg"}]

    monkeypatch.setattr(report_api, "ReportService", FakeReportService)

    response = client.get("/reports/headerImages")

    assert response.status_code == 200
    assert parse_json_response(response) == [{"filename": "hero.jpg"}]


@pytest.mark.parametrize(
    ("route", "method_name"),
    [
        ("/reports/thumbnailImages", "get_orphaned_and_missing_thumbnail_images"),
        ("/reports/previewImages", "get_orphaned_and_missing_preview_images"),
        ("/reports/logos", "get_orphaned_and_missing_logo_images"),
        ("/reports/banners", "get_orphaned_and_missing_banner_images"),
    ],
)
def test_report_public_image_routes_return_service_data(
    monkeypatch, client, parse_json_response, route, method_name
):
    """
    Return service data for the remaining public report routes.
    """
    monkeypatch.setattr(
        report_api,
        "ReportService",
        build_service(**{method_name: lambda: [{"route": route}]}),
    )

    response = client.get(route)

    assert response.status_code == 200
    assert parse_json_response(response) == [{"route": route}]
