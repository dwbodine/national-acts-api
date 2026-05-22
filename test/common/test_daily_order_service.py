"""
Unit tests for common.daily_order_service helpers.
"""

from datetime import datetime
from types import SimpleNamespace

from common.daily_order_service import DailyOrderService
from common.models.exchange_rate import ExchangeRate
from common.models.national_acts import VipOrder


class FakeHistory:
    """
    Test double for TicketSocketRefreshHistory order update bookkeeping.
    """

    def __init__(self):
        self.order_data_rows_total = 0
        self.order_data_update_succeeded = None
        self.calls = []

    def set_order_update_success(self, success, duration, inserts, updates):
        """
        Record order update status for assertions.
        """
        self.calls.append((success, duration, inserts, updates))


def create_ticket(
    is_refunded=False,
    refund_date=None,
    is_charged_back=False,
    chargeback_date=None,
):
    """
    Create a simple ticket object for daily order rollup tests.
    """
    return SimpleNamespace(
        is_refunded=is_refunded,
        refund_date=refund_date,
        is_charged_back=is_charged_back,
        chargeback_date=chargeback_date,
    )


def create_order(
    ticket_socket_event_id=10,
    ticket_socket_order_id=100,
    purchase_date="2026-05-01",
    num_tickets=2,
    revenue=100.0,
    service_fees=20.0,
    is_deleted=False,
    is_comped=False,
    has_refunds=False,
    has_chargebacks=False,
    num_tickets_refunded=0,
    revenue_refunded=0.0,
    service_fee_revenue_refunded=0.0,
    num_tickets_charged_back=0,
    revenue_charged_back=0.0,
    service_fee_revenue_charged_back=0.0,
    tickets=None,
):
    """
    Create a VipOrder instance with the fields used by DailyOrderService.
    """
    order = VipOrder()
    order.ticket_socket_event_id = ticket_socket_event_id
    order.ticket_socket_order_id = ticket_socket_order_id
    order.purchase_date = purchase_date
    order.purchase_unix_timestamp = None
    order.is_deleted = is_deleted
    order.is_comped = is_comped
    order.has_refunds = has_refunds
    order.has_chargebacks = has_chargebacks
    order.num_tickets = num_tickets
    order.revenue = revenue
    order.service_fees = service_fees
    order.num_tickets_refunded = num_tickets_refunded
    order.revenue_refunded = revenue_refunded
    order.service_fee_revenue_refunded = service_fee_revenue_refunded
    order.num_tickets_charged_back = num_tickets_charged_back
    order.revenue_charged_back = revenue_charged_back
    order.service_fee_revenue_charged_back = service_fee_revenue_charged_back
    order.tickets = tickets or []
    return order


def create_exchange_rate(usd_rate, currency_symbol, multiplier=1.0):
    """
    Create an ExchangeRate instance for mocked lookup results.
    """
    exchange_rate = ExchangeRate(1, "usd", currency_symbol)
    exchange_rate.usd_rate = usd_rate
    exchange_rate.multiplier = multiplier
    return exchange_rate


def test_update_daily_order_data_marks_history_failed_when_no_rollup_rows(
    monkeypatch,
):  # pylint: disable=unused-argument
    """
    Test that update_daily_order_data flags history as failed when no rollup rows exist.
    """
    history = FakeHistory()

    result = DailyOrderService().update_daily_order_data([], 0, 1, history)

    assert result is history
    assert history.order_data_rows_total == 0
    assert history.order_data_update_succeeded is False
    assert not history.calls


