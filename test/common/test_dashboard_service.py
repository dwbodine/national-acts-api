"""
Unit tests for common.dashboard_service helpers.
"""

from datetime import datetime

from common import dashboard_service


class FakeDashboardTotals:
    """
    Test double for DashboardTotals that avoids unrelated settings queries.
    """

    def __init__(self, year, month, day):
        self.year = year
        self.month = month
        self.day = day
        self.tickets = 0
        self.orders = 0
        self.num_tickets_refunded = 0
        self.num_tickets_charged_back = 0
        self.ticket_revenue = 0
        self.ticket_revenue_usd = 0
        self.service_fees_revenue = 0
        self.service_fees_revenue_usd = 0
        self.total_revenue = 0
        self.total_revenue_usd = 0
        self.revenue_refunded = 0
        self.revenue_refunded_usd = 0
        self.revenue_charged_back = 0
        self.revenue_charged_back_usd = 0
        self.service_fee_revenue_refunded = 0
        self.service_fee_revenue_refunded_usd = 0
        self.service_fee_revenue_charged_back = 0
        self.service_fee_revenue_charged_back_usd = 0
        self.price_per_ticket = 0
        self.service_fee_per_ticket = 0
        self.daily_order_data = []


class FakeDailyOrderService:
    """
    Test double for DailyOrderService rebuild orchestration.
    """

    instances = []

    def __init__(self):
        self.cleanup_calls = []
        self.update_calls = []
        FakeDailyOrderService.instances.append(self)

    def cleanup_daily_order_data_for_event(self, event_id):
        """
        Record cleanup requests.
        """
        self.cleanup_calls.append(event_id)

    def update_daily_order_data(self, orders, start, end, history):
        """
        Record daily order data rebuild requests.
        """
        self.update_calls.append((orders, start, end, history))


class FakeOrderService:
    """
    Test double for OrderService event order lookups.
    """

    instances = []
    orders_to_return = []

    def __init__(self):
        self.calls = []
        FakeOrderService.instances.append(self)

    def get_orders(self, start, end, seller_id):
        """
        Record get_orders arguments and return the configured orders.
        """
        self.calls.append((start, end, seller_id))
        return FakeOrderService.orders_to_return


class FixedDateTime(datetime):
    """
    Fixed datetime helper for current-date dashboard tests.
    """

    @classmethod
    def now(cls, tz=None):
        """
        Return a fixed current datetime.
        """
        return cls(2026, 4, 23, 12, 0, 0, tzinfo=tz)


