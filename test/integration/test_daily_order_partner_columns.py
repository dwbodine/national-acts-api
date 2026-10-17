"""Runtime rollups and refresh cleanup work without legacy DailyOrderData columns."""

import os
from datetime import datetime
from pathlib import Path
import shutil

import mariadb
import pytest
from test_migrations import database  # pylint: disable=unused-import

from common import db, data_refresh_service
from common.daily_order_service import DailyOrderService
from common.data_refresh_service import DataRefreshService
from common.models.national_acts import VipEvent, VipOrder, VipTicket
from common.models.ticket_socket import TicketSocketVenue, Country

pytestmark = pytest.mark.integration


def test_refresh_cleanup_and_rollups_use_only_partner_columns(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade", "7e3584499b4c")

    def connect(timeout=3000):
        return mariadb.connect(
            host="127.0.0.1",
            port=int(os.environ["TEST_MARIADB_PORT"]),
            user="root",
            password=os.environ["TEST_MARIADB_PASSWORD"],
            database=os.environ["MIGRATION_DB_DB"],
            autocommit=True,
        )

    monkeypatch.setattr(db, "db_get_connection", connect)
    monkeypatch.setattr(data_refresh_service, "db_get_connection", connect)
    # No email is sent by this test, including on an unexpected refresh failure.
    monkeypatch.setattr(
        data_refresh_service.MessagingService, "send_email", lambda *args: True
    )
    statements = [
        "INSERT INTO Sellers (SellerId, Name) VALUES (1, 'Seller')",
        "INSERT INTO ExchangeRates (ExchangeRateId, Name, Symbol, ServiceTokenId) VALUES (1, 'Dollar', '$', 'usd')",
        "INSERT INTO TicketSocket (TicketSocketId, AccountName, ServiceUrl, ExchangeRateId) VALUES (1, 'Account', 'https://example.com', 1)",
        "INSERT INTO SellerEventCategory (SellerEventCategoryId, SellerId, TicketSocketId, EventCategoryId) VALUES (1, 1, 1, 1)",
        "INSERT INTO Events (EventId, SellerId, Title, EventDate) VALUES (10, 1, 'Imported', '2026-11-01'), (20, 1, 'Other', '2026-11-02')",
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL) VALUES (100, 900, 1, 'Old title', '2026-11-01', ''), (200, 901, 1, 'Other', '2026-11-02', '')",
        "INSERT INTO TicketPartnerEvents (TicketPartnerEventId, TicketPartnerId, EventId, PartnerEventId) VALUES (1000, 2, 10, 100), (2000, 2, 20, 200)",
        "INSERT INTO TicketSocketOrders (Id, TicketSocketEventId, EventId, OrderId, PurchaseDate, PurchaseTimestamp, UserId) VALUES (110, 100, 900, 990, '2026-10-14', '2026-10-14 12:00:00', 1)",
        "INSERT INTO TicketPartnerOrders (TicketPartnerOrderId, TicketPartnerEventId, PartnerOrderId) VALUES (1100, 1000, 110)",
        "INSERT INTO DailyOrderData (PurchaseDate, TicketPartnerEventId, TicketPartnerOrderId) VALUES ('2026-10-14', 1000, NULL), ('2026-10-14', 1000, 1100), ('2026-10-13', 1000, NULL), ('2026-10-14', 2000, NULL)",
    ]
    with engine.begin() as connection:
        for sql in statements:
            connection.exec_driver_sql(sql)

    order = VipOrder()
    order.original_order_id, order.original_event_id, order.user_id = 990, 900, 1
    order.purchase_date = "2026-10-15"
    order.purchase_timestamp = "2026-10-15 12:00:00"
    order.purchase_unix_timestamp = 0
    order.tickets = []
    event = VipEvent()
    event.original_event_id, event.seller_id, event.seller_event_category_id = 900, 1, 1
    event.title, event.event_date, event.ticket_socket_url = (
        "Imported",
        "2026-11-01",
        "https://example.com/event",
    )
    event.venue = TicketSocketVenue(
        "Venue",
        "Address",
        "City",
        "NY",
        "10001",
        Country(1, "USA", "US"),
        "America/New_York",
    )
    event.orders, event.ticket_types = [order], []
    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, **kwargs: [event],
    )
    result = DataRefreshService().refresh_database_from_ticket_socket(start=0)
    assert result is not None and result.succeeded
    assert result.order_data_rows_removed == 2
    with engine.connect() as connection:
        remaining = connection.exec_driver_sql(
            "SELECT TicketPartnerEventId, PurchaseDate FROM DailyOrderData ORDER BY TicketPartnerEventId"
        ).all()
        assert [(row[0], str(row[1])) for row in remaining] == [
            (1000, "2026-10-13"),
            (2000, "2026-10-14"),
        ]

    order.ticket_partner_event_id, order.ticket_partner_order_id = 1000, 1100
    order.num_tickets, order.revenue, order.service_fees = 2, 50, 5
    order.currency_symbol = "$"
    service = DailyOrderService()
    start, end = (
        int(datetime(2026, month, day).timestamp()) for month, day in [(1, 1), (12, 31)]
    )
    service.update_daily_order_data([order], start, end)
    order.revenue = 60
    service.update_daily_order_data([order], start, end)
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT TicketPartnerEventId, TicketPartnerOrderId, TicketRevenue FROM DailyOrderData WHERE PurchaseDate='2026-10-15'"
        ).one()
        assert tuple(row) == (1000, None, 60)
    refunded_ticket = VipTicket()
    refunded_ticket.is_refunded, refunded_ticket.refund_date = True, "2026-10-16"
    order.tickets, order.has_refunds = [refunded_ticket], True
    order.num_tickets_refunded, order.revenue_refunded = 1, 30
    service.update_daily_order_data([order], start, end)
    with engine.connect() as connection:
        refund = connection.exec_driver_sql(
            "SELECT TicketPartnerEventId, TicketPartnerOrderId, RevenueRefunded FROM DailyOrderData WHERE PurchaseDate='2026-10-16'"
        ).one()
        assert tuple(refund) == (1000, 1100, 30)
    service.cleanup_daily_order_data_for_event(1000)
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT TicketPartnerEventId FROM DailyOrderData"
            ).scalar_one()
            == 2000
        )
