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

## Detail endpoint

The following routes return the same report with detailed order/event rows:

```text
GET /stripe/payment-intents/missing/details?startDate=2026-01-01&endDate=2027-01-01&ticketSocketId=4
GET /stripe/payment-intents/misssing/details?startDate=2026-01-01&endDate=2027-01-01&ticketSocketId=4
```

Both spellings are supported, including the originally requested `misssing` path.
`startDate` and `endDate` are YYYY-MM-DD purchase dates with an exclusive end.
The existing snake_case parameter names continue to work. The `orders` array also
includes seller ID, venue, city and state alongside event title, date and IDs.
Pagination and CSV options work on all three report routes.

## Insert or update a local payment intent

```text
POST /stripe/payment-intents/update
Authorization: Bearer <admin JWT>
Content-Type: application/json
```

This endpoint writes the local database. It does not call Stripe or change a
payment at Stripe. JSON uses database column names. `PaymentIntentId` is the
Stripe `pi_...` identifier and is looked up first. If it already exists, all
supplied fields overwrite that row, including nullable fields and native IDs.
Omitted fields remain unchanged. The existing integer primary key is preserved,
even if a different `StripePaymentIntentId` was supplied. Local integer ID lookup
remains supported when no row matches the Stripe identifier.

For example, this corrects the native IDs on an existing payment without requiring
the full insert payload:

```json
{
  "PaymentIntentId": "pi_REPLACE_WITH_REAL_STRIPE_ID",
  "NativeOrderId": 42547,
  "NativeEventId": 123
}
```

To reconcile an existing payment with an order, send only the fields to change:

```json
{
  "StripePaymentIntentId": 123,
  "TicketPartnerOrderId": 456
}
```

The service resolves `NativeOrderId`/`NativeEventId` from that eligible TicketSocket
order. Explicitly supplied native IDs must agree with the order. Other payment
fields remain unchanged. A payment cannot be relinked to an excluded, deleted or
cancelled event, or to an unknown order. A null partner order ID removes the link.
If native IDs are corrected without explicitly supplying a partner order link,
an incompatible previous link is cleared. An explicitly supplied partner order
must agree with the supplied native IDs.

To insert, omit the local ID for automatic allocation, or provide a currently
unused positive integer ID. If the Stripe identifier already exists, the request
updates that row instead of inserting a duplicate. New rows require all these fields:

```json
{
  "PaymentIntentId": "pi_REPLACE_WITH_REAL_STRIPE_ID",
  "Description": "tickets.nationalactsvip.com Order 42547",
  "DateReceived": "2026-03-15T12:00:00Z",
  "Total": "123.45",
  "ProcessingFee": "3.45",
  "ProcessingFeeCurrency": "usd",
  "Currency": "usd",
  "SourceUrl": "tickets.nationalactsvip.com",
  "ExchangeRate": "1",
  "TicketPartnerOrderId": 456
}
```

`TicketPartnerOrderId` is optional for new unlinked rows. Nullable customer/event
fields may be omitted or explicitly null. Database defaults apply on insertion,
including `Status='succeeded'`, `PaymentMethod='card'` and `Insurance=0`.
`DateReceived` accepts ISO datetimes; offsets are normalized to UTC. Decimal
amounts should be supplied as strings to preserve precision. Only succeeded
payments are supported. `LastUpdated` is managed by the service.

Responses contain `created` and the saved `paymentIntent` row: HTTP 201 for an
insert and 200 for an update. Invalid fields/order links return 400; conflicting
identifiers return 409. Local-ID updates cannot replace that row's Stripe
identifier with a different, previously unknown identifier, because refunds and
fees reference it. Writes are transactional;
ordinary scheduled imports still do not overwrite existing successful rows.
