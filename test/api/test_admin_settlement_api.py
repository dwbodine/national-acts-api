"""Internal financial reporting must not be exposed to clients."""

from types import SimpleNamespace

import pytest
from flask_jwt_extended import get_jwt

from api import dashboard_api, event_api
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
