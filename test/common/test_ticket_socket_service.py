"""
Unit tests for common.ticket_socket_service helpers.
"""

import json
from datetime import datetime

from common import ticket_socket_service
from common.models.ticket_socket import Country


def create_service(
    monkeypatch,
    ticket_socket_id=7,
    service_url="api.tickets.test",
    token="jwt-token",
    utc_offset_hours=0,
):
    """
    Create a TicketSocketService instance without running real initialization.
    """
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "_TicketSocketService__initialize",
        lambda self: None,
    )
    service = ticket_socket_service.TicketSocketService(ticket_socket_id)
    service.service_url = service_url
    service.token = token
    service.utc_offset_hours = utc_offset_hours
    return service


def build_order_ticket_item(**overrides):
    """
    Create a TicketSocket order-ticket payload for parser tests.
    """
    item = {
        "eventId": 77,
        "purchaseDate": 1713882000,
        "userId": 9,
        "billing_firstName": "Ada",
        "billing_lastName": "Lovelace",
        "billing_city": "Austin",
        "billing_state": "TX",
        "billing_zip": "73301",
        "billing_country": "USA",
        "remoteAddr": "127.0.0.1",
        "email": "buyer@example.com",
        "phone": "",
        "billing_phone": "555-1212",
        "purchaserQuestions": [],
        "attendeeQuestions": [],
        "price": 50.0,
        "id": 1001,
        "ticketTypeName": "VIP",
        "fee1Amount": 10.0,
        "typeId": 7,
        "barcode": "ABC123",
        "availableScans": 2,
        "purchaseLocation": "Online",
        "scannedTimestamp": 123,
        "partyMember": "Ada",
        "partyMemberLastName": "Lovelace",
    }
    item.update(overrides)
    return item


def test_init_loads_account_data_and_jwt_token(monkeypatch):
    """
    Test that initialization loads account metadata and fetches a JWT token.
    """
    payloads = []
    monkeypatch.setenv("API_UID_7", "user-7")
    monkeypatch.setenv("API_PWD_7", "pwd-7")
    monkeypatch.setenv("API_PK_7", "pk-7")
    monkeypatch.setenv("API_PK_SLUG_7", "slug-7")
    monkeypatch.setattr(
        ticket_socket_service,
        "db_query_one",
        lambda sql, data: {
            "AccountName": "Ticket Account",
            "ServiceUrl": "https://api.tickets.test",
            "DefaultUtcOffsetHours": -5,
            "ExchangeRateId": 2,
            "Symbol": "$",
            "ServiceTokenId": "usd",
        },
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "post_https_response",
        lambda host, url, payload: payloads.append((host, url, payload))
        or {"jwt": "jwt-token"},
    )

    service = ticket_socket_service.TicketSocketService(7)

    assert service.name == "Ticket Account"
    assert service.service_url == "api.tickets.test"
    assert service.utc_offset_hours == -5
    assert service.exchange_rate_id == 2
    assert service.currency_symbol == "$"
    assert service.exchange_rate_slug == "usd"
    assert service.token == "jwt-token"
    assert payloads[0][0] == "api.tickets.test"
    assert payloads[0][1] == "/api/v1/tokens"
    assert json.loads(payloads[0][2]) == {
        "userName": "user-7",
        "password": "pwd-7",
        "publicKey": "pk-7",
        "publicKeySlug": "slug-7",
    }


def test_get_categories_returns_empty_and_logs_without_credentials(monkeypatch):
    """
    Test that get_categories returns an empty list when credentials are missing.
    """
    logged_errors = []
    service = create_service(monkeypatch, service_url=None, token=None)
    monkeypatch.setattr(
        ticket_socket_service.logger,
        "error",
        lambda message, ticket_socket_id: logged_errors.append(
            (message, ticket_socket_id)
        ),
    )

    categories = service.get_categories()

    assert not categories
    assert logged_errors == [
        ("service url or token not present for ticket_socket_id %s", 7)
    ]


