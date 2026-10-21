"""Historical Stripe imports checkpoint complete windows and replay failed windows."""

import json
from types import SimpleNamespace

import pytest

from tools import backfill_stripe_transactions as runner


def test_chunk_limit_and_resume_use_contiguous_exclusive_windows(workspace_tmp_path):
    path = workspace_tmp_path / "history.json"
    start = runner.midnight("2023-05-23")
    end = start + 2 * 86400 + 123
    calls = []
    service = SimpleNamespace(get_transactions=lambda **kw: calls.append(kw) or [])
    runner.backfill(service, path, start, end, max_chunks=1)
    assert json.loads(path.read_text())["next_start"] == start + 86400
    # Omitting end on resume keeps the original cutoff.
    state = runner.backfill(service, path, start)
    assert calls == [
        {"start": start, "end": start + 86400},
        {"start": start + 86400, "end": start + 2 * 86400},
        {"start": start + 2 * 86400, "end": end},
    ]
    assert state["next_start"] == end
    runner.backfill(service, path, start)
    assert len(calls) == 3


def test_failure_does_not_advance_checkpoint_and_can_use_smaller_chunks(
    workspace_tmp_path, monkeypatch
):
    path = workspace_tmp_path / "history.json"
    start = runner.midnight("2023-05-23")
    calls = []
    monkeypatch.setattr(runner.clock, "sleep", lambda seconds: None)
    service = SimpleNamespace(get_transactions=lambda **kw: calls.append(kw))
    with pytest.raises(RuntimeError, match="failed"):
        runner.backfill(service, path, start, start + 86400)
    assert len(calls) == 3
    assert json.loads(path.read_text())["next_start"] == start
    service.get_transactions = lambda **kw: calls.append(kw) or []
    runner.backfill(service, path, start, chunk_hours=1, max_chunks=1)
    assert calls[-1] == {"start": start, "end": start + 3600}


def test_changed_start_or_end_is_rejected(workspace_tmp_path):
    path = workspace_tmp_path / "history.json"
    start = runner.midnight("2023-05-23")
    service = SimpleNamespace(get_transactions=lambda **kw: [])
    runner.backfill(service, path, start, start + 86400)
    with pytest.raises(ValueError, match="start"):
        runner.backfill(service, path, start + 86400)
    with pytest.raises(ValueError, match="cutoff"):
        runner.backfill(service, path, start, start + 172800)
