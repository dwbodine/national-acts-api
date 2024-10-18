import traceback
from common import utility
from common.models.ticket_socket import *
from common.models.user import *
import calendar
import datetime

from .. import db

class SellerEventCategory:
    sellerId: int = 0
    ticketSocketId: int = 0
    eventCategoryId: int = 0
    sellerEventCategoryId: int = 0

    def __init__(self, sellerId: int = None, ticketSocketId: int = None, eventCategoryId: int = None, sellerEventCategoryId: int = None):
        if sellerId != None and ticketSocketId != None and eventCategoryId == None and sellerEventCategoryId == None:
            self.__populateFromSellerIdAndTicketSocketId(sellerId, ticketSocketId)
        elif sellerId == None and ticketSocketId != None and eventCategoryId != None and sellerEventCategoryId == None:
            self.__populateFromTicketSocketIdAndEventCategoryId(ticketSocketId, eventCategoryId)
        elif sellerEventCategoryId != None:
            self.__populateFromSellerEventCategoryId(sellerEventCategoryId)
        elif sellerId != None and ticketSocketId != None and eventCategoryId != None and sellerEventCategoryId != None:
            self.sellerId = sellerId
            self.ticketSocketId = ticketSocketId
            self.eventCategoryId = eventCategoryId
            self.sellerEventCategoryId = sellerEventCategoryId
        else:
            raise Exception('Invalid input data for SellerEventCategory')

    def __populateFromSellerIdAndTicketSocketId(self, sellerId: int, ticketSocketId: int):
        self.sellerId = sellerId
        self.ticketSocketId = ticketSocketId
        sql = "SELECT * FROM SellerEventCategory WHERE SellerId=%(sellerId)s AND TicketSocketId=%(ticketSocketId)s"
        data = {
            'sellerId': self.sellerId,
            'ticketSocketId': self.ticketSocketId
        }
        sec = db.queryOne(sql, data)
        if sec != {}:
            self.eventCategoryId = sec['EventCategoryId']
            self.sellerEventCategoryId = sec['SellerEventCategoryId']

    def __populateFromTicketSocketIdAndEventCategoryId(self, ticketSocketId: int, eventCategoryId: int):
        self.ticketSocketId = ticketSocketId
        self.eventCategoryId = eventCategoryId
        sql = "SELECT * FROM SellerEventCategory WHERE TicketSocketId=%(ticketSocketId)s AND EventCategoryId=%(eventCategoryId)s"
        data = {
            'ticketSocketId': self.ticketSocketId,
            'eventCategoryId': self.eventCategoryId
        }
        sec = db.queryOne(sql, data)
        if sec != {}:
            self.sellerId = sec['SellerId']
            self.sellerEventCategoryId = sec['SellerEventCategoryId']

    def __populateFromSellerEventCategoryId(self, sellerEventCategoryId: int):
        self.sellerEventCategoryId = sellerEventCategoryId
        sql = "SELECT * FROM SellerEventCategory WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"
        data = {
            'sellerEventCategoryId': self.sellerEventCategoryId
        }
        sec = db.queryOne(sql, data)
        if sec != {}:
            self.sellerId = sec['SellerId']
            self.ticketSocketId = sec['TicketSocketId']
            self.eventCategoryId = sec['EventCategoryId']
  

class ShirtSales:
    def __init__(self, size: str, total: int):
        self.size = size
        self.total = total

class VipTicket(TicketSocketTicket):
    ticketSocketOrderId: int = 0
    ticketSocketOrderTicketId: int = 0
    isActive: bool = True

    def __init__(self, id: int, ticketType: str, price: float, serviceFee: float, ticketTypeId: int, barcode: str, availableScans: int, purchaseLocation: str, scannedTimestamp: int):
        super().__init__(id, ticketType, price, serviceFee, ticketTypeId, barcode, availableScans, purchaseLocation, scannedTimestamp)

