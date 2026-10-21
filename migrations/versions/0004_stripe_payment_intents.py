"""Rename Stripe payment storage and introduce an integer primary key."""

from alembic import op

revision = "0004_stripe_payment_intents"
down_revision = "0003_stripe_transaction_details"
branch_labels = None
depends_on = None


def _refresh_order_details(table, payment_column):
    """Keep existing view output names compatible with application consumers."""
    op.execute(f"""CREATE OR REPLACE SQL SECURITY INVOKER VIEW OrderDetails AS
        SELECT tpo.TicketPartnerOrderId AS TicketPartnerOrderId,
            tpo.TicketPartnerEventId AS TicketPartnerEventId,
            tpe.TicketPartnerId AS TicketPartnerId,
            tpe.EventId AS EventId,
            tpo.PartnerOrderId AS PartnerOrderId,
            tpo.LastUpdated AS OrderLastUpdated,
            tso.Id AS TicketSocketOrderId,
            tso.TicketSocketEventId AS TicketSocketEventId,
            tso.EventId AS TicketSocketNativeEventId,
            tso.OrderId AS TicketSocketNativeOrderId,
            tso.PurchaseDate AS PurchaseDate,
            tso.PurchaseTimestamp AS PurchaseTimestamp,
            tso.PurchaseUnixTimestamp AS PurchaseUnixTimestamp,
            tso.Phone AS Phone,
            tso.PhoneFormatted AS PhoneFormatted,
            tso.UserId AS UserId,
            tso.PurchaserLastName AS PurchaserLastName,
            tso.PurchaserFirstName AS PurchaserFirstName,
            tso.PurchaserCity AS PurchaserCity,
            tso.PurchaserState AS PurchaserState,
            tso.PurchaserZip AS PurchaserZip,
            tso.PurchaserCountry AS PurchaserCountry,
            tso.PurchaserIpAddress AS PurchaserIpAddress,
            tso.Email AS Email,
            tso.IsActive AS IsActive,
            tso.IsDeleted AS IsDeleted,
            tso.IsComped AS IsComped,
            tso.IsManualTransfer AS IsManualTransfer,
            tso.IsSenderUpdated AS IsSenderUpdated,
            tso.Notes AS Notes,
            tso.LastUpdate AS TicketSocketLastUpdate,
            st.{payment_column} AS StripeTransactionId,
            st.EventName AS StripeEventName,
            st.Description AS StripeDescription,
            st.DateReceived AS StripeDateReceived,
            st.Total AS StripeTotal,
            st.Insurance AS StripeInsurance,
            st.ProcessingFee AS StripeProcessingFee,
            st.CustomerName AS StripeCustomerName,
            st.CustomerEmail AS StripeCustomerEmail,
            st.CustomerPhone AS StripeCustomerPhone,
            st.Currency AS StripeCurrency,
            st.SourceUrl AS StripeSourceUrl,
            st.ExchangeRate AS StripeExchangeRate,
            st.LastUpdated AS StripeLastUpdated
        FROM TicketPartnerOrders tpo
        JOIN TicketPartnerEvents tpe
            ON tpe.TicketPartnerEventId=tpo.TicketPartnerEventId
        LEFT JOIN TicketSocketOrders tso
            ON tpe.TicketPartnerId=2 AND tso.Id=tpo.PartnerOrderId
            AND tso.TicketSocketEventId=tpe.PartnerEventId
        LEFT JOIN {table} st ON st.TicketPartnerOrderId=tpo.TicketPartnerOrderId
    """)


def upgrade():
    """Preserve payment IDs as unique keys and assign integer row identities."""
    op.execute("""ALTER TABLE StripeTransactions
        DROP PRIMARY KEY,
        CHANGE COLUMN StripeTransactionId PaymentIntentId VARCHAR(100) NOT NULL,
        ADD COLUMN StripePaymentIntentId INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
        RENAME INDEX UQ_StripeTransactions_StripeTransactionId TO UQ_StripePaymentIntents_PaymentIntentId,
        RENAME TO StripePaymentIntents""")
    _refresh_order_details("StripePaymentIntents", "PaymentIntentId")


def downgrade():
    """Restore the original table and string primary key without losing payments."""
    op.execute("""ALTER TABLE StripePaymentIntents
        DROP COLUMN StripePaymentIntentId,
        CHANGE COLUMN PaymentIntentId StripeTransactionId VARCHAR(100) NOT NULL,
        ADD PRIMARY KEY (StripeTransactionId),
        RENAME INDEX UQ_StripePaymentIntents_PaymentIntentId TO UQ_StripeTransactions_StripeTransactionId,
        RENAME TO StripeTransactions""")
    _refresh_order_details("StripeTransactions", "StripeTransactionId")
