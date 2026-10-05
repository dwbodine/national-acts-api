"""Locked migrations with explicit adoption of an existing production schema."""

import argparse
import json
import os
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "0001_baseline"


def configuration():
    return Config(str(ROOT / "alembic.ini"))


def engine():
    load_dotenv(ROOT / ".env", override=False)

    # Migration credentials can differ from the runtime application credentials.
    def setting(name):
        value = os.getenv("MIGRATION_" + name) or os.getenv(name)
        if not value:
            raise RuntimeError(f"Missing {name} (or MIGRATION_{name})")
        return value

    return create_engine(
        URL.create(
            "mariadb+mariadbconnector",
            username=setting("DB_USER"),
            password=setting("DB_PASSWORD"),
            host=setting("DB_HOST"),
            port=int(os.getenv("MIGRATION_DB_PORT", os.getenv("DB_PORT", "3306"))),
            database=setting("DB_DB"),
        ),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def normalized_ddl(ddl):
    return re.sub(r"\s+AUTO_INCREMENT=\d+", "", ddl).strip()


def snapshot(connection):
    database = connection.execute(text("SELECT DATABASE()")).scalar_one()
    objects = connection.execute(text("SHOW FULL TABLES")).all()
    result = {}
    for name, kind in objects:
        if name == "alembic_version":
            continue
        if kind != "BASE TABLE":
            raise RuntimeError(f"Uncaptured schema object: {kind} {name}")
        quoted = "`" + name.replace("`", "``") + "`"
        result[name] = normalized_ddl(
            connection.exec_driver_sql(f"SHOW CREATE TABLE {quoted}").one()[1]
        )
    for catalog in ("TRIGGERS", "ROUTINES", "EVENTS"):
        field = {
            "TRIGGERS": "TRIGGER_SCHEMA",
            "ROUTINES": "ROUTINE_SCHEMA",
            "EVENTS": "EVENT_SCHEMA",
        }[catalog]
        count = connection.execute(
            text(
                f"SELECT COUNT(*) FROM information_schema.{catalog} WHERE {field}=:db"
            ),
            {"db": database},
        ).scalar_one()
        if count:
            raise RuntimeError(
                f"Uncaptured schema objects in {catalog}; baseline adoption refused"
            )
    return dict(sorted(result.items()))


def verify_baseline(connection):
    expected = json.loads(
        (ROOT / "migrations/baseline-schema.json").read_text(encoding="utf-8")
    )
    actual = snapshot(connection)
    differences = sorted(
        name
        for name in expected.keys() | actual.keys()
        if expected.get(name) != actual.get(name)
    )
    if differences:
        raise RuntimeError("Baseline mismatch in tables: " + ", ".join(differences))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Local dotenv file; exported variables take precedence",
    )
    parser.add_argument(
        "action",
        choices=[
            "upgrade",
            "downgrade",
            "current",
            "check",
            "adopt-baseline",
            "verify-baseline",
            "snapshot",
            "revision",
        ],
    )
    parser.add_argument("target", nargs="?")
    args = parser.parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            parser.error("Environment file does not exist")
        load_dotenv(args.env_file, override=False)
    config = configuration()
    scripts = ScriptDirectory.from_config(config)
    if len(scripts.get_heads()) != 1:
        raise RuntimeError("Exactly one migration head is required")
    if args.action == "revision":
        if not args.target:
            parser.error("revision requires a message")
        command.revision(config, message=args.target)
        return
    if args.action == "downgrade" and (
        not args.target or args.target in ("base", "head")
    ):
        parser.error("downgrade requires an explicit safe revision")
    with engine().connect() as connection:
        # Connection-scoped lock survives DDL implicit commits.
        database = connection.execute(text("SELECT DATABASE()")).scalar_one()
        lock = "nationalacts:migrate:" + database
        acquired = connection.execute(
            text("SELECT GET_LOCK(:name, 0)"), {"name": lock}
        ).scalar_one()
        connection.commit()
        if acquired != 1:
            raise RuntimeError("Another migration runner holds the database lock")
        config.attributes["connection"] = connection
        try:
            current = MigrationContext.configure(connection).get_current_heads()
            connection.commit()
            if args.action in ("verify-baseline", "adopt-baseline"):
                if current and current != (BASELINE,):
                    raise RuntimeError("Database is already beyond the baseline")
                verify_baseline(connection)
                connection.commit()
                if args.action == "adopt-baseline":
                    command.stamp(config, BASELINE)
            elif args.action == "snapshot":
                print(json.dumps(snapshot(connection), indent=2))
            elif args.action == "current":
                print(",".join(current) or "unversioned")
            elif args.action == "check":
                if current != (scripts.get_current_head(),):
                    raise RuntimeError(
                        "Database is not at this release's migration head"
                    )
                print("Database is at release head")
            elif args.action == "upgrade":
                if not current and snapshot(connection):
                    raise RuntimeError(
                        "Existing database is unversioned; verify and adopt-baseline first"
                    )
                connection.commit()
                command.upgrade(config, args.target or "head")
            elif args.action == "downgrade":
                command.downgrade(config, args.target)
            connection.commit()
        finally:
            connection.rollback()
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock})
            connection.commit()


if __name__ == "__main__":
    main()