def test_update_daily_order_data_inserts_new_purchase_rollup_and_updates_history(
    monkeypatch,
):
    """
    Test that update_daily_order_data inserts new purchase rollups and records history counts.
    """
    order = create_order()
    history = FakeHistory()
    insert_calls = []
    select_calls = []
    time_values = iter([100.0, 101.5, 105.0])
    monkeypatch.setattr(
        "common.daily_order_service.time.time", lambda: next(time_values)
    )
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: create_exchange_rate(
            1.5, "EUR"
        ),
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_query_one",
        lambda sql, data: select_calls.append((sql, data)) or {},
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 88,
    )

    result = DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
        history,
    )

    assert result is history
    assert history.order_data_rows_total == 1
    assert history.calls
    assert history.calls[0][0] is True
    assert history.calls[0][2:] == (1, 0)
    assert select_calls[0][1]["ticketSocketEventId"] == 10
    assert select_calls[0][1]["purchaseDate"] == "2026-05-01"
    assert insert_calls[0][1]["orders"] == 1
    assert insert_calls[0][1]["tickets"] == 2
    assert insert_calls[0][1]["ticketRevenue"] == 100.0
    assert insert_calls[0][1]["serviceFeeRevenue"] == 20.0
    assert insert_calls[0][1]["totalRevenue"] == 120.0
    assert insert_calls[0][1]["exchangeRate"] == 1.5
    assert insert_calls[0][1]["currencySymbol"] == "EUR"
    assert insert_calls[0][1]["ticketSocketOrderId"] is None


def test_update_daily_order_data_updates_existing_rollup(monkeypatch):
    """
    Test that update_daily_order_data updates an existing daily order row when found.
    """
    order = create_order()
    history = FakeHistory()
    update_calls = []
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 200.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_query_one",
        lambda sql, data: {"DailyOrderDataId": 41},
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    result = DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
        history,
    )

    assert result is history
    assert update_calls[0][1]["dailyOrderDataId"] == 41
    assert update_calls[0][1]["exchangeRate"] == 1
    assert update_calls[0][1]["currencySymbol"] == "$"
    assert history.calls[0][2:] == (0, 1)


def test_update_daily_order_data_returns_none_without_history(monkeypatch):
    """
    Test that update_daily_order_data returns None when no history object is provided.
    """
    order = create_order()
    insert_calls = []
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 250.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_query_one",
        lambda sql, data: {},
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 88,
    )

    result = DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
    )

    assert result is None
    assert len(insert_calls) == 1


def test_update_daily_order_data_stops_when_existing_update_fails(monkeypatch):
    """
    Test that update_daily_order_data stops processing and records failure when an existing row update fails.
    """
    history = FakeHistory()
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 275.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_query_one",
        lambda sql, data: {"DailyOrderDataId": 41},
    )
    monkeypatch.setattr(
        "common.daily_order_service.db_update",
        lambda sql, data: False,
    )

    result = DailyOrderService().update_daily_order_data(
        [create_order()],
        0,
        9999999999,
        history,
    )

    assert result is history
    assert history.calls[0][0] is False
    assert history.calls[0][2:] == (0, 0)


def test_update_daily_order_data_stops_when_insert_fails(monkeypatch):
    """
    Test that update_daily_order_data stops processing and records failure when an insert fails.
    """
    orders = [
        create_order(ticket_socket_event_id=10, ticket_socket_order_id=100),
        create_order(ticket_socket_event_id=11, ticket_socket_order_id=101),
    ]
    history = FakeHistory()
    insert_calls = []
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 300.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data))
        or (0 if len(insert_calls) == 2 else 7),
    )

    result = DailyOrderService().update_daily_order_data(
        orders,
        0,
        9999999999,
        history,
    )

    assert result is history
    assert len(insert_calls) == 2
    assert history.calls[0][0] is False
    assert history.calls[0][2:] == (1, 0)


def test_update_daily_order_data_skips_deleted_and_comped_orders(monkeypatch):
    """
    Test that update_daily_order_data ignores deleted and comped orders in the rollup.
    """
    orders = [
        create_order(ticket_socket_order_id=100, is_deleted=True),
        create_order(ticket_socket_order_id=101, is_comped=True),
    ]
    history = FakeHistory()
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 400.0)
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: (_ for _ in ()).throw(
            AssertionError("db_insert should not run")
        ),
    )

    result = DailyOrderService().update_daily_order_data(
        orders,
        0,
        9999999999,
        history,
    )

    assert result is history
    assert history.order_data_rows_total == 0
    assert history.order_data_update_succeeded is False
    assert not history.calls


