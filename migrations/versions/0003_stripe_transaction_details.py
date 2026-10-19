"""Add status, payment method, and account to Stripe transactions."""

from alembic import op

revision = "0003_stripe_transaction_details"
down_revision = "7e3584499b4c"
branch_labels = None
depends_on = None


def upgrade():
    """Extend existing transactions while supporting the previous API image."""
    # Previously imported transactions were all succeeded. Unknown historical
    # payment methods/accounts remain empty until populated from Stripe.
    op.execute(
        """ALTER TABLE StripeTransactions
        ADD COLUMN Status VARCHAR(32) NOT NULL DEFAULT 'succeeded',
        ADD COLUMN PaymentMethod VARCHAR(32) NOT NULL DEFAULT 'card',
        ADD COLUMN StripeAccount VARCHAR(64) NOT NULL DEFAULT ''"""
    )


def downgrade():
    """Remove the added transaction details."""
    op.execute(
        """ALTER TABLE StripeTransactions
        DROP COLUMN StripeAccount,
        DROP COLUMN PaymentMethod,
        DROP COLUMN Status"""
    )
