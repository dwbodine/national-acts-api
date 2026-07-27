"""
Unit tests for common.event_service helpers.
"""

from datetime import datetime
from types import SimpleNamespace

from common import event_service
from common.models.national_acts import VipEvent


class FakeCalendarService:
    """
    Test double for calendar note lookups.
    """

    notes_by_event_id = {}
    instances = []

    def __init__(self):
        self.calls = []
        FakeCalendarService.instances.append(self)

    def get_event_notes(self, external_event_id):
        """
        Return the configured notes for an event.
        """
        self.calls.append(external_event_id)
        return FakeCalendarService.notes_by_event_id.get(external_event_id, [])


class FakeDashboardService:
    """
    Test double for dashboard rebuild requests.
    """

    instances = []

    def __init__(self):
        self.rebuild_calls = []
        FakeDashboardService.instances.append(self)

    def rebuild_daily_order_data_for_event(self, ticket_socket_event_id):
        """
        Record the event ids used for rebuilds.
        """
        self.rebuild_calls.append(ticket_socket_event_id)


class FakeOrder:
    """
    Minimal order object for VipEvent total calculations.
    """

    def __init__(self):
        self.is_comped = False
        self.num_tickets = 2
        self.has_refunds = False
        self.num_tickets_refunded = 0
        self.revenue_refunded = 0
        self.revenue_refunded_usd = 0
        self.service_fee_revenue_refunded = 0
        self.service_fee_revenue_refunded_usd = 0
        self.has_chargebacks = False
        self.num_tickets_charged_back = 0
        self.revenue_charged_back = 0
        self.revenue_charged_back_usd = 0
        self.service_fee_revenue_charged_back = 0
        self.service_fee_revenue_charged_back_usd = 0
        self.currency_abbrev = "USD"
        self.currency_symbol = "$"
        self.total_shirts = 0
        self.phone = "555-1111"
        self.is_deleted = False
        self.revenue = 100
        self.revenue_usd = 100
        self.service_fees = 20
        self.service_fees_usd = 20
        self.tickets = []


class FakeOrderService:
    """
    Test double for event order loading.
    """

    orders_to_return = []
    instances = []

    def __init__(self):
        self.calls = []
        FakeOrderService.instances.append(self)

    def get_orders_from_event_id(
        self,
        ticket_socket_event_id,
        show_inactive,
        show_deleted,
        ignore_flags,
    ):
        """
        Return the configured orders for an event.
        """
        self.calls.append(
            (ticket_socket_event_id, show_inactive, show_deleted, ignore_flags)
        )
        return FakeOrderService.orders_to_return


class FakeSeller:
    """
    Test double for Seller model lookups.
    """

    instances = []

    def __init__(self, seller_id):
        self.seller_id = seller_id
        FakeSeller.instances.append(self)


class FixedDateTime(datetime):
    """
    Fixed datetime helper for announce-date filtering tests.
    """

    @classmethod
    def now(cls, tz=None):
        """
        Return a fixed current datetime.
        """
        current = cls(2026, 4, 23, 12, 0, 0)
        if tz is not None:
            return tz.localize(current)
        return current


