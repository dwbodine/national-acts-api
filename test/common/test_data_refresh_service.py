"""
Unit tests for common.data_refresh_service helpers.
"""

from types import SimpleNamespace

from common.data_refresh_service import DataRefreshService
from common.models.national_acts import VipOrder


class FakeTicketSocketService:
    """
    Test double for TicketSocketService event retrieval.
    """

    instances = []
    events_by_id = {}

    def __init__(self, ticket_socket_id):
        self.ticket_socket_id = ticket_socket_id
        self.calls = []
        FakeTicketSocketService.instances.append(self)

    def get_events_and_orders(self, event_category_id, start, end):
        """
        Record query arguments and return configured events.
        """
        self.calls.append((event_category_id, start, end))
        return FakeTicketSocketService.events_by_id.get(self.ticket_socket_id, [])


class FakeSeller:
    """
    Test double for Seller lookups during refresh.
    """

    category_by_ticket_socket_id = {}
    instances = []

    def __init__(self, seller_id):
        self.seller_id = seller_id
        FakeSeller.instances.append(self)

    def get_seller_event_category(self, ticket_socket_id):
        """
        Return the configured seller event category for the TS account.
        """
        return FakeSeller.category_by_ticket_socket_id.get(ticket_socket_id)


class FakeSellerEventCategory:
    """
    Test double for SellerEventCategory lookups by TS account and category id.
    """

    mapping = {}
    calls = []

    def __init__(self, seller_id, ticket_socket_id, event_category_id):
        FakeSellerEventCategory.calls.append(
            (seller_id, ticket_socket_id, event_category_id)
        )
        result = FakeSellerEventCategory.mapping.get(
            (seller_id, ticket_socket_id, event_category_id)
        )
        self.seller_id = None if result is None else result.seller_id
        self.seller_event_category_id = (
            None if result is None else result.seller_event_category_id
        )


class FakeConnection:
    """
    Test double for a database connection with an open flag.
    """

    def __init__(self):
        self.open = True
        self.closed = False

    def close(self):
        """
        Mark the connection as closed.
        """
        self.open = False
        self.closed = True


class FakeRefreshHistory:
    """
    Test double for TicketSocketRefreshHistory results.
    """

    instances = []

    def __init__(self, *args):
        self.args = args
        self.succeeded = args[-2]
        self.error_message = args[-1]
        self.username = None
        self.order_data_rows_removed = 0
        self.commit_calls = []
        FakeRefreshHistory.instances.append(self)

    def commit(self, cnx):
        """
        Record commit calls for assertions.
        """
        self.commit_calls.append(cnx)


class FakeMessagingService:
    """
    Test double for failure email notifications.
    """

    instances = []

    def __init__(self):
        self.sent = []
        FakeMessagingService.instances.append(self)

    def send_email(self, to, subject, html, to_name):
        """
        Record outgoing email notifications.
        """
        self.sent.append((to, subject, html, to_name))


class FakeUserService:
    """
    Test double for loading the refresh user display name.
    """

    instances = []
    user_to_return = None

    def __init__(self):
        FakeUserService.instances.append(self)
        self.requested_user_id = None

    def get_user_by_id(self, user_id):
        """
        Return the configured user for the requested id.
        """
        self.requested_user_id = user_id
        return FakeUserService.user_to_return


class FakeEventService:
    """
    Test double for EventService external event syncing.
    """

    add_results = []
    add_calls = []

    def add_to_external_events(self, event_data, evt, cnx):
        """
        Record the add request and return the configured result.
        """
        FakeEventService.add_calls.append((event_data.copy(), evt.event_id, cnx))
        if FakeEventService.add_results:
            return FakeEventService.add_results.pop(0)
        return True


def create_event(event_id, event_category_id, title, orders):
    """
    Create a simple TicketSocket event-like object for retrieval tests.
    """
    event = SimpleNamespace()
    event.event_id = event_id
    event.event_category_id = event_category_id
    event.title = title
    event.ticket_socket_url = f"https://events/{event_id}"
    event.orders = orders
    return event


