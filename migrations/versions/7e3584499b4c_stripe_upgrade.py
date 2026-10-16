# pylint: disable=invalid-name
# pylint: disable=no-member
"""
Stripe upgrade
"""

from alembic import op

revision = "7e3584499b4c"
down_revision = "0002_manual_transfer"
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

    op.execute("""
        CREATE TABLE `TicketPartnerOrderTickets` (
            `TicketPartnerTicketId` INT(11) NOT NULL AUTO_INCREMENT,
            `TicketPartnerOrderId` INT(11) NOT NULL,
            `PartnerTicketId` INT(11) DEFAULT NULL,
            `LastUpdated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (`TicketPartnerTicketId`),
            UNIQUE KEY `UQ_TicketPartnerOrderTickets_TicketPartnerOrderTicketId`
                (`TicketPartnerOrderId`, `PartnerTicketId`),
            KEY `IX_TicketPartnerOrderTickets_TicketPartnerOrderId`
                (`TicketPartnerOrderId`),

            CONSTRAINT `FK_TicketPartnerOrderTickets_TicketPartnerOrders`
                FOREIGN KEY (`TicketPartnerOrderId`)
                REFERENCES `TicketPartnerOrders` (`TicketPartnerOrderId`)
                ON DELETE NO ACTION ON UPDATE NO ACTION

        ) ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci;
    """)

    op.execute("""
        INSERT INTO TicketPartnerOrderTickets (TicketPartnerOrderId, PartnerTicketId, LastUpdated)
            SELECT tpo.TicketPartnerOrderId, tsot.Id, tsot.LastUpdate
                FROM TicketPartnerOrders tpo
                JOIN TicketSocketOrderTickets tsot
                    ON tsot.TicketSocketOrderId = tpo.PartnerOrderId
                JOIN TicketPartnerEvents tpe
                    ON tpe.TicketPartnerEventId = tpo.TicketPartnerEventId                
                WHERE tpe.TicketPartnerId = 2
                    AND tpe.PartnerEventId IS NOT NULL
                ORDER BY tsot.Id
    """)

    # add new StripeTransactions table
    op.execute("""
        CREATE TABLE StripeTransactions (
                    StripeTransactionId VARCHAR(100) NOT NULL,
                    TicketPartnerOrderId INT NULL,
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
                AND tpo.TicketPartnerEventId = dod.TicketPartnerEventId
                SET dod.TicketPartnerOrderId = tpo.TicketPartnerOrderId            
    """)

    op.execute("""
        ALTER TABLE EventNotes
            DROP INDEX IX_EventNote_EventId
    """)

    op.execute("""
        ALTER TABLE EventNotes
            DROP INDEX FK_EventNote_ExternalEventId
    """)

    op.execute("""
        ALTER TABLE EventNotes
            RENAME COLUMN ExternalEventId TO EventId
    """)

    op.execute("""
        ALTER TABLE EventNotes
            ADD INDEX IX_EventNote_EventId
                (EventId)
    """)

    op.execute("""
        ALTER TABLE EventNotes
            ADD CONSTRAINT FK_EventNote_EventId
                FOREIGN KEY (EventId)
                REFERENCES Events (EventId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION
    """)

    op.execute("""
        ALTER TABLE FanMoments
            DROP FOREIGN KEY FK_FanMoment_ExternalEventId
    """)

    op.execute("""
        ALTER TABLE FanMoments
            DROP INDEX IX_FanMoment_ExternalEventId
    """)

    op.execute("""
        ALTER TABLE FanMoments
            RENAME COLUMN ExternalEventId TO EventId
    """)

    op.execute("""
        ALTER TABLE FanMoments
            ADD INDEX IX_FanMoment_EventId
                (EventId)
    """)

    op.execute("""
        ALTER TABLE FanMoments
            ADD CONSTRAINT FK_FanMoments_EventId
                FOREIGN KEY (EventId)
                REFERENCES Events (EventId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION
    """)

    op.execute("""
        ALTER TABLE TourEvent
            DROP FOREIGN KEY FK_TourEvent_ExternalEventId
    """)

    op.execute("""
        ALTER TABLE TourEvent
            DROP INDEX IX_TourEvent_Compound
    """)

    op.execute("""
        ALTER TABLE TourEvent
            RENAME COLUMN ExternalEventId TO EventId
    """)

    op.execute("""
            ALTER TABLE TourEvent
            ADD CONSTRAINT FK_TourEvent_EventId
                FOREIGN KEY (EventId)
                REFERENCES Events (EventId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION;
    """)

    op.execute("""
        ALTER TABLE TourEvent
            ADD INDEX IX_TourEvent_Compound
                (TourEventId, TourId, EventId)
    """)

    unmapped_daily_rows = op.get_bind().exec_driver_sql("""
        SELECT COUNT(*) FROM DailyOrderData
        WHERE TicketPartnerEventId IS NULL
            OR (TicketSocketOrderId IS NOT NULL AND TicketPartnerOrderId IS NULL)
    """).scalar_one()
    if unmapped_daily_rows:
        raise RuntimeError("DailyOrderData contains rows without partner mappings; legacy columns were not dropped")

    op.execute("""
        ALTER TABLE DailyOrderData
            DROP FOREIGN KEY FK_DailyOrderData_TicketSocketEvent,
            DROP INDEX IX_DailyOrderData_PurchaseDate_EventId,
            DROP COLUMN TicketSocketEventId,
            DROP COLUMN TicketSocketOrderId
    """)

    # Preserve the existing event projection using the new partner mapping.
    op.execute("""
        CREATE SQL SECURITY INVOKER VIEW EventDetails AS
        SELECT Sellers.SellerId AS SellerId,
               Sellers.Name AS SellerName,
               Sellers.SellerTypeId AS SellerType,
               Events.EventId AS EventId,
               TicketSocketEvents.Id AS TicketSocketEventId,
               COALESCE(Events.EventDate, TicketSocketEvents.EventDate) AS EventDate,
               TicketSocketEvents.SellerEventCategoryId AS SellerEventCategoryId,
               COALESCE(SellerEventCategory.IsVisibleOnSite, 1) AS IsVisibleOnSite,
               COALESCE(SellerEventCategory.IsVisibleOnPortal, 1) AS IsVisibleOnPortal,
               COALESCE(SellerEventCategory.SellerRatePercent, 0.0) AS SellerRatePercent,
               TicketSocketEvents.IsVip AS IsVip,
               Events.EventTime AS EventTime,
               Events.MeetAndGreetTime AS MeetAndGreetTime,
               Events.DoorsOpenTime AS DoorsOpenTime,
               COALESCE(Events.Title, TicketSocketEvents.Title) AS Title,
               COALESCE(Venues.Venue, TicketSocketEvents.Venue) AS Venue,
               COALESCE(Venues.Address, TicketSocketEvents.Address) AS Address,
               COALESCE(Venues.City, TicketSocketEvents.City) AS City,
               COALESCE(Venues.State, TicketSocketEvents.State) AS State,
               COALESCE(Venues.Zip, TicketSocketEvents.Zip) AS Zip,
               COALESCE(Country.CountryName, TicketSocketEvents.Country) AS Country,
               Venues.TimeZone AS TimeZone,
               Country.CountryId AS CountryId,
               Country.CountryCode AS CountryCode,
               COALESCE(Events.EmailSentToVips, 0) AS EmailSentToVips,
               COALESCE(Events.TextSentToVips, 0) AS TextSentToVips,
               COALESCE(Events.ListSentToBand, 0) AS ListSentToBand,
               Events.ListSentTime AS ListSentTime,
               COALESCE(Events.ListSentNumVips, 0) AS ListSentNumVips,
               Events.CheckInLocation AS CheckInLocation,
               Events.CheckInNotes AS CheckInNotes,
               Events.AnnounceDate AS AnnounceDate,
               Events.IsAddedToBandsInTown AS IsAddedToBandsInTown,
               Events.URL AS ExternalUrl,
               Events.Thumbnail AS ExternalThumbnail,
               Events.VenueId AS VenueId,
               Events.DisableLinkButton AS DisableLinkButton,
               Events.DisableLinkReason AS DisableLinkReason,
               Events.ExternalVipLink AS ExternalVipLink,
               Events.DisableVipLinkButton AS DisableVipLinkButton,
               Events.DisableVipLinkReason AS DisableVipLinkReason,
               Events.IsActive AS IsActive,
               Events.IsDeleted AS IsDeleted,
               Events.IsHidden AS IsHidden,
               Events.IsCancelled AS IsCancelled,
               Events.CancelledDate AS CancelledDate,
               Events.ExcludeFromDashboard AS ExcludeFromDashboard,
               Events.EventNote AS EventNote,
               TicketSocketEvents.EventId AS TicketSocketNativeEventId,
               TicketSocketEvents.URL AS URL,
               TicketSocketEvents.Thumbnail AS Thumbnail,
               Tour.AnnounceDate AS TourAnnounceDate,
               COALESCE(Tour.IsActive, 0) AS IsTourActive,
               COALESCE(TicketSocketEvents.IsSoldOut, 0) AS IsSoldOut,
               TicketPartnerEvents.TicketPartnerId AS TicketPartnerId,
               TicketPartnerEvents.TicketPartnerEventId AS TicketPartnerEventId,
               TicketSocketEvents.LastUpdate AS LastUpdate
        FROM Events
        JOIN Sellers ON Sellers.SellerId = Events.SellerId
        JOIN TicketPartnerEvents
            ON TicketPartnerEvents.EventId = Events.EventId
        LEFT JOIN TicketSocketEvents
            ON TicketSocketEvents.Id = TicketPartnerEvents.PartnerEventId
            AND TicketPartnerEvents.TicketPartnerId = 2
        LEFT JOIN SellerEventCategory
            ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
        LEFT JOIN Venues ON Venues.VenueID = Events.VenueId
        LEFT JOIN Country ON Country.CountryId = Venues.CountryId
        LEFT JOIN TourEvent ON TourEvent.EventId = Events.EventId
        LEFT JOIN Tour ON Tour.TourId = TourEvent.TourId
    """)

    op.execute("""
        CREATE SQL SECURITY INVOKER VIEW OrderDetails AS
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
                st.StripeTransactionId AS StripeTransactionId,
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
            ON tpe.TicketPartnerEventId = tpo.TicketPartnerEventId
        LEFT JOIN TicketSocketOrders tso
            ON tpe.TicketPartnerId = 2
            AND tso.Id = tpo.PartnerOrderId
            AND tso.TicketSocketEventId = tpe.PartnerEventId
        LEFT JOIN StripeTransactions st
            ON st.TicketPartnerOrderId = tpo.TicketPartnerOrderId
    """)


    op.execute("""
        CREATE SQL SECURITY INVOKER VIEW OrderOverview AS
SELECT DISTINCT
    od.TicketSocketOrderId AS Id,
    od.TicketSocketNativeOrderId AS OrderId,
    od.TicketSocketNativeEventId AS EventId,
    od.TicketPartnerOrderId, od.TicketPartnerEventId, od.TicketPartnerId,
    od.TicketSocketEventId, od.PurchaseDate, od.PurchaseTimestamp,
    od.PurchaseUnixTimestamp, od.UserId, od.Phone, od.Email,
    od.PurchaserLastName, od.PurchaserFirstName, od.PurchaserCity,
    od.PurchaserState, od.PurchaserZip, od.PurchaserCountry,
    od.PurchaserIpAddress, od.IsActive, od.IsDeleted, od.IsComped,
    od.IsManualTransfer, od.Notes, od.TicketSocketLastUpdate AS LastUpdate,
    ed.SellerEventCategoryId, ed.ExcludeFromDashboard,
    ed.Title AS EventTitle, ed.EventDate, ed.SellerName, ed.SellerId,
    ed.Venue, ed.Address AS EventAddress, ed.City AS EventCity,
    ed.State AS EventState, ed.Zip AS EventZip, ed.Country AS EventCountry,
    COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate,
    ExchangeRates.Symbol, ExchangeRates.Multiplier,
    UPPER(ExchangeRates.ServiceTokenId) AS CurrencyAbbrev
FROM OrderDetails od
JOIN EventDetails ed ON ed.TicketPartnerEventId = od.TicketPartnerEventId
JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = ed.SellerEventCategoryId
JOIN TicketSocket ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId
JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
LEFT JOIN ExchangeRateHistory ON ExchangeRateHistory.ExchangeRateId = ExchangeRates.ExchangeRateId
    AND ExchangeRateHistory.MidnightDate = od.PurchaseDate
    """)


    op.execute("""
        CREATE TABLE PartnerTicketTypes (
            PartnerTicketTypeId INT NOT NULL AUTO_INCREMENT,
            TicketPartnerEventId INT NOT NULL,
            ProviderTicketTypeId INT NULL,
            LastUpdated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (PartnerTicketTypeId),
            UNIQUE KEY UQ_PartnerTicketTypes_Event_Type
                (TicketPartnerEventId, ProviderTicketTypeId),
            CONSTRAINT FK_PartnerTicketTypes_TicketPartnerEvent
                FOREIGN KEY (TicketPartnerEventId)
                REFERENCES TicketPartnerEvents (TicketPartnerEventId)
                ON DELETE NO ACTION ON UPDATE NO ACTION
        ) ENGINE=InnoDB
            DEFAULT CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
    """)

    op.execute("""
        INSERT INTO PartnerTicketTypes
            (TicketPartnerEventId, ProviderTicketTypeId, LastUpdated)
        SELECT tpe.TicketPartnerEventId, tst.TicketSocketTicketTypeId, tst.LastUpdate
        FROM TicketPartnerEvents tpe
        JOIN TicketSocketTicketTypes tst
            ON tst.TicketSocketEventId = tpe.PartnerEventId
        WHERE tpe.TicketPartnerId = 2
        ORDER BY tpe.TicketPartnerEventId, tst.TicketTypeOrder, tst.TicketSocketTicketTypeId
    """)

    op.execute("""
        CREATE SQL SECURITY INVOKER VIEW TicketTypeDetails AS
        SELECT ptt.PartnerTicketTypeId AS PartnerTicketTypeId,
               ptt.TicketPartnerEventId AS TicketPartnerEventId,
               tpe.TicketPartnerId AS TicketPartnerId,
               tpe.EventId AS EventId,
               ptt.ProviderTicketTypeId AS ProviderTicketTypeId,
               ptt.LastUpdated AS TicketTypeLastUpdated,
               tse.Id AS TicketSocketEventId,
               tse.EventId AS TicketSocketNativeEventId,
               tst.TicketSocketTicketTypeId AS TicketSocketTicketTypeId,
               tst.TicketTypeName AS TicketTypeName,
               tst.TotalAvailable AS TotalAvailable,
               tst.IsActive AS IsActive,
               tst.TicketTypeOrder AS TicketTypeOrder,
               tst.LastUpdate AS TicketSocketLastUpdate
        FROM PartnerTicketTypes ptt
        JOIN TicketPartnerEvents tpe
            ON tpe.TicketPartnerEventId = ptt.TicketPartnerEventId
        LEFT JOIN TicketSocketEvents tse
            ON tpe.TicketPartnerId = 2
            AND tse.Id = tpe.PartnerEventId
        LEFT JOIN TicketSocketTicketTypes tst
            ON tst.TicketSocketEventId = tse.Id
            AND tst.TicketSocketTicketTypeId = ptt.ProviderTicketTypeId
    """)

    op.execute("""
        CREATE SQL SECURITY INVOKER VIEW TicketDetails AS
        SELECT tpot.TicketPartnerTicketId AS TicketPartnerTicketId,
               tpot.TicketPartnerOrderId AS TicketPartnerOrderId,
               tpo.TicketPartnerEventId AS TicketPartnerEventId,
               tpe.TicketPartnerId AS TicketPartnerId,
               tpe.EventId AS EventId,
               tpot.PartnerTicketId AS PartnerTicketId,
               tpo.PartnerOrderId AS PartnerOrderId,
               tpot.LastUpdated AS TicketLastUpdated,
               tso.Id AS TicketSocketOrderId,
               tso.TicketSocketEventId AS TicketSocketEventId,
               tso.EventId AS TicketSocketNativeEventId,
               tso.OrderId AS TicketSocketNativeOrderId,
               tso.IsActive AS OrderIsActive,
               tso.IsDeleted AS OrderIsDeleted,
               tso.IsComped AS OrderIsComped,
               tsot.Id AS TicketSocketOrderTicketId,
               tsot.TicketId AS TicketSocketNativeTicketId,
               tsot.TicketSocketTicketTypeId AS TicketSocketTicketTypeId,
               tst.PartnerTicketTypeId AS PartnerTicketTypeId,
               tsot.TicketType AS TicketType,
               COALESCE(tst.TicketTypeOrder, 1) AS TicketTypeOrder,
               tsot.Price AS Price,
               tsot.ServiceFee AS ServiceFee,
               tsot.AttendeeFirstName AS AttendeeFirstName,
               tsot.AttendeeLastName AS AttendeeLastName,
               tsot.AttendeePhone AS AttendeePhone,
               tsot.AttendeeEmail AS AttendeeEmail,
               tsot.ShirtSize AS ShirtSize,
               tsot.IsActive AS IsActive,
               tsot.IsCheckedIn AS IsCheckedIn,
               tsot.CheckedInDate AS CheckedInDate,
               tsot.IsRefunded AS IsRefunded,
               tsot.RefundDate AS RefundDate,
               tsot.IsChargedBack AS IsChargedBack,
               tsot.ChargebackDate AS ChargebackDate,
               tsot.IsServiceFeeRefunded AS IsServiceFeeRefunded,
               tsot.BarCode AS BarCode,
               tsot.AvailableScans AS AvailableScans,
               tsot.PurchaseLocation AS PurchaseLocation,
               tsot.ScannedTimestamp AS ScannedTimestamp,
               tsot.LastUpdate AS TicketSocketLastUpdate
        FROM TicketPartnerOrderTickets tpot
        JOIN TicketPartnerOrders tpo
            ON tpo.TicketPartnerOrderId = tpot.TicketPartnerOrderId
        JOIN TicketPartnerEvents tpe
            ON tpe.TicketPartnerEventId = tpo.TicketPartnerEventId
        LEFT JOIN TicketSocketOrders tso
            ON tpe.TicketPartnerId = 2
            AND tso.Id = tpo.PartnerOrderId
            AND tso.TicketSocketEventId = tpe.PartnerEventId
        LEFT JOIN TicketSocketOrderTickets tsot
            ON tsot.Id = tpot.PartnerTicketId
            AND tsot.TicketSocketOrderId = tso.Id
        LEFT JOIN TicketTypeDetails tst
            ON tst.TicketPartnerEventId = tpo.TicketPartnerEventId
            AND tst.ProviderTicketTypeId = tsot.TicketSocketTicketTypeId
            AND tst.TicketPartnerId = 2
            AND tst.TicketSocketTicketTypeId IS NOT NULL
    """)