def test_update_daily_order_data_creates_purchase_and_refund_rows(monkeypatch):
    """
    Test that update_daily_order_data creates separate purchase and refund rows when needed.
    """
    order = create_order(
        has_refunds=True,
        num_tickets=2,
        revenue=100.0,
        service_fees=20.0,
        num_tickets_refunded=1,
        revenue_refunded=50.0,
        service_fee_revenue_refunded=10.0,
        tickets=[
            create_ticket(is_refunded=True, refund_date="2026-05-03"),
            create_ticket(is_refunded=False),
        ],
    )
    insert_calls = []
    history = FakeHistory()

    def fake_exchange_rate(
        self, ticket_socket_order_id, midnight_date
    ):  # pylint: disable=unused-argument
        if midnight_date == "2026-05-03":
            return create_exchange_rate(0.5, "CAD")
        return create_exchange_rate(1.2, "EUR")

    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 500.0)
    monkeypatch.setattr(
        DailyOrderService, "get_exchange_rate_for_order_by_date", fake_exchange_rate
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 9,
    )

    DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
        history,
    )

    assert len(insert_calls) == 2
    refund_row = next(call[1] for call in insert_calls if call[1]["isRefunded"] == 1)
    purchase_row = next(call[1] for call in insert_calls if call[1]["isRefunded"] == 0)
    assert refund_row["purchaseDate"] == "2026-05-03"
    assert refund_row["ticketSocketOrderId"] == 100
    assert refund_row["numTicketsRefunded"] == 1
    assert refund_row["revenueRefunded"] == 50.0
    assert refund_row["serviceFeeRevenueRefunded"] == 10.0
    assert purchase_row["purchaseDate"] == "2026-05-01"
    assert purchase_row["ticketSocketOrderId"] is None
    assert purchase_row["ticketRevenue"] == 100.0


def test_update_daily_order_data_creates_purchase_and_chargeback_rows(monkeypatch):
    """
    Test that update_daily_order_data creates separate purchase and chargeback rows when needed.
    """
    order = create_order(
        has_chargebacks=True,
        num_tickets=2,
        revenue=100.0,
        service_fees=20.0,
        num_tickets_charged_back=1,
        revenue_charged_back=50.0,
        service_fee_revenue_charged_back=10.0,
        tickets=[
            create_ticket(is_charged_back=True, chargeback_date="2026-05-04"),
            create_ticket(is_charged_back=False),
        ],
    )
    insert_calls = []
    history = FakeHistory()

    def fake_exchange_rate(
        self, ticket_socket_order_id, midnight_date
    ):  # pylint: disable=unused-argument
        if midnight_date == "2026-05-04":
            return create_exchange_rate(0.7, "GBP")
        return create_exchange_rate(1.1, "EUR")

    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 600.0)
    monkeypatch.setattr(
        DailyOrderService, "get_exchange_rate_for_order_by_date", fake_exchange_rate
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 10,
    )

    DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
        history,
    )

    assert len(insert_calls) == 2
    chargeback_row = next(
        call[1] for call in insert_calls if call[1]["isChargeback"] == 1
    )
    purchase_row = next(
        call[1] for call in insert_calls if call[1]["isChargeback"] == 0
    )
    assert chargeback_row["purchaseDate"] == "2026-05-04"
    assert chargeback_row["ticketSocketOrderId"] == 100
    assert chargeback_row["numTicketsChargedBack"] == 1
    assert chargeback_row["revenueChargedBack"] == 50.0
    assert chargeback_row["serviceFeeRevenueChargedBack"] == 10.0
    assert purchase_row["purchaseDate"] == "2026-05-01"
    assert purchase_row["ticketRevenue"] == 100.0