def build_event_row(**overrides):
    """
    Create a complete event row with sensible defaults for tests.
    """
    row = {
        "SellerId": 7,
        "SellerName": "Seller A",
        "SellerType": 2,
        "ExternalEventId": 10,
        "TicketSocketEventId": 20,
        "EventDate": "2026-05-01",
        "SellerEventCategoryId": 5,
        "IsVisibleOnSite": 1,
        "IsVisibleOnPortal": 1,
        "SellerRatePercent": 12.5,
        "IsVip": 1,
        "EventTime": "19:00",
        "MeetAndGreetTime": "17:00",
        "DoorsOpenTime": "18:00",
        "Title": "VIP Night",
        "Venue": "Arena",
        "Address": "123 Main",
        "City": "Austin",
        "State": "TX",
        "Zip": "73301",
        "Country": "USA",
        "TimeZone": "America/Chicago",
        "CountryId": 1,
        "CountryCode": "US",
        "EmailSentToVips": 1,
        "TextSentToVips": 0,
        "ListSentToBand": 1,
        "ListSentTime": "2026-04-01 10:00:00",
        "ListSentNumVips": 4,
        "CheckInLocation": "Lobby",
        "CheckInNotes": "Bring ID",
        "AnnounceDate": "2026-04-01 09:00:00",
        "IsAddedToBandsInTown": 1,
        "ExternalUrl": "https://external.example.com",
        "ExternalThumbnail": None,
        "ExternalEventVenueId": 99,
        "DisableLinkButton": 0,
        "DisableLinkReason": None,
        "ExternalVipLink": None,
        "DisableVipLinkButton": 0,
        "DisableVipLinkReason": None,
        "IsActive": 1,
        "IsDeleted": 0,
        "IsHidden": 0,
        "IsCancelled": 0,
        "CancelledDate": None,
        "ExcludeFromDashboard": 0,
        "EventNote": None,
        "EventId": 222,
        "URL": "https://tickets.example.com",
        "Thumbnail": "ticket-socket.jpg",
        "TourAnnounceDate": None,
        "IsTourActive": 0,
        "IsSoldOut": 0,
        "LastUpdate": "2026-04-01 10:30:00",
    }
    row.update(overrides)
    return row


def build_ticket_type_row(**overrides):
    """
    Create a ticket-type row for private ticket type lookups.
    """
    row = {
        "TicketSocketTicketTypeId": 1,
        "TicketTypeName": "General Admission",
        "TotalAvailable": 100,
        "IsActive": 1,
        "TicketTypeOrder": 2,
    }
    row.update(overrides)
    return row


def create_vip_event(is_vip=True, ticket_socket_url="https://tickets.example.com"):
    """
    Create a VipEvent instance for add_to_external_events tests.
    """
    event = VipEvent()
    event.is_vip = is_vip
    event.ticket_socket_url = ticket_socket_url
    return event


def test_get_location_from_event_returns_none_without_event_or_venue():
    """
    Test that get_location_from_event handles missing event and venue values.
    """
    service = event_service.EventService()

    assert service.get_location_from_event(None) is None
    assert service.get_location_from_event(SimpleNamespace(venue=None)) is None


def test_get_location_from_event_formats_venue_city_and_state():
    """
    Test that get_location_from_event formats venue, city, and state.
    """
    evt = SimpleNamespace(
        venue=SimpleNamespace(
            name="The Arena",
            city="Austin",
            state="TX",
            country=None,
        )
    )

    location = event_service.EventService().get_location_from_event(evt)

    assert location == "The Arena, Austin, TX"


def test_get_location_from_event_omits_empty_state_and_appends_country():
    """
    Test that get_location_from_event omits empty state and appends non-default country names.
    """
    evt = SimpleNamespace(
        venue=SimpleNamespace(
            name="The Hall",
            city="Toronto",
            state=None,
            country=SimpleNamespace(
                country_id=37,
                country_name="Canada",
                country_code="CA",
                countryName="Canada",
            ),
        )
    )

    location = event_service.EventService().get_location_from_event(evt)

    assert location == "The Hall, Toronto, Canada"


def test_get_events_and_orders_builds_search_and_seller_filters(monkeypatch):
    """
    Test that get_events_and_orders sanitizes search terms and builds seller filters.
    """
    calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    events = event_service.EventService().get_events_and_orders(
        seller_id=7,
        search_term='VIP="Night"',
        show_cancelled=False,
    )

    assert not events
    assert "COALESCE(ExternalEvents.IsDeleted, 0) = 0" in calls[0][0]
    assert "COALESCE(ExternalEvents.IsActive, 1) = 1" in calls[0][0]
    assert "COALESCE(ExternalEvents.IsHidden, 0) = 0" in calls[0][0]
    assert "COALESCE(ExternalEvents.IsCancelled, 0) = 0" in calls[0][0]
    assert "LIKE ('%VIPNight%')" in calls[0][0]
    assert calls[0][1] == {"sellerId_0": 7}


