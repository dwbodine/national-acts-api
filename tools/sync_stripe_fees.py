"""Create, poll, and import daily Stripe fee reports through the API."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import requests

LOGGER = logging.getLogger(__name__)


def save_state(path, state):
    """Atomically save report IDs before polling or advancing to another date."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        os.chmod(temporary, 0o600)
        json.dump(state, output, indent=2, sort_keys=True)
    temporary.replace(path)


def sync_reports(session, base_url, state_path, days=7, poll_seconds=30, wait_seconds=600):
    """Refresh complete UTC days once per run date and resume outstanding reports."""
    today = datetime.now(timezone.utc).date()
    run_date = today.isoformat()
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    jobs = state.setdefault("jobs", {})
    dates = {(today - timedelta(days=offset)).isoformat() for offset in range(1, days + 1)}
    # Include unfinished reports even if their dates have aged out of the window.
    dates.update(day for day, job in jobs.items() if job.get("status") == "pending")
    for day in sorted(dates):
        job = jobs.get(day, {})
        if job.get("completed_on") == run_date:
            continue
        if job.get("status") != "pending":
            response = session.post(
                f"{base_url}/stripe/fees/report", json={"start_date": day}, timeout=60
            )
            if response.status_code == 409:
                LOGGER.info("Deferring %s: Stripe fee data is not available yet", day)
                continue
            response.raise_for_status()
            report = response.json()
            report_id = report.get("id")
            if not isinstance(report_id, str) or not report_id.startswith("frr_"):
                raise ValueError("Report creation did not return a report ID")
            job = {"report_id": report_id, "status": "pending"}
            jobs[day] = job
            save_state(state_path, state)
            LOGGER.info("Created %s for %s", report_id, day)
        else:
            LOGGER.info("Resuming %s for %s", job["report_id"], day)
        deadline = time.monotonic() + wait_seconds
        while True:
            response = session.get(
                f"{base_url}/stripe/fees/report/{job['report_id']}", timeout=300
            )
            response.raise_for_status()
            report = response.json()
            if report.get("status") == "succeeded":
                count = report.get("rows_upserted")
                if not isinstance(count, int) or count < 0:
                    raise ValueError("Report endpoint did not confirm database import")
                job.update(status="succeeded", completed_on=run_date, rows_upserted=count)
                save_state(state_path, state)
                LOGGER.info("Imported %s: %s rows (%s)", day, count, job["report_id"])
                break
            if report.get("status") == "failed":
                job["status"] = "failed"
                save_state(state_path, state)
                raise RuntimeError(f"Report failed for {day}: {job['report_id']}")
            if report.get("status") != "pending":
                raise ValueError("Unexpected report status")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Report still pending for {day}; rerun to resume")
            time.sleep(min(poll_seconds, remaining))


def main():
    """Run inside the deployed API container using its environment and mounted tmp."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--state-file", type=Path, default=Path("/app/tmp/stripe-fees/state.json"))
    parser.add_argument("--env-file", default="/app/.env")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--wait-seconds", type=int, default=600)
    args = parser.parse_args()
    if min(args.days, args.poll_seconds, args.wait_seconds) < 1:
        parser.error("days, poll-seconds, and wait-seconds must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(args.env_file, override=False)
    api_key = os.getenv("STRIPE_API_PUBLIC_KEY")
    if not api_key:
        parser.error("STRIPE_API_PUBLIC_KEY is not configured")
    try:
        with requests.Session() as session:
            session.headers["x-api-key"] = api_key
            sync_reports(
                session, args.base_url.rstrip("/"), args.state_file,
                args.days, args.poll_seconds, args.wait_seconds,
            )
    except (requests.RequestException, ValueError, OSError, RuntimeError):
        LOGGER.exception("Fee sync stopped; saved reports will be resumed on the next run")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
