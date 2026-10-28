"""Historical Stripe phone metadata survives migration without silent truncation."""

from pathlib import Path
import shutil

import pytest
from sqlalchemy import text
from test_migrations import database  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


def test_long_phone_is_preserved_and_unsafe_downgrade_refused(database):
    run, engine, root = database
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade", "0004_stripe_payment_intents")
    run("upgrade")
    phone = "+1 (555) 123-4567 extension 12345"
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO StripePaymentIntents (
            PaymentIntentId, EventName, Description, DateReceived, Total,
            Insurance, ProcessingFee, CustomerName, CustomerEmail, CustomerPhone,
            Currency, SourceUrl, ExchangeRate
        ) VALUES ('pi_phone', '', '', '2026-08-16', 100, 0, 3, '', '', :phone, 'usd', '', 1)
        """),
            {"phone": phone},
        )
        assert (
            connection.exec_driver_sql(
                "SELECT CustomerPhone FROM StripePaymentIntents"
            ).scalar_one()
            == phone
        )
        connection.exec_driver_sql("SELECT * FROM OrderDetails LIMIT 1").all()
    with pytest.raises(RuntimeError, match="exceed 20"):
        run("downgrade", "0004_stripe_payment_intents")
    with engine.begin() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT CustomerPhone FROM StripePaymentIntents"
            ).scalar_one()
            == phone
        )
        connection.exec_driver_sql(
            "UPDATE StripePaymentIntents SET CustomerPhone='5551234567'"
        )
    run("downgrade", "0004_stripe_payment_intents")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT CustomerPhone FROM StripePaymentIntents"
            ).scalar_one()
            == "5551234567"
        )
