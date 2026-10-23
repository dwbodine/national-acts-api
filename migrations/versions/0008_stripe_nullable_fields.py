"""Allow missing customer and event details on Stripe payment intents."""

from alembic import op
from sqlalchemy import text

revision = "0008_stripe_nullable_fields"
down_revision = "0007_stripe_native_ids"
branch_labels = None
depends_on = None


def upgrade():
    """Retain existing types while allowing nulls and setting requested defaults."""
    op.execute("""ALTER TABLE StripePaymentIntents
        MODIFY COLUMN EventName VARCHAR(100) NULL DEFAULT NULL,
        MODIFY COLUMN CustomerName VARCHAR(100) NULL DEFAULT NULL,
        MODIFY COLUMN CustomerEmail VARCHAR(100) NULL DEFAULT NULL,
        MODIFY COLUMN CustomerPhone TEXT NULL DEFAULT NULL,
        MODIFY COLUMN PaymentMethod VARCHAR(32) NULL DEFAULT 'card',
        MODIFY COLUMN Insurance DECIMAL(18,6) NULL DEFAULT 0""")


def downgrade():
    """Refuse to restore required fields if doing so would discard null values."""
    count = op.get_bind().execute(text("""SELECT COUNT(*) FROM StripePaymentIntents
        WHERE EventName IS NULL OR CustomerName IS NULL OR CustomerEmail IS NULL
            OR CustomerPhone IS NULL OR PaymentMethod IS NULL""")).scalar_one()
    if count:
        raise RuntimeError("Cannot restore NOT NULL fields while null values exist")
    op.execute("""ALTER TABLE StripePaymentIntents
        MODIFY COLUMN EventName VARCHAR(100) NOT NULL,
        MODIFY COLUMN CustomerName VARCHAR(100) NOT NULL,
        MODIFY COLUMN CustomerEmail VARCHAR(100) NOT NULL,
        MODIFY COLUMN CustomerPhone TEXT NOT NULL,
        MODIFY COLUMN PaymentMethod VARCHAR(32) NOT NULL DEFAULT 'card',
        MODIFY COLUMN Insurance DECIMAL(18,6) NULL DEFAULT NULL""")
