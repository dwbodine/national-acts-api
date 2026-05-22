"""
Unit tests for common.sender_api_service helpers.
"""

from pathlib import Path

from common import sender_api_service
from common.models.sender_api import Subscriber


class FakeResponse:
    """
    Test double for requests responses that return JSON data.
    """

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        """
        Return the configured JSON payload.
        """
        return self.payload


def build_subscriber(email="fan@example.com", order_id=101):
    """
    Build a Subscriber instance with representative field values.
    """
    subscriber = Subscriber()
    subscriber.id = "sub-1"
    subscriber.email = email
    subscriber.first_name = "Ada"
    subscriber.last_name = "Lovelace"
    subscriber.phone = "555-1111"
    subscriber.purchaser_zip = "30301"
    subscriber.venue = "The Hall"
    subscriber.venue_address = "123 Main"
    subscriber.venue_city = "Atlanta"
    subscriber.venue_state = "GA"
    subscriber.venue_zip = "30303"
    subscriber.venue_country = "USA"
    subscriber.band = "The Bots"
    subscriber.order_id = order_id
    return subscriber


def test_get_subscriber_by_email_maps_sender_response(monkeypatch):
    """
    Test that get_subscriber_by_email maps Sender fields and custom columns.
    """
    captured = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda method, url, headers, timeout: captured.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        or FakeResponse(
            {
                "data": {
                    "id": "sub-99",
                    "email": "fan@example.com",
                    "firstname": "Ada",
                    "lastname": "Lovelace",
                    "phone": "555-1111",
                    "columns": [
                        {"title": "Band", "value": "The Bots"},
                        {"title": "Venue", "value": "The Hall"},
                        {"title": "Venue Address", "value": "123 Main"},
                        {"title": "Venue City", "value": "Atlanta"},
                        {"title": "Venue State", "value": "GA"},
                        {"title": "Venue Zip", "value": "30303"},
                        {"title": "Venue Country", "value": "USA"},
                        {"title": "Purchaser Zip", "value": "30301"},
                    ],
                }
            }
        ),
    )

    subscriber = sender_api_service.SenderApiService().get_subscriber_by_email(
        "fan@example.com"
    )

    assert subscriber is not None
    assert subscriber.id == "sub-99"
    assert subscriber.email == "fan@example.com"
    assert subscriber.first_name == "Ada"
    assert subscriber.last_name == "Lovelace"
    assert subscriber.phone == "555-1111"
    assert subscriber.band == "The Bots"
    assert subscriber.venue == "The Hall"
    assert subscriber.venue_address == "123 Main"
    assert subscriber.venue_city == "Atlanta"
    assert subscriber.venue_state == "GA"
    assert subscriber.venue_zip == "30303"
    assert subscriber.venue_country == "USA"
    assert subscriber.purchaser_zip == "30301"
    assert captured[0] == {
        "method": "GET",
        "url": "https://sender.test/subscribers/fan@example.com",
        "headers": {
            "Authorization": "Bearer sender-key",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        "timeout": 300,
    }


def test_get_subscriber_by_email_returns_none_on_request_error(monkeypatch):
    """
    Test that get_subscriber_by_email returns None when Sender raises an error.
    """
    logged_errors = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        sender_api_service.logger,
        "error",
        lambda message, error: logged_errors.append((message, error)),
    )

    subscriber = sender_api_service.SenderApiService().get_subscriber_by_email(
        "fan@example.com"
    )

    assert subscriber is None
    assert logged_errors
    assert logged_errors[0][0] == "%s"
    assert "boom" in logged_errors[0][1]


def test_get_subscriber_by_email_returns_none_when_payload_has_no_data(monkeypatch):
    """
    Test that get_subscriber_by_email returns None when Sender responds without a data object.
    """
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda method, url, headers, timeout: FakeResponse({}),
    )

    subscriber = sender_api_service.SenderApiService().get_subscriber_by_email(
        "fan@example.com"
    )

    assert subscriber is None


