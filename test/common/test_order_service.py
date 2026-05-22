"""
Unit tests for common.order_service helpers.
"""

from datetime import date, datetime

from common import order_service
from common.models.national_acts import VipOrder, VipTicket


class FakeSeller:
    """
    Test double for seller category lookups.
    """

    category_ids_by_seller_id = {}
    instances = []

    def __init__(self, seller_id):
        self.seller_id = seller_id
        FakeSeller.instances.append(self)

    def get_seller_event_category_ids(self):
        """
        Return the configured seller event category ids.
        """
        return FakeSeller.category_ids_by_seller_id.get(self.seller_id, [])


class FlakyCategoryIds:
    """
    Helper that returns different lengths on successive checks.
    """

    def __init__(self, values, lengths):
        self.values = values
        self.lengths = list(lengths)

    def __len__(self):
        """
        Return the next configured length value.
        """
        if self.lengths:
            return self.lengths.pop(0)
        return len(self.values)

    def __iter__(self):
        """
        Iterate over the configured values.
        """
        return iter(self.values)


class FakeDailyOrderService:
    """
    Test double for daily order rebuilds.
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
        Record update requests.
        """
        self.update_calls.append((orders, start, end, history))


class FixedDateTime(datetime):
    """
    Fixed datetime helper for order timestamp tests.
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


def build_order_row(**overrides):
    """
    Create an order row with sensible defaults for mapping tests.
    """
    row = {
        "ExchangeRate": 1.5,
        "Symbol": "C$",
        "Multiplier": 2.0,
        "CurrencyAbbrev": "CAD",
        "Id": 11,
        "OrderId": 2222,
        "EventId": 333,
        "LastUpdate": "2026-04-23 10:00:00",
        "EventTitle": "VIP Night",
        "EventDate": "2026-05-01",
        "SellerName": "Seller A",
        "SellerId": 7,
        "Venue": "Arena",
        "EventAddress": "123 Main",
        "EventCity": "Austin",
        "EventState": "TX",
        "EventZip": "73301",
        "EventCountry": "USA",
        "TicketSocketEventId": 44,
        "PurchaseDate": "2026-04-23",
        "PurchaseTimestamp": "2026-04-23 09:00:00",
        "PurchaseUnixTimestamp": 1713882000,
        "UserId": 88,
        "Phone": "555-1111",
        "Email": "buyer@example.com",
        "PurchaserLastName": "Lovelace",
        "PurchaserFirstName": "Ada",
        "PurchaserCity": "Austin",
        "PurchaserState": "TX",
        "PurchaserZip": "73301",
        "PurchaserCountry": "USA",
        "PurchaserIpAddress": "127.0.0.1",
        "IsActive": 1,
        "IsDeleted": 0,
        "IsComped": 0,
        "Notes": "Front row",
    }
    row.update(overrides)
    return row


def build_ticket_row(**overrides):
    """
    Create a ticket row with sensible defaults for mapping tests.
    """
    row = {
        "TicketId": 1001,
        "IsActive": 1,
        "TicketType": "VIP",
        "Price": 50.0,
        "ServiceFee": 10.0,
        "TicketSocketTicketTypeId": 7,
        "BarCode": "ABC123",
        "AvailableScans": 2,
        "PurchaseLocation": "Online",
        "ScannedTimestamp": 0,
        "AttendeeFirstName": "Ada",
        "AttendeeLastName": "Lovelace",
        "LastUpdate": "2026-04-23 10:00:00",
        "AttendeePhone": "555-1111",
        "AttendeeEmail": "ada@example.com",
        "ShirtSize": "M",
        "Id": 501,
        "IsRefunded": 0,
        "IsServiceFeeRefunded": 0,
        "RefundDate": None,
        "IsCheckedIn": 0,
        "CheckedInDate": None,
        "IsChargedBack": 0,
        "ChargebackDate": None,
        "TicketTypeOrder": 3,
    }
    row.update(overrides)
    return row


def create_ticket(
    ticket_id=501,
    order_id=11,
    refunded=False,
    charged_back=False,
    refund_date=None,
    chargeback_date=None,
):
    """
    Create a VipTicket instance for update-order tests.
    """
    ticket = VipTicket()
    ticket.ticket_socket_order_ticket_id = ticket_id
    ticket.ticket_socket_order_id = order_id
    ticket.price = 55.0
    ticket.service_fee = 12.0
    ticket.is_checked_in = True
    ticket.attendee_first_name = "Ada"
    ticket.attendee_last_name = "Lovelace"
    ticket.attendee_email = "ada@example.com"
    ticket.attendee_phone = "555-1111"
    ticket.shirt_size = "M"
    ticket.is_active = True
    ticket.is_refunded = refunded
    ticket.is_charged_back = charged_back
    ticket.refund_date = refund_date
    ticket.chargeback_date = chargeback_date
    return ticket


def create_order(ticket_socket_order_id=11):
    """
    Create a VipOrder instance for update-order tests.
    """
    order = VipOrder()
    order.ticket_socket_order_id = ticket_socket_order_id
    order.is_active = True
    order.is_deleted = False
    order.is_comped = False
    order.notes = "Updated notes"
    order.tickets = []
    return order


def test_get_orders_returns_empty_list_when_seller_has_no_categories(monkeypatch):
    """
    Test that get_orders returns nothing when the seller has no event categories.
    """
    FakeSeller.instances = []
    FakeSeller.category_ids_by_seller_id = {9: []}
    monkeypatch.setattr(order_service, "Seller", FakeSeller)

    orders = order_service.OrderService().get_orders(seller_id=9)

    assert not orders
    assert FakeSeller.instances[0].seller_id == 9


def test_get_orders_builds_numeric_search_and_maps_orders(monkeypatch):
    """
    Test that get_orders handles numeric searches and maps order totals and currency data.
    """
    calls = []
    fake_ticket = VipTicket()
    fake_ticket.price = 50
    fake_ticket.service_fee = 10
    fake_ticket.shirt_size = "L"
    fake_ticket.is_refunded = False
    fake_ticket.is_charged_back = False
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [
            build_order_row(),
            build_order_row(
                Id=12,
                OrderId=3333,
                IsDeleted=1,
                Multiplier=0,
                CurrencyAbbrev="USD",
                Symbol="$",
                Notes=None,
            ),
        ],
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "get_tickets_from_order_id",
        lambda self, ticket_socket_order_id, ignore_flags=False: [fake_ticket],
    )

    orders = order_service.OrderService().get_orders(search_term="2222")

    assert len(orders) == 2
    assert "TicketSocketOrders.OrderId=2222" in calls[0][0]
    assert orders[0].ticket_socket_order_id == 11
    assert orders[0].exchange_rate == 3.0
    assert orders[0].currency_abbrev == "CAD"
    assert orders[0].currency_symbol == "C$"
    assert orders[0].revenue == 50
    assert orders[0].service_fees == 10
    assert orders[0].notes == "Front row"
    assert orders[1].is_deleted is True
    assert orders[1].is_active is False
    assert orders[1].exchange_rate == 1.5


def test_get_orders_uses_seller_categories_and_date_filters(monkeypatch):
    """
    Test that get_orders applies seller-category and date filters for range queries.
    """
    FakeSeller.instances = []
    FakeSeller.category_ids_by_seller_id = {7: [10, 11]}
    calls = []
    monkeypatch.setattr(order_service, "Seller", FakeSeller)
    monkeypatch.setattr(
        order_service,
        "get_pacific_date_from_unix_timestamp",
        lambda unix_time: "2026-04-23" if unix_time == 1 else "2026-04-24",
    )
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders(seller_id=7, start=1, end=2)

    assert not orders
    assert "WITH" in calls[0][0]
    assert "TicketSocketEvents.SellerEventCategoryId IN" in calls[0][0]
    assert "TicketSocketOrders.IsDeleted = 0" in calls[0][0]
    assert "ExternalEvents.ExcludeFromDashboard <> 1" in calls[0][0]
    assert calls[0][1] == {
        "sellerEventCategoryId_0": 10,
        "sellerEventCategoryId_1": 11,
        "startDate": "2026-04-23",
        "endDate": "2026-04-25",
    }


def test_get_orders_filters_by_ticket_socket_order_id(monkeypatch):
    """
    Test that get_orders filters directly by the TicketSocket order id when provided.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders(ts_order_id=55)

    assert not orders
    assert "TicketSocketOrders.Id = %(order_id)s" in calls[0][0]
    assert calls[0][1] == {"order_id": 55}