def test_update_daily_order_data_merges_refund_rows_for_same_order_id(monkeypatch):
    """
    Test that update_daily_order_data merges refund totals into an existing refund row for the same order id.
    """
    orders = [
        create_order(
            ticket_socket_order_id=100,
            has_refunds=True,
            num_tickets=2,
            revenue=100.0,
            service_fees=20.0,
            num_tickets_refunded=1,
            revenue_refunded=25.0,
            service_fee_revenue_refunded=5.0,
            tickets=[
                create_ticket(is_refunded=True, refund_date=None),
                create_ticket(is_refunded=True, refund_date="2026-05-03"),
                create_ticket(is_refunded=False),
                create_ticket(is_refunded=False),
            ],
        ),
        create_order(
            ticket_socket_order_id=100,
            has_refunds=True,
            num_tickets=1,
            revenue=50.0,
            service_fees=10.0,
            num_tickets_refunded=2,
            revenue_refunded=30.0,
            service_fee_revenue_refunded=6.0,
            tickets=[
                create_ticket(is_refunded=True, refund_date="2026-05-03"),
                create_ticket(is_refunded=False),
            ],
        ),
    ]
    insert_calls = []
    history = FakeHistory()

    def fake_exchange_rate(
        self, ticket_socket_order_id, midnight_date
    ):  # pylint: disable=unused-argument
        if midnight_date == "2026-05-03":
            return create_exchange_rate(0.5, "CAD")
        return create_exchange_rate(1.2, "EUR")

    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 650.0)
    monkeypatch.setattr(
        DailyOrderService, "get_exchange_rate_for_order_by_date", fake_exchange_rate
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 13,
    )

    DailyOrderService().update_daily_order_data(
        orders,
        0,
        9999999999,
        history,
    )

    assert len(insert_calls) == 2
    refund_row = next(call[1] for call in insert_calls if call[1]["isRefunded"] == 1)
    purchase_row = next(call[1] for call in insert_calls if call[1]["isRefunded"] == 0)
    assert refund_row["numTicketsRefunded"] == 3
    assert refund_row["revenueRefunded"] == 55.0
    assert refund_row["serviceFeeRevenueRefunded"] == 11.0
    assert purchase_row["orders"] == 2
    assert purchase_row["tickets"] == 3


def test_update_daily_order_data_merges_chargeback_rows_for_same_order_id(
    monkeypatch,
):
    """
    Test that update_daily_order_data merges chargeback totals into an existing chargeback row for the same order id.
    """
    orders = [
        create_order(
            ticket_socket_order_id=100,
            has_chargebacks=True,
            num_tickets=2,
            revenue=100.0,
            service_fees=20.0,
            num_tickets_charged_back=1,
            revenue_charged_back=25.0,
            service_fee_revenue_charged_back=5.0,
            tickets=[
                create_ticket(is_charged_back=True, chargeback_date=None),
                create_ticket(is_charged_back=True, chargeback_date="2026-05-04"),
                create_ticket(is_charged_back=False),
                create_ticket(is_charged_back=False),
            ],
        ),
        create_order(
            ticket_socket_order_id=100,
            has_chargebacks=True,
            num_tickets=1,
            revenue=50.0,
            service_fees=10.0,
            num_tickets_charged_back=2,
            revenue_charged_back=30.0,
            service_fee_revenue_charged_back=6.0,
            tickets=[
                create_ticket(is_charged_back=True, chargeback_date="2026-05-04"),
                create_ticket(is_charged_back=False),
            ],
        ),
    ]
    insert_calls = []
    history = FakeHistory()

    def fake_exchange_rate(
        self, ticket_socket_order_id, midnight_date
    ):  # pylint: disable=unused-argument
        if midnight_date == "2026-05-04":
            return create_exchange_rate(0.7, "GBP")
        return create_exchange_rate(1.1, "EUR")

    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 675.0)
    monkeypatch.setattr(
        DailyOrderService, "get_exchange_rate_for_order_by_date", fake_exchange_rate
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 14,
    )

    DailyOrderService().update_daily_order_data(
        orders,
        0,
        9999999999,
        history,
    )

    assert len(insert_calls) == 2
    chargeback_row = next(
        call[1] for call in insert_calls if call[1]["isChargeback"] == 1
    )
    purchase_row = next(
        call[1] for call in insert_calls if call[1]["isChargeback"] == 0
    )
    assert chargeback_row["numTicketsChargedBack"] == 3
    assert chargeback_row["revenueChargedBack"] == 55.0
    assert chargeback_row["serviceFeeRevenueChargedBack"] == 11.0
    assert purchase_row["orders"] == 2
    assert purchase_row["tickets"] == 3