class VipOrder(TicketSocketOrder):
    ticketSocketEventId: int = 0
    ticketSocketOrderId: int = 0
    sellerName: str = None
    sellerId: int = 0
    venue: str = None
    eventTitle: str = None
    eventAddress: str = None
    eventCity: str = None
    eventState: str = None
    eventZip: str = None
    eventCountry: str = None
    eventDate: str = None
    isActive: bool = True
    isDeleted: bool = False
    isRefunded: bool = False
    isChargedBack: bool = False
    refundDate: str = None
    chargebackDate: str = None
    numTicketsRefunded: int = 0
    revenueRefunded: float = 0
    serviceFeeRevenueRefunded: float = 0
    totalShirts: int = 0
    revenueUsd: float = 0
    serviceFeesUsd: float = 0
    exchangeRate: float = 1.0
    currencySymbol: str = None
    currencyAbbrev: str = None
    tickets: list[VipTicket] = []
    isHidden: bool = False

    def __init__(self, id: int, eventId: int):
        super().__init__(id, eventId)

    def getTotals(self):
        self.totalShirts = len(self.shirts)
        self.revenueUsd = self.revenue * self.exchangeRate            
        self.serviceFeesUsd = self.serviceFees * self.exchangeRate
        if self.numTickets > 0:
            i = 0
            for ticket in self.tickets:
                if len(self.attendeeNames) >= (i + 1):
                    ticket.attendeeName = self.attendeeNames[i]
                i += 1
    
class VipEvent(TicketSocketEvent):
    ticketSocketEventId: int = 0
    totalRevenue: float = 0
    totalServiceFees: float = 0
    totalTickets: int = 0
    totalCheckedIn: int = 0
    totalShirts: int = 0
    shirtSales: list[ShirtSales] = []
    isActive: bool = True
    orders: list[VipOrder] = []
    externalEventId: int = None
    externalSellerId: int = None
    externalTitle: str = None
    externalThumbnail: str = None
    externalUrl: str = None
    externalVenue: TicketSocketVenue = None
    disableLinkButton: bool = False
    disableLinkReason: bool = False
    externalVipLink: str = None
    disableVipLinkButton: bool = False
    disableVipLinkReason: bool = False
    sellerEventCategoryId: int = None
    isVip: bool = True
    isDeleted: bool = False
    isExternal: bool = False
    hasShirtData: bool = False
    hasPhoneData: bool = False
    hasNonUSAOrders: bool = False
    nonUsaCurrencySymbol: str = None
    nonUsaCurrencyAbbrev: str = None
    numTicketsRefunded: int = 0
    revenueRefunded: float = 0
    serviceFeeRevenueRefunded: float = 0
    hasTicketTypeData: bool = False
    isAddedToBandsInTown: bool = False
    sellerName: str = ''
    isHidden: bool = False

    def getTotals(self):
        totalRevenue: float = 0
        totalServiceFees: float = 0
        totalTickets: int = 0
        totalShirts: int = 0
        totalTicketsRefunded: int = 0
        totalRevenueRefunded: int = 0
        totalServiceFeeRevenueRefunded: int = 0
        totalCheckedIn: int = 0
        shirtd: dict() = {}
        for order in self.orders:
            if order.isRefunded or order.isChargedBack:
                totalTicketsRefunded += order.numTicketsRefunded
                totalRevenueRefunded += order.revenueRefunded
                totalServiceFeeRevenueRefunded += order.serviceFeeRevenueRefunded
            if self.hasNonUSAOrders == False and order.currencyAbbrev != "USD":
                self.hasNonUSAOrders = True
                self.nonUsaCurrencyAbbrev = order.currencyAbbrev
                self.nonUsaCurrencySymbol = order.currencySymbol

            if self.hasShirtData == False and len(order.shirts) > 0:
                self.hasShirtData = True

            if self.hasPhoneData == False and order.phone != None and len(order.phone) > 0:
                self.hasPhoneData = True
                
            if order.isDeleted != True:
                totalRevenue += order.revenueUsd
                totalServiceFees += order.serviceFeesUsd
                totalTickets += order.numTickets
                
                if len(order.tickets) > 0:
                    for ticket in order.tickets:
                        if ticket.isCheckedIn:
                            totalCheckedIn += 1
                
                if len(order.shirts) > 0:
                    totalShirts += len(order.shirts)
                    for size in order.shirts:
                        if size in shirtd:
                            shirtd[size] = int(shirtd[size]) + 1
                        else:
                            shirtd[size] = 1

        self.totalRevenue = totalRevenue
        self.totalServiceFees = totalServiceFees
        self.totalTickets = totalTickets
        self.totalCheckedIn = totalCheckedIn
        self.totalShirts = totalShirts
        self.numTicketsRefunded = totalTicketsRefunded
        self.revenueRefunded = totalRevenueRefunded
        self.serviceFeeRevenueRefunded = totalServiceFeeRevenueRefunded
        
        self.hasTicketTypeData = (len(self.ticketTypes) > 0)
        
        shirtSales: list[ShirtSales] = []
        for size in shirtd:
            shirtSale = ShirtSales(size, int(shirtd[size]))
            shirtSales.append(shirtSale)
        self.shirtSales = shirtSales

        # roll up external event data, if any
        if self.externalTitle != None and self.externalTitle != "":
            self.title = self.externalTitle
            
        if self.externalVenue != None:
            if self.externalVenue.name != None and self.externalVenue.name != "":
                self.venue.name = self.externalVenue.name
            if self.externalVenue.address1 != None and self.externalVenue.address1 != "":
                self.venue.address1 = self.externalVenue.address1
            if self.externalVenue.address2 != None and self.externalVenue.address2 != "":
                self.venue.address2 = self.externalVenue.address2
            if self.externalVenue.city != None and self.externalVenue.city != "":
                self.venue.city = self.externalVenue.city
            if self.externalVenue.state != None and self.externalVenue.state != "":
                self.venue.state = self.externalVenue.state
            if self.externalVenue.postalCode != None and self.externalVenue.postalCode != "":
                self.venue.postalCode = self.externalVenue.postalCode

        if self.externalThumbnail != None and self.externalThumbnail != "":
            self.thumbnail = self.externalThumbnail
        
        if self.externalVipLink != None and self.externalVipLink != "":
            self.ticketSocketUrl = self.externalVipLink
            