def test_get_orders_builds_text_search_query(monkeypatch):
    """
    Test that get_orders uses the text-search query for non-numeric search terms.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders(search_term="Ada")

    assert not orders
    assert "CONCAT_WS" in calls[0][0]
    assert "LIKE ('%Ada%')" in calls[0][0]
    assert calls[0][1] == {}


def test_get_orders_uses_open_range_filters_for_deleted_orders(monkeypatch):
    """
    Test that get_orders uses the open-range refund CTE and deleted-only filters.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "get_pacific_date_from_unix_timestamp",
        lambda unix_time: "2026-04-23",
    )
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders(
        start=1,
        show_deleted=True,
        show_hidden_from_dashboard=True,
    )

    assert not orders
    assert "WITH" in calls[0][0]
    assert "TicketSocketOrders.IsActive = 0" in calls[0][0]
    assert "ExternalEvents.ExcludeFromDashboard <> 1" not in calls[0][0]
    assert calls[0][1] == {"startDate": "2026-04-23"}


def test_get_orders_uses_current_date_when_only_future_end_is_provided(monkeypatch):
    """
    Test that get_orders starts from the current Pacific date when only a future end is provided.
    """
    calls = []
    monkeypatch.setattr(order_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        order_service,
        "get_pacific_date_from_unix_timestamp",
        lambda unix_time: "2026-04-30",
    )
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders(end=9999999999)

    assert not orders
    assert "RefundOrders" in calls[0][0]
    assert calls[0][1] == {
        "startDate": "2026-04-23",
        "endDate": "2026-05-01",
    }


