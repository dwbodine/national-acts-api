"""
Unit tests for common.update_service helpers.
"""

from datetime import datetime

from common import update_service
from common.models.national_acts import FileReport, TicketSocketRefreshHistory


class FixedDateTime(datetime):
    """
    Fixed datetime helper for deterministic update-service tests.
    """

    @classmethod
    def now(cls, tz=None):
        """
        Return a fixed current datetime.
        """
        current = cls(2026, 4, 23, 12, 0, 0)
        if tz is not None:
            return tz.localize(current)
        return current

    @classmethod
    def strptime(cls, date_string, fmt):  # pylint: disable=arguments-renamed
        """
        Parse strings into fixed datetime instances.
        """
        parsed = datetime.strptime(date_string, fmt)
        return cls(
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            parsed.second,
        )

    @classmethod
    def fromtimestamp(cls, timestamp, tz=None):
        """
        Convert timestamps into fixed datetime instances.
        """
        parsed = datetime.fromtimestamp(timestamp, tz=tz)
        return cls(
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            parsed.second,
        )


class FakeExchangeRateService:
    """
    Test double for ExchangeRateService lookups.
    """

    instances = []

    def __init__(self, exchange_rate):
        self.exchange_rate = exchange_rate
        self.calls = []
        FakeExchangeRateService.instances.append(self)

    def get_exchange_rate_by_time(self, unix_time, force_update):
        """
        Return the configured exchange rate.
        """
        self.calls.append((unix_time, force_update))
        self.exchange_rate.usd_rate = 1.25
        return self.exchange_rate


class FakeOrderService:
    """
    Test double for order retrieval during update runs.
    """

    instances = []
    orders_to_return = []

    def __init__(self):
        self.calls = []
        FakeOrderService.instances.append(self)

    def get_orders(self, start=None, end=None):
        """
        Return the configured order list.
        """
        self.calls.append((start, end))
        return FakeOrderService.orders_to_return


class FakeDailyOrderService:
    """
    Test double for daily order rollup updates.
    """

    instances = []
    result_to_return = None

    def __init__(self):
        self.calls = []
        FakeDailyOrderService.instances.append(self)

    def update_daily_order_data(self, orders, start, end, history):
        """
        Return the configured update result.
        """
        self.calls.append((orders, start, end, history))
        return FakeDailyOrderService.result_to_return


class FakeDataRefreshService:
    """
    Test double for TicketSocket refresh orchestration.
    """

    instances = []
    result_to_return = None
    error_to_raise = None

    def __init__(self):
        self.calls = []
        FakeDataRefreshService.instances.append(self)

    def refresh_database_from_ticket_socket(self, start=None, end=None):
        """
        Return the configured refresh result or raise a configured error.
        """
        self.calls.append((start, end))
        if FakeDataRefreshService.error_to_raise is not None:
            raise FakeDataRefreshService.error_to_raise
        return FakeDataRefreshService.result_to_return


class FakeReportService:
    """
    Test double for thumbnail report generation.
    """

    instances = []
    report_to_return = None

    def __init__(self):
        FakeReportService.instances.append(self)

    def get_orphaned_and_missing_thumbnail_images(self):
        """
        Return the configured thumbnail report.
        """
        return FakeReportService.report_to_return


class FakeDashboardService:
    """
    Test double for dashboard rebuild requests.
    """

    instances = []

    def __init__(self):
        self.calls = []
        FakeDashboardService.instances.append(self)

    def rebuild_daily_order_data_for_event(self, event_id):
        """
        Record rebuild requests.
        """
        self.calls.append(event_id)


def create_refresh_history(succeeded=True, error_message=None):
    """
    Create a TicketSocketRefreshHistory instance for orchestration tests.
    """
    return TicketSocketRefreshHistory(
        [],
        [],
        [],
        [],
        [],
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0.0,
        succeeded=succeeded,
        error_message=error_message,
    )


def test_update_all_exchange_rates_from_stripe_returns_success_message(monkeypatch):
    """
    Test that update_all_exchange_rates_from_stripe updates all rows and reports success.
    """
    FakeExchangeRateService.instances = []
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(update_service, "ExchangeRateService", FakeExchangeRateService)
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [
            {"ExchangeRateId": 1, "ServiceTokenId": "usd", "Symbol": "$"},
            {"ExchangeRateId": 2, "ServiceTokenId": "cad", "Symbol": "C$"},
        ],
    )

    result = update_service.UpdateService().update_all_exchange_rates_from_stripe(
        unix_time=123,
        force_update=True,
    )

    assert result == "[2026-04-23 12:00:00] - Exchange rates update succeeded\r\n"
    assert len(FakeExchangeRateService.instances) == 2
    assert FakeExchangeRateService.instances[0].calls == [(123, True)]
    assert (
        FakeExchangeRateService.instances[0].exchange_rate.exchange_rate_slug == "usd"
    )
    assert FakeExchangeRateService.instances[1].exchange_rate.currency_symbol == "C$"


