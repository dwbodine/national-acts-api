# Stripe synchronization on EC2

Deploy the image containing both runners and apply migrations through
`0005_stripe_customer_phone` before starting. The deployed fee API must import
reports into StripeFees and return `rows_upserted`, not CSV.

These commands use the existing `nationalactsapi` container, its `/app/.env`,
and its persistent `/app/tmp` mount. Run as `ec2-user` with Docker access.
Check `command -v flock docker` before using the paths below.

## Ongoing fee reports

Keep the existing 20-minute `/stripe/transactions` cron: it imports payment
intents and refunds. Fees have a separate daily job.

First exercise one available window. Recent unavailable days are deferred, so
use the full seven-day window for the initial server check:

```bash
/usr/bin/flock -n /home/ec2-user/stripe-fees.lock \
  /usr/bin/docker exec --user 5678 nationalactsapi \
  python -m tools.sync_stripe_fees --days 7
```

Then add this using `crontab -e`:

```cron
0 4 * * * /usr/bin/flock -n /home/ec2-user/stripe-fees.lock /usr/bin/docker exec --user 5678 nationalactsapi python -m tools.sync_stripe_fees --days 7 >> /home/ec2-user/stripe-fees.log 2>&1
```

This runs at 04:00 in the cron server's timezone, processing UTC calendar days.
It resumes pending report IDs and skips dates already completed that UTC day.
Unavailable days remain eligible on subsequent runs. A bounded wait expires
with a nonzero exit, retaining the report ID for retry. Re-run the same command
manually to resume. The checkpoint is `/app/tmp/stripe-fees/state.json`.

An optional weekly wider reconciliation can share the same lock and checkpoint:

```cron
0 6 * * 0 /usr/bin/flock -n /home/ec2-user/stripe-fees.lock /usr/bin/docker exec --user 5678 nationalactsapi python -m tools.sync_stripe_fees --days 30 >> /home/ec2-user/stripe-fees.log 2>&1
```

## One-time payment intent and refund backfill

The runner calls StripeService directly, bypassing HTTP/Gunicorn timeouts. It
imports one UTC day per chunk, freezes the cutoff at first invocation, and saves
progress only after payment intent AND refund processing succeeds. Stripe list
pagination is handled by the service. Failed chunks retry three times with
backoff; retrying a partially written chunk uses the existing database upserts.

First test a single chunk:

```bash
/usr/bin/flock -n /home/ec2-user/stripe-backfill.lock \
  /usr/bin/docker exec --user 5678 nationalactsapi \
  python -m tools.backfill_stripe_transactions --max-chunks 1
```

The default start is **2023-05-23 00:00:00 UTC**. Inspect logs and database rows
before continuing. The checkpoint lives at `/app/tmp/stripe-backfill/state.json`.
Resume the same checkpoint in the background:

```bash
nohup /usr/bin/flock -n /home/ec2-user/stripe-backfill.lock \
  /usr/bin/docker exec --user 5678 nationalactsapi \
  python -m tools.backfill_stripe_transactions \
  > /home/ec2-user/stripe-backfill.log 2>&1 < /dev/null &
```

```bash
tail -f /home/ec2-user/stripe-backfill.log
docker exec --user 5678 nationalactsapi cat /app/tmp/stripe-backfill/state.json
```

Completion is logged as `Backfill complete through ...`; the checkpoint's
`next_start` equals `end`. Running again after completion makes no Stripe calls.
If interrupted or the container is replaced, rerun the background command using
the same mounted state. Do not delete the checkpoint to resume.

For a large failing day, add `--chunk-hours 1` on resume. For an explicitly bounded
new run, `--end-date YYYY-MM-DD` is exclusive midnight UTC. Use a different state
file for a different date range. The runner refuses a changed start/end against
an existing checkpoint.

The ongoing transaction cron may remain enabled: payment intent IDs and refund
IDs are unique. This backfill imports succeeded payment intents with orderId
metadata and all refunds returned by the service; it does not backfill fee reports.
Historical TicketSocket orders and partner mappings should already exist, since
existing payment intent rows keep their original links, including unmatched links.
The current created-time transaction window does not revisit older intents or
refunds whose status changes later; that needs separate reconciliation/webhooks.
