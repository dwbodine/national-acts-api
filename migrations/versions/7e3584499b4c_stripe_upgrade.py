"""Stripe upgrade"""

from alembic import op
import sqlalchemy as sa

revision = "7e3584499b4c"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    # rename old unused Orders table
    op.execute("""
        RENAME TABLE Orders TO PrintedTicketOrders
    """)

    # rename old ExternalEventVenues table to Venues and update
    op.execute("""
        RENAME TABLE ExternalEventVenues TO Venues
    """)

    op.execute("""
        ALTER TABLE Venues
            DROP FOREIGN KEY FK_ExternalEventVenue_Country,
            ADD CONSTRAINT FK_Venue_Country
                FOREIGN KEY (CountryId)
                REFERENCES Country (CountryId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION;
    """)

    op.execute("""
        ALTER TABLE Venues
            RENAME INDEX FK_ExternalEventVenue_Country TO IX_Venue_Country
    """)

    op.execute("""
        ALTER TABLE Venues
            RENAME INDEX VenueIndex TO IX_Venue_Venue
    """)

    # rename main event table to Events and update
    op.execute("""
        RENAME TABLE ExternalEvents TO Events
    """)

    op.execute("""
        ALTER TABLE Events
            DROP FOREIGN KEY FK_ExternalEvents_SellerId,
            ADD CONSTRAINT FK_Events_SellerId
                FOREIGN KEY (SellerId)
                REFERENCES Sellers (SellerId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION;
    """)

    op.execute("""
        ALTER TABLE Events
            DROP FOREIGN KEY FK_ExternalEvents_TicketSocketEvents_Id,
            ADD CONSTRAINT FK_Events_TicketSocketEvents_Id
                FOREIGN KEY (TicketSocketEventId)
                REFERENCES TicketSocketEvents (Id)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION;
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME INDEX IX_ExternalEvents_SellerId TO IX_Events_SellerId
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME INDEX IX_ExternalEvents_Compound TO IX_Events_Compound
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME INDEX IX_ExternalEventsNew_Search TO IX_Events_Search
    """)

    op.execute("""
        ALTER TABLE Events
            DROP INDEX IX_ExternalEvents_SellerId_EventDateTime_TicketSocketEventId,
            ADD UNIQUE INDEX IX_Events_EventId_SellerId_EventDateTime
                (SellerId, EventDate, EventTime);
    """)

    op.execute("""
        ALTER TABLE Events
            DROP INDEX IX_ExternalEvents_VenueId
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME COLUMN ExternalEventVenueId TO VenueId
    """)

    op.execute("""
        ALTER TABLE Events
            ADD INDEX IX_Events_VenueId
                (VenueId)
    """)

    # add new TicketPartners table
    op.execute("""
        CREATE TABLE TicketPartners (
            TicketPartnerId INT NOT NULL PRIMARY KEY,
            Name VARCHAR(100) NOT NULL,
            LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
            DEFAULT CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci;
    """)

    op.execute("""
        INSERT INTO TicketPartners (TicketPartnerId, Name)
        VALUES
            (1, 'National Acts'),
            (2, 'TicketSocket')
    """)

    # add new TicketPartnerEvents table
    op.execute("""
        CREATE TABLE TicketPartnerEvents (
                    TicketPartnerEventId INT NOT NULL AUTO_INCREMENT,
                    TicketPartnerId INT NOT NULL,
                    EventId INT NOT NULL,
                    PartnerEventId INT NULL,
                    LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (TicketPartnerEventId),
                    
                    CONSTRAINT FK_TicketPartnerEvents_Event
                        FOREIGN KEY (EventId)
                        REFERENCES Events (EventId)
                        ON DELETE NO ACTION
                        ON UPDATE NO ACTION, 
                        
                    CONSTRAINT FK_TicketPartnerEvents_TicketPartner
                        FOREIGN KEY (TicketPartnerId)
                        REFERENCES TicketPartners (TicketPartnerId)
                        ON DELETE NO ACTION
                        ON UPDATE NO ACTION,

                    UNIQUE KEY UQ_TicketPartner_PartnerEvent
                        (TicketPartnerId, EventId, PartnerEventId)

                ) ENGINE=InnoDB
                    DEFAULT CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;
    """)

    op.execute("""
        INSERT INTO TicketPartnerEvents (TicketPartnerId, EventId, PartnerEventId, LastUpdated)
            SELECT CASE WHEN TicketSocketEventId IS NULL THEN 1 ELSE 2 END, EventId, TicketSocketEventId, LastUpdate
                FROM Events 
                ORDER BY EventDate, LastUpdate
    """)

    op.execute("""
        ALTER TABLE Events
            DROP FOREIGN KEY FK_Events_TicketSocketEvents_Id
    """)

    op.execute("""
        ALTER TABLE Events
            DROP COLUMN TicketSocketEventId
    """)

    # add new StripeTransactions table
    op.execute("""
        CREATE TABLE StripeTransactions (
                    StripeTransactionId VARCHAR(100) NOT NULL,
                    EventName VARCHAR(100) NOT NULL,
                    Description VARCHAR(255) NOT NULL,
                    DateReceived DATETIME NOT NULL,
                    Total DECIMAL(10, 2) NOT NULL,
                    Insurance DECIMAL(10, 2) NOT NULL,
                    ProcessingFee DECIMAL(10, 2) NOT NULL,
                    CustomerName VARCHAR(100) NOT NULL,
                    CustomerEmail VARCHAR(100) NOT NULL,
                    CustomerPhone VARCHAR(20) NOT NULL,
                    Currency VARCHAR(3) NOT NULL,
                    SourceUrl VARCHAR(64) NOT NULL,
                    ExchangeRate DECIMAL(10, 6) NOT NULL,
                    LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (StripeTransactionId),
                                        
                    UNIQUE KEY UQ_StripeTransactions_StripeTransactionId
                        (StripeTransactionId)

                ) ENGINE=InnoDB
                    DEFAULT CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;
    """)

    # create Tranaction order join table
    op.execute("""
        CREATE TABLE StripeTransactionOrder (
                    StripeTransactionOrderId INT NOT NULL AUTO_INCREMENT,
                    StripeTransactionId VARCHAR(100) NOT NULL,
                    OrderId INT NOT NULL,
                    EventId INT NOT NULL,
                    LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (StripeTransactionOrderId)
                ) ENGINE=InnoDB
                    DEFAULT CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;
    
                    
        """)


