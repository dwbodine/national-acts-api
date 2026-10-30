"""Add a nullable Radar fee total to Stripe payment intents."""

from alembic import op

revision = "0009_stripe_radar_fee"
down_revision = "0008_stripe_nullable_fields"
branch_labels = None
depends_on = None


def upgrade():
    """Add Radar totals and populate intents with matching imported Radar fees."""
    op.execute("""ALTER TABLE StripePaymentIntents
        ADD COLUMN RadarFee DECIMAL(10,2) NULL DEFAULT NULL""")
    op.execute("""UPDATE StripePaymentIntents pi
        JOIN (
            SELECT IncurredBy, SUM(Amount + Tax) AS RadarFee
            FROM StripeFees
            WHERE IncurredByType = 'payment_intent'
                AND (LOWER(FeatureName) LIKE '%radar%'
                     OR LOWER(Product) = 'radar')
            GROUP BY IncurredBy
        ) fees ON fees.IncurredBy = pi.PaymentIntentId
        SET pi.RadarFee = fees.RadarFee""")


def downgrade():
    """Remove the Radar fee total."""
    op.execute("ALTER TABLE StripePaymentIntents DROP COLUMN RadarFee")
