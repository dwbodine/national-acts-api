"""Alembic is invoked by tools.migrate, which owns the connection and lock."""

from alembic import context

if context.is_offline_mode():
    raise RuntimeError("Use python -m tools.migrate; offline mode is not configured")
connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use python -m tools.migrate to obtain the migration lock")
context.configure(connection=connection, target_metadata=None, transactional_ddl=False)
with context.begin_transaction():
    context.run_migrations()
