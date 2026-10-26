# Missing Stripe payment report

Matching and reconciliation now exclude events where `ExcludeFromDashboard`,
`IsDeleted`, or `IsCancelled` equals 1. Null event flags are treated as false.
The same event rules apply to the admin Order Costs panel.

An administrator JWT is required for this read-only endpoint:

```text
GET /stripe/payment-intents/missing?start_date=2026-01-01&end_date=2027-01-01&ticket_socket_id=4
```

- `start_date` is inclusive; `end_date` is exclusive, using order purchase dates.
- Omit `ticket_socket_id` for all accounts.
- JSON includes total eligible orders, missing count/percentage, monthly totals,
  and order details. Default pagination is `limit=100&offset=0`, maximum limit 1000.
- Add `format=csv` to download all missing rows for the selection. CSV ignores
  pagination. Customer text is escaped against spreadsheet formula execution.

The report includes native and internal order/event IDs, account, event title/date,
purchase date, customer name/email, checkout processing fee, and manual transfer
flag. Deleted, comped, and inactive orders are excluded. Manual transfers are
included and marked for review.

"Missing" means there is no **linked successful** payment intent for the internal
partner order. An unlinked payment might already exist in Stripe or in the local
table; the report is a reconciliation queue, not proof the customer did not pay.
It intentionally does not treat an order number from another TicketSocket account
as payment evidence. Orders missing an internal partner-order mapping are included
with a null `TicketPartnerOrderId`, provided their event is mapped and eligible.

No manual matching writes are performed by this endpoint. Review payment metadata,
account and amount before assigning a payment to an order. Existing successful
payment rows are not rewritten by this change.

Example CSV download using an admin bearer token:

```bash
curl --fail \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  'https://YOUR_API_HOST/stripe/payment-intents/missing?start_date=2026-01-01&end_date=2027-01-01&ticket_socket_id=4&format=csv' \
  -o missing-payments-2026.csv
```

The older ad-hoc monthly SQL must also join `TicketPartnerEvents` to `Events` and
apply these event filters to the eligible-order denominator; changing import
matching alone does not change that query's missing percentages.