def create_order(order_id):
    """
    Create a simple TicketSocket order-like object for retrieval tests.
    """
    order = SimpleNamespace()
    order.order_id = order_id
    order.event_id = 10
    order.user_id = 20
    order.tickets = []
    return order


def create_country(country_name="United States", country_code="US"):
    """
    Create a simple country-like object for refresh tests.
    """
    return SimpleNamespace(country_name=country_name, country_code=country_code)


def create_venue(
    name="The Venue",
    address1="123 Main St",
    city="Seattle",
    state="WA",
    postal_code="98101",
    country=None,
):
    """
    Create a simple venue-like object for refresh tests.
    """
    return SimpleNamespace(
        name=name,
        address1=address1,
        city=city,
        state=state,
        postal_code=postal_code,
        country=country or create_country(),
    )


def create_ticket_type(
    ticket_type_id,
    ticket_type_name="GA",
    total_available=1,
    is_active=True,
    ticket_type_order=1,
):
    """
    Create a simple ticket-type-like object for refresh tests.
    """
    return SimpleNamespace(
        ticket_type_id=ticket_type_id,
        ticket_type_name=ticket_type_name,
        total_available=total_available,
        is_active=is_active,
        ticket_type_order=ticket_type_order,
    )


def create_ticket(
    ticket_id,
    ticket_type_id=1,
    ticket_type="GA",
    price=0,
    service_fee=0,
    available_scans=0,
    barcode="abc123",
    purchase_location="Online",
    scanned_timestamp=0,
    attendee_first_name="Ada",
    attendee_last_name="Lovelace",
    shirt_size="M",
):
    """
    Create a simple ticket-like object for refresh tests.
    """
    return SimpleNamespace(
        ticket_id=ticket_id,
        ticket_type_id=ticket_type_id,
        ticket_type=ticket_type,
        price=price,
        service_fee=service_fee,
        available_scans=available_scans,
        barcode=barcode,
        purchase_location=purchase_location,
        scanned_timestamp=scanned_timestamp,
        attendee_first_name=attendee_first_name,
        attendee_last_name=attendee_last_name,
        shirt_size=shirt_size,
    )


def create_refresh_order(
    order_id,
    event_id,
    purchase_date="2024-06-10",
    purchase_unix_timestamp=1718000000,
    phone="2065551212",
    user_id="user-1",
    tickets=None,
):
    """
    Create a simple order-like object for refresh tests.
    """
    return SimpleNamespace(
        order_id=order_id,
        event_id=event_id,
        purchase_date=purchase_date,
        purchase_unix_timestamp=purchase_unix_timestamp,
        phone=phone,
        user_id=user_id,
        purchaser_last_name="Buyer",
        purchaser_first_name="Test",
        purchaser_city="Seattle",
        purchaser_state="WA",
        purchaser_zip_code="98101",
        purchaser_country="USA",
        purchaser_ip_address="127.0.0.1",
        email="buyer@example.com",
        tickets=tickets or [],
    )


def create_refresh_event(
    event_id,
    seller_event_category_id,
    seller_id=7,
    title=None,
    event_date="2024-07-01",
    ticket_types=None,
    orders=None,
    venue=None,
):
    """
    Create a simple event-like object for refresh tests.
    """
    return SimpleNamespace(
        event_id=event_id,
        seller_event_category_id=seller_event_category_id,
        seller_id=seller_id,
        title=title or f"Event {event_id}",
        event_date=event_date,
        ticket_socket_url=f"https://events/{event_id}",
        thumbnail=f"https://events/{event_id}.jpg",
        is_vip=True,
        ticket_types=ticket_types or [],
        orders=orders or [],
        venue=venue or create_venue(),
    )


