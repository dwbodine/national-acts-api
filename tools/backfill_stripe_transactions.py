"""Resume daily Stripe payment intent and refund imports from May 23, 2023."""

import argparse
from datetime import date, datetime, time, timezone
import json
import logging
import os
from pathlib import Path
import time as clock

from dotenv import load_dotenv

from tools.sync_stripe_fees import save_state

LOGGER = logging.getLogger(__name__)


def midnight(value):
    """Parse an explicit ISO calendar date as midnight UTC."""
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Dates must use YYYY-MM-DD")
    return int(datetime.combine(parsed, time.min, tzinfo=timezone.utc).timestamp())


def backfill(service, state_path, start, end=None, chunk_hours=24,
             max_chunks=None, attempts=3):
    """Checkpoint only fully imported chunks; replay partially imported failures safely."""
    if chunk_hours < 1 or attempts < 1 or (max_chunks is not None and max_chunks < 1):
        raise ValueError("Chunk hours, attempts, and max chunks must be positive")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("version") != 1 or state["start"] != start:
            raise ValueError("Checkpoint does not match this backfill start")
        if end is not None and state["end"] != end:
            raise ValueError("End date differs from the checkpoint's fixed cutoff")
        if not start <= state["next_start"] <= state["end"]:
            raise ValueError("Invalid checkpoint range")
    else:
        cutoff = end if end is not None else int(datetime.now(timezone.utc).timestamp())
        if cutoff <= start:
            raise ValueError("End must be after start")
        state = {"version": 1, "start": start, "end": cutoff,
                 "next_start": start, "chunks_completed": 0}
        save_state(state_path, state)
    processed = 0
    while state["next_start"] < state["end"]:
        if max_chunks is not None and processed >= max_chunks:
            LOGGER.info("Chunk limit reached; rerun with the same state file to resume")
            return state
        window_start = state["next_start"]
        window_end = min(window_start + chunk_hours * 3600, state["end"])
        LOGGER.info("Importing [%s, %s)",
                    datetime.fromtimestamp(window_start, timezone.utc).isoformat(),
                    datetime.fromtimestamp(window_end, timezone.utc).isoformat())
        for attempt in range(attempts):
            # The service returns None on failure, including partial import failures.
            result = service.get_transactions(start=window_start, end=window_end)
            if isinstance(result, list):
                break
            if attempt + 1 == attempts:
                raise RuntimeError("Stripe chunk failed; checkpoint remains at its start")
            delay = 5 * (2 ** attempt)
            LOGGER.warning("Chunk failed; retrying in %s seconds", delay)
            clock.sleep(delay)
        state["next_start"] = window_end
        state["chunks_completed"] += 1
        save_state(state_path, state)
        processed += 1
        LOGGER.info("Chunk complete: %s refunds processed; payment intents persisted by service",
                    len(result))
    LOGGER.info("Backfill complete through %s",
                datetime.fromtimestamp(state["end"], timezone.utc).isoformat())
    return state


def main():
    """Use the API container's credentials; keep checkpoints on its persistent tmp mount."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2023-05-23")
    parser.add_argument("--end-date", help="Exclusive midnight UTC; default freezes current time")
    parser.add_argument("--chunk-hours", type=int, default=24)
    parser.add_argument("--max-chunks", type=int)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--env-file", default="/app/.env")
    parser.add_argument("--state-file", type=Path,
                        default=Path("/app/tmp/stripe-backfill/state.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(args.env_file, override=False)
    if not os.getenv("STRIPE_API_SECRET_KEY"):
        parser.error("STRIPE_API_SECRET_KEY is not configured")
    # Import after dotenv configuration so the CLI can be inspected without app startup.
    from common.stripe_service import StripeService  # pylint: disable=import-outside-toplevel

    try:
        backfill(
            StripeService(), args.state_file, midnight(args.start_date),
            midnight(args.end_date) if args.end_date else None,
            args.chunk_hours, args.max_chunks, args.attempts,
        )
    except (ValueError, OSError, RuntimeError):
        LOGGER.exception("Backfill stopped; rerun using the same checkpoint to resume")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