def test_get_orders_uses_current_date_when_no_dates_or_seller_are_provided(monkeypatch):
    """
    Test that get_orders defaults to current-date filtering when no seller or dates are supplied.
    """
    calls = []
    monkeypatch.setattr(order_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders()

    assert not orders
    assert "RefundOrders" in calls[0][0]
    assert calls[0][1] == {"startDate": "2026-04-23"}


def test_get_orders_allows_unfiltered_queries_when_flags_are_ignored(monkeypatch):
    """
    Test that get_orders can fall through without WHERE filters when flags are ignored.
    """
    FakeSeller.instances = []
    FakeSeller.category_ids_by_seller_id = {
        7: FlakyCategoryIds([10], [1, 0]),
    }
    calls = []
    monkeypatch.setattr(order_service, "Seller", FakeSeller)
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders(seller_id=7, ignore_flags=True)

    assert not orders
    assert calls[0][0].count(" WHERE ") == 1
    assert "TicketSocketOrders.IsDeleted = 0" not in calls[0][0]
    assert "TicketSocketEvents.SellerEventCategoryId IN " not in calls[0][0]
    assert " ORDER BY TicketSocketOrders.PurchaseDate ASC" in calls[0][0]
    assert calls[0][1] == {}


def test_get_orders_from_event_id_maps_rows_and_respects_flags(monkeypatch):
    """
    Test that get_orders_from_event_id maps order rows and appends active/deleted filters.
    """
    calls = []
    fake_ticket = VipTicket()
    fake_ticket.price = 20
    fake_ticket.service_fee = 5
    fake_ticket.is_refunded = False
    fake_ticket.is_charged_back = False
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [build_order_row()],
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "get_tickets_from_order_id",
        lambda self, ticket_socket_order_id, ignore_flags=False: [fake_ticket],
    )

    orders = order_service.OrderService().get_orders_from_event_id(44)

    assert len(orders) == 1
    assert "TicketSocketOrders.IsDeleted = 0" in calls[0][0]
    assert "TicketSocketOrders.IsActive = 1" in calls[0][0]
    assert calls[0][1] == {"ticketSocketEventId": 44}
    assert orders[0].ticket_socket_event_id == 44
    assert orders[0].revenue == 20