def test_update_daily_order_data_creates_refund_row_without_refund_dates(
    monkeypatch,
):
    """
    Test that update_daily_order_data still creates a refund row when refunded tickets do not have a refund date.
    """
    order = create_order(
        has_refunds=True,
        num_tickets_refunded=1,
        revenue_refunded=25.0,
        service_fee_revenue_refunded=5.0,
        tickets=[create_ticket(is_refunded=True, refund_date=None)],
    )
    insert_calls = []
    history = FakeHistory()
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 690.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 15,
    )

    DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
        history,
    )

    refund_row = next(call[1] for call in insert_calls if call[1]["isRefunded"] == 1)
    assert refund_row["purchaseDate"] is None
    assert refund_row["exchangeRate"] == 1
    assert refund_row["currencySymbol"] == "$"


def test_update_daily_order_data_creates_chargeback_row_without_chargeback_dates(
    monkeypatch,
):
    """
    Test that update_daily_order_data still creates a chargeback row when charged-back tickets do not have a chargeback date.
    """
    order = create_order(
        has_chargebacks=True,
        num_tickets_charged_back=1,
        revenue_charged_back=25.0,
        service_fee_revenue_charged_back=5.0,
        tickets=[create_ticket(is_charged_back=True, chargeback_date=None)],
    )
    insert_calls = []
    history = FakeHistory()
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 695.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 16,
    )

    DailyOrderService().update_daily_order_data(
        [order],
        0,
        9999999999,
        history,
    )

    chargeback_row = next(
        call[1] for call in insert_calls if call[1]["isChargeback"] == 1
    )
    assert chargeback_row["purchaseDate"] is None
    assert chargeback_row["exchangeRate"] == 1
    assert chargeback_row["currencySymbol"] == "$"


def test_update_daily_order_data_scans_past_non_matching_existing_rows(
    monkeypatch,
):
    """
    Test that update_daily_order_data continues scanning existing rows when earlier rows for the same event do not match the current order or purchase date.
    """
    orders = [
        create_order(
            ticket_socket_order_id=100,
            purchase_date="2026-05-01",
            has_refunds=True,
            num_tickets_refunded=1,
            revenue_refunded=25.0,
            service_fee_revenue_refunded=5.0,
            tickets=[create_ticket(is_refunded=True, refund_date="2026-05-03")],
        ),
        create_order(
            ticket_socket_order_id=101,
            purchase_date="2026-05-02",
            has_refunds=True,
            num_tickets_refunded=1,
            revenue_refunded=30.0,
            service_fee_revenue_refunded=6.0,
            tickets=[create_ticket(is_refunded=True, refund_date="2026-05-04")],
        ),
    ]
    insert_calls = []
    history = FakeHistory()
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 697.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 17,
    )

    DailyOrderService().update_daily_order_data(
        orders,
        0,
        9999999999,
        history,
    )

    assert len(insert_calls) == 4


def test_update_daily_order_data_merges_multiple_orders_on_same_date(monkeypatch):
    """
    Test that update_daily_order_data merges purchase totals for the same event and date.
    """
    orders = [
        create_order(
            ticket_socket_order_id=100, num_tickets=1, revenue=25.0, service_fees=5.0
        ),
        create_order(
            ticket_socket_order_id=101, num_tickets=2, revenue=50.0, service_fees=10.0
        ),
    ]
    insert_calls = []
    history = FakeHistory()
    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 700.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 11,
    )

    DailyOrderService().update_daily_order_data(
        orders,
        0,
        9999999999,
        history,
    )

    assert len(insert_calls) == 1
    assert insert_calls[0][1]["orders"] == 2
    assert insert_calls[0][1]["tickets"] == 3
    assert insert_calls[0][1]["ticketRevenue"] == 75.0
    assert insert_calls[0][1]["serviceFeeRevenue"] == 15.0
    assert insert_calls[0][1]["totalRevenue"] == 90.0