def test_get_events_and_orders_uses_prepopulated_seller_ids_without_appending_seller_id(
    monkeypatch,
):
    """
    Test that get_events_and_orders uses the provided seller_ids list as-is when it is already populated.
    """
    calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    events = event_service.EventService().get_events_and_orders(
        seller_id=7,
        seller_ids=[8],
    )

    assert not events
    assert calls[0][1] == {"sellerId_0": 8}


def test_get_events_and_orders_uses_tour_event_ids_for_tour_filter(monkeypatch):
    """
    Test that get_events_and_orders converts tour event ids into query parameters.
    """
    calls = []

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        if "FROM TourEvent" in sql:
            return [
                {"ExternalEventId": 91},
                {"ExternalEventId": 0},
                {"ExternalEventId": None},
                {"ExternalEventId": 92},
            ]
        return []

    monkeypatch.setattr(event_service, "db_query_all", fake_db_query_all)

    events = event_service.EventService().get_events_and_orders(tour_id=77)

    assert not events
    assert calls[0][1] == {"tour_id": 77}
    assert "ExternalEvents.EventId IN" in calls[1][0]
    assert calls[1][1] == {"eventId_0": 91, "eventId_1": 92}


def test_get_events_and_orders_uses_event_id_filter_when_provided(monkeypatch):
    """
    Test that get_events_and_orders filters directly by event id when one is provided.
    """
    calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    events = event_service.EventService().get_events_and_orders(event_id=55)

    assert not events
    assert "ExternalEvents.EventId = %(event_id)s" in calls[0][0]
    assert calls[0][1] == {"event_id": 55}


def test_get_events_and_orders_handles_tours_without_valid_event_ids(monkeypatch):
    """
    Test that get_events_and_orders leaves the main query unfiltered when a tour has no valid event ids.
    """
    calls = []

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        if "FROM TourEvent" in sql:
            return [{"ExternalEventId": 0}, {"ExternalEventId": None}]
        return []

    monkeypatch.setattr(event_service, "db_query_all", fake_db_query_all)

    events = event_service.EventService().get_events_and_orders(tour_id=77)

    assert not events
    assert "ExternalEvents.EventId IN" not in calls[1][0]
    assert calls[1][1] == {}


def test_get_events_and_orders_maps_public_events_and_skips_future_announces(
    monkeypatch,
):
    """
    Test that public event lookups skip future announces and map returned fields.
    """
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {10: ["note-a"]}
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(event_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: [
            build_event_row(
                ExternalThumbnail="override.jpg",
                ExternalVipLink="https://vip.example.com",
                AnnounceDate="2026-04-01 09:00:00",
            ),
            build_event_row(
                ExternalEventId=11,
                TicketSocketEventId=21,
                AnnounceDate="2026-05-10 09:00:00",
                Title="Future Event",
            ),
        ],
    )
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )

    events = event_service.EventService().get_events_and_orders(is_public=True)

    assert len(events) == 1
    assert FakeCalendarService.instances[0].calls == [10]
    assert events[0].external_event_id == 10
    assert events[0].thumbnail == "override.jpg"
    assert events[0].external_thumbnail == "override.jpg"
    assert events[0].ticket_socket_url == "https://vip.example.com"
    assert events[0].venue.timezone == "CDT"
    assert events[0].venue.country.country_code == "US"
    assert events[0].notes == ["note-a"]
    assert not events[0].ticket_types
    assert not events[0].orders


