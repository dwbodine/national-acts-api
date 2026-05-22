"""
Unit tests for common.ticket_order_service helpers.
"""

from types import SimpleNamespace

from common import ticket_order_service
from common.models.ticket_order import (
    TicketOrder,
    TicketOrderAgeLimit,
    TicketOrderPriceLevel,
)


class FakeEventService:
    """
    Test double for loading events linked to ticket orders.
    """

    calls = []

    def get_events_and_orders(self, event_id=None, ignore_flags=False):
        """
        Record event lookups and return a simple event object.
        """
        FakeEventService.calls.append((event_id, ignore_flags))
        return SimpleNamespace(event_id=event_id, external_event_id=event_id)


def build_order(order_id=9):
    """
    Build a representative TicketOrder for update tests.
    """
    order = TicketOrder()
    order.order_id = order_id
    order.order_date = "2026-04-23"
    order.event = SimpleNamespace(external_event_id=55)
    order.age_limit = TicketOrderAgeLimit()
    order.age_limit.age_limit_id = 2
    order.age_limit.age_limit_name = "21+"
    order.is_hologram = True
    order.shipping_name = "Ada Lovelace"
    order.shipping_address = "123 Main"
    order.shipping_city = "Atlanta"
    order.shipping_state = "GA"
    order.shipping_zip = "30303"
    order.shipping_country = "USA"
    order.contact_name = "Ada Lovelace"
    order.contact_email = "ada@example.com"
    order.contact_cc_emails = ["copy1@example.com", "copy2@example.com"]
    order.contact_phone = "555-1111"
    order.ticket_note = "Front row"
    order.order_note = "Call on arrival"
    order.is_fulfulled = True
    order.is_paid = True
    order.notes = "VIP package"
    order.charged_shipping = 14.5
    order.ship_date = "2026-04-24"
    order.paid_date = "2026-04-25"
    order.price_levels = []
    return order


def build_price_level(
    ticket_order_price_level_id,
    level_id,
    level_name,
    quantity,
    price,
    per_ticket_charge,
):
    """
    Build a representative TicketOrderPriceLevel instance.
    """
    level = TicketOrderPriceLevel()
    level.ticket_order_price_level_id = ticket_order_price_level_id
    level.level_id = level_id
    level.level_name = level_name
    level.quantity = quantity
    level.price = price
    level.per_ticket_charge = per_ticket_charge
    return level


def test_get_ticket_orders_returns_mapped_orders_with_default_query(monkeypatch):
    """
    Test that get_ticket_orders maps rows with the default query when no flags are passed.
    """
    FakeEventService.calls = []
    captured_sql = []
    monkeypatch.setattr(
        ticket_order_service,
        "EventService",
        FakeEventService,
    )
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_all",
        lambda sql: captured_sql.append(sql)
        or [
            {
                "TicketOrderId": 11,
                "TicketOrderDate": "2026-04-23",
                "IsHologram": 1,
                "TicketOrderAgeLimitId": 2,
                "TicketOrderAgeLimitName": "21+",
                "EventID": 77,
                "ShippingName": "Ada Lovelace",
                "ShippingAddress": "123 Main",
                "ShippingCity": "Atlanta",
                "ShippingState": "GA",
                "ShippingZip": "30303",
                "ShippingCountry": "USA",
                "ContactName": "Ada Lovelace",
                "ContactEmail": "ada@example.com",
                "ContactPhone": "555-1111",
                "CCEmails": "copy1@example.com,copy2@example.com",
                "TicketNote": "Front row",
                "OrderNote": "Call on arrival",
                "IsFulfilled": 1,
                "IsPaid": 1,
                "Notes": "VIP package",
                "ShipDate": "2026-04-24",
                "PaidDate": "2026-04-25",
            }
        ],
    )
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: [
            build_price_level(1, 22, "VIP", 2, 150.0, 12.5),
        ],
    )

    orders = ticket_order_service.TicketOrdersService().get_ticket_orders()

    assert len(orders) == 1
    assert "FROM TicketOrders" in captured_sql[0]
    assert orders[0].order_id == 11
    assert orders[0].age_limit.age_limit_id == 2
    assert orders[0].age_limit.age_limit_name == "21+"
    assert orders[0].event.event_id == 77
    assert orders[0].contact_cc_emails == [
        "copy1@example.com",
        "copy2@example.com",
    ]
    assert orders[0].price_levels[0].level_name == "VIP"
    assert FakeEventService.calls == [(77, True)]