class DailyOrderData:
    ticketSocketOrderId: int = None
    orders: int = 0
    tickets: int = 0
    ticketRevenueUsd: float = 0
    serviceFeesRevenueUsd: float = 0
    totalRevenueUsd: float = 0
    eventTitle: str = None
    eventDate: str = None
    sellerId: int = None
    sellerName: str = None
    venue: str = None
    city: str = None
    state: str = None
    zip: str = None
    country: str = None
    ticketSocketId: int = 0
    isRefunded: bool = False
    isChargeback: bool = False
    numTicketsRefunded: int = 0
    revenueRefunded: float = 0
    serviceFeeRevenueRefunded: float = 0
    
    def __init__(self, purchaseDate: str, ticketSocketEventId: int):
        self.purchaseDate = purchaseDate
        self.ticketSocketEventId = ticketSocketEventId

class DashboardTotals:
    tickets: int = 0
    orders: int = 0
    numTicketsRefunded: int = 0
    ticketRevenueUsd: float = 0
    serviceFeesRevenueUsd: float = 0
    totalRevenueUsd: float = 0
    revenueRefunded: float = 0
    serviceFeeRevenueRefunded: float = 0
    pricePerTicket: float = 0
    serviceFeePerTicket: float = 0
    dailyOrderData: list[DailyOrderData] = []
   
    def __init__(self, year: int, month: int, day: int):
        self.year = year    
        self.month = month
        self.day = day
        self.daysInMonth = calendar.monthrange(year, month)[1]
        self.dayOfYear = datetime.datetime(year, month, day).timetuple().tm_yday
        self.totalDaysInYear = datetime.datetime(year, 12, 31).timetuple().tm_yday
        sql = "SELECT * FROM Settings WHERE Name=%(name)s"
        data = {
            'name': 'YearlyRevenueGoal'
        }
        row = db.queryOne(sql, data)
        self.yearlyRevenueGoal = float(row["Value"])
        data = {
            'name': 'MonthlyRevenueGoal'
        }
        row = db.queryOne(sql, data)
        self.monthlyRevenueGoal = float(row["Value"])
        
class DashboardPayload:
    def __init__(self, orders: list[VipOrder], totals: DashboardTotals):
        self.orders = orders
        self.totals = totals    
    
