import os
import json
import time
from datetime import datetime
import operator

from . import utility
from . import db
from common.ticket_socket_service import *
from common.models.national_acts import *
from common.models.ticket_socket import *

class EventService:
    def getEventsAndOrders(self, getOrders: bool = False, sellerId: int = None, start: int = None, end: int = None, showInactive: bool = False, searchTerm: str = None):
        events: list[VipEvent] = []
        
        sellerEventCategoryIds: list[int] = []
        if sellerId != None:
            seller = Seller(sellerId)
            sellerEventCategoryIds = seller.getSellerEventCategoryIds()
            # prevent against returning every event in the database
            if len(sellerEventCategoryIds) == 0: 
                return []

        if getOrders == False and searchTerm != None:
            searchTerm = searchTerm.replace("'", "''")
            searchTerm = searchTerm.replace('"', '')
            searchTerm = searchTerm.replace('=', '')
        else:
            searchTerm = None

        sql = """SELECT TicketSocketEvents.*, 
                    ExternalEventsNew.EventId AS ExternalEventId, 
                    ExternalEventsNew.SellerId AS ExternalSellerId, 
                    ExternalEventsNew.Title AS ExternalTitle, 
                    ExternalEventsNew.Thumbnail AS ExternalThumbnail, 
                    ExternalEventsNew.URL AS ExternalUrl, 
                    ExternalEventsNew.Venue AS ExternalVenue, 
                    ExternalEventsNew.Address AS ExternalAddress, 
                    ExternalEventsNew.City AS ExternalCity, 
                    ExternalEventsNew.State AS ExternalState, 
                    ExternalEventsNew.Zip AS ExternalZip, 
                    ExternalEventsNew.Country AS ExternalCountry, 
                    ExternalEventsNew.DisableLinkButton, 
                    ExternalEventsNew.DisableLinkReason, 
                    ExternalEventsNew.ExternalVipLink, 
                    ExternalEventsNew.DisableVipLinkButton, 
                    ExternalEventsNew.DisableVipLinkReason
                 FROM TicketSocketEvents 
                 JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId 
                 JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId
            LEFT JOIN ExternalEventsNew ON ExternalEventsNew.SellerId = Sellers.SellerId AND TicketSocketEvents.EventDate = ExternalEventsNew.EventDate """
        
        if showInactive != True:
            sql += " AND ExternalEventsNew.IsActive = 1"

        sql += " WHERE "
        data = {}

        whereClause: list[str] = []        
        if showInactive != True:
            whereClause.append("TicketSocketEvents.IsActive = 1")
        if searchTerm != None and len(searchTerm) > 0:
            whereClause.append("""MATCH (TicketSocketEvents.Title, 
                                         TicketSocketEvents.Venue, 
                                         TicketSocketEvents.Address, 
                                         TicketSocketEvents.City, 
                                         TicketSocketEvents.State, 
                                         TicketSocketEvents.Country) AGAINST (%(searchTerm)s IN BOOLEAN MODE)""")
            data["searchTerm"] = '*' + searchTerm + '*'
        if len(sellerEventCategoryIds) > 0:
            sellerEventCategoryIdStr = db.convertListToParameters(sellerEventCategoryIds, data, 'sellerEventCategoryId')
            whereClause.append("TicketSocketEvents.SellerEventCategoryId IN " + sellerEventCategoryIdStr)
        
        if start != None and end != None:
            whereClause.append("TicketSocketEvents.EventDate BETWEEEN %(startDate)s AND %(endDate)s")
            data["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
            data["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
        elif end != None:
            whereClause.append("TicketSocketEvents.EventDate BETWEEEN %(startDate)s AND %(endDate)s")
            data["startDate"] = datetime.now().strftime('%Y-%m-%d')
            data["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
        elif start != None:
            whereClause.append("TicketSocketEvents.EventDate >= %(startDate)s")
            data["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
        elif getOrders == False or sellerId == None:
            whereClause.append("TicketSocketEvents.EventDate >= %(startDate)s")
            data["startDate"] = datetime.now().strftime('%Y-%m-%d')

        if len(whereClause) > 0:
            sql += " AND ".join(whereClause)

        sql += " ORDER BY TicketSocketEvents.EventDate ASC, TicketSocketEvents.Title ASC"       

        sql = sql.replace('\n', '') 

        eventRows = db.queryAll(sql, data)
        for row in eventRows:
            eventId = int(row["EventId"])
            ticketSocketEventId = int(row["Id"])
            vipEvent = VipEvent(eventId, str(row["Title"]))
            vipEvent.ticketSocketEventId = ticketSocketEventId
            vipEvent.sellerEventCategoryId = int(row["SellerEventCategoryId"])
            vipEvent.eventDate = str(row["EventDate"])
            vipEvent.utcTime = int(row["UtcTime"])
            vipEvent.displayDate = str(row["DisplayDate"])
            vipEvent.thumbnail = str(row["Thumbnail"])
            vipEvent.ticketSocketUrl = str(row["URL"])
            venue = TicketSocketVenue(str(row["Venue"]), str(row["Address"]), '', str(row["City"]), str(row["State"]), str(row["Zip"]), str(row["Country"]), '')
            vipEvent.venue = venue
            vipEvent.onSale = True if int(row["OnSale"]) == 1 else False
            vipEvent.isActive = True if int(row["IsActive"]) == 1 else False
            vipEvent.isVip = True if int(row["IsVip"]) == 1 else False
            if row["ExternalEventId"] != None and row["ExternalEventId"] != '':
                vipEvent.externalEventId = int(row["ExternalEventId"])
                vipEvent.externalSellerId = int(row["ExternalSellerId"])
                vipEvent.externalTitle = str(row["ExternalTitle"])
                vipEvent.externalThumbnail = str(row["ExternalThumbnail"])
                vipEvent.externalUrl = str(row["ExternalUrl"])
                externalVenue = TicketSocketVenue(str(row["ExternalVenue"]), str(row["ExternalAddress"]), '', str(row["ExternalCity"]), str(row["ExternalState"]), str(row["ExternalZip"]), str(row["ExternalCountry"]), '')
                vipEvent.externalVenue = externalVenue
                vipEvent.disableLinkButton = str(row["DisableLinkButton"])
                vipEvent.disableLinkReason = str(row["DisableLinkReason"])
                vipEvent.externalVipLink = str(row["ExternalVipLink"])
                vipEvent.disableVipLinkButton = str(row["DisableVipLinkButton"])
                vipEvent.disableVipLinkReason = str(row["DisableVipLinkReason"])

            if getOrders == True:
                orders = self.__getOrdersFromEventId(ticketSocketEventId)
                vipEvent.orders = orders
            
            vipEvent.getTotals()
            
            events.append(vipEvent)            

        # get external events without matching TicketSocketEvents
        externalSql = """SELECT * FROM ExternalEventsNew WHERE """
        externalData = {}
        
        externalWhereClause: list[str] = []        
        if showInactive != True:
            externalWhereClause.append("IsActive = 1")
        if searchTerm != None and len(searchTerm) > 0:
            externalWhereClause.append("""MATCH (Title, Venue, Address, City, State, Country) AGAINST (%(searchTerm)s IN BOOLEAN MODE)""")
            externalData["searchTerm"] = '*' + searchTerm + '*'
        if sellerId != None:
            externalWhereClause.append("SellerId = %(sellerId)s")
            externalData["sellerId"] = sellerId
        if start != None and end != None:
            externalWhereClause.append("EventDate BETWEEEN %(startDate)s AND %(endDate)s")
            externalData["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
            externalData["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
        elif end != None:
            externalWhereClause.append("EventDate BETWEEEN %(startDate)s AND %(endDate)s")
            externalData["startDate"] = datetime.now().strftime('%Y-%m-%d')
            externalData["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
        elif start != None:
            externalWhereClause.append("EventDate >= %(startDate)s")
            externalData["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
        else:
            externalWhereClause.append("EventDate >= %(startDate)s")
            externalData["startDate"] = datetime.now().strftime('%Y-%m-%d')
        
        if len(externalWhereClause) > 0:
            externalSql += " AND ".join(externalWhereClause)
                    
        externalSql += """ AND EventId NOT IN (SELECT DISTINCT ExternalEventsNew.EventId FROM ExternalEventsNew
            JOIN Sellers ON Sellers.SellerId = ExternalEventsNew.SellerId 
            JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId 
            JOIN TicketSocketEvents ON SellerEventCategory.SellerEventCategoryId = SellerEventCategory.SellerEventCategoryId AND ExternalEventsNew.EventDate = TicketSocketEvents.EventDate) 
            ORDER BY EventDate ASC, Title ASC"""
    
        externalSql = externalSql.replace('\n', '')

        externalEventRows = db.queryAll(externalSql, externalData)
        for row in externalEventRows:
            eventId = int(row["EventId"])
            vipEvent = VipEvent(eventId, str(row["Title"]))
            vipEvent.eventDate = str(row["EventDate"])
            vipEvent.thumbnail = str(row["Thumbnail"])
            vipEvent.ticketSocketUrl = str(row["URL"])
            venue = TicketSocketVenue(str(row["Venue"]), str(row["Address"]), '', str(row["City"]), str(row["State"]), str(row["Zip"]), str(row["Country"]), '')
            vipEvent.venue = venue
            vipEvent.isActive = True if int(row["IsActive"]) == 1 else False
            vipEvent.externalEventId = int(row["EventId"])
            vipEvent.externalSellerId = int(row["SellerId"])
            vipEvent.disableLinkButton = str(row["DisableLinkButton"])
            vipEvent.disableLinkReason = str(row["DisableLinkReason"])
            vipEvent.externalVipLink = str(row["ExternalVipLink"])
            vipEvent.disableVipLinkButton = str(row["DisableVipLinkButton"])
            vipEvent.disableVipLinkReason = str(row["DisableVipLinkReason"])
            events.append(vipEvent)

        events.sort(key = operator.attrgetter('eventDate', 'title', 'externalEventId'))

        return events

    def __getOrdersFromEventId(self, ticketSocketEventId: int):
        orders: list[VipOrder] = []
        sql = """SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate, TicketSocketOrders.* FROM TicketSocketOrders
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
                    JOIN TicketSocket ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId
                    LEFT JOIN ExchangeRateHistory ON ExchangeRateHistory.ExchangeRateId = TicketSocket.ExchangeRateId 
                        AND ExchangeRateHistory.MidnightDate = TicketSocketOrders.PurchaseDate WHERE TicketSocketEventId=%(ticketSocketEventId)s"""
        data = {
            'ticketSocketEventId': ticketSocketEventId
        }

        rows = db.queryAll(sql, data)
        for row in rows:
            orderId = int(row["OrderId"])
            eventId = int(row["EventId"])
            ticketSocketOrderId = int(row["Id"])
            order = VipOrder(orderId, eventId)
            order.ticketSocketEventId = ticketSocketEventId
            order.ticketSocketOrderId = ticketSocketOrderId
            order.numTickets = int(row["NumTickets"])
            order.purchaseDate = str(row["PurchaseDate"])
            order.userId = int(row["UserId"])
            order.phone = str(row["Phone"])
            order.email = str(row["Email"])
            order.purchaserLastName = str(row["PurchaserLastName"])
            order.purchaserFirstName = str(row["PurchaserFirstName"])
            order.revenue = float(row["Revenue"])
            order.exchangeRate = float(row["ExchangeRate"])
            order.isActive = True if int(row["IsActive"]) == 1 else False
            shirtStr = str(row["Shirts"]).strip()
            shirts = []
            if len(shirtStr) > 0:
                shirtArray = shirtStr.split("/")
                for shirt in shirtArray:
                    shirts.append(shirt.strip())
            order.shirts = shirts
            attendeeStr = str(row["AttendeeNames"]).strip()
            attendees = []
            if len(attendeeStr) > 0:
                attendeeArray = attendeeStr.split("/")
                for attendee in attendeeArray:
                    attendees.append(attendee.strip())
            order.attendeeNames = attendees
            tickets = self.__getTicketsFromOrderId(ticketSocketOrderId)
            order.tickets = tickets
            order.getTotals()
            orders.append(order)
        return orders

    def __getTicketsFromOrderId(self, ticketSocketOrderId: int):
        tickets: list[VipTicket] = []
        sql = """SELECT * FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=%(ticketSocketOrderId)s"""
        data = {
            'ticketSocketOrderId': ticketSocketOrderId
        }

        rows = db.queryAll(sql, data)
        for row in rows:
            ticketId: int = 0
            if row["TicketId"] != None and row["TicketId"] != '':
                ticketId = int(row["TicketId"])
            ticket = VipTicket(ticketId, str(row["TicketType"]), float(row["Price"]))
            ticket.ticketSocketOrderId = ticketSocketOrderId
            ticket.ticketSocketOrderTicketId = int(row["Id"])
            ticket.isActive = True if int(row["IsActive"]) == 1 else False
            tickets.append(ticket)
        return tickets

    def retrieveTicketSocketEventsForUpdate(self, sellerId: int = None, start: int = None, end: int = None):
        # go get seller information from database
        seller: Seller = None

        if sellerId != None:
            seller = Seller(sellerId)

        # fetch TS data
        tsSql = "SELECT TicketSocketId, IsVip FROM TicketSocket"
        rows = db.queryAll(tsSql)

        # query events across all TS services
        allEvents: list[VipEvent] = []
        for row in rows:
            ticketSocketId = int(row['TicketSocketId'])
            isVipService = (int(row["IsVip"]) == 1)
            tss = TicketSocketService(ticketSocketId)

            # get event category for this TS account, if the seller has one
            eventCategoryId: int = None
            refreshSec: SellerEventCategory = None
            if seller != None:
                refreshSec = seller.getSellerEventCategory(ticketSocketId)

                # if we are restricting by seller and the seller doesn't have a category on this TS service, 
                # just skip it or the service will return everything for everyone in the time period
                if refreshSec != None:
                    eventCategoryId = refreshSec.eventCategoryId
                else:
                    continue

            events = tss.getEventsAndOrders(eventCategoryId, start, end)            

            if len(events) > 0:
                for event in events:
                    # convert ts events to vip events
                    vipEvent = VipEvent(event.id, event.title)
                    vipEvent.__dict__.update(event.__dict__)
                    vipEvent.isVip = isVipService

                    # populate sellerEventCategoryId, which is required on our end
                    if refreshSec != None:
                        vipEvent.sellerEventCategoryId = refreshSec.sellerEventCategoryId
                    elif vipEvent.eventCategoryId != None:
                        secTemp = SellerEventCategory(None, ticketSocketId, vipEvent.eventCategoryId)
                        vipEvent.sellerEventCategoryId = secTemp.sellerEventCategoryId

                    # if this combo of TS and category does not exist on our side, we can't update this event
                    if vipEvent.sellerEventCategoryId == None:
                        continue

                    #convert the orders
                    orders: list[VipEvent] = []
                    for order in event.orders:
                        vipOrder = VipOrder(order.id, order.eventId)
                        vipOrder.__dict__.update(order.__dict__)
                        orders.append(vipOrder)

                    vipEvent.orders = orders

                    allEvents.append(vipEvent)

        return allEvents

    def refreshDatabaseFromTicketSocket(self, sellerId: int = None, start: int = None, end: int = None, userId: int = 0):
        # initialize counters
        startTimer: int = int(time.time())
        endTimer: int = 0
        duration: int = 0

        serviceEventsSkipped: list[str] = []
        eventsFailed: list[int] = []
        ordersFailed: list[int] = []
        ticketsFailed: list[int] = []    
        totalEventsFromService: int = 0
        eventsUpdated: int = 0
        eventsInserted: int = 0
        eventsDeactivated: int = 0
        ordersInserted: int = 0
        ordersUpdated: int = 0
        ordersDeactivated: int = 0
        ticketsUpdated: int = 0
        ticketsInserted: int = 0
        ticketsDeactivated: int = 0

        allEvents = self.retrieveTicketSocketEventsForUpdate(sellerId, start, end)

        # get total number of events grabbed from service
        totalEventsFromService = len(allEvents)        

        if totalEventsFromService > 0:
            serviceEvents: list[int] = []
            for evt in allEvents:
                if evt.sellerEventCategoryId <= 0:
                    serviceEventsSkipped.append(evt.title + ' - eventId ' + str(evt.id) + ' (' + evt.ticketSocketUrl + ')')
                    continue

                serviceEvents.append(evt.id)
                # compile event data for update
                address = evt.venue.address1
                if evt.venue and evt.venue.address2:
                    address += " " + evt.venue.address2
                
                eventData = {
                    'title': evt.title.strip(),
                    'eventDate': evt.eventDate.strip(),
                    'utcTime': evt.utcTime,
                    'url': evt.ticketSocketUrl.strip(),
                    'venue': evt.venue.name.strip(),
                    'address': address.strip(),
                    'city': evt.venue.city.strip(),
                    'state': evt.venue.state.strip(),
                    'zip': evt.venue.postalCode.strip(),
                    'country': evt.venue.country.strip(),
                    'onsale': 1 if evt.onSale else 0,
                    'thumbnail': evt.thumbnail.strip(),
                    'displayDate': evt.displayDate.strip(),
                    'isVip': 1 if evt.isVip else 0
                }

                # determine if event already exists
                eventSql = "SELECT * FROM TicketSocketEvents WHERE EventId=%(eventId)s AND SellerEventCategoryId=%(sellerEventCategoryId)s"

                data = {
                    'eventId': evt.id,
                    'sellerEventCategoryId': evt.sellerEventCategoryId
                }

                existingEvent = db.queryOne(eventSql, data)

                eventSuccess: bool = False
                ticketSocketEventId: int = 0
                eventAddNew: bool = False
                
                if existingEvent != {}:
                    # update existing event
                    ticketSocketEventId = int(existingEvent['Id'])
                    eventData['id'] = ticketSocketEventId
                    sql = """UPDATE TicketSocketEvents SET Title=%(title)s, 
                             EventDate=%(eventDate)s, UtcTime=%(utcTime)s, URL=%(url)s, Venue=%(venue)s, 
                             Address=%(address)s, City=%(city)s, State=%(state)s, 
                             Zip=%(zip)s, Country=%(country)s, OnSale=%(onsale)s, 
                             Thumbnail=%(thumbnail)s, DisplayDate=%(displayDate)s, IsVip=%(isVip)s, 
                             IsActive=1, LastUpdate=CURRENT_TIMESTAMP
                             WHERE Id=%(id)s"""
                    eventSuccess = db.update(sql, eventData)
                else:
                    eventAddNew = True
                    # insert new event
                    eventData['eventId'] = int(evt.id)
                    eventData['sellerEventCategoryId'] = int(evt.sellerEventCategoryId)
                    sql = """INSERT INTO TicketSocketEvents (SellerEventCategoryId, EventId, Title, EventDate, UtcTime, 
                                URL, Venue, Address, City, State, Zip, Country, 
                                OnSale, Thumbnail, DisplayDate, IsVip) 
                                VALUES (%(sellerEventCategoryId)s, %(eventId)s, %(title)s, %(eventDate)s, %(utcTime)s, 
                                %(url)s, %(venue)s, %(address)s, %(city)s, %(state)s, %(zip)s, %(country)s, 
                                %(onsale)s, %(thumbnail)s, %(displayDate)s, %(isVip)s)"""
                    ticketSocketEventId = db.insert(sql, eventData)
                    eventSuccess = (ticketSocketEventId > 0)                

                # if the update succeeded, update counters
                if eventSuccess:
                    if eventAddNew:
                        eventsInserted += 1
                    else:
                        eventsUpdated += 1
                else:
                    # if that failed, just mark it failed and skip orders
                    eventsFailed.append(evt.id)
                    continue
                
                if ticketSocketEventId and len(evt.orders) > 0:
                    eventOrders: list[int] = []
                    for order in evt.orders:
                        eventOrders.append(order.id)
                        # compile order data for update
                        shirts: str = ''
                        if len(order.shirts) > 0:
                            shirts = " / ".join(order.shirts)
                        attendeeNames: str = ''
                        if len(order.attendeeNames) > 0:
                            attendeeNames = " / ".join(order.attendeeNames)

                        orderData = {
                            'numTickets': order.numTickets,
                            'purchaseDate': order.purchaseDate.strip(),
                            'phone': order.phone.strip(),
                            'shirts': shirts,
                            'attendeeNames': attendeeNames,
                            'userId': order.userId,
                            'eventId': order.eventId,
                            'purchaserLastName': order.purchaserLastName.strip(),
                            'purchaserFirstName': order.purchaserFirstName.strip(),
                            'email': order.email.strip(),
                            'revenue': order.revenue
                        }

                        # determine if order already exists
                        orderSql = "SELECT * FROM TicketSocketOrders WHERE TicketSocketEventId=%(ticketSocketEventId)s AND OrderId=%(orderId)s"

                        data = {
                            'ticketSocketEventId': ticketSocketEventId,
                            'orderId': order.id
                        }

                        existingOrder = db.queryOne(orderSql, data)

                        orderSuccess: bool = False
                        ticketSocketOrderId: int = 0
                        orderAddNew: bool = False

                        if existingOrder != {}:
                            #update existing order
                            ticketSocketOrderId = int(existingOrder['Id'])
                            orderData['id'] = ticketSocketOrderId
                            sql = """Update TicketSocketOrders SET NumTickets=%(numTickets)s, PurchaseDate=%(purchaseDate)s, Phone=%(phone)s, Shirts=%(shirts)s, 
									AttendeeNames=%(attendeeNames)s, EventId=%(eventId)s, UserId=%(userId)s, PurchaserLastName=%(purchaserLastName)s, 
                                    PurchaserFirstName=%(purchaserFirstName)s, Email=%(email)s, Revenue=%(revenue)s, 
                                    IsActive=1, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                            orderSuccess = db.update(sql, orderData)
                        else:
                            orderAddNew = True
                            #insert new order
                            orderData['orderId'] = int(order.id)
                            orderData['ticketSocketEventId'] = ticketSocketEventId
                            sql = """INSERT INTO TicketSocketOrders (TicketSocketEventId, OrderId, NumTickets, PurchaseDate, Phone, Shirts, 
											AttendeeNames, EventId, UserId, PurchaserLastName, PurchaserFirstName, Email, Revenue) 
                                            VALUES (%(ticketSocketEventId)s, %(orderId)s, %(numTickets)s, %(purchaseDate)s, %(phone)s, %(shirts)s, 
                                            %(attendeeNames)s, %(eventId)s, %(userId)s, %(purchaserLastName)s, %(purchaserFirstName)s, %(email)s, %(revenue)s)"""
                            ticketSocketOrderId = db.insert(sql, orderData)
                            orderSuccess = (ticketSocketOrderId > 0)

                        # if the update succeeded, update counters
                        if orderSuccess:
                            if orderAddNew:
                                ordersInserted += 1
                            else:
                                ordersUpdated += 1
                        else:
                            # if that failed, just mark it failed and skip orders
                            ordersFailed.append(order.id)
                            continue

                        if ticketSocketOrderId and len(order.tickets) > 0:
                            orderTickets: list[int] = []

                            # clean up any migrated data that doesn't have ticket Ids
                            deleteSql = "DELETE FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=%(ticketSocketOrderId)s AND TicketId IS NULL"
                            deleteData = {
                                'ticketSocketOrderId': ticketSocketOrderId
                            }
                            db.delete(deleteSql, deleteData)

                            for ticket in order.tickets:
                                orderTickets.append(ticket.id)
                                # compile ticket data for update
                                ticketData = {
                                    'price': ticket.price,
                                    'ticketType': ticket.ticketType.strip()
                                }

                                # determine if ticket already exists
                                ticketSql = "SELECT * FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=%(ticketSocketOrderId)s AND TicketId=%(ticketId)s"

                                data = {
                                    'ticketSocketOrderId': ticketSocketOrderId,
                                    'ticketId': ticket.id
                                }

                                existingTicket = db.queryOne(ticketSql, data)

                                ticketSuccess: bool = False
                                ticketSocketOrderTicketId: int = 0
                                ticketAddNew: bool = False
                                
                                if existingTicket != {}:
                                    #update existing ticket
                                    ticketSocketOrderTicketId = int(existingTicket['Id'])
                                    ticketData['id'] = ticketSocketOrderTicketId
                                    
                                    sql = """Update TicketSocketOrderTickets SET TicketType=%(ticketType)s, Price=%(price)s, 
                                             LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                    ticketSuccess = db.update(sql, ticketData)
                                else:
                                    #insert new ticket
                                    ticketAddNew = True
                                    ticketData['ticketId'] = int(ticket.id)
                                    ticketData['ticketSocketOrderId'] = ticketSocketOrderId
                                    sql = """INSERT INTO TicketSocketOrderTickets (TicketSocketOrderId, TicketId, TicketType, Price) 
                                             VALUES (%(ticketSocketOrderId)s, %(ticketId)s, %(ticketType)s, %(price)s)"""
                                    ticketSocketOrderTicketId = db.insert(sql, ticketData)
                                    ticketSuccess = (ticketSocketOrderTicketId > 0)

                                # if the update succeeded, update counters
                                if ticketSuccess:
                                    if ticketAddNew:
                                        ticketsInserted += 1
                                    else:
                                        ticketsUpdated += 1
                                else:
                                    # if that failed, just mark it failed and skip orders
                                    ticketsFailed.append(ticket.id)
                                    continue
                            
                            # find any tickets not returned by the service and mark as inactive
                            if len(orderTickets) > 0:
                                orderTicketData = {
                                    'ticketSocketOrderId': ticketSocketOrderId
                                }
                                orderTicketStr = db.convertListToParameters(orderTickets, orderTicketData, 'orderTicket')
                                sql = """UPDATE TicketSocketOrderTickets Set IsActive=0 
                                         WHERE TicketSocketOrderId=%(ticketSocketOrderId)s AND TicketId NOT IN """ + orderTicketStr

                                inactiveTickets = db.update(sql, orderTicketData)
                                ticketsDeactivated += inactiveTickets
                            
                    # find any orders not returned by the service and mark as inactive
                    if len(eventOrders) > 0:
                        eventOrderData = {
                            'ticketSocketEventId': ticketSocketEventId
                        }
                        eventOrderStr = db.convertListToParameters(eventOrders, eventOrderData, 'eventOrder')
                        sql = """UPDATE TicketSocketOrders Set IsActive=0 
                                 WHERE TicketSocketEventId=%(ticketSocketEventId)s AND OrderId NOT IN """ + eventOrderStr
 
                        inactiveOrders = db.update(sql, eventOrderData)
                        ordersDeactivated += inactiveOrders

            # find any orders not returned by the service and mark as inactive
            if len(serviceEvents) > 0:
                deleteData = {}
                delEventSql = "SELECT Id FROM TicketSocketEvents WHERE IsActive=1 AND EventDate"
                if start != None and end != None:
                    deleteData['startDate'] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
                    deleteData['endDate'] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
                    delEventSql += " BETWEEN %(startDate)s AND %(endDate)s"
                else:
                    deleteData['startDate'] = datetime.now().strftime('%Y-%m-%d')
                    delEventSql += " >= %(startDate)s"

                if sellerId != None:
                    sql = "SELECT TicketSocketId FROM TicketSocket"
                    rows = db.queryAll(sql)
                    sellerEventCategories: list[str] = []
                    for row in rows:
                        ticketSocketId = int(row['TicketSocketId'])
                        seller = SellerEventCategory(sellerId, ticketSocketId)
                        if seller.sellerEventCategoryId > 0:
                            sellerEventCategories.append(str(seller.sellerEventCategoryId))
                    if len(sellerEventCategories) > 0:
                        sellerEventCategoryStr = db.convertListToParameters(sellerEventCategories, deleteData, 'sellerEventCategory')
                        delEventSql += " AND SellerEventCategoryId IN " + sellerEventCategoryStr
                
                deleteEventStr = db.convertListToParameters(serviceEvents, deleteData, 'serviceEvent')
                delEventSql += " AND EventId NOT IN " + deleteEventStr

                deleteRows = db.queryAll(delEventSql, deleteData)
                for dRow in deleteRows:
                    id = int(dRow['Id'])

                    serviceEventData = {
                        'id': id
                    }

                    sql = """UPDATE TicketSocketEvents SET IsActive=0 
                            WHERE Id = %(id)s"""
                    inactiveEvents = db.update(sql, serviceEventData)
                    eventsDeactivated += inactiveEvents       

        endTimer = int(time.time())
        duration = endTimer - startTimer              
                                
        results = TicketSocketRefreshHistory(serviceEventsSkipped, eventsFailed, ordersFailed, ticketsFailed, totalEventsFromService, 
                                            eventsUpdated, eventsInserted, eventsDeactivated, ordersInserted, ordersUpdated, ordersDeactivated, 
                                            ticketsUpdated, ticketsInserted, ticketsDeactivated, startTimer, endTimer, duration, userId, sellerId, start, end)
        
        saved: bool = results.commit()

        if saved:
            return results
        else:
            return None
        