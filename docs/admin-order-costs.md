# Internal order costs

Dashboard and Sales Overview now include an administrator-only Order Costs panel.
The API enforces the administrator check using the database user, and the client
panel neither requests nor renders costs for other users. Existing client reports
and ticket-level calculations are unchanged.

TicketSocket supplies separate ticket prices, service fees, and checkout fees.
Checkout fees are summed from `individualProcessingFee` on tickets belonging to
the mapped event. A missing field is unknown, not zero; the 4.5% default is never
used to estimate historical fees. Explicit zero is retained.

Stripe supplies the actual charge payment method, the `stripe_fee` balance
transaction details, and application fees. The merchant confirmed application
`ca_AagDRnyDZMGwD09hWMO5LGWU3ASOyea3` represents TicketSocket insurance. Other
applications are not automatically classified as insurance.

Shortfall = actual Stripe processing fee minus customer checkout processing fee.
For #70854 this is $14.76 - $10.86 = $3.90. For #58994 the verified application fee
is $26.80 of insurance, separate from $11.29 of Stripe processing.

These are gross original-order figures, not a net settlement or refund report.
Costs are never allocated per ticket. Totals stay separate by currency; a fee in
a different settlement currency is not compared without conversion. Coverage
counts identify missing checkout amounts, missing Stripe costs, and unverified
insurance. Null order mappings remain null. Multi-event orders with ambiguous
Stripe mappings therefore remain incomplete rather than receiving an allocation.
The order detail preview shows the latest 100 rows; totals cover the selection.
Dashboard scopes purchase dates; Sales Overview scopes its visible event IDs.

## Deploy and populate

Deploy the API and users app changes together. Run the database migration before
starting the new API image, using the existing migration procedure:

```bash
python -m tools.migrate --env-file /app/.env upgrade
python -m tools.migrate --env-file /app/.env check
```

The new head is `0006_admin_settlement_costs`. It adds the checkout fee and fee
verification/currency fields. Old insurance candidates are retained as
`ApplicationFee`, but historical rows remain unverified until refreshed from
Stripe. The migration preserves their existing processing amount, since its
currency is unknown. Ordinary duplicate imports still leave existing successful
payment intents untouched.

Refresh the sample orders explicitly, inside the API container:

```bash
python -m tools.refresh_order_costs --order-ids 70854,58994
```

This reads TicketSocket checkout details and refreshes only the Stripe financial
metadata/payment method on existing intents. It does not change their gross
amount, customer details, or order mapping. Future TicketSocket order refreshes
populate checkout fees; newly inserted payment intents contain the new fields.

To refresh historical Stripe financial metadata, use a **new checkpoint**:

```bash
python -m tools.backfill_stripe_transactions \
  --start-date 2023-05-23 --refresh-financials \
  --state-file /app/tmp/stripe-backfill/financial-costs-v1.json
```

The command also replays refunds through their existing upsert. It does not fetch
historical TicketSocket checkout fees: those require TicketSocket order refreshes,
or explicit batches with `tools.refresh_order_costs --order-ids ...`. Until then,
the panel shows incomplete coverage. Do not reuse a completed old checkpoint for
the financial metadata refresh.

## Validation

Unit/API tests cover both example orders, verified versus unrelated application
fees, missing data, currency mismatches, default duplicate immutability, explicit
financial refresh, TicketSocket checkout summation, and administrator-only access.
`test/integration/test_admin_settlement.py` exercises migration upgrade/downgrade
and report SQL in a temporary MariaDB database when integration testing is enabled.
