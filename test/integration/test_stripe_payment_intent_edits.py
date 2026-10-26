"""Verify explicit admin inserts/updates and conflicts using the real MariaDB driver."""

import os
from pathlib import Path
import shutil

import mariadb
import pytest
from test_migrations import database  # pylint: disable=unused-import

from common import stripe_payment_intent_service as payment_service

pytestmark = pytest.mark.integration


def test_manual_payment_insert_update_and_duplicate_rollback(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(Path(__file__).resolve().parents[2] / "migrations/versions",
                    root / "migrations/versions", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    run("upgrade")
    monkeypatch.setattr(payment_service, "db_get_connection", lambda: mariadb.connect(
        host="127.0.0.1", port=int(os.environ["TEST_MARIADB_PORT"]), user="root",
        password=os.environ["TEST_MARIADB_PASSWORD"], database=os.environ["MIGRATION_DB_DB"],
        autocommit=True,
    ))
    service = payment_service.StripePaymentIntentService()
    payload = {"PaymentIntentId": "pi_manual_test", "Description": "Manual import",
               "DateReceived": "2026-10-26T12:00:00Z", "Total": "100.25",
               "ProcessingFee": "3.25", "Currency": "usd", "ExchangeRate": "1",
               "SourceUrl": "tickets.nationalactsvip.com"}
    inserted = service.save(payload)
    record_id = inserted["paymentIntent"]["StripePaymentIntentId"]
    assert inserted["created"] is True
    assert inserted["paymentIntent"]["Total"] == "100.25"
    assert inserted["paymentIntent"]["PaymentMethod"] == "card"
    updated = service.save({"StripePaymentIntentId": record_id, "CustomerName": "Manual Buyer",
                            "PaymentMethod": None, "Insurance": None})
    assert updated["created"] is False
    assert updated["paymentIntent"]["PaymentMethod"] is None
    assert updated["paymentIntent"]["Insurance"] is None
    assert updated["paymentIntent"]["Total"] == "100.25"
    with pytest.raises(payment_service.PaymentIntentConflict):
        service.save(payload)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM StripePaymentIntents").scalar_one() == 1
