"""
Models specific to National Acts
"""
import calendar
import datetime
import traceback
from common.utility import log_message
from common.models.ticket_socket import (
    TicketSocketTicket,
    TicketSocketOrder,
    TicketSocketVenue,
    TicketSocketEvent,
)
from common.db import db_query_all, db_query_one, db_insert, db_update, db_delete


class SellerEventCategory:
    """
    Construct bringing together "category" (aka "event_category_id" from TS)
    and "seller_id" (National acts representation across multiple TS services)
    """
    seller_id: int = 0
    ticket_socket_id: int = 0
    event_category_id: int = 0
    seller_event_category_id: int = 0

    def __init__(
        self,
        seller_id: int = None,
        ticket_socket_id: int = None,
        event_category_id: int = None,
        seller_event_category_id: int = None,
    ):
        if (
            seller_id is not None
            and ticket_socket_id is not None
            and event_category_id is None
            and seller_event_category_id is None
        ):
            self.__populate_from_seller_id_and_ticket_socket_id(seller_id, ticket_socket_id)
        elif (
            seller_id is None
            and ticket_socket_id is not None
            and event_category_id is not None
            and seller_event_category_id is None
        ):
            self.__populate_from_ticket_socket_id_and_event_category_id(
                ticket_socket_id, event_category_id
            )
        elif seller_event_category_id is not None:
            self.__populate_from_seller_event_category_id(seller_event_category_id)
        elif (
            seller_id is not None
            and ticket_socket_id is not None
            and event_category_id is not None
            and seller_event_category_id is not None
        ):
            self.seller_id = seller_id
            self.ticket_socket_id = ticket_socket_id
            self.event_category_id = event_category_id
            self.seller_event_category_id = seller_event_category_id
        else:
            raise RuntimeError("Invalid input data for SellerEventCategory")

    def __populate_from_seller_id_and_ticket_socket_id(
        self, seller_id: int, ticket_socket_id: int
    ):
        self.seller_id = seller_id
        self.ticket_socket_id = ticket_socket_id
        sql = """SELECT * FROM SellerEventCategory
                WHERE SellerId=%(sellerId)s AND TicketSocketId=%(ticketSocketId)s"""
        data = {"sellerId": self.seller_id, "ticketSocketId": self.ticket_socket_id}
        sec = db_query_one(sql, data)
        if sec:
            self.event_category_id = sec["EventCategoryId"]
            self.seller_event_category_id = sec["SellerEventCategoryId"]

    def __populate_from_ticket_socket_id_and_event_category_id(
        self, ticket_socket_id: int, event_category_id: int
    ):
        self.ticket_socket_id = ticket_socket_id
        self.event_category_id = event_category_id
        sql = """SELECT * FROM SellerEventCategory
                WHERE TicketSocketId=%(ticketSocketId)s
                AND EventCategoryId=%(eventCategoryId)s"""
        data = {
            "ticketSocketId": self.ticket_socket_id,
            "eventCategoryId": self.event_category_id,
        }
        sec = db_query_one(sql, data)
        if sec:
            self.seller_id = sec["SellerId"]
            self.seller_event_category_id = sec["SellerEventCategoryId"]

    def __populate_from_seller_event_category_id(self, seller_event_category_id: int):
        self.seller_event_category_id = seller_event_category_id
        sql = """SELECT * FROM SellerEventCategory
                WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"""
        data = {"sellerEventCategoryId": self.seller_event_category_id}
        sec = db_query_one(sql, data)
        if sec:
            self.seller_id = sec["SellerId"]
            self.ticket_socket_id = sec["TicketSocketId"]
            self.event_category_id = sec["EventCategoryId"]


class ShirtSales:
    """
    Shirt sale data
    """
    def __init__(self, size: str, total: int):
        self.size = size
        self.total = total


