"""Preserve historical Stripe phone metadata longer than twenty characters."""

from alembic import op
from sqlalchemy import text

revision = "0005_stripe_customer_phone"
down_revision = "0004_stripe_payment_intents"
branch_labels = None
depends_on = None


def upgrade():
    """Match refund storage and retain complete phone metadata without truncation."""
    op.execute(
        "ALTER TABLE StripePaymentIntents MODIFY COLUMN CustomerPhone TEXT NOT NULL"
    )


def downgrade():
    """Refuse to shrink the column when doing so would lose phone metadata."""
    count = (
        op.get_bind()
        .execute(
            text(
                "SELECT COUNT(*) FROM StripePaymentIntents WHERE CHAR_LENGTH(CustomerPhone) > 20"
            )
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError(
            "Cannot shrink CustomerPhone while values exceed 20 characters"
        )
    op.execute(
        "ALTER TABLE StripePaymentIntents MODIFY COLUMN CustomerPhone VARCHAR(20) NOT NULL"
    )
