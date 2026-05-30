"""
Route tests for public and messaging API modules.
"""

import json
from io import BytesIO
from types import SimpleNamespace

import pytest

from app import app
from api import messaging_api, public_api


def build_service(**methods):
    """
    Create a simple service object for route tests.
    """
    return lambda: SimpleNamespace(**methods)


def test_public_faq_requires_api_key(client):
    """
    Return 401 when the public FAQ route is missing the API key.
    """
    response = client.get("/public/faq/0")

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_public_faq_returns_faqs_for_category(monkeypatch, client, parse_json_response):
    """
    Return faq data for a valid public API request.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "FaqService",
        build_service(
            get_faq_by_category_id=lambda category_id: [{"faqId": category_id}]
        ),
    )

    response = client.get(
        "/public/faq/7",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"faqId": 7}]


def test_public_faq_categories_returns_service_results(
    monkeypatch, client, parse_json_response
):
    """
    Return faq categories for a valid public API request.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "FaqService",
        build_service(get_faq_categories=lambda: [{"faqCategoryId": 2}]),
    )

    response = client.get(
        "/public/faq_categories",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"faqCategoryId": 2}]


def test_public_events_parses_query_filters(monkeypatch, client, parse_json_response):
    """
    Forward parsed public event filters to the event service.
    """
    captured = {}

    class FakeEventService:
        """
        Fake event service for public event queries.
        """

        def get_events_and_orders(self, **kwargs):
            """
            Record parsed public event filters.
            """
            captured["kwargs"] = kwargs
            return [{"eventId": 10}]

    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(public_api, "EventService", FakeEventService)

    response = client.get(
        (
            "/public/events?sellerId=5&start=100&end=200&excludeStart=150"
            "&excludeEnd=175&search=vip&eventId=44&sellerIds=1,2&site=1"
        ),
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"eventId": 10}]
    assert captured["kwargs"]["seller_id"] == 5
    assert captured["kwargs"]["seller_ids"] == [1, 2]
    assert captured["kwargs"]["is_website"] is True
    assert captured["kwargs"]["is_public"] is True
    assert captured["kwargs"]["show_cancelled"] is False


def test_public_event_tours_returns_all_tours(monkeypatch, client, parse_json_response):
    """
    Return recent public tours from the event service.
    """
    captured = {}
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "EventService",
        build_service(
            get_tours_from_recent_events=lambda: (
                captured.update({"called": True}) or [{"tourId": 9}]
            )
        ),
    )

    response = client.get(
        "/public/tours",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"tourId": 9}]
    assert captured["called"] is True


