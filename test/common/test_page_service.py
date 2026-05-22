"""
Unit tests for common.page_service helpers.
"""

from datetime import datetime

from common import page_service
from common.models.admin import Page, PageSeller, PageType
from common.models.national_acts import VipEvent
from common.models.ticket_socket import Country


class FakeEventService:
    """
    Test double for page event lookups.
    """

    instances = []
    events_by_seller_id = {}

    def __init__(self):
        self.calls = []
        FakeEventService.instances.append(self)

    def get_events_and_orders(self, **kwargs):
        """
        Return the configured events for a seller id.
        """
        self.calls.append(kwargs)
        seller_id = kwargs.get("seller_id")
        return FakeEventService.events_by_seller_id.get(seller_id, [])


def create_page_type(page_type_id=7, name="Artist"):
    """
    Create a PageType instance for tests.
    """
    page_type = PageType()
    page_type.page_type_id = page_type_id
    page_type.page_type_name = name
    return page_type


def create_page(page_id=1, route="vip-night", page_type_id=7):
    """
    Create a Page instance for tests.
    """
    page = Page()
    page.page_id = page_id
    page.route = route
    page.title = "VIP Night"
    page.page_type = create_page_type(page_type_id=page_type_id)
    page.image = "new-header.jpg"
    page.thumbnail = "new-thumb.jpg"
    page.link_preview_image = "new-preview.jpg"
    page.logo_only_image = "new-logo.jpg"
    page.title1 = "Title 1"
    page.subtitle1 = "Subtitle 1"
    page.title2 = "Title 2"
    page.subtitle2 = "Subtitle 2"
    page.html_text = "<p>Hello</p>"
    page.is_active = True
    page.use_include_dates = True
    page.include_start = "2026-04-01 00:00:00"
    page.include_end = "2026-04-30 00:00:00"
    page.use_exclude_dates = True
    page.exclude_start = "2026-04-10 00:00:00"
    page.exclude_end = "2026-04-12 00:00:00"
    page.google_analytics_id = "GA-1"
    page.extra_html_head = "<meta>"
    page.extra_html_body = "<script>"
    page.page_order = 2
    page.sellers = []
    page.events = []
    return page


def create_page_seller(page_seller_id=1, seller_id=101, display_name="Featured Artist"):
    """
    Create a PageSeller instance for tests.
    """
    seller = PageSeller()
    seller.page_seller_id = page_seller_id
    seller.page_id = 1
    seller.seller_id = seller_id
    seller.display_name = display_name
    seller.show_display_name = True
    seller.address = "123 Main"
    seller.city = "Austin"
    seller.state = "TX"
    seller.zip = "73301"
    seller.country = Country(1, "USA", "US")
    seller.phone = "555-1111"
    seller.email = "artist@example.com"
    seller.twitter = "@artist"
    seller.facebook = "artist-fb"
    seller.instagram = "@artist-ig"
    seller.youtube = "artist-yt"
    seller.spotify = "artist-sp"
    seller.website = "https://artist.example.com"
    seller.website_display_text = "Artist Site"
    return seller


def create_event(event_date, event_time, meet_and_greet_time, title):
    """
    Create a VipEvent instance for page event sorting tests.
    """
    event = VipEvent()
    event.event_date = event_date
    event.event_time = event_time
    event.meet_and_greet_time = meet_and_greet_time
    event.title = title
    return event


def build_page_row(**overrides):
    """
    Create a page row for page mapping tests.
    """
    row = {
        "PageID": 1,
        "Inactive": 0,
        "Route": "vip-night",
        "Title": "VIP Night",
        "PageOrder": 2,
        "Image": "header.jpg",
        "Thumbnail": "thumb.jpg",
        "LinkPreviewImage": "preview.jpg",
        "LogoOnly": "logo.jpg",
        "Title1": "Title 1",
        "SubTitle1": "Subtitle 1",
        "Title2": "Title 2",
        "SubTitle2": "Subtitle 2",
        "HTMLText": "<p>Hello</p>",
        "ExtraHTMLHead": "<meta>",
        "ExtraHTMLBody": "<script>",
        "UseIncludeDates": 1,
        "IncludeStart": "2026-04-01 00:00:00",
        "IncludeEnd": "2026-04-30 00:00:00",
        "UseExcludeDates": 1,
        "ExcludeStart": "2026-04-10 00:00:00",
        "ExcludeEnd": "2026-04-12 00:00:00",
        "GoogleAnalyticsID": "GA-1",
        "LastUpdated": "2026-04-23 10:00:00",
        "PageTypeID": 7,
        "PageTypeName": "Artist",
    }
    row.update(overrides)
    return row