def test_get_categories_maps_valid_categories_only(monkeypatch):
    """
    Test that get_categories maps valid categories and skips invalid rows.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: [
            {"id": 10, "title": "VIP"},
            {"id": 0, "title": "Ignored"},
            {"id": 12, "title": ""},
        ],
    )

    categories = service.get_categories()

    assert len(categories) == 1
    assert categories[0].event_category_id == 10
    assert categories[0].name == "VIP"


def test_get_events_and_orders_maps_events_and_builds_filtered_url(monkeypatch):
    """
    Test that get_events_and_orders maps event data and builds the filtered request URL.
    """
    calls = []
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_country_from_country_name",
        lambda country_name, state, zip_code: Country(1, country_name, "US"),
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: calls.append((host, url, bearer_token))
        or [
            {
                "id": 50,
                "title": "VIP Night",
                "categories": [{"id": 3}],
                "smallPic": "small.jpg",
                "sefUrl": "vip-night",
                "venue": "Arena",
                "venueAddress1": "123 Main",
                "venueAddress2": "Suite B",
                "venueCity": "Austin",
                "venueState": "TX",
                "venuePostalCode": "73301",
                "venueCountry": "USA",
                "displayStartDate": "05/01/2026",
                "start": 1770000000,
                "ticketTypes": [
                    {
                        "id": 8,
                        "name": "VIP (Early Entry)",
                        "eventId": 50,
                        "quantity": 25,
                        "deleted": False,
                    }
                ],
            },
            {
                "id": 0,
                "title": "Ignored",
                "categories": [{"id": 3}],
            },
        ],
    )
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_orders_from_event_id",
        lambda self, event_id: ["order-1"] if event_id == 50 else [],
    )

    events = service.get_events_and_orders(
        event_category_id=3,
        unix_start=100,
        unix_end=200,
    )

    assert len(events) == 1
    assert calls[0] == (
        "api.tickets.test",
        "/api/v1/events?includeEnded=true&includeOffSale=true"
        "&includeTicketTypes=true&limit=9999&category=3&startsAfter=100"
        "&startsBefore=200",
        "jwt-token",
    )
    assert events[0].event_id == 50
    assert events[0].title == "VIP Night"
    assert events[0].event_category_id == 3
    assert events[0].thumbnail == "small.jpg"
    assert events[0].ticket_socket_url == "https://api.tickets.test/event/vip-night"
    assert events[0].event_date == "2026-05-01"
    assert events[0].venue.name == "Arena"
    assert events[0].venue.address1 == "123 Main, Suite B"
    assert events[0].venue.city == "Austin"
    assert events[0].venue.state == "TX"
    assert events[0].venue.postal_code == "73301"
    assert events[0].venue.country.country_name == "USA"
    assert events[0].ticket_types[0].ticket_type_name == "VIP"
    assert events[0].ticket_types[0].is_active is True
    assert events[0].orders == ["order-1"]


def test_get_events_and_orders_uses_default_start_and_timestamp_fallback(
    monkeypatch,
):
    """
    Test that get_events_and_orders uses the default start time and timestamp fallback.
    """
    calls = []
    service = create_service(monkeypatch, utc_offset_hours=1)
    monkeypatch.setattr(ticket_socket_service.time, "time", lambda: 5000)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_country_from_country_name",
        lambda country_name, state, zip_code: None,
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: calls.append((host, url, bearer_token))
        or [
            {
                "id": 60,
                "title": "Fallback Event",
                "categories": [{"id": 4}],
                "venue": "Club",
                "customFields": {
                    "venueAddress1": "456 Side",
                    "venueCity": "Nashville",
                    "venueState": "TN",
                    "venuePostalCode": "37201",
                    "venueCountry": "Canada",
                    "timezone": "Not/A_Timezone",
                },
                "displayStartDate": "not-a-date",
                "start": 1713882000,
            }
        ],
    )
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_orders_from_event_id",
        lambda self, event_id: [],
    )

    events = service.get_events_and_orders()

    assert len(events) == 1
    assert calls[0][1].endswith("&startsAfter=5000")
    assert events[0].event_date == datetime.fromtimestamp(1713882000 + 3600).strftime(
        "%Y-%m-%d"
    )
    assert events[0].venue.address1 == "456 Side"
    assert events[0].venue.country.country_name == "Canada"
    assert events[0].venue.timezone is None


def test_get_ticket_types_from_event_normalizes_names_and_deleted_status(
    monkeypatch,
):
    """
    Test that get_ticket_types_from_event strips
    parenthetical text and marks deleted types inactive.
    """
    service = create_service(monkeypatch)

    ticket_types = service.get_ticket_types_from_event(
        [
            {
                "id": 8,
                "name": "VIP (Early Entry)",
                "eventId": 50,
                "quantity": 25,
                "deleted": False,
            },
            {
                "id": 9,
                "name": "Standard (Upper Level)",
                "eventId": 50,
                "quantity": 10,
                "deleted": True,
            },
        ]
    )

    assert [ticket_type.ticket_type_name for ticket_type in ticket_types] == [
        "VIP",
        "Standard",
    ]
    assert [ticket_type.ticket_type_order for ticket_type in ticket_types] == [1, 2]
    assert ticket_types[0].is_active is True
    assert ticket_types[1].is_active is False


def test_get_orders_from_event_id_returns_empty_when_no_order_ids(monkeypatch):
    """
    Test that get_orders_from_event_id returns an empty list when the event has no orders.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_order_ids_from_event_id",
        lambda self, event_id: [],
    )

    orders = service.get_orders_from_event_id(77)

    assert not orders