class VipTicket(TicketSocketTicket):
    """
    National acts specific verison of TS tickets
    """
    ticket_socket_order_id: int = 0
    ticket_socket_order_ticket_id: int = 0
    is_checked_in: bool = False
    is_refunded: bool = False
    refund_date: str = None
    is_charged_back: bool = False
    chargeback_date: str = None
    is_service_fee_refunded: bool = False


class VipOrder(TicketSocketOrder):
    """
    National acts specific version of TS orders
    """
    ticket_socket_event_id: int = 0
    ticket_socket_order_id: int = 0
    seller_name: str = None
    seller_id: int = 0
    venue: str = None
    event_title: str = None
    event_address: str = None
    event_city: str = None
    event_state: str = None
    event_zip: str = None
    event_country: str = None
    event_date: str = None
    is_active: bool = True
    is_deleted: bool = False
    has_refunds: bool = False
    has_chargebacks: bool = False
    num_tickets_refunded: int = 0
    num_tickets_charged_back: int = 0
    revenue_refunded: float = 0
    revenue_charged_back: float = 0
    revenue_refunded_usd: float = 0
    revenue_charged_back_usd: float = 0
    service_fee_revenue_refunded: float = 0
    service_fee_revenue_refunded_usd: float = 0
    service_fee_revenue_charged_back: float = 0
    service_fee_revenue_charged_back_usd: float = 0
    total_shirts: int = 0
    revenue_usd: float = 0
    service_fees_usd: float = 0
    exchange_rate: float = 1.0
    currency_symbol: str = None
    currency_abbrev: str = None
    tickets: list[VipTicket] = []
    is_hidden: bool = False

    def get_totals(self):
        """
        Roll up data from tickets to order
        """
        self.total_shirts = len(self.shirts)
        for ticket in self.tickets:
            if ticket.is_refunded is True:
                self.num_tickets_refunded += 1
                self.revenue_refunded += ticket.price
                if ticket.is_service_fee_refunded is True:
                    self.service_fee_revenue_refunded += ticket.service_fee
            elif ticket.is_charged_back is True:
                self.num_tickets_charged_back += 1
                self.revenue_charged_back += ticket.price
                self.service_fee_revenue_charged_back += ticket.service_fee

        self.revenue_usd = self.revenue * self.exchange_rate
        self.service_fees_usd = self.service_fees * self.exchange_rate
        self.revenue_refunded_usd = self.revenue_refunded * self.exchange_rate
        self.service_fee_revenue_refunded_usd = (
            self.service_fee_revenue_refunded * self.exchange_rate
        )
        self.revenue_charged_back_usd = self.revenue_charged_back * self.exchange_rate
        self.service_fee_revenue_charged_back_usd = (
            self.service_fee_revenue_charged_back * self.exchange_rate
        )


