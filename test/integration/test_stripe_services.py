"""Exercise service SQL against the migrated schema with deliberately distinct IDs."""

import os
from pathlib import Path
import shutil
from datetime import datetime

import mariadb
import pytest
from test_migrations import database  # pylint: disable=unused-import

from common import db
from common.admin_service import AdminService
from common.calendar_service import CalendarService
from common.daily_order_service import DailyOrderService
from common.dashboard_service import DashboardService
from common.event_service import EventService
from common.models.national_acts import VipEvent
from common.order_service import OrderService
from common.ticket_partner_service import TicketPartnerService
from common.moments_service import MomentsService
from common.report_service import ReportService
from common.sender_api_service import SenderApiService
from common.update_service import UpdateService

pytestmark = pytest.mark.integration


def test_services_use_partner_ids_and_preserve_provider_identity(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(Path(__file__).resolve().parents[2] / "migrations/versions",
                    root / "migrations/versions", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    run("upgrade", "7e3584499b4c")

    def connect(timeout=3000):
        return mariadb.connect(host="127.0.0.1", port=int(os.environ["TEST_MARIADB_PORT"]),
                               user="root", password=os.environ["TEST_MARIADB_PASSWORD"],
                               database=os.environ["MIGRATION_DB_DB"], autocommit=True)
    monkeypatch.setattr(db, "db_get_connection", connect)
    statements = [
        "INSERT INTO Settings (Name, DisplayName, Type, Value) VALUES ('YearlyRevenueGoal', 'Year goal', 'number', '1000'), ('MonthlyRevenueGoal', 'Month goal', 'number', '100')",
        "INSERT INTO Sellers (SellerId, Name) VALUES (1, 'Example seller')",
        "INSERT INTO ExchangeRates (ExchangeRateId, Name, Symbol, ServiceTokenId) VALUES (1, 'Dollar', '$', 'usd')",
        "INSERT INTO TicketSocket (TicketSocketId, AccountName, ServiceUrl, ExchangeRateId) VALUES (1, 'Account', 'https://example.com', 1)",
        "INSERT INTO SellerEventCategory (SellerEventCategoryId, SellerId, TicketSocketId, EventCategoryId) VALUES (1, 1, 1, 1)",
        "INSERT INTO Events (EventId, SellerId, Title, EventDate) VALUES (10, 1, 'Service event', '2026-11-01'), (20, 1, 'Local event', '2026-11-02')",
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL) VALUES (100, 900, 1, 'Provider event', '2026-11-01', 'https://example.com')",
        "INSERT INTO TicketPartnerEvents (TicketPartnerEventId, TicketPartnerId, EventId, PartnerEventId) VALUES (1000, 2, 10, 100), (2000, 1, 20, NULL)",
        "INSERT INTO TicketSocketOrders (Id, TicketSocketEventId, EventId, OrderId, PurchaseDate, PurchaseTimestamp, UserId) VALUES (110, 100, 900, 990, '2026-10-14', '2026-10-14 12:00:00', 1)",
        "INSERT INTO TicketPartnerOrders (TicketPartnerOrderId, TicketPartnerEventId, PartnerOrderId) VALUES (1100, 1000, 110), (2100, 2000, 110)",
        "INSERT INTO TicketSocketOrderTickets (Id, TicketSocketOrderId, TicketId, TicketType, Price, ServiceFee) VALUES (120, 110, 980, 'VIP', 50, 5)",
        "INSERT INTO TicketPartnerOrderTickets (TicketPartnerTicketId, TicketPartnerOrderId, PartnerTicketId) VALUES (1200, 1100, 120), (2200, 2100, 120)",
    ]
    with engine.begin() as connection:
        for sql in statements:
            connection.exec_driver_sql(sql)

    events = EventService().get_events_and_orders(event_id=10, get_orders=True)
    assert len(events) == 1
    event = events[0]
    assert (event.event_id, event.ticket_partner_event_id, event.original_event_id) == (10, 1000, 900)
    order = event.orders[0]
    assert (order.ticket_partner_order_id, order.original_order_id, order.original_event_id) == (1100, 990, 900)
    ticket = order.tickets[0]
    assert (ticket.ticket_partner_order_ticket_id, ticket.ticket_partner_order_id, ticket.original_ticket_id) == (1200, 1100, 980)
    assert EventService().get_events_and_orders(event_id=20)[0].is_external
    assert EventService().get_events_and_orders(search_term="Service", ignore_flags=True)[0].event_id == 10
    assert OrderService().get_orders(ts_order_id=1100)[0].original_order_id == 990
    assert OrderService().get_orders(ts_order_id=110) == []

    # Read projections must not multiply orders, subscribers, or daily totals
    # when the views expose multiple payments or tour associations.
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO Tour (TourId, TourName) VALUES (1, 'First'), (2, 'Second')")
        connection.exec_driver_sql("INSERT INTO TourEvent (TourId, EventId) VALUES (1, 10), (2, 10)")
        connection.exec_driver_sql("UPDATE TicketSocketOrders SET Email='buyer@example.com', Phone='2125550199' WHERE Id=110")
        for transaction_id in ('pi_first', 'pi_second'):
            connection.exec_driver_sql("""INSERT INTO StripeTransactions
                (StripeTransactionId, TicketPartnerOrderId, EventName, Description,
                 DateReceived, Total, Insurance, ProcessingFee, CustomerName,
                 CustomerEmail, CustomerPhone, Currency, SourceUrl, ExchangeRate)
                VALUES (%s, 1100, 'Service event', 'Payment', '2026-10-14 12:00:00',
                        55, 0, 2, 'Buyer', 'buyer@example.com', '', 'USD', '', 1)""", (transaction_id,))
        connection.exec_driver_sql("INSERT INTO FanMoments (FanMomentId, EventId) VALUES (1, 10), (2, 20)")
        connection.exec_driver_sql("INSERT INTO FanMomentImages (FanMomentId, ImageName) VALUES (1, 'example.jpg'), (2, 'local.jpg')")
    assert len(OrderService().get_orders(ts_order_id=1100)) == 1
    with engine.connect() as connection:
        overview = connection.exec_driver_sql(
            "SELECT * FROM OrderOverview WHERE TicketPartnerOrderId=1100"
        ).mappings().one()
        assert overview["EventTitle"] == "Service event"
        assert overview["SellerId"] == 1
        assert overview["CurrencyAbbrev"] == "USD"
        assert overview["ExchangeRate"] == 1
    assert len(OrderService().get_orders_from_event_id(1000)) == 1
    assert len(OrderService().get_tickets_from_order_id(1100)) == 1
    assert len(AdminService().get_ticket_socket_events_only(1)) == 1
    assert len(ReportService().get_missing_venue_events()) == 1
    assert len(MomentsService()._list_matching_fan_moment_rows(seller_id=1)) == 2
    assert len(SenderApiService().get_sender_subscribers_from_db(limit=1)) == 1
    assert UpdateService().format_all_phone_numbers()

    service = OrderService()
    assert service.check_in_tickets([2200], True) is False
    assert service.refund_order(2100) is False
    assert service.refund_ticket(2200) is False
    assert service.check_in_tickets([1200], True)
    # Suppress rebuild only while exercising mutation ID resolution.
    monkeypatch.setattr(service, "rebuild_daily_order_data_for_order", lambda value: None)
    monkeypatch.setattr(service, "rebuild_daily_order_data_for_ticket", lambda value: None)
    assert service.refund_order(1100)
    assert service.refund_ticket(1200, refund_service_fees=True)
    order.notes = "Changed locally"
    ticket.is_checked_in = True
    ticket.attendee_first_name = "Updated attendee"
    ticket.ticket_partner_order_ticket_id = 2200
    assert service.update_order(order) is False
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT Notes FROM TicketSocketOrders WHERE Id=110").scalar_one() is None
    ticket.ticket_partner_order_ticket_id = 1200
    assert service.update_order(order)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT Notes FROM TicketSocketOrders WHERE Id=110").scalar_one() == "Changed locally"
        assert connection.exec_driver_sql("SELECT IsCheckedIn FROM TicketSocketOrderTickets WHERE Id=120").scalar_one() == 1

    partners = TicketPartnerService()
    assert partners.ensure_event(10, 2, 100) == 1000
    assert partners.ensure_order(100, 110) == 1100
    assert partners.ensure_ticket(1100, 120) == 1200
    assert partners.socket_ticket(1200, 2100) is None
    assert service.add_comped_order(10, 2)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM TicketPartnerOrderTickets").scalar_one() == 4

    start = int(datetime(2026, 1, 1).timestamp())
    end = int(datetime(2026, 12, 31, 23, 59, 59).timestamp())
    orders = service.get_orders(start=start, end=end, seller_id=1)
    DailyOrderService().update_daily_order_data(orders, start, end)
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("SELECT TicketPartnerEventId, TicketPartnerOrderId FROM DailyOrderData").all()
        assert rows and all(row[0] == 1000 and row[1] in (None, 1100) for row in rows)
    assert DashboardService().get_dashboard_data(2026).tickets == 1
    DashboardService().rebuild_daily_order_data_for_event(1000)
    assert UpdateService().rebuild_daily_order_data_for_year(2026, 11)

    CalendarService().add_note("Local note", event_id=20)
    assert CalendarService().get_event_notes(20)[0].event_id == 20
    local = VipEvent()
    local.event_id = 0
    local.seller_id = 1
    local.title = "New local event"
    local.event_date = "2026-12-01"
    local.ticket_types = []
    assert AdminService().update_event(local)
    assert EventService().get_events_and_orders(search_term="New local", ignore_flags=True)[0].ticket_partner_id == 1