def test_get_events_and_orders_skips_future_tour_announces_for_public_events(
    monkeypatch,
):
    """
    Test that public event lookups skip future active-tour announces even when the event announce date is missing.
    """
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {}
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(event_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: [
            build_event_row(
                ExternalEventId=10,
                TicketSocketEventId=20,
                AnnounceDate=None,
                TourAnnounceDate="2026-05-10 09:00:00",
                IsTourActive=1,
            ),
            build_event_row(
                ExternalEventId=11,
                TicketSocketEventId=21,
                AnnounceDate=None,
                TourAnnounceDate="2026-04-01 09:00:00",
                IsTourActive=1,
                Title="Visible Tour Event",
            ),
        ],
    )
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )

    events = event_service.EventService().get_events_and_orders(is_public=True)

    assert len(events) == 1
    assert events[0].title == "Visible Tour Event"


def test_get_events_and_orders_applies_external_and_visibility_filters(monkeypatch):
    """
    Test that get_events_and_orders skips excluded external and hidden website events.
    """
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {13: []}
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: [
            build_event_row(
                ExternalEventId=11,
                TicketSocketEventId=None,
                Title="External Only",
            ),
            build_event_row(
                ExternalEventId=12,
                TicketSocketEventId=22,
                Title="Hidden On Site",
                IsVisibleOnSite=0,
            ),
            build_event_row(
                ExternalEventId=13,
                TicketSocketEventId=23,
                Title="Visible Event",
            ),
        ],
    )
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )
    monkeypatch.setattr(
        event_service,
        "get_timezones_from_country_code",
        lambda country_code, event_date=None: ["America/Chicago"],
    )

    events = event_service.EventService().get_events_and_orders(
        exclude_external=True,
        is_website=True,
    )

    assert len(events) == 1
    assert events[0].title == "Visible Event"


def test_get_events_and_orders_skips_portal_hidden_events(monkeypatch):
    """
    Test that get_events_and_orders skips events hidden from the portal.
    """
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {13: []}
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: [
            build_event_row(
                ExternalEventId=12,
                TicketSocketEventId=22,
                Title="Hidden On Portal",
                IsVisibleOnPortal=0,
            ),
            build_event_row(
                ExternalEventId=13,
                TicketSocketEventId=23,
                Title="Visible Event",
            ),
        ],
    )
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )
    monkeypatch.setattr(
        event_service,
        "get_timezones_from_country_code",
        lambda country_code, event_date=None: ["America/Chicago"],
    )

    events = event_service.EventService().get_events_and_orders(is_portal=True)

    assert len(events) == 1
    assert events[0].title == "Visible Event"


def test_get_events_and_orders_loads_ticket_types_orders_and_country_timezones(
    monkeypatch,
):
    """
    Test that private event lookups load ticket types, orders, notes, and country timezones.
    """
    calls = []
    fake_order = FakeOrder()
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {10: ["note-a", "note-b"]}
    FakeOrderService.instances = []
    FakeOrderService.orders_to_return = [fake_order]
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        if "FROM TicketSocketTicketTypes" in sql:
            return [
                build_ticket_type_row(
                    TicketSocketTicketTypeId=7,
                    TicketTypeName="Early Entry",
                    TicketTypeOrder=None,
                )
            ]
        return [build_event_row()]

    monkeypatch.setattr(event_service, "db_query_all", fake_db_query_all)
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )
    monkeypatch.setattr(
        event_service,
        "get_timezones_from_country_code",
        lambda country_code, event_date=None: ["America/Chicago", "America/New_York"],
    )

    events = event_service.EventService().get_events_and_orders(
        get_orders=True,
        is_portal=True,
        show_inactive=True,
        show_deleted=True,
        ignore_flags=True,
    )

    assert len(events) == 1
    assert "AND IsActive=1" in calls[1][0]
    assert events[0].ticket_types[0].ticket_type_id == 7
    assert events[0].ticket_types[0].ticket_type_order == 1
    assert events[0].orders == [fake_order]
    assert events[0].notes == ["note-a", "note-b"]
    assert events[0].venue.country.timezones == [
        "America/Chicago",
        "America/New_York",
    ]
    assert events[0].total_revenue == 100
    assert events[0].total_tickets == 2
    assert events[0].has_ticket_type_data is True
    assert FakeOrderService.instances[0].calls == [(20, True, True, True)]