def test_public_featured_artists_returns_service_results(
    monkeypatch, client, parse_json_response
):
    """
    Return featured artists from the public service.
    """
    captured = {}
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "PublicService",
        build_service(
            get_featured_artists=lambda: (
                captured.update({"called": True})
                or [
                    SimpleNamespace(
                        featured_artist_id=3,
                        featured_artist_order=1,
                        page_seller_id=12,
                        title="Ada Beats",
                        background_image="background.jpg",
                        preview_image="preview.jpg",
                        logo_image="logo.png",
                        href="ada-beats",
                    )
                ]
            )
        ),
    )

    response = client.get(
        "/public/featuredArtists",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [
        {
            "featuredArtistId": 3,
            "featuredArtistOrder": 1,
            "pageSellerId": 12,
            "title": "Ada Beats",
            "backgroundImage": "background.jpg",
            "previewImage": "preview.jpg",
            "logoImage": "logo.png",
            "href": "ada-beats",
        }
    ]
    assert captured["called"] is True


def test_public_add_or_confirm_subscriber_returns_sender_result(
    monkeypatch, client, parse_json_response
):
    """
    Return the Sender subscriber result for a valid subscriber request.
    """
    captured = {}
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "SenderApiService",
        build_service(
            add_subscriber_from_email=lambda email: (
                captured.update({"email": email}) or "sender-123"
            )
        ),
    )

    response = client.post(
        "/public/addOrConfirmSubscriber",
        headers={"x-api-key": "public-key"},
        json={"email": " fan@example.com "},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == "sender-123"
    assert captured["email"] == "fan@example.com"


def test_public_add_or_confirm_subscriber_validates_email(monkeypatch, client):
    """
    Return 400 when the subscriber request does not include a usable email address.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")

    response = client.post(
        "/public/addOrConfirmSubscriber",
        headers={"x-api-key": "public-key"},
        json={"email": " "},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_public_moment_routes_forward_filters_and_return_results(
    monkeypatch, client, parse_json_response
):
    """
    Forward moment route filters to the moments service and return service results.
    """
    captured = {}

    class FakeMomentsService:
        """
        Fake moments service for public moment route tests.
        """

        def get_available_moment_dates(self, seller_id=None):
            """
            Record the seller filter for available dates.
            """
            captured["dates"] = seller_id
            return ["2026-05-01"]

        def get_available_moment_sellers(self, moment_date=None):
            """
            Record the date filter for available sellers.
            """
            captured["sellers"] = moment_date
            return [SimpleNamespace(seller_id=20, name="Alpha Presents")]

        def get_available_moment_events(self, moment_date=None, seller_id=None):
            """
            Record the date and seller filters for available events.
            """
            captured["events"] = (moment_date, seller_id)
            return [
                SimpleNamespace(
                    external_event_id=300,
                    event_date="2026-05-01",
                    title="VIP Night",
                )
            ]

        def filter_moments(self, moment_date=None, seller_id=None, event_id=None):
            """
            Record fan moment filters.
            """
            captured["filter"] = (moment_date, seller_id, event_id)
            return [
                SimpleNamespace(
                    moment_date="2026-05-01",
                    seller_id=20,
                    event_id=300,
                    url="moments-bucket/2026-05-01/20/300/a.jpg",
                )
            ]

    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(public_api, "MomentsService", FakeMomentsService)

    dates_response = client.get(
        "/public/getAllMomentDates?seller_id=20",
        headers={"x-api-key": "public-key"},
    )
    sellers_response = client.get(
        "/public/getAllMomentSellers?date=2026-05-01",
        headers={"x-api-key": "public-key"},
    )
    events_response = client.get(
        "/public/getAllMomentEvents?date=2026-05-01&sellerId=20",
        headers={"x-api-key": "public-key"},
    )
    filter_response = client.get(
        "/public/fan-moments/filter?date=2026-05-01&sellerId=20&eventId=300",
        headers={"x-api-key": "public-key"},
    )

    assert dates_response.status_code == 200
    assert parse_json_response(dates_response) == ["2026-05-01"]
    assert sellers_response.status_code == 200
    assert parse_json_response(sellers_response) == [
        {"sellerId": 20, "name": "Alpha Presents"}
    ]
    assert events_response.status_code == 200
    assert parse_json_response(events_response) == [
        {
            "externalEventId": 300,
            "eventDate": "2026-05-01",
            "title": "VIP Night",
        }
    ]
    assert filter_response.status_code == 200
    assert parse_json_response(filter_response) == [
        {
            "momentDate": "2026-05-01",
            "sellerId": 20,
            "eventId": 300,
            "url": "moments-bucket/2026-05-01/20/300/a.jpg",
        }
    ]
    assert captured["dates"] == 20
    assert captured["sellers"] == "2026-05-01"
    assert captured["events"] == ("2026-05-01", 20)
    assert captured["filter"] == ("2026-05-01", 20, 300)


def test_public_page_by_route_requires_non_empty_route(client):
    """
    Return 404 when the page-by-route endpoint is requested without a route.
    """
    response = client.get("/public/page/")

    assert response.status_code == 404


def test_public_page_by_route_passes_visibility_flags(
    monkeypatch, client, parse_json_response
):
    """
    Forward inactive and site flags when loading a public page by route.
    """
    captured = {}

    class FakePageService:
        """
        Fake page service for route-based page loading.
        """

        def get_page_by_route(self, route, show_inactive, is_website):
            """
            Record the page lookup arguments.
            """
            captured["args"] = (route, show_inactive, is_website)
            return {"route": route}

    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(public_api, "PageService", FakePageService)

    response = client.get(
        "/public/page/seller-a?inactive=1&site=1",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"route": "seller-a"}
    assert captured["args"] == ("seller-a", True, True)


def test_public_pages_by_type_validates_and_returns_results(
    monkeypatch, client, parse_json_response
):
    """
    Reject invalid page types and return mapped page data for valid ones.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "PageService",
        build_service(
            get_all_pages=lambda is_public=True, page_type_id=None: [
                {"pageTypeId": page_type_id, "isPublic": is_public}
            ]
        ),
    )

    bad_response = client.get(
        "/public/pages/0",
        headers={"x-api-key": "public-key"},
    )
    good_response = client.get(
        "/public/pages/3",
        headers={"x-api-key": "public-key"},
    )

    assert bad_response.status_code == 400
    assert bad_response.get_json() == {"msg": "Bad Request"}
    assert good_response.status_code == 200
    assert parse_json_response(good_response) == [{"pageTypeId": 3, "isPublic": True}]


