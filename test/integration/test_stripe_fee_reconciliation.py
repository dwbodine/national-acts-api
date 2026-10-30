"""Real SQL checks for fee attribution, retry totals, and import audit history."""

from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import mariadb
import pytest
import stripe
from test_migrations import database  # pylint: disable=unused-import

from common import db, stripe_service
from common.stripe_fee_reconciliation_service import StripeFeeReconciliationService
from test.common.test_stripe_fee_import import csv_content

pytestmark = pytest.mark.integration


def test_import_attribution_audit_and_missing_fees(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade")

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
    with engine.begin() as connection:
        for key in ("pi_paid", "pi_missing", "pi_refund_only"):
            connection.exec_driver_sql(
                """INSERT INTO StripePaymentIntents
                (PaymentIntentId, Description, DateReceived, Total, ProcessingFee,
                 Currency, SourceUrl, ExchangeRate, Status, StripeAccount)
                VALUES (%s, '', '2026-01-01', 10, 1, 'usd', '', 1, 'succeeded', 'acct_test')""",
                (key,),
            )
    report = stripe.StripeObject.construct_from(
        {
            "id": "frr_test",
            "status": "succeeded",
            "result": {"id": "file_test"},
            "parameters": {"interval_start": 1767225600, "interval_end": 1767312000},
        },
        None,
    )
    client = SimpleNamespace(
        v1=SimpleNamespace(
            accounts=SimpleNamespace(
                retrieve_current=lambda: SimpleNamespace(id="acct_test")
            ),
            reporting=SimpleNamespace(
                report_runs=SimpleNamespace(retrieve=lambda key: report)
            ),
            charges=SimpleNamespace(
                retrieve=lambda key: SimpleNamespace(payment_intent="pi_paid")
            ),
            refunds=SimpleNamespace(
                retrieve=lambda key: SimpleNamespace(payment_intent="pi_refund_only")
            ),
        )
    )
    monkeypatch.setenv("STRIPE_API_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(stripe_service.stripe, "StripeClient", lambda api_key: client)
    content = csv_content(
        [
            {
                "incurred_by": "ch_paid",
                "incurred_by_type": "charge",
                "feature_name": "Radar standard",
                "amount": "0.05",
                "tax": "0.01",
            },
            {
                "incurred_by": "pi_paid",
                "feature_name": "Radar standard",
                "amount": "0.02",
            },
            {
                "incurred_by": "re_only",
                "incurred_by_type": "refund",
                "feature_name": "Radar standard",
                "amount": "0.50",
            },
            {"incurred_by": "po_other", "incurred_by_type": "payout"},
        ]
    )
    monkeypatch.setattr(
        stripe_service.StripeService, "get_fee_report_csv", lambda *_: content
    )
    service = stripe_service.StripeService()
    for _ in range(2):
        assert service.get_fee_report("frr_test")["rows_upserted"] == 4
    payments = db.db_query_all(
        "SELECT PaymentIntentId, RadarFee FROM StripePaymentIntents"
    )
    assert {row["PaymentIntentId"]: row["RadarFee"] for row in payments} == {
        "pi_paid": Decimal("0.08"),
        "pi_missing": None,
        "pi_refund_only": None,
    }
    assert db.db_query_all("SELECT COUNT(*) AS n FROM StripeFees")[0]["n"] == 4
    audit = db.db_query_all("SELECT * FROM StripeFeeReportImports")[0]
    assert audit["StripeAccount"] == "acct_test"
    assert audit["Status"] == "succeeded"
    assert audit["RowsRead"] == audit["RowsImported"] == 4
    assert audit["RowsSkipped"] == 0
    assert audit["RowsUnresolved"] == 1
    assert audit["ImportedAt"] is not None
    missing = StripeFeeReconciliationService().get_missing(
        date(2026, 1, 1), date(2027, 1, 1)
    )
    assert missing["total"] == 2
    assert {row["PaymentIntentId"] for row in missing["payments"]} == {
        "pi_missing",
        "pi_refund_only",
    }
    monkeypatch.setattr(
        stripe_service.StripeService, "get_fee_report_csv", lambda *_: b"bad"
    )
    with pytest.raises(ValueError):
        service.get_fee_report("frr_test")
    audit = db.db_query_all("SELECT * FROM StripeFeeReportImports")[0]
    assert audit["Status"] == "failed"
    assert "required columns" in audit["Error"]
    assert audit["ImportedAt"] is None