class Seller:
    hideInList: bool = False
    isActive: bool = True
    name: str = None
    sellerType: int = 1

    sellerEventCategories: list[SellerEventCategory] = []

    def __init__(self, sellerId: int):
        self.sellerId = sellerId
        self.__initialize()

    def __initialize(self):
        sql = """SELECT * FROM Sellers
                 WHERE SellerId=%(sellerId)s"""
        data = {
            'sellerId': self.sellerId
        }

        row = db.queryOne(sql, data)
        if row != {}:
            self.name = str(row['Name'])
            self.sellerType = int(row["SellerTypeId"])
            self.hideInList = int(row['HideInList']) == 1
            self.isActive = int(row['Inactive']) != 1
            self.__getSellerEventCategories()

    def __getSellerEventCategories(self):
        sql = """SELECT * 
                 FROM SellerEventCategory
                 WHERE SellerId=%(sellerId)s"""
        data = {
            'sellerId': self.sellerId
        }

        sellerEventCategories = []
        rows = db.queryAll(sql, data)
        for row in rows:
            sec = SellerEventCategory(self.sellerId, int(row['TicketSocketId']), int(row['EventCategoryId']), int(row['SellerEventCategoryId']))
            sellerEventCategories.append(sec)
        self.sellerEventCategories = sellerEventCategories

    def getSellerEventCategory(self, ticketSocketId: int):
        if len(self.sellerEventCategories) == 0:
            return None
        
        sellerEventCategory = None
        for sec in self.sellerEventCategories:
            if sec.ticketSocketId == ticketSocketId:
                sellerEventCategory = sec
                break

        return sellerEventCategory
    
    def getSellerEventCategoryIds(self):
        ids: list[int] = []
        if len(self.sellerEventCategories) > 0:
            for sec in self.sellerEventCategories:
                ids.append(sec.sellerEventCategoryId)
        return ids
  
