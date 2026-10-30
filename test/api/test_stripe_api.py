"""Stripe fee report authentication, input validation, and API parameters."""

from types import SimpleNamespace
from datetime import datetime, timezone

from flask import Flask
import pytest
import stripe
import requests

from api.stripe_api import stripe_api
from common.stripe_service import StripeService
from common import stripe_service


@pytest.fixture
def report_client(monkeypatch):
    """Create an isolated route client with fake credentials."""
    monkeypatch.setenv("STRIPE_API_PUBLIC_KEY", "test_endpoint_key")
    monkeypatch.setenv("STRIPE_API_SECRET_KEY", "sk_test_example")
    monkeypatch.setattr(stripe_service, "db_update", lambda sql, data: None)
    app = Flask(__name__)
    app.register_blueprint(stripe_api)
    app.config["TESTING"] = True
    return app.test_client()


def test_report_creates_exact_utc_day(report_client, monkeypatch):
    """Use the SDK report service and return the pending report to the caller."""
    calls = []
    report = stripe.StripeObject.construct_from(
        {"id": "frr_test", "status": "pending", "result": None}, None
    )
    client = SimpleNamespace(
        v1=SimpleNamespace(
            reporting=SimpleNamespace(
                report_types=SimpleNamespace(
                    retrieve=lambda report_type: SimpleNamespace(
                        data_available_end=int(
                            datetime(2026, 10, 20, tzinfo=timezone.utc).timestamp()
                        )
                    )
                ),
                report_runs=SimpleNamespace(
                    create=lambda params: calls.append(params) or report
                ),
            )
        )
    )
    client.v1.accounts = SimpleNamespace(retrieve_current=lambda: SimpleNamespace(id="acct_test"))
    monkeypatch.setattr(stripe, "StripeClient", lambda api_key: client)
    response = report_client.post(
        "/stripe/fees/report",
        json={"start_date": "2026-10-01"},
        headers={"x-api-key": "test_endpoint_key"},
    )
    assert response.status_code == 202
    assert response.get_json()["id"] == "frr_test"
    expected = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
    assert calls == [
        {
            "report_type": "all_fees.incurred_at.itemized.2",
            "parameters": {
                "interval_start": expected,
                "interval_end": expected + 86400,
            },
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"start_date": "2026-02-30"},
        {"start_date": "2026-10-01T01:00:00Z"},
    ],
)
def test_report_rejects_invalid_dates(report_client, payload):
    """Reject missing or non-calendar dates before calling Stripe."""
    response = report_client.post(
        "/stripe/fees/report", json=payload, headers={"x-api-key": "test_endpoint_key"}
    )
    assert response.status_code == 400


def test_report_requires_authentication(report_client):
    """An unauthenticated caller cannot start reports."""
    assert report_client.post("/stripe/fees/report").status_code == 401


def test_report_defers_days_beyond_stripe_availability(report_client, monkeypatch):
    """Reject unavailable intervals before creating a report run."""
    client = SimpleNamespace(
        v1=SimpleNamespace(
            reporting=SimpleNamespace(
                report_types=SimpleNamespace(
                    retrieve=lambda report_type: SimpleNamespace(data_available_end=0)
                ),
            )
        )
    )
    client.v1.accounts = SimpleNamespace(retrieve_current=lambda: SimpleNamespace(id="acct_test"))
    monkeypatch.setattr(stripe, "StripeClient", lambda api_key: client)
    response = report_client.post(
        "/stripe/fees/report",
        json={"start_date": "2026-10-19"},
        headers={"x-api-key": "test_endpoint_key"},
    )
    assert response.status_code == 409
    assert response.get_json()["available_until"] == 0


def test_report_returns_failure_status(report_client, monkeypatch):
    """Stripe failures must not look like accepted report requests."""

    def fail(self, start):
        raise stripe.APIError("unavailable")

    monkeypatch.setattr(StripeService, "create_fee_report", fail)
    response = report_client.post(
        "/stripe/fees/report",
        json={"start_date": "2026-10-01"},
        headers={"x-api-key": "test_endpoint_key"},
    )
    assert response.status_code == 502