class VipEvent(TicketSocketEvent):
    ticket_socket_event_id: int = 0
    total_revenue: float = 0
    totalServiceFees: float = 0
    totalTickets: int = 0
    totalCheckedIn: int = 0
    total_shirts: int = 0
    shirtSales: list[ShirtSales] = []
    is_active: bool = True
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
    seller_event_category_id: int = None
    isVip: bool = True
    is_deleted: bool = False
    isExternal: bool = False
    hasShirtData: bool = False
    hasPhoneData: bool = False
    hasNonUSAOrders: bool = False
    nonUsaCurrencySymbol: str = None
    nonUsaCurrencyAbbrev: str = None
    num_tickets_refunded: int = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0
    num_tickets_charged_back: int = 0
    revenue_charged_back: float = 0
    service_fee_revenue_charged_back: float = 0
    hasTicketTypeData: bool = False
    isAddedToBandsInTown: bool = False
    seller_name: str = ""
    is_hidden: bool = False
    is_cancelled: bool = False
    cancelled_date: str = None
    announce_date: str = None

    def get_totals(self):
        total_revenue: float = 0
        totalServiceFees: float = 0
        totalTickets: int = 0
        total_shirts: int = 0
        totalTicketsRefunded: int = 0
        totalTicketsChargedBack: int = 0
        totalRevenueRefunded: float = 0
        totalRevenueChargedBack: float = 0
        totalServiceFeeRevenueRefunded: float = 0
        totalServiceFeeRevenueChargedBack: float = 0
        totalCheckedIn: int = 0
        shirtd: dict() = {}
        for order in self.orders:
            if order.has_refunds is True:
                totalTicketsRefunded += order.num_tickets_refunded
                totalRevenueRefunded += order.revenue_refunded_usd
                totalServiceFeeRevenueRefunded += order.service_fee_revenue_refunded_usd
            if order.has_chargebacks is True:
                totalTicketsChargedBack += order.num_tickets_charged_back
                totalRevenueChargedBack += order.revenue_charged_back_usd
                totalServiceFeeRevenueChargedBack += (
                    order.service_fee_revenue_charged_back_usd
                )
            if self.hasNonUSAOrders is False and order.currency_abbrev != "USD":
                self.hasNonUSAOrders = True
                self.nonUsaCurrencyAbbrev = order.currency_abbrev
                self.nonUsaCurrencySymbol = order.currency_symbol

            if self.hasShirtData is False and len(order.shirts) > 0:
                self.hasShirtData = True

            if (
                self.hasPhoneData is False
                and order.phone is not None
                and len(order.phone) > 0
            ):
                self.hasPhoneData = True

            if order.is_deleted is not True:
                total_revenue += order.revenue_usd
                totalServiceFees += order.service_fees_usd
                totalTickets += order.numTickets

                if len(order.tickets) > 0:
                    for ticket in order.tickets:
                        if ticket.is_checked_in:
                            totalCheckedIn += 1

                if len(order.shirts) > 0:
                    total_shirts += len(order.shirts)
                    for size in order.shirts:
                        if size in shirtd:
                            shirtd[size] = int(shirtd[size]) + 1
                        else:
                            shirtd[size] = 1

        self.total_revenue = total_revenue
        self.totalServiceFees = totalServiceFees
        self.totalTickets = totalTickets
        self.totalCheckedIn = totalCheckedIn
        self.total_shirts = total_shirts
        self.num_tickets_refunded = totalTicketsRefunded
        self.num_tickets_charged_back = totalTicketsRefunded
        self.revenue_refunded = totalRevenueRefunded
        self.revenue_charged_back = totalRevenueChargedBack
        self.service_fee_revenue_refunded = totalServiceFeeRevenueRefunded
        self.service_fee_revenue_charged_back = totalServiceFeeRevenueChargedBack

        self.hasTicketTypeData = len(self.ticketTypes) > 0

        shirtSales: list[ShirtSales] = []
        for size in shirtd:
            shirtSale = ShirtSales(size, int(shirtd[size]))
            shirtSales.append(shirtSale)
        self.shirtSales = shirtSales

        # roll up external event data, if any
        if self.externalTitle is not None and self.externalTitle != "":
            self.title = self.externalTitle

        if self.externalVenue is not None:
            if self.externalVenue.name is not None and self.externalVenue.name != "":
                self.venue.name = self.externalVenue.name
            if (
                self.externalVenue.address1 is not None
                and self.externalVenue.address1 != ""
            ):
                self.venue.address1 = self.externalVenue.address1
            if (
                self.externalVenue.address2 is not None
                and self.externalVenue.address2 != ""
            ):
                self.venue.address2 = self.externalVenue.address2
            if self.externalVenue.city is not None and self.externalVenue.city != "":
                self.venue.city = self.externalVenue.city
            if self.externalVenue.state is not None and self.externalVenue.state != "":
                self.venue.state = self.externalVenue.state
            if (
                self.externalVenue.postalCode is not None
                and self.externalVenue.postalCode != ""
            ):
                self.venue.postalCode = self.externalVenue.postalCode

        if self.externalThumbnail is not None and self.externalThumbnail != "":
            self.thumbnail = self.externalThumbnail

        if self.externalVipLink is not None and self.externalVipLink != "":
            self.ticketSocketUrl = self.externalVipLink


