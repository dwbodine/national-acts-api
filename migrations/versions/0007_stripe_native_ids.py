"""Retain TicketSocket native event and order IDs on Stripe payment intents."""

from alembic import op

revision = "0007_stripe_native_ids"
down_revision = "0006_admin_settlement_costs"
branch_labels = None
depends_on = None


def upgrade():
    """Add source IDs independently of nullable internal order mappings."""
    op.execute("""ALTER TABLE StripePaymentIntents
        ADD COLUMN NativeEventId INT NULL,
        ADD COLUMN NativeOrderId INT NULL""")


def downgrade():
    """Remove the native source ID columns."""
    op.execute("""ALTER TABLE StripePaymentIntents
        DROP COLUMN NativeEventId,
        DROP COLUMN NativeOrderId""")
