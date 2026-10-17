"""Ticket type mappings preserve event-scoped IDs and survive migration round trips."""

from pathlib import Path
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_migrations import database  # pylint: disable=unused-import
import os
import mariadb

from common import db
from common.event_service import EventService
from common.order_service import OrderService
from common.ticket_partner_service import TicketPartnerService

pytestmark = pytest.mark.integration


def test_ticket_type_backfill_projection_and_downgrade(database, monkeypatch):
    run, engine, root = database
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    run("upgrade", "0002_manual_transfer")
    statements = [
        "INSERT INTO Sellers (SellerId, Name) VALUES (1, 'Seller')",
        "INSERT INTO ExchangeRates (ExchangeRateId, Name, Symbol, ServiceTokenId) VALUES (1, 'Dollar', '$', 'usd')",
        "INSERT INTO TicketSocket (TicketSocketId, AccountName, ServiceUrl, ExchangeRateId) VALUES (1, 'Account', 'https://example.com', 1)",
        "INSERT INTO SellerEventCategory (SellerEventCategoryId, SellerId, TicketSocketId, EventCategoryId) VALUES (1, 1, 1, 1)",
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL) VALUES (100, 900, 1, 'First', '2026-11-01', ''), (200, 901, 1, 'Second', '2026-11-02', '')",
        "INSERT INTO ExternalEvents (EventId, SellerId, TicketSocketEventId, Title, EventDate) VALUES (10, 1, 100, 'First', '2026-11-01'), (20, 1, 200, 'Second', '2026-11-02')",
        "INSERT INTO TicketSocketTicketTypes (TicketSocketEventId, TicketSocketTicketTypeId, TicketTypeName, TotalAvailable, IsActive, TicketTypeOrder, LastUpdate) VALUES (100, 7, 'First VIP', 100, 1, 2, '2026-10-01 12:00:00'), (100, 0, 'Comp', 0, 1, 1, '2026-10-01 12:00:00'), (200, 7, 'Second VIP', 50, 1, 3, '2026-10-01 12:00:00'), (200, 8, 'Inactive', 25, 0, 4, '2026-10-01 12:00:00')",
    ]
    with engine.begin() as connection:
        for sql in statements:
            connection.exec_driver_sql(sql)
    run("upgrade", "7e3584499b4c")

    def connect(timeout=3000):
        return mariadb.connect(
            host="127.0.0.1",
            port=int(os.environ["TEST_MARIADB_PORT"]),
            user="root",
            password=os.environ["TEST_MARIADB_PASSWORD"],
            database=os.environ["MIGRATION_DB_DB"],
            autocommit=True,
        )

    monkeypatch.setattr(db, "db_get_connection", connect)
    with engine.connect() as connection:
        rows = (
            connection.exec_driver_sql(
                "SELECT * FROM TicketTypeDetails ORDER BY EventId, ProviderTicketTypeId"
            )
            .mappings()
            .all()
        )
        assert len(rows) == 4
        assert len({row["PartnerTicketTypeId"] for row in rows}) == 4
        assert [
            (row["EventId"], row["ProviderTicketTypeId"], row["TicketTypeName"])
            for row in rows
        ] == [
            (10, 0, "Comp"),
            (10, 7, "First VIP"),
            (20, 7, "Second VIP"),
            (20, 8, "Inactive"),
        ]
        first_event = rows[0]["TicketPartnerEventId"]
        second_event = rows[2]["TicketPartnerEventId"]
        assert rows[1]["TicketSocketEventId"] == 100
        assert rows[1]["TicketSocketNativeEventId"] == 900
        assert rows[1]["TicketSocketTicketTypeId"] == 7
        assert rows[1]["TotalAvailable"] == 100
        assert rows[1]["TicketTypeOrder"] == 2
        assert rows[3]["IsActive"] == 0
        assert rows[1]["TicketTypeLastUpdated"] == rows[1]["TicketSocketLastUpdate"]
    events = EventService().get_events_and_orders(event_id=10, get_orders=True)
    assert [kind.ticket_type_name for kind in events[0].ticket_types] == [
        "Comp",
        "First VIP",
    ]
    portal = EventService().get_events_and_orders(
        event_id=20, get_orders=True, is_portal=True
    )
    assert [kind.ticket_type_name for kind in portal[0].ticket_types] == ["Second VIP"]
    comp_service = OrderService()
    monkeypatch.setattr(
        comp_service, "rebuild_daily_order_data_for_order", lambda order: None
    )
    assert comp_service.add_comped_order(20, 1)
    with engine.connect() as connection:
        comp_type = (
            connection.exec_driver_sql(
                "SELECT * FROM TicketTypeDetails WHERE EventId=20 AND ProviderTicketTypeId=0"
            )
            .mappings()
            .one()
        )
        assert comp_type["TicketTypeName"] == "Comp"
        comp_ticket = (
            connection.exec_driver_sql("SELECT * FROM TicketDetails WHERE EventId=20")
            .mappings()
            .one()
        )
        assert comp_ticket["PartnerTicketTypeId"] == comp_type["PartnerTicketTypeId"]
    assert (
        TicketPartnerService().ensure_ticket_type(200, 0)
        == comp_type["PartnerTicketTypeId"]
    )
    assert TicketPartnerService().ensure_ticket_type(99999, 7) == 0
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO PartnerTicketTypes (TicketPartnerEventId, ProviderTicketTypeId) VALUES (:event, 7)"
            ),
            {"event": first_event},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO PartnerTicketTypes (TicketPartnerEventId, ProviderTicketTypeId) VALUES (99999, 1)"
        )
    with engine.begin() as connection:
        # The same type exists on a different event; it must not leak across.
        connection.execute(
            text(
                "INSERT INTO PartnerTicketTypes (TicketPartnerEventId, ProviderTicketTypeId) VALUES (:event, 99)"
            ),
            {"event": second_event},
        )
        connection.exec_driver_sql(
            "INSERT INTO TicketPartnerEvents (TicketPartnerEventId, TicketPartnerId, EventId, PartnerEventId) VALUES (3000, 1, 10, 100)"
        )
        connection.exec_driver_sql(
            "INSERT INTO PartnerTicketTypes (TicketPartnerEventId, ProviderTicketTypeId) VALUES (3000, 7), (3000, NULL)"
        )
    with engine.connect() as connection:
        missing = (
            connection.execute(
                text(
                    "SELECT * FROM TicketTypeDetails WHERE TicketPartnerEventId=:event AND ProviderTicketTypeId=99"
                ),
                {"event": second_event},
            )
            .mappings()
            .one()
        )
        assert missing["TicketSocketTicketTypeId"] is None
        assert missing["TicketTypeName"] is None
        local = (
            connection.exec_driver_sql(
                "SELECT * FROM TicketTypeDetails WHERE TicketPartnerEventId=3000"
            )
            .mappings()
            .all()
        )
        assert len(local) == 2
        assert all(
            row["TicketSocketEventId"] is None and row["TicketTypeName"] is None
            for row in local
        )
    run("downgrade", "0002_manual_transfer")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SHOW FULL TABLES LIKE 'TicketTypeDetails'"
            ).first()
            is None
        )
        assert (
            connection.exec_driver_sql("SHOW TABLES LIKE 'PartnerTicketTypes'").first()
            is None
        )
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM TicketSocketTicketTypes"
            ).scalar_one()
            == 5
        )
    run("upgrade", "7e3584499b4c")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM TicketTypeDetails"
            ).scalar_one()
            == 5
        )
