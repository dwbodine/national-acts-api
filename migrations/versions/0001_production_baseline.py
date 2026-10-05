"""Schema-only baseline from production export dated 2026-10-05."""

import json
from pathlib import Path
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    statements = json.loads(
        (Path(__file__).parents[1] / "baseline.json").read_text(encoding="utf-8")
    )
    for statement in statements:
        op.execute(statement)


def downgrade():
    raise RuntimeError(
        "Baseline downgrade would delete all application tables; refused"
    )
