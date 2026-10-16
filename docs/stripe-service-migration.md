# Stripe migration service plan

Implemented against revision `7e3584499b4c` and the updated models:

1. Replace references to renamed tables and columns: `Events`, `Venues`,
   `EventNotes.EventId`, `FanMoments.EventId`, and `TourEvent.EventId`.
   `TicketOrders.ExternalEventId` remains unchanged in this migration.
2. Resolve application event/order/ticket IDs through `TicketPartnerEvents`,
   `TicketPartnerOrders`, and `TicketPartnerOrderTickets`. Preserve provider-native
   IDs in the models' `original_*` properties. Create mappings during refresh and
   comp-ticket creation.
3. Resolve partner IDs before provider-owned mutations. Restrict TicketSocket
   operations to partner 2 and verify the provider order's event and ticket's
   parent order. Reject unsupported partner mutations.
4. Use only `TicketPartnerEventId` and `TicketPartnerOrderId` for daily reporting,
   writes, lookups, and purchase-date cleanup. Runtime queries do not depend on
   the legacy provider columns. Historical migration backfill and downgrade SQL
   still reference them to convert between schemas.
5. Verify service behavior with updated unit fixtures and isolated MariaDB tests
   that use different application, provider-row, and provider-native IDs.

## ID contract

| Model property | Database identity |
| --- | --- |
| `VipEvent.event_id` | `Events.EventId` |
| `ticket_partner_event_id` | `TicketPartnerEvents.TicketPartnerEventId` |
| `ticket_partner_order_id` | `TicketPartnerOrders.TicketPartnerOrderId` |
| `ticket_partner_order_ticket_id` | `TicketPartnerOrderTickets.TicketPartnerTicketId` |
| `original_event_id` | TicketSocket-native `TicketSocketEvents.EventId` |
| `original_order_id` | TicketSocket-native `TicketSocketOrders.OrderId` |
| `original_ticket_id` | TicketSocket-native `TicketSocketOrderTickets.TicketId` |

Order lookup by API ID, order mutations, ticket mutations, and reporting rebuilds
use partner mapping IDs. Existing route names and the `ts_order_id` lookup keyword
remain for compatibility; their ID values now refer to the partner mapping.
Clients must use the renamed model fields returned by the API.

The event view now projects `TicketPartnerEventId` and `VenueId`, and includes
local partner events. These corrections are in the existing development migration;
an installation already at that revision will need an explicit view update or a
follow-up migration before running these services. Nothing runs a database upgrade
or downgrade automatically.

Stripe fetching remains read-only. Persisting Stripe transactions and deciding how
Stripe metadata identifies partner orders is a separate integration step; this
change does not invent that association or implement native Stripe ticket storage.

## TicketDetails

`TicketDetails` projects one row per `TicketPartnerOrderTickets` mapping, with
event/order/partner IDs, provider-native IDs, ticket fields, and order status
columns `OrderIsActive`, `OrderIsDeleted`, and `OrderIsComped`. Ticket status
columns retain names such as `IsActive`, `IsRefunded`, and `IsChargedBack`.
Provider fields stay NULL when a source is missing or belongs to a different
partner, event, or parent order. The view does not join Stripe transactions or
tours, so those relationships cannot multiply ticket rows.

The view is created and removed by the Stripe migration. Like the event-view
correction above, an already-applied revision needs an explicit view update or a
follow-up migration. The ticket projection and downgrade were verified against
MariaDB, including multiple Stripe payments, missing sources, wrong-parent ticket
links, and colliding IDs across partners/events.

## Partner ticket types

The end of the Stripe upgrade creates `PartnerTicketTypes` and `TicketTypeDetails`.
`PartnerTicketTypeId` is the internal primary key, `TicketPartnerEventId` links to
the application partner event, and nullable `ProviderTicketTypeId` stores the
provider's event-scoped ticket type ID. The event/provider-type pair is unique;
provider type zero is valid for TicketSocket comp types.

The migration backfills all existing TicketSocket types, including inactive and
comp types. `TicketTypeDetails` exposes partner and event identities plus the
provider's name, availability, active status, display order, and update timestamps.
Provider fields remain NULL for local or missing sources. Downgrade removes the
view and mapping table before dropping their event mapping dependency, leaving
the original TicketSocket ticket types intact.

Event ticket type reads, refresh lookups, and comp type lookups use
`TicketTypeDetails`. Refresh and comp creation ensure the corresponding
`PartnerTicketTypes` mapping exists before reading through the view. Writes still
target `TicketSocketTicketTypes`. `TicketDetails` also resolves its type metadata
through `TicketTypeDetails`, including the internal `PartnerTicketTypeId`.
The migration creates `TicketDetails` after `TicketTypeDetails` and drops it first
to respect this dependency.

Imported events now pass through `TicketPartnerService.ensure_imported_event()`
after their source row exists. It reuses the mapped application event or creates
the missing `Events` row and partner mapping, and preserves event date syncing.
Orders likewise pass through `ensure_order()` before import success is counted.
Failed parent mappings stop child processing and appear in refresh failure lists.
These checks run in `refresh_database_from_ticket_socket`; the retrieval method
continues to fetch and translate provider data without writing it.

## Validation

The Stripe upgrade drops `DailyOrderData.TicketSocketEventId` and
`TicketSocketOrderId` and their legacy foreign key/index after backfilling the
partner columns. It refuses to drop them if a daily row lacks the required
partner mapping. Downgrade recreates the source columns, restores their values
from the partner mappings, and reinstates the original nullability and constraints.

Application reads now use `EventDetails`, `OrderDetails`, and `TicketDetails`
where their projections cover the required data. This includes order/ticket lists,
refund discovery, ID resolution, dashboard and exchange-rate lookups, event reports,
fan moments, subscriber exports, printed-ticket event lookups, and seller event
lookups. Writes, provider refresh reconciliation, and mapping creation retain base
tables because they must operate on source rows, including rows not yet mapped.

Order projections deliberately omit payment-specific columns before `DISTINCT`;
other read projections omit tour-specific columns. Integration coverage includes
multiple Stripe payments and tour associations on the same event to check that
orders, tickets, subscribers, fan moments, and daily totals are not multiplied.

`OrderOverview` is the shared database projection for order lists. It combines
`OrderDetails`, `EventDetails`, and purchase-date exchange rates, omitting payment
and tour fields before `DISTINCT`. Services filter this view rather than sharing
a Python SQL constant. The Stripe migration creates it after its source views
and drops it before them during downgrade. Databases already at that revision
need an explicit view update or a follow-up migration to install it.

- All 19 integration tests passed against an isolated MariaDB 11.4 instance,
  including upgrade/downgrade round trips and populated service operations.
- Pylint error checks passed for all changed application modules.
- The full non-integration run completed with 913 passed and 13 failed. Remaining
  failures concern country-route authorization, FAQ behavior, page fixtures missing
  `IsPrimary`, and health-test connection doubles that do not accept `timeout`.
  These failures are outside the service/schema changes in this plan.