class DailyOrderData:
    ticket_socket_order_id: int = None
    orders: int = 0
    tickets: int = 0
    ticketRevenueUsd: float = 0
    serviceFeesRevenueUsd: float = 0
    totalRevenueUsd: float = 0
    event_title: str = None
    event_date: str = None
    seller_id: int = None
    seller_name: str = None
    venue: str = None
    city: str = None
    state: str = None
    zip: str = None
    country: str = None
    ticket_socket_id: int = 0
    is_refunded: bool = False
    isChargeback: bool = False
    num_tickets_refunded: int = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0

    def __init__(self, purchaseDate: str, ticket_socket_event_id: int):
        self.purchaseDate = purchaseDate
        self.ticket_socket_event_id = ticket_socket_event_id


class DashboardTotals:
    tickets: int = 0
    orders: int = 0
    num_tickets_refunded: int = 0
    ticketRevenueUsd: float = 0
    serviceFeesRevenueUsd: float = 0
    totalRevenueUsd: float = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0
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
        data = {"name": "YearlyRevenueGoal"}
        row = db_query_one(sql, data)
        self.yearlyRevenueGoal = float(row["Value"])
        data = {"name": "MonthlyRevenueGoal"}
        row = db_query_one(sql, data)
        self.monthlyRevenueGoal = float(row["Value"])


class DashboardPayload:
    def __init__(self, orders: list[VipOrder], totals: DashboardTotals):
        self.orders = orders
        self.totals = totals


class Seller:
    hideInList: bool = False
    is_active: bool = True
    name: str = None
    sellerType: int = 1

    sellerEventCategories: list[SellerEventCategory] = []

    def __init__(self, seller_id: int):
        self.seller_id = seller_id
        self.__initialize()

    def __initialize(self):
        sql = """SELECT * FROM Sellers
                 WHERE SellerId=%(sellerId)s"""
        data = {"sellerId": self.seller_id}

        row = db_query_one(sql, data)
        if row:
            self.name = str(row["Name"])
            self.sellerType = int(row["SellerTypeId"])
            self.hideInList = int(row["HideInList"]) == 1
            self.is_active = int(row["Inactive"]) != 1
            self.__getSellerEventCategories()

    def __getSellerEventCategories(self):
        sql = """SELECT * 
                 FROM SellerEventCategory
                 WHERE SellerId=%(sellerId)s"""
        data = {"sellerId": self.seller_id}

        sellerEventCategories = []
        rows = db_query_all(sql, data)
        for row in rows:
            sec = SellerEventCategory(
                self.seller_id,
                int(row["TicketSocketId"]),
                int(row["EventCategoryId"]),
                int(row["SellerEventCategoryId"]),
            )
            sellerEventCategories.append(sec)
        self.sellerEventCategories = sellerEventCategories

    def getSellerEventCategory(self, ticket_socket_id: int):
        if len(self.sellerEventCategories) == 0:
            return None

        sellerEventCategory = None
        for sec in self.sellerEventCategories:
            if sec.ticket_socket_id == ticket_socket_id:
                sellerEventCategory = sec
                break

        return sellerEventCategory

    def getSellerEventCategoryIds(self):
        ids: list[int] = []
        if len(self.sellerEventCategories) > 0:
            for sec in self.sellerEventCategories:
                ids.append(sec.seller_event_category_id)
        return ids


