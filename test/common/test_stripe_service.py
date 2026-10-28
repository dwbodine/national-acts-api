"""Tests for the Stripe service."""

from types import SimpleNamespace
from datetime import datetime

import pytest
import stripe

from common import stripe_service


def test_transaction_exchange_rate_is_not_scaled():
    """Stripe exchange rates are ratios, unlike amount fields in minor units."""
    intent = SimpleNamespace(
        id="pi_rate",
        metadata={},
        description="",
        created=100,
        amount=1000,
        currency="cad",
        application_fee_amount=None,
        payment_method_types=["card"],
        latest_charge=SimpleNamespace(
            balance_transaction=SimpleNamespace(
                fee=30,
                exchange_rate=1.25,
            )
        ),
    )
    transaction = stripe_service.StripeTransaction("42", "succeeded", intent)
    assert transaction.exchange_rate == 1.25


def test_expanded_refund_details_are_persisted(monkeypatch):
    """Keep expanded payment metadata and the refund exchange rate in storage."""
    refund = stripe.Refund.construct_from(
        {
            "id": "re_expanded",
            "amount": 500,
            "currency": "usd",
            "status": "pending",
            "reason": "requested_by_customer",
            "created": 150,
            "payment_intent": {
                "id": "pi_original",
                "amount": 2000,
                "metadata": {
                    "orderId": "42",
                    "customerName": "Buyer",
                    "customerEmail": "buyer@example.com",
                    "customerPhone": "555",
                    "domain": "example.com",
                    "eventIds": "10,11",
                    "eventNames": "VIP",
                },
            },
            "balance_transaction": {"exchange_rate": 1.25},
        },
        None,
    )
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append(data)
    )
    stripe_service.StripeService()._upset_refund(stripe_service.StripeRefund(refund))
    data = writes[0]
    assert data["PaymentIntentId"] == "pi_original"
    assert data["OrderId"] == "42"
    assert data["OriginalAmount"] == 20
    assert data["Amount"] == 5
    assert data["CustomerName"] == "Buyer"
    assert data["CustomerEmail"] == "buyer@example.com"
    assert data["CustomerPhone"] == "555"
    assert data["SourceUrl"] == "example.com"
    assert data["EventId"] == "10,11"
    assert data["EventName"] == "VIP"
    assert data["ExchangeRate"] == 1.25
    assert data["Status"] == "pending"


def test_get_transactions_auto_pages_through_every_result(monkeypatch):
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
            self.v1 = SimpleNamespace(
                payment_intents=FakePaymentIntents(),
                refunds=SimpleNamespace(list=list_refunds),
            )

    def list_refunds(params):
        """Return multiple pages of real SDK refund objects."""
        calls["refund_params"] = params
        return SimpleNamespace(
            auto_paging_iter=lambda: (
                stripe.Refund.construct_from(
                    {
                        "id": f"re_{index}",
                        "payment_intent": "pi_older_payment",
                        "amount": 250,
                        "currency": "usd",
                        "status": "succeeded",
                        "reason": None,
                        "created": 150,
                        "balance_transaction": None,
                    },
                    None,
                )
                for index in range(205)
            )
        )

    monkeypatch.setenv("STRIPE_API_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(stripe_service.stripe, "StripeClient", FakeStripeClient)
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append((sql, data)) or 0
    )

    result = stripe_service.StripeService().get_transactions(start=100, end=200)

    assert calls["api_key"] == "sk_test_example"
    assert calls["params"] == {
        "created": {"gte": 100, "lt": 200},
        "limit": 100,
        "expand": ["data.latest_charge.balance_transaction"],
    }
    assert calls["iterated"] is True
    assert calls["refund_params"]["created"] == {"gte": 100, "lt": 200}
    assert calls["refund_params"]["limit"] == 100
    assert len(result) == 205
    assert all(isinstance(item, stripe_service.StripeRefund) for item in result)
    assert result[-1].stripe_id == "re_204"
    assert result[0].payment_intent_id == "pi_older_payment"
    assert result[0].amount == 2.5
    assert result[0].created_at == 150
    assert len(writes) == 205
    assert "INSERT INTO StripeRefunds" in writes[0][0]
    assert "Status=VALUES(Status)" in writes[0][0]
    assert writes[0][1]["StripeRefundId"] == "re_0"
    assert writes[0][1]["PaymentIntentId"] == "pi_older_payment"
    assert writes[0][1]["CreatedAt"] == datetime(1970, 1, 1, 0, 2, 30)
    assert writes[0][1]["Amount"] == 2.5
    assert writes[0][1]["ExchangeRate"] == 0


