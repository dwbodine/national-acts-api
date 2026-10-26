"""Internal financial reporting must not be exposed to clients."""

from types import SimpleNamespace

import pytest
from flask_jwt_extended import get_jwt

from api import dashboard_api, event_api, stripe_api
from common import common_api


@pytest.fixture(autouse=True)
def database_user(monkeypatch):
    """Authorization uses the database user, never a client-supplied role claim."""
    monkeypatch.setattr(common_api.UserService, "get_user_by_user_name",
                        lambda *_: SimpleNamespace(is_admin=get_jwt()["role"] == "admin"))


def test_client_cannot_read_settlements(client, auth_headers):
    response = client.get("/dashboard/settlements?start=1&end=2", headers=auth_headers(role="client"))
    assert response.status_code == 401


def test_admin_settlement_event_scope(monkeypatch, client, auth_headers):
    calls = []
    monkeypatch.setattr(dashboard_api, "AdminSettlementService", lambda: SimpleNamespace(
        get_report=lambda *args: calls.append(args) or {"orders": []}))
    response = client.get("/dashboard/settlements?start=1&end=2&sellerId=4&eventIds=10,11",
                          headers=auth_headers())
    assert response.status_code == 200
    assert calls == [(1, 2, 4, [10, 11])]


@pytest.mark.parametrize("query", ["", "start=-1&end=2", "start=3&end=2", "start=1&end=2&eventIds=no"])
def test_invalid_settlement_scope_is_rejected(client, auth_headers, query):
    assert client.get("/dashboard/settlements?" + query, headers=auth_headers()).status_code == 400


def test_client_cannot_opt_into_raw_stripe_financials(monkeypatch, client, auth_headers):
    calls = []
    monkeypatch.setattr(event_api, "EventService", lambda: SimpleNamespace(
        get_events_and_orders=lambda **kwargs: calls.append(kwargs) or []))
    response = client.get("/events/getEventsAndOrders?includeStripeFinancials=1",
                          headers=auth_headers(role="client"))
    assert response.status_code == 200
    assert calls[0]["include_stripe_financials"] is False


def test_missing_payments_is_admin_only(monkeypatch, client, auth_headers):
    monkeypatch.setattr(stripe_api, "StripeReconciliationService",
                        lambda: pytest.fail("Unauthorized request accessed financial data"))
    url = "/stripe/payment-intents/missing?start_date=2026-01-01&end_date=2027-01-01"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_headers(role="client")).status_code == 401


@pytest.mark.parametrize("query", ["", "start_date=2026-01-01&end_date=2026-01-01",
    "start_date=bad&end_date=2027-01-01",
    "start_date=2026-01-01&end_date=2027-01-01&ticket_socket_id=0",
    "start_date=2026-01-01&end_date=2027-01-01&limit=1001",
    "start_date=2026-01-01&end_date=2027-01-01&offset=-1",
    "start_date=2026-01-01&end_date=2027-01-01&format=html"])
def test_missing_payments_validates_filters(client, auth_headers, query):
    assert client.get("/stripe/payment-intents/missing?" + query,
                      headers=auth_headers()).status_code == 400


@pytest.mark.parametrize("output_format", ["json", "csv"])
def test_missing_payments_exports_and_paginates(monkeypatch, client, auth_headers, output_format):
    calls = []

    def report(*args):
        calls.append(args)
        return {"missingPaymentIntents": 1, "orders": [{"NativeOrderId": 42547,
                "NativeEventId": 123, "CustomerName": "=UNTRUSTED()"}]}

    monkeypatch.setattr(stripe_api, "StripeReconciliationService", lambda: SimpleNamespace(
        get_missing_payments=report))
    response = client.get("/stripe/payment-intents/missing?start_date=2026-01-01"
                          "&end_date=2027-01-01&ticket_socket_id=4&limit=25&offset=10&format="
                          + output_format, headers=auth_headers())
    assert response.status_code == 200
    assert calls[0][0].isoformat() == "2026-01-01"
    assert calls[0][1].isoformat() == "2027-01-01"
    if output_format == "json":
        assert calls[0][2:] == (4, 25, 10)
        assert response.get_json()["missingPaymentIntents"] == 1
    else:
        assert calls[0][2:] == (4, None, 0)
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        assert "42547" in response.text
        assert "'=UNTRUSTED()" in response.text