def test_public_page_type_routes_return_results(
    monkeypatch, client, parse_json_response
):
    """
    Return normal and seller-only page types from the page service.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "PageService",
        build_service(
            get_all_page_types=lambda seller_types_only=False: [
                {"sellerTypesOnly": seller_types_only}
            ]
        ),
    )

    page_types_response = client.get(
        "/public/page_types",
        headers={"x-api-key": "public-key"},
    )
    seller_types_response = client.get(
        "/public/page_seller_types",
        headers={"x-api-key": "public-key"},
    )

    assert page_types_response.status_code == 200
    assert parse_json_response(page_types_response) == [{"sellerTypesOnly": False}]
    assert seller_types_response.status_code == 200
    assert parse_json_response(seller_types_response) == [{"sellerTypesOnly": True}]


def test_public_sellers_and_settings_return_results(
    monkeypatch, client, parse_json_response
):
    """
    Return sellers and site settings from their respective services.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "SellerService",
        build_service(get_all_sellers=lambda: [{"sellerId": 11}]),
    )
    monkeypatch.setattr(
        public_api,
        "AdminService",
        build_service(get_site_settings=lambda: [{"settingId": 4}]),
    )

    sellers_response = client.get(
        "/public/sellers",
        headers={"x-api-key": "public-key"},
    )
    settings_response = client.get(
        "/public/settings",
        headers={"x-api-key": "public-key"},
    )

    assert sellers_response.status_code == 200
    assert parse_json_response(sellers_response) == [{"sellerId": 11}]
    assert settings_response.status_code == 200
    assert parse_json_response(settings_response) == [{"settingId": 4}]


def test_public_timezones_populates_country_timezones(
    monkeypatch, client, parse_json_response
):
    """
    Attach timezone lists for each returned country code.
    """
    country = SimpleNamespace(country_code="US", timezones=None)

    class FakeAdminService:
        """
        Fake admin service for timezone lookups.
        """

        def get_all_countries(self, country_code):
            """
            Return fake countries for timezone expansion.
            """
            assert country_code == "US"
            return [country]

    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(public_api, "AdminService", FakeAdminService)
    monkeypatch.setattr(
        public_api,
        "get_timezones_from_country_code",
        lambda country_code: ["America/New_York"],
    )

    response = client.get(
        "/public/timezones?country_code=US",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [
        {"countryCode": "US", "timezones": ["America/New_York"]}
    ]


def test_public_timezones_skips_empty_country_codes(
    monkeypatch, client, parse_json_response
):
    """
    Leave countries without a country code unchanged when building timezone data.
    """
    country = SimpleNamespace(country_code=None, timezones=None)
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "AdminService",
        build_service(get_all_countries=lambda country_code: [country]),
    )

    response = client.get(
        "/public/timezones",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"countryCode": None, "timezones": None}]