def test_get_orders_from_event_id_skips_flag_filters_when_requested(monkeypatch):
    """
    Test that get_orders_from_event_id skips deleted and active filters when flags are ignored.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    orders = order_service.OrderService().get_orders_from_event_id(
        44,
        show_deleted=True,
        show_inactive=True,
        ignore_flags=True,
    )

    assert not orders
    assert "TicketSocketOrders.IsDeleted = 0" not in calls[0][0]
    assert "TicketSocketOrders.IsActive = 1" not in calls[0][0]


def test_get_orders_from_event_id_marks_deleted_rows_inactive(monkeypatch):
    """
    Test that get_orders_from_event_id forces deleted orders inactive when mapping rows.
    """
    fake_ticket = VipTicket()
    fake_ticket.price = 20
    fake_ticket.service_fee = 5
    fake_ticket.is_refunded = False
    fake_ticket.is_charged_back = False
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: [
            build_order_row(
                Id=12,
                IsDeleted=1,
                IsActive=1,
                Multiplier=0,
                ExchangeRate=1.25,
            )
        ],
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "get_tickets_from_order_id",
        lambda self, ticket_socket_order_id, ignore_flags=False: [fake_ticket],
    )

    orders = order_service.OrderService().get_orders_from_event_id(44)

    assert len(orders) == 1
    assert orders[0].is_deleted is True
    assert orders[0].is_active is False
    assert orders[0].exchange_rate == 1.25


def test_rebuild_daily_order_data_for_ticket_calls_order_rebuild(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_ticket forwards positive order ids for rebuild.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: {"TicketSocketOrderId": 17},
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: calls.append(order_id),
    )

    order_service.OrderService().rebuild_daily_order_data_for_ticket(501)

    assert calls == [17]


def test_rebuild_daily_order_data_for_ticket_ignores_missing_order_rows(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_ticket does nothing when the ticket lookup is missing.
    """
    calls = []
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: None)
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: calls.append(order_id),
    )

    order_service.OrderService().rebuild_daily_order_data_for_ticket(501)

    assert not calls


def test_rebuild_daily_order_data_for_ticket_ignores_non_positive_order_ids(
    monkeypatch,
):
    """
    Test that rebuild_daily_order_data_for_ticket ignores non-positive order ids.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: {"TicketSocketOrderId": 0},
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: calls.append(order_id),
    )

    order_service.OrderService().rebuild_daily_order_data_for_ticket(501)

    assert not calls


def test_rebuild_daily_order_data_for_order_rebuilds_event_year(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_order reloads yearly orders and updates daily totals.
    """
    FakeDailyOrderService.instances = []
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: {
            "TicketSocketEventId": 44,
            "EventYear": 2026,
            "SellerId": 7,
        },
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "get_orders",
        lambda self, **kwargs: ["order-a"],
    )
    monkeypatch.setattr(order_service, "DailyOrderService", FakeDailyOrderService)

    order_service.OrderService().rebuild_daily_order_data_for_order(17)

    start = datetime.strptime("2026-01-01 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
    end = datetime(2026, 12, 31).timestamp()
    assert FakeDailyOrderService.instances[0].cleanup_calls == [44]
    assert FakeDailyOrderService.instances[0].update_calls == [
        (["order-a"], start, end, None)
    ]


def test_rebuild_daily_order_data_for_order_ignores_missing_event_rows(monkeypatch):
    """
    Test that rebuild_daily_order_data_for_order does nothing when the order event lookup is missing.
    """
    FakeDailyOrderService.instances = []
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: None)

    order_service.OrderService().rebuild_daily_order_data_for_order(17)

    assert not FakeDailyOrderService.instances


def test_get_tickets_from_order_id_maps_refund_and_chargeback_data(monkeypatch):
    """
    Test that get_tickets_from_order_id maps ticket fields including date fields.
    """
    calls = []
    pacific_conversion_calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [
            build_ticket_row(
                IsRefunded=1,
                IsServiceFeeRefunded=1,
                RefundDate=date(2026, 4, 23),
                IsCheckedIn=1,
                CheckedInDate="2026-04-23 12:00:00",
                TicketTypeOrder=None,
            ),
            build_ticket_row(
                TicketId=1002,
                Id=502,
                IsRefunded=0,
                IsChargedBack=1,
                ChargebackDate=date(2026, 4, 24),
            ),
        ],
    )

    def convert_to_pacific(utc_string):
        pacific_conversion_calls.append(utc_string)
        return f"pacific:{utc_string}"

    monkeypatch.setattr(
        order_service,
        "get_pacific_date_from_utc_datetime_string",
        convert_to_pacific,
    )

    tickets = order_service.OrderService().get_tickets_from_order_id(11)

    assert len(tickets) == 2
    assert "TicketSocketOrderTickets.IsActive=1" in calls[0][0]
    assert tickets[0].refund_date == "2026-04-23"
    assert tickets[0].ticket_type_order == 1
    assert tickets[0].is_checked_in is True
    assert tickets[0].checked_in_date == "pacific:2026-04-23 12:00:00"
    assert tickets[1].chargeback_date == "2026-04-24"
    assert pacific_conversion_calls == ["2026-04-23 12:00:00"]