def build_page_seller_row(**overrides):
    """
    Create a page seller row for seller mapping tests.
    """
    row = {
        "PageSellerId": 1,
        "SellerId": 101,
        "PageId": 1,
        "DisplayName": "Featured Artist",
        "ShowDisplayName": 1,
        "AddressOverride": "123 Override",
        "CityOverride": "Austin",
        "StateOverride": "TX",
        "ZipOverride": "73301",
        "CountryIdOverride": 1,
        "PhoneOverride": "555-1111",
        "EmailOverride": "artist@example.com",
        "TwitterOverride": "@artist",
        "FacebookOverride": "artist-fb",
        "InstagramOverride": "@artist-ig",
        "YouTubeOverride": "artist-yt",
        "SpotifyOverride": "artist-sp",
        "WebsiteOverride": "https://artist.example.com",
        "WebsiteDisplayTextOverride": "Artist Site",
        "CountryNameOverride": "USA",
        "CountryCodeOverride": "US",
        "SellerName": "Seller Name",
        "Address": "123 Seller",
        "City": "Dallas",
        "State": "TX",
        "Zip": "75001",
        "CountryId": 2,
        "CountryName": "Canada",
        "CountryCode": "CA",
        "Phone": "555-2222",
        "Email": "seller@example.com",
        "Twitter": "@seller",
        "Facebook": "seller-fb",
        "Instagram": "@seller-ig",
        "YouTube": "seller-yt",
        "Spotify": "seller-sp",
        "Website": "https://seller.example.com",
        "WebsiteDisplayText": "Seller Site",
    }
    row.update(overrides)
    return row


def test_get_all_pages_maps_pages_and_loads_sellers_for_seller_types(monkeypatch):
    """
    Test that get_all_pages maps page rows and loads sellers for seller page types.
    """
    calls = []

    def fake_db_query_all(sql, data):
        calls.append((sql, data))
        if "FROM Pages" in sql:
            return [build_page_row(), build_page_row(PageID=2, PageTypeID=1)]
        return [
            build_page_seller_row(),
        ]

    monkeypatch.setattr(page_service, "db_query_all", fake_db_query_all)

    pages = page_service.PageService().get_all_pages(is_public=True, page_type_id=7)

    assert len(pages) == 2
    assert "Pages.PageTypeID=%(page_type_id)s" in calls[0][0]
    assert "Pages.Inactive=0" in calls[0][0]
    assert calls[0][1] == {"page_type_id": 7}
    assert len(pages[0].sellers) == 1
    assert pages[1].sellers == []


def test_get_all_pages_orders_seller_pages_by_page_order_for_admin_queries(monkeypatch):
    """
    Test that get_all_pages uses the seller-page admin ordering when a page type filter is present.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    pages = page_service.PageService().get_all_pages(page_type_id=7, is_public=False)

    assert not pages
    assert "AND Pages.Inactive=0" not in calls[0][0]
    assert "ORDER BY Pages.PageOrder ASC, Pages.LastUpdated DESC" in calls[0][0]


def test_get_all_pages_uses_public_filter_without_page_type_and_skips_invalid_rows(
    monkeypatch,
):
    """
    Test that get_all_pages uses the public-only query path and skips unmappable rows.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [build_page_row(PageID=0), build_page_row(PageID=2, PageTypeID=1)],
    )

    pages = page_service.PageService().get_all_pages(is_public=True)

    assert len(pages) == 1
    assert "WHERE Pages.Inactive=0" in calls[0][0]
    assert "ORDER BY Pages.Title ASC, Pages.Inactive DESC" in calls[0][0]
    assert calls[0][1] == {}


