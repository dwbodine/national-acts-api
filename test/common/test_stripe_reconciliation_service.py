"""Execute reconciliation SQL against representative orders and eligibility flags."""

from datetime import date
import re
import sqlite3

import pytest

from common import stripe_reconciliation_service as report_service, stripe_service
from test_admin_settlement_service import payment


@pytest.fixture
def order_database(monkeypatch):
    """Exercise joins, exclusions and pagination without an external database."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.create_function("DATE_FORMAT", 2, lambda value, _format: value[:7])
    connection.create_function(
        "CONCAT_WS",
        -1,
        lambda sep, *args: sep.join(str(value) for value in args if value is not None),
    )
    connection.executescript("""
        CREATE TABLE Events (EventId INT, Title TEXT, EventDate TEXT,
            ExcludeFromDashboard INT, IsDeleted INT, IsCancelled INT, SellerId INT, VenueId INT);
        CREATE TABLE Venues (VenueId INT, Venue TEXT, City TEXT, State TEXT);
        CREATE TABLE TicketSocket (TicketSocketId INT, AccountName TEXT);
        CREATE TABLE SellerEventCategory (SellerEventCategoryId INT, TicketSocketId INT);
        CREATE TABLE TicketSocketEvents (Id INT, SellerEventCategoryId INT,
            Venue TEXT, City TEXT, State TEXT);
        CREATE TABLE TicketPartnerEvents (TicketPartnerEventId INT, TicketPartnerId INT,
            PartnerEventId INT, EventId INT);
        CREATE TABLE TicketPartnerOrders (TicketPartnerOrderId INT, TicketPartnerEventId INT,
            PartnerOrderId INT);
        CREATE TABLE TicketSocketOrders (Id INT, OrderId INT, EventId INT, TicketSocketEventId INT,
            PurchaseDate TEXT, IsDeleted INT, IsComped INT, IsActive INT, IsManualTransfer INT,
            PurchaserFirstName TEXT, PurchaserLastName TEXT, Email TEXT, CustomerProcessingFee NUMERIC);
        CREATE TABLE StripePaymentIntents (PaymentIntentId TEXT, TicketPartnerOrderId INT, Status TEXT);
        INSERT INTO TicketSocket VALUES (4, 'Tickets'), (1, 'Secure');
        INSERT INTO SellerEventCategory VALUES (1, 4), (2, 1);
        INSERT INTO Venues VALUES (1, 'Theater', 'Austin', 'TX');
    """)
    for index, flags in enumerate(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (None, None, None), (0, 0, 0)], 1
    ):
        connection.execute(
            "INSERT INTO Events VALUES (?, ?, '2026-06-01', ?, ?, ?, 1, 1)",
            (index, f"Event {index}", *flags),
        )
        connection.execute(
            "INSERT INTO TicketSocketEvents (Id, SellerEventCategoryId) VALUES (?, ?)",
            (index, 2 if index == 6 else 1),
        )
        connection.execute(
            "INSERT INTO TicketPartnerEvents VALUES (?, 2, ?, ?)", (index, index, index)
        )
        connection.execute(
            "INSERT INTO TicketPartnerOrders VALUES (?, ?, ?)", (index, index, index)
        )
        connection.execute(
            """INSERT INTO TicketSocketOrders VALUES
            (?, ?, ?, ?, '2026-03-01', 0, 0, 1, 0, 'Buyer', 'Name', 'buyer@example.com', 10)""",
            (index, 100 + index, 200 + index, index),
        )
    connection.execute(
        "INSERT INTO StripePaymentIntents VALUES ('pi_paid', 1, 'succeeded')"
    )
    connection.execute(
        "INSERT INTO StripePaymentIntents VALUES ('pi_pending', 5, 'processing')"
    )

    def query(sql, data):
        sql = re.sub(r"%\((\w+)\)s", r":\1", sql)
        data = {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in data.items()
        }
        return [dict(row) for row in connection.execute(sql, data)]

    monkeypatch.setattr(report_service, "db_query_all", query)
    monkeypatch.setattr(stripe_service, "db_query_all", query)
    yield connection
    connection.close()


def test_coverage_ignores_excluded_deleted_cancelled_events(order_database):
    report = report_service.StripeReconciliationService().get_missing_payments(
        date(2026, 1, 1), date(2027, 1, 1), ticket_socket_id=4
    )
    assert report["totalOrders"] == 2
    assert report["missingPaymentIntents"] == 1
    assert report["missingPercentage"] == 50
    assert [row["NativeOrderId"] for row in report["orders"]] == [105]
    assert report["orders"][0]["Venue"] == "Theater"
    assert report["months"][0]["TotalOrders"] == 2
    # A paid order is recognized only after successful payment status.
    order_database.execute(
        "UPDATE StripePaymentIntents SET Status='succeeded' WHERE PaymentIntentId='pi_pending'"
    )
    assert (
        report_service.StripeReconciliationService().get_missing_payments(
            date(2026, 1, 1), date(2027, 1, 1), ticket_socket_id=4
        )["missingPaymentIntents"]
        == 0
    )


def test_pagination_and_exclusive_end_do_not_change_coverage_counts(order_database):
    report = report_service.StripeReconciliationService().get_missing_payments(
        date(2026, 1, 1), date(2027, 1, 1), limit=1, offset=1
    )
    assert report["missingPaymentIntents"] == 2
    assert len(report["orders"]) == 1
    assert report["orders"][0]["TicketSocketId"] == 4
    empty = report_service.StripeReconciliationService().get_missing_payments(
        date(2026, 1, 1), date(2026, 3, 1)
    )
    assert empty["orders"] == []
    assert empty["missingPercentage"] is None


@pytest.mark.parametrize(
    "native_order, inserted",
    [(101, True), (102, False), (103, False), (104, False), (105, True)],
)
def test_import_matching_obeys_event_flags(
    order_database, monkeypatch, native_order, inserted
):
    writes = []
    transaction = payment()
    transaction.order_id = str(native_order)
    transaction.ticket_socket_id = 4
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append(data)
    )
    stripe_service.StripeService()._upsert_transaction(transaction)
    assert bool(writes) is inserted