def test_retrieve_ticket_socket_events_for_update_maps_events_without_seller(
    monkeypatch,
):
    """
    Test that retrieve_ticket_socket_events_for_update maps TS events and resolves seller categories.
    """
    FakeTicketSocketService.instances = []
    FakeSellerEventCategory.calls = []
    FakeSellerEventCategory.mapping = {
        (None, 1, 501): SimpleNamespace(seller_id=77, seller_event_category_id=88)
    }
    FakeTicketSocketService.events_by_id = {
        1: [create_event(10, 501, "VIP One", [create_order(1001)])],
        2: [create_event(20, 999, "VIP Two", [create_order(2001)])],
    }
    monkeypatch.setattr(
        "common.data_refresh_service.db_query_all",
        lambda sql: [
            {"TicketSocketId": 1, "IsVip": 1},
            {"TicketSocketId": 2, "IsVip": 0},
        ],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketService", FakeTicketSocketService
    )
    monkeypatch.setattr(
        "common.data_refresh_service.SellerEventCategory",
        FakeSellerEventCategory,
    )

    events = DataRefreshService().retrieve_ticket_socket_events_for_update(
        start=1,
        end=2,
    )

    assert len(FakeTicketSocketService.instances) == 2
    assert FakeTicketSocketService.instances[0].calls == [(None, 1, 2)]
    assert FakeTicketSocketService.instances[1].calls == [(None, 1, 2)]
    assert len(events) == 1
    assert events[0].event_id == 10
    assert events[0].is_vip is True
    assert events[0].seller_id == 77
    assert events[0].seller_event_category_id == 88
    assert len(events[0].orders) == 1
    assert isinstance(events[0].orders[0], VipOrder)
    assert events[0].orders[0].order_id == 1001


def test_retrieve_ticket_socket_events_for_update_respects_seller_categories(
    monkeypatch,
):
    """
    Test that retrieve_ticket_socket_events_for_update only queries TS accounts assigned to the seller.
    """
    FakeTicketSocketService.instances = []
    FakeTicketSocketService.events_by_id = {
        1: [create_event(10, 501, "VIP One", [])],
        2: [create_event(20, 999, "VIP Two", [])],
    }
    FakeSeller.instances = []
    FakeSeller.category_by_ticket_socket_id = {
        1: SimpleNamespace(
            seller_id=55,
            seller_event_category_id=66,
            event_category_id=501,
        )
    }
    monkeypatch.setattr(
        "common.data_refresh_service.db_query_all",
        lambda sql: [
            {"TicketSocketId": 1, "IsVip": 1},
            {"TicketSocketId": 2, "IsVip": 0},
        ],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketService", FakeTicketSocketService
    )
    monkeypatch.setattr("common.data_refresh_service.Seller", FakeSeller)

    events = DataRefreshService().retrieve_ticket_socket_events_for_update(
        seller_id=9,
        start=11,
        end=22,
    )

    assert FakeSeller.instances[0].seller_id == 9
    assert FakeTicketSocketService.instances[0].calls == [(501, 11, 22)]
    assert not FakeTicketSocketService.instances[1].calls
    assert len(events) == 1
    assert events[0].seller_id == 55
    assert events[0].seller_event_category_id == 66


def test_retrieve_ticket_socket_events_for_update_skips_empty_and_unmapped_events(
    monkeypatch,
):
    """
    Test that retrieve_ticket_socket_events_for_update skips empty TicketSocket responses and events without a mapped seller category.
    """
    FakeTicketSocketService.instances = []
    FakeSellerEventCategory.calls = []
    FakeSellerEventCategory.mapping = {}
    FakeTicketSocketService.events_by_id = {
        1: [],
        2: [create_event(30, None, "Unmapped Event", [])],
    }
    monkeypatch.setattr(
        "common.data_refresh_service.db_query_all",
        lambda sql: [
            {"TicketSocketId": 1, "IsVip": 1},
            {"TicketSocketId": 2, "IsVip": 0},
        ],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketService", FakeTicketSocketService
    )
    monkeypatch.setattr(
        "common.data_refresh_service.SellerEventCategory",
        FakeSellerEventCategory,
    )

    events = DataRefreshService().retrieve_ticket_socket_events_for_update()

    assert not events
    assert FakeTicketSocketService.instances[0].calls == [(None, None, None)]
    assert FakeTicketSocketService.instances[1].calls == [(None, None, None)]
    assert not FakeSellerEventCategory.calls


