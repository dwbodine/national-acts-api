"""Separate customer checkout fees, Stripe processing, and unverified Connect fees."""

from alembic import op
from sqlalchemy import text

revision = "0006_admin_settlement_costs"
down_revision = "0005_stripe_customer_phone"
branch_labels = None
depends_on = None


def upgrade():
    """Preserve source fees and stop presenting every application fee as insurance."""
    op.execute("""ALTER TABLE TicketSocketOrders
        ADD COLUMN CustomerProcessingFee DECIMAL(18,6) NULL""")
    op.execute("""ALTER TABLE StripePaymentIntents
        ADD COLUMN ApplicationFee DECIMAL(18,6) NOT NULL DEFAULT 0,
        ADD COLUMN InsuranceVerified TINYINT NOT NULL DEFAULT 0,
        ADD COLUMN ProcessingFeeCurrency VARCHAR(3) NULL,
        MODIFY COLUMN Insurance DECIMAL(18,6) NULL""")
    # The old importer stored application_fee_amount in Insurance. Preserve it,
    # but do not guess the application identity or the balance transaction currency.
    # ProcessingFee remains unverified until an explicit Stripe refresh; subtracting
    # the old Insurance here could mix presentment and settlement currencies.
    op.execute("""UPDATE StripePaymentIntents SET
        ApplicationFee=COALESCE(Insurance,0),
        Insurance=NULL""")


def downgrade():
    """Restore the previous importer representation before removing the new columns."""
    incompatible = op.get_bind().execute(text("""SELECT COUNT(*) FROM StripePaymentIntents
        WHERE ApplicationFee <> 0 AND ProcessingFeeCurrency IS NOT NULL
            AND ProcessingFeeCurrency <> Currency""")).scalar_one()
    if incompatible:
        raise RuntimeError("Cannot restore combined fees across different currencies")
    op.execute("""UPDATE StripePaymentIntents SET
        ProcessingFee=CASE WHEN ProcessingFeeCurrency=Currency
            THEN ProcessingFee+ApplicationFee ELSE ProcessingFee END,
        Insurance=ApplicationFee""")
    op.execute("""ALTER TABLE StripePaymentIntents
        DROP COLUMN ApplicationFee, DROP COLUMN InsuranceVerified,
        DROP COLUMN ProcessingFeeCurrency,
        MODIFY COLUMN Insurance DECIMAL(10,2) NOT NULL""")
    op.execute("ALTER TABLE TicketSocketOrders DROP COLUMN CustomerProcessingFee")
