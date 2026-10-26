"""Create, poll, and import daily Stripe fee reports through the API."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import time

from dotenv import load_dotenv
import requests

LOGGER = logging.getLogger(__name__)


def parse_date(value):
    """Accept an exact UTC calendar date for fixed backfill boundaries."""
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD")
    return parsed


def save_state(path, state):
    """Atomically save report IDs before polling or advancing to another date."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        os.chmod(temporary, 0o600)
        json.dump(state, output, indent=2, sort_keys=True)
    temporary.replace(path)


def sync_reports(
    session, base_url, state_path, days=7, poll_seconds=30, wait_seconds=600,
    *, start_date=None, end_date=None,
):
    """Refresh rolling days, or permanently checkpoint a fixed [start, end) backfill."""
    today = datetime.now(timezone.utc).date()
    run_date = today.isoformat()
    fixed = start_date is not None or end_date is not None
    if min(days, poll_seconds, wait_seconds) < 1:
        raise ValueError("days, poll_seconds, and wait_seconds must be positive")
    if fixed and (start_date is None or end_date is None):
        raise ValueError("Both start_date and end_date are required")
    if fixed and (start_date >= end_date or end_date > today):
        raise ValueError("Use start_date < end_date <= today UTC (end exclusive)")
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {}
    )
    if not isinstance(state, dict) or not isinstance(state.get("jobs", {}), dict):
        raise ValueError("Invalid fee-sync checkpoint")
    if state.get("mode") not in (None, "backfill"):
        raise ValueError("Unsupported fee-sync checkpoint mode")
    jobs = state.setdefault("jobs", {})
    if any(not isinstance(job, dict) for job in jobs.values()):
        raise ValueError("Invalid report job in fee-sync checkpoint")
    if fixed:
        bounds = {"version": 1, "mode": "backfill", "start_date": start_date.isoformat(),
                  "end_date": end_date.isoformat()}
        if state.get("mode") == "backfill":
            if any(state.get(key) != value for key, value in bounds.items()):
                raise ValueError("Backfill checkpoint does not match the requested date range")
        elif jobs or state.get("mode") is not None:
            raise ValueError("Use a separate state file for the fixed backfill")
        dates = {(start_date + timedelta(days=offset)).isoformat()
                 for offset in range((end_date - start_date).days)}
        if set(jobs) - dates:
            raise ValueError("Backfill checkpoint contains dates outside the fixed range")
        state.update(bounds)
        save_state(state_path, state)
    else:
        if state.get("mode") == "backfill":
            raise ValueError("Use a separate state file for rolling sync")
        dates = {
            (today - timedelta(days=offset)).isoformat() for offset in range(1, days + 1)
        }
        # Include unfinished reports even if their dates have aged out of the window.
        dates.update(day for day, job in jobs.items() if job.get("status") == "pending")
    for day in sorted(dates):
        job = jobs.get(day, {})
        if fixed and job.get("status") == "succeeded":
            count = job.get("rows_upserted")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("Completed backfill job lacks a confirmed database import")
            continue
        if not fixed and job.get("completed_on") == run_date:
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
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    raise ValueError("Report endpoint did not confirm database import")
                job.update(
                    status="succeeded", completed_on=run_date, rows_upserted=count
                )
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
    if fixed:
        completed = sum(jobs.get(day, {}).get("status") == "succeeded" for day in dates)
        if completed == len(dates):
            LOGGER.info("Fee backfill complete: %s days in [%s, %s)",
                        completed, start_date, end_date)
        else:
            LOGGER.warning(
                "Fee backfill incomplete: %s/%s days imported; rerun the same "
                "range and state file to retry unavailable days", completed, len(dates)
            )


def main():
    """Run inside the deployed API container using its environment and mounted tmp."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int,
                        help="Rolling lookback (default: 7); cannot use with dates")
    parser.add_argument("--start-date", type=parse_date, help="Inclusive UTC date: YYYY-MM-DD")
    parser.add_argument("--end-date", type=parse_date, help="Exclusive UTC date: YYYY-MM-DD")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument(
        "--state-file", type=Path,
        help="Checkpoint path; fixed backfills default to a separate file named for their dates",
    )
    parser.add_argument("--env-file", default="/app/.env")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--wait-seconds", type=int, default=600)
    args = parser.parse_args()
    if (args.start_date is None) != (args.end_date is None):
        parser.error("--start-date and --end-date must be supplied together")
    if args.start_date is not None and args.days is not None:
        parser.error("Use either --days or --start-date/--end-date")
    if args.start_date is not None and (
        args.start_date >= args.end_date or args.end_date > datetime.now(timezone.utc).date()
    ):
        parser.error("Use start-date < end-date <= today UTC (end exclusive)")
    if min(args.days if args.days is not None else 7, args.poll_seconds, args.wait_seconds) < 1:
        parser.error("days, poll-seconds, and wait-seconds must be positive")
    state_path = args.state_file or (
        Path(f"/app/tmp/stripe-fees/backfill-{args.start_date}-{args.end_date}.json")
        if args.start_date is not None else Path("/app/tmp/stripe-fees/state.json")
    )
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    load_dotenv(args.env_file, override=False)
    api_key = os.getenv("STRIPE_API_PUBLIC_KEY")
    if not api_key:
        parser.error("STRIPE_API_PUBLIC_KEY is not configured")
    try:
        with requests.Session() as session:
            session.headers["x-api-key"] = api_key
            sync_reports(
                session,
                args.base_url.rstrip("/"),
                state_path,
                args.days if args.days is not None else 7,
                args.poll_seconds,
                args.wait_seconds,
                start_date=args.start_date,
                end_date=args.end_date,
            )
    except (requests.RequestException, ValueError, OSError, RuntimeError):
        LOGGER.exception(
            "Fee sync stopped; saved reports will be resumed on the next run"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