def test_get_events_and_orders_builds_date_and_exclusion_filters(monkeypatch):
    """
    Test that get_events_and_orders builds start/end and exclusion date filters.
    """
    calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    events = event_service.EventService().get_events_and_orders(
        start=1746057600,
        end=1748736000,
        exclude_start=1746144000,
        exclude_end=1746230400,
    )

    assert not events
    assert (
        "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s" in calls[0][0]
    )
    assert (
        "ExternalEvents.EventDate NOT BETWEEN %(exclude_start)s AND %(exclude_end)s"
        in calls[0][0]
    )
    assert calls[0][1] == {
        "startDate": "2025-04-30",
        "endDate": "2025-05-31",
        "exclude_start": "2025-05-01",
        "exclude_end": "2025-05-02",
    }


def test_get_events_and_orders_builds_future_end_only_filter(monkeypatch):
    """
    Test that get_events_and_orders uses today as the lower bound when only a future end date is provided.
    """
    calls = []
    monkeypatch.setattr(event_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )
    future_end = int(FixedDateTime(2026, 5, 1, 0, 0, 0).timestamp())

    events = event_service.EventService().get_events_and_orders(end=future_end)

    assert not events
    assert (
        "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s" in calls[0][0]
    )
    assert calls[0][1] == {
        "startDate": "2026-04-23",
        "endDate": "2026-05-01",
    }


def test_get_events_and_orders_builds_start_only_filter(monkeypatch):
    """
    Test that get_events_and_orders builds a start-only date filter when only start is provided.
    """
    calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    events = event_service.EventService().get_events_and_orders(start=1746057600)

    assert not events
    assert "ExternalEvents.EventDate >= %(startDate)s" in calls[0][0]
    assert calls[0][1] == {"startDate": "2025-04-30"}


def test_get_events_and_orders_maps_events_without_country_codes(monkeypatch):
    """
    Test that get_events_and_orders leaves the venue country unset when the row has no country code.
    """
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {10: []}
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: [
            build_event_row(CountryCode=None, CountryId=None, Country=""),
        ],
    )
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )

    events = event_service.EventService().get_events_and_orders()

    assert len(events) == 1
    assert events[0].venue.country is None


def test_get_events_and_orders_marks_deleted_rows_inactive(monkeypatch):
    """
    Test that get_events_and_orders forces deleted events to inactive in the mapped model.
    """
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {10: []}
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: [build_event_row(IsDeleted=1, IsActive=1)],
    )
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )
    monkeypatch.setattr(
        event_service,
        "get_timezones_from_country_code",
        lambda country_code, event_date=None: ["America/Chicago"],
    )

    events = event_service.EventService().get_events_and_orders()

    assert len(events) == 1
    assert events[0].is_deleted is True
    assert events[0].is_active is False


def test_get_events_and_orders_loads_ticket_types_without_portal_filter(
    monkeypatch,
):
    """
    Test that get_events_and_orders loads ticket types without the portal active filter when not in portal mode.
    """
    calls = []
    FakeCalendarService.instances = []
    FakeCalendarService.notes_by_event_id = {10: []}
    FakeOrderService.instances = []
    FakeOrderService.orders_to_return = []
    monkeypatch.setattr(event_service, "CalendarService", FakeCalendarService)
    monkeypatch.setattr(event_service, "OrderService", FakeOrderService)

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        if "FROM TicketSocketTicketTypes" in sql:
            return [build_ticket_type_row()]
        return [build_event_row()]

    monkeypatch.setattr(event_service, "db_query_all", fake_db_query_all)
    monkeypatch.setattr(
        event_service,
        "get_timezone_abbreviation",
        lambda timezone_code, event_date: "CDT",
    )
    monkeypatch.setattr(
        event_service,
        "get_timezones_from_country_code",
        lambda country_code, event_date=None: ["America/Chicago"],
    )

    events = event_service.EventService().get_events_and_orders(get_orders=True)

    assert len(events) == 1
    assert "AND IsActive=1" not in calls[1][0]


