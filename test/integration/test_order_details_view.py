"""Order projection preserves optional sources and prevents cross-partner joins."""

from pathlib import Path
import shutil

import pytest
from sqlalchemy import text
from test_migrations import database  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


def test_order_details_sources_and_stripe_rollback(database):
    run, engine, root = database
    source = Path(__file__).resolve().parents[2] / "migrations/versions"
    shutil.copytree(
        source,
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade", "7e3584499b4c")
    statements = [
        "INSERT INTO Sellers (SellerId, Name) VALUES (1, 'Example seller')",
        "INSERT INTO ExchangeRates (ExchangeRateId, Name, Symbol, ServiceTokenId) VALUES (1, 'Dollar', 'USD', 'test')",
        "INSERT INTO TicketSocket (TicketSocketId, AccountName, ServiceUrl, ExchangeRateId) VALUES (1, 'Example account', 'https://example.com', 1)",
        "INSERT INTO SellerEventCategory (SellerEventCategoryId, SellerId, TicketSocketId, EventCategoryId) VALUES (1, 1, 1, 1)",
        "INSERT INTO Events (EventId, SellerId, Title, EventDate) VALUES (1, 1, 'Event one', '2026-11-01'), (2, 1, 'Event two', '2026-11-02')",
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL) VALUES (10, 900, 1, 'TS one', '2026-11-01', 'https://example.com/10'), (20, 901, 1, 'TS two', '2026-11-02', 'https://example.com/20')",
        "INSERT INTO TicketSocketOrders (Id, TicketSocketEventId, EventId, OrderId, PurchaseDate, PurchaseTimestamp, UserId, Phone, PurchaserFirstName, PurchaserLastName, Email, IsManualTransfer) VALUES (11, 10, 900, 1100, '2026-10-14', '2026-10-14 12:00:00', 1, '5550100', 'Ticket', 'Buyer', 'ticket@example.com', 1), (12, 10, 900, 1200, '2026-10-14', '2026-10-14 12:00:00', 2, '', 'Other', 'Buyer', 'other@example.com', 0)",
        "INSERT INTO TicketPartnerEvents (TicketPartnerEventId, TicketPartnerId, EventId, PartnerEventId) VALUES (100, 2, 1, 10), (101, 1, 1, NULL), (102, 2, 2, 20)",
        "INSERT INTO TicketPartnerOrders (TicketPartnerOrderId, TicketPartnerEventId, PartnerOrderId) VALUES (1, 100, 11), (2, 100, 12), (3, 101, 11), (4, 101, NULL), (5, 102, 11)",
        "INSERT INTO TicketSocketTicketTypes (TicketSocketTicketTypeId, TicketSocketEventId, TicketTypeName, TotalAvailable, TicketTypeOrder) VALUES (7, 10, 'VIP', 100, 3), (7, 20, 'Other event VIP', 50, 8)",
        "INSERT INTO PartnerTicketTypes (TicketPartnerEventId, ProviderTicketTypeId) VALUES (100, 7), (102, 7)",
        "INSERT INTO TicketSocketOrderTickets (Id, TicketSocketOrderId, TicketSocketTicketTypeId, TicketId, TicketType, Price, IsCheckedIn, IsRefunded) VALUES (21, 11, 7, 2100, 'VIP', 50, 1, 0), (22, 12, 7, 2200, 'VIP', 60, 0, 0), (23, 11, 0, 2300, 'Comp', 0, 0, 1)",
        "INSERT INTO TicketPartnerOrderTickets (TicketPartnerTicketId, TicketPartnerOrderId, PartnerTicketId) VALUES (101, 1, 21), (102, 2, NULL), (103, 3, 21), (104, 2, 21), (105, 5, 21), (106, 1, 23)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        for transaction_id, order_id in [
            ("tx_one", 1),
            ("tx_two", 1),
            ("tx_manual", 3),
            ("tx_unlinked", None),
        ]:
            connection.execute(
                text("""
                INSERT INTO StripeTransactions
                    (StripeTransactionId, TicketPartnerOrderId, EventName,
                     Description, DateReceived, Total, Insurance, ProcessingFee,
                     CustomerName, CustomerEmail, CustomerPhone, Currency,
                     SourceUrl, ExchangeRate)
                VALUES (:id, :order_id, 'Event one', 'Example payment',
                        '2026-10-14 12:00:00', 100, 5, 3,
                        'Stripe Buyer', 'stripe@example.com', '5550200', 'USD',
                        'https://example.com', 1)
            """),
                {"id": transaction_id, "order_id": order_id},
            )
    run("upgrade")
    run("check")
    with engine.connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT * FROM OrderDetails ORDER BY TicketPartnerOrderId, StripeTransactionId"
                )
            ).mappings()
        ]
    assert len(rows) == 6  # Two payments for order 1, one row for each other order.
    assert [row["StripeTransactionId"] for row in rows[:2]] == ["tx_one", "tx_two"]
    assert rows[0]["EventId"] == 1
    assert rows[0]["TicketSocketNativeEventId"] == 900
    assert rows[0]["PartnerOrderId"] == rows[0]["TicketSocketOrderId"] == 11
    assert rows[0]["TicketSocketNativeOrderId"] == 1100
    assert rows[0]["Email"] == "ticket@example.com"
    assert rows[0]["StripeCustomerEmail"] == "stripe@example.com"
    assert rows[0]["IsManualTransfer"] == 1
    assert rows[2]["TicketSocketOrderId"] == 12
    assert rows[2]["StripeTransactionId"] is None
    assert rows[3]["TicketSocketOrderId"] is None  # Same ID, different partner.
    assert rows[3]["StripeTransactionId"] == "tx_manual"
    assert rows[4]["TicketSocketOrderId"] is None
    assert rows[4]["StripeTransactionId"] is None
    assert rows[5]["TicketSocketOrderId"] is None  # Same ID, different event.
    with engine.connect() as connection:
        tickets = [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM TicketDetails ORDER BY TicketPartnerTicketId")
            ).mappings()
        ]
        # Multiple Stripe payments must not multiply ticket rows.
        assert len(tickets) == 6
        ticket = tickets[0]
        assert ticket["TicketPartnerTicketId"] == 101
        assert ticket["TicketPartnerOrderId"] == 1
        assert ticket["TicketPartnerEventId"] == 100
        assert ticket["TicketPartnerId"] == 2
        assert ticket["EventId"] == 1
        assert ticket["TicketSocketOrderTicketId"] == ticket["PartnerTicketId"] == 21
        assert ticket["TicketSocketNativeTicketId"] == 2100
        assert ticket["TicketSocketNativeOrderId"] == 1100
        assert ticket["TicketSocketNativeEventId"] == 900
        assert ticket["IsCheckedIn"] == 1
        assert ticket["OrderIsDeleted"] == 0
        assert ticket["Price"] == 50
        assert ticket["TicketTypeOrder"] == 3
        for missing in tickets[1:5]:
            assert missing["TicketSocketOrderTicketId"] is None
            assert missing["IsActive"] is None
        assert tickets[2]["TicketSocketOrderId"] is None  # Different partner.
        assert tickets[3]["TicketSocketOrderId"] == 12  # Ticket belongs to order 11.
        assert tickets[4]["TicketSocketOrderId"] is None  # Different event.
        assert tickets[5]["TicketTypeOrder"] == 1  # No provider ticket type.
        assert connection.exec_driver_sql("""
            SELECT COUNT(*) FROM TicketDetails
            WHERE EventId=1 AND TicketPartnerId=2 AND OrderIsDeleted <> 1
                AND IsActive=1 AND IsRefunded=0 AND IsChargedBack=0
        """).scalar_one() == 1
    run("downgrade", "0002_manual_transfer")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SHOW FULL TABLES LIKE 'OrderOverview'").first()
            is None
        )
        assert (
            connection.exec_driver_sql("SHOW FULL TABLES LIKE 'TicketDetails'").first()
            is None
        )
        assert (
            connection.exec_driver_sql("SHOW FULL TABLES LIKE 'OrderDetails'").first()
            is None
        )
        assert (
            connection.exec_driver_sql("SHOW FULL TABLES LIKE 'EventDetails'").first()
            is None
        )
        for table in (
            "TicketPartnerOrders",
            "TicketPartnerEvents",
            "StripeTransactions",
        ):
            assert (
                connection.exec_driver_sql(f"SHOW TABLES LIKE '{table}'").first()
                is None
            )
        # Full Stripe rollback removes its new tables, but retains original source orders.
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM TicketSocketOrders"
            ).scalar_one()
            == 2
        )
        assert (
            connection.exec_driver_sql(
                "SELECT IsManualTransfer FROM TicketSocketOrders WHERE Id=11"
            ).scalar_one()
            == 1
        )
        assert (
            connection.exec_driver_sql(
                "SELECT TicketSocketEventId FROM ExternalEvents WHERE EventId=1"
            ).scalar_one()
            == 10
        )
    run("upgrade")
    run("check")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM TicketDetails"
            ).scalar_one()
            == 3
        )
        assert (
            connection.exec_driver_sql("SELECT COUNT(*) FROM OrderDetails").scalar_one()
            == 2
        )
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM OrderDetails WHERE StripeTransactionId IS NOT NULL"
            ).scalar_one()
            == 0
        )