def test_get_ticket_orders_uses_paid_and_fulfilled_filter(monkeypatch):
    """
    Test that get_ticket_orders uses the fulfilled and paid filter query when requested.
    """
    captured_sql = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_all",
        lambda sql: captured_sql.append(sql) or [],
    )

    orders = ticket_order_service.TicketOrdersService().get_ticket_orders(
        show_fulfilled=True,
        show_paid=True,
    )

    assert not orders
    assert captured_sql[0] == " WHERE TicketOrders.Fulfilled=1 AND TicketOrders.Paid=1"


def test_get_ticket_orders_uses_unfulfilled_unpaid_filter(monkeypatch):
    """
    Test that get_ticket_orders uses the open-order filter query when both flags are false.
    """
    captured_sql = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_all",
        lambda sql: captured_sql.append(sql) or [],
    )

    orders = ticket_order_service.TicketOrdersService().get_ticket_orders(
        show_fulfilled=False,
        show_paid=False,
    )

    assert not orders
    assert captured_sql[0] == " WHERE TicketOrders.Fulfilled=0 AND TicketOrders.Paid=0"


def test_get_ticket_orders_uses_fulfilled_unpaid_filter(monkeypatch):
    """
    Test that get_ticket_orders uses the fulfilled but unpaid filter query when requested.
    """
    captured_sql = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_all",
        lambda sql: captured_sql.append(sql) or [],
    )

    orders = ticket_order_service.TicketOrdersService().get_ticket_orders(
        show_fulfilled=True,
        show_paid=False,
    )

    assert not orders
    assert captured_sql[0] == " WHERE TicketOrders.Fulfilled=1 AND TicketOrders.Paid=0"


def test_get_ticket_order_by_id_returns_none_for_blank_id():
    """
    Test that get_ticket_order_by_id returns None for blank ids.
    """
    service = ticket_order_service.TicketOrdersService()

    assert service.get_ticket_order_by_id(None) is None
    assert service.get_ticket_order_by_id(0) is None


def test_get_ticket_order_by_id_returns_none_when_row_missing(monkeypatch):
    """
    Test that get_ticket_order_by_id returns None when the database row is missing.
    """
    monkeypatch.setattr(ticket_order_service, "db_query_one", lambda sql, data: None)

    order = ticket_order_service.TicketOrdersService().get_ticket_order_by_id(5)

    assert order is None


def test_get_ticket_order_by_id_returns_none_for_invalid_row_id(monkeypatch):
    """
    Test that get_ticket_order_by_id skips rows that do not contain a valid order id.
    """
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_one",
        lambda sql, data: {"TicketOrderId": 0},
    )

    order = ticket_order_service.TicketOrdersService().get_ticket_order_by_id(5)

    assert order is None