def test_get_order_ids_from_event_id_filters_invalid_ids(monkeypatch):
    """
    Test that get_order_ids_from_event_id keeps only non-zero order ids.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: [
            {"orderId": 101},
            {"orderId": 0},
            {"other": 303},
            {"orderId": 202},
        ],
    )

    order_ids = service.get_order_ids_from_event_id(88)

    assert order_ids == [101, 202]


def test_get_orders_from_event_id_maps_matching_order_response(monkeypatch):
    """
    Test that get_orders_from_event_id maps matching order responses into order objects.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_order_ids_from_event_id",
        lambda self, event_id: [11, 22],
    )

    def fake_get_https_response(host, url, bearer_token):
        _ = host, bearer_token
        if url == "/api/v1/orders/11":
            return {
                "id": 11,
                "cancelled": True,
                "deleted": True,
                "tickets": {
                    "totalCount": 2,
                    "data": [
                        {
                            "eventId": 77,
                            "purchaseDate": 1713882000,
                            "userId": 9,
                            "billing_firstName": "Ada",
                            "billing_lastName": "Lovelace",
                            "billing_city": "Austin",
                            "billing_state": "TX",
                            "billing_zip": "73301",
                            "billing_country": "USA",
                            "remoteAddr": "127.0.0.1",
                            "email": "buyer@example.com",
                            "phone": "",
                            "billing_phone": "",
                            "purchaserQuestions": [
                                {
                                    "question": "Phone Number",
                                    "answerText": "555-1212",
                                }
                            ],
                            "attendeeQuestions": [
                                {
                                    "question": "Shirt Size",
                                    "answerText": "3XL",
                                }
                            ],
                            "price": 50.0,
                            "id": 1001,
                            "ticketTypeName": "VIP",
                            "fee1Amount": 10.0,
                            "typeId": 7,
                            "barcode": "ABC123",
                            "availableScans": 2,
                            "purchaseLocation": "Online",
                            "scannedTimestamp": 123,
                            "partyMember": "Ada",
                            "partyMemberLastName": "Lovelace",
                        },
                        {
                            "eventId": 999,
                            "purchaseDate": 1713882000,
                            "price": 20.0,
                            "id": 1002,
                            "ticketTypeName": "Ignored",
                        },
                    ],
                },
            }
        return {"id": 999, "tickets": {"totalCount": 0, "data": []}}

    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        fake_get_https_response,
    )

    orders = service.get_orders_from_event_id(77)

    assert len(orders) == 1
    assert orders[0].order_id == 11
    assert orders[0].event_id == 77
    assert orders[0].cancelled is True
    assert orders[0].deleted is True
    assert orders[0].user_id == 9
    assert orders[0].purchaser_first_name == "Ada"
    assert orders[0].purchaser_last_name == "Lovelace"
    assert orders[0].purchaser_city == "Austin"
    assert orders[0].purchaser_state == "TX"
    assert orders[0].purchaser_zip_code == "73301"
    assert orders[0].purchaser_country == "USA"
    assert orders[0].purchaser_ip_address == "127.0.0.1"
    assert orders[0].email == "buyer@example.com"
    assert orders[0].phone == "555-1212"
    assert orders[0].purchase_date == datetime.fromtimestamp(1713882000).strftime(
        "%Y-%m-%d"
    )
    assert orders[0].purchase_timestamp == datetime.fromtimestamp(1713882000).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert orders[0].purchase_unix_timestamp == 1713882000
    assert len(orders[0].tickets) == 1
    assert orders[0].tickets[0].ticket_id == 1001
    assert orders[0].tickets[0].ticket_type == "VIP"
    assert orders[0].tickets[0].price == 50.0
    assert orders[0].tickets[0].service_fee == 10.0
    assert orders[0].tickets[0].ticket_type_id == 7
    assert orders[0].tickets[0].barcode == "ABC123"
    assert orders[0].tickets[0].available_scans == 2
    assert orders[0].tickets[0].purchase_location == "Online"
    assert orders[0].tickets[0].scanned_timestamp == 123
    assert orders[0].tickets[0].attendee_first_name == "Ada"
    assert orders[0].tickets[0].attendee_last_name == "Lovelace"
    assert orders[0].tickets[0].shirt_size == "XXXL"


