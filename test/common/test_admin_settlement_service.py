"""Order-level accounting examples and incomplete data coverage."""

from decimal import Decimal
import pytest
import stripe

from common.admin_settlement_service import reconcile_order, summarize
from common.models.stripe import StripeTransaction, TICKETSOCKET_INSURANCE_APPLICATION
from common import stripe_service, admin_settlement_service


def payment(application=None):
    """Build expanded SDK resources rather than dictionary-only substitutes."""
    app_fee = 2680 if application else 0
    processor = 1129 if application else 1476
    details = [{"type": "stripe_fee", "amount": processor}]
    if application:
        details.append(
            {"type": "application_fee", "amount": app_fee, "application": application}
        )
    intent = stripe.PaymentIntent.construct_from(
        {
            "id": "pi_example",
            "metadata": {},
            "description": "",
            "created": 100,
            "amount": 25780 if application else 24136,
            "currency": "usd",
            "application_fee_amount": app_fee,
            "payment_method_types": ["card", "klarna"],
            "latest_charge": {
                "payment_method_details": {"type": "card" if application else "klarna"},
                "balance_transaction": {
                    "fee": processor + app_fee,
                    "currency": "usd",
                    "exchange_rate": None,
                    "fee_details": details,
                },
            },
        },
        None,
    )
    return StripeTransaction("42", "succeeded", intent)


def order(checkout="10.86", currency="usd"):
    """A TicketSocket order with separate sales and checkout amounts."""
    return {
        "TicketPartnerOrderId": 1,
        "OrderId": 70854,
        "EventId": 3,
        "PurchaseDate": "2026-09-28",
        "Currency": currency,
        "TicketSales": 200,
        "ServiceFees": "30.50",
        "CustomerProcessingFee": checkout,
    }


def stored(transaction):
    """Represent the persisted fields used by reconciliation."""
    return {
        "Status": "succeeded",
        "Currency": "usd",
        "PaymentIntentId": "pi_example",
        "ProcessingFee": transaction.processing_fee,
        "ProcessingFeeCurrency": transaction.processing_fee_currency,
        "InsuranceVerified": transaction.insurance_verified,
        "Insurance": transaction.insurance,
        "ApplicationFee": transaction.application_fee,
        "PaymentMethod": transaction.payment_method,
    }


def test_klarna_checkout_shortfall_is_once_per_order():
    transaction = payment()
    result = reconcile_order(order(), [stored(transaction)])
    assert transaction.payment_method == "klarna"
    assert Decimal(result["actualProcessingFee"]) == Decimal("14.76")
    assert Decimal(result["processingShortfall"]) == Decimal("3.90")
    assert Decimal(result["serviceFees"]) == Decimal("30.50")
    assert Decimal(result["insurancePremium"]) == 0


def test_confirmed_insurance_is_separate_from_processor_cost():
    transaction = payment(TICKETSOCKET_INSURANCE_APPLICATION)
    result = reconcile_order(order("0"), [stored(transaction)])
    assert Decimal(result["actualProcessingFee"]) == Decimal("11.29")
    assert Decimal(result["insurancePremium"]) == Decimal("26.80")


def test_other_application_fees_are_not_assumed_to_be_insurance():
    result = reconcile_order(order(), [stored(payment("ca_other"))])
    assert result["insurancePremium"] is None
    assert Decimal(result["applicationFee"]) == Decimal("26.80")


@pytest.mark.parametrize(
    "payments", [[], [{**stored(payment()), "ProcessingFeeCurrency": "cad"}]]
)
def test_unknown_and_cross_currency_costs_are_not_zero(payments):
    result = reconcile_order(order(None), payments)
    assert result["actualProcessingFee"] is None
    assert result["processingShortfall"] is None
    summary = summarize([result])["usd"]
    assert summary["missingCustomerFee"] == 1
    assert summary["missingStripeCost"] == 1
    assert summary["comparedOrders"] == 0


def test_explicit_refresh_only_updates_financial_fields(monkeypatch):
    writes = []
    monkeypatch.setattr(
        stripe_service,
        "db_query_all",
        lambda *_: [
            {"TicketPartnerOrderId": 1, "EventId": 77, "OrderId": 42, "Id": 80}
        ],
    )
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append((sql, data))
    )
    service = stripe_service.StripeService()
    service._upsert_transaction(payment())
    assert (
        writes[-1][0].split("ON DUPLICATE KEY UPDATE")[1].strip()
        == "PaymentIntentId=PaymentIntentId"
    )
    service.refresh_financials = True
    service._upsert_transaction(payment(TICKETSOCKET_INSURANCE_APPLICATION))
    updates = writes[-1][0].split("ON DUPLICATE KEY UPDATE")[1]
    assert "InsuranceVerified=VALUES(InsuranceVerified)" in updates
    assert "Total=" not in updates
    assert "TicketPartnerOrderId=" not in updates
    assert writes[-1][1]["insurance_verified"] == 1


def test_report_uses_two_bulk_queries_and_does_not_multiply_ticket_rows(monkeypatch):
    calls = []

    def query(sql, data):
        calls.append((sql, data))
        if len(calls) == 1:
            return [order()]
        return [{**stored(payment()), "TicketPartnerOrderId": 1}]

    monkeypatch.setattr(admin_settlement_service, "db_query_all", query)
    report = admin_settlement_service.AdminSettlementService().get_report(1, 2)
    assert len(calls) == 2
    assert report["totalOrders"] == 1
    assert Decimal(report["totalsByCurrency"]["usd"]["processingShortfall"]) == Decimal(
        "3.90"
    )
    assert "GROUP BY TicketSocketOrderId" in calls[0][0]