def test_refresh_database_from_ticket_socket_commits_empty_results_as_system(
    monkeypatch,
):
    """
    Test that refresh_database_from_ticket_socket commits empty results and labels them as System.
    """
    FakeRefreshHistory.instances = []
    fake_connection = FakeConnection()
    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: [],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.db_get_connection", lambda: fake_connection
    )
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketRefreshHistory",
        FakeRefreshHistory,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.MessagingService", FakeMessagingService
    )

    results = DataRefreshService().refresh_database_from_ticket_socket(
        seller_id=4,
        start=10,
        end=20,
        user_id=0,
    )

    assert results is FakeRefreshHistory.instances[0]
    assert results.username == "System"
    assert results.order_data_rows_removed == 0
    assert results.commit_calls == [fake_connection]
    assert fake_connection.closed is True
    assert not FakeMessagingService.instances


def test_refresh_database_from_ticket_socket_sets_username_for_user_id(monkeypatch):
    """
    Test that refresh_database_from_ticket_socket loads the display name for a user-triggered refresh.
    """
    FakeRefreshHistory.instances = []
    FakeUserService.instances = []
    FakeUserService.user_to_return = SimpleNamespace(
        user_full_name=lambda: "Ada Lovelace (ada@example.com)"
    )
    fake_connection = FakeConnection()
    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: [],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.db_get_connection", lambda: fake_connection
    )
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketRefreshHistory",
        FakeRefreshHistory,
    )
    monkeypatch.setattr("common.data_refresh_service.UserService", FakeUserService)

    results = DataRefreshService().refresh_database_from_ticket_socket(user_id=12)

    assert results.username == "Ada Lovelace (ada@example.com)"
    assert FakeUserService.instances


def test_refresh_database_from_ticket_socket_sends_email_when_refresh_raises(
    monkeypatch,
):
    """
    Test that refresh_database_from_ticket_socket emails dB when refresh orchestration raises an error.
    """
    FakeMessagingService.instances = []
    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        "common.data_refresh_service.MessagingService", FakeMessagingService
    )

    results = DataRefreshService().refresh_database_from_ticket_socket()

    assert results is None
    assert FakeMessagingService.instances
    assert FakeMessagingService.instances[0].sent[0][0] == "dwbodine@gmail.com"
    assert "Error in TS Refresh" in FakeMessagingService.instances[0].sent[0][1]
    assert "boom" in FakeMessagingService.instances[0].sent[0][2]


