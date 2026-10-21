"""Extend Stripe transactions and add refund and itemized fee storage."""

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
    op.execute(
        """CREATE TABLE StripeRefunds (
            StripeRefundId VARCHAR(100) NOT NULL PRIMARY KEY,
            PaymentIntentId VARCHAR(100) NOT NULL,
            Amount DECIMAL(18,2) NOT NULL,
            Currency VARCHAR(3) NOT NULL,
            Status VARCHAR(32) NOT NULL,
            Reason VARCHAR(100) NULL,
            CreatedAt DATETIME NOT NULL,
            OrderId VARCHAR(100) NOT NULL,
            CustomerName TEXT NOT NULL,
            CustomerEmail TEXT NOT NULL,
            CustomerPhone TEXT NOT NULL,
            SourceUrl TEXT NOT NULL,
            EventId TEXT NOT NULL,
            EventName TEXT NOT NULL,
            OriginalAmount DECIMAL(18,2) NOT NULL,
            ExchangeRate DECIMAL(18,8) NOT NULL,
            LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY IX_StripeRefunds_PaymentIntentId (PaymentIntentId)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
    )
    op.execute(
        """CREATE TABLE StripeFees (
            StripeFeeId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            FeeRowKey CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            Suite VARCHAR(100) NULL,
            Product VARCHAR(100) NULL,
            FeatureName VARCHAR(255) NULL,
            BalanceTransactionCreated DATETIME NULL,
            BalanceTransactionId VARCHAR(100) NULL,
            BalanceTransactionDescription TEXT NULL,
            FeeDescription TEXT NULL,
            IncurredBy VARCHAR(100) NULL,
            IncurredByType VARCHAR(64) NULL,
            Amount DECIMAL(38,18) NOT NULL,
            Tax DECIMAL(38,18) NOT NULL DEFAULT 0,
            Currency VARCHAR(3) NOT NULL,
            InvoiceNumber VARCHAR(100) NULL,
            CreditNoteNumber VARCHAR(100) NULL,
            IncurredAt DATETIME NULL,
            FeatureDescription TEXT NULL,
            FeeTransactionId VARCHAR(100) NULL,
            FeeTransactionCreated DATETIME NULL,
            PricingTier VARCHAR(255) NULL,
            FeeCategory VARCHAR(100) NULL,
            SettledAt DATETIME NULL,
            SettledVia VARCHAR(32) NULL,
            LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY UQ_StripeFees_FeeRowKey (FeeRowKey),
            KEY IX_StripeFees_IncurredBy (IncurredBy, IncurredByType),
            KEY IX_StripeFees_BalanceTransactionId (BalanceTransactionId),
            KEY IX_StripeFees_FeeTransactionId (FeeTransactionId),
            KEY IX_StripeFees_IncurredAt (IncurredAt)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
    )


def downgrade():
    """Remove fee/refund storage and the added transaction details."""
    op.execute("DROP TABLE StripeFees")
    op.execute("DROP TABLE StripeRefunds")
    op.execute(
        """ALTER TABLE StripeTransactions
        DROP COLUMN StripeAccount,
        DROP COLUMN PaymentMethod,
        DROP COLUMN Status"""
    )
