from datetime import datetime
from common.models.ticket_socket import *
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
    isActive: bool = True

    def __init__(self, id: int, ticketType: str, price: float):
        super().__init__(id, ticketType, price)

class VipOrder(TicketSocketOrder):
    isActive: bool = True
    totalShirts: int = 0
    revenueUsd: float = 0
    exchangeRate: float = 1.0

    def __init__(self, id: int, title: str):
        super().__init__(id, title)

    def getTotals(self):
        self.getExchangeRate()
        self.totalShirts = len(self.shirts)
        self.revenueUsd = self.revenue * self.exchangeRate
            

class VipEvent(TicketSocketEvent):
    totalRevenue: float = 0
    totalTickets: int = 0
    totalShirts: int = 0
    shirtSales: list[ShirtSales] = []
    isActive: bool = True
    orders: list[VipOrder] = []
    externalUrl: str = ''
    disableLinkButton: bool = False
    disableLinkReason: bool = False
    externalVipLink: str = ''
    disableVipLinkButton: bool = False
    disableVipLinkReason: bool = False
    sellerEventCategoryId: int = None
    isVip: bool = True

    def getTotals(self):
        totalRevenue: float = 0
        totalTickets: int = 0
        totalShirts: int = 0
        shirtd: dict() = {}
        for order in self.orders:
            totalRevenue += order.revenue
            totalTickets += order.numTickets
            if len(order.shirts) > 0:
                totalShirts += len(order.shirts)
                for size in order.shirts:
                    if size in shirtd:
                        shirtd[size] = int(shirtd[size]) + 1
                    else:
                        shirtd[size] = 1

        self.totalRevenue = totalRevenue
        self.totalTickets = totalTickets
        self.totalShirts = totalShirts
        
        shirtSales: list[ShirtSales] = []
        for size in shirtd:
            shirtSale = ShirtSales(size, int(shirtd[size]))
            shirtSales.append(shirtSale)
        self.shirtSales = shirtSales


class Seller:
    thumbnail: str = ''
    hideInList: bool = False
    isActive: bool = True
    created: datetime
    lastUpdated: datetime

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
            self.thumbnail = row['SellerThumbnail']
            self.name = row['Name']
            self.hideInList = bool(row['HideInList'])
            self.isActive = bool(row['Inactive']) != False
            self.created = row['Created']
            self.lastUpdated = row['LastUpdate']
            if self.isActive:
                self.__getSellerEventCategories()

    def __getSellerEventCategories(self):
        sql = """SELECT * 
                 FROM SellerEventCategory
                 WHERE SellerId=%(sellerId)s"""
        data = {
            'sellerId': self.sellerId
        }

        self.sellerEventCategories = []
        rows = db.queryAll(sql, data)
        for row in rows:
            sec = SellerEventCategory(self.sellerId, int(row['TicketSocketId']), int(row['EventCategoryId']), int(row['SellerEventCategoryId']))
            self.sellerEventCategories.append(sec)

    def getSellerEventCategory(self, ticketSocketId: int):
        if len(self.sellerEventCategories) == 0:
            return None
        
        sellerEventCategory = None
        for sec in self.sellerEventCategories:
            if sec.ticketSocketId == ticketSocketId:
                sellerEventCategory = sec
                break

        return sellerEventCategory