def test_get_order_from_order_id_returns_none_for_mismatched_response_id(
    monkeypatch,
):
    """
    Test that get_order_from_order_id rejects responses for a different order id.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: {
            "id": 999,
            "tickets": {"totalCount": 0, "data": []},
        },
    )

    order = service.get_order_from_order_id(22, event_id=77)

    assert order is None


def test_get_order_from_order_id_returns_none_without_credentials(monkeypatch):
    """
    Test that get_order_from_order_id returns None when credentials are missing.
    """
    logged_errors = []
    service = create_service(monkeypatch, service_url=None, token=None)
    monkeypatch.setattr(
        ticket_socket_service.logger,
        "error",
        lambda message, ticket_socket_id: logged_errors.append(
            (message, ticket_socket_id)
        ),
    )

    order = service.get_order_from_order_id(22, event_id=77)

    assert order is None
    assert logged_errors == [
        ("service url or token not present for ticket_socket_id %s", 7)
    ]


def test_init_leaves_defaults_when_account_and_token_lookups_fail(monkeypatch):
    """
    Test that initialization leaves defaults alone when no account row or JWT is returned.
    """
    monkeypatch.setattr(ticket_socket_service, "db_query_one", lambda sql, data: None)
    monkeypatch.setattr(
        ticket_socket_service,
        "post_https_response",
        lambda host, url, payload: None,
    )

    service = ticket_socket_service.TicketSocketService(7)

    assert service.name == ""
    assert service.service_url == ""
    assert service.token == ""


def test_get_categories_skips_rows_missing_required_fields(monkeypatch):
    """
    Test that get_categories skips rows missing ids or titles.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: [
            {"title": "No Id"},
            {"id": 11},
            {"id": 12, "title": None},
        ],
    )

    categories = service.get_categories()

    assert not categories