def test_disable_events_returns_true_for_empty_ids():
    """
    Test that disable_events returns True when there are no event ids to update.
    """
    assert event_service.EventService().disable_events([], disabled=True) is True


def test_disable_events_updates_rows_and_rebuilds_dashboard(monkeypatch):
    """
    Test that disable_events updates rows and rebuilds dashboard data for TS events.
    """
    update_calls = []
    query_calls = []
    FakeDashboardService.instances = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        event_service,
        "db_query_one",
        lambda sql, data: query_calls.append((sql, data))
        or {"TicketSocketEventId": 44},
    )
    monkeypatch.setattr(event_service, "DashboardService", FakeDashboardService)

    success = event_service.EventService().disable_events([10], disabled=True)

    assert success is True
    assert update_calls[0][1] == {"event_id": 10, "is_active": 0}
    assert query_calls[0][1] == {"event_id": 10}
    assert FakeDashboardService.instances[0].rebuild_calls == [44]


def test_disable_events_skips_dashboard_rebuild_without_ticket_socket_event_id(
    monkeypatch,
):
    """
    Test that disable_events skips dashboard rebuilds when the lookup row is missing or empty.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(event_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(event_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(event_service, "db_query_one", lambda sql, data: {})

    success = event_service.EventService().disable_events([10], disabled=True)

    assert success is True
    assert not FakeDashboardService.instances


def test_disable_events_skips_dashboard_rebuild_for_zero_ticket_socket_event_ids(
    monkeypatch,
):
    """
    Test that disable_events skips dashboard rebuilds when the looked-up ticket-socket id is zero.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(event_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(event_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        event_service,
        "db_query_one",
        lambda sql, data: {"TicketSocketEventId": 0},
    )

    success = event_service.EventService().disable_events([10], disabled=True)

    assert success is True
    assert not FakeDashboardService.instances


def test_disable_events_stops_after_first_failed_update(monkeypatch):
    """
    Test that disable_events stops processing when an update fails.
    """
    update_calls = []
    query_calls = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or False,
    )
    monkeypatch.setattr(
        event_service,
        "db_query_one",
        lambda sql, data: query_calls.append((sql, data)) or {},
    )

    success = event_service.EventService().disable_events([10, 11], disabled=False)

    assert success is False
    assert len(update_calls) == 1
    assert not query_calls


def test_mark_events_live_in_bands_in_town_stops_on_failure(monkeypatch):
    """
    Test that mark_events_live_in_bands_in_town stops after the first failed update.
    """
    update_calls = []
    results = iter([True, False])
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or next(results),
    )

    success = event_service.EventService().mark_events_live_in_bands_in_town([5, 6, 7])

    assert success is False
    assert len(update_calls) == 2
    assert update_calls[1][1] == {"event_id": 6}


def test_mark_events_live_in_bands_in_town_returns_true_for_empty_lists():
    """
    Test that mark_events_live_in_bands_in_town returns True when there are no event ids to update.
    """
    assert event_service.EventService().mark_events_live_in_bands_in_town([]) is True


def test_mark_events_live_in_bands_in_town_updates_all_rows_on_success(monkeypatch):
    """
    Test that mark_events_live_in_bands_in_town returns True when all updates succeed.
    """
    update_calls = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = event_service.EventService().mark_events_live_in_bands_in_town([5, 6])

    assert success is True
    assert len(update_calls) == 2


