"""Legacy daily order identities are removed only after backfill and restored on rollback."""

from pathlib import Path
import shutil

import pytest
from test_migrations import database  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("event_is_mapped", [True, False])
def test_daily_order_columns_and_data_round_trip(database, event_is_mapped):
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
        "INSERT INTO TicketSocketEvents (Id, EventId, SellerEventCategoryId, Title, EventDate, URL) VALUES (100, 900, 1, 'First', '2026-11-01', '')",
        "INSERT INTO ExternalEvents (EventId, SellerId, TicketSocketEventId, Title, EventDate) VALUES (10, 1, 100, 'First', '2026-11-01')",
        "INSERT INTO TicketSocketOrders (Id, TicketSocketEventId, EventId, OrderId, PurchaseDate, PurchaseTimestamp, UserId) VALUES (110, 100, 900, 990, '2026-10-14', '2026-10-14 12:00:00', 1)",
        "INSERT INTO DailyOrderData (PurchaseDate, TicketSocketEventId, TicketSocketOrderId, TicketRevenue) VALUES ('2026-10-14', 100, NULL, 50), ('2026-10-15', 100, 110, 25)",
    ]
    with engine.begin() as connection:
        for sql in statements:
            if not event_is_mapped and sql.startswith("INSERT INTO ExternalEvents"):
                continue
            connection.exec_driver_sql(sql)
    if not event_is_mapped:
        with pytest.raises(RuntimeError, match="without partner mappings"):
            run("upgrade", "7e3584499b4c")
        with engine.connect() as connection:
            columns = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SHOW COLUMNS FROM DailyOrderData"
                )
            }
            assert {"TicketSocketEventId", "TicketSocketOrderId"} <= columns
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM DailyOrderData WHERE TicketSocketEventId=100"
                ).scalar_one()
                == 2
            )
        return
    run("upgrade", "7e3584499b4c")
    with engine.connect() as connection:
        columns = {
            row[0]
            for row in connection.exec_driver_sql("SHOW COLUMNS FROM DailyOrderData")
        }
        assert {"TicketPartnerEventId", "TicketPartnerOrderId"} <= columns
        assert not {"TicketSocketEventId", "TicketSocketOrderId"} & columns
        event_id = connection.exec_driver_sql(
            "SELECT TicketPartnerEventId FROM TicketPartnerEvents"
        ).scalar_one()
        order_id = connection.exec_driver_sql(
            "SELECT TicketPartnerOrderId FROM TicketPartnerOrders"
        ).scalar_one()
        assert event_id != 100 and order_id != 110
        rows = connection.exec_driver_sql(
            "SELECT TicketPartnerEventId, TicketPartnerOrderId, TicketRevenue FROM DailyOrderData ORDER BY PurchaseDate"
        ).all()
        assert [tuple(row) for row in rows] == [
            (event_id, None, 50),
            (event_id, order_id, 25),
        ]
    run("downgrade", "0002_manual_transfer")
    with engine.connect() as connection:
        columns = {
            row[0]: row
            for row in connection.exec_driver_sql("SHOW COLUMNS FROM DailyOrderData")
        }
        assert not {"TicketPartnerEventId", "TicketPartnerOrderId"} & columns.keys()
        assert columns["TicketSocketEventId"][2] == "NO"  # Restore legacy NOT NULL.
        rows = connection.exec_driver_sql(
            "SELECT TicketSocketEventId, TicketSocketOrderId, TicketRevenue FROM DailyOrderData ORDER BY PurchaseDate"
        ).all()
        assert [tuple(row) for row in rows] == [(100, None, 50), (100, 110, 25)]
        ddl = connection.exec_driver_sql("SHOW CREATE TABLE DailyOrderData").one()[1]
        assert "FK_DailyOrderData_TicketSocketEvent" in ddl
        assert "IX_DailyOrderData_PurchaseDate_EventId" in ddl
    run("upgrade", "7e3584499b4c")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM DailyOrderData"
            ).scalar_one()
            == 2
        )