def test_refresh_database_from_ticket_socket_processes_existing_and_new_records(
    monkeypatch,
):
    """
    Test that refresh_database_from_ticket_socket updates and inserts events, orders, tickets, and ticket types.
    """
    FakeRefreshHistory.instances = []
    FakeUserService.instances = []
    FakeUserService.user_to_return = SimpleNamespace(
        user_full_name=lambda: "Grace Hopper (grace@example.com)"
    )
    FakeEventService.add_calls = []
    FakeEventService.add_results = [True, True]
    fake_connection = FakeConnection()

    skipped_event = create_refresh_event(99, 0, title="Skipped Event")
    existing_event = create_refresh_event(
        100,
        10,
        title="Existing Event",
        ticket_types=[
            create_ticket_type(201, total_available=1, ticket_type_order=2),
            create_ticket_type(202, "Balcony", total_available=0),
        ],
        orders=[
            create_refresh_order(5000, 999),
            create_refresh_order(
                5001,
                100,
                tickets=[
                    create_ticket(7001, ticket_type_id=201, price=50),
                    create_ticket(7002, ticket_type_id=202, price=0),
                ],
            ),
            create_refresh_order(5002, 100, tickets=[]),
        ],
    )
    existing_without_external = create_refresh_event(
        101,
        11,
        title="Existing Without External",
    )
    new_event = create_refresh_event(
        102,
        12,
        title="New Event",
    )
    all_events = [
        skipped_event,
        existing_event,
        existing_without_external,
        new_event,
    ]

    def fake_query_one(sql, data=None, cnx=None):
        """
        Return configured rows for event, order, ticket-type, and ticket lookups.
        """
        _ = cnx
        result = None
        if "FROM TicketSocketEvents" in sql:
            event_id = data["event_id"]
            if event_id == 100:
                result = {"Id": 300}
            elif event_id == 101:
                result = {"Id": 301}
        elif "FROM ExternalEvents" in sql:
            if data["id"] == 300:
                result = {"EventDate": "2024-01-01", "EventId": 900}
        elif "FROM TicketSocketTicketTypes" in sql:
            if data["ticketSocketTicketTypeId"] == 201:
                result = {"TicketTypeOrder": 9}
        elif "FROM TicketSocketOrders" in sql:
            if data["order_id"] == 5001:
                result = {
                    "Id": 800,
                    "PhoneFormatted": "+1 206-555-9999",
                    "Phone": "2065559999",
                    "IsComped": 0,
                    "IsDeleted": 0,
                    "IsActive": 1,
                    "PurchaseDate": "2024-06-01",
                }
        elif "FROM TicketSocketOrderTickets" in sql:
            if data["ticketId"] == 7001:
                result = {"Id": 900, "IsChargedBack": 0, "IsActive": 1}
        return result

    def fake_query_all(sql, data=None):
        """
        Return cleanup rows for changed purchase dates.
        """
        _ = data
        if "FROM DailyOrderData" in sql:
            return [{"DailyOrderDataId": 1000}]
        return []

    insert_ids = iter([401, 501, 601, 302])

    def fake_insert(sql, data, cnx=None):
        """
        Return deterministic ids for inserts during refresh.
        """
        _ = sql, data, cnx
        return next(insert_ids)

    update_calls = []
    delete_calls = []

    def fake_update(sql, data, cnx=None):
        """
        Record successful updates during refresh.
        """
        _ = cnx
        update_calls.append((sql, dict(data)))
        return True

    def fake_delete(sql, data, cnx=None):
        """
        Record successful deletes during refresh.
        """
        _ = cnx
        delete_calls.append((sql, dict(data)))
        return True

    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: all_events,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.db_get_connection", lambda: fake_connection
    )
    monkeypatch.setattr("common.data_refresh_service.db_query_one", fake_query_one)
    monkeypatch.setattr("common.data_refresh_service.db_query_all", fake_query_all)
    monkeypatch.setattr("common.data_refresh_service.db_insert", fake_insert)
    monkeypatch.setattr("common.data_refresh_service.db_update", fake_update)
    monkeypatch.setattr("common.data_refresh_service.db_delete", fake_delete)
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketRefreshHistory",
        FakeRefreshHistory,
    )
    monkeypatch.setattr("common.data_refresh_service.UserService", FakeUserService)
    monkeypatch.setattr("common.data_refresh_service.EventService", FakeEventService)
    monkeypatch.setattr(
        "common.data_refresh_service.get_pacific_purchase_date_from_order",
        lambda order: order.purchase_date,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.get_pacific_purchase_timestamp_from_order",
        lambda order: f"{order.purchase_date} 12:00:00",
    )

    results = DataRefreshService().refresh_database_from_ticket_socket(
        seller_id=5,
        start=1,
        end=2,
        user_id=44,
    )

    assert results is FakeRefreshHistory.instances[0]
    assert results.username == "Grace Hopper (grace@example.com)"
    assert results.order_data_rows_removed == 1
    assert results.succeeded is True
    assert results.commit_calls == [fake_connection]
    assert fake_connection.closed is True
    assert results.args[0] == ["Skipped Event - eventId 99 (https://events/99)"]
    assert results.args[1] == []
    assert results.args[2] == []
    assert results.args[3] == []
    assert results.args[4] == []
    assert results.args[5] == 4
    assert results.args[6] == 2
    assert results.args[7] == 1
    assert results.args[8] == 1
    assert results.args[9] == 1
    assert results.args[11] == 1
    assert results.args[12] == 1
    assert results.args[13] == 1
    assert results.args[14] == 1
    assert len(FakeEventService.add_calls) == 2
    assert FakeEventService.add_calls[0][1] == 101
    assert FakeEventService.add_calls[1][1] == 102
    assert any("UPDATE ExternalEvents SET EventDate" in sql for sql, _ in update_calls)
    assert any(
        "UPDATE TicketSocketEvents SET IsSoldOut" in sql for sql, _ in update_calls
    )
    assert any(data["dailyOrderDataId"] == 1000 for _, data in delete_calls if data)


