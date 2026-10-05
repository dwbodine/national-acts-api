"""Real MariaDB migration tests. Opt in with TEST_MARIADB_PORT and password."""

import os
from pathlib import Path
import shutil
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from tools import migrate

pytestmark = pytest.mark.integration


@pytest.fixture
def database(monkeypatch, tmp_path):
    if not os.getenv("TEST_MARIADB_PORT"):
        pytest.skip("Set TEST_MARIADB_PORT to an isolated MariaDB server")
    name = "migration_ci_" + uuid.uuid4().hex
    url = URL.create(
        "mariadb+mariadbconnector",
        username="root",
        password=os.environ["TEST_MARIADB_PASSWORD"],
        host="127.0.0.1",
        port=int(os.environ["TEST_MARIADB_PORT"]),
    )
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(
            f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_uca1400_ai_ci"
        )
    for key, value in {
        "HOST": "127.0.0.1",
        "PORT": os.environ["TEST_MARIADB_PORT"],
        "DB": name,
        "USER": "root",
        "PASSWORD": os.environ["TEST_MARIADB_PASSWORD"],
    }.items():
        monkeypatch.setenv("MIGRATION_DB_" + key, value)
    root = tmp_path / "project"
    root.mkdir()
    shutil.copytree(
        migrate.ROOT / "migrations",
        root / "migrations",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # Synthetic migration tests stay isolated from future project revisions.
    for revision in (root / "migrations/versions").glob("*.py"):
        if revision.name != "0001_production_baseline.py":
            revision.unlink()
    shutil.copy(migrate.ROOT / "alembic.ini", root)
    monkeypatch.setattr(migrate, "ROOT", root)

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["migrate", *args])
        migrate.main()

    db_engine = migrate.engine()
    try:
        yield run, db_engine, root
    finally:
        db_engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE `{name}`")
        admin.dispose()


def test_actual_project_upgrade_from_previous_revision(database):
    run, engine, root = database
    project_root = Path(__file__).resolve().parents[2]
    shutil.copytree(
        project_root / "migrations/versions",
        root / "migrations/versions",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    scripts = migrate.ScriptDirectory.from_config(migrate.configuration())
    head = scripts.get_revision(scripts.get_current_head())
    previous = head.down_revision or head.revision
    run("upgrade", previous)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO Activity (ActivityName) VALUES ('previous release row')"
        )
    run("upgrade")
    run("check")
    run("upgrade")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT ActivityName FROM Activity")).scalar_one()
            == "previous release row"
        )


def test_empty_database_and_repeat_upgrade(database):
    run, engine, _ = database
    run("upgrade")
    run("check")
    run("verify-baseline")
    with engine.begin() as connection:
        assert len(migrate.snapshot(connection)) == 45
        assert connection.execute(text("SELECT COUNT(*) FROM Users")).scalar_one() == 0
        connection.exec_driver_sql(
            "INSERT INTO Activity (ActivityName) VALUES ('migration test')"
        )
    run("upgrade")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM Activity")).scalar_one() == 1
        )


def test_adoption_preserves_data_and_rejects_drift(database):
    run, engine, _ = database
    run("upgrade")
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.exec_driver_sql(
            "INSERT INTO Activity (ActivityName) VALUES ('keep me')"
        )
        connection.exec_driver_sql("ALTER TABLE Activity AUTO_INCREMENT=9000")
    with pytest.raises(RuntimeError, match="unversioned"):
        run("upgrade")
    run("adopt-baseline")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT ActivityName FROM Activity")).scalar_one()
            == "keep me"
        )
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.exec_driver_sql("ALTER TABLE Activity ADD COLUMN unexpected INT")
    with pytest.raises(RuntimeError, match="Activity"):
        run("adopt-baseline")
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SHOW TABLES LIKE 'alembic_version'").first()
            is None
        )


def test_lock_excludes_concurrent_runner(database):
    run, engine, _ = database
    with engine.connect() as connection:
        name = connection.execute(text("SELECT DATABASE()")).scalar_one()
        assert (
            connection.execute(
                text("SELECT GET_LOCK(:name, 0)"),
                {"name": "nationalacts:migrate:" + name},
            ).scalar_one()
            == 1
        )
        try:
            with pytest.raises(RuntimeError, match="Another migration runner"):
                run("upgrade")
        finally:
            connection.execute(
                text("SELECT RELEASE_LOCK(:name)"),
                {"name": "nationalacts:migrate:" + name},
            )
    run("upgrade")


def test_reversible_change_preserves_existing_rows(database):
    run, engine, root = database
    run("upgrade")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO Activity (ActivityName) VALUES ('retain')"
        )
    (root / "migrations/versions/0002_example.py").write_text(
        """from alembic import op
revision = "0002_example"
down_revision = "0001_baseline"
branch_labels = depends_on = None
def upgrade():
    op.execute("CREATE TABLE MigrationExample (id INT PRIMARY KEY)")
def downgrade():
    op.execute("DROP TABLE MigrationExample")
""",
        encoding="utf-8",
    )
    run("upgrade")
    run("check")
    run("downgrade", "0001_baseline")
    run("verify-baseline")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT ActivityName FROM Activity")).scalar_one()
            == "retain"
        )
    run("upgrade")
    run("check")


def test_baseline_drop_is_refused(database):
    run, engine, _ = database
    run("upgrade")
    with pytest.raises(RuntimeError, match="delete all"):
        run("downgrade", "-1")
    run("check")
    with engine.connect() as connection:
        assert len(migrate.snapshot(connection)) == 45


def test_partial_ddl_failure_retains_previous_revision(database):
    run, engine, root = database
    run("upgrade")
    (root / "migrations/versions/0002_failure.py").write_text(
        """from alembic import op
revision = "0002_failure"
down_revision = "0001_baseline"
branch_labels = depends_on = None
def upgrade():
    op.execute("CREATE TABLE PartialChange (id INT)")
    raise RuntimeError("injected failure")
def downgrade():
    raise RuntimeError("unsafe")
""",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        run("upgrade")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0001_baseline"
        )
        assert connection.exec_driver_sql("SHOW TABLES LIKE 'PartialChange'").first()
    with pytest.raises(RuntimeError, match="not at"):
        run("check")