def test_get_categories_returns_empty_when_payload_is_missing(monkeypatch):
    """
    Test that get_categories returns an empty list when the API payload is missing.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: None,
    )

    categories = service.get_categories()

    assert not categories


def test_get_events_and_orders_returns_empty_without_credentials(monkeypatch):
    """
    Test that get_events_and_orders returns an empty list when credentials are missing.
    """
    logged_errors = []
    service = create_service(monkeypatch, service_url=None, token=None)
    monkeypatch.setattr(
        ticket_socket_service.logger,
        "error",
        lambda message, ticket_socket_id: logged_errors.append(
            (message, ticket_socket_id)
        ),
    )

    events = service.get_events_and_orders()

    assert not events
    assert logged_errors == [
        ("service url or token not present for ticket_socket_id %s", 7)
    ]


def test_get_events_and_orders_returns_empty_when_payload_is_missing(monkeypatch):
    """
    Test that get_events_and_orders returns an empty list when the API payload is missing.
    """
    calls = []
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: calls.append((host, url, bearer_token)) or None,
    )

    events = service.get_events_and_orders(unix_end=200)

    assert not events
    assert calls[0][1].endswith("&startsBefore=200")


def test_get_events_and_orders_skips_invalid_rows_and_uses_custom_field_fallbacks(
    monkeypatch,
):
    """
    Test that get_events_and_orders skips invalid rows and can use custom-field fallbacks.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_country_from_country_name",
        lambda country_name, state, zip_code: Country(1, country_name, "US"),
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: [
            {"title": "Missing Id"},
            {"id": 61, "categories": [{"id": 4}]},
            {"id": 62, "title": "No Categories"},
            {"id": 63, "title": "Bad Category", "categories": [{}]},
            {
                "id": 64,
                "title": "No Date",
                "categories": [{"id": 4}],
                "custom_fields": {"venueCity": "Austin"},
            },
            {
                "id": 65,
                "title": "Custom Event",
                "categories": [{"id": 4}],
                "custom_fields": {
                    "venueAddress2": "Suite C",
                    "venueCity": "Nashville",
                    "venueState": "TN",
                    "venuePostalCode": "37201",
                    "venueCountry": "USA",
                    "timezone": "America/Chicago",
                },
                "start": 1713882000,
            },
        ],
    )
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_orders_from_event_id",
        lambda self, event_id: [],
    )

    events = service.get_events_and_orders(unix_start=100)

    assert len(events) == 1
    assert events[0].event_id == 65
    assert events[0].venue.address1 == "Suite C"
    assert events[0].venue.city == "Nashville"
    assert events[0].venue.timezone == "America/Chicago"
    assert not events[0].ticket_types


def test_get_events_and_orders_maps_events_without_any_city_source(monkeypatch):
    """
    Test that get_events_and_orders can map events even when no city source is present.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_country_from_country_name",
        lambda country_name, state, zip_code: Country(1, country_name, "US"),
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: [
            {
                "id": 66,
                "title": "No City Event",
                "categories": [{"id": 4}],
                "start": 1713882000,
            }
        ],
    )
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_orders_from_event_id",
        lambda self, event_id: [],
    )

    events = service.get_events_and_orders(unix_start=100)

    assert len(events) == 1
    assert events[0].venue.city is None


def test_get_ticket_types_from_event_returns_empty_for_empty_lists(monkeypatch):
    """
    Test that get_ticket_types_from_event returns an empty list for empty payloads.
    """
    service = create_service(monkeypatch)

    ticket_types = service.get_ticket_types_from_event([])

    assert not ticket_types


def test_get_ticket_types_from_event_keeps_plain_names_without_deleted_flags(
    monkeypatch,
):
    """
    Test that get_ticket_types_from_event keeps plain names and defaults deleted flags to active.
    """
    service = create_service(monkeypatch)

    ticket_types = service.get_ticket_types_from_event(
        [{"id": 10, "name": "General", "eventId": 50, "quantity": 5}]
    )

    assert len(ticket_types) == 1
    assert ticket_types[0].ticket_type_name == "General"
    assert ticket_types[0].is_active is True


def test_get_ticket_types_from_event_keeps_empty_names(monkeypatch):
    """
    Test that get_ticket_types_from_event keeps empty names when there is nothing to normalize.
    """
    service = create_service(monkeypatch)

    ticket_types = service.get_ticket_types_from_event(
        [{"id": 10, "name": "", "eventId": 50, "quantity": 5}]
    )

    assert len(ticket_types) == 1
    assert ticket_types[0].ticket_type_name is None


def test_get_orders_from_event_id_returns_empty_without_credentials(monkeypatch):
    """
    Test that get_orders_from_event_id returns an empty list and logs when credentials are missing.
    """
    logged_errors = []
    service = create_service(monkeypatch, service_url=None, token=None)
    monkeypatch.setattr(
        ticket_socket_service.logger,
        "error",
        lambda message, ticket_socket_id: logged_errors.append(
            (message, ticket_socket_id)
        ),
    )
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_order_ids_from_event_id",
        lambda self, event_id: [11],
    )

    orders = service.get_orders_from_event_id(77)

    assert not orders
    assert logged_errors == [
        ("service url or token not present for ticket_socket_id %s", 7)
    ]


def test_get_orders_from_event_id_skips_empty_and_missing_order_responses(monkeypatch):
    """
    Test that get_orders_from_event_id skips empty responses and responses missing valid ids.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "get_order_ids_from_event_id",
        lambda self, event_id: [11, 22, 33],
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: (
            None
            if url.endswith("/11")
            else (
                {"tickets": {"totalCount": 0, "data": []}}
                if url.endswith("/22")
                else {"id": 0, "tickets": {"totalCount": 0, "data": []}}
            )
        ),
    )

    orders = service.get_orders_from_event_id(77)

    assert not orders


