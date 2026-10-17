"""Tests for the Stripe service."""

from types import SimpleNamespace
from datetime import datetime

import pytest
import stripe

from common import stripe_service


def test_get_payment_intents_auto_pages_through_every_result(monkeypatch):
    """Process every intent exposed by Stripe's auto-pagination iterator."""

    calls = {}
    intents = [
        SimpleNamespace(
            id=f"pi_{index}",
            metadata=stripe.StripeObject.construct_from({}, None),
            amount=100,
            status="succeeded",
        )
        for index in range(205)
    ]

    class FakePaymentIntentList:
        """Fake paginated Stripe list."""

        def auto_paging_iter(self):
            """Yield all fake payment intents."""

            calls["iterated"] = True
            yield from intents

    class FakePaymentIntents:
        """Fake Payment Intents client service."""

        def list(self, params):
            """Capture list parameters and return the fake result."""

            calls["params"] = params
            return FakePaymentIntentList()

    class FakeStripeClient:
        """Fake top-level Stripe client."""

        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.v1 = SimpleNamespace(payment_intents=FakePaymentIntents())

    monkeypatch.setenv("STRIPE_API_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(stripe_service.stripe, "StripeClient", FakeStripeClient)

    result = stripe_service.StripeService().get_payment_intents(start=100, end=200)

    assert calls["api_key"] == "sk_test_example"
    assert calls["params"] == {
        "created": {"gte": 100, "lt": 200},
        "limit": 100,
        "expand": ["data.latest_charge.balance_transaction"],
    }
    assert calls["iterated"] is True
    assert result == []


@pytest.mark.parametrize(
    "orders, expected_order_id",
    [
        ([{"TicketPartnerOrderId": 900}], 900),
        ([], None),
        ([{"TicketPartnerOrderId": 900}, {"TicketPartnerOrderId": 901}], None),
    ],
)
def test_successful_intents_are_saved_with_partner_order_mapping(
    monkeypatch, orders, expected_order_id
):
    """Match external order IDs and persist only succeeded intents with metadata."""
    intent = SimpleNamespace(
        id="pi_new",
        metadata=stripe.StripeObject.construct_from(
            {"orderId": "42621", "eventNames": "VIP Night"}, None
        ),
        status="succeeded",
        description=None,
        created=1704067200,
        amount=12500,
        currency="usd",
        application_fee_amount=500,
        latest_charge=SimpleNamespace(
            balance_transaction=SimpleNamespace(fee=350, exchange_rate=None)
        ),
    )
    intents = [
        intent,
        SimpleNamespace(
            id="pi_pending",
            metadata=stripe.StripeObject.construct_from({"orderId": "42621"}, None),
            status="processing",
        ),
        SimpleNamespace(
            id="pi_unrelated",
            metadata=stripe.StripeObject.construct_from({}, None),
            status="succeeded",
        ),
    ]
    client = SimpleNamespace(v1=SimpleNamespace(payment_intents=SimpleNamespace(
        list=lambda params: SimpleNamespace(auto_paging_iter=lambda: iter(intents))
    )))
    monkeypatch.setenv("STRIPE_API_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(stripe_service.stripe, "StripeClient", lambda api_key: client)
    lookups = []
    inserts = []
    monkeypatch.setattr(
        stripe_service, "db_query_all",
        lambda sql, data: lookups.append((sql, data)) or orders,
    )
    monkeypatch.setattr(
        stripe_service, "db_insert",
        lambda sql, data: inserts.append((sql, data)) or 0,
    )

    transactions = stripe_service.StripeService().get_payment_intents(100, 200)

    assert len(transactions) == 1
    assert len(inserts) == 1
    assert lookups[0][1] == {"order_id": "42621"}
    assert "WHERE tso.OrderId=%(order_id)s" in lookups[0][0]
    sql, data = inserts[0]
    assert data["partner_order_id"] == expected_order_id
    assert data["stripe_id"] == "pi_new"
    assert data["date_received"] == datetime(2024, 1, 1)
    assert data["total"] == 125
    assert data["insurance"] == 5
    assert data["processing_fee"] == 3.5
    assert data["description"] == ""
    # A duplicate must leave every stored field, including LastUpdated, alone.
    assert sql.split("ON DUPLICATE KEY UPDATE")[1].strip() == (
        "StripeTransactionId=StripeTransactionId"
    )
