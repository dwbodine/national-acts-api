"""Exercise the accounting migration and report query against real MariaDB."""

from decimal import Decimal
from pathlib import Path
import shutil

import pytest
from test_migrations import database  # pylint: disable=unused-import

from common import admin_settlement_service

pytestmark = pytest.mark.integration


def test_accounting_upgrade_and_report_query(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(Path(__file__).resolve().parents[2] / "migrations/versions",
                    root / "migrations/versions", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    run("upgrade", "0005_stripe_customer_phone")
    with engine.begin() as connection:
        connection.exec_driver_sql("""INSERT INTO StripePaymentIntents (
            PaymentIntentId, EventName, Description, DateReceived, Total, Insurance,
            ProcessingFee, CustomerName, CustomerEmail, CustomerPhone, Currency,
            SourceUrl, ExchangeRate
        ) VALUES ('pi_insurance', '', '', '2026-07-27', 257.80, 26.80, 38.09,
            '', '', '', 'usd', '', 1)""")
    run("upgrade")
    with engine.connect() as connection:
        row = connection.exec_driver_sql("""SELECT ApplicationFee, Insurance,
            ProcessingFee, InsuranceVerified, ProcessingFeeCurrency
            FROM StripePaymentIntents""").one()
        assert tuple(row) == (Decimal("26.80"), None, Decimal("38.09"), 0, None)
        connection.exec_driver_sql("SELECT * FROM OrderDetails LIMIT 1").all()

    def query(sql, data=None):
        with engine.connect() as connection:
            return [dict(row) for row in connection.exec_driver_sql(sql, data).mappings()]

    monkeypatch.setattr(admin_settlement_service, "db_query_all", query)
    # An empty database still resolves every table, field, grouping and date filter.
    assert admin_settlement_service.AdminSettlementService().get_report(1, 2)["orders"] == []
    assert admin_settlement_service.AdminSettlementService().get_report(
        1, 2, seller_id=4, event_ids=[10]
    )["orders"] == []
    run("downgrade", "0005_stripe_customer_phone")
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT Insurance, ProcessingFee FROM StripePaymentIntents"
        ).one()
        assert tuple(row) == (Decimal("26.80"), Decimal("38.09"))