def test_get_ticket_order_by_id_maps_price_levels_and_skips_invalid_level_rows(
    monkeypatch,
):
    """
    Test that get_ticket_order_by_id maps price levels and ignores invalid level rows.
    """
    FakeEventService.calls = []
    captured_queries = []
    monkeypatch.setattr(ticket_order_service, "EventService", FakeEventService)
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_one",
        lambda sql, data: {
            "TicketOrderId": 15,
            "TicketOrderDate": "2026-04-23",
            "IsHologram": 0,
            "TicketOrderAgeLimitId": 0,
            "TicketOrderAgeLimitName": "",
            "EventID": 0,
            "ShippingName": "Ada Lovelace",
            "ShippingAddress": "123 Main",
            "ShippingCity": "Atlanta",
            "ShippingState": "GA",
            "ShippingZip": "30303",
            "ShippingCountry": "USA",
            "ContactName": "Ada Lovelace",
            "ContactEmail": "ada@example.com",
            "ContactPhone": "555-1111",
            "CCEmails": "   ",
            "TicketNote": "Front row",
            "OrderNote": "Call on arrival",
            "IsFulfilled": 0,
            "IsPaid": 0,
            "Notes": "VIP package",
            "ShipDate": "",
            "PaidDate": "",
        },
    )
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_all",
        lambda sql, data: captured_queries.append((sql, data))
        or [
            {
                "TicketOrderPriceLevelId": 0,
                "PriceLevelId": 1,
                "PriceLevelName": "Ignored",
                "PriceLevelQuantity": 1,
                "PriceLevelPrice": 50.0,
                "PerTicketCharge": 5.0,
            },
            {
                "TicketOrderPriceLevelId": 31,
                "PriceLevelId": 2,
                "PriceLevelName": "VIP",
                "PriceLevelQuantity": 2,
                "PriceLevelPrice": 125.0,
                "PerTicketCharge": 9.5,
            },
        ],
    )

    order = ticket_order_service.TicketOrdersService().get_ticket_order_by_id(15)

    assert order is not None
    assert order.order_id == 15
    assert getattr(order, "age_limit", None) is None
    assert getattr(order, "event", None) is None
    assert order.contact_cc_emails == []
    assert len(order.price_levels) == 1
    assert order.price_levels[0].ticket_order_price_level_id == 31
    assert order.price_levels[0].level_name == "VIP"
    assert captured_queries[0][1] == {"order_id": 15}
    assert not FakeEventService.calls


def test_get_ticket_order_by_id_leaves_price_levels_empty_when_loader_returns_none(
    monkeypatch,
):
    """
    Test that get_ticket_order_by_id leaves price levels empty when the loader returns None.
    """
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_one",
        lambda sql, data: {
            "TicketOrderId": 15,
            "TicketOrderDate": "2026-04-23",
            "IsHologram": 0,
            "TicketOrderAgeLimitId": 0,
            "TicketOrderAgeLimitName": "",
            "EventID": 0,
            "ShippingName": "Ada Lovelace",
            "ShippingAddress": "123 Main",
            "ShippingCity": "Atlanta",
            "ShippingState": "GA",
            "ShippingZip": "30303",
            "ShippingCountry": "USA",
            "ContactName": "Ada Lovelace",
            "ContactEmail": "ada@example.com",
            "ContactPhone": "555-1111",
            "CCEmails": "",
            "TicketNote": "Front row",
            "OrderNote": "Call on arrival",
            "IsFulfilled": 0,
            "IsPaid": 0,
            "Notes": "VIP package",
            "ShipDate": "",
            "PaidDate": "",
        },
    )
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: None,
    )

    order = ticket_order_service.TicketOrdersService().get_ticket_order_by_id(15)

    assert order is not None
    assert order.price_levels == []


def test_get_ticket_orders_skips_rows_that_do_not_map_to_orders(monkeypatch):
    """
    Test that get_ticket_orders skips rows without valid order ids.
    """
    monkeypatch.setattr(
        ticket_order_service,
        "EventService",
        FakeEventService,
    )
    monkeypatch.setattr(
        ticket_order_service,
        "db_query_all",
        lambda sql: [{"TicketOrderId": 0}],
    )
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: [],
    )

    orders = ticket_order_service.TicketOrdersService().get_ticket_orders()

    assert not orders


def test_update_order_returns_none_for_missing_order():
    """
    Test that update_order returns None when no order is provided.
    """
    order = ticket_order_service.TicketOrdersService().update_order(None)

    assert order is None


def test_update_order_inserts_new_order_without_price_levels(monkeypatch):
    """
    Test that update_order inserts a new order and returns it when no price levels are present.
    """
    insert_calls = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 77,
    )

    order = build_order(order_id=0)

    saved_order = ticket_order_service.TicketOrdersService().update_order(order)

    assert saved_order is order
    assert "INSERT INTO TicketOrders" in insert_calls[0][0]
    assert insert_calls[0][1]["eventId"] == 55
    assert insert_calls[0][1]["ageLimitId"] == 2
    assert (
        insert_calls[0][1]["contactCCEmails"] == "copy1@example.com,copy2@example.com"
    )