def test_get_order_from_order_id_returns_none_for_missing_payload_or_id(monkeypatch):
    """
    Test that get_order_from_order_id returns None for empty payloads and payloads without ids.
    """
    service = create_service(monkeypatch)
    responses = iter(
        [
            None,
            {"tickets": {"totalCount": 0, "data": []}},
        ]
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: next(responses),
    )

    order_one = service.get_order_from_order_id(22, event_id=77)
    order_two = service.get_order_from_order_id(22, event_id=77)

    assert order_one is None
    assert order_two is None


def test_get_order_from_order_id_parses_matching_ids(monkeypatch):
    """
    Test that get_order_from_order_id parses matching order ids.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: {
            "id": 22,
            "tickets": {"totalCount": 0, "data": []},
        },
    )
    monkeypatch.setattr(
        ticket_socket_service.TicketSocketService,
        "_TicketSocketService__parse_response_to_order_object",
        lambda self, order_id, event_id, json_data: ("parsed", order_id, event_id),
    )

    order = service.get_order_from_order_id(22, event_id=77)

    assert order == ("parsed", 22, 77)


def test_get_order_ids_from_event_id_returns_empty_without_credentials(monkeypatch):
    """
    Test that get_order_ids_from_event_id returns an empty list and logs when credentials are missing.
    """
    logged_errors = []
    service = create_service(monkeypatch, service_url=None, token=None)
    monkeypatch.setattr(
        ticket_socket_service.logger,
        "error",
        lambda message, ticket_socket_id: logged_errors.append(
            (message, ticket_socket_id)
        ),
    )

    order_ids = service.get_order_ids_from_event_id(88)

    assert not order_ids
    assert logged_errors == [
        ("service url or token not present for ticket_socket_id %s", 7)
    ]


def test_get_order_ids_from_event_id_returns_empty_for_missing_payloads(monkeypatch):
    """
    Test that get_order_ids_from_event_id returns an empty list when the API payload is missing.
    """
    service = create_service(monkeypatch)
    monkeypatch.setattr(
        ticket_socket_service,
        "get_https_response",
        lambda host, url, bearer_token: None,
    )

    order_ids = service.get_order_ids_from_event_id(88)

    assert not order_ids


def test_parse_response_to_order_object_handles_empty_ticket_payloads(monkeypatch):
    """
    Test that the order parser returns an empty order when there are no tickets to map.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )

    order = parse_order(11, 77, {"cancelled": True, "deleted": True})

    assert order.order_id == 11
    assert order.event_id == 77
    assert order.cancelled is True
    assert order.deleted is True
    assert not order.tickets


