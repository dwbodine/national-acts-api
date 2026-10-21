"""Fee orchestration resumes report IDs and requires confirmed database imports."""

import json
from types import SimpleNamespace

import pytest
import requests

from tools.sync_stripe_fees import sync_reports


def response(data):
    return SimpleNamespace(
        status_code=200, raise_for_status=lambda: None, json=lambda: data
    )


def test_daily_sync_creates_imports_and_skips_completed_dates(workspace_tmp_path):
    state = workspace_tmp_path / "state.json"
    creates = []
    gets = []
    session = SimpleNamespace(
        post=lambda url, **kwargs: creates.append(kwargs)
        or response({"id": "frr_test"}),
        get=lambda url, **kwargs: gets.append(url)
        or response({"status": "succeeded", "rows_upserted": 12}),
    )
    sync_reports(session, "http://api", state, days=1)
    sync_reports(session, "http://api", state, days=1)
    assert len(creates) == 1
    assert len(gets) == 1
    job = next(iter(json.loads(state.read_text())["jobs"].values()))
    assert job["status"] == "succeeded"
    assert job["rows_upserted"] == 12


def test_network_failure_resumes_existing_report(workspace_tmp_path):
    state = workspace_tmp_path / "state.json"
    creates = []

    def fail(url, **kwargs):
        raise requests.Timeout("test timeout")

    session = SimpleNamespace(
        post=lambda url, **kwargs: creates.append(url) or response({"id": "frr_saved"}),
        get=fail,
    )
    with pytest.raises(requests.Timeout):
        sync_reports(session, "http://api", state, days=1)
    gets = []
    session.get = lambda url, **kwargs: gets.append(url) or response(
        {"status": "succeeded", "rows_upserted": 0}
    )
    sync_reports(session, "http://api", state, days=1)
    assert len(creates) == 1
    assert gets == ["http://api/stripe/fees/report/frr_saved"]


def test_unimported_success_does_not_advance_checkpoint(workspace_tmp_path):
    state = workspace_tmp_path / "state.json"
    session = SimpleNamespace(
        post=lambda url, **kwargs: response({"id": "frr_saved"}),
        get=lambda url, **kwargs: response({"status": "succeeded"}),
    )
    with pytest.raises(ValueError, match="confirm"):
        sync_reports(session, "http://api", state, days=1)
    job = next(iter(json.loads(state.read_text())["jobs"].values()))
    assert job["status"] == "pending"


def test_unavailable_days_are_deferred_without_checkpoint(workspace_tmp_path):
    """Recent dates outside Stripe's reporting availability can be tried tomorrow."""
    state = workspace_tmp_path / "state.json"
    gets = []
    session = SimpleNamespace(
        post=lambda url, **kwargs: SimpleNamespace(status_code=409),
        get=lambda url, **kwargs: gets.append(url),
    )
    sync_reports(session, "http://api", state, days=1)
    assert gets == []
    assert not state.exists()