def test_delete_events_marks_deleted_and_rebuilds_dashboard(monkeypatch):
    """
    Test that delete_events deactivates deleted events and rebuilds dashboard data.
    """
    update_calls = []
    FakeDashboardService.instances = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        event_service,
        "db_query_one",
        lambda sql, data: {"TicketSocketEventId": 70},
    )
    monkeypatch.setattr(event_service, "DashboardService", FakeDashboardService)

    success = event_service.EventService().delete_events([15], deleted=True)

    assert success is True
    assert "IsDeleted=%(isDeleted)s" in update_calls[0][0]
    assert "IsActive=0" in update_calls[0][0]
    assert update_calls[0][1] == {"event_id": 15, "isDeleted": 1}
    assert FakeDashboardService.instances[0].rebuild_calls == [70]


def test_delete_events_can_clear_deleted_flag_without_deactivating(monkeypatch):
    """
    Test that delete_events omits deactivation SQL when clearing a deleted flag.
    """
    update_calls = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(event_service, "db_query_one", lambda sql, data: {})

    success = event_service.EventService().delete_events([15], deleted=False)

    assert success is True
    assert "IsActive=0" not in update_calls[0][0]
    assert update_calls[0][1] == {"event_id": 15, "isDeleted": 0}


def test_delete_events_returns_true_for_empty_lists():
    """
    Test that delete_events returns True when there are no event ids to update.
    """
    assert event_service.EventService().delete_events([], deleted=True) is True


def test_delete_events_stops_when_an_update_fails(monkeypatch):
    """
    Test that delete_events stops processing when the row update fails.
    """
    monkeypatch.setattr(event_service, "db_update", lambda sql, data: False)

    success = event_service.EventService().delete_events([15], deleted=True)

    assert success is False


def test_delete_events_skips_dashboard_rebuild_without_ticket_socket_event_id(
    monkeypatch,
):
    """
    Test that delete_events skips dashboard rebuilds when the lookup row is missing or empty.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(event_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(event_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(event_service, "db_query_one", lambda sql, data: {})

    success = event_service.EventService().delete_events([15], deleted=True)

    assert success is True
    assert not FakeDashboardService.instances


def test_delete_events_skips_dashboard_rebuild_for_zero_ticket_socket_event_ids(
    monkeypatch,
):
    """
    Test that delete_events skips dashboard rebuilds when the looked-up ticket-socket id is zero.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(event_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(event_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        event_service,
        "db_query_one",
        lambda sql, data: {"TicketSocketEventId": 0},
    )

    success = event_service.EventService().delete_events([15], deleted=True)

    assert success is True
    assert not FakeDashboardService.instances


def test_get_events_and_orders_uses_deleted_inactive_and_visibility_branches(
    monkeypatch,
):
    """
    Test that get_events_and_orders toggles deleted, inactive, hidden, and cancelled filters when requested.
    """
    calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    events = event_service.EventService().get_events_and_orders(
        show_deleted=True,
        show_hidden=True,
        show_cancelled=True,
    )

    assert not events
    assert "COALESCE(ExternalEvents.IsDeleted, 0) = 0" not in calls[0][0]
    assert "COALESCE(ExternalEvents.IsActive, 1) = 0" in calls[0][0]
    assert "COALESCE(ExternalEvents.IsHidden, 0) = 0" not in calls[0][0]
    assert "COALESCE(ExternalEvents.IsCancelled, 0) = 0" not in calls[0][0]


def test_hide_events_returns_false_when_an_update_fails(monkeypatch):
    """
    Test that hide_events returns False when any update fails.
    """
    update_calls = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or False,
    )

    success = event_service.EventService().hide_events([30], hidden=True)

    assert success is False
    assert update_calls[0][1] == {"event_id": 30, "isHidden": 1}


def test_hide_events_returns_true_for_empty_lists():
    """
    Test that hide_events returns True when there are no event ids to update.
    """
    assert event_service.EventService().hide_events([], hidden=True) is True


