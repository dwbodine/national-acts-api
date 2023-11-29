import os
import json
import time
from datetime import datetime

from . import utility
from . import db
from common.ticket_socket_service import *
from common.models.national_acts import *
from common.models.ticket_socket import *

class EventService:
    def getEventsAndOrders(self, sellerId: int = None, start: int = None, end: int = None, searchTerm: str = None):
        pass

    def getOrdersFromEventId(self, eventId: int):
        pass

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
                delEventSql = "SELECT Id FROM TicketSocketEvents WHERE IsActive=1 AND (EventDate"
                if start != None and end != None:
                    deleteData['startDate'] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
                    deleteData['endDate'] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
                    delEventSql += " >= %(startDate)s and EventDate <= %(endDate)s)'"
                else:
                    deleteData['startDate'] = datetime.now().strftime('%Y-%m-%d')
                    delEventSql += " >= %(startDate)s)"

                if sellerId != None:
                    sql = "SELECT TicketSocketId FROM TicketSocket"
                    rows = db.queryAll(sql)
                    sellerEventCategories: list[str] = []
                    for row in rows:
                        ticketSocketId = int(row['TicketSocketId'])
                        seller = SellerEventCategory(sellerId, ticketSocketId)
                        if seller.sellerEventCategoryId > 0:
                            sellerEventCategories.append(str(seller.sellerEventCategoryId))

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
        