@pytest.mark.parametrize("status", ["pending", "succeeded", "failed"])
def test_get_report_returns_status_and_result(report_client, monkeypatch, status):
    """Retrieve the actual run without creating another report."""
    calls = []
    result = {"id": "file_test"} if status == "succeeded" else None
    parameters = {"interval_start": 1790812800, "interval_end": 1790899200}
    report = stripe.StripeObject.construct_from(
        {"id": "frr_test", "status": status, "result": result, "parameters": parameters}, None
    )
    client = SimpleNamespace(
        v1=SimpleNamespace(
            reporting=SimpleNamespace(
                report_runs=SimpleNamespace(
                    retrieve=lambda report_id: calls.append(report_id) or report
                )
            )
        )
    )
    client.v1.accounts = SimpleNamespace(retrieve_current=lambda: SimpleNamespace(id="acct_test"))
    monkeypatch.setattr(stripe, "StripeClient", lambda api_key: client)
    downloads = []
    writes = []
    monkeypatch.setattr(
        stripe_service, "db_insert", lambda sql, data: writes.append(data)
    )

    class Download:
        """Fake Stripe CSV response."""

        status_code = 200
        content = (
            ",".join(stripe_service.FEE_COLUMNS)
            + "\n"
            + ",".join(
                {
                    "incurred_by": "pi_test",
                    "incurred_by_type": "payment_intent",
                    "amount": "0.05",
                    "currency": "usd",
                }.get(key, "")
                for key in stripe_service.FEE_COLUMNS
            )
            + "\n"
        ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        requests,
        "get",
        lambda url, **kwargs: downloads.append((url, kwargs)) or Download(),
    )
    response = report_client.get(
        "/stripe/fees/report/frr_test", headers={"x-api-key": "test_endpoint_key"}
    )
    assert response.status_code == 200
    if status == "succeeded":
        assert response.get_json()["rows_upserted"] == 1
        assert response.get_json()["status"] == "succeeded"
        assert len(writes) == 1
        assert writes[0]["IncurredBy"] == "pi_test"
        assert downloads == [
            (
                "https://files.stripe.com/v1/files/file_test/contents",
                {
                    "auth": ("sk_test_example", ""),
                    "timeout": 60,
                    "allow_redirects": False,
                },
            )
        ]
    else:
        assert response.get_json() == {
            "id": "frr_test",
            "status": status,
            "result": result,
            "parameters": parameters,
        }
        assert downloads == []
        assert writes == []
    assert calls == ["frr_test"]


def test_get_report_requires_authentication(report_client):
    """Protect report results just like report creation."""
    assert report_client.get("/stripe/fees/report/frr_test").status_code == 401


@pytest.mark.parametrize("missing", [True, False])
def test_get_report_handles_stripe_errors(report_client, monkeypatch, missing):
    """Distinguish nonexistent reports from upstream service failures."""

    def fail(self, report_id):
        if missing:
            raise stripe.InvalidRequestError(
                "No such report", "id", code="resource_missing", http_status=404
            )
        raise stripe.APIError("unavailable")

    monkeypatch.setattr(StripeService, "get_fee_report", fail)
    response = report_client.get(
        "/stripe/fees/report/frr_test", headers={"x-api-key": "test_endpoint_key"}
    )
    assert response.status_code == (404 if missing else 502)


def test_get_report_requires_secret_key(report_client, monkeypatch):
    """Missing server configuration returns a clear service error."""
    monkeypatch.delenv("STRIPE_API_SECRET_KEY")
    response = report_client.get(
        "/stripe/fees/report/frr_test", headers={"x-api-key": "test_endpoint_key"}
    )
    assert response.status_code == 503