def test_hide_events_updates_all_rows_on_success(monkeypatch):
    """
    Test that hide_events returns True when all row updates succeed.
    """
    update_calls = []
    monkeypatch.setattr(
        event_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = event_service.EventService().hide_events([30, 31], hidden=False)

    assert success is True
    assert len(update_calls) == 2


def test_add_to_external_events_reuses_existing_venue_for_vip_events(monkeypatch):
    """
    Test that add_to_external_events reuses an existing venue and stores VIP links.
    """
    insert_calls = []
    monkeypatch.setattr(
        event_service,
        "db_query_one",
        lambda sql, data: {"VenueID": 55},
    )
    monkeypatch.setattr(
        event_service,
        "db_insert",
        lambda sql, data, cnx: insert_calls.append((sql, data, cnx)) or 101,
    )
    event_data = {
        "id": 20,
        "seller_id": 7,
        "title": "VIP Night",
        "eventDate": "2026-05-01",
        "thumbnail": "thumb.jpg",
        "venue": "Arena",
        "city": "Austin",
    }

    success = event_service.EventService().add_to_external_events(
        event_data,
        create_vip_event(is_vip=True),
        "cnx-1",
    )

    assert success is True
    assert insert_calls[0][1]["venue_id"] == 55
    assert insert_calls[0][1]["url"] is None
    assert insert_calls[0][1]["external_vip_link"] == "https://tickets.example.com"
    assert insert_calls[0][2] == "cnx-1"


def test_add_to_external_events_inserts_non_vip_events_without_existing_venue(
    monkeypatch,
):
    """
    Test that add_to_external_events stores the ticket URL for non-VIP events.
    """
    insert_calls = []
    monkeypatch.setattr(event_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        event_service,
        "db_insert",
        lambda sql, data, cnx: insert_calls.append((sql, data, cnx)) or 202,
    )
    event_data = {
        "id": 21,
        "seller_id": 8,
        "title": "Standard Event",
        "eventDate": "2026-06-01",
        "thumbnail": "thumb.jpg",
        "venue": "Club",
        "city": "Dallas",
    }

    success = event_service.EventService().add_to_external_events(
        event_data,
        create_vip_event(is_vip=False, ticket_socket_url="https://public.example.com"),
        "cnx-2",
    )

    assert success is True
    assert insert_calls[0][1]["venue_id"] is None
    assert insert_calls[0][1]["url"] == "https://public.example.com"
    assert insert_calls[0][1]["external_vip_link"] is None


def test_get_tours_from_recent_events_maps_recent_tour_cards(monkeypatch):
    """
    Test that recent event tours are mapped with seller, cover image, and route data.
    """
    FakeSeller.instances = []
    calls = []
    monkeypatch.setattr(event_service, "Seller", FakeSeller)

    def fake_db_query_all(sql):
        calls.append(sql)
        return [
            {
                "SellerId": 7,
                "PageRoute": "/seller-a",
                "CoverImage": "cover-a.jpg",
            },
            {
                "SellerId": 8,
                "PageRoute": "/seller-b",
                "CoverImage": None,
            },
        ]

    monkeypatch.setattr(event_service, "db_query_all", fake_db_query_all)

    tours = event_service.EventService().get_tours_from_recent_events()

    assert len(tours) == 2
    assert [tour.sellers[0].seller_id for tour in tours] == [7, 8]
    assert tours[0].cover_image == "cover-a.jpg"
    assert tours[0].href == "/seller-a"
    assert tours[1].cover_image is None
    assert tours[1].href == "/seller-b"
    assert "WITH UpcomingEvents" not in calls[0]
    assert "s.SellerTypeId = 1" in calls[0]
    assert "p.PageTypeID = 7" in calls[0]
    assert "p.PageOrder" in calls[0]
    assert "ORDER BY p.PageOrder, MIN(ee.EventDate) ASC" in calls[0]
    assert "LIMIT 18" in calls[0]
