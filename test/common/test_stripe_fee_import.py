"""Fee import precision, shared IDs, and repeat report handling."""

import csv
from decimal import Decimal
from io import StringIO

import pytest

from common import stripe_service


def csv_content(rows):
    """Create representative itemized fee CSV bytes."""
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=stripe_service.FEE_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "balance_transaction_id": "txn_shared",
                "fee_transaction_id": "ft_shared",
                "currency": "usd",
                "amount": "0.050000000000000000",
                "incurred_by_type": "payment_intent",
                "incurred_at": "2026-10-09 00:00:00",
                **row,
            }
        )
    return stream.getvalue().encode("utf-8-sig")


def test_reimports_preserve_precision_and_shared_ids(monkeypatch):
    """Overlapping reports reuse row keys without collapsing different fee rows."""
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append((sql, data))
    )
    rows = [
        {"incurred_by": "pi_one"},
        {"incurred_by": "pi_two", "amount": "0.284736000000000001", "tax": "-0.000001"},
        {"incurred_by": "pi_one"},
    ]
    service = stripe_service.StripeService()
    assert service._upsert_fee_report(csv_content(rows)) == 2
    assert len(writes) == 2
    first_keys = {data["FeeRowKey"] for _, data in writes}
    assert len(first_keys) == 2
    assert writes[1][1]["Amount"] == Decimal("0.284736000000000001")
    assert writes[1][1]["Tax"] == Decimal("-0.000001")
    assert writes[0][1]["PricingTier"] is None
    assert "ON DUPLICATE KEY UPDATE" in writes[0][0]
    writes.clear()
    service._upsert_fee_report(csv_content(list(reversed(rows))))
    assert {data["FeeRowKey"] for _, data in writes} == first_keys


def test_equivalent_decimal_rows_are_not_duplicated(monkeypatch):
    """Decimal formatting differences must not create separate fees."""
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append(data)
    )
    service = stripe_service.StripeService()
    count = service._upsert_fee_report(
        csv_content(
            [
                {"amount": "0.05", "tax": "0"},
                {"amount": "0.050000000000000000", "tax": "0.000000000000000000"},
            ]
        )
    )
    assert count == 1
    assert len(writes) == 1


@pytest.mark.parametrize(
    "invalid",
    [
        {"amount": "NaN"},
        {"amount": "bad"},
        {"incurred_at": "not-a-date"},
        {"currency": ""},
    ],
)
def test_invalid_report_does_not_write_partial_rows(monkeypatch, invalid):
    """Validate the entire CSV before any rows are persisted."""
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append(data)
    )
    with pytest.raises(ValueError):
        stripe_service.StripeService()._upsert_fee_report(csv_content([{}, invalid]))
    assert writes == []


def test_missing_headers_are_rejected():
    """A different report layout must not silently import incomplete data."""
    with pytest.raises(ValueError, match="columns"):
        stripe_service.StripeService()._upsert_fee_report(b"amount,currency\n1,usd\n")


def test_only_payment_intent_fees_are_imported(monkeypatch):
    """Ignore charge, refund, and unclassified rows in a mixed fee report."""
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append(data)
    )
    count = stripe_service.StripeService()._upsert_fee_report(
        csv_content(
            [
                {"incurred_by": "pi_keep", "incurred_by_type": "payment_intent"},
                {"incurred_by": "ch_skip", "incurred_by_type": "charge"},
                {"incurred_by": "re_skip", "incurred_by_type": "refund"},
                {"incurred_by_type": ""},
            ]
        )
    )
    assert count == 1
    assert len(writes) == 1
    assert writes[0]["IncurredBy"] == "pi_keep"