def test_public_upload_image_requires_temp_file(monkeypatch, client):
    """
    Return 400 when the upload-image route is missing the posted file.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")

    response = client.post(
        "/public/uploadImage/header",
        headers={"x-api-key": "public-key"},
        data={},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_public_upload_image_returns_uploaded_filename(
    monkeypatch, client, parse_json_response
):
    """
    Return the uploaded filename after delegating to the public service.
    """
    captured = {}

    class FakePublicService:
        """
        Fake public service for image uploads.
        """

        def upload_image_to_bucket(self, _request, bucket_name, max_width):
            """
            Record the upload destination and width.
            """
            captured["bucket_name"] = bucket_name
            captured["max_width"] = max_width
            return "hero.jpg"

    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(public_api, "PublicService", FakePublicService)
    monkeypatch.setattr(
        public_api, "get_bucket_name_from_image_type", lambda image_type: "bucket"
    )
    monkeypatch.setattr(
        public_api, "get_image_width_from_image_type", lambda image_type: 1200
    )

    response = client.post(
        "/public/uploadImage/headers",
        headers={"x-api-key": "public-key"},
        data={"tempFile": (BytesIO(b"image-bytes"), "hero.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert parse_json_response(response) == "hero.jpg"
    assert captured["bucket_name"] == "bucket"
    assert captured["max_width"] == 1200


def test_messaging_email_requires_api_key(client):
    """
    Return 401 when the messaging email route is missing the mail API key.
    """
    response = client.post("/messaging/email", json={})

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_messaging_email_validates_required_fields(monkeypatch, client):
    """
    Return 400 when the email route is missing required form fields.
    """
    monkeypatch.setenv("MAIL_API_KEY", "mail-key")

    response = client.post(
        "/messaging/email",
        headers={"x-api-key": "mail-key"},
        json={"to": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_messaging_email_sends_with_cc_and_reply_to(
    monkeypatch, client, parse_json_response
):
    """
    Split cc recipients and forward optional sender fields to the messaging service.
    """
    captured = {}

    class FakeMessagingService:
        """
        Fake messaging service for outbound email.
        """

        def send_email(
            self,
            to_email_address,
            subject,
            html_content,
            to_name,
            cc_emails=None,
            reply_to=None,
            reply_to_name=None,
            from_address=None,
            from_name=None,
        ):
            """
            Record the outbound email payload.
            """
            captured["args"] = (
                to_email_address,
                subject,
                html_content,
                to_name,
                cc_emails,
                reply_to,
                reply_to_name,
                from_address,
                from_name,
            )
            return {"success": True}

    monkeypatch.setenv("MAIL_API_KEY", "mail-key")
    monkeypatch.setattr(messaging_api, "MessagingService", FakeMessagingService)

    response = client.post(
        "/messaging/email",
        headers={"x-api-key": "mail-key"},
        json={
            "to": "ada@example.com",
            "toName": "Ada",
            "subject": "Hello",
            "html": "<p>Hi</p>",
            "ccEmails": "one@example.com,two@example.com",
            "replyTo": "reply@example.com",
            "replyToName": "Support",
            "fromAddress": "sender@example.com",
            "fromName": "Sender",
        },
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"success": True}
    assert captured["args"][4] == ["one@example.com", "two@example.com"]
    assert captured["args"][5] == "reply@example.com"
    assert captured["args"][7] == "sender@example.com"


def test_messaging_get_token_requires_google_id(monkeypatch, client):
    """
    Return 400 when the token route is missing the Google id.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")

    response = client.post(
        "/messaging/token",
        headers={"x-api-key": "public-key"},
        json={},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_messaging_validate_token_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Forward token validation requests to the messaging service.
    """
    captured = {}

    class FakeMessagingService:
        """
        Fake messaging service for token validation.
        """

        def validate_google_auth_token(self, google_id, token_id):
            """
            Record the token validation arguments.
            """
            captured["args"] = (google_id, token_id)
            return {"success": True}

    monkeypatch.setenv("MAIL_API_KEY", "mail-key")
    monkeypatch.setattr(messaging_api, "MessagingService", FakeMessagingService)

    response = client.post(
        "/messaging/token/validate",
        headers={"x-api-key": "mail-key"},
        json={"gId": "abc123", "tId": 55},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"success": True}
    assert captured["args"] == ("abc123", 55)


@pytest.mark.parametrize(
    ("route", "method", "form_data"),
    [
        ("/public/faq_categories", "get", None),
        ("/public/events", "get", None),
        ("/public/tours", "get", None),
        ("/public/featuredArtists", "get", None),
        ("/public/addOrConfirmSubscriber", "post", {"email": "fan@example.com"}),
        ("/public/page/seller-a", "get", None),
        ("/public/pages/3", "get", None),
        ("/public/page_types", "get", None),
        ("/public/page_seller_types", "get", None),
        ("/public/sellers", "get", None),
        ("/public/settings", "get", None),
        ("/public/timezones", "get", None),
        ("/public/uploadImage/headers", "post", {}),
        ("/public/getAllMomentDates", "get", None),
        ("/public/getAllMomentSellers", "get", None),
        ("/public/getAllMomentEvents", "get", None),
        ("/public/fan-moments/filter", "get", None),
    ],
)
def test_public_routes_require_api_key(client, route, method, form_data):
    """
    Return 401 when secured public routes are called without the public API key.
    """
    request_kwargs = {}
    if form_data is not None:
        request_kwargs["data"] = form_data

    response = getattr(client, method)(route, **request_kwargs)

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_public_faq_direct_call_defaults_missing_category_to_zero(monkeypatch):
    """
    Default a missing FAQ category id to zero when the handler is called directly.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "FaqService",
        build_service(
            get_faq_by_category_id=lambda category_id: [{"faqId": category_id}]
        ),
    )

    with app.test_request_context(
        "/public/faq/0",
        headers={"x-api-key": "public-key"},
    ):
        response = public_api.get_faqs(None)

    assert json.loads(response) == [{"faqId": 0}]