def test_refresh_database_from_ticket_socket_tracks_failures_and_emails_results(
    monkeypatch,
):
    """
    Test that refresh_database_from_ticket_socket records per-entity failures and emails the failed refresh summary.
    """
    FakeRefreshHistory.instances = []
    FakeMessagingService.instances = []
    FakeEventService.add_calls = []
    FakeEventService.add_results = [False]
    fake_connection = FakeConnection()

    failed_event = create_refresh_event(200, 20, title="Failed Event")
    ticket_type_failure_event = create_refresh_event(
        201,
        21,
        title="Ticket Type Failure",
        ticket_types=[create_ticket_type(301)],
    )
    order_failure_event = create_refresh_event(
        202,
        22,
        title="Order Failure",
        orders=[create_refresh_order(6001, 202, phone="bad-phone", tickets=[])],
    )
    ticket_failure_event = create_refresh_event(
        203,
        23,
        title="Ticket Failure",
        orders=[
            create_refresh_order(
                6002,
                203,
                phone="bad-phone",
                tickets=[create_ticket(7101, price=10)],
            )
        ],
    )
    new_event_failure = create_refresh_event(204, 24, title="New Event Failure")
    all_events = [
        failed_event,
        ticket_type_failure_event,
        order_failure_event,
        ticket_failure_event,
        new_event_failure,
    ]

    def fake_query_one(sql, data=None, cnx=None):
        """
        Return configured rows for failure scenarios.
        """
        _ = cnx
        result = None
        if "FROM TicketSocketEvents" in sql:
            event_id = data["event_id"]
            if event_id in (200, 201, 202, 203):
                result = {"Id": event_id + 1000}
        elif "FROM ExternalEvents" in sql:
            result = {"EventDate": "2024-07-01", "EventId": 901}
        elif "FROM TicketSocketTicketTypes" in sql:
            result = None
        elif "FROM TicketSocketOrders" in sql:
            if data["order_id"] == 6001:
                result = {
                    "Id": 820,
                    "PhoneFormatted": None,
                    "Phone": None,
                    "IsComped": 0,
                    "IsDeleted": 0,
                    "IsActive": 1,
                    "PurchaseDate": "2024-06-10",
                }
            elif data["order_id"] == 6002:
                result = {
                    "Id": 821,
                    "PhoneFormatted": None,
                    "Phone": None,
                    "IsComped": 0,
                    "IsDeleted": 0,
                    "IsActive": 1,
                    "PurchaseDate": "2024-06-10",
                }
        elif "FROM TicketSocketOrderTickets" in sql:
            result = {"Id": 930, "IsChargedBack": 0, "IsActive": 1}
        return result

    def fake_query_all(sql, data=None):
        """
        Return no cleanup rows for failure scenarios.
        """
        _ = sql, data
        return []

    def fake_insert(sql, data, cnx=None):
        """
        Fail the ticket type insert and the new event insert.
        """
        _ = data, cnx
        if "INSERT INTO TicketSocketTicketTypes" in sql:
            return 0
        if "INSERT INTO TicketSocketEvents" in sql:
            return 0
        return 999

    def fake_update(sql, data, cnx=None):
        """
        Fail the configured event, order, and ticket updates.
        """
        _ = cnx
        if "UPDATE TicketSocketEvents SET Title" in sql and data["id"] == 1200:
            return False
        if "UPDATE TicketSocketOrders" in sql and data["id"] == 820:
            return False
        if "UPDATE TicketSocketOrderTickets" in sql and data["id"] == 930:
            return False
        return True

    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: all_events,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.db_get_connection", lambda: fake_connection
    )
    monkeypatch.setattr("common.data_refresh_service.db_query_one", fake_query_one)
    monkeypatch.setattr("common.data_refresh_service.db_query_all", fake_query_all)
    monkeypatch.setattr("common.data_refresh_service.db_insert", fake_insert)
    monkeypatch.setattr("common.data_refresh_service.db_update", fake_update)
    monkeypatch.setattr("common.data_refresh_service.db_delete", lambda *args: True)
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketRefreshHistory",
        FakeRefreshHistory,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.MessagingService", FakeMessagingService
    )
    monkeypatch.setattr("common.data_refresh_service.EventService", FakeEventService)
    monkeypatch.setattr(
        "common.data_refresh_service.get_pacific_purchase_date_from_order",
        lambda order: order.purchase_date,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.get_pacific_purchase_timestamp_from_order",
        lambda order: f"{order.purchase_date} 12:00:00",
    )
    monkeypatch.setattr(
        "common.data_refresh_service.phonenumbers.parse",
        lambda phone, region: (_ for _ in ()).throw(ValueError("bad phone")),
    )

    results = DataRefreshService().refresh_database_from_ticket_socket()

    assert results is FakeRefreshHistory.instances[0]
    assert results.succeeded is False
    assert results.args[1] == [200, 204]
    assert results.args[2] == [6001]
    assert results.args[3] == [7101]
    assert results.args[4] == [301]
    assert FakeMessagingService.instances
    assert "Error in TS Refresh" in FakeMessagingService.instances[0].sent[0][1]
    assert '"errorMessage": null' in FakeMessagingService.instances[0].sent[0][2]