@pytest.mark.parametrize(
    "orders, expected_order_id",
    [
        (
            [{"Id": 80, "OrderId": 42621, "EventId": 77, "TicketPartnerOrderId": 900}],
            900,
        ),
        (
            [{"Id": 80, "OrderId": 42621, "EventId": 77, "TicketPartnerOrderId": None}],
            None,
        ),
        ([], None),
        ([{"TicketPartnerOrderId": 900}, {"TicketPartnerOrderId": 901}], None),
    ],
)
@pytest.mark.parametrize("event_metadata", [None, "", "999,888"])
def test_successful_intents_are_saved_with_partner_order_mapping(
    monkeypatch, orders, expected_order_id, event_metadata
):
    """Match external order IDs and persist only succeeded intents with metadata."""
    intent = SimpleNamespace(
        id="pi_new",
        metadata=stripe.StripeObject.construct_from(
            {
                "orderId": "42621",
                "domain": "europe.nationalactsvip.com",
                "eventIds": event_metadata,
                "eventNames": "VIP Night",
                "stripeAccount": "acct_test",
            },
            None,
        ),
        status="succeeded",
        description=None,
        payment_method_types=["card"],
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
    client = SimpleNamespace(
        v1=SimpleNamespace(
            payment_intents=SimpleNamespace(
                list=lambda params: SimpleNamespace(
                    auto_paging_iter=lambda: iter(intents)
                )
            ),
            refunds=SimpleNamespace(
                list=lambda params: SimpleNamespace(auto_paging_iter=lambda: iter(()))
            ),
        )
    )
    monkeypatch.setenv("STRIPE_API_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(stripe_service.stripe, "StripeClient", lambda api_key: client)
    lookups = []
    inserts = []
    monkeypatch.setattr(
        stripe_service,
        "db_query_all",
        lambda sql, data: lookups.append((sql, data)) or orders,
    )
    monkeypatch.setattr(
        stripe_service,
        "db_insert",
        lambda sql, data: inserts.append((sql, data)) or 0,
    )

    transactions = stripe_service.StripeService().get_transactions(100, 200)

    assert transactions == []
    assert lookups[0][1] == {"order_id": "42621", "ticket_socket_id": 2}
    assert "WHERE tso.OrderId=%(order_id)s" in lookups[0][0]
    assert "sec.TicketSocketId=%(ticket_socket_id)s" in lookups[0][0]
    if expected_order_id is None:
        assert inserts == []
        return
    assert len(inserts) == 1
    sql, data = inserts[0]
    assert data["partner_order_id"] == expected_order_id
    assert data["native_order_id"] == "42621"
    assert data["native_event_id"] == (77 if len(orders) == 1 else None)
    assert data["stripe_id"] == "pi_new"
    assert data["date_received"] == datetime(2024, 1, 1)
    assert data["total"] == 125
    assert data["insurance"] is None
    assert data["application_fee"] == 5
    assert data["insurance_verified"] == 0
    assert data["processing_fee"] == 3.5
    assert data["description"] == ""
    assert data["status"] == "succeeded"
    assert data["payment_method"] == "card"
    assert data["stripe_account"] == "acct_test"
    assert "Status, PaymentMethod, StripeAccount" in sql
    # A duplicate must leave every stored field, including LastUpdated, alone.
    assert sql.split("ON DUPLICATE KEY UPDATE")[1].strip() == (
        "PaymentIntentId=PaymentIntentId"
    )


@pytest.mark.parametrize(
    "domain, expected_account",
    [
        ("secure.nationalactsvip.com", 1),
        ("europe.nationalactsvip.com", 2),
        ("australia.nationalactsvip.com", 3),
        ("tickets.nationalactsvip.com", 4),
        ("japan.nationalactsvip.com", 5),
        ("secure.savingabelvip.com", 6),
    ],
)
def test_domain_identifies_ticket_socket_account(domain, expected_account):
    """Account identity must reach the upsert even when eventIds is absent."""
    intent = SimpleNamespace(
        id="pi_account",
        metadata={"orderId": "42547", "domain": domain},
        description="",
        created=100,
        amount=100,
        currency="usd",
        application_fee_amount=None,
        payment_method_types=["card"],
        latest_charge=None,
    )
    transaction = stripe_service.StripeTransaction("42547", "succeeded", intent)
    assert transaction.ticket_socket_id == expected_account
    assert transaction.event_id == ""
