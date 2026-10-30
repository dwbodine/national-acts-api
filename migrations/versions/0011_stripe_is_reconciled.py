"""Mark payment intents with known total, processing, and Radar amounts."""

from alembic import op

revision = "0011_stripe_is_reconciled"
down_revision = "0010_stripe_fee_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    """Add the reconciliation flag and backfill existing complete amounts."""
    op.execute("""ALTER TABLE StripePaymentIntents
        ADD COLUMN IsReconciled TINYINT NOT NULL DEFAULT 0""")
    op.execute("""UPDATE StripePaymentIntents SET IsReconciled=1
        WHERE Total IS NOT NULL AND ProcessingFee IS NOT NULL
            AND RadarFee IS NOT NULL""")


def downgrade():
    """Remove the reconciliation flag."""
    op.execute("ALTER TABLE StripePaymentIntents DROP COLUMN IsReconciled")
