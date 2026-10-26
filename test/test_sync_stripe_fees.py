"""Fee orchestration resumes report IDs and requires confirmed database imports."""

import json
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace
import sys

import pytest
import requests

from tools.sync_stripe_fees import sync_reports
from tools import sync_stripe_fees as runner


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


@pytest.fixture
def utc_clock(monkeypatch):
    """Advance the UTC date without waiting or depending on the execution date."""
    clock = SimpleNamespace(now=datetime(2026, 10, 26, 12, tzinfo=timezone.utc))

    class Clock:
        @staticmethod
        def now(_timezone):
            return clock.now

    monkeypatch.setattr(runner, "datetime", Clock)
    return clock


def successful_session():
    calls = {"post": [], "get": []}

    def post(_url, **kwargs):
        calls["post"].append(kwargs["json"]["start_date"])
        return response({"id": f"frr_{len(calls['post'])}"})

    def get(url, **_kwargs):
        calls["get"].append(url)
        return response({"status": "succeeded", "rows_upserted": 0})

    return SimpleNamespace(post=post, get=get), calls


def test_fixed_range_completion_persists_across_utc_days(workspace_tmp_path, utc_clock):
    path = workspace_tmp_path / "backfill.json"
    session, calls = successful_session()
    options = {"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 3)}
    sync_reports(session, "http://api", path, **options)
    assert calls["post"] == ["2026-01-01", "2026-01-02"]
    utc_clock.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    sync_reports(session, "http://api", path, **options)
    assert calls["post"] == ["2026-01-01", "2026-01-02"]
    assert len(calls["get"]) == 2
    state = json.loads(path.read_text())
    assert state["mode"] == "backfill"
    assert state["start_date"] == "2026-01-01"
    assert state["end_date"] == "2026-01-03"
    assert all(job["status"] == "succeeded" for job in state["jobs"].values())


def test_rolling_sync_still_refreshes_completed_days_on_a_later_day(workspace_tmp_path, utc_clock):
    path = workspace_tmp_path / "rolling.json"
    session, calls = successful_session()
    sync_reports(session, "http://api", path, days=1)
    utc_clock.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    sync_reports(session, "http://api", path, days=2)
    assert calls["post"] == ["2026-10-25", "2026-10-25", "2026-10-26"]


def test_fixed_resume_keeps_completed_days_and_reuses_pending_report(workspace_tmp_path, utc_clock):
    path = workspace_tmp_path / "backfill.json"
    session, calls = successful_session()
    successful_get = session.get

    def fail_second(url, **kwargs):
        if url.endswith("frr_2"):
            raise requests.Timeout("Interrupted")
        return successful_get(url, **kwargs)

    session.get = fail_second
    options = {"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 4)}
    with pytest.raises(requests.Timeout):
        sync_reports(session, "http://api", path, **options)
    state = json.loads(path.read_text())
    assert state["jobs"]["2026-01-01"]["status"] == "succeeded"
    assert state["jobs"]["2026-01-02"]["report_id"] == "frr_2"
    assert state["jobs"]["2026-01-02"]["status"] == "pending"
    session.get = successful_get
    utc_clock.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    sync_reports(session, "http://api", path, **options)
    assert calls["post"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert calls["get"] == ["http://api/stripe/fees/report/frr_1",
                             "http://api/stripe/fees/report/frr_2",
                             "http://api/stripe/fees/report/frr_3"]


def test_fixed_unavailable_day_remains_unfinished_and_is_retried(workspace_tmp_path, utc_clock):
    path = workspace_tmp_path / "backfill.json"
    session, calls = successful_session()
    successful_post = session.post
    session.post = lambda *_args, **_kwargs: SimpleNamespace(status_code=409)
    options = {"start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)}
    sync_reports(session, "http://api", path, **options)
    assert json.loads(path.read_text())["jobs"] == {}
    assert calls["get"] == []
    session.post = successful_post
    utc_clock.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    sync_reports(session, "http://api", path, **options)
    assert calls["post"] == ["2026-01-01"]


@pytest.mark.parametrize("options", [
    {"start_date": date(2026, 1, 1)}, {"end_date": date(2026, 1, 3)},
    {"start_date": date(2026, 1, 2), "end_date": date(2026, 1, 2)},
    {"start_date": date(2026, 1, 3), "end_date": date(2026, 1, 2)},
    {"start_date": date(2026, 1, 1), "end_date": date(2026, 10, 27)},
])
def test_invalid_fixed_ranges_make_no_requests_or_checkpoint(workspace_tmp_path, utc_clock, options):
    path = workspace_tmp_path / "state.json"
    session, calls = successful_session()
    with pytest.raises(ValueError):
        sync_reports(session, "http://api", path, **options)
    assert calls == {"post": [], "get": []}
    assert not path.exists()


def test_checkpoint_cannot_change_range_or_be_reused_for_rolling(workspace_tmp_path, utc_clock):
    path = workspace_tmp_path / "state.json"
    session, calls = successful_session()
    sync_reports(session, "http://api", path,
                 start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    saved = path.read_text()
    with pytest.raises(ValueError, match="date range"):
        sync_reports(session, "http://api", path,
                     start_date=date(2026, 1, 1), end_date=date(2026, 1, 3))
    with pytest.raises(ValueError, match="separate state file"):
        sync_reports(session, "http://api", path)
    assert path.read_text() == saved
    assert len(calls["post"]) == 1


def test_backfill_rejects_existing_rolling_checkpoint(workspace_tmp_path, utc_clock):
    path = workspace_tmp_path / "state.json"
    session, calls = successful_session()
    sync_reports(session, "http://api", path, days=1)
    saved = path.read_text()
    with pytest.raises(ValueError, match="separate state file"):
        sync_reports(session, "http://api", path,
                     start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    assert path.read_text() == saved
    assert len(calls["post"]) == 1


@pytest.mark.parametrize("arguments", [
    ["--start-date", "2026-01-01"],
    ["--start-date", "2026-01-01", "--end-date", "2026-01-02", "--days", "7"],
    ["--start-date", "20260101", "--end-date", "2026-01-02"],
])
def test_cli_rejects_incompatible_options_before_http(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["sync_stripe_fees", *arguments])
    monkeypatch.setattr(runner.requests, "Session", lambda: pytest.fail("Unexpected HTTP session"))
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


@pytest.mark.parametrize("arguments, expected_path, expected_start", [
    ([], "/app/tmp/stripe-fees/state.json", None),
    (["--start-date", "2026-01-01", "--end-date", "2026-01-03"],
     "/app/tmp/stripe-fees/backfill-2026-01-01-2026-01-03.json", date(2026, 1, 1)),
    (["--start-date", "2026-01-01", "--end-date", "2026-01-03", "--state-file", "custom.json"],
     "custom.json", date(2026, 1, 1)),
])
def test_cli_keeps_backfill_checkpoint_separate_by_default(monkeypatch, utc_clock,
                                                        arguments, expected_path, expected_start):
    calls = []
    monkeypatch.setattr(sys, "argv", ["sync_stripe_fees", *arguments])
    monkeypatch.setenv("STRIPE_API_PUBLIC_KEY", "test_key")
    monkeypatch.setattr(runner, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner.requests, "Session",
                        lambda: nullcontext(SimpleNamespace(headers={})))
    monkeypatch.setattr(runner, "sync_reports", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert runner.main() == 0
    assert calls[0][0][2].as_posix() == expected_path
    assert calls[0][1]["start_date"] == expected_start
