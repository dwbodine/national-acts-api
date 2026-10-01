"""Tests for the Stripe service."""

from types import SimpleNamespace

from common import stripe_service


def test_get_payment_intents_auto_pages_through_every_result(monkeypatch):
    """Process every intent exposed by Stripe's auto-pagination iterator."""

    calls = {}
    intents = [
        SimpleNamespace(
            id=f"pi_{index}",
            metadata={},
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

    stripe_service.StripeService().get_payment_intents(start=100, end=200)

    assert calls["api_key"] == "sk_test_example"
    assert calls["params"] == {
        "created": {"gte": 100, "lt": 200},
        "limit": 100,
    }
    assert calls["iterated"] is True