def test_get_tickets_from_order_id_includes_inactive_rows_when_flags_are_ignored(
    monkeypatch,
):
    """
    Test that get_tickets_from_order_id omits the active-only filter when flags are ignored.
    """
    calls = []
    monkeypatch.setattr(
        order_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    tickets = order_service.OrderService().get_tickets_from_order_id(
        11,
        ignore_flags=True,
    )

    assert not tickets
    assert "TicketSocketOrderTickets.IsActive=1" not in calls[0][0]


def test_disable_orders_stops_after_first_failed_update(monkeypatch):
    """
    Test that disable_orders stops processing when an update fails.
    """
    update_calls = []
    rebuild_calls = []
    results = iter([True, False])
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or next(results),
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().disable_orders([11, 12, 13], disabled=True)

    assert success is False
    assert len(update_calls) == 2
    assert rebuild_calls == [11]
    assert update_calls[0][1]["is_active"] == 0


def test_disable_orders_returns_true_for_empty_order_lists(monkeypatch):
    """
    Test that disable_orders returns True when there are no orders to process.
    """
    update_calls = []
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = order_service.OrderService().disable_orders([], disabled=True)

    assert success is True
    assert not update_calls


def test_delete_orders_rebuilds_each_successful_update(monkeypatch):
    """
    Test that delete_orders rebuilds daily data after each successful update.
    """
    update_calls = []
    rebuild_calls = []
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().delete_orders([21, 22], deleted=True)

    assert success is True
    assert rebuild_calls == [21, 22]
    assert update_calls[0][1] == {"ticket_socket_order_id": 21, "isDeleted": 1}


def test_delete_orders_stops_after_first_failed_update(monkeypatch):
    """
    Test that delete_orders stops processing when an update fails.
    """
    update_calls = []
    rebuild_calls = []
    results = iter([True, False])
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or next(results),
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().delete_orders([21, 22, 23], deleted=True)

    assert success is False
    assert len(update_calls) == 2
    assert rebuild_calls == [21]


def test_check_in_tickets_sets_timestamp_when_checked_in(monkeypatch):
    """
    Test that check_in_tickets stores the current timestamp when checking tickets in.
    """
    calls = []
    monkeypatch.setattr(order_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = order_service.OrderService().check_in_tickets([501], checked_in=True)

    assert success is True
    assert calls[0][1] == {
        "ticket_socket_order_ticket_id": 501,
        "checkedIn": 1,
        "checkedInDate": "2026-04-23 12:00:00",
    }


def test_check_in_tickets_clears_timestamp_and_stops_on_failure(monkeypatch):
    """
    Test that check_in_tickets clears the timestamp when unchecking and stops on failure.
    """
    calls = []
    results = iter([True, False])
    monkeypatch.setattr(order_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or next(results),
    )

    success = order_service.OrderService().check_in_tickets(
        [501, 502], checked_in=False
    )

    assert success is False
    assert len(calls) == 2
    assert calls[0][1]["checkedInDate"] is None


def test_refund_order_marks_chargeback_and_rebuilds(monkeypatch):
    """
    Test that refund_order can mark chargebacks and rebuild daily data.
    """
    calls = []
    rebuild_calls = []
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().refund_order(
        11,
        refund_service_fees=False,
        mark_chargeback=True,
    )

    assert success is True
    assert "IsChargedBack=1" in calls[0][0]
    assert "IsServiceFeeRefunded=1" in calls[0][0]
    assert rebuild_calls == [11]


def test_refund_order_marks_refund_without_service_fee_and_skips_rebuild_on_failure(
    monkeypatch,
):
    """
    Test that refund_order leaves service fees alone and skips rebuilds when the update fails.
    """
    calls = []
    rebuild_calls = []
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or False,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().refund_order(
        11,
        refund_service_fees=False,
        mark_chargeback=False,
    )

    assert success is False
    assert "IsRefunded=1" in calls[0][0]
    assert "IsServiceFeeRefunded=1" not in calls[0][0]
    assert not rebuild_calls


def test_refund_ticket_sets_service_fee_refund_and_rebuilds(monkeypatch):
    """
    Test that refund_ticket optionally marks service fees refunded and rebuilds by ticket.
    """
    calls = []
    rebuild_calls = []
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_ticket",
        lambda self, ticket_id: rebuild_calls.append(ticket_id),
    )

    success = order_service.OrderService().refund_ticket(501, refund_service_fees=True)

    assert success is True
    assert "IsServiceFeeRefunded=1" in calls[0][0]
    assert rebuild_calls == [501]


def test_refund_ticket_skips_service_fee_refund_and_rebuild_on_failure(monkeypatch):
    """
    Test that refund_ticket skips rebuilds when the ticket refund update fails.
    """
    calls = []
    rebuild_calls = []
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or False,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_ticket",
        lambda self, ticket_id: rebuild_calls.append(ticket_id),
    )

    success = order_service.OrderService().refund_ticket(
        501,
        refund_service_fees=False,
    )

    assert success is False
    assert "IsServiceFeeRefunded=1" not in calls[0][0]
    assert not rebuild_calls