class TicketSocketRefreshHistory:
    seller_name: str = None
    userName: str = None
    ticketSocketRefreshHistoryId: int = None
    orderDataRowsRemoved: int = 0
    orderDataRowsUpdated: int = 0
    orderDataRowsInserted: int = 0
    orderDataRowsTotal: int = 0
    orderDataUpdateSucceeded: bool = False
    orderDataUpdateDuration: float = 0
    totalDuration: float = 0

    def __init__(
        self,
        serviceEventsSkipped: list[int],
        eventsFailed: list[int],
        ordersFailed: list[int],
        ticketsFailed: list[int],
        ticketTypesFailed: list[int],
        totalEventsFromService: int,
        eventsUpdated: int,
        eventsInserted: int,
        ordersInserted: int,
        ordersUpdated: int,
        ordersDeleted: int,
        ticketsUpdated: int,
        ticketsInserted: int,
        ticketTypesUpdated: int,
        ticketTypesInserted: int,
        startTimer: int,
        endTimer: int,
        duration: float,
        userId: int = 0,
        seller_id: int = 0,
        start: int = 0,
        end: int = 0,
        succeeded: bool = False,
        errorMessage: str = None,
    ):
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
        self.seller_id = seller_id
        self.start = start
        self.end = end
        self.startTimer = startTimer
        self.endTimer = endTimer
        self.duration = duration
        self.succeeded = succeeded
        self.errorMessage = errorMessage

    def __getSellerName(self):
        if self.seller_id is not None:
            seller = Seller(self.seller_id)
            self.seller_name = seller.name + " (SellerId: " + str(self.seller_id) + ")"

    def cleanup(self, cnx=None):
        success: bool = True

        try:
            weekAgo: int = self.endTimer - (24 * 60 * 60)
            sql = """DELETE FROM TicketSocketRefreshHistory WHERE EndTimer <= %(weekAgo)s"""
            data = {"weekAgo": weekAgo}
            db_delete(sql, data, cnx)
        except Exception as error:
            success = False
            errorMessage: str = str(error) + "\n" + traceback.format_exc()
            log_message(errorMessage)

        return success

    def setOrderUpdateSuccess(
        self, success: bool, duration: float, inserts: int, updates: int, cnx=None
    ):
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
            "successVal": 1 if success is True else 0,
            "ticketSocketRefreshHistoryId": self.ticketSocketRefreshHistoryId,
            "orderDataUpdateDuration": duration,
            "totalDuration": totalDuration,
            "orderDataRowsTotal": self.orderDataRowsTotal,
            "orderDataRowsInserted": self.orderDataRowsInserted,
            "orderDataRowsUpdated": self.orderDataRowsUpdated,
            "orderDataRowsRemoved": self.orderDataRowsRemoved,
        }
        db_update(sql, data, cnx)

    def commit(self, cnx=None):
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
            "userId": self.userId,
            "sellerId": self.seller_id,
            "start": self.start,
            "end": self.end,
            "startTimer": self.startTimer,
            "endTimer": self.endTimer,
            "duration": self.duration,
            "success": 1 if self.succeeded is True else 0,
            "errorMessage": self.errorMessage,
            "serviceEventsSkipped": ", ".join(self.serviceEventsSkipped),
            "eventsFailed": ", ".join(str(v) for v in self.eventsFailed),
            "ordersFailed": ", ".join(str(v) for v in self.ordersFailed),
            "ticketsFailed": ", ".join(str(v) for v in self.ticketsFailed),
            "ticketTypesFailed": ", ".join(str(v) for v in self.ticketTypesFailed),
            "totalEventsFromService": self.totalEventsFromService,
            "eventsUpdated": self.eventsUpdated,
            "eventsInserted": self.eventsInserted,
            "ordersInserted": self.ordersInserted,
            "ordersUpdated": self.ordersUpdated,
            "ordersDeleted": self.ordersDeleted,
            "ticketsUpdated": self.ticketsUpdated,
            "ticketsInserted": self.ticketsInserted,
            "ticketTypesUpdated": self.ticketTypesUpdated,
            "ticketTypesInserted": self.ticketTypesInserted,
        }

        self.ticketSocketRefreshHistoryId = db_insert(sql, data, cnx)

        return self.ticketSocketRefreshHistoryId > 0