def test_get_subscriber_by_email_handles_none_and_unknown_columns(monkeypatch):
    """
    Test that get_subscriber_by_email tolerates missing columns and ignores unknown custom columns.
    """
    responses = iter(
        [
            {
                "data": {
                    "id": "sub-99",
                    "email": "fan@example.com",
                    "firstname": "Ada",
                    "lastname": "Lovelace",
                    "phone": "555-1111",
                    "columns": None,
                }
            },
            {
                "data": {
                    "id": "sub-100",
                    "email": "fan@example.com",
                    "firstname": "Ada",
                    "lastname": "Lovelace",
                    "phone": "555-1111",
                    "columns": [{"title": "Unknown", "value": "ignored"}],
                }
            },
        ]
    )
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda method, url, headers, timeout: FakeResponse(next(responses)),
    )

    no_columns = sender_api_service.SenderApiService().get_subscriber_by_email(
        "fan@example.com"
    )
    unknown_columns = sender_api_service.SenderApiService().get_subscriber_by_email(
        "fan@example.com"
    )

    assert no_columns is not None
    assert getattr(no_columns, "band", None) == ""
    assert unknown_columns is not None
    assert getattr(unknown_columns, "venue", None) == ""


def test_add_subscriber_from_email_returns_existing_subscriber_id(monkeypatch):
    """
    Test that add_subscriber_from_email returns the Sender id for known subscribers.
    """
    existing = build_subscriber(email="known@example.com")
    existing.id = "sender-123"
    created_subscribers = []
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        lambda self, email: existing,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "create_subscriber",
        lambda self, subscriber: created_subscribers.append(subscriber) or True,
    )

    subscriber_id = sender_api_service.SenderApiService().add_subscriber_from_email(
        "known@example.com"
    )

    assert subscriber_id == "sender-123"
    assert not created_subscribers


def test_add_subscriber_from_email_creates_missing_subscriber(monkeypatch):
    """
    Test that add_subscriber_from_email creates a Subscriber with the submitted email.
    """
    created_subscribers = []
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        lambda self, email: None,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "create_subscriber",
        lambda self, subscriber: created_subscribers.append(subscriber) or True,
    )

    subscriber_id = sender_api_service.SenderApiService().add_subscriber_from_email(
        "new@example.com"
    )

    assert subscriber_id == 0
    assert len(created_subscribers) == 1
    assert created_subscribers[0].email == "new@example.com"


def test_add_subscriber_from_email_returns_error_marker_when_create_fails(
    monkeypatch,
):
    """
    Test that add_subscriber_from_email returns -1 when Sender rejects a new subscriber.
    """
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        lambda self, email: None,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "create_subscriber",
        lambda self, subscriber: False,
    )

    subscriber_id = sender_api_service.SenderApiService().add_subscriber_from_email(
        "new@example.com"
    )

    assert subscriber_id == -1


def test_create_subscriber_posts_payload_and_returns_success(monkeypatch):
    """
    Test that create_subscriber sends the expected payload and returns success.
    """
    captured = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda method, url, headers, json, timeout: captured.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        or FakeResponse({"success": True}),
    )

    success = sender_api_service.SenderApiService().create_subscriber(
        build_subscriber()
    )

    assert success is True
    assert captured[0]["method"] == "POST"
    assert captured[0]["url"] == "https://sender.test/subscribers"
    assert captured[0]["headers"]["Authorization"] == "Bearer sender-key"
    assert captured[0]["json"] == {
        "email": "fan@example.com",
        "firstname": "Ada",
        "lastname": "Lovelace",
        "phone": "555-1111",
        "fields": {
            "{$purchaser_zip}": "30301",
            "{$venue}": "The Hall",
            "{$venue_address}": "123 Main",
            "{$venue_city}": "Atlanta",
            "{$venue_state}": "GA",
            "{$venue_zip}": "30303",
            "{$venue_country}": "USA",
            "{$band}": "The Bots",
        },
    }
    assert captured[0]["timeout"] == 300