def test_public_events_uses_default_optional_filters(
    monkeypatch, client, parse_json_response
):
    """
    Leave optional seller-id and site filters unset when they are omitted.
    """
    captured = {}
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "EventService",
        build_service(
            get_events_and_orders=lambda **kwargs: (
                captured.update({"kwargs": kwargs}) or [{"eventId": 77}]
            )
        ),
    )

    response = client.get(
        "/public/events?sellerId=5",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"eventId": 77}]
    assert captured["kwargs"]["seller_ids"] is None
    assert captured["kwargs"]["is_website"] is False


def test_public_page_by_route_direct_call_rejects_empty_route(monkeypatch):
    """
    Return 400 when the page handler is called directly with an empty route.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")

    with app.test_request_context(
        "/public/page/",
        headers={"x-api-key": "public-key"},
    ):
        response, status_code = public_api.get_page_by_route("")

    assert status_code == 400
    assert response == {"msg": "Bad Request"}


def test_public_page_by_route_uses_default_flags(
    monkeypatch, client, parse_json_response
):
    """
    Leave inactive and site flags false when they are omitted.
    """
    captured = {}
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        public_api,
        "PageService",
        build_service(
            get_page_by_route=lambda route, show_inactive, is_website: (
                captured.update({"args": (route, show_inactive, is_website)})
                or {"route": route}
            )
        ),
    )

    response = client.get(
        "/public/page/seller-b",
        headers={"x-api-key": "public-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"route": "seller-b"}
    assert captured["args"] == ("seller-b", False, False)


def test_public_upload_image_rejects_invalid_image_type(monkeypatch, client):
    """
    Return 400 when the upload route receives an unsupported image type.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")

    response = client.post(
        "/public/uploadImage/not-a-real-type",
        headers={"x-api-key": "public-key"},
        data={"tempFile": (BytesIO(b"image-bytes"), "hero.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_messaging_email_sends_without_cc_list(
    monkeypatch, client, parse_json_response
):
    """
    Leave the CC list unset when the email payload does not include ccEmails.
    """
    captured = {}

    class FakeMessagingService:
        """
        Fake messaging service for outbound email without CC recipients.
        """

        def send_email(
            self,
            to_email_address,
            subject,
            html_content,
            to_name,
            cc_emails=None,
            reply_to=None,
            reply_to_name=None,
            from_address=None,
            from_name=None,
        ):
            """
            Record the outbound email payload.
            """
            captured["args"] = (
                to_email_address,
                subject,
                html_content,
                to_name,
                cc_emails,
                reply_to,
                reply_to_name,
                from_address,
                from_name,
            )
            return True

    monkeypatch.setenv("MAIL_API_KEY", "mail-key")
    monkeypatch.setattr(messaging_api, "MessagingService", FakeMessagingService)

    response = client.post(
        "/messaging/email",
        headers={"x-api-key": "mail-key"},
        json={
            "to": "ada@example.com",
            "toName": "Ada",
            "subject": "Hello",
            "html": "<p>Hi</p>",
        },
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["args"][4] is None


@pytest.mark.parametrize(
    ("route", "headers", "payload"),
    [
        ("/messaging/token", {"x-api-key": "wrong"}, {"gId": "abc123"}),
        (
            "/messaging/token/validate",
            {"x-api-key": "wrong"},
            {"gId": "abc123", "tId": 55},
        ),
    ],
)
def test_messaging_token_routes_require_matching_api_keys(
    monkeypatch, client, route, headers, payload
):
    """
    Return 401 when token routes receive the wrong API key.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setenv("MAIL_API_KEY", "mail-key")

    response = client.post(route, headers=headers, json=payload)

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_messaging_get_token_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Return the generated Google auth token from the messaging service.
    """
    monkeypatch.setenv("PUBLIC_API_KEY", "public-key")
    monkeypatch.setattr(
        messaging_api,
        "MessagingService",
        build_service(generate_google_auth_token=lambda google_id: {"tokenId": 88}),
    )

    response = client.post(
        "/messaging/token",
        headers={"x-api-key": "public-key"},
        json={"gId": "abc123"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"tokenId": 88}


def test_messaging_validate_token_rejects_invalid_payload(monkeypatch, client):
    """
    Return 400 when token validation is missing the Google id or token id.
    """
    monkeypatch.setenv("MAIL_API_KEY", "mail-key")

    response = client.post(
        "/messaging/token/validate",
        headers={"x-api-key": "mail-key"},
        json={"gId": "abc123", "tId": 0},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}