def downgrade():
    # Replace this refusal only with a reviewed, data-preserving downgrade.

    op.execute("""
        DROP TABLE StripeTransactionOrder
    """)

    op.execute("""
        DROP TABLE StripeTransactions
    """)

    op.execute("""
        ALTER TABLE Events
            ADD COLUMN TicketSocketEventId INT NULL
    """)

    op.execute("""
        UPDATE Events e
            LEFT JOIN TicketPartnerEvents tpe
                ON tpe.EventId = e.EventId
            AND tpe.TicketPartnerId = 2
            SET e.TicketSocketEventId = tpe.PartnerEventId
    """)

    op.execute("""
        DROP TABLE TicketPartnerEvents
    """)

    op.execute("""
        DROP TABLE TicketPartners
    """)

    op.execute("""
        ALTER TABLE Events
            DROP INDEX IX_Events_VenueId
    """)

    op.execute("""
        ALTER TABLE Events
        RENAME COLUMN VenueId TO ExternalEventVenueId
    """)

    op.execute("""
        ALTER TABLE Events
            ADD INDEX IX_ExternalEvents_VenueId
                (ExternalEventVenueId)
    """)

    op.execute("""
        ALTER TABLE Events
            DROP INDEX IX_Events_EventId_SellerId_EventDateTime,
            ADD UNIQUE INDEX IX_ExternalEvents_SellerId_EventDateTime_TicketSocketEventId
                (SellerId, EventDate, EventTime, TicketSocketEventId)
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME INDEX IX_Events_Search TO IX_ExternalEventsNew_Search
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME INDEX IX_Events_Compound TO IX_ExternalEvents_Compound
    """)

    op.execute("""
        ALTER TABLE Events
            RENAME INDEX IX_Events_SellerId TO IX_ExternalEvents_SellerId
    """)

    op.execute("""
        ALTER TABLE Events
            ADD CONSTRAINT FK_ExternalEvents_TicketSocketEvents_Id
            FOREIGN KEY (TicketSocketEventId)
            REFERENCES TicketSocketEvents (Id)
            ON DELETE NO ACTION
            ON UPDATE NO ACTION;
    """)

    op.execute("""
        ALTER TABLE Events
            DROP FOREIGN KEY FK_Events_SellerId,
            ADD CONSTRAINT FK_ExternalEvents_SellerId
                FOREIGN KEY (SellerId)
                REFERENCES Sellers (SellerId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION;
    """)

    op.execute("""
        RENAME TABLE Events TO ExternalEvents
    """)

    op.execute("""
        ALTER TABLE Venues
            RENAME INDEX IX_Venue_Country TO FK_ExternalEventVenue_Country
    """)

    op.execute("""
        ALTER TABLE Venues
            RENAME INDEX IX_Venue_Venue TO VenueIndex
    """)

    op.execute("""
        ALTER TABLE Venues
            DROP FOREIGN KEY FK_Venue_Country,
            ADD CONSTRAINT FK_ExternalEventVenue_Country
                FOREIGN KEY (CountryId)
                REFERENCES Country (CountryId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION
    """)

    op.execute("""
        RENAME TABLE Venues TO ExternalEventVenues
    """)

    op.execute("""
        RENAME TABLE PrintedTicketOrders TO Orders
    """)
