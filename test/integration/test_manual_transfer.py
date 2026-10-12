"""Reconcile a schema change already executed in production without repeating DDL."""

from pathlib import Path
import shutil

import pytest
from sqlalchemy import text
from tools import migrate
from test_migrations import database  # pylint: disable=unused-import

pytestmark = pytest.mark.integration


@pytest.fixture
def reconciled_database(database):
    run, engine, root = database
    source = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/0002_manual_transfer.py"
    )
    shutil.copy(source, root / "migrations/versions")
    run("upgrade", migrate.BASELINE)
    return run, engine, root


def test_normal_upgrade_and_downgrade(reconciled_database):
    run, engine, _ = reconciled_database
    run("upgrade", migrate.MANUAL_TRANSFER)
    with engine.connect() as connection:
        migrate.verify_manual_transfer(connection)
    run("downgrade", migrate.BASELINE)
    run("verify-baseline")


@pytest.mark.parametrize("unversioned", [False, True])
def test_adopt_existing_change_without_repeating_ddl(reconciled_database, unversioned):
    run, engine, _ = reconciled_database
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE TicketSocketOrders ADD COLUMN IsManualTransfer TINYINT NOT NULL DEFAULT 0 AFTER IsComped"
        )
        connection.exec_driver_sql(
            "INSERT INTO Activity (ActivityName) VALUES ('preserve existing data')"
        )
        if unversioned:
            connection.exec_driver_sql("DROP TABLE alembic_version")
    run("adopt-manual-transfer")
    run("adopt-manual-transfer")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == migrate.MANUAL_TRANSFER
        )
        assert (
            connection.execute(text("SELECT ActivityName FROM Activity")).scalar_one()
            == "preserve existing data"
        )


@pytest.mark.parametrize(
    "definition", ["TINYINT NOT NULL DEFAULT 1", "TINYINT DEFAULT 0"]
)
def test_adoption_refuses_missing_or_wrong_column(reconciled_database, definition):
    run, engine, _ = reconciled_database
    with pytest.raises(RuntimeError, match="TicketSocketOrders"):
        run("adopt-manual-transfer")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE TicketSocketOrders ADD COLUMN IsManualTransfer "
            + definition
            + " AFTER IsComped"
        )
    with pytest.raises(RuntimeError, match="TicketSocketOrders"):
        run("adopt-manual-transfer")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == migrate.BASELINE
        )


def test_adoption_refuses_unrelated_schema_change(reconciled_database):
    run, engine, _ = reconciled_database
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE TicketSocketOrders ADD COLUMN IsManualTransfer TINYINT NOT NULL DEFAULT 0 AFTER IsComped"
        )
        connection.exec_driver_sql("ALTER TABLE Activity ADD COLUMN unexpected INT")
    with pytest.raises(RuntimeError, match="Activity"):
        run("adopt-manual-transfer")


def test_adoption_refuses_wrong_column_position(reconciled_database):
    run, engine, _ = reconciled_database
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE TicketSocketOrders ADD COLUMN IsManualTransfer TINYINT NOT NULL DEFAULT 0"
        )
    with pytest.raises(RuntimeError, match="TicketSocketOrders"):
        run("adopt-manual-transfer")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == migrate.BASELINE
        )


def test_adoption_refuses_later_revision(reconciled_database):
    run, engine, _ = reconciled_database
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num='later_revision'")
        )
    with pytest.raises(RuntimeError, match="requires"):
        run("adopt-manual-transfer")


@pytest.mark.parametrize("flag", [1])
def test_downgrade_preserves_non_default_flags(reconciled_database, flag):
    run, engine, _ = reconciled_database
    run("upgrade", migrate.MANUAL_TRANSFER)
    with engine.begin() as connection:
        # This test isolates column preservation from unrelated event fixtures.
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        try:
            connection.execute(
                text("""
                INSERT INTO TicketSocketOrders
                    (TicketSocketEventId, EventId, OrderId, PurchaseDate,
                     PurchaseTimestamp, Phone, UserId, PurchaserLastName,
                     PurchaserFirstName, IsManualTransfer)
                VALUES (1, 1, 1, '2026-10-12', '2026-10-12 00:00:00',
                        '', 1, 'Example', 'Test', :flag)
            """),
                {"flag": flag},
            )
        finally:
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
    with pytest.raises(RuntimeError, match="non-default"):
        run("downgrade", migrate.BASELINE)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == migrate.MANUAL_TRANSFER
        )
        assert (
            connection.execute(
                text("SELECT IsManualTransfer FROM TicketSocketOrders")
            ).scalar_one()
            == flag
        )
