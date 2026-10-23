"""Stripe cash summaries stay independent of ticket accounting and child fanout."""

from decimal import Decimal
from types import SimpleNamespace
import json

from common import stripe_financial_service as financial
from common.utility import convert_to_json


def test_bulk_financials_sum_children_without_multiplication(monkeypatch):
    payments = [
        {"PaymentIntentId": "pi_a", "TicketPartnerOrderId": 10,
         "Total": Decimal("100"), "Currency": "usd", "Status": "succeeded"},
        {"PaymentIntentId": "pi_b", "TicketPartnerOrderId": 10,
         "Total": Decimal("50"), "Currency": "usd", "Status": "succeeded"},
    ]
    refunds = [
        {"PaymentIntentId": "pi_a", "Amount": Decimal("10"), "Currency": "usd", "Status": "succeeded"},
        {"PaymentIntentId": "pi_a", "Amount": Decimal("5"), "Currency": "usd", "Status": "succeeded"},
        {"PaymentIntentId": "pi_b", "Amount": Decimal("40"), "Currency": "usd", "Status": "pending"},
    ]
    fees = [
        {"IncurredBy": "pi_a", "Currency": "usd", "Amount": Decimal("0.050001"), "Tax": 0},
        {"IncurredBy": "pi_a", "Currency": "usd", "Amount": Decimal("1"), "Tax": Decimal("0.1")},
    ]
    calls = []
    results = iter([payments, refunds, fees])
    monkeypatch.setattr(financial, "db_query_all", lambda sql, data: calls.append(sql) or next(results))
    order = SimpleNamespace(ticket_partner_order_id=10, revenue=200, num_tickets=4)
    other = SimpleNamespace(ticket_partner_order_id=11)
    event = SimpleNamespace(orders=[order, other])
    financial.StripeFinancialService().enrich_events([event])
    assert len(calls) == 3
    assert order.stripe_gross == "150"
    assert order.stripe_refunded == "15"
    assert order.stripe_reported_fees == "1.150001"
    assert order.stripe_net == "133.849999"
    assert event.stripe_net == order.stripe_net
    assert len(order.stripe_refunds) == 3
    assert order.revenue == 200 and order.num_tickets == 4
    assert other.stripe_payments == []
    assert json.loads(convert_to_json(event))["stripeNet"] == "133.849999"


def test_currency_mismatch_leaves_net_unset():
    target = SimpleNamespace()
    financial.attach_financials(target, [
        {"PaymentIntentId": "pi_cad", "Total": 100, "Currency": "cad", "Status": "succeeded"},
    ], [], [{"IncurredBy": "pi_cad", "Amount": 3, "Tax": 0, "Currency": "usd"}])
    assert target.stripe_currency_mismatch
    assert target.stripe_net is None
    assert target.stripe_totals_by_currency["cad"]["gross"] == "100"
    assert target.stripe_totals_by_currency["usd"]["reported_fees"] == "3"
    assert all(bucket["net"] is None for bucket in target.stripe_totals_by_currency.values())


def test_unscoped_left_joins_preserve_null_mappings(monkeypatch):
    orphan = {"PaymentIntentId": "pi_orphan", "TicketPartnerOrderId": None}
    results = iter([[orphan], [], []])
    calls = []
    monkeypatch.setattr(financial, "db_query_all", lambda sql, data: calls.append(sql) or next(results))
    payments, _, _ = financial.StripeFinancialService().get_financials()
    assert payments[0]["TicketPartnerOrderId"] is None
    assert all("LEFT JOIN" in sql for sql in calls)
    assert not any("IS NOT NULL" in sql for sql in calls)


def test_no_orders_does_not_query_database(monkeypatch):
    def unexpected(*args):
        raise AssertionError("No financial queries should run")
    monkeypatch.setattr(financial, "db_query_all", unexpected)
    event = SimpleNamespace(orders=[])
    financial.StripeFinancialService().enrich_events([event])
    assert event.stripe_totals_by_currency == {}
