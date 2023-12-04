from datetime import datetime
import traceback 
import sys 

from . import db
from common.ticket_socket_service import *
from common.models.national_acts import *
from common.models.ticket_socket import *

class MigrationTicket: 
    ticketType: str
    price: float

    def __init__(self, ticketSocketOrderId: int):
        self.ticketSocketOrderId = ticketSocketOrderId

class MigrationOrder:
    ticketsMigrated: list[MigrationTicket] = []

    def __init__(self, orderId: int, ticketsFound: int):
        self.orderId = orderId
        self.ticketsFound = ticketsFound

class MigrationEvent:
    ordersMigrated: list[MigrationOrder] = []

    def __init__(self, eventId: int, title: str, date: str):
        self.eventId = eventId
        self.title = title
        self.date = date

class MigrationData:
    eventsMigrated: list[MigrationEvent] = []

    def __init__(self, totalEvents: int, totalOrders: int, totalTickets: int):
        self.totalEvents = totalEvents
        self.totalOrders = totalOrders
        self.totalTickets = totalTickets

class MigrationService:
    def clearOutNewTables(self):
        success: bool = True
        errMsg: str = ''

        try:
            sql = "DELETE FROM TicketSocketOrderTickets"
            db.delete(sql)

            sql = "DELETE FROM TicketSocketOrders"
            db.delete(sql)

            sql = "DELETE FROM TicketSocketEvents"
            db.delete(sql)

            sql = "DELETE FROM ExternalEventsNew"
            db.delete(sql)

            sql = "DELETE FROM UserSeller"
            db.delete(sql)
        except Exception as error:
            errMsg = error
            success = False

        return "Success" if success else errMsg
        
    def findMissingSellers(self):
        sellerIds: list[int] = []
        sql = """SELECT Sellers.SellerId FROM Sellers 
                    WHERE Sellers.EventCategoryID <> 0 
                    AND NOT EXISTS 
                        (SELECT 1 FROM SellerEventCategory 
                            WHERE TicketSocketId=1 AND EventCategoryId=Sellers.EventCategoryID)"""
        rows = db.queryAll(sql)
        for row in rows:
            sellerIds.append(int(row["SellerId"]))

        sql = """SELECT Sellers.SellerId FROM Sellers 
                    WHERE Sellers.EventCategoryId_Europe <> 0 
                    AND NOT EXISTS 
                        (SELECT 1 FROM SellerEventCategory 
                            WHERE TicketSocketId=2 AND EventCategoryId=Sellers.EventCategoryId_Europe)"""
        rows = db.queryAll(sql)
        for row in rows:
            sellerIds.append(int(row["SellerId"]))
        
        return sellerIds if len(sellerIds) > 0 else "None"
    
    def migrateSellers(self):
        success: bool = True
        errMsg: str = ''

        try: 
            sql = """INSERT INTO UserSeller (UserId, SellerId)
                        SELECT Users.UserId, Sellers.SellerId 
                        FROM Users 
                        JOIN UserEventCategory ON UserEventCategory.UserId = Users.UserId
                        JOIN Sellers ON Sellers.EventCategoryID = UserEventCategory.EventCategoryId
                        WHERE Users.IsAdmin <> 1"""
            result = db.update(sql)
            success = (result > 0)
        except Exception as error:
            errMsg = error
            success = False

        return "Success" if success else errMsg 
    
    def migrateExternalEvents(self): 
        success: bool = True
        errMsg: str = ''

        try:
            sql = """INSERT INTO ExternalEventsNew (EventId, SellerId, Title, EventDate,  
                                Thumbnail, URL, Venue, Address, City, State, Zip, 
                                DisableLinkButton, DisableLinkReason,  ExternalVipLink, DisableVipLinkButton, 
                                DisableVipLinkReason, Created, LastUpdate, Country, IsActive)
                    SELECT e.EventId, s.SellerId, e.Title, DATE_FORMAT(Time, '%Y-%m-%d') AS EventDate, 
                            e.Thumbnail, e.URL, e.Venue, e.Address, e.City, e.State, e.Zip, 
                            e.DisableLinkButton, e.DisableLinkReason, e.ExternalVipLink, e.DisableVipLinkButton, 
                            e.DisableVipLinkReason, e.Created, e.LastUpdate, e.Country, e.IsActive
                    FROM ExternalEvents e
                    JOIN Sellers s ON s.EventCategoryID = e.EventCategoryID"""
            result = db.update(sql)
            success = (result > 0)
        except Exception as error:
            errMsg = error
            success = False

        return "Success" if success else errMsg 
    
    def migrateEventData(self):
        try:
            totalEvents: int = 0
            totalOrders: int = 0
            totalTickets: int = 0

            migratedEvents: list[MigrationEvent] = []

            # migrate USA VIP events
            sql = """SELECT Events.*, SellerEventCategory.SellerEventCategoryId 
                        FROM Events 
                        JOIN Sellers ON Sellers.EventCategoryId = Events.EventCategoryId
                        JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId AND SellerEventCategory.TicketSocketId = 1"""
            rows = db.queryAll(sql)

            for row in rows:
                eventId = int(row["EventID"])
                title = str(row["Title"])
                time = datetime.fromisoformat(str(row["Time"]))
                utcTime = int(time.timestamp() + (7 * 60 * 60))
                displayDate = str(row["DisplayDate"])
                if displayDate == None or displayDate == '':
                    displayDate = time.strftime("%m/%d/%Y")

                migrationEvent = MigrationEvent(eventId, title, displayDate)

                data = {
                    'eventId': eventId,
                    'sellerEventCategoryId': int(row["SellerEventCategoryId"]),
                    'title': title,
                    'eventDate': time.strftime('%Y-%m-%d'),
                    'utcTime': utcTime,
                    'displayDate': displayDate,
                    'thumbnail': str(row["Thumbnail"]), 
                    'url': str(row["URL"]),
                    'venue': str(row["Venue"]),
                    'address': str(row["Address"]),
                    'city': str(row["City"]),
                    'state': str(row["State"]),
                    'zip': str(row["Zip"]),
                    'country': str(row["Country"]),
                    'onSale': int(row["OnSale"]),
                    'isActive': int(row["IsActive"]),
                    'created': str(row["Created"]),
                    'lastUpdate': str(row["LastUpdate"])
                }

                insertSql = """INSERT INTO TicketSocketEvents (EventId, SellerEventCategoryId, Title, EventDate, UtcTime, DisplayDate, Thumbnail, 
                                    URL, Venue, Address, City, State, Zip, Country, OnSale, IsActive, Created, LastUpdate) VALUES
                            (%(eventId)s, %(sellerEventCategoryId)s, %(title)s, %(eventDate)s, %(utcTime)s, %(displayDate)s, %(thumbnail)s, 
                                %(url)s, %(venue)s, %(address)s, %(city)s, %(state)s, %(zip)s, %(country)s, %(onSale)s, %(isActive)s, %(created)s, %(lastUpdate)s)"""
                
                id = db.insert(insertSql, data)
                
                if id > 0:
                    totalEvents += 1
                    migrated = self.__migrateOrdersForEvent(id, eventId)
                    migrationEvent.ordersMigrated = migrated
                    totalOrders += len(migrationEvent.ordersMigrated)
                    for order in migrationEvent.ordersMigrated:
                        totalTickets += len(order.ticketsMigrated)


            # migrate Europe VIP events
            sql = """SELECT EventsEurope.*, SellerEventCategory.SellerEventCategoryId 
                        FROM EventsEurope 
                        JOIN Sellers ON Sellers.EventCategoryId_Europe = EventsEurope.EventCategoryID
                        JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId AND SellerEventCategory.TicketSocketId = 2"""
            rows = db.queryAll(sql)

            for row in rows:
                eventId = int(row["EventID"])
                time = datetime.fromisoformat(str(row["Time"]))
                utcTime = int(time.timestamp())
                displayDate = str(row["DisplayDate"])
                if displayDate == None or displayDate == '':
                    displayDate = time.strftime("%m/%d/%Y")

                migrationEvent = MigrationEvent(eventId, title, displayDate)

                data = {
                    'eventId': eventId,
                    'sellerEventCategoryId': int(row["SellerEventCategoryId"]),
                    'title': str(row["Title"]),
                    'eventDate': time.strftime('%Y-%m-%d'),
                    'utcTime': utcTime,
                    'displayDate': displayDate,
                    'thumbnail': str(row["Thumbnail"]), 
                    'url': str(row["URL"]),
                    'venue': str(row["Venue"]),
                    'address': str(row["Address"]),
                    'city': str(row["City"]),
                    'state': str(row["State"]),
                    'zip': str(row["Zip"]),
                    'country': str(row["Country"]),
                    'onSale': int(row["OnSale"]),
                    'isActive': int(row["IsActive"]),
                    'created': str(row["Created"]),
                    'lastUpdate': str(row["LastUpdate"])
                }

                insertSql = """INSERT INTO TicketSocketEvents (EventId, SellerEventCategoryId, Title, EventDate, UtcTime, DisplayDate, Thumbnail, 
                                    URL, Venue, Address, City, State, Zip, Country, OnSale, IsActive, Created, LastUpdate) VALUES
                            (%(eventId)s, %(sellerEventCategoryId)s, %(title)s, %(eventDate)s, %(utcTime)s, %(displayDate)s, %(thumbnail)s, 
                                %(url)s, %(venue)s, %(address)s, %(city)s, %(state)s, %(zip)s, %(country)s, %(onSale)s, %(isActive)s, %(created)s, %(lastUpdate)s)"""
                
                id = db.insert(insertSql, data)
                
                if id > 0:
                    totalEvents += 1
                    migrated = self.__migrateOrdersForEventEurope(id, eventId)
                    migrationEvent.ordersMigrated = migrated
                    totalOrders += len(migrationEvent.ordersMigrated)
                    for order in migrationEvent.ordersMigrated:
                        totalTickets += len(order.ticketsMigrated)
                    migratedEvents.append(migrationEvent)

            migrationData = MigrationData(totalEvents, totalOrders, totalTickets)
            migrationData.eventsMigrated = migratedEvents

            return migrationData
        except Exception as error:
            traceback.print_exception(*sys.exc_info()) 
            return error
    
    def __migrateOrdersForEvent(self, ticketSocketEventId: int, eventId: int):
        migratedOrders: list[MigrationOrder] = []
        sql = """SELECT SellerEventCategory.SellerEventCategoryId, VipOrders.*
                    FROM VipOrders 
                    JOIN Events ON Events.EventId = VipOrders.EventId
                    JOIN Sellers ON Sellers.EventCategoryId = Events.EventCategoryID
                    JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId AND SellerEventCategory.TicketSocketId = 1
                    WHERE Events.EventID=%(eventId)s"""
        
        data = {
            'eventId': eventId
        }

        rows = db.queryAll(sql, data)
        for row in rows:
            orderId = int(row["OrderId"])
            numTickets = int(row["NumTickets"])
            ticketTypeStr = str(row["TicketType"])
            purchaseDate = datetime.fromisoformat(str(row["PurchaseDate"]))
            revenue = float(row["Revenue"])

            shirtData = str(row["Shirts"]).split("/")
            shirts: list[str] = []
            for shirt in shirtData:
                shirts.append(str(shirt).strip())
            
            attendeeData = str(row["AttendeeNames"]).split("/")
            attendees: list[str] = []
            for attendee in attendeeData:
                attendees.append(str(attendee).strip())

            migrationOrder = MigrationOrder(orderId, numTickets)

            data = {
                'ticketSocketEventId': ticketSocketEventId,
                'eventId': eventId,
                'orderId': orderId,
                'numTickets': numTickets,
                'purchaseDate': purchaseDate.strftime("%Y-%m-%d"),
                'phone': str(row["Phone"]),
                'shirts': " / ".join(shirts),
                'attendeeNames': " / ".join(attendees),
                'userId': int(row["UserId"]),
                'purchaserLastName': str(row["PurchaserLastName"]),
                'purchaserFirstName': str(row["PurchaserFirstName"]),
                'email': str(row["Email"]),
                'revenue': revenue,
                'isActive': int(row["IsActive"]),
                'lastUpdate': str(row["LastUpdate"])
            }

            insertSql = """INSERT INTO TicketSocketOrders (TicketSocketEventId, EventId, OrderId, NumTickets, PurchaseDate, 
                            Phone, Shirts, AttendeeNames, UserId, PurchaserLastName, PurchaserFirstName, Email, 
                            Revenue, IsActive, LastUpdate) VALUES (%(ticketSocketEventId)s, %(eventId)s, %(orderId)s, %(numTickets)s, %(purchaseDate)s, 
                            %(phone)s, %(shirts)s, %(attendeeNames)s, %(userId)s, %(purchaserLastName)s, %(purchaserFirstName)s, %(email)s, 
                            %(revenue)s, %(isActive)s, %(lastUpdate)s)"""
            
            id = db.insert(insertSql, data)

            if id > 0:
                migrated = self.__migrateTicketsForOrder(id, ticketTypeStr, numTickets)
                migrationOrder.ticketsMigrated = migrated
                migratedOrders.append(migrationOrder)

        return migratedOrders


    def __migrateOrdersForEventEurope(self, ticketSocketEventId: int, eventId: int):
        migratedOrders: list[MigrationOrder] = []
        sql = """SELECT SellerEventCategory.SellerEventCategoryId, VipOrdersEurope.*
                    FROM VipOrdersEurope 
                    JOIN EventsEurope ON EventsEurope.EventId = VipOrdersEurope.EventId
                    JOIN Sellers ON Sellers.EventCategoryId_Europe = EventsEurope.EventCategoryID
                    JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId AND SellerEventCategory.TicketSocketId = 2
                    WHERE EventsEurope.EventID=%(eventId)s"""
        
        data = {
            'eventId': eventId
        }

        rows = db.queryAll(sql, data)
        for row in rows:
            orderId = int(row["OrderId"])
            numTickets = int(row["NumTickets"])
            ticketTypeStr = str(row["TicketType"])
            purchaseDate = datetime.fromisoformat(str(row["PurchaseDate"]))
            revenue = float(row["Revenue"])

            shirtData = str(row["Shirts"]).split("/")
            shirts: list[str] = []
            for shirt in shirtData:
                shirts.append(str(shirt).strip())
            
            attendeeData = str(row["AttendeeNames"]).split("/")
            attendees: list[str] = []
            for attendee in attendeeData:
                attendees.append(str(attendee).strip())

            migrationOrder = MigrationOrder(orderId, numTickets)

            data = {
                'ticketSocketEventId': ticketSocketEventId,
                'eventId': eventId,
                'orderId': orderId,
                'numTickets': numTickets,
                'purchaseDate': purchaseDate.strftime("%Y-%m-%d"),
                'phone': str(row["Phone"]),
                'shirts': " / ".join(shirts),
                'attendeeNames': " / ".join(attendees),
                'userId': int(row["UserId"]),
                'purchaserLastName': str(row["PurchaserLastName"]),
                'purchaserFirstName': str(row["PurchaserFirstName"]),
                'email': str(row["Email"]),
                'revenue': revenue,
                'isActive': int(row["IsActive"]),
                'lastUpdate': str(row["LastUpdate"])
            }

            insertSql = """INSERT INTO TicketSocketOrders (TicketSocketEventId, EventId, OrderId, NumTickets, PurchaseDate, 
                            Phone, Shirts, AttendeeNames, UserId, PurchaserLastName, PurchaserFirstName, Email, 
                            Revenue, IsActive, LastUpdate) VALUES (%(ticketSocketEventId)s, %(eventId)s, %(orderId)s, %(numTickets)s, %(purchaseDate)s, 
                            %(phone)s, %(shirts)s, %(attendeeNames)s, %(userId)s, %(purchaserLastName)s, %(purchaserFirstName)s, %(email)s, 
                            %(revenue)s, %(isActive)s, %(lastUpdate)s)"""
            
            id = db.insert(insertSql, data)

            if id > 0:
                migrated = self.__migrateTicketsForOrder(id, ticketTypeStr, numTickets)
                migrationOrder.ticketsMigrated = migrated
                migratedOrders.append(migrationOrder)

        return migratedOrders
        

    def __migrateTicketsForOrder(self, ticketSocketOrderId: int, ticketTypeStr: str, totalTickets: int):
        migratedTickets: list[MigrationTicket] = []

        rawTicketData = ticketTypeStr.split(';')
        for rawTicketStr in rawTicketData:
            tickets = self.__convertRawTicketStringToObjects(rawTicketStr, ticketSocketOrderId)
            migratedTickets += tickets

        if len(migratedTickets) != totalTickets:
            raise Exception("Received order # " + ticketSocketOrderId + " for " + totalTickets + " tickets but only found " + len(migratedTickets))
        
        insertSql = """INSERT INTO TicketSocketOrderTickets (TicketSocketOrderId, TicketType, Price) 
                            VALUES (%(ticketSocketOrderId)s, %(ticketType)s, %(price)s)"""

        for t in migratedTickets:
            data = {
                'ticketSocketOrderId': t.ticketSocketOrderId, 
                'ticketType': t.ticketType, 
                'price': t.price
            }
            db.insert(insertSql, data)

        return migratedTickets
        
    def __convertRawTicketStringToObjects(self, rawTicketStr: str, ticketSocketOrderId: int):
        tickets: list[MigrationTicket] = []

        rawTicketStr = rawTicketStr.strip()
        lastParen = rawTicketStr.rfind('(')
        lastAt = rawTicketStr.rfind('@')
        type = rawTicketStr[0:lastParen].strip()
        num = int(rawTicketStr[lastParen+1:lastAt].strip())
        price = rawTicketStr[lastAt+1:len(rawTicketStr)-1].strip().replace('$', '')
        for x in range(0, num):
            ticket = MigrationTicket(ticketSocketOrderId)
            ticket.ticketType = type
            ticket.price = float(price)
            tickets.append(ticket)
        return tickets
    
        
        
        

        