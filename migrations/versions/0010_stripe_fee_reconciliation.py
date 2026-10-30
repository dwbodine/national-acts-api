"""Preserve fee attribution, resolved payment links, and report import history."""

from alembic import op

revision = "0010_stripe_fee_reconciliation"
down_revision = "0009_stripe_radar_fee"
branch_labels = None
depends_on = None


def upgrade():
    """Add resolved links independently of Stripe's original attribution."""
    op.execute("""ALTER TABLE StripeFees
        ADD COLUMN PaymentIntentId VARCHAR(100) NULL,
        ADD COLUMN StripeAccount VARCHAR(64) NULL,
        ADD KEY IX_StripeFees_PaymentIntentId (PaymentIntentId, IncurredByType)""")
    op.execute("""UPDATE StripeFees SET PaymentIntentId=IncurredBy
        WHERE IncurredByType='payment_intent'""")
    op.execute("""CREATE TABLE StripeFeeReportImports (
        ReportId VARCHAR(100) NOT NULL PRIMARY KEY,
        StripeAccount VARCHAR(64) NOT NULL,
        IntervalStart DATETIME NOT NULL,
        IntervalEnd DATETIME NOT NULL,
        Status VARCHAR(32) NOT NULL,
        RowsRead INT NOT NULL DEFAULT 0,
        RowsImported INT NOT NULL DEFAULT 0,
        RowsSkipped INT NOT NULL DEFAULT 0,
        RowsUnresolved INT NOT NULL DEFAULT 0,
        ImportedAt DATETIME NULL,
        Error TEXT NULL,
        LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY IX_StripeFeeReportImports_Range (StripeAccount, IntervalStart, IntervalEnd)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")


def downgrade():
    """Remove report history and derived attribution."""
    op.execute("DROP TABLE StripeFeeReportImports")
    op.execute("""ALTER TABLE StripeFees
        DROP KEY IX_StripeFees_PaymentIntentId,
        DROP COLUMN PaymentIntentId, DROP COLUMN StripeAccount""")
