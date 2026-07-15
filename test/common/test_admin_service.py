"""
Unit tests for common.admin_service helpers.
"""

from common import admin_service
from common.models.admin import ExternalVenue, SiteSetting, SiteSettingType
from common.models.national_acts import VipEvent
from common.models.ticket_socket import Country, TicketSocketTicketType, Timezone


class FakeTicketSocketService:
    """
    Test double for TicketSocketService account loading.
    """

    instances = []
    categories_by_id = {}

    def __init__(self, ticket_socket_id):
        self.ticket_socket_id = ticket_socket_id
        self.name = f"Account {ticket_socket_id}"
        self.currency_symbol = "$"
        self.exchange_rate_id = ticket_socket_id + 10
        self.exchange_rate_slug = f"slug-{ticket_socket_id}"
        self.service_url = f"https://service/{ticket_socket_id}"
        self.utc_offset_hours = ticket_socket_id
        FakeTicketSocketService.instances.append(self)

    def get_categories(self):
        """
        Return the configured categories for the fake account.
        """
        return FakeTicketSocketService.categories_by_id.get(
            self.ticket_socket_id, [f"category-{self.ticket_socket_id}"]
        )


class FakeOrderService:
    """
    Test double for order refund orchestration.
    """

    instances = []
    refund_results = []

    def __init__(self):
        self.calls = []
        FakeOrderService.instances.append(self)

    def refund_order(self, order_id, refund_service_fees, notify_user):
        """
        Record refund requests and return the next configured result.
        """
        self.calls.append((order_id, refund_service_fees, notify_user))
        return FakeOrderService.refund_results.pop(0)


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
        Record the event id used for dashboard rebuilds.
        """
        self.rebuild_calls.append(ticket_socket_event_id)


class FakeEventService:
    """
    Test double for event queries.
    """

    instances = []
    events_to_return = []

    def __init__(self):
        self.calls = []
        FakeEventService.instances.append(self)

    def get_events_and_orders(self, **kwargs):
        """
        Record query arguments and return the configured events.
        """
        self.calls.append(kwargs)
        return FakeEventService.events_to_return


def create_site_setting(
    setting_id=0,
    name="HeroImage",
    display_name="Hero Image",
    setting_type=SiteSettingType.TEXT,
    value="value",
):
    """
    Create a SiteSetting instance for tests.
    """
    setting = SiteSetting()
    setting.setting_id = setting_id
    setting.name = name
    setting.display_name = display_name
    setting.type = setting_type
    setting.value = value
    setting.file_path = None
    setting.dirty = True
    return setting


def create_external_venue(venue_id=0):
    """
    Create an ExternalVenue instance for tests.
    """
    venue = ExternalVenue()
    venue.venue_id = venue_id
    venue.venue = "The Arena"
    venue.address = "123 Main"
    venue.city = "Nashville"
    venue.state = "TN"
    venue.zip_code = "37011"
    venue.country = Country(1, "USA", "US")
    venue.timezone = Timezone()
    venue.timezone.timezone = "America/Chicago"
    return venue


def create_vip_event(external_event_id=0, ticket_socket_event_id=12):
    """
    Create a VipEvent instance for tests.
    """
    event = VipEvent()
    event.external_event_id = external_event_id
    event.seller_id = 44
    event.ticket_socket_event_id = ticket_socket_event_id
    event.title = "VIP Night"
    event.event_date = "2026-05-01"
    event.meet_and_greet_time = "17:00"
    event.doors_open = "18:00"
    event.event_time = "19:00"
    event.is_active = True
    event.is_deleted = False
    event.is_added_to_bands_in_town = True
    event.is_hidden = False
    event.announce_date = "2026-04-01"
    event.check_in_location = "Lobby"
    event.check_in_notes = "Bring ID"
    event.email_sent_to_vips = True
    event.text_sent_to_vips = False
    event.external_url = "https://event"
    event.external_event_venue_id = 99
    event.disable_link_button = False
    event.disable_link_reason = None
    event.external_vip_link = "https://vip"
    event.disable_vip_link_button = False
    event.disable_vip_link_reason = None
    event.external_thumbnail = "thumb.jpg"
    event.exclude_from_dashboard = False
    event.event_note = None
    event.is_cancelled = False
    event.ticket_types = []
    return event


def test_get_site_settings_maps_rows_to_site_setting_objects(monkeypatch):
    """
    Test that get_site_settings converts database rows into SiteSetting objects.
    """
    rows = [
        {
            "ID": "7",
            "Name": "HeroImage",
            "DisplayName": "Hero Image",
            "Type": "Image",
            "Value": "hero.jpg",
            "FilePath": "/tmp/hero.jpg",
        }
    ]
    monkeypatch.setattr(admin_service, "db_query_all", lambda sql: rows)

    settings = admin_service.AdminService().get_site_settings()

    assert len(settings) == 1
    assert settings[0].setting_id == 7
    assert settings[0].name == "HeroImage"
    assert settings[0].display_name == "Hero Image"
    assert settings[0].type == "Image"
    assert settings[0].value == "hero.jpg"
    assert settings[0].file_path == "/tmp/hero.jpg"
    assert settings[0].dirty is False


def test_update_setting_returns_false_when_setting_is_none():
    """
    Test that update_setting returns False when no setting is provided.
    """
    assert admin_service.AdminService().update_setting(None) is False


def test_update_setting_inserts_new_setting(monkeypatch):
    """
    Test that update_setting inserts a new setting when the id is missing.
    """
    calls = []
    setting = create_site_setting(setting_id=0)

    def fake_db_insert(sql, data):
        calls.append((sql, data))
        return 12

    monkeypatch.setattr(admin_service, "db_insert", fake_db_insert)

    success = admin_service.AdminService().update_setting(setting)

    assert success is True
    assert "INSERT INTO Settings" in calls[0][0]
    assert calls[0][1]["name"] == "HeroImage"


def test_update_setting_updates_existing_image_and_removes_old_file(monkeypatch):
    """
    Test that update_setting removes the old image when an image setting changes.
    """
    calls = {"remove": []}
    setting = create_site_setting(
        setting_id=5,
        setting_type=SiteSettingType.IMAGE,
        value="new.jpg",
    )
    monkeypatch.setattr(
        admin_service,
        "db_query_one",
        lambda sql, data: {"Value": "old.jpg"},
    )
    monkeypatch.setattr(admin_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        admin_service,
        "get_bucket_name_from_image_type",
        lambda image_type: "home-banner-bucket",
    )
    monkeypatch.setattr(
        admin_service,
        "remove_file",
        lambda file_name, bucket_name: calls["remove"].append((file_name, bucket_name)),
    )

    success = admin_service.AdminService().update_setting(setting)

    assert success is True
    assert calls["remove"] == [("old.jpg", "home-banner-bucket")]


def test_update_setting_does_not_remove_file_when_value_is_unchanged(monkeypatch):
    """
    Test that update_setting leaves image files alone when the value does not change.
    """
    setting = create_site_setting(
        setting_id=5,
        setting_type=SiteSettingType.IMAGE,
        value="same.jpg",
    )
    monkeypatch.setattr(
        admin_service,
        "db_query_one",
        lambda sql, data: {"Value": "same.jpg"},
    )
    monkeypatch.setattr(admin_service, "db_update", lambda sql, data: True)
    removed = []
    monkeypatch.setattr(
        admin_service,
        "remove_file",
        lambda file_name, bucket_name: removed.append((file_name, bucket_name)),
    )

    success = admin_service.AdminService().update_setting(setting)

    assert success is True
    assert not removed


def test_update_setting_updates_existing_image_without_original_row(monkeypatch):
    """
    Test that update_setting skips file cleanup when the original image row is missing.
    """
    setting = create_site_setting(
        setting_id=5,
        setting_type=SiteSettingType.IMAGE,
        value="new.jpg",
    )
    removed = []
    monkeypatch.setattr(admin_service, "db_query_one", lambda sql, data: None)
    monkeypatch.setattr(admin_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        admin_service,
        "remove_file",
        lambda file_name, bucket_name: removed.append((file_name, bucket_name)),
    )

    success = admin_service.AdminService().update_setting(setting)

    assert success is True
    assert not removed


def test_get_ticket_socket_accounts_maps_ticket_socket_service_objects(monkeypatch):
    """
    Test that get_ticket_socket_accounts maps TicketSocketService data into accounts.
    """
    FakeTicketSocketService.instances = []
    FakeTicketSocketService.categories_by_id = {1: ["A"], 2: ["B", "C"]}
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql: [{"TicketSocketId": 1}, {"TicketSocketId": 2}],
    )
    monkeypatch.setattr(
        admin_service,
        "TicketSocketService",
        FakeTicketSocketService,
    )

    accounts = admin_service.AdminService().get_ticket_socket_accounts()

    assert [account.ticket_socket_id for account in accounts] == [1, 2]
    assert accounts[0].name == "Account 1"
    assert accounts[1].categories == ["B", "C"]


def test_get_all_accounts_returns_ticket_socket_service_instances(monkeypatch):
    """
    Test that get_all_accounts returns TicketSocketService instances for each row.
    """
    FakeTicketSocketService.instances = []
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql: [{"TicketSocketId": 3}, {"TicketSocketId": 4}],
    )
    monkeypatch.setattr(
        admin_service,
        "TicketSocketService",
        FakeTicketSocketService,
    )

    accounts = admin_service.AdminService().get_all_accounts()

    assert [account.ticket_socket_id for account in accounts] == [3, 4]


def test_get_external_venues_maps_country_timezones_and_search_sql(monkeypatch):
    """
    Test that get_external_venues maps venue rows and adds country timezones.
    """
    calls = []
    timezone = Timezone()
    timezone.timezone = "America/Chicago"
    timezone.display_name = "America/Chicago (CDT)"

    def fake_db_query_all(sql):
        calls.append(sql)
        return [
            {
                "VenueID": 7,
                "Venue": "The Arena",
                "Address": "123 Main",
                "City": "Nashville",
                "State": "TN",
                "Zip": "37011",
                "CountryId": 1,
                "TimeZone": "America/Chicago",
                "CountryName": "USA",
                "CountryCode": "US",
                "HasEvents": 1,
            }
        ]

    monkeypatch.setattr(admin_service, "db_query_all", fake_db_query_all)
    monkeypatch.setattr(
        admin_service,
        "get_timezones_from_country_code",
        lambda country_code: [timezone],
    )

    venues = admin_service.AdminService().get_external_venues("Nash")

    assert len(venues) == 1
    assert venues[0].venue_id == 7
    assert venues[0].country.country_code == "US"
    assert venues[0].country.timezones == [timezone]
    assert venues[0].has_events is True
    assert "LIKE ('%Nash%')" in calls[0]


def test_get_external_venues_ignores_short_search_terms(monkeypatch):
    """
    Test that get_external_venues does not add a search filter for short terms.
    """
    calls = []

    def fake_db_query_all(sql):
        calls.append(sql)
        return [
            {
                "VenueID": 2,
                "Venue": "Club",
                "Address": "123 Main",
                "City": "Austin",
                "State": "TX",
                "Zip": "73301",
                "CountryId": None,
                "TimeZone": "America/Chicago",
                "CountryName": None,
                "CountryCode": None,
                "HasEvents": 0,
            }
        ]

    monkeypatch.setattr(admin_service, "db_query_all", fake_db_query_all)

    venues = admin_service.AdminService().get_external_venues("Au")

    assert len(venues) == 1
    assert venues[0].country is None
    assert venues[0].has_events is False
    assert "LIKE ('%Au%')" not in calls[0]


def test_update_external_venue_inserts_new_venue(monkeypatch):
    """
    Test that update_external_venue inserts a new venue and sets its id.
    """
    calls = []
    venue = create_external_venue(venue_id=0)
    monkeypatch.setenv("DEFAULT_COUNTRY_ID", "55")

    def fake_db_insert(sql, data):
        calls.append((sql, data))
        return 77

    monkeypatch.setattr(admin_service, "db_insert", fake_db_insert)

    updated_venue = admin_service.AdminService().update_external_venue(venue)

    assert updated_venue is venue
    assert venue.venue_id == 77
    assert "INSERT INTO ExternalEventVenues" in calls[0][0]
    assert calls[0][1]["venue"] == "The Arena"


def test_update_external_venue_updates_existing_venue(monkeypatch):
    """
    Test that update_external_venue updates an existing venue.
    """
    calls = []
    venue = create_external_venue(venue_id=8)

    def fake_db_update(sql, data):
        calls.append((sql, data))
        return True

    monkeypatch.setattr(admin_service, "db_update", fake_db_update)

    updated_venue = admin_service.AdminService().update_external_venue(venue)

    assert updated_venue is venue
    assert "UPDATE ExternalEventVenues" in calls[0][0]
    assert calls[0][1]["venue_id"] == 8


def test_update_external_venue_returns_none_when_update_fails(monkeypatch):
    """
    Test that update_external_venue returns None when persistence fails.
    """
    venue = create_external_venue(venue_id=8)
    monkeypatch.setattr(admin_service, "db_update", lambda sql, data: False)

    assert admin_service.AdminService().update_external_venue(venue) is None


def test_update_external_venue_uses_default_country_when_missing(monkeypatch):
    """
    Test that update_external_venue falls back to the default country id when missing.
    """
    calls = []
    venue = create_external_venue(venue_id=8)
    venue.country = None
    monkeypatch.setenv("DEFAULT_COUNTRY_ID", "55")

    def fake_db_update(sql, data):
        calls.append((sql, data))
        return True

    monkeypatch.setattr(admin_service, "db_update", fake_db_update)

    updated_venue = admin_service.AdminService().update_external_venue(venue)

    assert updated_venue is venue
    assert calls[0][1]["country_id"] == 55


def test_update_external_venue_uses_default_country_when_country_id_is_missing(
    monkeypatch,
):
    """
    Test that update_external_venue falls back to the default country id when the country object has no id.
    """
    calls = []
    venue = create_external_venue(venue_id=8)
    venue.country = Country(None, "USA", "US")
    monkeypatch.setenv("DEFAULT_COUNTRY_ID", "55")

    def fake_db_update(sql, data):
        calls.append((sql, data))
        return True

    monkeypatch.setattr(admin_service, "db_update", fake_db_update)

    updated_venue = admin_service.AdminService().update_external_venue(venue)

    assert updated_venue is venue
    assert calls[0][1]["country_id"] == 55


def test_delete_external_venue_deletes_row(monkeypatch):
    """
    Test that delete_external_venue deletes the requested venue id.
    """
    calls = []
    monkeypatch.setattr(
        admin_service,
        "db_delete",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = admin_service.AdminService().delete_external_venue(15)

    assert success is True
    assert calls[0][1] == {"venue_id": 15}


def test_get_all_countries_filters_by_code_and_skips_missing_country_codes(monkeypatch):
    """
    Test that get_all_countries skips rows without country codes and adds timezones.
    """
    calls = []
    timezone = Timezone()
    timezone.timezone = "America/New_York"
    timezone.display_name = "America/New_York (EST)"

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        return [
            {"CountryId": 1, "CountryName": "USA", "CountryCode": "US"},
            {"CountryId": 2, "CountryName": "Unknown", "CountryCode": None},
        ]

    monkeypatch.setattr(admin_service, "db_query_all", fake_db_query_all)
    monkeypatch.setattr(
        admin_service,
        "get_timezones_from_country_code",
        lambda country_code: [timezone],
    )

    countries = admin_service.AdminService().get_all_countries("US")

    assert len(countries) == 1
    assert countries[0].country_name == "USA"
    assert countries[0].timezones == [timezone]
    assert calls[0][1] == {"country_code": "US"}


def test_get_all_countries_uses_default_query_without_country_code(monkeypatch):
    """
    Test that get_all_countries omits the filter when no country code is provided.
    """
    calls = []
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [{"CountryId": 1, "CountryName": "USA", "CountryCode": "US"}],
    )
    monkeypatch.setattr(
        admin_service,
        "get_timezones_from_country_code",
        lambda country_code: [],
    )

    countries = admin_service.AdminService().get_all_countries()

    assert len(countries) == 1
    assert calls[0][1] == {}
    assert "WHERE CountryCode=%(country_code)s" not in calls[0][0]


def test_get_ticket_socket_refresh_history_maps_rows_to_history_objects(monkeypatch):
    """
    Test that get_ticket_socket_refresh_history maps refresh rows and usernames.
    """
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql: [
            {
                "UserId": 0,
                "UserName": None,
                "Email": None,
                "SellerId": 5,
                "SellerName": "Band A",
                "Start": 1,
                "End": 2,
                "StartTimer": 10,
                "EndTimer": 20,
                "Duration": 2.5,
                "Success": 1,
                "ErrorMessage": None,
                "ServiceEventsSkipped": "1, 2",
                "EventsFailed": "3",
                "OrdersFailed": "4",
                "TicketsFailed": "5",
                "TicketTypesFailed": "6",
                "TotalEventsFromService": 7,
                "EventsUpdated": 8,
                "EventsInserted": 9,
                "OrdersInserted": 10,
                "OrdersUpdated": 11,
                "OrdersDeleted": 12,
                "TicketsUpdated": 13,
                "TicketsInserted": 14,
                "TicketTypesUpdated": 15,
                "TicketTypesInserted": 16,
                "OrderDataUpdateSucceeded": 1,
                "OrderDataUpdateDuration": 3.5,
                "TotalDuration": 6.0,
                "OrderDataRowsTotal": 20,
                "OrderDataRowsInserted": 8,
                "OrderDataRowsUpdated": 9,
                "OrderDataRowsRemoved": 3,
            },
            {
                "UserId": 2,
                "UserName": "Ada Lovelace",
                "Email": "ada@example.com",
                "SellerId": 6,
                "SellerName": "Band B",
                "Start": 1,
                "End": 2,
                "StartTimer": 10,
                "EndTimer": 20,
                "Duration": 2.5,
                "Success": 0,
                "ErrorMessage": "bad",
                "ServiceEventsSkipped": "",
                "EventsFailed": "",
                "OrdersFailed": "",
                "TicketsFailed": "",
                "TicketTypesFailed": "",
                "TotalEventsFromService": 1,
                "EventsUpdated": 2,
                "EventsInserted": 3,
                "OrdersInserted": 4,
                "OrdersUpdated": 5,
                "OrdersDeleted": 6,
                "TicketsUpdated": 7,
                "TicketsInserted": 8,
                "TicketTypesUpdated": 9,
                "TicketTypesInserted": 10,
                "OrderDataUpdateSucceeded": 0,
                "OrderDataUpdateDuration": 1.5,
                "TotalDuration": 4.0,
                "OrderDataRowsTotal": 11,
                "OrderDataRowsInserted": 2,
                "OrderDataRowsUpdated": 3,
                "OrderDataRowsRemoved": 1,
            },
        ],
    )

    history = admin_service.AdminService().get_ticket_socket_refresh_history()

    assert len(history) == 2
    assert history[0].username == "System"
    assert history[0].seller_name == "Band A"
    assert history[0].order_data_rows_total == 20
    assert history[1].username == "Ada Lovelace (ada@example.com)"
    assert history[1].succeeded is False


def test_get_ticket_socket_events_only_maps_ticket_socket_events(monkeypatch):
    """
    Test that get_ticket_socket_events_only maps event rows and timezone data.
    """
    country = Country(1, "USA", "US")
    timezone = Timezone()
    timezone.timezone = "America/Chicago"
    timezone.display_name = "America/Chicago (CDT)"
    calls = []

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        return [
            {
                "Id": 8,
                "IsVisibleOnSite": 1,
                "IsVisibleOnPortal": 0,
                "EventId": 444,
                "Title": "VIP Night",
                "EventDate": "2026-05-01",
                "Thumbnail": "thumb.jpg",
                "URL": "https://event",
                "State": "TN",
                "Zip": "37011",
                "Country": "USA",
                "Venue": "Arena",
                "Address": "123 Main",
                "City": "Nashville",
                "IsVip": 1,
                "IsSoldOut": 0,
            }
        ]

    monkeypatch.setattr(admin_service, "db_query_all", fake_db_query_all)
    monkeypatch.setattr(
        admin_service,
        "get_country_from_country_name",
        lambda country_name, state, zip_code: country,
    )
    monkeypatch.setattr(
        admin_service,
        "get_timezones_from_country_code",
        lambda country_code, event_date=None: [timezone],
    )

    events = admin_service.AdminService().get_ticket_socket_events_only(44)

    assert len(events) == 1
    assert events[0].ticket_socket_event_id == 8
    assert events[0].venue.country.timezones == [timezone]
    assert events[0].is_visible_on_portal is False
    assert calls[0][1] == {"seller_id": 44}


def test_get_ticket_socket_events_only_uses_placeholder_country_when_lookup_fails(
    monkeypatch,
):
    """
    Test that get_ticket_socket_events_only falls back to a placeholder country.
    """
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql, data: [
            {
                "Id": 8,
                "IsVisibleOnSite": 1,
                "IsVisibleOnPortal": 1,
                "EventId": 444,
                "Title": "VIP Night",
                "EventDate": "2026-05-01",
                "Thumbnail": "thumb.jpg",
                "URL": "https://event",
                "State": "TN",
                "Zip": "37011",
                "Country": "Unknownland",
                "Venue": "Arena",
                "Address": "123 Main",
                "City": "Nashville",
                "IsVip": 1,
                "IsSoldOut": 0,
            }
        ],
    )
    monkeypatch.setattr(
        admin_service,
        "get_country_from_country_name",
        lambda country_name, state, zip_code: None,
    )

    events = admin_service.AdminService().get_ticket_socket_events_only()

    assert events[0].venue.country.country_name == "Unknownland"
    assert events[0].venue.country.country_code is None


def test_cancel_event_returns_true_for_empty_event_ids():
    """
    Test that cancel_event returns True when there are no event ids to update.
    """
    assert admin_service.AdminService().cancel_event([]) is True


def test_cancel_event_updates_each_event_id(monkeypatch):
    """
    Test that cancel_event updates each event id with the cancelled SQL branch.
    """
    calls = []

    def fake_db_update(sql, data):
        calls.append((sql, data))
        return True

    monkeypatch.setattr(admin_service, "db_update", fake_db_update)

    success = admin_service.AdminService().cancel_event([10, 20], is_cancelled=True)

    assert success is True
    assert len(calls) == 2
    assert "IsCancelled=1" in calls[0][0]
    assert calls[1][1]["event_id"] == 20
    assert len(calls[1][1]["cancelled_date"]) == 10


def test_cancel_event_uses_uncancel_sql_branch(monkeypatch):
    """
    Test that cancel_event clears the cancelled flag when requested.
    """
    calls = []
    monkeypatch.setattr(
        admin_service,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = admin_service.AdminService().cancel_event([10], is_cancelled=False)

    assert success is True
    assert "IsCancelled=0" in calls[0][0]


def test_refund_all_event_orders_refunds_orders_and_rebuilds_dashboard(monkeypatch):
    """
    Test that refund_all_event_orders refunds each order and rebuilds the dashboard.
    """
    FakeOrderService.instances = []
    FakeOrderService.refund_results = [True, True]
    FakeDashboardService.instances = []
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql, data: [
            {"OrderId": 11, "EventId": 222},
            {"OrderId": 12, "EventId": 222},
        ],
    )
    monkeypatch.setattr(admin_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(admin_service, "DashboardService", FakeDashboardService)

    success = admin_service.AdminService().refund_all_event_orders(
        event_id=7,
        refund_service_fees=True,
    )

    assert success is True
    assert FakeOrderService.instances[0].calls == [(11, True, False)]
    assert FakeOrderService.instances[1].calls == [(12, True, False)]
    assert FakeDashboardService.instances[0].rebuild_calls == [222]


def test_refund_all_event_orders_stops_on_first_failed_refund(monkeypatch):
    """
    Test that refund_all_event_orders stops and skips rebuild when a refund fails.
    """
    FakeOrderService.instances = []
    FakeOrderService.refund_results = [False, True]
    FakeDashboardService.instances = []
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql, data: [
            {"OrderId": 11, "EventId": 222},
            {"OrderId": 12, "EventId": 222},
        ],
    )
    monkeypatch.setattr(admin_service, "OrderService", FakeOrderService)
    monkeypatch.setattr(admin_service, "DashboardService", FakeDashboardService)

    success = admin_service.AdminService().refund_all_event_orders(event_id=7)

    assert success is False
    assert len(FakeOrderService.instances) == 1
    assert not FakeDashboardService.instances


def test_refund_all_event_orders_marks_event_cancelled_first(monkeypatch):
    """
    Test that refund_all_event_orders passes the event id through cancel_event as a list.
    """
    calls = []
    monkeypatch.setattr(
        admin_service.AdminService,
        "cancel_event",
        lambda self, event_ids, is_cancelled=False: calls.append(
            (event_ids, is_cancelled)
        )
        or True,
    )
    monkeypatch.setattr(admin_service, "db_query_all", lambda sql, data: [])

    success = admin_service.AdminService().refund_all_event_orders(
        event_id=9,
        mark_cancelled=True,
    )

    assert success is True
    assert calls == [([9], True)]


def test_refund_all_event_orders_returns_cancel_failure_without_querying_orders(
    monkeypatch,
):
    """
    Test that refund_all_event_orders stops immediately when cancel_event fails.
    """
    query_calls = []
    monkeypatch.setattr(
        admin_service.AdminService,
        "cancel_event",
        lambda self, event_ids, is_cancelled=False: False,
    )
    monkeypatch.setattr(
        admin_service,
        "db_query_all",
        lambda sql, data: query_calls.append((sql, data)) or [],
    )

    success = admin_service.AdminService().refund_all_event_orders(
        event_id=9,
        mark_cancelled=True,
    )

    assert success is False
    assert not query_calls


def test_refund_all_event_orders_skips_dashboard_rebuild_without_orders(monkeypatch):
    """
    Test that refund_all_event_orders returns true without rebuilding when there are no orders.
    """
    FakeDashboardService.instances = []
    monkeypatch.setattr(admin_service, "db_query_all", lambda sql, data: [])
    monkeypatch.setattr(admin_service, "DashboardService", FakeDashboardService)

    success = admin_service.AdminService().refund_all_event_orders(event_id=7)

    assert success is True
    assert not FakeDashboardService.instances


def test_send_list_to_band_marks_event_sent_and_returns_updated_event(monkeypatch):
    """
    Test that send_list_to_band updates the event and returns the refreshed event.
    """
    FakeEventService.instances = []
    updated_event = VipEvent()
    updated_event.external_event_id = 5
    FakeEventService.events_to_return = [updated_event]
    update_calls = []
    monkeypatch.setattr(
        admin_service,
        "db_query_one",
        lambda sql, data: {"NumVips": 14},
    )
    monkeypatch.setattr(
        admin_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(admin_service, "EventService", FakeEventService)

    result = admin_service.AdminService().send_list_to_band(5, True)

    assert result is updated_event
    assert update_calls[0][1]["numVips"] == 14
    assert update_calls[0][1]["listSent"] == 1
    assert "ListSentTime=CURRENT_TIMESTAMP" in update_calls[0][0]


def test_send_list_to_band_clears_timestamp_when_not_sent(monkeypatch):
    """
    Test that send_list_to_band clears the sent timestamp when the list is unsent.
    """
    FakeEventService.instances = []
    FakeEventService.events_to_return = []
    update_calls = []
    monkeypatch.setattr(
        admin_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(admin_service, "EventService", FakeEventService)

    result = admin_service.AdminService().send_list_to_band(5, False)

    assert result is None
    assert update_calls[0][1]["numVips"] == 0
    assert update_calls[0][1]["listSent"] == 0
    assert "ListSentTime=NULL" in update_calls[0][0]


def test_send_list_to_band_uses_zero_vips_when_count_row_is_missing(monkeypatch):
    """
    Test that send_list_to_band keeps the VIP count at zero when no count row exists.
    """
    update_calls = []
    monkeypatch.setattr(admin_service, "db_query_one", lambda sql, data: None)
    monkeypatch.setattr(
        admin_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or False,
    )

    result = admin_service.AdminService().send_list_to_band(5, True)

    assert result is None
    assert update_calls[0][1]["numVips"] == 0


def test_send_list_to_band_returns_none_when_event_refresh_is_empty(monkeypatch):
    """
    Test that send_list_to_band returns None when the event refresh yields no rows.
    """
    FakeEventService.instances = []
    FakeEventService.events_to_return = []
    monkeypatch.setattr(
        admin_service,
        "db_query_one",
        lambda sql, data: {"NumVips": 2},
    )
    monkeypatch.setattr(admin_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(admin_service, "EventService", FakeEventService)

    result = admin_service.AdminService().send_list_to_band(5, True)

    assert result is None


def test_update_event_returns_false_when_event_is_none():
    """
    Test that update_event returns False when no event is provided.
    """
    assert admin_service.AdminService().update_event(None) is False


def test_update_event_updates_existing_event_and_ticket_types(monkeypatch):
    """
    Test that update_event updates the event and ticket types in sorted order.
    """
    FakeEventService.instances = []
    FakeDashboardService.instances = []
    existing_event = VipEvent()
    existing_event.external_event_id = 12
    FakeEventService.events_to_return = [existing_event]
    update_calls = []
    event = create_vip_event(external_event_id=12, ticket_socket_event_id=99)
    event.ticket_types = [
        TicketSocketTicketType(99, 200, "B", 10, True, 2),
        TicketSocketTicketType(99, 100, "A", 10, False, 1),
    ]

    def fake_db_update(sql, data):
        update_calls.append((sql, data))
        return True

    monkeypatch.setattr(admin_service, "EventService", FakeEventService)
    monkeypatch.setattr(admin_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(admin_service, "db_update", fake_db_update)

    success = admin_service.AdminService().update_event(event)

    assert success is True
    assert "UPDATE ExternalEvents" in update_calls[0][0]
    assert update_calls[1][1]["ticket_type_id"] == 100
    assert update_calls[1][1]["order"] == 1
    assert update_calls[2][1]["ticket_type_id"] == 200
    assert update_calls[2][1]["order"] == 2
    assert FakeDashboardService.instances[0].rebuild_calls == [99]


def test_update_event_inserts_new_event_and_skips_rebuild_without_ticket_types(
    monkeypatch,
):
    """
    Test that update_event inserts a new event and skips rebuild without ticket types.
    """
    event = create_vip_event(external_event_id=0, ticket_socket_event_id=-1)
    event.ticket_types = []
    insert_calls = []
    monkeypatch.setattr(
        admin_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 88,
    )

    success = admin_service.AdminService().update_event(event)

    assert success is True
    assert "INSERT INTO ExternalEvents" in insert_calls[0][0]
    assert insert_calls[0][1]["ticket_socket_event_id"] is None


def test_update_event_inserts_new_event_with_ticket_types_and_rebuilds(monkeypatch):
    """
    Test that update_event updates ticket types and rebuilds after inserting a new event.
    """
    FakeDashboardService.instances = []
    update_calls = []
    event = create_vip_event(external_event_id=0, ticket_socket_event_id=99)
    event.ticket_types = [TicketSocketTicketType(99, 100, "VIP", 10, True, 1)]
    monkeypatch.setattr(admin_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(admin_service, "db_insert", lambda sql, data: 88)
    monkeypatch.setattr(
        admin_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = admin_service.AdminService().update_event(event)

    assert success is True
    assert len(update_calls) == 1
    assert update_calls[0][1]["ticket_type_id"] == 100
    assert FakeDashboardService.instances[0].rebuild_calls == [99]


def test_update_event_inserts_new_event_without_refreshing_existing_event(monkeypatch):
    """
    Test that update_event skips the existing-event lookup when the external id is not positive.
    """
    calls = []
    event = create_vip_event(external_event_id=0, ticket_socket_event_id=-1)
    monkeypatch.setattr(
        admin_service,
        "EventService",
        lambda: calls.append("event_service") or FakeEventService(),
    )
    monkeypatch.setattr(admin_service, "db_insert", lambda sql, data: 77)

    success = admin_service.AdminService().update_event(event)

    assert success is True
    assert not calls


def test_update_event_uses_insert_path_when_existing_event_lookup_is_empty(monkeypatch):
    """
    Test that update_event inserts when the existing-event lookup returns no rows.
    """
    FakeEventService.instances = []
    FakeEventService.events_to_return = []
    event = create_vip_event(external_event_id=12, ticket_socket_event_id=-1)
    insert_calls = []
    monkeypatch.setattr(admin_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        admin_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 77,
    )

    success = admin_service.AdminService().update_event(event)

    assert success is True
    assert "INSERT INTO ExternalEvents" in insert_calls[0][0]


def test_update_event_stops_when_ticket_type_update_fails(monkeypatch):
    """
    Test that update_event stops ticket type updates and skips rebuild on failure.
    """
    FakeEventService.instances = []
    FakeDashboardService.instances = []
    existing_event = VipEvent()
    existing_event.external_event_id = 12
    FakeEventService.events_to_return = [existing_event]
    event = create_vip_event(external_event_id=12, ticket_socket_event_id=99)
    event.ticket_types = [
        TicketSocketTicketType(99, 100, "A", 10, True, 1),
        TicketSocketTicketType(99, 200, "B", 10, True, 2),
    ]
    call_counter = {"count": 0}

    def fake_db_update(sql, data):  # pylint: disable=unused-argument
        call_counter["count"] += 1
        return call_counter["count"] != 2

    monkeypatch.setattr(admin_service, "EventService", FakeEventService)
    monkeypatch.setattr(admin_service, "DashboardService", FakeDashboardService)
    monkeypatch.setattr(admin_service, "db_update", fake_db_update)

    success = admin_service.AdminService().update_event(event)

    assert success is False
    assert not FakeDashboardService.instances
