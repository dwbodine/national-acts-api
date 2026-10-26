"""Manual payment inserts, partial edits, order checks and transaction rollback."""

from datetime import datetime
from decimal import Decimal
import re
import sqlite3

import mariadb
import pytest

from common import stripe_payment_intent_service as payment_service
from test_stripe_reconciliation_service import order_database  # pylint: disable=unused-import


class CursorAdapter:
    """Execute the service's SQL, emulating MariaDB parameter binding and dict rows."""

    def __init__(self, connection, owner):
        self.cursor = connection.cursor()
        self.owner = owner

    def execute(self, sql, data):
        if self.owner.fail_write and sql.startswith("UPDATE"):
            raise mariadb.OperationalError("Simulated write failure")
        sql = re.sub(r"%\((\w+)\)s", r":\1", sql).replace(" FOR UPDATE", "")
        values = {key: str(value) if isinstance(value, Decimal) else
                  value.isoformat() if isinstance(value, datetime) else value
                  for key, value in data.items()}
        try:
            self.cursor.execute(sql, values)
        except sqlite3.IntegrityError as error:
            raise mariadb.IntegrityError(str(error)) from error

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def close(self):
        self.cursor.close()


class ConnectionAdapter:
    """Keep fixture storage alive while observing the service's transaction boundary."""

    def __init__(self, connection):
        self.connection = connection
        self.rollbacks = 0
        self.closed = False
        self.fail_write = False

    def begin(self):
        self.connection.execute("BEGIN")

    def cursor(self, **_options):
        return CursorAdapter(self.connection, self)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.rollbacks += 1
        self.connection.rollback()

    def close(self):
        self.closed = True


@pytest.fixture
def payments(order_database, monkeypatch):
    order_database.executescript("""
        DROP TABLE StripePaymentIntents;
        CREATE TABLE StripePaymentIntents (
            StripePaymentIntentId INTEGER PRIMARY KEY AUTOINCREMENT,
            PaymentIntentId TEXT NOT NULL UNIQUE, TicketPartnerOrderId INT,
            NativeOrderId INT, NativeEventId INT, EventName TEXT, Description TEXT NOT NULL,
            DateReceived TEXT NOT NULL, Total NUMERIC NOT NULL, Insurance NUMERIC DEFAULT 0,
            ProcessingFee NUMERIC NOT NULL, CustomerName TEXT, CustomerEmail TEXT, CustomerPhone TEXT,
            Currency TEXT NOT NULL, SourceUrl TEXT NOT NULL, ExchangeRate NUMERIC NOT NULL,
            Status TEXT NOT NULL DEFAULT 'succeeded', PaymentMethod TEXT DEFAULT 'card',
            StripeAccount TEXT NOT NULL DEFAULT '', ApplicationFee NUMERIC NOT NULL DEFAULT 0,
            InsuranceVerified INT NOT NULL DEFAULT 0, ProcessingFeeCurrency TEXT,
            LastUpdated TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO StripePaymentIntents (StripePaymentIntentId, PaymentIntentId, Description,
            DateReceived, Total, ProcessingFee, Currency, SourceUrl, ExchangeRate)
        VALUES (7, 'pi_existing', 'Original description', '2026-03-01', 100, 3,
            'usd', 'tickets.nationalactsvip.com', 1);
    """)
    adapter = ConnectionAdapter(order_database)
    monkeypatch.setattr(payment_service, "db_get_connection", lambda: adapter)
    return order_database, adapter


def new_payment(**overrides):
    return {"PaymentIntentId": "pi_new", "Description": "Imported manually",
            "DateReceived": "2026-03-01T07:00:00-05:00", "Total": "123.45",
            "ProcessingFee": "3.45", "Currency": "USD",
            "SourceUrl": "tickets.nationalactsvip.com", "ExchangeRate": "1",
            "TicketPartnerOrderId": 5, **overrides}


