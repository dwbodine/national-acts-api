# pylint: disable=invalid-name
# pylint: disable=no-member
"""
Stripe upgrade
"""

from alembic import op

revision = "7e3584499b4c"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade the database schema for Stripe integration.
    """

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

    # add new Orders table
    op.execute("""
        CREATE TABLE TicketPartnerOrders (
                    TicketPartnerOrderId INT NOT NULL AUTO_INCREMENT,
                    TicketPartnerEventId INT NOT NULL,
                    PartnerOrderId INT NULL,
                    LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    
                    PRIMARY KEY (TicketPartnerOrderId),
                    
                    CONSTRAINT FK_TicketPartnerOrders_TicketPartnerEvent
                        FOREIGN KEY (TicketPartnerEventId)
                        REFERENCES TicketPartnerEvents (TicketPartnerEventId)
                        ON DELETE NO ACTION
                        ON UPDATE NO ACTION, 
                        
                    UNIQUE KEY UQ_TicketPartnerOrders_PartnerEvent
                        (TicketPartnerEventId, PartnerOrderId)

                ) ENGINE=InnoDB
                    DEFAULT CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;
    """)

    op.execute("""
        INSERT INTO TicketPartnerOrders (TicketPartnerEventId, PartnerOrderId, LastUpdated)
            SELECT tpe.TicketPartnerEventId, tso.Id, tso.LastUpdate
                FROM TicketPartnerEvents tpe
                JOIN TicketSocketOrders tso
                    ON tpe.PartnerEventId = tso.TicketSocketEventId
                WHERE tpe.TicketPartnerId = 2
                    AND tpe.PartnerEventId IS NOT NULL
                ORDER BY tso.PurchaseDate, tso.LastUpdate
    """)

    # add new StripeTransactions table
    op.execute("""
        CREATE TABLE StripeTransactions (
                    StripeTransactionId VARCHAR(100) NOT NULL,
                    TicketPartnerOrderId INT NOT NULL,
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
                    
                    CONSTRAINT FK_StripeTransactions_TicketPartnerOrder
                        FOREIGN KEY (TicketPartnerOrderId)
                        REFERENCES TicketPartnerOrders (TicketPartnerOrderId)
                        ON DELETE NO ACTION
                        ON UPDATE NO ACTION,
                                        
                    UNIQUE KEY UQ_StripeTransactions_StripeTransactionId
                        (StripeTransactionId)

                ) ENGINE=InnoDB
                    DEFAULT CHARACTER SET utf8mb4
                    COLLATE utf8mb4_unicode_ci;
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            ADD COLUMN TicketPartnerEventId INT NULL,
            ADD COLUMN TicketPartnerOrderId INT NULL
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            ADD CONSTRAINT IX_DailyOrderData_PurchaseDate_EventId_OrderId
                UNIQUE (PurchaseDate, TicketPartnerEventId, TicketPartnerOrderId);
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            ADD CONSTRAINT FK_DailyOrderData_TicketPartnerEvent
            FOREIGN KEY (TicketPartnerEventId)
            REFERENCES TicketPartnerEvents (TicketPartnerEventId)
            ON DELETE NO ACTION
            ON UPDATE NO ACTION;
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            ADD CONSTRAINT FK_DailyOrderData_TicketPartnerOrder
            FOREIGN KEY (TicketPartnerOrderId)
            REFERENCES TicketPartnerOrders (TicketPartnerOrderId)
            ON DELETE NO ACTION
            ON UPDATE NO ACTION;
    """)

    op.execute("""
        UPDATE DailyOrderData dod
            JOIN TicketPartnerEvents tpe
                ON tpe.PartnerEventId = dod.TicketSocketEventId
                AND tpe.TicketPartnerId = 2
            SET dod.TicketPartnerEventId = tpe.TicketPartnerEventId            
    """)

    op.execute("""
        UPDATE DailyOrderData dod
            JOIN TicketPartnerOrders tpo
                ON tpo.PartnerOrderId = dod.TicketSocketOrderId
                SET dod.TicketPartnerOrderId = tpo.TicketPartnerOrderId            
    """)

    # op.execute("""
    #     ALTER TABLE DailyOrderData
    #        DROP FOREIGN KEY FK_DailyOrderData_TicketSocketEvent
    # """)

    # op.execute("""
    #     ALTER TABLE DailyOrderData
    #         DROP INDEX IX_DailyOrderData_PurchaseDate_EventId
    # """)

    # op.execute("""
    #    ALTER TABLE DailyOrderData
    #        DROP COLUMN TicketSocketEventId,
    #        DROP COLUMN TicketSocketOrderId
    # """)


def downgrade():
    """
    Downgrade the database schema for Stripe integration.
    """

    # op.execute("""
    #     ALTER TABLE DailyOrderData
    #         ADD COLUMN TicketSocketEventId INT NULL,
    #         ADD COLUMN TicketSocketOrderId INT NULL
    # """)

    # op.execute("""
    #     ALTER TABLE DailyOrderData
    #         ADD CONSTRAINT IX_DailyOrderData_PurchaseDate_EventId
    #         UNIQUE (PurchaseDate, TicketSocketEventId, TicketSocketOrderId);
    # """)

    # op.execute("""
    #    ALTER TABLE DailyOrderData
    #        ADD CONSTRAINT FK_DailyOrderData_TicketSocketEvent
    #        FOREIGN KEY (TicketSocketEventId)
    #        REFERENCES TicketSocketEvents (Id)
    #        ON DELETE NO ACTION
    #        ON UPDATE NO ACTION;
    # """)

    op.execute("""
        UPDATE DailyOrderData dod
            JOIN TicketPartnerEvents tpe
                ON tpe.TicketPartnerEventId = dod.TicketPartnerEventId
                AND tpe.TicketPartnerId = 2
            SET dod.TicketSocketEventId = tpe.PartnerEventId            
    """)

    op.execute("""
        UPDATE DailyOrderData dod
            JOIN TicketPartnerOrders tpo
                ON tpo.TicketPartnerOrderId = dod.TicketPartnerOrderId
                SET dod.TicketSocketOrderId = tpo.PartnerOrderId            
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            DROP FOREIGN KEY FK_DailyOrderData_TicketPartnerEvent
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            DROP FOREIGN KEY FK_DailyOrderData_TicketPartnerOrder
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            DROP INDEX IX_DailyOrderData_PurchaseDate_EventId_OrderId
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            DROP COLUMN TicketPartnerEventId,
            DROP COLUMN TicketPartnerOrderId
    """)

    op.execute("""
        DROP TABLE StripeTransactions
    """)

    op.execute("""
        DROP TABLE TicketPartnerOrders
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
