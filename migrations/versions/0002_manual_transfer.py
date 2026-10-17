"""Record the IsManualTransfer column already added manually in production."""

from alembic import op
from sqlalchemy import text

revision = "0002_manual_transfer"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE TicketSocketOrders ADD COLUMN IsManualTransfer TINYINT NOT NULL DEFAULT 0 AFTER IsComped"
    )


def downgrade():
    count = (
        op.get_bind()
        .execute(
            text("SELECT COUNT(*) FROM TicketSocketOrders WHERE IsManualTransfer <> 0")
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError(
            "Cannot drop IsManualTransfer while non-default values exist"
        )
    op.execute("ALTER TABLE TicketSocketOrders DROP COLUMN IsManualTransfer")