def test_update_order_uses_none_when_cc_email_list_is_empty(monkeypatch):
    """
    Test that update_order stores no cc string when the cc email list is empty.
    """
    update_calls = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    order = build_order(order_id=9)
    order.contact_cc_emails = []

    saved_order = ticket_order_service.TicketOrdersService().update_order(order)

    assert saved_order is order
    assert update_calls[0][1]["contactCCEmails"] is None


def test_update_order_updates_existing_order_and_syncs_price_levels(monkeypatch):
    """
    Test that update_order updates existing orders and synchronizes price level changes.
    """
    update_calls = []
    insert_calls = []
    delete_calls = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        ticket_order_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data))
        or (300 if "TicketOrderPriceLevels" in sql else 9),
    )
    monkeypatch.setattr(
        ticket_order_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: [
            build_price_level(10, 1, "VIP", 2, 100.0, 11.0),
            build_price_level(20, 2, "GA", 1, 50.0, 6.0),
        ],
    )

    order = build_order(order_id=9)
    order.price_levels = [
        build_price_level(10, 1, "VIP Updated", 3, 125.0, 12.0),
        build_price_level(0, 3, "Balcony", 2, 75.0, 7.5),
    ]

    saved_order = ticket_order_service.TicketOrdersService().update_order(order)

    assert saved_order is order
    assert "UPDATE TicketOrders SET TicketOrderDate=%(date)s" in update_calls[0][0]
    assert update_calls[0][1]["order_id"] == 9
    assert any(
        "UPDATE TicketOrderPriceLevels SET" in call[0] for call in update_calls[1:]
    )
    assert "INSERT INTO TicketOrderPriceLevels" in insert_calls[0][0]
    assert order.price_levels[1].ticket_order_price_level_id == 300
    assert "DELETE FROM TicketOrderPriceLevel" in delete_calls[0][0]
    assert delete_calls[0][1] == {"to_price_level_id": 20}


def test_update_order_skips_invalid_new_price_levels_without_inserting(monkeypatch):
    """
    Test that update_order skips unmatched price levels that do not have a valid level id.
    """
    update_calls = []
    insert_calls = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        ticket_order_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 999,
    )
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: [],
    )

    order = build_order(order_id=9)
    order.price_levels = [
        build_price_level(0, 0, "Ignored", 1, 50.0, 5.0),
    ]

    saved_order = ticket_order_service.TicketOrdersService().update_order(order)

    assert saved_order is order
    assert len(update_calls) == 1
    assert not insert_calls


def test_update_order_returns_none_when_new_price_level_insert_fails(monkeypatch):
    """
    Test that update_order returns None when inserting a new price level fails.
    """
    monkeypatch.setattr(ticket_order_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(ticket_order_service, "db_delete", lambda sql, data: True)
    monkeypatch.setattr(
        ticket_order_service,
        "db_insert",
        lambda sql, data: 0 if "TicketOrderPriceLevels" in sql else 12,
    )
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: [],
    )

    order = build_order(order_id=0)
    order.price_levels = [
        build_price_level(0, 3, "Balcony", 2, 75.0, 7.5),
    ]

    saved_order = ticket_order_service.TicketOrdersService().update_order(order)

    assert saved_order is None


def test_update_order_returns_none_when_price_level_delete_fails(monkeypatch):
    """
    Test that update_order returns None when deleting a removed price level fails.
    """
    update_calls = []
    monkeypatch.setattr(
        ticket_order_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(ticket_order_service, "db_insert", lambda sql, data: 9)
    monkeypatch.setattr(ticket_order_service, "db_delete", lambda sql, data: False)
    monkeypatch.setattr(
        ticket_order_service.TicketOrdersService,
        "_TicketOrdersService__get_ticket_price_levels",
        lambda self, order_id: [
            build_price_level(10, 1, "VIP", 2, 100.0, 11.0),
            build_price_level(20, 2, "GA", 1, 50.0, 6.0),
        ],
    )

    order = build_order(order_id=9)
    order.price_levels = [
        build_price_level(10, 1, "VIP", 2, 100.0, 11.0),
    ]

    saved_order = ticket_order_service.TicketOrdersService().update_order(order)

    assert saved_order is None
    assert "UPDATE TicketOrders SET TicketOrderDate=%(date)s" in update_calls[0][0]