def test_get_dashboard_data_rolls_up_purchase_refund_and_chargeback_rows(
    monkeypatch,
):
    """
    Test that get_dashboard_data maps dashboard rows and rolls up totals.
    """
    calls = []
    monkeypatch.setattr(dashboard_service, "DashboardTotals", FakeDashboardTotals)

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        return [
            {
                "PurchaseDate": "2026-01-10",
                "TicketSocketEventId": 11,
                "ExchangeRate": 2.0,
                "CurrencySymbol": "C$",
                "LastUpdate": "2026-01-10 10:00:00",
                "Title": "VIP Night",
                "EventDate": "2026-02-01",
                "SellerId": 7,
                "SellerName": "Seller A",
                "Venue": "Arena",
                "City": "Austin",
                "State": "TX",
                "Country": "USA",
                "Zip": "73301",
                "Tickets": 2,
                "Orders": 1,
                "TicketRevenue": 100.0,
                "ServiceFeeRevenue": 20.0,
                "TotalRevenue": 120.0,
                "TicketSocketId": 5,
                "TicketSocketOrderId": None,
                "IsRefunded": 0,
                "NumTicketsRefunded": 0,
                "RevenueRefunded": 0,
                "ServiceFeeRevenueRefunded": 0,
                "IsChargeback": 0,
                "NumTicketsChargedBack": 0,
                "RevenueChargedBack": 0,
                "ServiceFeeRevenueChargedBack": 0,
            },
            {
                "PurchaseDate": "2026-01-11",
                "TicketSocketEventId": 11,
                "ExchangeRate": 2.0,
                "CurrencySymbol": "C$",
                "LastUpdate": "2026-01-11 10:00:00",
                "Title": "VIP Night",
                "EventDate": "2026-02-01",
                "SellerId": 7,
                "SellerName": "Seller A",
                "Venue": "Arena",
                "City": "Austin",
                "State": "TX",
                "Country": "USA",
                "Zip": "73301",
                "Tickets": 0,
                "Orders": 0,
                "TicketRevenue": 0.0,
                "ServiceFeeRevenue": 0.0,
                "TotalRevenue": 0.0,
                "TicketSocketId": 5,
                "TicketSocketOrderId": 99,
                "IsRefunded": 1,
                "NumTicketsRefunded": 1,
                "RevenueRefunded": 50.0,
                "ServiceFeeRevenueRefunded": 10.0,
                "IsChargeback": 0,
                "NumTicketsChargedBack": 0,
                "RevenueChargedBack": 0,
                "ServiceFeeRevenueChargedBack": 0,
            },
            {
                "PurchaseDate": "2026-01-12",
                "TicketSocketEventId": 11,
                "ExchangeRate": 2.0,
                "CurrencySymbol": "C$",
                "LastUpdate": "2026-01-12 10:00:00",
                "Title": "VIP Night",
                "EventDate": "2026-02-01",
                "SellerId": 7,
                "SellerName": "Seller A",
                "Venue": "Arena",
                "City": "Austin",
                "State": "TX",
                "Country": "USA",
                "Zip": "73301",
                "Tickets": 0,
                "Orders": 0,
                "TicketRevenue": 0.0,
                "ServiceFeeRevenue": 0.0,
                "TotalRevenue": 0.0,
                "TicketSocketId": 5,
                "TicketSocketOrderId": 100,
                "IsRefunded": 0,
                "NumTicketsRefunded": 0,
                "RevenueRefunded": 0,
                "ServiceFeeRevenueRefunded": 0,
                "IsChargeback": 1,
                "NumTicketsChargedBack": 1,
                "RevenueChargedBack": 40.0,
                "ServiceFeeRevenueChargedBack": 5.0,
            },
        ]

    monkeypatch.setattr(dashboard_service, "db_query_all", fake_db_query_all)

    totals = dashboard_service.DashboardService().get_dashboard_data(2026)

    assert calls[0][1] == {
        "start": "2026-01-01 00:00:00",
        "end": "2026-12-31 23:59:59",
    }
    assert len(totals.daily_order_data) == 3
    assert totals.year == 2026
    assert totals.month == 12
    assert totals.day == 31
    assert totals.tickets == 2
    assert totals.orders == 1
    assert totals.ticket_revenue == 100.0
    assert totals.ticket_revenue_usd == 200.0
    assert totals.service_fees_revenue == 20.0
    assert totals.service_fees_revenue_usd == 40.0
    assert totals.total_revenue == 120.0
    assert totals.total_revenue_usd == 240.0
    assert totals.num_tickets_refunded == 1
    assert totals.revenue_refunded == 50.0
    assert totals.revenue_refunded_usd == 100.0
    assert totals.service_fee_revenue_refunded == 10.0
    assert totals.service_fee_revenue_refunded_usd == 20.0
    assert totals.num_tickets_charged_back == 1
    assert totals.revenue_charged_back == 40.0
    assert totals.revenue_charged_back_usd == 80.0
    assert totals.service_fee_revenue_charged_back == 5.0
    assert totals.service_fee_revenue_charged_back_usd == 10.0
    assert totals.price_per_ticket == 100.0
    assert totals.service_fee_per_ticket == 20.0