def test_create_subscriber_clears_phone_when_sender_rejects_phone(monkeypatch):
    """
    Test that create_subscriber clears the stored phone when Sender rejects it.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(
            {"success": False, "message": "Invalid phone number"}
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().create_subscriber(
        build_subscriber(order_id=222)
    )

    assert success is False
    assert cleared_order_ids == [222]
    assert not updated_order_ids


def test_create_subscriber_marks_order_when_sender_rejects_email(monkeypatch):
    """
    Test that create_subscriber marks the order updated when Sender rejects email.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(
            {"success": False, "message": "Invalid email address"}
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().create_subscriber(
        build_subscriber(order_id=222)
    )

    assert success is False
    assert not cleared_order_ids
    assert updated_order_ids == [222]


def test_create_subscriber_returns_false_without_side_effects_when_message_missing(
    monkeypatch,
):
    """
    Test that create_subscriber returns False without side effects when Sender omits a failure message.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse({"success": False, "message": None}),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().create_subscriber(
        build_subscriber(order_id=222)
    )

    assert success is False
    assert not cleared_order_ids
    assert not updated_order_ids


def test_create_subscriber_returns_false_when_response_json_is_none(monkeypatch):
    """
    Test that create_subscriber returns False without side effects when Sender returns no JSON body.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(None),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().create_subscriber(
        build_subscriber(order_id=222)
    )

    assert success is False
    assert not cleared_order_ids
    assert not updated_order_ids


def test_create_subscriber_returns_false_without_side_effects_for_other_errors(
    monkeypatch,
):
    """
    Test that create_subscriber returns False without side effects for non-phone and non-email errors.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(
            {"success": False, "message": "Temporary service outage"}
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().create_subscriber(
        build_subscriber(order_id=222)
    )

    assert success is False
    assert not cleared_order_ids
    assert not updated_order_ids


def test_update_subscriber_marks_order_when_sender_rejects_email(monkeypatch):
    """
    Test that update_subscriber marks the order updated when Sender rejects email.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(
            {"success": False, "message": "Invalid email address"}
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().update_subscriber(
        build_subscriber(order_id=333)
    )

    assert success is False
    assert not cleared_order_ids
    assert updated_order_ids == [333]


def test_update_subscriber_clears_phone_when_sender_rejects_phone(monkeypatch):
    """
    Test that update_subscriber clears the stored phone when Sender rejects it.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(
            {"success": False, "message": "Invalid phone number"}
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().update_subscriber(
        build_subscriber(order_id=333)
    )

    assert success is False
    assert cleared_order_ids == [333]
    assert not updated_order_ids


def test_update_subscriber_returns_false_without_side_effects_when_message_missing(
    monkeypatch,
):
    """
    Test that update_subscriber returns False without side effects when Sender omits a failure message.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse({"success": False, "message": None}),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().update_subscriber(
        build_subscriber(order_id=333)
    )

    assert success is False
    assert not cleared_order_ids
    assert not updated_order_ids


def test_update_subscriber_returns_false_when_response_json_is_none(monkeypatch):
    """
    Test that update_subscriber returns False without side effects when Sender returns no JSON body.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(None),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().update_subscriber(
        build_subscriber(order_id=333)
    )

    assert success is False
    assert not cleared_order_ids
    assert not updated_order_ids


def test_update_subscriber_returns_true_for_successful_updates(monkeypatch):
    """
    Test that update_subscriber returns True when Sender reports success.
    """
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse({"success": True}),
    )

    success = sender_api_service.SenderApiService().update_subscriber(
        build_subscriber(order_id=333)
    )

    assert success is True


def test_update_subscriber_returns_false_without_side_effects_for_other_errors(
    monkeypatch,
):
    """
    Test that update_subscriber returns False without side effects for non-phone and non-email errors.
    """
    cleared_order_ids = []
    updated_order_ids = []
    monkeypatch.setenv("SENDER_BASE_URL", "https://sender.test")
    monkeypatch.setenv("SENDER_API_KEY", "sender-key")
    monkeypatch.setattr(
        sender_api_service.requests,
        "request",
        lambda *args, **kwargs: FakeResponse(
            {"success": False, "message": "Temporary service outage"}
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "clear_subscriber_phone",
        lambda self, order_id: cleared_order_ids.append(order_id) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_order_ids.append(order_id) or True,
    )

    success = sender_api_service.SenderApiService().update_subscriber(
        build_subscriber(order_id=333)
    )

    assert success is False
    assert not cleared_order_ids
    assert not updated_order_ids


def test_update_sender_subscribers_updates_existing_and_creates_new(monkeypatch):
    """
    Test that update_sender_subscribers updates existing records and creates new ones.
    """
    updated_subscribers = []
    created_subscribers = []
    updated_orders = []
    existing = build_subscriber(email="existing@example.com", order_id=10)
    new = build_subscriber(email="new@example.com", order_id=20)

    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_sender_subscribers_from_db",
        lambda self, limit=0: [existing, new],
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        lambda self, email: (
            build_subscriber(email=email, order_id=0)
            if email == "existing@example.com"
            else None
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber",
        lambda self, subscriber: updated_subscribers.append(subscriber) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "create_subscriber",
        lambda self, subscriber: created_subscribers.append(subscriber) or True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_orders.append(order_id) or True,
    )
    monkeypatch.setattr(sender_api_service.time, "sleep", lambda seconds: None)

    results = sender_api_service.SenderApiService().update_sender_subscribers()

    assert results == {
        "total_subscribers_fetched": 2,
        "subscribers_processed": 2,
        "subscribers_added": 1,
        "subscribers_updated": 1,
        "existing_subscribers_with_error": [],
        "new_subscribers_with_error": [],
    }
    assert updated_subscribers[0].email == "existing@example.com"
    assert updated_subscribers[0].id == "sub-1"
    assert created_subscribers[0].email == "new@example.com"
    assert updated_orders == [10, 20]


def test_update_sender_subscribers_returns_empty_counts_when_no_rows_exist(monkeypatch):
    """
    Test that update_sender_subscribers returns empty counts when there are no stored subscribers.
    """
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_sender_subscribers_from_db",
        lambda self, limit=0: [],
    )

    results = sender_api_service.SenderApiService().update_sender_subscribers()

    assert results == {
        "total_subscribers_fetched": 0,
        "subscribers_processed": 0,
        "subscribers_added": 0,
        "subscribers_updated": 0,
        "existing_subscribers_with_error": [],
        "new_subscribers_with_error": [],
    }


def test_update_sender_subscribers_skips_order_updates_for_zero_order_ids(monkeypatch):
    """
    Test that update_sender_subscribers skips order updates for successful subscribers without order ids.
    """
    updated_orders = []
    existing = build_subscriber(email="existing@example.com", order_id=0)
    new = build_subscriber(email="new@example.com", order_id=0)

    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_sender_subscribers_from_db",
        lambda self, limit=0: [existing, new],
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        lambda self, email: (
            build_subscriber(email=email, order_id=0)
            if email == "existing@example.com"
            else None
        ),
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber",
        lambda self, subscriber: True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "create_subscriber",
        lambda self, subscriber: True,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber_order",
        lambda self, order_id: updated_orders.append(order_id) or True,
    )
    monkeypatch.setattr(sender_api_service.time, "sleep", lambda seconds: None)

    results = sender_api_service.SenderApiService().update_sender_subscribers()

    assert results["subscribers_processed"] == 2
    assert not updated_orders


def test_update_sender_subscribers_tracks_failures_and_logs_exceptions(monkeypatch):
    """
    Test that update_sender_subscribers tracks failures and logs loop exceptions.
    """
    logged_errors = []
    existing = build_subscriber(email="existing@example.com", order_id=10)
    new = build_subscriber(email="new@example.com", order_id=20)
    exploding = build_subscriber(email="boom@example.com", order_id=30)

    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_sender_subscribers_from_db",
        lambda self, limit=0: [existing, new, exploding],
    )

    def fake_get_subscriber_by_email(_self, email):
        if email == "existing@example.com":
            return build_subscriber(email=email, order_id=0)
        if email == "boom@example.com":
            raise RuntimeError("sync failed")
        return None

    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        fake_get_subscriber_by_email,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "update_subscriber",
        lambda self, subscriber: False,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "create_subscriber",
        lambda self, subscriber: False,
    )
    monkeypatch.setattr(sender_api_service.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        sender_api_service.logger,
        "error",
        lambda message, error: logged_errors.append((message, error)),
    )

    results = sender_api_service.SenderApiService().update_sender_subscribers()

    assert results["total_subscribers_fetched"] == 3
    assert results["subscribers_processed"] == 2
    assert results["subscribers_added"] == 0
    assert results["subscribers_updated"] == 0
    assert results["existing_subscribers_with_error"] == ["existing@example.com"]
    assert results["new_subscribers_with_error"] == ["new@example.com"]
    assert logged_errors
    assert "sync failed" in logged_errors[0][1]


def test_update_subscriber_order_passes_expected_sql_to_db(monkeypatch):
    """
    Test that update_subscriber_order marks the order as updated in the database.
    """
    calls = []
    monkeypatch.setattr(
        sender_api_service.db,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = sender_api_service.SenderApiService().update_subscriber_order(77)

    assert success is True
    assert "IsSenderUpdated=1" in calls[0][0]
    assert calls[0][1] == {"orderId": 77}


def test_clear_subscriber_phone_passes_expected_sql_to_db(monkeypatch):
    """
    Test that clear_subscriber_phone clears the phone and resets Sender status.
    """
    calls = []
    monkeypatch.setattr(
        sender_api_service.db,
        "db_update",
        lambda sql, data: calls.append((sql, data)) or True,
    )

    success = sender_api_service.SenderApiService().clear_subscriber_phone(88)

    assert success is True
    assert "Phone=NULL" in calls[0][0]
    assert calls[0][1] == {"orderId": 88}


def test_get_missing_subscribers_csv_only_exports_missing_subscribers(monkeypatch):
    """
    Test that get_missing_subscribers_csv exports only subscribers missing in Sender.
    """
    exported_lists = []
    existing = build_subscriber(email="existing@example.com")
    missing = build_subscriber(email="missing@example.com")

    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_sender_subscribers_from_db",
        lambda self, limit=0: [existing, missing],
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscriber_by_email",
        lambda self, email: (
            build_subscriber(email=email) if email == "existing@example.com" else None
        ),
    )
    monkeypatch.setattr(sender_api_service.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscribers_csv",
        lambda self, subscribers: exported_lists.append(subscribers) or True,
    )

    success = sender_api_service.SenderApiService().get_missing_subscribers_csv()

    assert success is True
    assert len(exported_lists[0]) == 1
    assert exported_lists[0][0].email == "missing@example.com"


def test_get_sender_subscribers_csv_exports_all_stored_subscribers(monkeypatch):
    """
    Test that get_sender_subscribers_csv exports every stored subscriber.
    """
    exported_lists = []
    subscribers = [
        build_subscriber(email="a@example.com"),
        build_subscriber(email="b@example.com"),
    ]
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_sender_subscribers_from_db",
        lambda self, limit=0: subscribers,
    )
    monkeypatch.setattr(
        sender_api_service.SenderApiService,
        "get_subscribers_csv",
        lambda self, stored_subscribers: exported_lists.append(stored_subscribers)
        or True,
    )

    success = sender_api_service.SenderApiService().get_sender_subscribers_csv()

    assert success is True
    assert exported_lists[0] == subscribers


def test_get_subscribers_csv_writes_header_and_rows(monkeypatch, workspace_tmp_path):
    """
    Test that get_subscribers_csv writes the expected CSV file contents.
    """
    monkeypatch.chdir(workspace_tmp_path)
    subscribers = [build_subscriber()]

    success = sender_api_service.SenderApiService().get_subscribers_csv(subscribers)

    csv_path = Path(workspace_tmp_path) / "subscribers.csv"
    csv_contents = csv_path.read_text(encoding="utf-8")

    assert success is True
    assert csv_path.exists()
    assert (
        '"Email","First name","Last name","Phone number","Purchaser Zip","Venue",'
        in csv_contents
    )
    assert (
        '"fan@example.com","Ada","Lovelace","555-1111","30301","The Hall"'
        in csv_contents
    )
    assert '"123 Main","Atlanta","GA","30303","USA","The Bots"' in csv_contents


def test_get_subscribers_csv_writes_only_the_header_for_empty_lists(
    monkeypatch,
    workspace_tmp_path,
):
    """
    Test that get_subscribers_csv writes only the header row when there are no subscribers.
    """
    monkeypatch.chdir(workspace_tmp_path)

    success = sender_api_service.SenderApiService().get_subscribers_csv([])

    assert success is True
    csv_contents = Path("subscribers.csv").read_text(encoding="utf-8")
    assert csv_contents.count("\n") == 1


def test_get_sender_subscribers_from_db_maps_rows_and_limit(monkeypatch):
    """
    Test that get_sender_subscribers_from_db maps database rows into Subscriber models.
    """
    calls = []
    monkeypatch.setattr(
        sender_api_service.db,
        "db_query_all",
        lambda sql, data: calls.append((sql, data))
        or [
            {
                "Email": "fan@example.com",
                "PurchaserFirstName": "Ada",
                "PurchaserLastName": "Lovelace",
                "Phone": "555-1111",
                "PurchaserZip": "30301",
                "Venue": "The Hall",
                "VenueAddress": "123 Main",
                "VenueCity": "Atlanta",
                "VenueState": "GA",
                "VenueZip": "30303",
                "VenueCountry": "USA",
                "Band": "The Bots",
                "OrderId": 42,
            }
        ],
    )

    subscribers = sender_api_service.SenderApiService().get_sender_subscribers_from_db(
        25
    )

    assert len(subscribers) == 1
    assert subscribers[0].email == "fan@example.com"
    assert subscribers[0].first_name == "Ada"
    assert subscribers[0].last_name == "Lovelace"
    assert subscribers[0].phone == "555-1111"
    assert subscribers[0].purchaser_zip == "30301"
    assert subscribers[0].venue == "The Hall"
    assert subscribers[0].venue_address == "123 Main"
    assert subscribers[0].venue_city == "Atlanta"
    assert subscribers[0].venue_state == "GA"
    assert subscribers[0].venue_zip == "30303"
    assert subscribers[0].venue_country == "USA"
    assert subscribers[0].band == "The Bots"
    assert subscribers[0].order_id == 42
    assert "LIMIT 0, %(limit)s" in calls[0][0]
    assert calls[0][1] == {"limit": 25}


def test_get_sender_subscribers_from_db_returns_empty_on_query_error(monkeypatch):
    """
    Test that get_sender_subscribers_from_db returns an empty list when querying fails.
    """
    logged_errors = []
    monkeypatch.setattr(
        sender_api_service.db,
        "db_query_all",
        lambda sql, data: (_ for _ in ()).throw(RuntimeError("db failed")),
    )
    monkeypatch.setattr(
        sender_api_service.logger,
        "error",
        lambda message, error: logged_errors.append((message, error)),
    )

    subscribers = sender_api_service.SenderApiService().get_sender_subscribers_from_db()

    assert not subscribers
    assert logged_errors
    assert "db failed" in logged_errors[0][1]
