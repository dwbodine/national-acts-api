"""Compact Stripe fields replace raw financial payloads on event orders."""

from decimal import Decimal
from types import SimpleNamespace

from common import stripe_financial_service as financial


def test_compact_fields_use_stripe_and_join_fee_rows_by_payment_intent(monkeypatch):
    payments = [{"PaymentIntentId": "pi_a", "TicketPartnerOrderId": 10, "Currency": "cad",
                 "Status": "succeeded", "ExchangeRate": Decimal("0.75"),
                 "ProcessingFee": Decimal("14.76"), "ProcessingFeeCurrency": "usd",
                 "Insurance": Decimal("26.80")}]
    fees = [{"TicketPartnerOrderId": 10, "FeatureName": "Radar standard",
             "Amount": Decimal("0.05"), "Tax": Decimal("0.01"), "Currency": "usd"},
            {"TicketPartnerOrderId": 10, "FeatureName": "Radar standard",
             "Amount": Decimal("0.02"), "Tax": None, "Currency": "usd"},
            {"TicketPartnerOrderId": 10, "FeatureName": "Radar standard",
             "Amount": Decimal("0.03"), "Tax": None, "Currency": "eur"}]
    calls = []
    results = iter([payments, fees])
    monkeypatch.setattr(financial, "db_query_all",
                        lambda sql, data: calls.append((sql, data)) or next(results))
    order = SimpleNamespace(ticket_partner_order_id=10, exchange_rate=99, revenue=200)
    missing = SimpleNamespace(ticket_partner_order_id=None, exchange_rate=1)
    event = SimpleNamespace(orders=[order, missing])
    financial.StripeFinancialService().enrich_order_fields([event])
    assert order.exchange_rate == 0.75
    assert order.stripe_processing_fee == "14.76"
    assert order.insurance == "26.80"
    assert order.other_fees == [
        {"key": "Radar standard", "value": "0.03", "currency": "eur"},
        {"key": "Radar standard", "value": "0.08", "currency": "usd"},
    ]
    assert missing.exchange_rate is None
    assert missing.stripe_processing_fee is None and missing.insurance is None
    assert missing.other_fees == []
    assert len(calls) == 2
    assert "pi.PaymentIntentId=f.IncurredBy" in calls[1][0]
    assert "stripe_payments" not in vars(order)
    assert "stripe_refunds" not in vars(order)
    assert "stripe_totals_by_currency" not in vars(event)
    assert order.revenue == 200


def test_multiple_payments_do_not_invent_a_single_exchange_rate(monkeypatch):
    payments = [{"PaymentIntentId": f"pi_{index}", "TicketPartnerOrderId": 10,
                 "Currency": "cad", "Status": "succeeded", "ExchangeRate": rate,
                 "ProcessingFee": Decimal("2"), "ProcessingFeeCurrency": "usd",
                 "Insurance": None} for index, rate in enumerate([Decimal("0.75"), Decimal("0.76")])]
    results = iter([payments, []])
    monkeypatch.setattr(financial, "db_query_all", lambda *_: next(results))
    order = SimpleNamespace(ticket_partner_order_id=10)
    financial.StripeFinancialService().enrich_order_fields([SimpleNamespace(orders=[order])])
    assert order.exchange_rate is None
    assert order.stripe_processing_fee == "4"
    assert order.insurance is None


def test_no_mapped_orders_produces_nulls_without_database_queries(monkeypatch):
    monkeypatch.setattr(financial, "db_query_all", lambda *_: (_ for _ in ()).throw(
        AssertionError("Unexpected query")))
    order = SimpleNamespace(ticket_partner_order_id=None, exchange_rate=12)
    financial.StripeFinancialService().enrich_order_fields([SimpleNamespace(orders=[order])])
    assert order.exchange_rate is None
    assert order.other_fees == []