def test_get_dashboard_data_uses_current_pacific_date_when_year_is_not_provided(
    monkeypatch,
):
    """
    Test that get_dashboard_data uses the current Pacific date when year is omitted.
    """
    calls = []
    monkeypatch.setattr(dashboard_service, "DashboardTotals", FakeDashboardTotals)
    monkeypatch.setattr(dashboard_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        dashboard_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    totals = dashboard_service.DashboardService().get_dashboard_data()

    assert totals.year == 2026
    assert totals.month == 4
    assert totals.day == 23
    assert calls[0][1] == {
        "start": "2026-01-01 00:00:00",
        "end": "2026-04-23 23:59:59",
    }
    assert not totals.daily_order_data
    assert totals.price_per_ticket == 0
    assert totals.service_fee_per_ticket == 0


def test_rebuild_daily_order_data_for_event_returns_without_event_row(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_event exits when the event lookup returns nothing.
    """
    FakeDailyOrderService.instances = []
    FakeOrderService.instances = []
    monkeypatch.setattr(dashboard_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(dashboard_service, "DailyOrderService", FakeDailyOrderService)
    monkeypatch.setattr(dashboard_service, "OrderService", FakeOrderService)

    dashboard_service.DashboardService().rebuild_daily_order_data_for_event(44)
    assert not FakeDailyOrderService.instances
    assert not FakeOrderService.instances


def test_rebuild_daily_order_data_for_event_only_cleans_when_hidden(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_event only clears data when the event is hidden.
    """
    FakeDailyOrderService.instances = []
    FakeOrderService.instances = []
    monkeypatch.setattr(
        dashboard_service,
        "db_query_one",
        lambda sql, data: {
            "TicketSocketEventId": 55,
            "EventYear": 2026,
            "SellerId": 7,
            "ExcludeFromDashboard": 1,
        },
    )
    monkeypatch.setattr(dashboard_service, "DailyOrderService", FakeDailyOrderService)
    monkeypatch.setattr(dashboard_service, "OrderService", FakeOrderService)

    dashboard_service.DashboardService().rebuild_daily_order_data_for_event(55)

    assert FakeDailyOrderService.instances[0].cleanup_calls == [55]
    assert not FakeDailyOrderService.instances[0].update_calls
    assert not FakeOrderService.instances


def test_rebuild_daily_order_data_for_event_rebuilds_visible_event(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_event cleans, loads orders, and updates rollups.
    """
    FakeDailyOrderService.instances = []
    FakeOrderService.instances = []
    fake_orders = ["order-a", "order-b"]
    FakeOrderService.orders_to_return = fake_orders
    monkeypatch.setattr(
        dashboard_service,
        "db_query_one",
        lambda sql, data: {
            "TicketSocketEventId": 88,
            "EventYear": 2026,
            "SellerId": 9,
            "ExcludeFromDashboard": 0,
        },
    )
    monkeypatch.setattr(dashboard_service, "DailyOrderService", FakeDailyOrderService)
    monkeypatch.setattr(dashboard_service, "OrderService", FakeOrderService)

    dashboard_service.DashboardService().rebuild_daily_order_data_for_event(88)

    start = datetime.strptime("2026-01-01 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
    end = datetime(2026, 12, 31).timestamp()
    assert FakeDailyOrderService.instances[0].cleanup_calls == [88]
    assert FakeOrderService.instances[0].calls == [(start, end, 9)]
    assert FakeDailyOrderService.instances[0].update_calls == [
        (fake_orders, start, end, None)
    ]


def test_rebuild_daily_order_data_for_event_skips_update_when_no_orders(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_event skips rollup updates when no orders are returned.
    """
    FakeDailyOrderService.instances = []
    FakeOrderService.instances = []
    FakeOrderService.orders_to_return = []
    monkeypatch.setattr(
        dashboard_service,
        "db_query_one",
        lambda sql, data: {
            "TicketSocketEventId": 89,
            "EventYear": 2026,
            "SellerId": 11,
            "ExcludeFromDashboard": 0,
        },
    )
    monkeypatch.setattr(dashboard_service, "DailyOrderService", FakeDailyOrderService)
    monkeypatch.setattr(dashboard_service, "OrderService", FakeOrderService)

    dashboard_service.DashboardService().rebuild_daily_order_data_for_event(89)

    assert FakeDailyOrderService.instances[0].cleanup_calls == [89]
    assert not FakeDailyOrderService.instances[0].update_calls