def test_parse_response_to_order_object_skips_tickets_without_purchase_dates_or_ids(
    monkeypatch,
):
    """
    Test that the order parser skips tickets that cannot establish a purchase date or valid id.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )

    order = parse_order(
        11,
        77,
        {
            "tickets": {
                "totalCount": 2,
                "data": [
                    {
                        "eventId": 77,
                        "id": 1001,
                        "ticketTypeName": "VIP",
                    },
                    build_order_ticket_item(id=0),
                ],
            }
        },
    )

    assert order.order_id == 11
    assert not order.tickets


def test_parse_response_to_order_object_preserves_existing_order_values(monkeypatch):
    """
    Test that the order parser keeps the first non-empty order values and uses billing phone fallback.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )
    monkeypatch.setattr(
        ticket_socket_service,
        "fix_magic_quotes",
        lambda value: f"fixed:{value}",
    )

    order = parse_order(
        11,
        77,
        {
            "tickets": {
                "totalCount": 2,
                "data": [
                    build_order_ticket_item(
                        purchaserQuestions=[{"question": "", "answerText": "ignored"}],
                        attendeeQuestions=[
                            {"question": "Shirt Size", "answerText": " "}
                        ],
                    ),
                    build_order_ticket_item(
                        billing_firstName="Grace",
                        billing_lastName="Hopper",
                        billing_city="New York",
                        billing_state="NY",
                        billing_zip="10001",
                        billing_country="Canada",
                        remoteAddr="192.168.1.1",
                        email="other@example.com",
                        phone="999-9999",
                        purchaserQuestions=[
                            {"question": "Phone Number", "answerText": "444-4444"}
                        ],
                        attendeeQuestions=[
                            {"question": "Shirt Size", "answerText": "extra small"}
                        ],
                        id=1002,
                    ),
                ],
            }
        },
    )

    assert len(order.tickets) == 2
    assert order.purchaser_first_name == "fixed:Ada"
    assert order.purchaser_last_name == "fixed:Lovelace"
    assert order.purchaser_city == "fixed:Austin"
    assert order.purchaser_state == "fixed:TX"
    assert order.purchaser_zip_code == "fixed:73301"
    assert order.purchaser_country == "fixed:USA"
    assert order.purchaser_ip_address == "fixed:127.0.0.1"
    assert order.email == "buyer@example.com"
    assert order.phone == "555-1212"
    assert order.tickets[1].shirt_size == "XS"