def test_update_order_returns_false_when_order_is_none():
    """
    Test that update_order returns False when no order object is supplied.
    """
    assert order_service.OrderService().update_order(None) is False


def test_update_order_returns_false_for_non_positive_order_ids():
    """
    Test that update_order returns False for non-positive TicketSocket order ids.
    """
    order_to_update = create_order(0)

    assert order_service.OrderService().update_order(order_to_update) is False


def test_update_order_returns_true_when_existing_order_is_missing(monkeypatch):
    """
    Test that update_order returns the untouched success value when the order row is missing.
    """
    update_calls = []
    order_to_update = create_order(11)
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: None)
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is True
    assert not update_calls


def test_update_order_updates_order_and_tickets_then_rebuilds(monkeypatch):
    """
    Test that update_order persists order flags, ticket changes, and rebuilds daily data.
    """
    update_calls = []
    rebuild_calls = []
    order_to_update = create_order(11)
    order_to_update.tickets = [
        create_ticket(
            ticket_id=501, order_id=11, refunded=True, refund_date="2026-04-23"
        ),
        create_ticket(
            ticket_id=502,
            order_id=11,
            refunded=False,
            charged_back=True,
            chargeback_date="2026-04-24",
        ),
    ]
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: {"Id": 11},
    )
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is True
    assert update_calls[0][1]["ticket_socket_order_id"] == 11
    assert "RefundDate=%(refundDate)s" in update_calls[1][0]
    assert update_calls[1][1]["refundDate"] == "2026-04-23"
    assert "ChargebackDate=%(chargebackDate)s" in update_calls[2][0]
    assert update_calls[2][1]["chargebackDate"] == "2026-04-24"
    assert rebuild_calls == [11]


def test_update_order_rebuilds_deleted_orders_without_updating_tickets(monkeypatch):
    """
    Test that update_order skips ticket updates when the order is deleted and still rebuilds.
    """
    update_calls = []
    rebuild_calls = []
    order_to_update = create_order(11)
    order_to_update.is_deleted = True
    order_to_update.tickets = [create_ticket(ticket_id=501, order_id=11)]
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: {"Id": 11})
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is True
    assert len(update_calls) == 1
    assert rebuild_calls == [11]


def test_update_order_rebuilds_when_no_tickets_are_supplied(monkeypatch):
    """
    Test that update_order still rebuilds when the order has no ticket updates.
    """
    update_calls = []
    rebuild_calls = []
    order_to_update = create_order(11)
    order_to_update.tickets = []
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: {"Id": 11})
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is True
    assert len(update_calls) == 1
    assert rebuild_calls == [11]


def test_update_order_skips_rebuild_when_order_update_fails(monkeypatch):
    """
    Test that update_order skips rebuilds when the main order update fails.
    """
    rebuild_calls = []
    order_to_update = create_order(11)
    order_to_update.tickets = []
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: {"Id": 11})
    monkeypatch.setattr(order_service, "db_update", lambda sql, data: False)
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is False
    assert not rebuild_calls


def test_update_order_updates_plain_tickets_without_refund_or_chargeback_dates(
    monkeypatch,
):
    """
    Test that update_order leaves refund and chargeback dates out for plain ticket updates.
    """
    update_calls = []
    rebuild_calls = []
    order_to_update = create_order(11)
    order_to_update.tickets = [create_ticket(ticket_id=501, order_id=11)]
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: {"Id": 11})
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is True
    assert "RefundDate=%(refundDate)s" not in update_calls[1][0]
    assert "ChargebackDate=%(chargebackDate)s" not in update_calls[1][0]
    assert rebuild_calls == [11]


