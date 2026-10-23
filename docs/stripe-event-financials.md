# Optional Stripe event financials

For private events with loaded orders:

```python
events = EventService().get_events_and_orders(
    event_id=event_id,
    get_orders=True,
    include_stripe_financials=True,
)
```

The authenticated `/events/getEventsAndOrders` endpoint accepts
`includeStripeFinancials=1` for administrators only. The default stays false. Public requests and
requests omitting orders do not load Stripe data.

Each loaded order and event receives these additional fields:

- `stripe_payments`, `stripe_refunds`, and `stripe_fees`: supporting database rows.
- `stripe_totals_by_currency`: gross, succeeded refunds, reported fees including
  tax, and provisional net, grouped by currency.
- `stripe_currency`, `stripe_gross`, `stripe_refunded`, `stripe_reported_fees`, and
  `stripe_net`: convenient single-currency values, or null for multiple currencies.
- `stripe_currency_mismatch`: refunds/fees whose currency differs from their payment.
  Net remains null in that case; no implicit currency conversion is performed.
- `stripe_fees_available`: at least one fee row exists, not a completeness guarantee.
- `stripe_net_is_provisional`: true because fee reports arrive later and currently
  contain only payment-intent-attributed fees.
- `stripe_financials_loaded`: true after enrichment.

Amounts are calculated with Decimal and serialized as decimal strings to preserve
precision. Supporting rows retain the database's column names. Event totals count
each partner order once. Pending/failed refunds appear in supporting rows but do
not reduce totals. Reported fees are summed once; the payment's ProcessingFee is
not added again. Ticket counts, refund flags, and existing revenue calculations
remain independent.

Three bulk queries load payments, refunds, and fees separately, preventing
multiplication from one-to-many joins. PaymentIntentId links both refunds and
payment-intent-attributed fees. TicketPartnerOrderId links payments to orders.

Null order mappings remain null: no metadata fallback assigns them to an event.
`StripeFinancialService().get_financials()` without an order filter retains those
payments via left joins for reconciliation. Event-scoped results cannot include
payments with no known order/event association.

The Stripe model now stores exchange rates as ratios rather than dividing them
by 100. Existing persisted exchange-rate values are not rewritten by this change.