def test_parse_response_to_order_object_maps_minimal_ticket_payloads(monkeypatch):
    """
    Test that the order parser can map a minimal valid ticket payload using default values.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )

    order = parse_order(
        11,
        77,
        {
            "tickets": {
                "totalCount": 1,
                "data": [
                    {
                        "eventId": 77,
                        "purchaseDate": 1713882000,
                        "id": 1001,
                        "ticketTypeName": "VIP",
                    }
                ],
            }
        },
    )

    assert len(order.tickets) == 1
    assert order.tickets[0].price == 0
    assert order.tickets[0].service_fee == 0
    assert order.tickets[0].ticket_type_id == 0
    assert order.tickets[0].barcode is None
    assert order.tickets[0].available_scans == 0
    assert order.tickets[0].purchase_location is None
    assert order.tickets[0].scanned_timestamp == 0
    assert order.tickets[0].attendee_first_name is None
    assert order.tickets[0].attendee_last_name is None
    assert order.tickets[0].shirt_size is None


def test_parse_response_to_order_object_handles_null_optional_fields_and_blank_answers(
    monkeypatch,
):
    """
    Test that the order parser tolerates null optional fields, missing keys, and blank shirt answers.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )

    order = parse_order(
        11,
        77,
        {
            "tickets": {
                "totalCount": 4,
                "data": [
                    build_order_ticket_item(
                        billing_firstName=None,
                        billing_lastName=None,
                        billing_city=None,
                        billing_state=None,
                        billing_zip=None,
                        billing_country=None,
                        remoteAddr=None,
                        purchaserQuestions=[
                            {"answerText": "555-0000"},
                            {"question": "Phone Number"},
                        ],
                        id=1003,
                        attendeeQuestions=[
                            {"question": "Shirt Size", "answerText": " "}
                        ],
                        partyMember=None,
                        partyMemberLastName=None,
                    ),
                    {
                        "eventId": 77,
                        "purchaseDate": 1713882000,
                        "ticketTypeName": "VIP",
                    },
                    {
                        "eventId": 77,
                        "purchaseDate": 1713882000,
                        "id": 1004,
                    },
                    {
                        "purchaseDate": 1713882000,
                        "id": 1005,
                        "ticketTypeName": "VIP",
                    },
                ],
            }
        },
    )

    assert len(order.tickets) == 1
    assert order.phone == "555-1212"
    assert order.purchaser_first_name is None
    assert order.purchaser_last_name is None
    assert order.purchaser_city is None
    assert order.purchaser_state is None
    assert order.purchaser_zip_code is None
    assert order.purchaser_country is None
    assert order.purchaser_ip_address is None
    assert order.tickets[0].attendee_first_name is None
    assert order.tickets[0].attendee_last_name is None
    assert order.tickets[0].shirt_size is None


def test_parse_response_to_order_object_keeps_blank_and_unknown_shirt_sizes(
    monkeypatch,
):
    """
    Test that the order parser handles blank stripped shirt sizes and leaves unknown values unchanged.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )
    original_override = ticket_socket_service.get_override_string_value_or_default

    monkeypatch.setattr(
        ticket_socket_service,
        "get_override_string_value_or_default",
        lambda value, default=None: (
            value if value == " " else original_override(value, default)
        ),
    )

    blank_order = parse_order(
        11,
        77,
        {
            "tickets": {
                "totalCount": 1,
                "data": [
                    build_order_ticket_item(
                        id=2001,
                        attendeeQuestions=[
                            {"question": "Shirt Size", "answerText": " "}
                        ],
                    )
                ],
            }
        },
    )
    unknown_order = parse_order(
        11,
        77,
        {
            "tickets": {
                "totalCount": 1,
                "data": [
                    build_order_ticket_item(
                        id=2002,
                        attendeeQuestions=[
                            {"question": "Shirt Size", "answerText": "Youth"}
                        ],
                    )
                ],
            }
        },
    )

    assert blank_order.tickets[0].shirt_size == ""
    assert unknown_order.tickets[0].shirt_size == "Youth"


def test_parse_response_to_order_object_handles_missing_total_counts(monkeypatch):
    """
    Test that the order parser returns an empty order when totalCount is missing.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )

    order = parse_order(11, 77, {"tickets": {"data": []}})

    assert order.order_id == 11
    assert not order.tickets


def test_parse_response_to_order_object_normalizes_multiple_shirt_size_answers(
    monkeypatch,
):
    """
    Test that the order parser normalizes the supported shirt-size aliases.
    """
    service = create_service(monkeypatch)
    parse_order = getattr(
        service,
        "_TicketSocketService__parse_response_to_order_object",
    )
    expected_sizes = {
        "3xl": "XXXL",
        "2xl": "XXL",
        "extra large": "XL",
        "large": "L",
        "medium": "M",
        "small": "S",
    }

    for index, (answer, expected) in enumerate(expected_sizes.items(), start=1):
        order = parse_order(
            11,
            77,
            {
                "tickets": {
                    "totalCount": 1,
                    "data": [
                        build_order_ticket_item(
                            id=1000 + index,
                            attendeeQuestions=[
                                {"question": "Shirt Size", "answerText": answer}
                            ],
                        )
                    ],
                }
            },
        )

        assert len(order.tickets) == 1
        assert order.tickets[0].shirt_size == expected