def test_update_order_stops_when_ticket_update_fails(monkeypatch):
    """
    Test that update_order stops ticket processing and skips rebuild after a ticket failure.
    """
    update_calls = []
    rebuild_calls = []
    order_to_update = create_order(11)
    order_to_update.tickets = [create_ticket(ticket_id=501, order_id=11)]
    results = iter([True, False])
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: {"Id": 11},
    )
    monkeypatch.setattr(
        order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or next(results),
    )
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().update_order(order_to_update)

    assert success is False
    assert len(update_calls) == 2
    assert not rebuild_calls


def test_add_comped_order_returns_false_for_invalid_inputs():
    """
    Test that add_comped_order rejects invalid event ids and ticket counts.
    """
    assert order_service.OrderService().add_comped_order(0, 1) is False
    assert order_service.OrderService().add_comped_order(5, 0) is False


def test_add_comped_order_returns_true_when_no_external_event_is_found(monkeypatch):
    """
    Test that add_comped_order returns the untouched success value when no event row is found.
    """
    insert_calls = []
    monkeypatch.setattr(order_service, "db_query_one", lambda sql, data: None)
    monkeypatch.setattr(
        order_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 1,
    )

    success = order_service.OrderService().add_comped_order(5, 2)

    assert success is True
    assert not insert_calls


def test_add_comped_order_inserts_missing_type_and_tickets(monkeypatch):
    """
    Test that add_comped_order inserts the comp ticket type, order, tickets, and rebuilds.
    """
    query_responses = iter(
        [
            {"TicketSocketEventId": 44},
            {},
        ]
    )
    insert_calls = []
    rebuild_calls = []

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "TicketSocketTicketTypes" in sql:
            return 0
        if "INSERT INTO TicketSocketOrders" in sql:
            return 100
        return 200 + len(insert_calls)

    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: next(query_responses),
    )
    monkeypatch.setattr(order_service, "db_insert", fake_db_insert)
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().add_comped_order(5, 2)

    assert success is True
    assert "INSERT INTO TicketSocketTicketTypes" in insert_calls[0][0]
    assert "INSERT INTO TicketSocketOrders" in insert_calls[1][0]
    assert insert_calls[2][1] == {"order_id": 100, "ticketId": 100}
    assert insert_calls[3][1] == {"order_id": 100, "ticketId": 101}
    assert rebuild_calls == [100]


def test_add_comped_order_returns_false_when_type_activation_fails(monkeypatch):
    """
    Test that add_comped_order returns False when the existing comp type cannot be activated.
    """
    query_responses = iter(
        [
            {"TicketSocketEventId": 44},
            {"TicketSocketTicketTypeId": 0},
        ]
    )
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: next(query_responses),
    )
    monkeypatch.setattr(order_service, "db_update", lambda sql, data: False)

    success = order_service.OrderService().add_comped_order(5, 2)

    assert success is False


def test_add_comped_order_returns_false_when_order_insert_fails(monkeypatch):
    """
    Test that add_comped_order returns False when the comp order insert fails.
    """
    query_responses = iter(
        [
            {"TicketSocketEventId": 44},
            {"TicketSocketTicketTypeId": 0},
        ]
    )
    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: next(query_responses),
    )
    monkeypatch.setattr(order_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(order_service, "db_insert", lambda sql, data: 0)

    success = order_service.OrderService().add_comped_order(5, 2)

    assert success is False


def test_add_comped_order_returns_false_when_ticket_insert_fails(monkeypatch):
    """
    Test that add_comped_order stops and skips rebuilds when a ticket insert fails.
    """
    query_responses = iter(
        [
            {"TicketSocketEventId": 44},
            {"TicketSocketTicketTypeId": 0},
        ]
    )
    insert_calls = []
    rebuild_calls = []

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "INSERT INTO TicketSocketOrders" in sql:
            return 100
        return 0

    monkeypatch.setattr(
        order_service,
        "db_query_one",
        lambda sql, data: next(query_responses),
    )
    monkeypatch.setattr(order_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(order_service, "db_insert", fake_db_insert)
    monkeypatch.setattr(
        order_service.OrderService,
        "rebuild_daily_order_data_for_order",
        lambda self, order_id: rebuild_calls.append(order_id),
    )

    success = order_service.OrderService().add_comped_order(5, 2)

    assert success is False
    assert len(insert_calls) == 2
    assert not rebuild_calls
