import time
from datetime import datetime, timedelta
import operator
import traceback

from . import utility
from . import db
from common.ticket_socket_service import *
from common.models.national_acts import *
from common.models.ticket_socket import *
from common.user_service import *

class EventService:
    def getEventsAndOrders(self, getOrders: bool = False, sellerId: int = None, start: int = None, end: int = None, showInactive: bool = False, 
                           searchTerm: str = None, tsEventId: int = None, showDeleted: bool = False, excludeStart: int = None, excludeEnd: int = None,
                           excludeExternal: bool = False, showHidden: bool = False, ignoreFlags: bool = False):
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
                    ExternalEvents.EventId AS ExternalEventId, 
                    ExternalEvents.SellerId AS ExternalSellerId, 
                    ExternalEvents.Title AS ExternalTitle, 
                    ExternalEvents.Thumbnail AS ExternalThumbnail, 
                    ExternalEvents.URL AS ExternalUrl, 
                    ExternalEvents.Venue AS ExternalVenue, 
                    ExternalEvents.Address AS ExternalAddress, 
                    ExternalEvents.City AS ExternalCity, 
                    ExternalEvents.State AS ExternalState, 
                    ExternalEvents.Zip AS ExternalZip, 
                    ExternalEvents.Country AS ExternalCountry, 
                    ExternalEvents.DisableLinkButton, 
                    ExternalEvents.DisableLinkReason, 
                    ExternalEvents.ExternalVipLink, 
                    ExternalEvents.DisableVipLinkButton, 
                    ExternalEvents.DisableVipLinkReason,
                    Sellers.Name AS SellerName
                 FROM TicketSocketEvents 
                 JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId 
                 JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId
            LEFT JOIN ExternalEvents ON ExternalEvents.SellerId = Sellers.SellerId AND TicketSocketEvents.EventDate = ExternalEvents.EventDate """
        
        if tsEventId == None:
            if showInactive == True:
                sql += " AND ExternalEvents.IsActive = 0"
            elif ignoreFlags != True:
                sql += " AND ExternalEvents.IsActive = 1"

        sql += " WHERE "
        data = {}

        whereClause: list[str] = []       
        if tsEventId != None:
            whereClause.append("TicketSocketEvents.Id = %(eventId)s")
            data["eventId"] = tsEventId        
        else:
            if ignoreFlags != True:
                if showDeleted != True:
                    whereClause.append("TicketSocketEvents.IsDeleted = 0")
                else:
                    showInactive = True
                    
                if showInactive == True:
                    whereClause.append("TicketSocketEvents.IsActive = 0")
                else:
                    whereClause.append("TicketSocketEvents.IsActive = 1")
                    
                if showHidden != True:
                    whereClause.append("TicketSocketEvents.IsHidden = 0")
            
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
                whereClause.append("TicketSocketEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
                data["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
            elif end != None:
                whereClause.append("TicketSocketEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s")
                data["startDate"] = datetime.now().strftime('%Y-%m-%d')
                data["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
            elif start != None:
                whereClause.append("TicketSocketEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
            elif getOrders == False or sellerId == None:
                whereClause.append("TicketSocketEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.now().strftime('%Y-%m-%d')

            if excludeStart != None and excludeEnd != None:
                whereClause.append("TicketSocketEvents.EventDate NOT BETWEEN %(excludeStart)s AND %(excludeEnd)s")
                data["excludeStart"] = datetime.fromtimestamp(excludeStart).strftime('%Y-%m-%d')
                data["excludeEnd"] = datetime.fromtimestamp(excludeEnd).strftime('%Y-%m-%d')

        if len(whereClause) > 0:
            sql += " AND ".join(whereClause)

        sql += " ORDER BY TicketSocketEvents.EventDate ASC, TicketSocketEvents.Title ASC"       

        sql = sql.replace('\n', '') 
        
        eventRows = db.queryAll(sql, data)
        for row in eventRows:
            eventId = int(row["EventId"])
            ticketSocketEventId = int(row["Id"])
            vipEvent = VipEvent(eventId, str(row["Title"]))
            vipEvent.sellerName = str(row["SellerName"])
            vipEvent.isExternal = False
            vipEvent.ticketSocketEventId = ticketSocketEventId
            vipEvent.sellerEventCategoryId = int(row["SellerEventCategoryId"])
            vipEvent.eventDate = str(row["EventDate"])
            vipEvent.utcTime = int(row["UtcTime"])
            vipEvent.displayDate = str(row["DisplayDate"]) if row["DisplayDate"] != None else None
            vipEvent.thumbnail = str(row["Thumbnail"]) if row["Thumbnail"] != None else None
            vipEvent.ticketSocketUrl = str(row["URL"])
            vipEvent.isAddedToBandsInTown = True if int(row["IsAddedToBandsInTown"]) == 1 else False
            vipEvent.isHidden = True if int(row["IsHidden"]) == 1 else False
            
            venueName = str(row["Venue"]) if row["Venue"] != None else None
            if row["ExternalVenue"] != None:
                venueName = str(row["ExternalVenue"])
            address = str(row["Address"]) if row["Address"] != None else None
            if row["ExternalAddress"] != None:
                address = str(row["ExternalAddress"])
            city = str(row["City"]) if row["City"] != None else None
            if row["ExternalCity"] != None:
                city = str(row["ExternalCity"])
            state = str(row["State"]) if row["State"] != None else None
            if row["ExternalState"] != None:
                state = str(row["ExternalState"])
            zip = str(row["Zip"]) if row["Zip"] != None else None
            if row["ExternalZip"] != None:
                zip = str(row["ExternalZip"])
            vipCountry = str(row["Country"]) if row["Country"] != None else None
            if row["ExternalCountry"] != None:
                vipCountry = str(row["ExternalCountry"])
            
            venue = TicketSocketVenue(venueName, address, '', city, state, zip, vipCountry, '')
            vipEvent.venue = venue
            vipEvent.onSale = True if int(row["OnSale"]) == 1 else False
            vipEvent.isActive = True if int(row["IsActive"]) == 1 else False
            vipEvent.isDeleted = True if int(row["IsDeleted"]) == 1 else False
            if vipEvent.isDeleted == True:
                vipEvent.isActive = False
            vipEvent.isVip = True if int(row["IsVip"]) == 1 else False
            if row["ExternalEventId"] != None and row["ExternalEventId"] != '' and excludeExternal != True:
                vipEvent.externalEventId = int(row["ExternalEventId"])
                vipEvent.externalSellerId = int(row["ExternalSellerId"])
                vipEvent.externalTitle = str(row["ExternalTitle"])
                vipEvent.externalThumbnail = str(row["ExternalThumbnail"])
                vipEvent.externalUrl = str(row["ExternalUrl"])
                externalCountry = str(row["ExternalCountry"]) if row["ExternalCountry"] != None else None
                externalVenue = TicketSocketVenue(str(row["ExternalVenue"]), str(row["ExternalAddress"]), '', str(row["ExternalCity"]), str(row["ExternalState"]), str(row["ExternalZip"]), externalCountry, '')
                vipEvent.externalVenue = externalVenue
                vipEvent.disableLinkButton = str(row["DisableLinkButton"])
                vipEvent.disableLinkReason = str(row["DisableLinkReason"])
                vipEvent.externalVipLink = str(row["ExternalVipLink"])
                vipEvent.disableVipLinkButton = str(row["DisableVipLinkButton"])
                vipEvent.disableVipLinkReason = str(row["DisableVipLinkReason"])

            if getOrders == True:
                ticketTypes = self.__getTicketTypesFromEventId(ticketSocketEventId)
                vipEvent.ticketTypes = ticketTypes
                orders = self.__getOrdersFromEventId(ticketSocketEventId, showInactive, showDeleted, showHidden, ignoreFlags)
                vipEvent.orders = orders
            
            vipEvent.getTotals()
            
            events.append(vipEvent)            

        # if not excluded, get external events without matching TicketSocketEvents
        if excludeExternal != True:
            externalSql = """SELECT ExternalEvents.*, Sellers.Name as SellerName 
                                FROM ExternalEvents 
                                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                                WHERE """
            externalData = {}
            
            externalWhereClause: list[str] = []        
            if showInactive == True:
                externalWhereClause.append("ExternalEvents.IsActive = 0")
            elif ignoreFlags != True:
                externalWhereClause.append("ExternalEvents.IsActive = 1")
            
            if showHidden != True and ignoreFlags != True:
                externalWhereClause.append("ExternalEvents.IsHidden = 0")
                
            if searchTerm != None and len(searchTerm) > 0:
                externalWhereClause.append("""MATCH (ExternalEvents.Title, ExternalEvents.Venue, ExternalEvents.Address, ExternalEvents.City, ExternalEvents.State, ExternalEvents.Country) AGAINST (%(searchTerm)s IN BOOLEAN MODE)""")
                externalData["searchTerm"] = '*' + searchTerm + '*'
            if sellerId != None:
                externalWhereClause.append("ExternalEvents.SellerId = %(sellerId)s")
                externalData["sellerId"] = sellerId
            if start != None and end != None:
                externalWhereClause.append("ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s")
                externalData["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
                externalData["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
            elif end != None:
                externalWhereClause.append("ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s")
                externalData["startDate"] = datetime.now().strftime('%Y-%m-%d')
                externalData["endDate"] = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
            elif start != None:
                externalWhereClause.append("ExternalEvents.EventDate >= %(startDate)s")
                externalData["startDate"] = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
            else:
                externalWhereClause.append("ExternalEvents.EventDate >= %(startDate)s")
                externalData["startDate"] = datetime.now().strftime('%Y-%m-%d')
            
            if len(externalWhereClause) > 0:
                externalSql += " AND ".join(externalWhereClause)
                        
            externalSql += """ AND ExternalEvents.EventId NOT IN (SELECT DISTINCT ExternalEvents.EventId FROM ExternalEvents
                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId 
                JOIN TicketSocketEvents ON TicketSocketEvents.SellerEventCategoryId = SellerEventCategory.SellerEventCategoryId AND ExternalEvents.EventDate = TicketSocketEvents.EventDate) 
                ORDER BY ExternalEvents.EventDate ASC, ExternalEvents.Title ASC"""
        
            externalSql = externalSql.replace('\n', '')
            
            externalEventRows = db.queryAll(externalSql, externalData)
            for row in externalEventRows:
                eventId = int(row["EventId"])
                vipEvent = VipEvent(eventId, str(row["Title"]))
                vipEvent.sellerName = str(row["SellerName"])
                vipEvent.isExternal = True
                vipEvent.eventDate = str(row["EventDate"])
                vipEvent.thumbnail = str(row["Thumbnail"])
                vipEvent.externalUrl = str(row["URL"])
                venue = TicketSocketVenue(str(row["Venue"]), str(row["Address"]), '', str(row["City"]), str(row["State"]), str(row["Zip"]), str(row["Country"]), '')
                vipEvent.venue = venue
                vipEvent.isActive = True if int(row["IsActive"]) == 1 else False
                vipEvent.externalEventId = int(row["EventId"])
                vipEvent.externalSellerId = int(row["SellerId"])
                vipEvent.disableLinkButton = str(row["DisableLinkButton"])
                vipEvent.disableLinkReason = str(row["DisableLinkReason"])
                vipEvent.externalVipLink = str(row["ExternalVipLink"])
                vipEvent.isVip = True if (vipEvent.externalVipLink != None and vipEvent.externalVipLink != "") else False
                vipEvent.disableVipLinkButton = str(row["DisableVipLinkButton"])
                vipEvent.disableVipLinkReason = str(row["DisableVipLinkReason"])
                vipEvent.isAddedToBandsInTown = True if int(row["IsAddedToBandsInTown"]) == 1 else False
                vipEvent.isHidden = True if int(row["IsHidden"]) == 1 else False
                events.append(vipEvent)

        events.sort(key = operator.attrgetter('eventDate', 'title', 'externalEventId'))

        return events

    def getOrders(self, sellerId: int = None, start: int = None, end: int = None, showInactive: bool = False, 
                           showDeleted: bool = False, showHidden: bool = False, ignoreFlags: bool = False):
        orders: list[VipOrder] = []
        
        midnightStart: str = None
        if start != None:
            midnightStart = datetime.fromtimestamp(start).strftime('%Y-%m-%d')
            
        midnightEnd: str = None
        if end != None:
            end_str = datetime.fromtimestamp(end).strftime('%Y-%m-%d')
            midnightEndDate = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)
            midnightEnd = midnightEndDate.strftime('%Y-%m-%d')        
                
        sellerEventCategoryIds: list[int] = []
        if sellerId != None:
            seller = Seller(sellerId)
            sellerEventCategoryIds = seller.getSellerEventCategoryIds()
            # prevent against returning every event in the database
            if len(sellerEventCategoryIds) == 0: 
                return []

        sql = """SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate, ExchangeRates.Symbol, UPPER(ExchangeRates.ServiceTokenId) AS CurrencyAbbrev, TicketSocketOrders.*, 
                    TicketSocketEvents.Title as EventTitle, TicketSocketEvents.EventDate, Sellers.Name AS SellerName, Sellers.SellerId, TicketSocketEvents.Venue, 
                    TicketSocketEvents.Address AS EventAddress, TicketSocketEvents.City AS EventCity, TicketSocketEvents.State AS EventState, 
                    TicketSocketEvents.Zip AS EventZip, TicketSocketEvents.Country AS EventCountry 
                    FROM TicketSocketOrders
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
                    JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId 
                    JOIN TicketSocket ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId
                    JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                    LEFT JOIN ExchangeRateHistory ON ExchangeRateHistory.ExchangeRateId = ExchangeRates.ExchangeRateId 
                        AND ExchangeRateHistory.MidnightDate = TicketSocketOrders.PurchaseDate"""        

        sql += " WHERE "
        data = {}

        whereClause: list[str] = []       
        
        if ignoreFlags != True:
            if showDeleted != True:
                whereClause.append("TicketSocketOrders.IsDeleted = 0")
            else:
                showInactive = True
                
            if showInactive == True:
                whereClause.append("TicketSocketOrders.IsActive = 0")
            else:
                whereClause.append("TicketSocketOrders.IsActive = 1")
                
            if showHidden != True:
                whereClause.append("TicketSocketOrders.IsHidden = 0")
        
        if len(sellerEventCategoryIds) > 0:
            sellerEventCategoryIdStr = db.convertListToParameters(sellerEventCategoryIds, data, 'sellerEventCategoryId')
            whereClause.append("TicketSocketEvents.SellerEventCategoryId IN " + sellerEventCategoryIdStr)
            
        bothDatesSql = """((TicketSocketOrders.PurchaseDate BETWEEN %(startDate)s AND %(endDate)s) OR 
                          (TicketSocketOrders.RefundDate IS NOT NULL AND TicketSocketOrders.RefundDate BETWEEN %(startDate)s AND %(endDate)s) OR
                          (TicketSocketOrders.ChargebackDate IS NOT NULL AND TicketSocketOrders.ChargebackDate BETWEEN %(startDate)s AND %(endDate)s))"""
                          
        startDateSql = """((TicketSocketOrders.PurchaseDate >= %(startDate)s) OR 
                          (TicketSocketOrders.RefundDate IS NOT NULL AND TicketSocketOrders.RefundDate >= %(startDate)s) OR
                          (TicketSocketOrders.ChargebackDate IS NOT NULL AND TicketSocketOrders.ChargebackDate >= %(startDate)s))"""
        
        if midnightStart != None and midnightEnd != None:
            whereClause.append(bothDatesSql)
            data["startDate"] = midnightStart
            data["endDate"] = midnightEnd
        elif end != None:
            whereClause.append(bothDatesSql)
            data["startDate"] = datetime.now().strftime('%Y-%m-%d')
            data["endDate"] = midnightEnd
        elif start != None:
            whereClause.append(startDateSql)
            data["startDate"] = midnightStart
        elif getOrders == False or sellerId == None:
            whereClause.append(startDateSql)
            data["startDate"] = datetime.now().strftime('%Y-%m-%d')

        if len(whereClause) > 0:
            sql += " AND ".join(whereClause)

        sql += " ORDER BY TicketSocketOrders.PurchaseDate ASC, TicketSocketEvents.EventDate ASC, TicketSocketEvents.Title ASC"       

        sql = sql.replace('\n', '') 
        
        orderRows = db.queryAll(sql, data)
        for row in orderRows:
            orderId = int(row["OrderId"])
            eventId = int(row["EventId"])
            ticketSocketOrderId = int(row["Id"])
            order = VipOrder(orderId, eventId)
            order.eventTitle = str(row["EventTitle"])
            order.venue = str(row["Venue"])
            order.eventAddress = str(row["EventAddress"])
            order.eventCity = str(row["EventCity"])
            order.eventState = str(row["EventState"])
            order.eventZip = str(row["EventZip"])
            order.eventCountry = str(row["EventCountry"])
            order.eventDate = str(row["EventDate"])
            order.sellerName = str(row["SellerName"])
            order.sellerId = int(row["SellerId"])
            order.ticketSocketEventId = int(row["TicketSocketEventId"])
            order.ticketSocketOrderId = ticketSocketOrderId
            order.numTickets = int(row["NumTickets"])
            order.purchaseDate = str(row["PurchaseDate"])
            order.purchaseTimestamp = str(row["PurchaseTimestamp"])
            order.userId = int(row["UserId"])
            order.phone = str(row["Phone"]) if row["Phone"] != None else None
            order.email = str(row["Email"]) if row["Email"] != None else None
            order.purchaserLastName = str(row["PurchaserLastName"]) if row["PurchaserLastName"] != None else None
            order.purchaserFirstName = str(row["PurchaserFirstName"]) if row["PurchaserFirstName"] != None else None
            order.purchaserCity = str(row["PurchaserCity"]) if row["PurchaserCity"] != None else None
            order.purchaserState = str(row["PurchaserState"]) if row["PurchaserState"] != None else None
            order.purchaserZipCode = str(row["PurchaserZip"]) if row["PurchaserZip"] != None else None
            order.purchaserCountry = str(row["PurchaserCountry"]) if row["PurchaserCountry"] != None else None
            order.purchaserIpAddress = str(row["PurchaserIpAddress"]) if row["PurchaserIpAddress"] != None else None
            order.revenue = float(row["Revenue"])
            order.serviceFees = float(row["ServiceFees"])
            order.exchangeRate = float(row["ExchangeRate"])
            order.currencyAbbrev = str(row["CurrencyAbbrev"])
            order.currencySymbol = str(row["Symbol"])
            order.isActive = True if int(row["IsActive"]) == 1 else False
            order.isDeleted = True if int(row["IsDeleted"]) == 1 else False
            order.isHidden = True if int(row["IsHidden"]) == 1 else False
            isRefunded: bool = True if int(row["IsRefunded"]) == 1 else False
            order.isRefunded = isRefunded
            order.refundDate = str(row["RefundDate"]) if row["RefundDate"] != None else None
            isChargedBack: bool = True if int(row["IsChargedback"]) == 1 else False
            order.isChargedBack = isChargedBack
            order.chargebackDate = str(row["ChargebackDate"]) if row["ChargebackDate"] != None else None
            
            if isRefunded or isChargedBack:
                order.numTicketsRefunded = int(row["NumTicketsRefunded"])
                order.revenueRefunded = float(row["RevenueRefunded"])
                order.serviceFeeRevenueRefunded = float(row["ServiceFeeRevenueRefunded"])
            else:
                order.numTicketsRefunded = 0
                order.revenueRefunded = 0
                order.serviceFeeRevenueRefunded = 0
            
            if order.isDeleted == True:
                order.isActive = False
            shirtStr = str(row["Shirts"]).strip() if row["Shirts"] != None else None
            shirts = []
            if shirtStr != None and shirtStr != '':
                shirtArray = shirtStr.split("/")
                for shirt in shirtArray:
                    shirts.append(shirt.strip())
            order.shirts = shirts
            attendeeStr = str(row["AttendeeNames"]).strip() if row["AttendeeNames"] != None else None
            attendees = []
            if attendeeStr != None and attendeeStr != '':
                attendeeArray = attendeeStr.split("/")
                for attendee in attendeeArray:
                    attendees.append(attendee.strip())
            attendees.sort()
            order.attendeeNames = attendees
            tickets = self.__getTicketsFromOrderId(ticketSocketOrderId)
            order.tickets = tickets
            order.getTotals()
            orders.append(order)
        return orders

    def getDailyOrderDataFromOrders(self, year: int = 0, sellerId: int = None):
        dailyOrderData: list[DailyOrderData] = []
        month: int = 0
        day: int = 0
        currentYear: int = 0
        
        if year > 0:
            currentYear = year
            month = 12
            day = 31
        else:
            currentYear = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day

        start = datetime.strptime(f'{currentYear}-01-01 00:00:00', '%Y-%m-%d %H:%M:%S').timestamp()
        end = datetime(currentYear, month, day).timestamp()
        
        orders: list[VipOrder] = self.getOrders(start=start, end=end, ignoreFlags=True, sellerId=sellerId)
        
        regularOrders: int = 0
        refundOrders: int = 0
        
        for order in orders:
            if order.isDeleted == True:
                continue
            
            purchaseTimestamp = datetime.strptime(order.purchaseDate, '%Y-%m-%d').timestamp()
            
            orderData: DailyOrderData = None
            foundIndex: int = -1
            
            refundOrderData: DailyOrderData = None
            foundRefundIndex: int = -1
            
            for idx, x in enumerate(dailyOrderData):
                if x.ticketSocketEventId == order.ticketSocketEventId:
                    if (order.isRefunded and x.ticketSocketOrderId == order.ticketSocketOrderId) or (order.isChargedBack and x.ticketSocketOrderId == order.ticketSocketOrderId):
                        refundOrderData = x
                        foundRefundIndex = idx
                    elif x.purchaseDate == order.purchaseDate:
                        orderData = x
                        foundIndex = idx
                        break
                
            if order.isRefunded and order.refundDate != None and refundOrderData == None:
                refundOrderData = DailyOrderData(order.refundDate, order.ticketSocketEventId)
                refundOrderData.ticketSocketOrderId = order.ticketSocketOrderId
                refundOrderData.isRefunded = True
                refundOrderData.isChargeback = False
            elif order.isChargedBack and order.chargebackDate != None and refundOrderData == None:
                refundOrderData = DailyOrderData(order.chargebackDate, order.ticketSocketEventId)
                refundOrderData.ticketSocketOrderId = order.ticketSocketOrderId
                refundOrderData.isRefunded = False
                refundOrderData.isChargeback = True
                
            if orderData == None and (purchaseTimestamp >= start and purchaseTimestamp <= end):
                orderData = DailyOrderData(order.purchaseDate, order.ticketSocketEventId)
                orderData.ticketSocketOrderId = None
                orderData.isRefunded = False
                orderData.isChargeback = False
            
            if refundOrderData != None:
                refundOrderData.numTicketsRefunded += order.numTicketsRefunded
                refundOrderData.revenueRefunded += order.revenueRefunded
                refundOrderData.serviceFeeRevenueRefunded += order.serviceFeeRevenueRefunded 
                
            if orderData != None:
                orderData.orders += 1
                orderData.tickets += order.numTickets
                orderData.ticketRevenueUsd += order.revenueUsd
                orderData.serviceFeesRevenueUsd += order.serviceFeesUsd
                orderData.totalRevenueUsd += (order.revenueUsd + order.serviceFeesUsd)
            
            if orderData != None:
                regularOrders += 1
                if foundIndex >= 0:
                    dailyOrderData[foundIndex] = orderData
                else:
                    dailyOrderData.append(orderData)
                
            if refundOrderData != None:
                refundOrders += 1
                if foundRefundIndex >= 0:
                    dailyOrderData[foundRefundIndex] = refundOrderData
                else:
                    dailyOrderData.append(refundOrderData)
        
        return dailyOrderData
     
    def updateDailyOrderData(self, history: TicketSocketRefreshHistory, year: int = 0, sellerId: int = None):
        utility.logMessage('Starting update of daily order data')
        timer: float = time.time()
        duration: float = 0
        dailyOrderData = self.getDailyOrderDataFromOrders(year, sellerId)
        duration = time.time() - timer
        utility.logMessage(f'Daily order data fetch completed in {duration} seconds')
        
        history.orderDataRowsTotal = len(dailyOrderData)
        
        if len(dailyOrderData) <= 0:
            history.orderDataUpdateSucceeded = False
            return history
        
        utility.logMessage(f'Daily order data - starting database update')

        success = True       
        updates: int = 0
        inserts: int = 0 
        for orderData in dailyOrderData:
            sql = """SELECT DailyOrderDataId FROM DailyOrderData WHERE TicketSocketEventId=%(ticketSocketEventId)s AND PurchaseDate=DATE(%(purchaseDate)s)"""
            data = {
                'ticketSocketEventId': orderData.ticketSocketEventId,
                'purchaseDate': orderData.purchaseDate
            }
            
            if orderData.ticketSocketOrderId != None:
                sql += """ AND TicketSocketOrderId=%(ticketSocketOrderId)s"""
                data["ticketSocketOrderId"] = orderData.ticketSocketOrderId  
            else:
                sql += """ AND TicketSocketOrderId IS NULL"""              
            
            existingData = db.queryOne(sql, data)
            
            updateData = {
                'purchaseDate': orderData.purchaseDate,
                'ticketSocketEventId': orderData.ticketSocketEventId,
                'orders': orderData.orders,
                'tickets': orderData.tickets,
                'ticketRevenue': orderData.ticketRevenueUsd,
                'serviceFeeRevenue': orderData.serviceFeesRevenueUsd, 
                'totalRevenue': orderData.totalRevenueUsd,
                'isRefunded': 1 if orderData.isRefunded == True else 0,
                'isChargeback': 1 if orderData.isChargeback == True else 0,
                'numTicketsRefunded': orderData.numTicketsRefunded,
                'revenueRefunded': orderData.revenueRefunded,
                'serviceFeeRevenueRefunded': orderData.serviceFeeRevenueRefunded,
                'ticketSocketOrderId': orderData.ticketSocketOrderId
            }
                
            if existingData != {}:
                dailyOrderDataId = int(existingData["DailyOrderDataId"])
                updateSql = """UPDATE DailyOrderData SET Orders=%(orders)s, Tickets=%(tickets)s, TicketRevenue=%(ticketRevenue)s, 
                                ServiceFeeRevenue=%(serviceFeeRevenue)s, TotalRevenue=%(totalRevenue)s, IsRefunded=%(isRefunded)s, 
                                IsChargeback=%(isChargeback)s, NumTicketsRefunded=%(numTicketsRefunded)s, RevenueRefunded=%(revenueRefunded)s, 
                                ServiceFeeRevenueRefunded=%(serviceFeeRevenueRefunded)s, TicketSocketOrderId=%(ticketSocketOrderId)s, 
                                LastUpdate=CURRENT_TIMESTAMP WHERE DailyOrderDataId=%(dailyOrderDataId)s"""
                updateData["dailyOrderDataId"] = dailyOrderDataId
                success = db.update(updateSql, updateData)
                if success:
                    updates += 1
            else:
                insertSql = """INSERT INTO DailyOrderData (PurchaseDate, TicketSocketEventId, Orders, Tickets, TicketRevenue, ServiceFeeRevenue, 
                                    TotalRevenue, IsRefunded, IsChargeback, NumTicketsRefunded, RevenueRefunded, ServiceFeeRevenueRefunded, 
                                    TicketSocketOrderId) VALUES (%(purchaseDate)s, %(ticketSocketEventId)s, %(orders)s, %(tickets)s, %(ticketRevenue)s, 
                                    %(serviceFeeRevenue)s, %(totalRevenue)s, %(isRefunded)s, %(isChargeback)s, %(numTicketsRefunded)s, %(revenueRefunded)s, 
                                    %(serviceFeeRevenueRefunded)s, %(ticketSocketOrderId)s )"""
                
                id = db.insert(insertSql, updateData)
                success = (id > 0)
                if success:
                    inserts += 1
            if success != True:
                break
        
        duration = time.time() - timer
        history.setOrderUpdateSuccess(success, duration, inserts, updates)  
            
        utility.logMessage(f'Daily order data - update complete in {duration} seconds')
        
        return history
    
    def getDashboardData(self, year: int = 0):
        dailyOrderData: list[DailyOrderData] = []
        month: int = 0
        day: int = 0
        currentYear: int = 0
        now = None
        
        if year > 0:
            currentYear = year
            month = 12
            day = 31
        else:
            currentYear = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day

        now = datetime(currentYear, month, day) + timedelta(days=1)         
        dashTotals = DashboardTotals(currentYear, month, day)
        
        start = f'{currentYear}-01-01 00:00:00'
        end = now.strftime('%Y-%m-%d %H:%M:%S')
        
        sql = """SELECT DailyOrderData.*, TicketSocketEvents.Title AS EventTitle, TicketSocketEvents.EventDate, TicketSocketEvents.Venue, 
                    TicketSocketEvents.City, TicketSocketEvents.State, TicketSocketEvents.Country, TicketSocketEvents.Zip, 
                    Sellers.Name AS SellerName, Sellers.SellerId, TicketSocket.TicketSocketId, TicketSocket.AccountName 
                    FROM DailyOrderData 
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = DailyOrderData.TicketSocketEventId 
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId 
                    JOIN TicketSocket ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId 
                    JOIN Sellers on Sellers.SellerId = SellerEventCategory.SellerId 
                 WHERE DailyOrderData.PurchaseDate BETWEEN %(start)s and %(end)s 
                    ORDER BY DailyOrderData.PurchaseDate, Sellers.Name"""
        data = {
            'start': start,
            'end': end
        }
        
        rows = db.queryAll(sql, data)
        for row in rows:
            purchaseDate = str(row["PurchaseDate"])
            ticketSocketEventId = int(row["TicketSocketEventId"])
            orderData = DailyOrderData(purchaseDate, ticketSocketEventId)
            orderData.eventTitle = str(row["EventTitle"])
            orderData.eventDate = str(row["EventDate"])            
            orderData.sellerId = int(row["SellerId"])
            orderData.sellerName = str(row["SellerName"])
            orderData.venue = str(row["Venue"])
            orderData.city = str(row["City"])
            orderData.state = str(row["State"])
            orderData.country = str(row["Country"])
            orderData.zip = str(row["Zip"])
            orderData.tickets = int(row["Tickets"])
            orderData.orders = int(row["Orders"])
            orderData.ticketRevenueUsd = float(row["TicketRevenue"])
            orderData.serviceFeesRevenueUsd = float(row["ServiceFeeRevenue"])
            orderData.totalRevenueUsd = float(row["TotalRevenue"])
            orderData.ticketSocketId = int(row["TicketSocketId"])
            orderData.ticketSocketOrderId = int(row["TicketSocketOrderId"]) if row["TicketSocketOrderId"] != None else None
            orderData.isRefunded = True if int(row["IsRefunded"]) == 1 else False
            orderData.isChargeback = True if int(row["IsChargeback"]) == 1 else False
            orderData.numTicketsRefunded = int(row["NumTicketsRefunded"])
            orderData.revenueRefunded = float(row["RevenueRefunded"])
            orderData.serviceFeeRevenueRefunded = float(row["ServiceFeeRevenueRefunded"])

            dashTotals.tickets += orderData.tickets
            dashTotals.orders += orderData.orders
            dashTotals.numTicketsRefunded += orderData.numTicketsRefunded
            dashTotals.revenueRefunded += orderData.revenueRefunded
            dashTotals.serviceFeeRevenueRefunded += orderData.serviceFeeRevenueRefunded
            dashTotals.ticketRevenueUsd += orderData.ticketRevenueUsd
            dashTotals.serviceFeesRevenueUsd += orderData.serviceFeesRevenueUsd
            dashTotals.totalRevenueUsd += orderData.totalRevenueUsd    
            
            dailyOrderData.append(orderData)
        
        dashTotals.dailyOrderData = dailyOrderData
        dashTotals.pricePerTicket = (dashTotals.ticketRevenueUsd - dashTotals.revenueRefunded) / dashTotals.tickets
        dashTotals.serviceFeePerTicket = (dashTotals.serviceFeesRevenueUsd - dashTotals.serviceFeeRevenueRefunded) / dashTotals.tickets
        return dashTotals

    def __getTicketTypesFromEventId(self, ticketSocketEventId: int):
        ticketTypes: list[TicketSocketTicketType] = []
        
        sql = """SELECT TicketSocketTicketTypes.* 
                    FROM TicketSocketTicketTypes
                    WHERE TicketSocketTicketTypes.TicketSocketEventId=%(ticketSocketEventId)s 
                    ORDER BY TicketSocketTicketTypes.TicketTypeName"""
        data = {
            'ticketSocketEventId': ticketSocketEventId
        }           
        
        rows = db.queryAll(sql, data)
        for row in rows:
            id = int(row["TicketSocketTicketTypeId"])
            name = str(row["TicketTypeName"])
            total = int(row["TotalAvailable"])
            isActive: bool = (int(row["IsActive"]) == 1)
            ticketType = TicketSocketTicketType(ticketSocketEventId, id, name, total, isActive)
            ticketTypes.append(ticketType)
        
        return ticketTypes

    def __getOrdersFromEventId(self, ticketSocketEventId: int, showInactive: bool = False, showDeleted: bool = False, showHidden: bool = False, ignoreFlags: bool = False):
        orders: list[VipOrder] = []
        sql = """SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate, ExchangeRates.Symbol, UPPER(ExchangeRates.ServiceTokenId) AS CurrencyAbbrev, TicketSocketOrders.*, 
                    TicketSocketEvents.Title as EventTitle, TicketSocketEvents.EventDate, Sellers.Name AS SellerName, Sellers.SellerId, TicketSocketEvents.Venue, 
                    TicketSocketEvents.Address AS EventAddress, TicketSocketEvents.City AS EventCity, TicketSocketEvents.State AS EventState, 
                    TicketSocketEvents.Zip AS EventZip, TicketSocketEvents.Country AS EventCountry 
                    FROM TicketSocketOrders
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId 
                    JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId 
                    JOIN TicketSocket ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId
                    JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                    LEFT JOIN ExchangeRateHistory ON ExchangeRateHistory.ExchangeRateId = ExchangeRates.ExchangeRateId 
                        AND ExchangeRateHistory.MidnightDate = TicketSocketOrders.PurchaseDate WHERE TicketSocketOrders.TicketSocketEventId=%(ticketSocketEventId)s"""
        data = {
            'ticketSocketEventId': ticketSocketEventId
        }

        if showDeleted != True and ignoreFlags != True:
            sql += """ AND TicketSocketOrders.IsDeleted = 0"""
            
        if showHidden != True and ignoreFlags != True:
            sql += """ AND TicketSocketOrders.IsHidden = 0"""
            
        if showInactive != True and ignoreFlags != True:
            sql += """ AND TicketSocketOrders.IsActive = 1"""
            
            
        sql += " ORDER BY TicketSocketOrders.PurchaserLastName ASC, TicketSocketOrders.PurchaserFirstName ASC"

        rows = db.queryAll(sql, data)
        for row in rows:
            orderId = int(row["OrderId"])
            eventId = int(row["EventId"])
            ticketSocketOrderId = int(row["Id"])
            order = VipOrder(orderId, eventId)
            order.venue = str(row["Venue"])
            order.eventTitle = str(row["EventTitle"])
            order.eventAddress = str(row["EventAddress"])
            order.eventCity = str(row["EventCity"])
            order.eventState = str(row["EventState"])
            order.eventZip = str(row["EventZip"])
            order.eventCountry = str(row["EventCountry"])
            order.eventDate = str(row["EventDate"])
            order.sellerName = str(row["SellerName"])
            order.sellerId = int(row["SellerId"])
            order.ticketSocketEventId = ticketSocketEventId
            order.ticketSocketOrderId = ticketSocketOrderId
            order.numTickets = int(row["NumTickets"])
            order.purchaseDate = str(row["PurchaseDate"])
            order.purchaseTimestamp = str(row["PurchaseTimestamp"])
            order.userId = int(row["UserId"])
            order.phone = str(row["Phone"]) if row["Phone"] != None else None
            order.email = str(row["Email"]) if row["Email"] != None else None
            order.purchaserLastName = str(row["PurchaserLastName"]) if row["PurchaserLastName"] != None else None
            order.purchaserFirstName = str(row["PurchaserFirstName"]) if row["PurchaserFirstName"] != None else None
            order.purchaserCity = str(row["PurchaserCity"]) if row["PurchaserCity"] != None else None
            order.purchaserState = str(row["PurchaserState"]) if row["PurchaserState"] != None else None
            order.purchaserZipCode = str(row["PurchaserZip"]) if row["PurchaserZip"] != None else None
            order.purchaserCountry = str(row["PurchaserCountry"]) if row["PurchaserCountry"] != None else None
            order.purchaserIpAddress = str(row["PurchaserIpAddress"]) if row["PurchaserIpAddress"] != None else None
            order.revenue = float(row["Revenue"])
            order.serviceFees = float(row["ServiceFees"])
            order.exchangeRate = float(row["ExchangeRate"])
            order.currencyAbbrev = str(row["CurrencyAbbrev"])
            order.currencySymbol = str(row["Symbol"])
            order.isActive = True if int(row["IsActive"]) == 1 else False
            order.isDeleted = True if int(row["IsDeleted"]) == 1 else False
            order.isHidden = True if int(row["IsHidden"]) == 1 else False
            order.isRefunded = True if int(row["IsRefunded"]) == 1 else False
            order.refundDate = str(row["RefundDate"]) if row["RefundDate"] != None else None
            order.isChargedBack = True if int(row["IsChargedback"]) == 1 else False
            order.chargebackDate = str(row["ChargebackDate"]) if row["ChargebackDate"] != None else None
            
            if order.isRefunded or order.isChargedBack:
                order.numTicketsRefunded = int(row["NumTicketsRefunded"])
                order.revenueRefunded = float(row["RevenueRefunded"])
                order.serviceFeeRevenueRefunded = float(row["ServiceFeeRevenueRefunded"])
            else:
                order.numTicketsRefunded = 0
                order.revenueRefunded = 0
                order.serviceFeeRevenueRefunded = 0
            
            if order.isDeleted == True:
                order.isActive = False
            shirtStr = str(row["Shirts"]).strip() if row["Shirts"] != None else None
            shirts = []
            if shirtStr != None and shirtStr != '':
                shirtArray = shirtStr.split("/")
                for shirt in shirtArray:
                    shirts.append(shirt.strip())
            order.shirts = shirts
            attendeeStr = str(row["AttendeeNames"]).strip() if row["AttendeeNames"] != None else None
            attendees = []
            if attendeeStr != None and attendeeStr != '':
                attendeeArray = attendeeStr.split("/")
                for attendee in attendeeArray:
                    attendees.append(attendee.strip())
            attendees.sort()
            order.attendeeNames = attendees
            tickets = self.__getTicketsFromOrderId(ticketSocketOrderId)
            order.tickets = tickets
            order.getTotals()
            orders.append(order)
        return orders

    def __getTicketsFromOrderId(self, ticketSocketOrderId: int):
        tickets: list[VipTicket] = []
        sql = """SELECT * FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=%(ticketSocketOrderId)s AND IsActive=1"""
        data = {
            'ticketSocketOrderId': ticketSocketOrderId
        }

        rows = db.queryAll(sql, data)
        for row in rows:
            ticketId: int = 0
            if row["TicketId"] != None and row["TicketId"] != '':
                ticketId = int(row["TicketId"])
            ticket = VipTicket(ticketId, str(row["TicketType"]), float(row["Price"]), float(row["ServiceFee"]), int(row["TicketSocketTicketTypeId"]), str(row["BarCode"]), int(row["AvailableScans"]), str(row["PurchaseLocation"]), int(row["ScannedTimestamp"]))
            ticket.ticketSocketOrderId = ticketSocketOrderId
            ticket.ticketSocketOrderTicketId = int(row["Id"])
            ticket.isActive = True if int(row["IsActive"]) == 1 else False
            ticket.isCheckedIn = True if int(row["IsCheckedIn"]) == 1 else False
            tickets.append(ticket)
        return tickets
    
    def disableEvent(self, ticketSocketEventId: int, disabled: bool):
        sql = """UPDATE TicketSocketEvents SET IsActive=%(isActive)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketEventId)s"""
        data = {
            'ticketSocketEventId': ticketSocketEventId,
            'isActive': 0 if disabled == True else 1
        }
        return db.update(sql, data)
    
    def deleteEvent(self, ticketSocketEventId: int, deleted: bool):
        sql = """UPDATE TicketSocketEvents SET IsDeleted=%(isDeleted)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketEventId)s"""
        data = {
            'ticketSocketEventId': ticketSocketEventId,
            'isDeleted': 1 if deleted == True else 0
        }
        return db.update(sql, data)
    
    def disableOrder(self, ticketSocketOrderId: int, disabled: bool):
        sql = """UPDATE TicketSocketOrders SET IsActive=%(isActive)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketOrderId)s"""
        data = {
            'ticketSocketOrderId': ticketSocketOrderId,
            'isActive': 0 if disabled == True else 1
        }
        return db.update(sql, data)
    
    def deleteOrder(self, ticketSocketOrderId: int, deleted: bool):
        sql = """UPDATE TicketSocketOrders SET IsDeleted=%(isDeleted)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketOrderId)s"""
        data = {
            'ticketSocketOrderId': ticketSocketOrderId,
            'isDeleted': 1 if deleted == True else 0
        }
        return db.update(sql, data)
    
    def hideEvent(self, ticketSocketEventId: int, hidden: bool):
        sql = """UPDATE TicketSocketEvents SET IsHidden=%(isHidden)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketEventId)s"""
        data = {
            'ticketSocketEventId': ticketSocketEventId,
            'isHidden': 1 if hidden == True else 0
        }
        return db.update(sql, data)
    
    def hideOrder(self, ticketSocketOrderId: int, hidden: bool):
        sql = """UPDATE TicketSocketOrders SET IsHidden=%(isHidden)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketOrderId)s"""
        data = {
            'ticketSocketOrderId': ticketSocketOrderId,
            'isHidden': 1 if hidden == True else 0
        }
        return db.update(sql, data)
    
    def checkInTicket(self, ticketSocketOrderTicketId: int, checkedIn: bool):
        sql = """UPDATE TicketSocketOrderTickets SET IsCheckedIn=%(checkedIn)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketSocketOrderTicketId)s"""
        data = {
            'ticketSocketOrderTicketId': ticketSocketOrderTicketId,
            'checkedIn': 1 if checkedIn == True else 0
        }
        return db.update(sql, data)
    
    def updateEvent(self, eventToUpdate: VipEvent):
        success: bool = True
        if eventToUpdate == None or eventToUpdate.ticketSocketEventId <= 0:
            return False
        
        ticketSocketEventId: int = eventToUpdate.ticketSocketEventId
        sql = """SELECT * FROM TicketSocketEvents WHERE Id=%(ticketSocketEventId)s"""
        data = {
            'ticketSocketEventId': ticketSocketEventId
        }
        existingEvent: VipEvent = db.queryOne(sql, data)
        
        if existingEvent != None:
            updateSql = """UPDATE TicketSocketEvents 
                            SET IsActive=%(isActive)s, 
                            IsDeleted=%(isDeleted)s, 
                            IsAddedToBandsInTown=%(isAddedToBandsInTown)s, 
                            IsHidden=%(isHidden)s, 
                            LastUpdate=CURRENT_TIMESTAMP 
                            WHERE Id=%(ticketSocketEventId)s"""
            updateData = {
                'ticketSocketEventId': ticketSocketEventId,
                'isActive': 1 if eventToUpdate.isActive == True else 0,
                'isDeleted': 1 if eventToUpdate.isDeleted else 0,
                'isAddedToBandsInTown': 1 if eventToUpdate.isAddedToBandsInTown else 0,
                'isHidden': 1 if eventToUpdate.isHidden else 0
            }
            success = db.update(updateSql, updateData)
        return success   
    
    def updateOrder(self, orderToUpdate: VipOrder):
        success: bool = True
        if orderToUpdate == None or orderToUpdate.ticketSocketOrderId <= 0:
            return False
        
        ticketSocketOrderId: int = orderToUpdate.ticketSocketOrderId
        sql = """SELECT * FROM TicketSocketOrders WHERE Id=%(ticketSocketOrderId)s"""
        data = {
            'ticketSocketOrderId': ticketSocketOrderId
        }
        existingOrder: VipOrder = db.queryOne(sql, data)
        
        if existingOrder != None:
            updateSql = """UPDATE TicketSocketOrders 
                            SET IsActive=%(isActive)s, 
                            IsDeleted=%(isDeleted)s, 
                            IsHidden=%(isHidden)s, 
                            LastUpdate=CURRENT_TIMESTAMP 
                            WHERE Id=%(ticketSocketOrderId)s"""
            updateData = {
                'ticketSocketOrderId': ticketSocketOrderId,
                'isActive': 1 if orderToUpdate.isActive else 0,
                'isDeleted': 1 if orderToUpdate.isDeleted else 0,
                'isHidden': 1 if orderToUpdate.isHidden else 0
            }
            success = db.update(updateSql, updateData)
        return success      
    
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
        #utility.logMessage('starting TS update')
        updateSuccess: bool = True
        errorMessage: str = None
        
        # initialize counters
        startTimer: float = time.time()
        endTimer: float = 0
        duration: float = 0

        serviceEventsSkipped: list[str] = []
        eventsFailed: list[int] = []
        ordersFailed: list[int] = []
        ticketTypesFailed: list[int] = []
        ticketsFailed: list[int] = []    
        totalEventsFromService: int = 0
        eventsUpdated: int = 0
        eventsInserted: int = 0
        ordersInserted: int = 0
        ordersUpdated: int = 0
        ordersDeleted: int = 0
        ticketsUpdated: int = 0
        ticketsInserted: int = 0
        ticketTypesUpdated: int = 0
        ticketTypesInserted: int = 0
        dailyOrderDataRowsRemoved: int = 0
        results: TicketSocketRefreshHistory = None

        try:
            utility.logMessage('retrieving events from TicketSocket Service')
            allEvents = self.retrieveTicketSocketEventsForUpdate(sellerId, start, end)
            #utility.logMessage('events retrieved')
            
            serviceTimer = time.time()
            serviceDuration = serviceTimer - startTimer
            utility.logMessage('Service fetch done in ' + str(serviceDuration) + ' seconds')

            # get total number of events grabbed from service
            totalEventsFromService = len(allEvents)        
            
            utility.logMessage('starting database update - opening connection')
            # get one database connection
            cnx = db.getDbConnection()

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
                        'country': evt.venue.country.strip() if evt.venue.country != None else None,
                        'onsale': 1 if evt.onSale else 0,
                        'thumbnail': evt.thumbnail.strip() if evt.thumbnail != None else None,
                        'displayDate': evt.displayDate.strip() if evt.displayDate != None else None,
                        'isVip': 1 if evt.isVip else 0
                    }

                    # determine if event already exists
                    eventSql = "SELECT * FROM TicketSocketEvents WHERE EventId=%(eventId)s AND SellerEventCategoryId=%(sellerEventCategoryId)s"

                    data = {
                        'eventId': evt.id,
                        'sellerEventCategoryId': evt.sellerEventCategoryId
                    }

                    existingEvent = db.queryOne(eventSql, data, cnx)

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
                                Thumbnail=%(thumbnail)s, DisplayDate=%(displayDate)s, IsVip=%(isVip)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                        eventSuccess = db.update(sql, eventData, cnx)
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
                        ticketSocketEventId = db.insert(sql, eventData, cnx)
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
                        updateSuccess = False
                        continue
                    
                    if ticketSocketEventId and len(evt.ticketTypes) > 0:
                        eventTicketTypes: list[int] = []
                        for ticketType in evt.ticketTypes:
                            eventTicketTypes.append(ticketType.ticketTypeId)
                            
                            ticketTypeData = {
                                'ticketSocketTicketTypeId': ticketType.ticketTypeId,
                                'ticketSocketEventId': ticketSocketEventId,
                                'ticketTypeName': ticketType.ticketTypeName,
                                'totalAvailable': ticketType.totalAvailable,
                                'isActive': 1 if ticketType.isActive else 0
                            }
                            
                            ticketTypeSql = """SELECT * FROM TicketSocketTicketTypes WHERE TicketSocketEventId=%(ticketSocketEventId)s AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                            ticketTypeSqlData = {
                                'ticketSocketTicketTypeId': ticketType.ticketTypeId,
                                'ticketSocketEventId': ticketSocketEventId
                            }
                            
                            existingTicketType = db.queryOne(ticketTypeSql, ticketTypeSqlData, cnx)
                            
                            ticketTypeSuccess: bool = False
                            ticketSocketTypeId: int = 0
                            ticketTypeAddNew: bool = False
                            
                            if existingTicketType != {}:
                                #update existing ticket type
                                sql = """UPDATE TicketSocketTicketTypes SET TicketTypeName=%(ticketTypeName)s, TotalAvailable=%(totalAvailable)s, IsActive=%(isActive)s, 
                                            LastUpdate=CURRENT_TIMESTAMP 
                                            WHERE TicketSocketEventId=%(ticketSocketEventId)s AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                                ticketTypeSuccess = db.update(sql, ticketTypeData, cnx)
                            else:
                                ticketTypeAddNew = True
                                #insert new ticket type
                                sql = """INSERT INTO TicketSocketTicketTypes (TicketSocketTicketTypeId, TicketSocketEventId, TicketTypeName, TotalAvailable, IsActive)  
                                                VALUES (%(ticketSocketTicketTypeId)s, %(ticketSocketEventId)s, %(ticketTypeName)s, %(totalAvailable)s, %(isActive)s)"""
                                ticketSocketTypeId = db.insert(sql, ticketTypeData, cnx)
                                ticketTypeSuccess = (ticketSocketTypeId > 0)
                                
                            # if the update succeeded, update counters
                            if ticketTypeSuccess:
                                if ticketTypeAddNew:
                                    ticketTypesInserted += 1
                                else:
                                    ticketTypesUpdated += 1
                            else:
                                # if that failed, mark it
                                ticketTypesFailed.append(ticketType.ticketTypeId)
                                
                    if ticketSocketEventId and len(evt.orders) > 0:
                        eventOrders: list[int] = []
                        for order in evt.orders:
                            if order.eventId != evt.id:
                                continue
                            eventOrders.append(order.id)
                            # compile order data for update
                            shirts: str = None
                            if len(order.shirts) > 0:
                                shirts = " / ".join(order.shirts)
                            attendeeNames: str = None
                            if len(order.attendeeNames) > 0:
                                attendeeNames = " / ".join(order.attendeeNames)

                            orderData = {
                                'numTickets': order.numTickets,
                                'purchaseDate': order.purchaseDate.strip(),
                                'purchaseTimestamp': order.purchaseTimestamp.strip(),
                                'phone': order.phone.strip() if order.phone != None else None,
                                'shirts': shirts,
                                'attendeeNames': attendeeNames,
                                'userId': order.userId,
                                'eventId': order.eventId,
                                'purchaserLastName': order.purchaserLastName.strip() if order.purchaserLastName != None else None,
                                'purchaserFirstName': order.purchaserFirstName.strip() if order.purchaserFirstName != None else None,
                                'purchaserCity': order.purchaserCity.strip() if (order.purchaserCity != None and order.purchaserCity != '') else None,
                                'purchaserState': order.purchaserState.strip() if (order.purchaserState != None and order.purchaserState != '') else None,
                                'purchaserZip': order.purchaserZipCode.strip() if (order.purchaserZipCode != None and order.purchaserZipCode != '') else None,
                                'purchaserCountry': order.purchaserCountry.strip() if (order.purchaserCountry != None and order.purchaserCountry != '') else None,
                                'purchaserIpAddress': order.purchaserIpAddress.strip() if (order.purchaserIpAddress != None and order.purchaserIpAddress != '') else None,
                                'email': order.email.strip() if order.email != None else None
                            }
                            
                            if order.revenue > 0:
                                orderData['revenue'] = order.revenue
                                
                            if order.serviceFees > 0:
                                orderData['serviceFees'] = order.serviceFees

                            # determine if order already exists
                            orderSql = "SELECT * FROM TicketSocketOrders WHERE TicketSocketEventId=%(ticketSocketEventId)s AND OrderId=%(orderId)s"

                            data = {
                                'ticketSocketEventId': ticketSocketEventId,
                                'orderId': order.id
                            }

                            existingOrder = db.queryOne(orderSql, data, cnx)

                            orderSuccess: bool = False
                            ticketSocketOrderId: int = 0
                            orderAddNew: bool = False

                            if existingOrder != {}:
                                ticketSocketOrderId = int(existingOrder['Id'])
                                orderData['id'] = ticketSocketOrderId
                                # if purchase date changed, clear out daily order data for event
                                orderPurchaseTimestamp = datetime.strptime(order.purchaseDate, '%Y-%m-%d').timestamp()
                                existingPurchaseTimestamp = datetime.strptime(str(existingOrder['PurchaseDate']), '%Y-%m-%d').timestamp()
                                if orderPurchaseTimestamp != existingPurchaseTimestamp:
                                    checkCleanupData = {
                                        'ticketSocketEventId': ticketSocketEventId, 
                                        'purchaseDate': str(existingOrder['PurchaseDate'])
                                    }
                                    checkCleanupSql = """SELECT DailyOrderDataId FROM DailyOrderData WHERE TicketSocketEventId=%(ticketSocketEventId)s AND PurchaseDate=DATE(%(purchaseDate)s)"""
                                    rows = db.queryAll(checkCleanupSql, checkCleanupData)
                                    if len(rows) > 0:
                                        for row in rows:
                                            cleanupSql = """DELETE FROM DailyOrderData WHERE DailyOrderDataId=%(dailyOrderDataId)s"""
                                            cleanupData = {
                                                'dailyOrderDataId': int(row["DailyOrderDataId"])
                                            }
                                            delSuccess = db.delete(cleanupSql, cleanupData)
                                            if delSuccess == True:
                                                dailyOrderDataRowsRemoved += 1
                                
                                #update existing order
                                sql = """UPDATE TicketSocketOrders SET NumTickets=%(numTickets)s, PurchaseDate=%(purchaseDate)s, PurchaseTimestamp=%(purchaseTimestamp)s, 
                                        Phone=%(phone)s, Shirts=%(shirts)s, AttendeeNames=%(attendeeNames)s, EventId=%(eventId)s, UserId=%(userId)s, 
                                        PurchaserLastName=%(purchaserLastName)s, PurchaserFirstName=%(purchaserFirstName)s, PurchaserCity=%(purchaserCity)s, 
                                        PurchaserState=%(purchaserState)s, PurchaserZip=%(purchaserZip)s, PurchaserCountry=%(purchaserCountry)s, PurchaserIpAddress=%(purchaserIpAddress)s, 
                                        Email=%(email)s, """
                                if order.revenue > 0:
                                    sql += """Revenue=%(revenue)s, """
                                if order.serviceFees > 0:
                                    sql += """ServiceFees=%(serviceFees)s, """                                        
                                sql += """LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                
                                orderSuccess = db.update(sql, orderData, cnx)
                            else:
                                orderAddNew = True
                                #insert new order
                                orderData['orderId'] = int(order.id)
                                orderData['ticketSocketEventId'] = ticketSocketEventId
                                sql = """INSERT INTO TicketSocketOrders (TicketSocketEventId, OrderId, NumTickets, PurchaseDate, PurchaseTimestamp, Phone, Shirts, 
                                                AttendeeNames, EventId, UserId, PurchaserLastName, PurchaserFirstName, PurchaserCity, PurchaserState, PurchaserZip, PurchaserCountry, 
                                                PurchaserIpAddress, Email"""
                                if order.revenue > 0:
                                    sql += """, Revenue"""
                                if order.serviceFees > 0:
                                    sql += """, ServiceFees"""
                                sql += """) VALUES (%(ticketSocketEventId)s, %(orderId)s, %(numTickets)s, %(purchaseDate)s, %(purchaseTimestamp)s, %(phone)s, %(shirts)s, 
                                               %(attendeeNames)s, %(eventId)s, %(userId)s, %(purchaserLastName)s, %(purchaserFirstName)s, %(purchaserCity)s, %(purchaserState)s, 
                                                %(purchaserZip)s, %(purchaserCountry)s, %(purchaserIpAddress)s,  %(email)s"""
                                if order.revenue > 0:
                                    sql +=""", %(revenue)s"""
                                if order.serviceFees > 0:
                                    sql += """, %(serviceFees)s"""
                                sql += """)"""
                                
                                ticketSocketOrderId = db.insert(sql, orderData, cnx)
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
                                updateSuccess = False
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
                                        'ticketType': ticket.ticketType.strip(),
                                        'serviceFee': ticket.serviceFee if ticket.serviceFee != None else 0,
                                        'availableScans': ticket.availableScans,
                                        'barcode': ticket.barcode,
                                        'purchaseLocation': ticket.purchaseLocation,
                                        'scannedTimestamp': ticket.scannedTimestamp
                                    }

                                    ticketPrice = ticket.price if ticket.price != None else 0
                                    
                                    if ticketPrice > 0:
                                        ticketData['price'] = ticketPrice
                                     
                                    # determine if ticket already exists
                                    ticketSql = "SELECT * FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=%(ticketSocketOrderId)s AND TicketId=%(ticketId)s"

                                    data = {
                                        'ticketSocketOrderId': ticketSocketOrderId,
                                        'ticketId': ticket.id
                                    }

                                    existingTicket = db.queryOne(ticketSql, data, cnx)

                                    ticketSuccess: bool = False
                                    ticketSocketOrderTicketId: int = 0
                                    ticketAddNew: bool = False
                                    
                                    if existingTicket != {}:
                                        #update existing ticket
                                        ticketSocketOrderTicketId = int(existingTicket['Id'])
                                        isCheckedIn = int(existingTicket['IsCheckedIn'])
                                        if isCheckedIn != 1:
                                            isCheckedIn = 1 if ticket.scannedTimestamp != 0 else 0
                                        ticketData['id'] = ticketSocketOrderTicketId
                                        ticketData['isCheckedIn'] = isCheckedIn
                                        
                                        sql = """Update TicketSocketOrderTickets SET TicketType=%(ticketType)s, ServiceFee=%(serviceFee)s, 
                                                BarCode=%(barcode)s, AvailableScans=%(availableScans)s, PurchaseLocation=%(purchaseLocation)s, 
                                                ScannedTimestamp=%(scannedTimestamp)s, IsCheckedIn=%(isCheckedIn)s, """
                                        if ticketPrice > 0:
                                            sql += """Price=%(price)s, """
                                        sql += """LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                        ticketSuccess = db.update(sql, ticketData, cnx)
                                    else:
                                        #insert new ticket
                                        ticketAddNew = True
                                        ticketData['ticketId'] = int(ticket.id)
                                        ticketData['ticketSocketOrderId'] = ticketSocketOrderId
                                        ticketData['isCheckedIn'] = 1 if ticket.scannedTimestamp != 0 else 0
                                        sql = """INSERT INTO TicketSocketOrderTickets (TicketSocketOrderId, TicketId, TicketType, ServiceFee, BarCode, AvailableScans, PurchaseLocation, ScannedTimestamp, IsCheckedIn""" 
                                        if ticketPrice > 0:
                                            sql += ", Price"
                                        sql += """) """
                                        sql += """VALUES (%(ticketSocketOrderId)s, %(ticketId)s, %(ticketType)s, %(serviceFee)s, %(barcode)s, %(availableScans)s, %(purchaseLocation)s, %(scannedTimestamp)s, %(isCheckedIn)s"""
                                        if ticketPrice > 0:
                                            sql += ", %(price)s"
                                        sql += """)"""
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
                                        updateSuccess = False
                                        continue
            else:
                updateSuccess = True
                
            endTimer = time.time()
            duration = endTimer - startTimer  
            
            databaseDuration = endTimer - serviceTimer            
            utility.logMessage('database update complete in ' + str(databaseDuration) + ' seconds')       
                                    
            results = TicketSocketRefreshHistory(serviceEventsSkipped, eventsFailed, ordersFailed, ticketsFailed, ticketTypesFailed, totalEventsFromService, 
                                                eventsUpdated, eventsInserted, ordersInserted, ordersUpdated, ordersDeleted, 
                                                ticketsUpdated, ticketsInserted, ticketTypesUpdated, ticketTypesInserted, 
                                                int(startTimer), int(endTimer), duration, userId, sellerId, start, end, 
                                                updateSuccess, errorMessage)
            if userId != None and userId > 0:
                userService = UserService()
                user = userService.getUserById(userId)
                if user != None:
                    results.userName = user.userFullname()
            else:
                results.userName = "System"
                
            results.orderDataRowsRemoved = dailyOrderDataRowsRemoved
            
            results.commit(cnx)
            
            if cnx != None and cnx.is_connected:
                cnx.close()

        except Exception as error:
            updateSuccess = False
            errorMessage: str = str(error) + "\n" + traceback.format_exc()
            utility.logMessage(errorMessage)
            

        # alert dB if it failed
        if updateSuccess != True or (results != None and results.succeeded != True):
            subject = "Error in TS Refresh - " + datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            if results != None:
                html = utility.convertToJson(results)
            else:
                html = errorMessage
            to = "dwbodine@gmail.com"
            toName = "dB"
            result = utility.sendEmail(to, subject, html, toName)
            
        return results
        
    def getTicketSocketRefreshHistory(self):
        logs: list[TicketSocketRefreshHistory] = []

        sql = """SELECT TicketSocketRefreshHistory.*, CONCAT(Users.FirstName, ' ', Users.LastName) AS UserName, Users.UserName AS Email, Sellers.Name AS SellerName
                  FROM TicketSocketRefreshHistory 
                  LEFT JOIN Users ON Users.UserId = TicketSocketRefreshHistory.UserId
                  LEFT JOIN Sellers ON Sellers.SellerId = TicketSocketRefreshHistory.SellerId
                  ORDER BY TicketSocketRefreshHistory.StartTimer DESC"""


        rows = db.queryAll(sql)
        for row in rows:
            userId = int(row["UserId"])
            if userId == 0:
                userName = "System"
            else:
                userName = str(row["UserName"]) + " (" + str(row["Email"]) + ")"
            sellerId = int(row["SellerId"]) if row["SellerId"] != None else None
            sellerName = str(row["SellerName"]) if row["SellerName"] != None else None
            start = int(row["Start"]) if row["Start"] != None else None
            end = int(row["End"]) if row["End"] != None else None
            startTimer = int(row["StartTimer"])
            endTimer = int(row["EndTimer"])
            duration = float(row["Duration"])
            succeeded = True if int(row["Success"]) == 1 else False
            errorMessage = str(row["ErrorMessage"])
            serviceEventsSkipped = str(row["ServiceEventsSkipped"])
            eventsFailed = str(row["EventsFailed"])
            ordersFailed = str(row["OrdersFailed"])
            ticketsFailed = str(row["TicketsFailed"])
            ticketTypesFailed = str(row["TicketTypesFailed"])
            totalEventsFromService = int(row["TotalEventsFromService"])
            eventsUpdated = int(row["EventsUpdated"])
            eventsInserted = int(row["EventsInserted"])
            ordersInserted = int(row["OrdersInserted"])
            ordersUpdated = int(row["OrdersUpdated"])
            ordersDeleted = int(row["OrdersDeleted"])
            ticketsUpdated = int(row["TicketsUpdated"])
            ticketsInserted = int(row["TicketsInserted"])
            ticketTypesUpdated = int(row["TicketTypesUpdated"])
            ticketTypesInserted = int(row["TicketTypesInserted"])
            orderDataUpdateSucceeded = True if int(row["OrderDataUpdateSucceeded"]) == 1 else False
            orderDataUpdateDuration = float(row["OrderDataUpdateDuration"])
            totalDuration = float(row["TotalDuration"])
            orderDataRowsTotal = int(row["OrderDataRowsTotal"])
            orderDataRowsInserted = int(row["OrderDataRowsInserted"])
            orderDataRowsUpdated = int(row["OrderDataRowsUpdated"])
            orderDataRowsRemoved = int(row["OrderDataRowsRemoved"])
            

            history = TicketSocketRefreshHistory(serviceEventsSkipped, eventsFailed, ordersFailed, ticketsFailed, ticketTypesFailed, totalEventsFromService, eventsUpdated, 
                                                 eventsInserted, ordersInserted, ordersUpdated, ordersDeleted, ticketsUpdated, ticketsInserted, 
                                                 ticketTypesUpdated, ticketTypesInserted,  
                                                 startTimer, endTimer, duration, userId, sellerId, start, end, succeeded, errorMessage)
            history.sellerName = sellerName
            history.userName = userName
            history.orderDataUpdateSucceeded = orderDataUpdateSucceeded
            history.orderDataUpdateDuration = orderDataUpdateDuration
            history.orderDataRowsTotal = orderDataRowsTotal
            history.orderDataRowsUpdated = orderDataRowsUpdated
            history.orderDataRowsRemoved = orderDataRowsRemoved
            history.orderDataRowsInserted = orderDataRowsInserted
            history.totalDuration = totalDuration
            logs.append(history)
        
        return logs