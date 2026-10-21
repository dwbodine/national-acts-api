"""Payment intent table renaming preserves data, uniqueness, and dependent views."""

from pathlib import Path
import shutil

import pytest
from test_migrations import database  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


def test_payment_intent_migration_round_trip(database):
    run, engine, root = database
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade", "0003_stripe_transaction_details")
    insert = """INSERT INTO StripeTransactions (
        StripeTransactionId, EventName, Description, DateReceived, Total,
        Insurance, ProcessingFee, CustomerName, CustomerEmail, CustomerPhone,
        Currency, SourceUrl, ExchangeRate
    ) VALUES ('pi_existing', 'VIP', '', '2026-10-01', 100, 0, 3, '', '', '', 'usd', '', 1)"""
    with engine.begin() as connection:
        connection.exec_driver_sql(insert)
    run("upgrade")
    with engine.begin() as connection:
        row = connection.exec_driver_sql(
            "SELECT StripePaymentIntentId, PaymentIntentId, Total FROM StripePaymentIntents"
        ).one()
        assert row[0] > 0
        assert row[1] == "pi_existing"
        assert row[2] == 100
        updated_insert = insert.replace(
            "StripeTransactions", "StripePaymentIntents"
        ).replace("StripeTransactionId", "PaymentIntentId")
        connection.exec_driver_sql(
            updated_insert + " ON DUPLICATE KEY UPDATE PaymentIntentId=PaymentIntentId"
        )
        connection.exec_driver_sql(updated_insert.replace("pi_existing", "pi_new"))
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(DISTINCT StripePaymentIntentId) FROM StripePaymentIntents"
            ).scalar_one()
            == 2
        )
        connection.exec_driver_sql("SELECT * FROM OrderDetails LIMIT 1").all()
        connection.exec_driver_sql("SELECT * FROM OrderOverview LIMIT 1").all()
    run("downgrade", "0003_stripe_transaction_details")
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT StripeTransactionId FROM StripeTransactions ORDER BY StripeTransactionId"
        ).scalars().all() == ["pi_existing", "pi_new"]
        connection.exec_driver_sql("SELECT * FROM OrderDetails LIMIT 1").all()
        connection.exec_driver_sql("SELECT * FROM OrderOverview LIMIT 1").all()