def test_partial_update_links_order_without_overwriting_payment_amount(payments):
    database, connection = payments
    result = payment_service.StripePaymentIntentService().save({
        "StripePaymentIntentId": 7, "TicketPartnerOrderId": 5,
    })
    assert result["created"] is False
    assert result["paymentIntent"]["Total"] == 100
    assert result["paymentIntent"]["Description"] == "Original description"
    assert result["paymentIntent"]["NativeOrderId"] == 105
    assert result["paymentIntent"]["NativeEventId"] == 205
    assert database.execute("SELECT TicketPartnerOrderId FROM StripePaymentIntents").fetchone()[0] == 5
    assert connection.closed


@pytest.mark.parametrize("record_id", [None, 20])
def test_insert_returns_id_defaults_and_utc_timestamp(payments, record_id):
    payload = new_payment()
    if record_id is not None:
        payload["StripePaymentIntentId"] = record_id
    result = payment_service.StripePaymentIntentService().save(payload)
    row = result["paymentIntent"]
    assert result["created"] is True
    assert row["StripePaymentIntentId"] == (record_id or 8)
    assert row["Currency"] == "usd"
    assert row["DateReceived"] == "2026-03-01T12:00:00"
    assert row["PaymentMethod"] == "card"
    assert row["Insurance"] == 0
    assert row["CustomerName"] is None
    assert row["NativeEventId"] == 205


@pytest.mark.parametrize("changes", [
    {"TicketPartnerOrderId": 2}, {"TicketPartnerOrderId": 3}, {"TicketPartnerOrderId": 4},
    {"TicketPartnerOrderId": 999}, {"TicketPartnerOrderId": 5, "NativeEventId": 999},
])
def test_ineligible_or_inconsistent_order_links_roll_back(payments, changes):
    database, connection = payments
    with pytest.raises(ValueError):
        payment_service.StripePaymentIntentService().save({"StripePaymentIntentId": 7, **changes})
    assert connection.rollbacks == 1
    assert connection.closed
    assert database.execute("SELECT TicketPartnerOrderId FROM StripePaymentIntents").fetchone()[0] is None


def test_duplicate_stripe_identifier_never_updates_a_different_row(payments):
    database, connection = payments
    with pytest.raises(payment_service.PaymentIntentConflict):
        payment_service.StripePaymentIntentService().save(new_payment(PaymentIntentId="pi_existing"))
    assert connection.rollbacks == 1
    assert database.execute("SELECT COUNT(*) FROM StripePaymentIntents").fetchone()[0] == 1


def test_existing_stripe_identity_cannot_be_replaced(payments):
    with pytest.raises(payment_service.PaymentIntentConflict):
        payment_service.StripePaymentIntentService().save({
            "StripePaymentIntentId": 7, "PaymentIntentId": "pi_different",
        })


def test_failed_write_rolls_back_and_closes_connection(payments):
    database, connection = payments
    connection.fail_write = True
    with pytest.raises(mariadb.OperationalError):
        payment_service.StripePaymentIntentService().save({"StripePaymentIntentId": 7, "Total": 250})
    assert connection.rollbacks == 1
    assert connection.closed
    assert database.execute("SELECT Total FROM StripePaymentIntents").fetchone()[0] == 100


@pytest.mark.parametrize("changes", [
    {"Total": "NaN"}, {"Total": "0.001"}, {"Total": "100000000"}, {"Total": -1},
    {"NativeOrderId": True}, {"StripePaymentIntentId": 0}, {"LastUpdated": "today"},
    {"Currency": "USDD"}, {"Status": "pending"}, {"PaymentIntentId": "not_a_stripe_id"},
])
def test_invalid_changes_never_open_a_connection(monkeypatch, changes):
    monkeypatch.setattr(payment_service, "db_get_connection", lambda: pytest.fail("Unexpected DB access"))
    with pytest.raises(ValueError):
        payment_service.StripePaymentIntentService().save({"StripePaymentIntentId": 7, **changes})


def test_insert_requires_complete_fields_and_preserves_existing_data(payments):
    database, connection = payments
    with pytest.raises(ValueError, match="Missing insert fields"):
        payment_service.StripePaymentIntentService().save({"StripePaymentIntentId": 999, "Total": 1})
    assert connection.rollbacks == 1
    assert database.execute("SELECT COUNT(*) FROM StripePaymentIntents").fetchone()[0] == 1
