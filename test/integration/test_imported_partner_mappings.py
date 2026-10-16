"""Imported event/order identities are created once and reused on subsequent refreshes."""

import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import mariadb
import pytest
from test_migrations import database  # pylint: disable=unused-import

from common import db
from common.ticket_partner_service import TicketPartnerService

pytestmark = pytest.mark.integration


def test_imported_event_and_order_mappings_are_created_and_reused(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(Path(__file__).resolve().parents[2] / "migrations/versions",
                    root / "migrations/versions", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    run("upgrade", "7e3584499b4c")

    def connect(timeout=3000):
        return mariadb.connect(host="127.0.0.1", port=int(os.environ["TEST_MARIADB_PORT"]),
                               user="root", password=os.environ["TEST_MARIADB_PASSWORD"],
                               database=os.environ["MIGRATION_DB_DB"], autocommit=True)
    monkeypatch.setattr(db, "db_get_connection", connect)
    statements = [
        "INSERT INTO Sellers (SellerId, Name) VALUES (1, 'Seller')",
        "INSERT INTO ExchangeRates (ExchangeRateId, Name, Symbol, ServiceTokenId) VALUES (1, 'Dollar', '$', 'usd')",
        "INSERT INTO TicketSocket (TicketSocketId, AccountName, ServiceUrl, ExchangeRateId) VALUES (1, 'Account', 'https://example.com', 1)",
        "INSERT INTO SellerEventCategory (SellerEventCategoryId, SellerId, TicketSocketId, EventCategoryId) VALUES (1, 1, 1, 1)",
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL) VALUES (100, 900, 1, 'Imported', '2026-11-01', '')",
        "INSERT INTO TicketSocketOrders (Id, TicketSocketEventId, EventId, OrderId, PurchaseDate, PurchaseTimestamp, UserId) VALUES (500, 100, 900, 990, '2026-10-16', '2026-10-16 12:00:00', 1)",
    ]
    with engine.begin() as connection:
        for sql in statements:
            connection.exec_driver_sql(sql)
    service = TicketPartnerService()
    assert service.ensure_order(100, 500) == 0  # Parent mapping must exist first.
    event = SimpleNamespace(seller_id=1, event_date="2026-11-01", is_vip=True,
                            ticket_socket_url="https://example.com/imported")
    payload = {"title": "Imported", "eventDate": "2026-11-01", "thumbnail": None,
               "venue": "New venue", "city": "New city"}
    cnx = connect()
    try:
        partner_event = service.ensure_imported_event(100, payload, event, cnx)
        assert partner_event > 0
        partner_order = service.ensure_order(100, 500, cnx)
        assert partner_order > 0
        assert service.ensure_imported_event(100, payload, event, cnx) == partner_event
        assert service.ensure_order(100, 500, cnx) == partner_order
        assert "id" not in payload  # Creating an application row does not mutate import data.
        event.event_date = "2026-11-02"
        assert service.ensure_imported_event(100, payload, event, cnx) == partner_event
    finally:
        cnx.close()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM Events").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM TicketPartnerEvents").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM TicketPartnerOrders").scalar_one() == 1
        assert str(connection.exec_driver_sql("SELECT EventDate FROM Events").scalar_one()) == "2026-11-02"
        row = connection.exec_driver_sql("SELECT TicketPartnerEventId, TicketSocketOrderId, TicketSocketNativeOrderId FROM OrderDetails").one()
        assert tuple(row) == (partner_event, 500, 990)