def test_update_all_exchange_rates_from_stripe_returns_failure_message_when_empty(
    monkeypatch,
):
    """
    Test that update_all_exchange_rates_from_stripe reports failure when no rates are found.
    """
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(update_service, "db_query_all", lambda sql: [])

    result = update_service.UpdateService().update_all_exchange_rates_from_stripe()

    assert result == "[2026-04-23 12:00:00] - Exchange rates update failed\r\n"


def test_update_all_exchange_rates_from_stripe_returns_exception_message(monkeypatch):
    """
    Test that update_all_exchange_rates_from_stripe returns exception details on failure.
    """
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = update_service.UpdateService().update_all_exchange_rates_from_stripe()

    assert result.startswith("[2026-04-23 12:00:00] - boom")
    assert "Traceback" in result


def test_update_all_events_from_ticket_socket_runs_daily_rollup_on_success(
    monkeypatch,
):
    """
    Test that update_all_events_from_ticket_socket
    refreshes events and updates daily orders on success.
    """
    FakeDataRefreshService.instances = []
    FakeOrderService.instances = []
    FakeDailyOrderService.instances = []
    refresh_history = create_refresh_history(succeeded=True)
    final_history = create_refresh_history(succeeded=True)
    FakeDataRefreshService.result_to_return = refresh_history
    FakeDataRefreshService.error_to_raise = None
    FakeOrderService.orders_to_return = ["order-1", "order-2"]
    FakeDailyOrderService.result_to_return = final_history
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(update_service, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(update_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(update_service, "DailyOrderService", FakeDailyOrderService)

    result = update_service.UpdateService().update_all_events_from_ticket_socket()

    expected_start = FixedDateTime.strptime(
        "2026-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
    ).timestamp()
    expected_end = FixedDateTime(2026, 4, 23).timestamp()

    assert result == "[2026-04-23 12:00:00] - Auto events update succeeded\r\n"
    assert FakeDataRefreshService.instances[0].calls == [(None, None)]
    assert FakeOrderService.instances[0].calls == [(expected_start, expected_end)]
    assert FakeDailyOrderService.instances[0].calls == [
        (["order-1", "order-2"], expected_start, expected_end, refresh_history)
    ]


def test_update_all_events_from_ticket_socket_reports_daily_rollup_failure(
    monkeypatch,
):
    """
    Test that update_all_events_from_ticket_socket
    includes the daily-rollup error message on failure.
    """
    refresh_history = create_refresh_history(succeeded=True)
    final_history = create_refresh_history(
        succeeded=False,
        error_message="daily rollup failed",
    )
    FakeDataRefreshService.result_to_return = refresh_history
    FakeDataRefreshService.error_to_raise = None
    FakeOrderService.orders_to_return = []
    FakeDailyOrderService.result_to_return = final_history
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(update_service, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(update_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(update_service, "DailyOrderService", FakeDailyOrderService)

    result = update_service.UpdateService().update_all_events_from_ticket_socket()

    assert "Auto events update failed" in result
    assert "daily rollup failed" in result


def test_update_all_events_from_ticket_socket_returns_base_message_when_refresh_fails(
    monkeypatch,
):
    """
    Test that update_all_events_from_ticket_socket returns the base timestamped message when refresh does not succeed.
    """
    FakeDataRefreshService.instances = []
    FakeOrderService.instances = []
    FakeDailyOrderService.instances = []
    FakeDataRefreshService.result_to_return = create_refresh_history(succeeded=False)
    FakeDataRefreshService.error_to_raise = None
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(update_service, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(update_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(update_service, "DailyOrderService", FakeDailyOrderService)

    result = update_service.UpdateService().update_all_events_from_ticket_socket()

    assert result == "[2026-04-23 12:00:00] - "
    assert not FakeOrderService.instances
    assert not FakeDailyOrderService.instances


def test_update_all_events_from_ticket_socket_returns_exception_message(
    monkeypatch,
):
    """
    Test that update_all_events_from_ticket_socket returns exception details when refresh fails.
    """
    logged_errors = []
    FakeDataRefreshService.result_to_return = None
    FakeDataRefreshService.error_to_raise = RuntimeError("refresh blew up")
    monkeypatch.setattr(update_service, "datetime", FixedDateTime)
    monkeypatch.setattr(update_service, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(
        update_service.logger,
        "error",
        logged_errors.append,
    )

    result = update_service.UpdateService().update_all_events_from_ticket_socket()

    assert result.startswith("[2026-04-23 12:00:00] - refresh blew up")
    assert "Traceback" in result
    assert logged_errors


def test_update_historical_events_from_ticket_socket_runs_daily_rollup(monkeypatch):
    """
    Test that update_historical_events_from_ticket_socket
    refreshes and updates daily orders on success.
    """
    refresh_history = create_refresh_history(succeeded=True)
    final_history = create_refresh_history(succeeded=True)
    FakeDataRefreshService.result_to_return = refresh_history
    FakeDataRefreshService.error_to_raise = None
    FakeOrderService.orders_to_return = ["order-1"]
    FakeDailyOrderService.result_to_return = final_history
    monkeypatch.setattr(update_service, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(update_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(update_service, "DailyOrderService", FakeDailyOrderService)

    result = update_service.UpdateService().update_historical_events_from_ticket_socket(
        start=10,
        end=20,
    )

    assert result is final_history
    assert FakeDataRefreshService.instances[-1].calls == [(10, 20)]
    assert FakeOrderService.instances[-1].calls == [(10, 20)]
    assert FakeDailyOrderService.instances[-1].calls == [
        (["order-1"], 10, 20, refresh_history)
    ]


def test_update_historical_events_from_ticket_socket_returns_refresh_result_when_failed(
    monkeypatch,
):
    """
    Test that update_historical_events_from_ticket_socket
    returns the refresh result unchanged when it fails.
    """
    refresh_history = create_refresh_history(
        succeeded=False,
        error_message="refresh failed",
    )
    FakeDataRefreshService.result_to_return = refresh_history
    FakeDataRefreshService.error_to_raise = None
    monkeypatch.setattr(update_service, "DataRefreshService", FakeDataRefreshService)
    monkeypatch.setattr(update_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(update_service, "DailyOrderService", FakeDailyOrderService)

    result = update_service.UpdateService().update_historical_events_from_ticket_socket(
        start=10,
        end=20,
    )

    assert result is refresh_history


def test_format_all_phone_numbers_formats_valid_numbers_and_clears_invalid(
    monkeypatch,
):
    """
    Test that format_all_phone_numbers formats valid numbers and clears invalid or unparsable ones.
    """
    update_calls = []
    logged_errors = []
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [
            {"Id": 1, "Phone": "(555) 111-2222", "CountryCode": "US"},
            {"Id": 2, "Phone": "invalid", "CountryCode": "US"},
            {"Id": 3, "Phone": "boom", "CountryCode": "US"},
        ],
    )
    monkeypatch.setattr(
        update_service,
        "clean_up_phone_input_for_parsing",
        lambda phone: phone,
    )

    def fake_parse(phone, country_code):
        if phone == "boom":
            raise RuntimeError("parse failed")
        return f"{country_code}:{phone}"

    monkeypatch.setattr(update_service.phonenumbers, "parse", fake_parse)
    monkeypatch.setattr(
        update_service.phonenumbers,
        "is_possible_number",
        lambda parsed: parsed == "US:(555) 111-2222",
    )
    monkeypatch.setattr(
        update_service.phonenumbers,
        "format_number",
        lambda parsed, fmt: "+1 555 111 2222",
    )
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        update_service.logger,
        "error",
        lambda message, error: logged_errors.append((message, error)),
    )

    success = update_service.UpdateService().format_all_phone_numbers()

    assert success is True
    assert update_calls[0][1] == {"phone": "+1 555 111 2222", "order_id": 1}
    assert update_calls[1][1] == {"phone": None, "order_id": 2}
    assert update_calls[2][1] == {"phone": None, "order_id": 3}
    assert logged_errors
    assert "parse failed" in logged_errors[0][1]


def test_format_all_phone_numbers_stops_when_update_fails(monkeypatch):
    """
    Test that format_all_phone_numbers stops processing when a database update fails.
    """
    update_calls = []
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [
            {"Id": 1, "Phone": "5551112222", "CountryCode": "US"},
            {"Id": 2, "Phone": "5553334444", "CountryCode": "US"},
        ],
    )
    monkeypatch.setattr(
        update_service,
        "clean_up_phone_input_for_parsing",
        lambda phone: phone,
    )
    monkeypatch.setattr(
        update_service.phonenumbers, "parse", lambda phone, country: phone
    )
    monkeypatch.setattr(
        update_service.phonenumbers, "is_possible_number", lambda z: True
    )
    monkeypatch.setattr(
        update_service.phonenumbers,
        "format_number",
        lambda parsed, fmt: parsed,
    )
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or False,
    )

    success = update_service.UpdateService().format_all_phone_numbers()

    assert success is False
    assert len(update_calls) == 1


def test_format_all_phone_numbers_updates_none_for_blank_phones(monkeypatch):
    """
    Test that format_all_phone_numbers stores None when a phone number is blank after cleanup.
    """
    update_calls = []
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [{"Id": 7, "Phone": "   ", "CountryCode": "US"}],
    )
    monkeypatch.setattr(
        update_service,
        "clean_up_phone_input_for_parsing",
        lambda phone: "",
    )
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = update_service.UpdateService().format_all_phone_numbers()

    assert success is True
    assert update_calls[0][1] == {"phone": None, "order_id": 7}


def test_clear_out_missing_thumbnails_updates_matching_old_events(monkeypatch):
    """
    Test that clear_out_missing_thumbnails clears thumbnails only when a matching event exists.
    """
    update_calls = []
    FakeReportService.report_to_return = FileReport(
        orphaned=[],
        missing=["missing-a.jpg", "missing-b.jpg"],
    )
    monkeypatch.setattr(update_service, "ReportService", FakeReportService)

    def fake_db_query_one(_sql, data):
        return {"EventId": 1} if data["thumb"] == "missing-a.jpg" else None

    monkeypatch.setattr(update_service, "db_query_one", fake_db_query_one)
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = update_service.UpdateService().clear_out_missing_thumbnails()

    assert success is True
    assert len(update_calls) == 1
    assert update_calls[0][1] == {"thumb": "missing-a.jpg"}


def test_clear_out_missing_thumbnails_returns_true_when_no_missing_files(monkeypatch):
    """
    Test that clear_out_missing_thumbnails returns True without querying rows when no missing files exist.
    """
    FakeReportService.report_to_return = FileReport(orphaned=[], missing=[])
    monkeypatch.setattr(update_service, "ReportService", FakeReportService)
    monkeypatch.setattr(
        update_service,
        "db_query_one",
        lambda sql, data: (_ for _ in ()).throw(
            AssertionError("db_query_one should not run")
        ),
    )

    success = update_service.UpdateService().clear_out_missing_thumbnails()

    assert success is True


def test_clear_out_missing_thumbnails_stops_when_update_fails(monkeypatch):
    """
    Test that clear_out_missing_thumbnails stops when clearing a missing thumbnail fails.
    """
    FakeReportService.report_to_return = FileReport(
        orphaned=[], missing=["missing-a.jpg"]
    )
    monkeypatch.setattr(update_service, "ReportService", FakeReportService)
    monkeypatch.setattr(
        update_service, "db_query_one", lambda sql, data: {"EventId": 1}
    )
    monkeypatch.setattr(update_service, "db_update", lambda sql, data: False)

    success = update_service.UpdateService().clear_out_missing_thumbnails()

    assert success is False


def test_clean_up_html_removes_wrappers_and_updates_changed_pages(monkeypatch):
    """
    Test that clean_up_html strips wrapper markup and updates only changed HTML.
    """
    update_calls = []
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [
            {
                "PageID": 1,
                "HTMLText": (
                    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                    "<title>Title</title></head><body><p>Hello</p></body></html>"
                ),
            },
            {"PageID": 2, "HTMLText": "<p>Already Clean</p>"},
            {"PageID": 3, "HTMLText": "<html><body></body></html>"},
        ],
    )
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = update_service.UpdateService().clean_up_html()

    assert success is True
    assert len(update_calls) == 2
    assert update_calls[0][1] == {"html_text": "<p>Hello</p>", "page_id": 1}
    assert update_calls[1][1] == {"html_text": None, "page_id": 3}


def test_clean_up_html_skips_rows_with_none_html_text(monkeypatch):
    """
    Test that clean_up_html skips rows whose html text is None.
    """
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [{"PageID": 9, "HTMLText": None}],
    )
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: (_ for _ in ()).throw(
            AssertionError("db_update should not run")
        ),
    )

    success = update_service.UpdateService().clean_up_html()

    assert success is True


def test_clean_up_html_stops_when_update_fails(monkeypatch):
    """
    Test that clean_up_html stops processing when an HTML update fails.
    """
    update_calls = []
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql: [
            {"PageID": 1, "HTMLText": "<html><body><p>Hello</p></body></html>"}
        ],
    )
    monkeypatch.setattr(
        update_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or False,
    )

    success = update_service.UpdateService().clean_up_html()

    assert success is False
    assert len(update_calls) == 1


def test_rebuild_daily_order_data_for_year_rebuilds_each_event(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_year rebuilds daily order data for each matching event.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(update_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(
        update_service,
        "db_query_all",
        lambda sql, data: [{"Id": 10}, {"Id": 20}],
    )

    success = update_service.UpdateService().rebuild_daily_order_data_for_year(2026, 4)

    assert success is True
    assert FakeDashboardService.instances[0].calls == [10, 20]


def test_rebuild_daily_order_data_for_year_returns_true_for_empty_results(
    monkeypatch,
):
    """
    Test that rebuild_daily_order_data_for_year returns true when no events need rebuilding.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(update_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(update_service, "db_query_all", lambda sql, data: [])

    success = update_service.UpdateService().rebuild_daily_order_data_for_year(2026, 4)

    assert success is True
    assert FakeDashboardService.instances[0].calls == []