def downgrade():
    """
    Downgrade the database schema for Stripe integration.
    """

    op.execute("DROP VIEW TicketDetails")
    op.execute("DROP VIEW TicketTypeDetails")
    op.execute("DROP TABLE PartnerTicketTypes")
    op.execute("DROP VIEW OrderOverview")
    op.execute("DROP VIEW OrderDetails")

    # Remove the view before dropping mappings or renaming its source tables.
    op.execute("DROP VIEW EventDetails")

    # Undo dependent-table changes while the parent is still named Events.
    op.execute("""
        ALTER TABLE TourEvent
            DROP FOREIGN KEY FK_TourEvent_EventId,
            DROP INDEX IX_TourEvent_Compound,
            RENAME COLUMN EventId TO ExternalEventId,
            ADD UNIQUE INDEX IX_TourEvent_Compound
                (TourEventId, TourId, ExternalEventId) USING BTREE,
            ADD CONSTRAINT FK_TourEvent_ExternalEventId
                FOREIGN KEY (ExternalEventId)
                REFERENCES Events (EventId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION
    """)

    op.execute("""
        ALTER TABLE FanMoments
            DROP FOREIGN KEY FK_FanMoments_EventId,
            DROP INDEX IX_FanMoment_EventId,
            RENAME COLUMN EventId TO ExternalEventId,
            ADD UNIQUE INDEX IX_FanMoment_ExternalEventId (ExternalEventId),
            ADD CONSTRAINT FK_FanMoment_ExternalEventId
                FOREIGN KEY (ExternalEventId)
                REFERENCES Events (EventId)
                ON DELETE NO ACTION
                ON UPDATE NO ACTION
    """)

    op.execute("""
        ALTER TABLE EventNotes
            DROP FOREIGN KEY FK_EventNote_EventId,
            DROP INDEX IX_EventNote_EventId,
            RENAME COLUMN EventId TO ExternalEventId,
            ADD INDEX IX_EventNote_EventId
                (ExternalEventId, EventNoteId, NoteTimestamp) USING BTREE,
            ADD INDEX FK_EventNote_ExternalEventId (ExternalEventId) USING BTREE
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            ADD COLUMN TicketSocketEventId INT NULL AFTER PurchaseDate,
            ADD COLUMN TicketSocketOrderId INT NULL AFTER TicketSocketEventId
    """)

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
                AND tpo.TicketPartnerEventId = dod.TicketPartnerEventId
                SET dod.TicketSocketOrderId = tpo.PartnerOrderId            
    """)

    op.execute("""
        ALTER TABLE DailyOrderData
            MODIFY COLUMN TicketSocketEventId INT NOT NULL,
            ADD CONSTRAINT IX_DailyOrderData_PurchaseDate_EventId
                UNIQUE (PurchaseDate, TicketSocketEventId, TicketSocketOrderId),
            ADD CONSTRAINT FK_DailyOrderData_TicketSocketEvent
                FOREIGN KEY (TicketSocketEventId)
                REFERENCES TicketSocketEvents (Id)
                ON DELETE NO ACTION ON UPDATE NO ACTION
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
        DROP TABLE TicketPartnerOrderTickets
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