def test_refresh_database_from_ticket_socket_covers_remaining_order_and_ticket_branches(
    monkeypatch,
):
    """
    Test that refresh_database_from_ticket_socket covers the remaining order, phone, cleanup, and ticket SQL branches.
    """
    FakeRefreshHistory.instances = []
    fake_connection = FakeConnection()
    event = create_refresh_event(
        300,
        30,
        ticket_types=[create_ticket_type(401, total_available=2)],
        orders=[
            create_refresh_order(
                7001,
                300,
                phone="2065550000",
                tickets=[create_ticket(8001, price=0)],
            ),
            create_refresh_order(
                7002,
                300,
                phone="6045550000",
                tickets=[create_ticket(8002, price=25)],
            ),
            create_refresh_order(7003, 300, phone="9999999999", tickets=[]),
            create_refresh_order(7004, 300, phone="", tickets=[]),
        ],
    )
    venue_without_country = create_venue()
    venue_without_country.country = None
    venues_by_order_id = {
        7001: venue_without_country,
        7002: create_venue(country=create_country("Canada", "CA")),
        7003: create_venue(country=create_country()),
        7004: create_venue(country=create_country()),
    }

    def fake_query_one(sql, data=None, cnx=None):
        """
        Return configured rows for the remaining branch coverage scenario.
        """
        _ = cnx
        result = None
        if "FROM TicketSocketEvents" in sql:
            result = {"Id": 1300}
        elif "FROM ExternalEvents" in sql:
            result = {"EventDate": "2024-07-01", "EventId": 930}
        elif "FROM TicketSocketTicketTypes" in sql:
            result = {"TicketTypeOrder": 1}
        elif "FROM TicketSocketOrders" in sql:
            order_id = data["order_id"]
            event.venue = venues_by_order_id[order_id]
            order_rows = {
                7001: {
                    "Id": 830,
                    "PhoneFormatted": "saved",
                    "Phone": "2065550000",
                    "IsComped": 1,
                    "IsDeleted": 0,
                    "IsActive": 1,
                    "PurchaseDate": "2024-06-01",
                },
                7002: {
                    "Id": 831,
                    "PhoneFormatted": "ca formatted",
                    "Phone": "6045550000",
                    "IsComped": 0,
                    "IsDeleted": 0,
                    "IsActive": 1,
                    "PurchaseDate": "2024-06-01",
                },
                7003: {
                    "Id": 832,
                    "PhoneFormatted": None,
                    "Phone": "9999999999",
                    "IsComped": 0,
                    "IsDeleted": 0,
                    "IsActive": 1,
                    "PurchaseDate": "2024-06-01",
                },
            }
            result = order_rows.get(order_id)
        elif "FROM TicketSocketOrderTickets" in sql and data["ticketId"] == 8001:
            result = {"Id": 940, "IsChargedBack": 0, "IsActive": 0}
        return result

    cleanup_query_count = {"count": 0}

    def fake_query_all(sql, data=None):
        """
        Return a cleanup row for changed orders and no rows otherwise.
        """
        _ = sql
        if data and data["purchaseDate"] == "2024-06-01":
            cleanup_query_count["count"] += 1
            if cleanup_query_count["count"] == 1:
                return [{"DailyOrderDataId": 1100}]
            return []
        return []

    insert_sql = []
    update_sql = []

    def fake_insert(sql, data, cnx=None):
        """
        Record new ticket and order inserts for assertions.
        """
        _ = data, cnx
        insert_sql.append(sql)
        if "INSERT INTO TicketSocketOrderTickets" in sql:
            return 950
        return 960

    def fake_update(sql, data, cnx=None):
        """
        Record successful updates for assertions.
        """
        _ = cnx
        update_sql.append((sql, dict(data)))
        return True

    def fake_delete(sql, data, cnx=None):
        """
        Fail cleanup deletes while allowing migrated-ticket cleanup.
        """
        _ = data, cnx
        if "DELETE FROM DailyOrderData" in sql:
            return False
        return True

    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: [event],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.db_get_connection", lambda: fake_connection
    )
    monkeypatch.setattr("common.data_refresh_service.db_query_one", fake_query_one)
    monkeypatch.setattr("common.data_refresh_service.db_query_all", fake_query_all)
    monkeypatch.setattr("common.data_refresh_service.db_insert", fake_insert)
    monkeypatch.setattr("common.data_refresh_service.db_update", fake_update)
    monkeypatch.setattr("common.data_refresh_service.db_delete", fake_delete)
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketRefreshHistory",
        FakeRefreshHistory,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.get_pacific_purchase_date_from_order",
        lambda order: order.purchase_date,
    )
    monkeypatch.setattr(
        "common.data_refresh_service.get_pacific_purchase_timestamp_from_order",
        lambda order: f"{order.purchase_date} 12:00:00",
    )
    monkeypatch.setattr(
        "common.data_refresh_service.phonenumbers.parse",
        lambda phone, region: {"phone": phone, "region": region},
    )
    monkeypatch.setattr(
        "common.data_refresh_service.phonenumbers.is_possible_number",
        lambda parsed: parsed["phone"] != "9999999999",
    )
    monkeypatch.setattr(
        "common.data_refresh_service.phonenumbers.format_number",
        lambda parsed, fmt: f"{parsed['region']}-{fmt}",
    )

    results = DataRefreshService().refresh_database_from_ticket_socket()

    assert results.succeeded is True
    assert results.order_data_rows_removed == 0
    assert any(
        "INSERT INTO TicketSocketOrderTickets" in sql and ", Price" in sql
        for sql in insert_sql
    )
    assert any(
        "UPDATE TicketSocketOrderTickets" in sql and ", Price=%(price)s" not in sql
        for sql, _ in update_sql
    )


def test_refresh_database_from_ticket_socket_leaves_username_blank_when_user_is_missing(
    monkeypatch,
):
    """
    Test that refresh_database_from_ticket_socket leaves the username unset when the requesting user cannot be loaded.
    """
    FakeRefreshHistory.instances = []
    FakeUserService.instances = []
    FakeUserService.user_to_return = None
    fake_connection = FakeConnection()
    fake_connection.open = False
    monkeypatch.setattr(
        DataRefreshService,
        "retrieve_ticket_socket_events_for_update",
        lambda self, seller_id, start, end: [],
    )
    monkeypatch.setattr(
        "common.data_refresh_service.db_get_connection", lambda: fake_connection
    )
    monkeypatch.setattr(
        "common.data_refresh_service.TicketSocketRefreshHistory",
        FakeRefreshHistory,
    )
    monkeypatch.setattr("common.data_refresh_service.UserService", FakeUserService)

    results = DataRefreshService().refresh_database_from_ticket_socket(user_id=9)

    assert results.username is None
    assert fake_connection.closed is False
