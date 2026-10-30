# Stripe fields on event orders

`EventService.get_events_and_orders(get_orders=True)` automatically integrates
compact Stripe data for private order results. The `includeStripeFinancials`
request option and `include_stripe_financials` service parameter are removed.

Order properties:

- `exchange_rate`: recorded Stripe `ExchangeRate`, or null without a linked
  successful payment. Multiple payments must agree on currency and rate;
  otherwise the single rate is unknown. No TicketSocket rate fallback is used.
- `stripe_processing_fee`: stored Stripe processing fee, summed for multiple
  payments only when their fee currencies are compatible.
- `insurance`: stored Stripe insurance, or null when unknown. Multiple payments
  are summed only within one currency.
- `partner_processing_fee`: TicketSocketOrders `CustomerProcessingFee`, the amount
  collected at checkout; null when unknown.
- `radar_fee`: stored StripePaymentIntents `RadarFee` in USD; summed across linked
  successful payments, or null if any amount is unknown.
- `other_fees`: report fees joined through `StripeFees.IncurredBy = PaymentIntentId`,
  restricted to `IncurredByType='payment_intent'` and successful payments.

The API uses existing camelCase serialization. Example admin order fields:

```json
{
  "exchangeRate": 0.75,
  "stripeProcessingFee": "14.76",
  "insurance": "26.80",
  "radarFee": "0.07",
  "partnerProcessingFee": "10.86",
  "otherFees": [
    {"key": "Radar standard", "value": "0.07", "currency": "usd"}
  ]
}
```

Fee keys use feature name, falling back to fee description. Values include amount
plus tax and are grouped by name and currency. Decimal strings preserve precision;
different currencies remain separate. All matching report categories are included.
Those categories can overlap the separately returned processing fee, so the
endpoint does not combine them into a net total.

Missing payments return null rate/amounts and an empty fee array. Null order
mappings remain unassigned. Two bulk queries load payment fields and report fees.
Raw payment/refund records and event-level Stripe summaries are not attached.

Processing fees, insurance, Radar fees and other fees remain admin-only at the authenticated
event API boundary. Clients receive the Stripe-derived exchange rate. Public
event results do not load orders or Stripe fields.

These are returned order fields. Existing ticket revenue/refund calculations and
USD totals retain their current calculation; changing the returned exchange rate
does not recalculate those totals.