class TicketSocketRefreshHistory:
    sellerName: str = None
    userName: str = None
    ticketSocketRefreshHistoryId: int = None
    orderDataRowsRemoved: int = 0
    orderDataRowsUpdated: int = 0
    orderDataRowsInserted: int = 0
    orderDataRowsTotal: int = 0
    orderDataUpdateSucceeded: bool = False
    orderDataUpdateDuration: float = 0
    totalDuration: float = 0

    def __init__(self, serviceEventsSkipped: list[int], eventsFailed: list[int], ordersFailed: list[int], ticketsFailed: list[int], ticketTypesFailed: list[int], 
                  totalEventsFromService: int, eventsUpdated: int, eventsInserted: int, ordersInserted: int, ordersUpdated: int, 
                  ordersDeleted: int, ticketsUpdated: int, ticketsInserted: int, ticketTypesUpdated: int, ticketTypesInserted: int, 
                  startTimer: int, endTimer: int, duration: float, userId: int = 0, sellerId: int = 0, start: int = 0, end: int = 0, succeeded: bool = False,
                  errorMessage: str = None):
        self.serviceEventsSkipped = serviceEventsSkipped
        self.eventsFailed = eventsFailed
        self.ordersFailed = ordersFailed
        self.ticketsFailed = ticketsFailed
        self.ticketTypesFailed = ticketTypesFailed
        self.totalEventsFromService = totalEventsFromService
        self.eventsUpdated = eventsUpdated
        self.eventsInserted = eventsInserted
        self.ordersInserted = ordersInserted
        self.ordersUpdated = ordersUpdated
        self.ordersDeleted = ordersDeleted
        self.ticketsUpdated = ticketsUpdated
        self.ticketsInserted = ticketsInserted
        self.ticketTypesUpdated = ticketTypesUpdated
        self.ticketTypesInserted = ticketTypesInserted
        self.userId = userId
        self.sellerId = sellerId
        self.start = start
        self.end = end
        self.startTimer = startTimer
        self.endTimer = endTimer
        self.duration = duration
        self.succeeded = succeeded
        self.errorMessage = errorMessage

    def __getSellerName(self):
        if self.sellerId != None:
            seller = Seller(self.sellerId)
            self.sellerName = seller.name + " (SellerId: " + str(self.sellerId) + ")"
            
    def cleanup(self, cnx = None):
        success: bool = True
        
        try:
            weekAgo: int = self.endTimer - (24 * 60 * 60)            
            sql = """DELETE FROM TicketSocketRefreshHistory WHERE EndTimer <= %(weekAgo)s"""
            data = {
                'weekAgo': weekAgo
            }
            db.delete(sql, data, cnx)
        except Exception as error:
            success = False
            errorMessage: str = str(error) + "\n" + traceback.format_exc()
            utility.logMessage(errorMessage)
            
        return success
    
    def setOrderUpdateSuccess(self, success: bool, duration: float, inserts: int, updates: int, cnx = None):
        if self.ticketSocketRefreshHistoryId <= 0:
            self.orderDataUpdateSucceeded = False
            return
        
        self.orderDataUpdateSucceeded = success
        self.orderDataUpdateDuration = duration
        self.orderDataRowsInserted = inserts
        self.orderDataRowsUpdated = updates
        totalDuration = self.duration + duration
        self.totalDuration = totalDuration
        
        sql = """UPDATE TicketSocketRefreshHistory SET OrderDataUpdateSucceeded=%(successVal)s, 
                    OrderDataUpdateDuration=%(orderDataUpdateDuration)s, TotalDuration=%(totalDuration)s, 
                    OrderDataRowsTotal=%(orderDataRowsTotal)s, OrderDataRowsInserted=%(orderDataRowsInserted)s, 
                    OrderDataRowsUpdated=%(orderDataRowsUpdated)s, OrderDataRowsRemoved=%(orderDataRowsRemoved)s, 
                    LastUpdate=CURRENT_TIMESTAMP 
                    WHERE TicketSocketRefreshHistoryId=%(ticketSocketRefreshHistoryId)s"""
        data = {
            'successVal': 1 if success == True else 0,
            'ticketSocketRefreshHistoryId': self.ticketSocketRefreshHistoryId, 
            'orderDataUpdateDuration': duration, 
            'totalDuration': totalDuration, 
            'orderDataRowsTotal': self.orderDataRowsTotal,
            'orderDataRowsInserted': self.orderDataRowsInserted,
            'orderDataRowsUpdated': self.orderDataRowsUpdated,
            'orderDataRowsRemoved': self.orderDataRowsRemoved
        }
        db.update(sql, data, cnx)        

    def commit(self, cnx = None):
        if self.endTimer > 0:
            self.cleanup(cnx)
            
        self.__getSellerName()

        sql = """INSERT INTO TicketSocketRefreshHistory (UserId, SellerId, Start, End, StartTimer, EndTimer, Duration, Success, ErrorMessage, 
                 ServiceEventsSkipped,  EventsFailed, OrdersFailed, TicketsFailed, TicketTypesFailed, TotalEventsFromService, EventsUpdated, EventsInserted,  
                 OrdersInserted, OrdersUpdated, OrdersDeleted, TicketsUpdated, TicketsInserted,  
                 TicketTypesUpdated, TicketTypesInserted) VALUES (%(userId)s, %(sellerId)s, 
                 %(start)s, %(end)s, %(startTimer)s, %(endTimer)s, %(duration)s, %(success)s, %(errorMessage)s, %(serviceEventsSkipped)s, %(eventsFailed)s, 
                 %(ordersFailed)s, %(ticketsFailed)s, %(ticketTypesFailed)s, %(totalEventsFromService)s, %(eventsUpdated)s, %(eventsInserted)s, %(ordersInserted)s, 
                 %(ordersUpdated)s, %(ordersDeleted)s, %(ticketsUpdated)s, %(ticketsInserted)s,  
                 %(ticketTypesUpdated)s, %(ticketTypesInserted)s)"""
        
        data = {
            'userId': self.userId,
            'sellerId': self.sellerId,
            'start': self.start,
            'end': self.end,
            'startTimer': self.startTimer,
            'endTimer': self.endTimer,
            'duration': self.duration,
            'success': 1 if self.succeeded == True else 0,
            'errorMessage': self.errorMessage,
            'serviceEventsSkipped': ", ".join(self.serviceEventsSkipped),
            'eventsFailed': ", ".join(str(v) for v in self.eventsFailed),
            'ordersFailed': ", ".join(str(v) for v in self.ordersFailed),
            'ticketsFailed': ", ".join(str(v) for v in self.ticketsFailed),
            'ticketTypesFailed': ", ".join(str(v) for v in self.ticketTypesFailed),
            'totalEventsFromService': self.totalEventsFromService,
            'eventsUpdated': self.eventsUpdated,
            'eventsInserted': self.eventsInserted,
            'ordersInserted': self.ordersInserted,
            'ordersUpdated': self.ordersUpdated,
            'ordersDeleted': self.ordersDeleted,
            'ticketsUpdated': self.ticketsUpdated,
            'ticketsInserted': self.ticketsInserted, 
            'ticketTypesUpdated': self.ticketTypesUpdated,
            'ticketTypesInserted': self.ticketTypesInserted
        }
        
        self.ticketSocketRefreshHistoryId = db.insert(sql, data, cnx)

        return (self.ticketSocketRefreshHistoryId > 0)