def test_get_all_pages_orders_non_public_pages_by_title_without_filters(monkeypatch):
    """
    Test that get_all_pages uses the default title ordering when no filters are supplied.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data)) or [],
    )

    pages = page_service.PageService().get_all_pages()

    assert not pages
    assert "Pages.Inactive=0" not in calls[0][0]
    assert "ORDER BY Pages.Title ASC, Pages.Inactive DESC" in calls[0][0]


def test_get_page_by_route_sanitizes_route_and_loads_sorted_events(monkeypatch):
    """
    Test that get_page_by_route sanitizes routes, loads sellers, and sorts seller events.
    """
    FakeEventService.instances = []
    FakeEventService.events_by_seller_id = {
        101: [
            create_event("2026-05-02", "20:00", "18:00", "B Event"),
            create_event("2026-05-01", "19:00", "17:00", "A Event"),
        ]
    }
    calls = []
    monkeypatch.setattr(page_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: calls.append((sql, data)) or build_page_row(),
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [create_page_seller()],
    )

    page = page_service.PageService().get_page_by_route(
        "vip:'\"night",
        is_website=True,
    )

    assert page is not None
    assert calls[0][1] == {"route": "vipnight"}
    assert page.sellers[0].seller_id == 101
    assert [event.title for event in page.events] == ["A Event", "B Event"]
    event_call = FakeEventService.instances[0].calls[0]
    assert event_call["is_public"] is True
    assert event_call["seller_id"] == 101
    assert event_call["is_website"] is True
    assert (
        event_call["start"]
        == datetime.strptime("2026-04-01 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
    )
    assert event_call["exclude_start"] == (
        datetime.strptime("2026-04-10 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
        + 7 * 60 * 60
    )


def test_get_page_by_route_returns_none_when_page_is_missing(monkeypatch):
    """
    Test that get_page_by_route returns None when the route lookup is missing.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: calls.append((sql, data)) or None,
    )

    page = page_service.PageService().get_page_by_route("vip-night", show_inactive=True)

    assert page is None
    assert "AND Pages.Inactive = 0" not in calls[0][0]


def test_get_page_by_route_skips_seller_loading_for_non_seller_page_types(monkeypatch):
    """
    Test that get_page_by_route does not load page sellers for non-seller page types.
    """
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: build_page_row(PageTypeID=1),
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: (_ for _ in ()).throw(
            AssertionError("get_page_sellers should not be called")
        ),
    )

    page = page_service.PageService().get_page_by_route("vip-night")

    assert page is not None
    assert page.page_type.page_type_id == 1
    assert not page.sellers


def test_get_page_by_route_handles_pages_without_sellers(monkeypatch):
    """
    Test that get_page_by_route leaves page events empty when a seller page has no sellers.
    """
    FakeEventService.instances = []
    monkeypatch.setattr(page_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: build_page_row(),
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [],
    )

    page = page_service.PageService().get_page_by_route("vip-night")

    assert page is not None
    assert not page.sellers
    assert not page.events
    assert not FakeEventService.instances[0].calls