def test_update_daily_order_data_skips_purchase_row_outside_range_but_keeps_refund(
    monkeypatch,
):
    """
    Test that update_daily_order_data skips out-of-range purchases while still recording refunds.
    """
    order = create_order(
        purchase_date="2026-05-01",
        has_refunds=True,
        num_tickets_refunded=1,
        revenue_refunded=25.0,
        service_fee_revenue_refunded=5.0,
        tickets=[create_ticket(is_refunded=True, refund_date="2026-05-03")],
    )
    insert_calls = []
    history = FakeHistory()
    start = int(datetime(2026, 5, 2).timestamp())
    end = int(datetime(2026, 5, 4).timestamp())

    monkeypatch.setattr("common.daily_order_service.time.time", lambda: 800.0)
    monkeypatch.setattr(
        DailyOrderService,
        "get_exchange_rate_for_order_by_date",
        lambda self, ticket_socket_order_id, midnight_date: None,
    )
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        "common.daily_order_service.db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 12,
    )

    DailyOrderService().update_daily_order_data([order], start, end, history)

    assert len(insert_calls) == 1
    assert insert_calls[0][1]["isRefunded"] == 1
    assert insert_calls[0][1]["purchaseDate"] == "2026-05-03"


def test_cleanup_daily_order_data_for_event_deletes_by_event_id(monkeypatch):
    """
    Test that cleanup_daily_order_data_for_event deletes rows for the given event id.
    """
    calls = []
    monkeypatch.setattr(
        "common.daily_order_service.db_delete",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    DailyOrderService().cleanup_daily_order_data_for_event(55)

    assert calls[0][1] == {"ticketSocketEventId": 55}


def test_get_exchange_rate_for_order_by_date_returns_rate_with_multiplier(monkeypatch):
    """
    Test that get_exchange_rate_for_order_by_date applies the exchange rate multiplier.
    """
    calls = []
    monkeypatch.setattr(
        "common.daily_order_service.db_query_one",
        lambda sql, data: calls.append((sql, data))
        or {
            "ExchangeRate": 1.5,
            "ExchangeRateSlug": "cad",
            "CurrencySymbol": "C$",
            "Multiplier": 2.0,
            "ExchangeRateId": 7,
        },
    )

    exchange_rate = DailyOrderService().get_exchange_rate_for_order_by_date(
        100,
        "2026-05-01",
    )

    assert exchange_rate.exchange_rate_id == 7
    assert exchange_rate.exchange_rate_slug == "cad"
    assert exchange_rate.currency_symbol == "C$"
    assert exchange_rate.usd_rate == 3.0
    assert calls[0][1] == {
        "ticket_socket_order_id": 100,
        "midnight_date": "2026-05-01",
    }


def test_get_exchange_rate_for_order_by_date_returns_default_rate_when_multiplier_is_zero(
    monkeypatch,
):
    """
    Test that get_exchange_rate_for_order_by_date leaves the
    default USD rate when multiplier is zero.
    """
    monkeypatch.setattr(
        "common.daily_order_service.db_query_one",
        lambda sql, data: {
            "ExchangeRate": 1.5,
            "ExchangeRateSlug": "cad",
            "CurrencySymbol": "C$",
            "Multiplier": 0,
            "ExchangeRateId": 7,
        },
    )

    exchange_rate = DailyOrderService().get_exchange_rate_for_order_by_date(
        100,
        "2026-05-01",
    )

    assert exchange_rate.usd_rate == 1.0


def test_get_exchange_rate_for_order_by_date_returns_none_when_row_is_missing(
    monkeypatch,
):
    """
    Test that get_exchange_rate_for_order_by_date returns None when no row is found.
    """
    monkeypatch.setattr("common.daily_order_service.db_query_one", lambda sql, data: {})

    exchange_rate = DailyOrderService().get_exchange_rate_for_order_by_date(
        100,
        "2026-05-01",
    )

    assert exchange_rate is None