def test_get_page_by_route_uses_partial_date_filters(monkeypatch):
    """
    Test that get_page_by_route passes through partial include and exclude date windows.
    """
    FakeEventService.instances = []
    FakeEventService.events_by_seller_id = {101: []}
    monkeypatch.setattr(page_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: build_page_row(
            IncludeEnd=None,
            ExcludeEnd=None,
        ),
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [create_page_seller()],
    )

    page = page_service.PageService().get_page_by_route("vip-night")

    assert page is not None
    event_call = FakeEventService.instances[0].calls[0]
    assert (
        event_call["start"]
        == datetime.strptime("2026-04-01 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
    )
    assert event_call["end"] is None
    assert event_call["exclude_start"] == (
        datetime.strptime("2026-04-10 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
        + 7 * 60 * 60
    )
    assert event_call["exclude_end"] is None
    assert not page.events


def test_get_page_by_route_skips_date_windows_when_disabled(monkeypatch):
    """
    Test that get_page_by_route sends no date windows when include and exclude ranges are disabled.
    """
    FakeEventService.instances = []
    FakeEventService.events_by_seller_id = {101: []}
    monkeypatch.setattr(page_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: build_page_row(
            UseIncludeDates=0,
            UseExcludeDates=0,
        ),
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [create_page_seller()],
    )

    page = page_service.PageService().get_page_by_route("vip-night")

    assert page is not None
    event_call = FakeEventService.instances[0].calls[0]
    assert event_call["start"] is None
    assert event_call["end"] is None
    assert event_call["exclude_start"] is None
    assert event_call["exclude_end"] is None


def test_get_page_by_route_uses_end_only_date_windows(monkeypatch):
    """
    Test that get_page_by_route can pass only include-end and exclude-end values.
    """
    FakeEventService.instances = []
    FakeEventService.events_by_seller_id = {101: []}
    monkeypatch.setattr(page_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        page_service,
        "db_query_one",
        lambda sql, data: build_page_row(
            IncludeStart=None,
            ExcludeStart=None,
        ),
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [create_page_seller()],
    )

    page = page_service.PageService().get_page_by_route("vip-night")

    assert page is not None
    event_call = FakeEventService.instances[0].calls[0]
    assert event_call["start"] is None
    assert (
        event_call["end"]
        == datetime.strptime("2026-04-30 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
    )
    assert event_call["exclude_start"] is None
    assert event_call["exclude_end"] == (
        datetime.strptime("2026-04-12 00:00:00", "%Y-%m-%d %H:%M:%S").timestamp()
        + 7 * 60 * 60
    )


def test_get_page_sellers_uses_public_defaults_when_overrides_are_missing(monkeypatch):
    """
    Test that get_page_sellers falls back to seller defaults for public pages.
    """
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql, data: [
            build_page_seller_row(
                DisplayName=None,
                ShowDisplayName=0,
                AddressOverride=None,
                CityOverride=None,
                StateOverride=None,
                ZipOverride=None,
                CountryIdOverride=None,
                CountryNameOverride=None,
                CountryCodeOverride=None,
                PhoneOverride=None,
                EmailOverride=None,
                TwitterOverride=None,
                FacebookOverride=None,
                InstagramOverride=None,
                YouTubeOverride=None,
                SpotifyOverride=None,
                WebsiteOverride=None,
                WebsiteDisplayTextOverride=None,
            ),
            build_page_seller_row(PageSellerId=0),
        ],
    )

    sellers = page_service.PageService().get_page_sellers(1, is_public=True)

    assert len(sellers) == 1
    assert sellers[0].display_name == "Seller Name"
    assert sellers[0].address == "123 Seller"
    assert sellers[0].city == "Dallas"
    assert sellers[0].country.country_id == 2
    assert sellers[0].country.country_code == "CA"
    assert sellers[0].phone == "555-2222"
    assert sellers[0].website == "https://seller.example.com"


def test_get_page_sellers_uses_override_values_for_non_public_pages(monkeypatch):
    """
    Test that get_page_sellers keeps override values and can omit country data for non-public pages.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [
            build_page_seller_row(
                DisplayName=None,
                CountryIdOverride=None,
                CountryNameOverride=None,
                CountryCodeOverride=None,
            )
        ],
    )

    sellers = page_service.PageService().get_page_sellers(1, is_public=False)

    assert len(sellers) == 1
    assert "AND Inactive = 0" not in calls[0][0]
    assert sellers[0].display_name is None
    assert sellers[0].country is None
    assert sellers[0].address == "123 Override"
    assert sellers[0].phone == "555-1111"


def test_get_page_sellers_uses_display_name_for_public_pages_when_requested(
    monkeypatch,
):
    """
    Test that get_page_sellers keeps the explicit display name on public pages when allowed.
    """
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql, data: [build_page_seller_row()],
    )

    sellers = page_service.PageService().get_page_sellers(1, is_public=True)

    assert len(sellers) == 1
    assert sellers[0].display_name == "Featured Artist"


def test_update_page_updates_existing_page_cleans_images_and_syncs_sellers(monkeypatch):
    """
    Test that update_page updates page data, removes replaced images, and syncs sellers.
    """
    update_calls = []
    insert_calls = []
    delete_calls = []
    removed_files = []

    page_to_update = create_page(page_id=1)
    existing_seller = create_page_seller(page_seller_id=1, seller_id=101)
    new_seller = create_page_seller(page_seller_id=0, seller_id=202, display_name="New")
    page_to_update.sellers = [existing_seller, new_seller]

    old_page = create_page(page_id=1)
    old_page.image = "old-header.jpg"
    old_page.thumbnail = "old-thumb.jpg"
    old_page.link_preview_image = "old-preview.jpg"
    old_page.logo_only_image = "old-logo.jpg"

    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: old_page,
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [
            existing_seller,
            create_page_seller(page_seller_id=3, seller_id=303, display_name="Delete"),
        ],
    )
    monkeypatch.setattr(
        page_service,
        "get_bucket_name_from_image_type",
        lambda image_type: f"bucket-{image_type}",
    )
    monkeypatch.setattr(
        page_service,
        "remove_file",
        lambda file_name, bucket_name: removed_files.append((file_name, bucket_name)),
    )
    monkeypatch.setattr(
        page_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        page_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 55,
    )
    monkeypatch.setattr(
        page_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is page_to_update
    assert removed_files == [
        ("old-header.jpg", "bucket-headers"),
        ("old-thumb.jpg", "bucket-thumbnails"),
        ("old-preview.jpg", "bucket-previews"),
        ("old-logo.jpg", "bucket-logos"),
    ]
    assert "UPDATE Pages SET" in update_calls[0][0]
    assert update_calls[1][1]["pageSellerId"] == 1
    assert insert_calls[0][1]["sellerId"] == 202
    assert delete_calls[0][1] == {"pageSellerId": 3}
    assert page_to_update.sellers[1].page_seller_id == 55


def test_update_page_returns_none_for_missing_pages_or_routes():
    """
    Test that update_page returns None for missing page objects or routes.
    """
    assert page_service.PageService().update_page(None) is None
    assert page_service.PageService().update_page(create_page(route=None)) is None


def test_update_page_returns_none_when_existing_page_update_fails(monkeypatch):
    """
    Test that update_page returns None when the main page update fails.
    """
    page_to_update = create_page(page_id=1)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: None,
    )
    monkeypatch.setattr(page_service, "db_update", lambda sql, data: False)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: (_ for _ in ()).throw(
            AssertionError("get_page_sellers should not be called")
        ),
    )

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is None


def test_update_page_returns_none_when_new_page_insert_fails(monkeypatch):
    """
    Test that update_page returns None when a new page insert fails.
    """
    page_to_update = create_page(page_id=0, route="new-page")
    page_to_update.sellers = [create_page_seller(page_seller_id=0, seller_id=101)]
    monkeypatch.setattr(page_service, "db_insert", lambda sql, data: 0)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: (_ for _ in ()).throw(
            AssertionError("get_page_sellers should not be called")
        ),
    )

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is None


def test_update_page_skips_seller_sync_when_no_sellers_are_provided(monkeypatch):
    """
    Test that update_page returns the page when there are no sellers to synchronize.
    """
    page_to_update = create_page(page_id=1)
    page_to_update.sellers = []
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: None,
    )
    monkeypatch.setattr(page_service, "db_update", lambda sql, data: True)

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is page_to_update


def test_update_page_skips_invalid_new_sellers_without_inserting(monkeypatch):
    """
    Test that update_page skips new sellers with non-positive seller ids.
    """
    insert_calls = []
    page_to_update = create_page(page_id=1)
    invalid_seller = create_page_seller(page_seller_id=0, seller_id=0)
    page_to_update.sellers = [invalid_seller]
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: None,
    )
    monkeypatch.setattr(page_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [],
    )
    monkeypatch.setattr(
        page_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 99,
    )

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is page_to_update
    assert not insert_calls


def test_update_page_returns_none_when_new_seller_insert_fails(monkeypatch):
    """
    Test that update_page returns None when inserting a new page seller fails.
    """
    page_to_update = create_page(page_id=1)
    page_to_update.sellers = [create_page_seller(page_seller_id=0, seller_id=202)]
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: None,
    )
    monkeypatch.setattr(page_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [],
    )
    monkeypatch.setattr(page_service, "db_insert", lambda sql, data: 0)

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is None


def test_update_page_returns_none_when_existing_seller_update_fails(monkeypatch):
    """
    Test that update_page stops and returns None when a seller update fails.
    """
    update_calls = []
    page_to_update = create_page(page_id=1)
    existing_seller = create_page_seller(page_seller_id=1, seller_id=101)
    page_to_update.sellers = [existing_seller]
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: None,
    )
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [existing_seller],
    )
    monkeypatch.setattr(
        page_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or (len(update_calls) == 1),
    )

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is None
    assert len(update_calls) == 2


def test_update_page_returns_none_when_seller_delete_fails(monkeypatch):
    """
    Test that update_page returns None when deleting an old seller fails.
    """
    page_to_update = create_page(page_id=1)
    page_to_update.sellers = [create_page_seller(page_seller_id=1, seller_id=101)]
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_by_route",
        lambda self, route, show_inactive=False, is_website=False: None,
    )
    monkeypatch.setattr(page_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [
            create_page_seller(page_seller_id=1, seller_id=101),
            create_page_seller(page_seller_id=2, seller_id=202),
        ],
    )
    monkeypatch.setattr(page_service, "db_delete", lambda sql, data: False)

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is None


def test_update_page_inserts_new_page_and_preserves_seller_country_id(monkeypatch):
    """
    Test that update_page inserts new pages and passes seller country ids on seller inserts.
    """
    insert_calls = []
    page_to_update = create_page(page_id=0, route="new-page")
    page_to_update.page_type = create_page_type(page_type_id=7)
    page_to_update.sellers = [create_page_seller(page_seller_id=0, seller_id=101)]

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "INSERT INTO Pages" in sql:
            return 10
        return 20

    monkeypatch.setattr(page_service, "db_insert", fake_db_insert)
    monkeypatch.setattr(page_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(page_service, "db_delete", lambda sql, data: True)
    monkeypatch.setattr(
        page_service.PageService,
        "get_page_sellers",
        lambda self, page_id, is_public=False: [],
    )

    updated_page = page_service.PageService().update_page(page_to_update)

    assert updated_page is page_to_update
    assert "INSERT INTO Pages" in insert_calls[0][0]
    assert insert_calls[1][1]["country_id"] == 1
    assert page_to_update.sellers[0].page_seller_id == 20


def test_get_all_page_types_can_filter_to_seller_types(monkeypatch):
    """
    Test that get_all_page_types can filter results down to seller page types.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql: calls.append(sql)
        or [
            {
                "PageTypeID": 7,
                "PageType": "Artist",
            }
        ],
    )

    page_types = page_service.PageService().get_all_page_types(seller_types_only=True)

    assert len(page_types) == 1
    assert page_types[0].page_type_id == 7
    assert "WHERE PageTypeID in" in calls[0]


def test_get_all_page_types_returns_all_page_types_without_filter(monkeypatch):
    """
    Test that get_all_page_types returns rows without a seller-type filter by default.
    """
    calls = []
    monkeypatch.setattr(
        page_service,
        "db_query_all",
        lambda sql: calls.append(sql)
        or [
            {
                "PageTypeID": 1,
                "PageType": "Standard",
            }
        ],
    )

    page_types = page_service.PageService().get_all_page_types()

    assert len(page_types) == 1
    assert "WHERE PageTypeID in" not in calls[0]


def test_update_seller_page_order_updates_only_seller_page_types(monkeypatch):
    """
    Test that update_seller_page_order skips non-seller types and stops on failures.
    """
    update_calls = []
    seller_page = create_page(page_id=1)
    seller_page.page_order = 3
    non_seller_page = create_page(page_id=2, page_type_id=1)
    non_seller_page.page_order = 4
    invalid_page = create_page(page_id=3)
    invalid_page.page_order = None
    results = iter([True, False])
    monkeypatch.setattr(
        page_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or next(results),
    )

    success = page_service.PageService().update_seller_page_order(
        [seller_page, non_seller_page, invalid_page, create_page(page_id=4)]
    )

    assert success is False
    assert len(update_calls) == 2
    assert update_calls[0][1] == {"page_order": 3, "page_id": 1}


def test_update_seller_page_order_returns_true_when_all_pages_are_skipped():
    """
    Test that update_seller_page_order returns True when every page is skipped.
    """
    skipped_page = create_page(page_id=1, page_type_id=1)
    skipped_page.page_order = None

    success = page_service.PageService().update_seller_page_order([skipped_page])

    assert success is True
