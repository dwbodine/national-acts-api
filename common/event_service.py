"""
Event Service
"""
import time
from datetime import datetime, timedelta
import operator
import traceback

from common.db import queryAll, queryOne, update, insert
from common.db import convertListToParameters, getDbConnection, delete
from common.utility import logMessage, convertToJson, sendEmail
from common.ticket_socket_service import TicketSocketService
from common.models.national_acts import (
    VipEvent, VipOrder, VipTicket, Seller, 
    SellerEventCategory, DailyOrderData, 
    TicketSocketRefreshHistory, DashboardTotals
)
from common.models.ticket_socket import TicketSocketVenue, TicketSocketTicketType
from common.user_service import UserService


class EventService:
    """
    Service to handle all event-related activity
    """
    def get_events_and_orders(
        self,
        get_orders: bool = False,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        show_inactive: bool = False,
        search_term: str = None,
        ts_event_id: int = None,
        show_deleted: bool = False,
        exclude_start: int = None,
        exclude_end: int = None,
        exclude_external: bool = False,
        show_hidden: bool = False,
        ignore_flags: bool = False,
        show_cancelled: bool = False,
        show_unannounced: bool = True
    ):
        """
        main method to fetch events and orders
        """
        events: list[VipEvent] = []

        seller_event_category_ids: list[int] = []
        if seller_id is not None:
            seller = Seller(seller_id)
            seller_event_category_ids = seller.getSellerEventCategoryIds()
            # prevent against returning every event in the database
            if len(seller_event_category_ids) == 0:
                return []

        if get_orders is False and search_term is not None:
            search_term = search_term.replace("'", "''")
            search_term = search_term.replace('"', "")
            search_term = search_term.replace("=", "")
        else:
            search_term = None

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
            LEFT JOIN ExternalEvents ON ExternalEvents.SellerId = Sellers.SellerId 
                AND TicketSocketEvents.EventDate = ExternalEvents.EventDate """

        if ts_event_id is None:
            if show_inactive is True:
                sql += " AND ExternalEvents.IsActive = 0"
            elif ignore_flags is not True:
                sql += " AND ExternalEvents.IsActive = 1"

        sql += " WHERE "
        data = {}

        where_clause: list[str] = []
        if ts_event_id is not None:
            where_clause.append("TicketSocketEvents.Id = %(event_id)s")
            data["event_id"] = ts_event_id
        else:
            if ignore_flags is not True:
                if show_deleted is not True:
                    where_clause.append("TicketSocketEvents.IsDeleted = 0")
                else:
                    show_inactive = True

                if show_inactive is True:
                    where_clause.append("TicketSocketEvents.IsActive = 0")
                else:
                    where_clause.append("TicketSocketEvents.IsActive = 1")

                if show_hidden is not True:
                    where_clause.append("TicketSocketEvents.IsHidden = 0")

                if show_cancelled is not True:
                    where_clause.append("TicketSocketEvents.IsCancelled = 0")
            if search_term is not None and len(search_term) > 0:
                where_clause.append(
                    """MATCH (TicketSocketEvents.Title, 
                                TicketSocketEvents.Venue, 
                                TicketSocketEvents.Address, 
                                TicketSocketEvents.City, 
                                TicketSocketEvents.State,
                                TicketSocketEvents.Country) 
                                AGAINST (%(search_term)s IN BOOLEAN MODE)"""
                )
                data["search_term"] = "*" + search_term + "*"
            if len(seller_event_category_ids) > 0:
                seller_event_category_id_str = convertListToParameters(
                    seller_event_category_ids, data, "sellerEventCategoryId"
                )
                where_clause.append(
                    "TicketSocketEvents.SellerEventCategoryId IN "
                    + seller_event_category_id_str
                )

            if start is not None and end is not None:
                where_clause.append(
                    "TicketSocketEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif end is not None:
                where_clause.append(
                    "TicketSocketEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                data["startDate"] = datetime.now().strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif start is not None:
                where_clause.append("TicketSocketEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            elif get_orders is False or seller_id is None:
                where_clause.append("TicketSocketEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.now().strftime("%Y-%m-%d")
            if show_unannounced is not True:
                where_clause.append("""COALESCE(TicketSocketEvents.AnnounceDate,
                                     CURRENT_TIMESTAMP) >= CURRENT_TIMESTAMP""")

            if exclude_start is not None and exclude_end is not None:
                where_clause.append(
                    "TicketSocketEvents.EventDate NOT BETWEEN %(exclude_start)s AND %(exclude_end)s"
                )
                data["exclude_start"] = datetime.fromtimestamp(exclude_start).strftime(
                    "%Y-%m-%d"
                )
                data["exclude_end"] = datetime.fromtimestamp(exclude_end).strftime(
                    "%Y-%m-%d"
                )

        if len(where_clause) > 0:
            sql += " AND ".join(where_clause)

        sql += (
            " ORDER BY TicketSocketEvents.EventDate ASC, TicketSocketEvents.Title ASC"
        )

        sql = sql.replace("\n", "")

        event_rows = queryAll(sql, data)
        for row in event_rows:
            event_id = int(row["EventId"])
            ticket_socket_event_id = int(row["Id"])
            vip_event = VipEvent(event_id, str(row["Title"]))
            vip_event.seller_name = str(row["SellerName"])
            vip_event.isExternal = False
            vip_event.ticketSocketEventId = ticket_socket_event_id
            vip_event.sellerEventCategoryId = int(row["SellerEventCategoryId"])
            vip_event.eventDate = str(row["EventDate"])
            vip_event.utcTime = int(row["UtcTime"])
            vip_event.displayDate = (
                str(row["DisplayDate"]) if row["DisplayDate"] is not None else None
            )
            vip_event.thumbnail = (
                str(row["Thumbnail"]) if row["Thumbnail"] is not None else None
            )
            vip_event.ticketSocketUrl = str(row["URL"])
            vip_event.isAddedToBandsInTown = (
                True if int(row["IsAddedToBandsInTown"]) == 1 else False
            )
            vip_event.isHidden = True if int(row["IsHidden"]) == 1 else False
            vip_event.isCancelled = True if int(row["IsCancelled"]) == 1 else False
            vip_event.cancelledDate = (
                str(row["CancelledDate"])
                if (vip_event.isCancelled is True and row["CancelledDate"] is not None)
                else None
            )
            venue_name = str(row["Venue"]) if row["Venue"] is not None else None
            if row["ExternalVenue"] is not None:
                venue_name = str(row["ExternalVenue"])
            address = str(row["Address"]) if row["Address"] is not None else None
            if row["ExternalAddress"] is not None:
                address = str(row["ExternalAddress"])
            city = str(row["City"]) if row["City"] is not None else None
            if row["ExternalCity"] is not None:
                city = str(row["ExternalCity"])
            state = str(row["State"]) if row["State"] is not None else None
            if row["ExternalState"] is not None:
                state = str(row["ExternalState"])
            zip_code = str(row["Zip"]) if row["Zip"] is not None else None
            if row["ExternalZip"] is not None:
                zip_code = str(row["ExternalZip"])
            vip_country = str(row["Country"]) if row["Country"] is not None else None
            if row["ExternalCountry"] is not None:
                vip_country = str(row["ExternalCountry"])

            venue = TicketSocketVenue(
                venue_name, address, "", city, state, zip_code, vip_country, ""
            )
            vip_event.venue = venue
            vip_event.onSale = True if int(row["OnSale"]) == 1 else False
            vip_event.is_active = True if int(row["IsActive"]) == 1 else False
            vip_event.isDeleted = True if int(row["IsDeleted"]) == 1 else False
            if vip_event.isDeleted is True:
                vip_event.is_active = False
            vip_event.isVip = True if int(row["IsVip"]) == 1 else False
            if (
                row["ExternalEventId"] is not None
                and row["ExternalEventId"] != ""
                and exclude_external is not True
            ):
                vip_event.externalEventId = int(row["ExternalEventId"])
                vip_event.externalSellerId = int(row["ExternalSellerId"])
                vip_event.externalTitle = str(row["ExternalTitle"])
                vip_event.externalThumbnail = str(row["ExternalThumbnail"])
                vip_event.externalUrl = str(row["ExternalUrl"])
                external_country = (
                    str(row["ExternalCountry"])
                    if row["ExternalCountry"] is not None
                    else None
                )
                external_venue = TicketSocketVenue(
                    str(row["ExternalVenue"]),
                    str(row["ExternalAddress"]),
                    "",
                    str(row["ExternalCity"]),
                    str(row["ExternalState"]),
                    str(row["ExternalZip"]),
                    external_country,
                    "",
                )
                vip_event.externalVenue = external_venue
                vip_event.disableLinkButton = str(row["DisableLinkButton"])
                vip_event.disableLinkReason = str(row["DisableLinkReason"])
                vip_event.externalVipLink = str(row["ExternalVipLink"])
                vip_event.disableVipLinkButton = str(row["DisableVipLinkButton"])
                vip_event.disableVipLinkReason = str(row["DisableVipLinkReason"])

            if get_orders is True:
                ticket_types = self.__get_ticket_types_from_event_id(ticket_socket_event_id)
                vip_event.ticketTypes = ticket_types
                orders = self.__get_orders_from_event_id(
                    ticket_socket_event_id,
                    show_inactive,
                    show_deleted,
                    show_hidden,
                    ignore_flags,
                )
                vip_event.orders = orders

            vip_event.getTotals()

            events.append(vip_event)

        # if not excluded, get external events without matching TicketSocketEvents
        if exclude_external is not True:
            external_sql = """SELECT ExternalEvents.*, Sellers.Name as SellerName
                                FROM ExternalEvents 
                                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                                WHERE """
            external_data = {}

            externalwhere_clause: list[str] = []
            if show_inactive is True:
                externalwhere_clause.append("ExternalEvents.IsActive = 0")
            elif ignore_flags is not True:
                externalwhere_clause.append("ExternalEvents.IsActive = 1")

            if show_hidden is not True and ignore_flags is not True:
                externalwhere_clause.append("ExternalEvents.IsHidden = 0")

            if show_cancelled is not True and ignore_flags is not True:
                externalwhere_clause.append("ExternalEvents.IsCancelled = 0")

            if search_term is not None and len(search_term) > 0:
                externalwhere_clause.append(
                    """MATCH (ExternalEvents.Title, ExternalEvents.Venue,
                              ExternalEvents.Address, ExternalEvents.City,
                              ExternalEvents.State, ExternalEvents.Country)
                              AGAINST (%(search_term)s IN BOOLEAN MODE)"""
                )
                external_data["search_term"] = "*" + search_term + "*"
            if seller_id is not None:
                externalwhere_clause.append("ExternalEvents.seller_id = %(seller_id)s")
                external_data["seller_id"] = seller_id
            if start is not None and end is not None:
                externalwhere_clause.append(
                    "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                external_data["startDate"] = datetime.fromtimestamp(start).strftime(
                    "%Y-%m-%d"
                )
                external_data["endDate"] = datetime.fromtimestamp(end).strftime(
                    "%Y-%m-%d"
                )
            elif end is not None:
                externalwhere_clause.append(
                    "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                external_data["startDate"] = datetime.now().strftime("%Y-%m-%d")
                external_data["endDate"] = datetime.fromtimestamp(end).strftime(
                    "%Y-%m-%d"
                )
            elif start is not None:
                externalwhere_clause.append("ExternalEvents.EventDate >= %(startDate)s")
                external_data["startDate"] = datetime.fromtimestamp(start).strftime(
                    "%Y-%m-%d"
                )
            else:
                externalwhere_clause.append("ExternalEvents.EventDate >= %(startDate)s")
                external_data["startDate"] = datetime.now().strftime("%Y-%m-%d")

            if len(externalwhere_clause) > 0:
                external_sql += " AND ".join(externalwhere_clause)

            external_sql += """ AND ExternalEvents.EventId NOT IN
                (SELECT DISTINCT ExternalEvents.EventId FROM ExternalEvents
                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId 
                JOIN TicketSocketEvents ON 
                    TicketSocketEvents.SellerEventCategoryId = SellerEventCategory.SellerEventCategoryId
                    AND ExternalEvents.EventDate = TicketSocketEvents.EventDate) 
                ORDER BY ExternalEvents.EventDate ASC, ExternalEvents.Title ASC"""

            external_sql = external_sql.replace("\n", "")

            externalevent_rows = queryAll(external_sql, external_data)
            for row in externalevent_rows:
                event_id = int(row["EventId"])
                vip_event = VipEvent(event_id, str(row["Title"]))
                vip_event.seller_name = str(row["SellerName"])
                vip_event.isExternal = True
                vip_event.eventDate = str(row["EventDate"])
                vip_event.thumbnail = str(row["Thumbnail"])
                vip_event.externalUrl = str(row["URL"])
                venue = TicketSocketVenue(
                    str(row["Venue"]),
                    str(row["Address"]),
                    "",
                    str(row["City"]),
                    str(row["State"]),
                    str(row["Zip"]),
                    str(row["Country"]),
                    "",
                )
                vip_event.venue = venue
                vip_event.is_active = True if int(row["IsActive"]) == 1 else False
                vip_event.externalEventId = int(row["EventId"])
                vip_event.externalSellerId = int(row["SellerId"])
                vip_event.disableLinkButton = str(row["DisableLinkButton"])
                vip_event.disableLinkReason = str(row["DisableLinkReason"])
                vip_event.externalVipLink = str(row["ExternalVipLink"])
                vip_event.isVip = (
                    True
                    if (
                        vip_event.externalVipLink is not None
                        and vip_event.externalVipLink != ""
                    )
                    else False
                )
                vip_event.disableVipLinkButton = str(row["DisableVipLinkButton"])
                vip_event.disableVipLinkReason = str(row["DisableVipLinkReason"])
                vip_event.isAddedToBandsInTown = (
                    True if int(row["IsAddedToBandsInTown"]) == 1 else False
                )
                vip_event.isHidden = True if int(row["IsHidden"]) == 1 else False
                vip_event.isCancelled = True if int(row["IsCancelled"]) == 1 else False
                vip_event.cancelledDate = (
                    str(row["CancelledDate"])
                    if (
                        vip_event.isCancelled is True
                        and row["CancelledDate"] is not None
                    )
                    else None
                )
                events.append(vip_event)

        events.sort(key=operator.attrgetter("eventDate", "title", "externalEventId"))

        return events

    def get_orders(
        self,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        show_inactive: bool = False,
        show_deleted: bool = False,
        show_hidden: bool = False,
        ignore_flags: bool = False,
        show_cancelled: bool = False,
    ):
        """
        Retreive order data from database
        """
        orders: list[VipOrder] = []

        midnight_start: str = None
        if start is not None:
            midnight_start = datetime.fromtimestamp(start).strftime("%Y-%m-%d")

        midnight_end: str = None
        if end is not None:
            end_str = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            midnight_end_date = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(days=1)
            midnight_end = midnight_end_date.strftime("%Y-%m-%d")

        seller_event_category_ids: list[int] = []
        if seller_id is not None:
            seller = Seller(seller_id)
            seller_event_category_ids = seller.getSellerEventCategoryIds()
            # prevent against returning every event in the database
            if len(seller_event_category_ids) == 0:
                return []

        sql = """SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate,
                    ExchangeRates.Symbol,
                    UPPER(ExchangeRates.ServiceTokenId) AS CurrencyAbbrev, 
                    TicketSocketOrders.*,
                    TicketSocketEvents.Title as EventTitle, 
                    TicketSocketEvents.EventDate, 
                    Sellers.Name AS SellerName, 
                    Sellers.SellerId, 
                    TicketSocketEvents.Venue, 
                    TicketSocketEvents.Address AS EventAddress, 
                    TicketSocketEvents.City AS EventCity, 
                    TicketSocketEvents.State AS EventState, 
                    TicketSocketEvents.Zip AS EventZip, 
                    TicketSocketEvents.Country AS EventCountry 
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

        where_clause: list[str] = []

        if ignore_flags is not True:
            if show_deleted is not True:
                where_clause.append("TicketSocketOrders.IsDeleted = 0")
            else:
                show_inactive = True

            if show_inactive is True:
                where_clause.append("TicketSocketOrders.IsActive = 0")
            else:
                where_clause.append("TicketSocketOrders.IsActive = 1")

            if show_hidden is not True:
                where_clause.append("TicketSocketOrders.IsHidden = 0")

            if show_cancelled is not True:
                where_clause.append("TicketSocketEvents.IsCancelled = 0")

        if len(seller_event_category_ids) > 0:
            seller_event_category_id_str = convertListToParameters(
                seller_event_category_ids, data, "sellerEventCategoryId"
            )
            where_clause.append(
                "TicketSocketEvents.SellerEventCategoryId IN "
                + seller_event_category_id_str
            )

        both_dates_sql = """((TicketSocketOrders.PurchaseDate
                            BETWEEN %(startDate)s AND %(endDate)s) OR
                            (TicketSocketOrders.RefundDate IS NOT NULL 
                                AND TicketSocketOrders.RefundDate 
                                BETWEEN %(startDate)s AND %(endDate)s) OR
                            (TicketSocketOrders.ChargebackDate IS NOT NULL
                                AND TicketSocketOrders.ChargebackDate
                                BETWEEN %(startDate)s AND %(endDate)s))"""

        start_date_sql = """((TicketSocketOrders.PurchaseDate >= %(startDate)s) OR
                          (TicketSocketOrders.RefundDate IS NOT NULL
                            AND TicketSocketOrders.RefundDate >= %(startDate)s) OR
                          (TicketSocketOrders.ChargebackDate IS NOT NULL
                            AND TicketSocketOrders.ChargebackDate >= %(startDate)s))"""

        if midnight_start is not None and midnight_end is not None:
            where_clause.append(both_dates_sql)
            data["startDate"] = midnight_start
            data["endDate"] = midnight_end
        elif end is not None:
            where_clause.append(start_date_sql)
            data["startDate"] = datetime.now().strftime("%Y-%m-%d")
            data["endDate"] = midnight_end
        elif start is not None:
            where_clause.append(start_date_sql)
            data["startDate"] = midnight_start
        elif seller_id is None:
            where_clause.append(start_date_sql)
            data["startDate"] = datetime.now().strftime("%Y-%m-%d")

        if len(where_clause) > 0:
            sql += " AND ".join(where_clause)

        sql += """ ORDER BY TicketSocketOrders.PurchaseDate ASC,
                   TicketSocketEvents.EventDate ASC, 
                   TicketSocketEvents.Title ASC"""

        sql = sql.replace("\n", "")

        order_rows = queryAll(sql, data)
        for row in order_rows:
            order_id = int(row["OrderId"])
            event_id = int(row["EventId"])
            ticket_socket_order_id = int(row["Id"])
            order = VipOrder(order_id, event_id)
            order.eventTitle = str(row["EventTitle"])
            order.venue = str(row["Venue"])
            order.eventAddress = str(row["EventAddress"])
            order.eventCity = str(row["EventCity"])
            order.eventState = str(row["EventState"])
            order.eventZip = str(row["EventZip"])
            order.eventCountry = str(row["EventCountry"])
            order.eventDate = str(row["EventDate"])
            order.sellerName = str(row["SellerName"])
            order.sellerId = int(row["seller_id"])
            order.ticketSocketEventId = int(row["TicketSocketEventId"])
            order.ticketSocketOrderId = ticket_socket_order_id
            order.numTickets = int(row["NumTickets"])
            order.purchaseDate = str(row["PurchaseDate"])
            order.purchaseTimestamp = str(row["PurchaseTimestamp"])
            order.userId = int(row["UserId"])
            order.phone = str(row["Phone"]) if row["Phone"] is not None else None
            order.email = str(row["Email"]) if row["Email"] is not None else None
            order.purchaserLastName = (
                str(row["PurchaserLastName"])
                if row["PurchaserLastName"] is not None
                else None
            )
            order.purchaserFirstName = (
                str(row["PurchaserFirstName"])
                if row["PurchaserFirstName"] is not None
                else None
            )
            order.purchaserCity = (
                str(row["PurchaserCity"]) if row["PurchaserCity"] is not None else None
            )
            order.purchaserState = (
                str(row["PurchaserState"])
                if row["PurchaserState"] is not None
                else None
            )
            order.purchaserZipCode = (
                str(row["PurchaserZip"]) if row["PurchaserZip"] is not None else None
            )
            order.purchaserCountry = (
                str(row["PurchaserCountry"])
                if row["PurchaserCountry"] is not None
                else None
            )
            order.purchaserIpAddress = (
                str(row["PurchaserIpAddress"])
                if row["PurchaserIpAddress"] is not None
                else None
            )
            order.revenue = float(row["Revenue"])
            order.serviceFees = float(row["ServiceFees"])
            order.exchangeRate = float(row["ExchangeRate"])
            order.currencyAbbrev = str(row["CurrencyAbbrev"])
            order.currencySymbol = str(row["Symbol"])
            order.is_active = True if int(row["IsActive"]) == 1 else False
            order.isDeleted = True if int(row["IsDeleted"]) == 1 else False
            order.isHidden = True if int(row["IsHidden"]) == 1 else False

            if order.isDeleted is True:
                order.is_active = False
                order.isHidden = False
            shirt_str = str(row["Shirts"]).strip() if row["Shirts"] is not None else None
            shirts = []
            if shirt_str is not None and shirt_str != "":
                shirt_array = shirt_str.split("/")
                for shirt in shirt_array:
                    shirts.append(shirt.strip())
            order.shirts = shirts
            tickets = self.__get_tickets_from_order_id(ticket_socket_order_id)
            order.tickets = tickets
            order.getTotals()
            orders.append(order)
        return orders

    def get_daily_order_data_from_orders(self, year: int = 0, seller_id: int = None):
        """
        extracts daily order data for update to database
        """
        daily_order_data: list[DailyOrderData] = []
        month: int = 0
        day: int = 0
        current_year: int = 0

        if year > 0:
            current_year = year
            month = 12
            day = 31
        else:
            current_year = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day

        start = datetime.strptime(
            f"{current_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
        ).timestamp()
        end = datetime(current_year, month, day).timestamp()

        orders: list[VipOrder] = self.get_orders(
            start=start, end=end, ignore_flags=True, seller_id=seller_id
        )

        regular_orders: int = 0
        refund_orders: int = 0

        for order in orders:
            if order.isDeleted is True:
                continue

            purchase_timestamp = datetime.strptime(
                order.purchaseDate, "%Y-%m-%d"
            ).timestamp()

            order_data: DailyOrderData = None
            found_index: int = -1

            refund_order_data: DailyOrderData = None
            found_refund_index: int = -1

            for idx, x in enumerate(daily_order_data):
                if x.ticketSocketEventId == order.ticketSocketEventId:
                    if (
                        order.hasRefunds is True
                        and x.ticketSocketOrderId == order.ticketSocketOrderId
                    ) or (
                        order.hasChargebacks is True
                        and x.ticketSocketOrderId == order.ticketSocketOrderId
                    ):
                        refund_order_data = x
                        found_refund_index = idx
                    elif x.purchaseDate == order.purchaseDate:
                        order_data = x
                        found_index = idx
                        break

            if (
                order.hasRefunds is True
                and refund_order_data is None
            ):
                refund_order_data = DailyOrderData(
                    order.refundDate, order.ticketSocketEventId
                )
                refund_order_data.ticketSocketOrderId = order.ticketSocketOrderId
                refund_order_data.isRefunded = True
                refund_order_data.isChargeback = False
            elif (
                order.hasChargebacks is True
                and refund_order_data is None
            ):
                refund_order_data = DailyOrderData(
                    order.chargebackDate, order.ticketSocketEventId
                )
                refund_order_data.ticketSocketOrderId = order.ticketSocketOrderId
                refund_order_data.isRefunded = False
                refund_order_data.isChargeback = True

            if order_data is None and (
                purchase_timestamp >= start and purchase_timestamp <= end
            ):
                order_data = DailyOrderData(
                    order.purchaseDate, order.ticketSocketEventId
                )
                order_data.ticketSocketOrderId = None
                order_data.isRefunded = False
                order_data.isChargeback = False

            if refund_order_data is not None:
                refund_order_data.numTicketsRefunded += order.numTicketsRefunded
                refund_order_data.revenueRefunded += order.revenueRefunded
                refund_order_data.serviceFeeRevenueRefunded += (
                    order.serviceFeeRevenueRefunded
                )

            if order_data is not None:
                order_data.orders += 1
                order_data.tickets += order.numTickets
                order_data.ticketRevenueUsd += order.revenueUsd
                order_data.serviceFeesRevenueUsd += order.serviceFeesUsd
                order_data.totalRevenueUsd += order.revenueUsd + order.serviceFeesUsd

            if order_data is not None:
                regular_orders += 1
                if found_index >= 0:
                    daily_order_data[found_index] = order_data
                else:
                    daily_order_data.append(order_data)

            if refund_order_data is not None:
                refund_orders += 1
                if found_refund_index >= 0:
                    daily_order_data[found_refund_index] = refund_order_data
                else:
                    daily_order_data.append(refund_order_data)

        return daily_order_data

    def update_daily_order_data(
        self, history: TicketSocketRefreshHistory, year: int = 0, seller_id: int = None
    ):
        """
        Pulls order data from the database and rolls it up to DailyOrderData
        """
        logMessage("Starting update of daily order data")
        timer: float = time.time()
        duration: float = 0
        daily_order_data = self.get_daily_order_data_from_orders(year, seller_id)
        duration = time.time() - timer
        logMessage(f"Daily order data fetch completed in {duration} seconds")

        history.order_data_rows_total = len(daily_order_data)

        if len(daily_order_data) <= 0:
            history.order_data_update_succeeded = False
            return history

        logMessage("Daily order data - starting database update")

        success = True
        updates: int = 0
        inserts: int = 0
        for order_data in daily_order_data:
            sql = """SELECT DailyOrderDataId FROM DailyOrderData
                        WHERE TicketSocketEventId=%(ticketSocketEventId)s
                        AND PurchaseDate=DATE(%(purchaseDate)s)"""
            data = {
                "ticketSocketEventId": order_data.ticketSocketEventId,
                "purchaseDate": order_data.purchaseDate,
            }

            if order_data.ticketSocketOrderId is not None:
                sql += """ AND TicketSocketOrderId=%(ticketSocketOrderId)s"""
                data["ticketSocketOrderId"] = order_data.ticketSocketOrderId
            else:
                sql += """ AND TicketSocketOrderId IS NULL"""

            existing_data = queryOne(sql, data)

            update_data = {
                "purchaseDate": order_data.purchaseDate,
                "ticketSocketEventId": order_data.ticketSocketEventId,
                "orders": order_data.orders,
                "tickets": order_data.tickets,
                "ticketRevenue": order_data.ticketRevenueUsd,
                "serviceFeeRevenue": order_data.serviceFeesRevenueUsd,
                "totalRevenue": order_data.totalRevenueUsd,
                "isRefunded": 1 if order_data.isRefunded is True else 0,
                "isChargeback": 1 if order_data.isChargeback is True else 0,
                "numTicketsRefunded": order_data.numTicketsRefunded,
                "revenueRefunded": order_data.revenueRefunded,
                "serviceFeeRevenueRefunded": order_data.serviceFeeRevenueRefunded,
                "ticketSocketOrderId": order_data.ticketSocketOrderId,
            }

            if existing_data:
                daily_order_data_id = int(existing_data["DailyOrderDataId"])
                update_sql = """UPDATE DailyOrderData SET Orders=%(orders)s, Tickets=%(tickets)s,
                                TicketRevenue=%(ticketRevenue)s,
                                ServiceFeeRevenue=%(serviceFeeRevenue)s,
                                TotalRevenue=%(totalRevenue)s, IsRefunded=%(isRefunded)s, 
                                IsChargeback=%(isChargeback)s,
                                NumTicketsRefunded=%(numTicketsRefunded)s,
                                RevenueRefunded=%(revenueRefunded)s,
                                ServiceFeeRevenueRefunded=%(serviceFeeRevenueRefunded)s,
                                TicketSocketOrderId=%(ticketSocketOrderId)s, 
                                LastUpdate=CURRENT_TIMESTAMP
                                WHERE DailyOrderDataId=%(dailyOrderDataId)s"""
                update_data["dailyOrderDataId"] = daily_order_data_id
                success = update(update_sql, update_data)
                if success:
                    updates += 1
            else:
                insert_sql = """INSERT INTO DailyOrderData (PurchaseDate, TicketSocketEventId,
                                    Orders, Tickets, TicketRevenue, ServiceFeeRevenue,
                                    TotalRevenue, IsRefunded, IsChargeback, NumTicketsRefunded,
                                    RevenueRefunded, ServiceFeeRevenueRefunded, 
                                    TicketSocketOrderId) VALUES (%(purchaseDate)s,
                                    %(ticket_socket_event_id)s, %(orders)s, %(tickets)s,
                                    %(ticketRevenue)s, %(serviceFeeRevenue)s, %(totalRevenue)s,
                                    %(isRefunded)s, %(isChargeback)s, %(numTicketsRefunded)s,
                                    %(revenueRefunded)s, %(serviceFeeRevenueRefunded)s,
                                    %(ticket_socket_order_id)s )"""

                daily_order_data_id = insert(insert_sql, update_data)
                success = daily_order_data_id > 0
                if success:
                    inserts += 1
            if success is not True:
                break

        duration = time.time() - timer
        history.setOrderUpdateSuccess(success, duration, inserts, updates)

        logMessage(f"Daily order data - update complete in {duration} seconds")

        return history

    def get_dashboard_data(self, year: int = 0):
        """
        Fetch most data needed for admin dashboard display
        """
        daily_order_data: list[DailyOrderData] = []
        month: int = 0
        day: int = 0
        current_year: int = 0
        now = None

        if year > 0:
            current_year = year
            month = 12
            day = 31
        else:
            current_year = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day

        now = datetime(current_year, month, day) + timedelta(days=1)
        dash_totals = DashboardTotals(current_year, month, day)

        start = f"{current_year}-01-01 00:00:00"
        end = now.strftime("%Y-%m-%d %H:%M:%S")

        sql = """SELECT DailyOrderData.*,
                    TicketSocketEvents.Title AS EventTitle,
                    TicketSocketEvents.EventDate,
                    TicketSocketEvents.Venue,
                    TicketSocketEvents.City,
                    TicketSocketEvents.State,
                    TicketSocketEvents.Country,
                    TicketSocketEvents.Zip, 
                    Sellers.Name AS SellerName,
                    Sellers.SellerId,
                    TicketSocket.TicketSocketId,
                    TicketSocket.AccountName 
                    FROM DailyOrderData 
                    JOIN TicketSocketEvents 
                        ON TicketSocketEvents.Id
                            = DailyOrderData.TicketSocketEventId 
                    JOIN SellerEventCategory 
                        ON SellerEventCategory.SellerEventCategoryId
                            = TicketSocketEvents.SellerEventCategoryId 
                    JOIN TicketSocket 
                        ON TicketSocket.TicketSocketId
                            = SellerEventCategory.TicketSocketId 
                    JOIN Sellers
                        ON Sellers.SellerId = SellerEventCategory.SellerId 
                 WHERE DailyOrderData.PurchaseDate
                    BETWEEN %(start)s and %(end)s 
                    ORDER BY DailyOrderData.PurchaseDate, Sellers.Name"""
        data = {"start": start, "end": end}

        rows = queryAll(sql, data)
        for row in rows:
            purchase_date = str(row["PurchaseDate"])
            ticket_socket_event_id = int(row["TicketSocketEventId"])
            order_data = DailyOrderData(purchase_date, ticket_socket_event_id)
            order_data.eventTitle = str(row["EventTitle"])
            order_data.eventDate = str(row["EventDate"])
            order_data.seller_id = int(row["seller_id"])
            order_data.seller_name = str(row["SellerName"])
            order_data.venue = str(row["Venue"])
            order_data.city = str(row["City"])
            order_data.state = str(row["State"])
            order_data.country = str(row["Country"])
            order_data.zip = str(row["Zip"])
            order_data.tickets = int(row["Tickets"])
            order_data.orders = int(row["Orders"])
            order_data.ticketRevenueUsd = float(row["TicketRevenue"])
            order_data.serviceFeesRevenueUsd = float(row["ServiceFeeRevenue"])
            order_data.totalRevenueUsd = float(row["TotalRevenue"])
            order_data.ticketSocketId = int(row["TicketSocketId"])
            order_data.ticket_socket_order_id = (
                int(row["TicketSocketOrderId"])
                if row["TicketSocketOrderId"] is not None
                else None
            )
            order_data.isRefunded = True if int(row["IsRefunded"]) == 1 else False
            order_data.isChargeback = True if int(row["IsChargeback"]) == 1 else False
            order_data.numTicketsRefunded = int(row["NumTicketsRefunded"])
            order_data.revenueRefunded = float(row["RevenueRefunded"])
            order_data.serviceFeeRevenueRefunded = float(
                row["ServiceFeeRevenueRefunded"]
            )

            dash_totals.tickets += order_data.tickets
            dash_totals.orders += order_data.orders
            dash_totals.numTicketsRefunded += order_data.numTicketsRefunded
            dash_totals.revenueRefunded += order_data.revenueRefunded
            dash_totals.serviceFeeRevenueRefunded += order_data.serviceFeeRevenueRefunded
            dash_totals.ticketRevenueUsd += order_data.ticketRevenueUsd
            dash_totals.serviceFeesRevenueUsd += order_data.serviceFeesRevenueUsd
            dash_totals.totalRevenueUsd += order_data.totalRevenueUsd

            daily_order_data.append(order_data)

        dash_totals.daily_order_data = daily_order_data
        dash_totals.pricePerTicket = (
            dash_totals.ticketRevenueUsd - dash_totals.revenueRefunded
        ) / dash_totals.tickets
        dash_totals.serviceFeePerTicket = (
            dash_totals.serviceFeesRevenueUsd - dash_totals.serviceFeeRevenueRefunded
        ) / dash_totals.tickets
        return dash_totals

    def __get_ticket_types_from_event_id(self, ticket_socket_event_id: int):
        """
        Fetch from TicketSocketTickeTypes based on event Id
        """
        ticket_types: list[TicketSocketTicketType] = []

        sql = """SELECT TicketSocketTicketTypes.*
                    FROM TicketSocketTicketTypes
                    WHERE TicketSocketTicketTypes.TicketSocketEventId=%(ticketSocketEventId)s 
                    ORDER BY TicketSocketTicketTypes.TicketTypeName"""
        data = {"ticketSocketEventId": ticket_socket_event_id}

        rows = queryAll(sql, data)
        for row in rows:
            ticket_type_id = int(row["TicketSocketTicketTypeId"])
            name = str(row["TicketTypeName"])
            total = int(row["TotalAvailable"])
            is_active: bool = int(row["IsActive"]) == 1
            ticket_type = TicketSocketTicketType(
                ticket_socket_event_id, ticket_type_id, name, total, is_active
            )
            ticket_types.append(ticket_type)

        return ticket_types

    def __get_orders_from_event_id(
        self,
        ticket_socket_event_id: int,
        show_inactive: bool = False,
        show_deleted: bool = False,
        show_hidden: bool = False,
        ignore_flags: bool = False,
    ):
        orders: list[VipOrder] = []
        sql = """SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate,
                    ExchangeRates.Symbol, UPPER(ExchangeRates.ServiceTokenId) AS CurrencyAbbrev,
                    TicketSocketOrders.*, TicketSocketEvents.Title as EventTitle,
                    TicketSocketEvents.EventDate, Sellers.Name AS SellerName,
                    Sellers.SellerId, TicketSocketEvents.Venue, 
                    TicketSocketEvents.Address AS EventAddress,
                    TicketSocketEvents.City AS EventCity,
                    TicketSocketEvents.State AS EventState, 
                    TicketSocketEvents.Zip AS EventZip,
                    TicketSocketEvents.Country AS EventCountry 
                    FROM TicketSocketOrders
                    JOIN TicketSocketEvents 
                        ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN SellerEventCategory 
                        ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId 
                    JOIN Sellers 
                        ON Sellers.SellerId = SellerEventCategory.SellerId 
                    JOIN TicketSocket 
                        ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId
                    JOIN ExchangeRates 
                        ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                    LEFT JOIN ExchangeRateHistory 
                        ON ExchangeRateHistory.ExchangeRateId = ExchangeRates.ExchangeRateId 
                        AND ExchangeRateHistory.MidnightDate = TicketSocketOrders.PurchaseDate
                    WHERE TicketSocketOrders.TicketSocketEventId=%(ticketSocketEventId)s"""
        data = {"ticketSocketEventId": ticket_socket_event_id}

        if show_deleted is not True and ignore_flags is not True:
            sql += """ AND TicketSocketOrders.IsDeleted = 0"""

        if show_hidden is not True and ignore_flags is not True:
            sql += """ AND TicketSocketOrders.IsHidden = 0"""

        if show_inactive is not True and ignore_flags is not True:
            sql += """ AND TicketSocketOrders.IsActive = 1"""

        sql += """ ORDER BY TicketSocketOrders.PurchaserLastName ASC,
                    TicketSocketOrders.PurchaserFirstName ASC"""

        rows = queryAll(sql, data)
        for row in rows:
            order_id = int(row["OrderId"])
            event_id = int(row["EventId"])
            ticket_socket_order_id = int(row["Id"])
            order = VipOrder(order_id, event_id)
            order.venue = str(row["Venue"])
            order.eventTitle = str(row["EventTitle"])
            order.eventAddress = str(row["EventAddress"])
            order.eventCity = str(row["EventCity"])
            order.eventState = str(row["EventState"])
            order.eventZip = str(row["EventZip"])
            order.eventCountry = str(row["EventCountry"])
            order.eventDate = str(row["EventDate"])
            order.seller_name = str(row["SellerName"])
            order.sellerId = int(row["seller_id"])
            order.ticketSocketEventId = ticket_socket_event_id
            order.ticketSocketOrderId = ticket_socket_order_id
            order.numTickets = int(row["NumTickets"])
            order.purchaseDate = str(row["PurchaseDate"])
            order.purchaseTimestamp = str(row["PurchaseTimestamp"])
            order.user_id = int(row["UserId"])
            order.phone = str(row["Phone"]) if row["Phone"] is not None else None
            order.email = str(row["Email"]) if row["Email"] is not None else None
            order.purchaserLastName = (
                str(row["PurchaserLastName"])
                if row["PurchaserLastName"] is not None
                else None
            )
            order.purchaserFirstName = (
                str(row["PurchaserFirstName"])
                if row["PurchaserFirstName"] is not None
                else None
            )
            order.purchaserCity = (
                str(row["PurchaserCity"]) if row["PurchaserCity"] is not None else None
            )
            order.purchaserState = (
                str(row["PurchaserState"])
                if row["PurchaserState"] is not None
                else None
            )
            order.purchaserZipCode = (
                str(row["PurchaserZip"]) if row["PurchaserZip"] is not None else None
            )
            order.purchaserCountry = (
                str(row["PurchaserCountry"])
                if row["PurchaserCountry"] is not None
                else None
            )
            order.purchaserIpAddress = (
                str(row["PurchaserIpAddress"])
                if row["PurchaserIpAddress"] is not None
                else None
            )
            order.revenue = float(row["Revenue"])
            order.serviceFees = float(row["ServiceFees"])
            order.exchangeRate = float(row["ExchangeRate"])
            order.currencyAbbrev = str(row["CurrencyAbbrev"])
            order.currencySymbol = str(row["Symbol"])
            order.isActive = True if int(row["IsActive"]) == 1 else False
            order.isDeleted = True if int(row["IsDeleted"]) == 1 else False
            order.isHidden = True if int(row["IsHidden"]) == 1 else False

            if order.isDeleted is True:
                order.is_active = False
                order.isHidden = False
            shirt_str = str(row["Shirts"]).strip() if row["Shirts"] is not None else None
            shirts = []
            if shirt_str is not None and shirt_str != "":
                shirt_array = shirt_str.split("/")
                for shirt in shirt_array:
                    shirts.append(shirt.strip())
            order.shirts = shirts
            tickets = self.__get_tickets_from_order_id(ticket_socket_order_id)
            order.tickets = tickets
            order.getTotals()
            orders.append(order)
        return orders

    def __get_tickets_from_order_id(self, ticket_socket_order_id: int):
        tickets: list[VipTicket] = []
        sql = """SELECT * FROM TicketSocketOrderTickets
                    WHERE TicketSocketOrderId=%(ticket_socket_order_id)s
                    AND IsActive=1"""
        data = {"ticket_socket_order_id": ticket_socket_order_id}

        rows = queryAll(sql, data)
        for row in rows:
            ticket_id: int = 0
            if row["TicketId"] is not None and row["TicketId"] != "":
                ticket_id = int(row["TicketId"])
            ticket = VipTicket(
                ticket_id,
                str(row["TicketType"]),
                float(row["Price"]),
                float(row["ServiceFee"]),
                int(row["TicketSocketTicketTypeId"]),
                str(row["BarCode"]),
                int(row["AvailableScans"]),
                str(row["PurchaseLocation"]),
                int(row["ScannedTimestamp"]),
                str(row["AttendeeFirstName"]),
                str(row["AttendeeLastName"]),
            )
            ticket.ticket_socket_order_id = ticket_socket_order_id
            ticket.ticket_socket_order_ticket_id = int(row["Id"])
            ticket.is_checked_in = True if int(row["IsCheckedIn"]) == 1 else False
            is_refunded: bool = True if int(row["IsRefunded"]) == 1 else False
            ticket.isRefunded = is_refunded
            ticket.refundDate = (
                str(row["RefundDate"])
                if (is_refunded is True and row["RefundDate"] is not None)
                else None
            )
            is_charged_back: bool = True if int(row["IsChargedback"]) == 1 else False
            ticket.isChargedBack = is_charged_back
            ticket.chargebackDate = (
                str(row["ChargebackDate"])
                if (is_charged_back is True and row["ChargebackDate"] is not None)
                else None
            )
            tickets.append(ticket)
        return tickets

    def disable_events(self, ticket_socket_event_ids: list[int], disabled: bool):
        """
        Marks eventIds as disabled
        """
        success: bool = True
        for ticket_socket_event_id in ticket_socket_event_ids:
            sql = """UPDATE TicketSocketEvents
                        SET IsActive=%(is_active)s,
                        LastUpdate=CURRENT_TIMESTAMP
                    WHERE Id=%(ticket_socket_event_id)s"""
            data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "is_active": 0 if disabled is True else 1,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def delete_events(self, ticket_socket_event_ids: list[int], deleted: bool):
        """
        Marks eventIds as deleted
        """
        success: bool = True
        for ticket_socket_event_id in ticket_socket_event_ids:
            sql = """UPDATE TicketSocketEvents
                        SET IsDeleted=%(isDeleted)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_event_id)s"""
            data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "isDeleted": 1 if deleted is True else 0,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def hide_events(self, ticket_socket_event_ids: list[int], hidden: bool):
        """
        Marks events as hidden
        """
        success: bool = True
        for ticket_socket_event_id in ticket_socket_event_ids:
            sql = """UPDATE TicketSocketEvents
                        SET IsHidden=%(isHidden)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_event_id)s"""
            data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "isHidden": 1 if hidden is True else 0,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def disable_orders(self, ticket_socket_order_ids: list[int], disabled: bool):
        """
        Marks orders as disabled
        """
        success: bool = True
        for ticket_socket_order_id in ticket_socket_order_ids:
            sql = """UPDATE TicketSocketOrders
                        SET IsActive=%(is_active)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_order_id)s"""
            data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "is_active": 0 if disabled is True else 1,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def delete_orders(self, ticket_socket_order_ids: list[int], deleted: bool):
        """
        Marks orders as deleted
        """
        success: bool = True
        for ticket_socket_order_id in ticket_socket_order_ids:
            sql = """UPDATE TicketSocketOrders
                        SET IsDeleted=%(isDeleted)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_order_id)s"""
            data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "isDeleted": 1 if deleted is True else 0,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def hide_orders(self, ticket_socket_order_ids: list[int], hidden: bool):
        """
        Marks orders as hidden
        """
        success: bool = True
        for ticket_socket_order_id in ticket_socket_order_ids:
            sql = """UPDATE TicketSocketOrders
                        SET IsHidden=%(isHidden)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_order_id)s"""
            data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "isHidden": 1 if hidden is True else 0,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def check_in_tickets(self, ticket_socket_order_ticket_ids: list[int], checked_in: bool):
        """
        Marks tickets as checked in
        """
        success: bool = True
        for ticket_socket_order_ticket_id in ticket_socket_order_ticket_ids:
            sql = """UPDATE TicketSocketOrderTickets
                        SET IsCheckedIn=%(checkedIn)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_order_ticket_id)s"""
            data = {
                "ticket_socket_order_ticket_id": ticket_socket_order_ticket_id,
                "checkedIn": 1 if checked_in is True else 0,
            }
            success = update(sql, data)
            if success is False:
                break
        return success

    def cancel_event(
        self,
        ticket_socket_event_id: int,
        refund_service_fees: bool = False,
    ):
        """
        Cancels event, refunding all orders and/or service fees
        """
        success: bool = True
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        sql = """UPDATE TicketSocketEvents
                    SET IsCancelled=1,
                    CancelledDate=CURRENT_TIMESTAMP,
                    LastUpdate=CURRENT_TIMESTAMP
                    WHERE Id=%(ticket_socket_event_id)s"""
        success = update(sql, data)
        if success is True:
            success = self.refund_all_event_orders(ticket_socket_event_id, refund_service_fees)
        return success

    def refund_all_event_orders(
        self,
        ticket_socket_event_id: int,
        refund_service_fees: bool = False,
        mark_chargeback: bool = False
    ):
        """
        Refunds all orders in an event one at a time
        """
        success: bool = True
        sql = """SELECT Id FROM TicketSocketOrders
                    WHERE TicketSocketEventId=%(ticket_socket_event_id)s"""
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        rows = queryAll(sql, data)
        if len(rows) > 0:
            for row in rows:
                order_id = int(row["Id"])
                success = self.refund_order(order_id, refund_service_fees, mark_chargeback)
                if success is False:
                    break
        return success

    def refund_order(
        self,
        ticket_socket_order_id: int,
        refund_service_fees: bool = False,
        mark_chargeback: bool = False,
    ):
        """
        Refunds all tickets in an order
        """
        ticket_sql = (
            """UPDATE TicketSocketOrderTickets SET LastUpdate=CURRENT_TIMESTAMP"""
        )
        if mark_chargeback is True:
            ticket_sql += """, IsChargedBack=1, IsRefunded=0,
                            ChargebackDate=CURRENT_TIMESTAMP, RefundDate=NULL"""
        else:
            ticket_sql += """, IsRefunded=1, IsChargedBack=0,
                            RefundDate=CURRENT_TIMESTAMP, ChargebackDate=NULL"""
        if refund_service_fees is True:
            ticket_sql += """, ServiceFeeRevenueRefunded=ServiceFees"""
        ticket_sql += """ WHERE TicketSocketOrderId=%(ticket_socket_order_id)s"""
        ticket_data = {"ticket_socket_order_id": ticket_socket_order_id}
        success = update(ticket_sql, ticket_data)

        return success

    def update_event(self, event_to_update: VipEvent):
        """
        Update single event from admin
        """
        success: bool = True
        if event_to_update is None or event_to_update.ticketSocketEventId <= 0:
            return False

        ticket_socket_event_id: int = event_to_update.ticketSocketEventId
        sql = """SELECT * FROM TicketSocketEvents WHERE Id=%(ticket_socket_event_id)s"""
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        existing_event: VipEvent = queryOne(sql, data)

        if existing_event is not None:
            update_sql = """UPDATE TicketSocketEvents
                             SET IsActive=%(is_active)s, 
                             IsDeleted=%(isDeleted)s, 
                             IsAddedToBandsInTown=%(isAddedToBandsInTown)s, 
                             IsHidden=%(isHidden)s, 
                             AnnounceDate=%(announceDate)s, 
                             LastUpdate=CURRENT_TIMESTAMP 
                             WHERE Id=%(ticket_socket_event_id)s"""
            update_data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "is_active": (
                    1
                    if event_to_update.isActive is True
                    and event_to_update.isDeleted is False
                    else 0
                ),
                "isDeleted": 1 if event_to_update.isDeleted is True else 0,
                "isAddedToBandsInTown": (
                    1 if event_to_update.isAddedToBandsInTown is True else 0
                ),
                "isHidden": 1 if event_to_update.isHidden is True else 0,
                "announceDate": event_to_update.announceDate
            }
            success = update(update_sql, update_data)

            if event_to_update.isDeleted is False and len(event_to_update.ticketTypes) > 0:
                for ticket_type in event_to_update.ticketTypes:
                    ticket_type_wql = """UPDATE TicketSocketTicketTypes
                                        SET IsActive=%(is_active)s, LastUpdate=CURRENT_TIMESTAMP 
                                        WHERE TicketSocketTicketTypeId=%(ticket_type_id)s 
                                        AND TicketSocketEventId=%(ticket_socket_event_id)s"""
                    ticket_type_data = {
                        "ticket_type_id": ticket_type.ticketTypeId,
                        "ticket_socket_event_id": ticket_socket_event_id,
                        "is_active": 1 if ticket_type.isActive is True else 0,
                    }
                    success = update(ticket_type_wql, ticket_type_data)
                    if success is False:
                        break
        return success

    def update_order(self, order_to_update: VipOrder):
        """
        Update single order from admin
        """
        success: bool = True
        if order_to_update is None or order_to_update.ticketSocketOrderId <= 0:
            return False

        ticket_socket_order_id: int = order_to_update.ticketSocketOrderId
        sql = """SELECT * FROM TicketSocketOrders WHERE Id=%(ticket_socket_order_id)s"""
        data = {"ticket_socket_order_id": ticket_socket_order_id}
        existing_order: VipOrder = queryOne(sql, data)

        if existing_order is not None:
            update_sql = """UPDATE TicketSocketOrders
                             SET IsActive=%(is_active)s, 
                             IsDeleted=%(isDeleted)s, 
                             IsHidden=%(isHidden)s, 
                             Revenue=%(revenue)s, 
                             ServiceFees=%(serviceFees)s, 
                             LastUpdate=CURRENT_TIMESTAMP 
                             WHERE Id=%(ticket_socket_order_id)s"""
            update_data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "revenue": (
                    order_to_update.revenue if order_to_update.revenue != "None" else 0
                ),
                "serviceFees": (
                    order_to_update.serviceFees
                    if order_to_update.serviceFees != "None"
                    else 0
                ),
                "is_active": 1 if order_to_update.is_active is True else 0,
                "isDeleted": 1 if order_to_update.isDeleted is True else 0,
                "isHidden": 1 if order_to_update.isHidden is True else 0,
            }
            success = update(update_sql, update_data)
            if order_to_update.isDeleted is False and len(order_to_update.tickets) > 0:
                for ticket in order_to_update.tickets:
                    order_ticket_sql = """UPDATE TicketSocketOrderTickets
                                            SET Price=%(price)s, 
                                            ServiceFee=%(serviceFee)s, 
                                            IsCheckedIn=%(is_checked_in)s, 
                                            LastUpdate=CURRENT_TIMESTAMP 
                                            WHERE Id=%(ticketId)s 
                                            AND TicketSocketOrderId=%(ticket_socket_order_id)s"""
                    order_ticket_data = {
                        "ticketId": ticket.id,
                        "ticket_socket_order_id": ticket.ticketSocketOrderId,
                        "price": ticket.price,
                        "serviceFee": ticket.serviceFee,
                        "is_checked_in": 1 if ticket.is_checked_in is True else 0,
                    }
                    success = update(order_ticket_sql, order_ticket_data)
                    if success is False:
                        break
        return success

    def retrieve_ticket_socket_events_for_update(
        self, seller_id: int = None, start: int = None, end: int = None
    ):
        """
        Call TS API to retrieve updated event/order/ticket/ticket type data
        """
        # go get seller information from database
        seller: Seller = None

        if seller_id is not None:
            seller = Seller(seller_id)

        # fetch TS data
        ts_sql = "SELECT TicketSocketId, IsVip FROM TicketSocket"
        rows = queryAll(ts_sql)

        # query events across all TS services
        all_events: list[VipEvent] = []
        for row in rows:
            ticket_socket_id = int(row["TicketSocketId"])
            is_vip_service = int(row["IsVip"]) == 1
            tss = TicketSocketService(ticket_socket_id)

            # get event category for this TS account, if the seller has one
            event_category_id: int = None
            seller_event_category: SellerEventCategory = None
            if seller is not None:
                seller_event_category = seller.getSellerEventCategory(ticket_socket_id)

                # if we are restricting by seller and the seller doesn't have
                # a category on this TS service, just skip it or the service will
                # return everything for everyone in the time period
                if seller_event_category is not None:
                    event_category_id = seller_event_category.eventCategoryId
                else:
                    continue

            events = tss.getEventsAndOrders(event_category_id, start, end)

            if len(events) > 0:
                for event in events:
                    # convert ts events to vip events
                    vip_event = VipEvent(event.id, event.title)
                    vip_event.__dict__.update(event.__dict__)
                    vip_event.isVip = is_vip_service

                    # populate sellerEventCategoryId, which is required on our end
                    if seller_event_category is not None:
                        vip_event.sellerEventCategoryId = (
                            seller_event_category.sellerEventCategoryId
                        )
                    elif vip_event.eventCategoryId is not None:
                        seller_ec_temp = SellerEventCategory(
                            None, ticket_socket_id, vip_event.eventCategoryId
                        )
                        vip_event.sellerEventCategoryId = seller_ec_temp.sellerEventCategoryId

                    # if this combo of TS and category does not exist on our side,
                    # we can't update this event
                    if vip_event.sellerEventCategoryId is None:
                        continue

                    # convert the orders
                    orders: list[VipEvent] = []
                    for order in event.orders:
                        vip_order = VipOrder(order.id, order.eventId)
                        vip_order.__dict__.update(order.__dict__)
                        orders.append(vip_order)

                    vip_event.orders = orders

                    all_events.append(vip_event)

        return all_events

    def refresh_database_from_ticket_socket(
        self, seller_id: int = None, start: int = None, end: int = None, user_id: int = 0
    ):
        """
        Calls out to TS and refreshes objects in database
        """
        # logMessage('starting TS update')
        update_success: bool = True
        error_message: str = None

        # initialize counters
        start_timer: float = time.time()
        end_timer: float = 0
        duration: float = 0

        service_events_skipped: list[str] = []
        events_failed: list[int] = []
        orders_failed: list[int] = []
        ticket_types_failed: list[int] = []
        tickets_failed: list[int] = []
        total_events_from_service: int = 0
        events_updated: int = 0
        events_inserted: int = 0
        orders_inserted: int = 0
        orders_updated: int = 0
        orders_deleted: int = 0
        tickets_updated: int = 0
        tickets_inserted: int = 0
        ticket_types_updated: int = 0
        ticket_types_inserted: int = 0
        daily_order_data_rows_removed: int = 0
        results: TicketSocketRefreshHistory = None

        try:
            logMessage("retrieving events from TicketSocket Service")
            all_events = self.retrieve_ticket_socket_events_for_update(seller_id, start, end)
            # logMessage('events retrieved')

            service_timer = time.time()
            service_duration = service_timer - start_timer
            logMessage(
                "Service fetch done in " + str(service_duration) + " seconds"
            )

            # get total number of events grabbed from service
            total_events_from_service = len(all_events)

            logMessage("starting database update - opening connection")
            # get one database connection
            cnx = getDbConnection()

            if total_events_from_service > 0:

                service_events: list[int] = []
                for evt in all_events:
                    if evt.sellerEventCategoryId <= 0:
                        service_events_skipped.append(
                            evt.title
                            + " - eventId "
                            + str(evt.id)
                            + " ("
                            + evt.ticketSocketUrl
                            + ")"
                        )
                        continue

                    service_events.append(evt.id)
                    # compile event data for update
                    address = evt.venue.address1
                    if evt.venue and evt.venue.address2:
                        address += " " + evt.venue.address2

                    event_data = {
                        "title": evt.title.strip(),
                        "eventDate": evt.eventDate.strip(),
                        "utcTime": evt.utcTime,
                        "url": evt.ticketSocketUrl.strip(),
                        "venue": evt.venue.name.strip(),
                        "address": address.strip(),
                        "city": evt.venue.city.strip(),
                        "state": evt.venue.state.strip(),
                        "zip": evt.venue.postalCode.strip(),
                        "country": (
                            evt.venue.country.strip()
                            if evt.venue.country is not None
                            else None
                        ),
                        "onsale": 1 if evt.onSale else 0,
                        "thumbnail": (
                            evt.thumbnail.strip() if evt.thumbnail is not None else None
                        ),
                        "displayDate": (
                            evt.displayDate.strip()
                            if evt.displayDate is not None
                            else None
                        ),
                        "isVip": 1 if evt.isVip else 0,
                    }

                    # determine if event already exists
                    event_sql = """SELECT * FROM TicketSocketEvents
                                    WHERE EventId=%(event_id)s
                                    AND SellerEventCategoryId=%(sellerEventCategoryId)s"""

                    data = {
                        "event_id": evt.id,
                        "sellerEventCategoryId": evt.sellerEventCategoryId,
                    }

                    existing_event = queryOne(event_sql, data, cnx)

                    event_success: bool = False
                    ticket_socket_event_id: int = 0
                    event_add_new: bool = False

                    if existing_event:
                        # update existing event
                        ticket_socket_event_id = int(existing_event["Id"])
                        event_data["id"] = ticket_socket_event_id
                        sql = """UPDATE TicketSocketEvents SET Title=%(title)s,
                                EventDate=%(eventDate)s, UtcTime=%(utcTime)s, URL=%(url)s,
                                Venue=%(venue)s, Address=%(address)s, City=%(city)s,
                                State=%(state)s, Zip=%(zip)s, Country=%(country)s,
                                OnSale=%(onsale)s, Thumbnail=%(thumbnail)s,
                                DisplayDate=%(displayDate)s, IsVip=%(isVip)s,
                                LastUpdate=CURRENT_TIMESTAMP
                                WHERE Id=%(id)s"""
                        event_success = update(sql, event_data, cnx)
                    else:
                        event_add_new = True
                        # insert new event
                        event_data["event_id"] = int(evt.id)
                        event_data["sellerEventCategoryId"] = int(
                            evt.sellerEventCategoryId
                        )
                        sql = """INSERT INTO TicketSocketEvents (SellerEventCategoryId,
                                    EventId, Title, EventDate, UtcTime,
                                    URL, Venue, Address, City, State, Zip, Country, 
                                    OnSale, Thumbnail, DisplayDate, IsVip) 
                                    VALUES (%(sellerEventCategoryId)s, %(event_id)s, %(title)s,
                                    %(eventDate)s, %(utcTime)s, %(url)s, %(venue)s, %(address)s,
                                    %(city)s, %(state)s, %(zip)s, %(country)s, 
                                    %(onsale)s, %(thumbnail)s, %(displayDate)s, %(isVip)s)"""
                        ticket_socket_event_id = insert(sql, event_data, cnx)
                        event_success = ticket_socket_event_id > 0

                    # if the update succeeded, update counters
                    if event_success:
                        if event_add_new:
                            events_inserted += 1
                        else:
                            events_updated += 1
                    else:
                        # if that failed, just mark it failed and skip orders
                        events_failed.append(evt.id)
                        update_success = False
                        continue

                    if ticket_socket_event_id and len(evt.ticket_types) > 0:
                        event_ticket_types: list[int] = []
                        for ticket_type in evt.ticket_types:
                            event_ticket_types.append(ticket_type.ticket_type_id)

                            ticket_type_data = {
                                "ticketSocketTicketTypeId": ticket_type.ticket_type_id,
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "ticketTypeName": ticket_type.ticketTypeName,
                                "totalAvailable": ticket_type.totalAvailable,
                                "is_active": 1 if ticket_type.is_active else 0,
                            }

                            ticket_type_sql = """SELECT
                                    TicketSocketTicketTypes.*
                                    FROM TicketSocketTicketTypes 
                                    WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                    AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                            ticket_type_sql_data = {
                                "ticketSocketTicketTypeId": ticket_type.ticket_type_id,
                                "ticket_socket_event_id": ticket_socket_event_id,
                            }

                            existing_ticket_type = queryOne(
                                ticket_type_sql, ticket_type_sql_data, cnx
                            )

                            ticket_type_success: bool = False
                            ticket_socket_type_id: int = 0
                            ticket_type_add_new: bool = False

                            if existing_ticket_type:
                                # update existing ticket type
                                sql = """UPDATE TicketSocketTicketTypes
                                        SET TicketTypeName=%(ticketTypeName)s,
                                        TotalAvailable=%(totalAvailable)s,
                                        IsActive=%(is_active)s, 
                                        LastUpdate=CURRENT_TIMESTAMP 
                                        WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                        AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                                ticket_type_success = update(sql, ticket_type_data, cnx)
                            else:
                                ticket_type_add_new = True
                                # insert new ticket type
                                sql = """INSERT INTO TicketSocketTicketTypes
                                        (TicketSocketTicketTypeId, TicketSocketEventId,
                                            TicketTypeName, TotalAvailable, IsActive)
                                                VALUES (%(ticketSocketTicketTypeId)s,
                                                %(ticket_socket_event_id)s, %(ticketTypeName)s,
                                                %(totalAvailable)s, %(is_active)s)"""
                                ticket_socket_type_id = insert(sql, ticket_type_data, cnx)
                                ticket_type_success = ticket_socket_type_id > 0

                            # if the update succeeded, update counters
                            if ticket_type_success:
                                if ticket_type_add_new:
                                    ticket_types_inserted += 1
                                else:
                                    ticket_types_updated += 1
                            else:
                                # if that failed, mark it
                                ticket_types_failed.append(ticket_type.ticket_type_id)

                    if ticket_socket_event_id and len(evt.orders) > 0:
                        event_orders: list[int] = []
                        for order in evt.orders:
                            if order.event_id != evt.id:
                                continue
                            event_orders.append(order.id)
                            # compile order data for update
                            shirts: str = None
                            if len(order.shirts) > 0:
                                shirts = " / ".join(order.shirts)

                            order_data = {
                                "numTickets": order.numTickets,
                                "purchaseDate": order.purchaseDate.strip(),
                                "purchaseTimestamp": order.purchaseTimestamp.strip(),
                                "phone": (
                                    order.phone.strip()
                                    if order.phone is not None
                                    else None
                                ),
                                "shirts": shirts,
                                "user_id": order.user_id,
                                "event_id": order.event_id,
                                "purchaserLastName": (
                                    order.purchaserLastName.strip()
                                    if order.purchaserLastName is not None
                                    else None
                                ),
                                "purchaserFirstName": (
                                    order.purchaserFirstName.strip()
                                    if order.purchaserFirstName is not None
                                    else None
                                ),
                                "purchaserCity": (
                                    order.purchaserCity.strip()
                                    if (
                                        order.purchaserCity is not None
                                        and order.purchaserCity != ""
                                    )
                                    else None
                                ),
                                "purchaserState": (
                                    order.purchaserState.strip()
                                    if (
                                        order.purchaserState is not None
                                        and order.purchaserState != ""
                                    )
                                    else None
                                ),
                                "purchaserZip": (
                                    order.purchaserZipCode.strip()
                                    if (
                                        order.purchaserZipCode is not None
                                        and order.purchaserZipCode != ""
                                    )
                                    else None
                                ),
                                "purchaserCountry": (
                                    order.purchaserCountry.strip()
                                    if (
                                        order.purchaserCountry is not None
                                        and order.purchaserCountry != ""
                                    )
                                    else None
                                ),
                                "purchaserIpAddress": (
                                    order.purchaserIpAddress.strip()
                                    if (
                                        order.purchaserIpAddress is not None
                                        and order.purchaserIpAddress != ""
                                    )
                                    else None
                                ),
                                "email": (
                                    order.email.strip()
                                    if order.email is not None
                                    else None
                                ),
                            }

                            if order.revenue > 0:
                                order_data["revenue"] = order.revenue

                            if order.serviceFees > 0:
                                order_data["serviceFees"] = order.serviceFees

                            # determine if order already exists
                            order_sql = """SELECT TicketSocketOrders.*
                                            FROM TicketSocketOrders
                                            WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                            AND OrderId=%(order_id)s"""

                            data = {
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "order_id": order.id,
                            }

                            existing_order = queryOne(order_sql, data, cnx)

                            order_success: bool = False
                            ticket_socket_order_id: int = 0
                            order_add_new: bool = False

                            if existing_order:
                                ticket_socket_order_id = int(existing_order["Id"])
                                order_data["id"] = ticket_socket_order_id
                                # if purchase date changed, clear out daily order data for event
                                order_purchase_timestamp = datetime.strptime(
                                    order.purchaseDate, "%Y-%m-%d"
                                ).timestamp()
                                existing_purchase_timestamp = datetime.strptime(
                                    str(existing_order["PurchaseDate"]), "%Y-%m-%d"
                                ).timestamp()
                                if order_purchase_timestamp != existing_purchase_timestamp:
                                    check_cleanup_data = {
                                        "ticket_socket_event_id": ticket_socket_event_id,
                                        "purchaseDate": str(
                                            existing_order["PurchaseDate"]
                                        ),
                                    }
                                    check_cleanup_sql = """SELECT DailyOrderData.DailyOrderDataId
                                            FROM DailyOrderData
                                            WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                            AND PurchaseDate=DATE(%(purchaseDate)s)"""
                                    rows = queryAll(
                                        check_cleanup_sql, check_cleanup_data
                                    )
                                    if len(rows) > 0:
                                        for row in rows:
                                            cleanup_sql = """DELETE FROM DailyOrderData
                                                    WHERE DailyOrderDataId=%(dailyOrderDataId)s"""
                                            cleanup_data = {
                                                "dailyOrderDataId": int(
                                                    row["DailyOrderDataId"]
                                                )
                                            }
                                            del_success = delete(
                                                cleanup_sql, cleanup_data
                                            )
                                            if del_success is True:
                                                daily_order_data_rows_removed += 1

                                # update existing order
                                sql = """UPDATE TicketSocketOrders SET NumTickets=%(numTickets)s,
                                        PurchaseDate=%(purchaseDate)s, PurchaseTimestamp=%(purchaseTimestamp)s,
                                        Phone=%(phone)s, Shirts=%(shirts)s, EventId=%(event_id)s,
                                        UserId=%(user_id)s, PurchaserLastName=%(purchaserLastName)s,
                                        PurchaserFirstName=%(purchaserFirstName)s, PurchaserCity=%(purchaserCity)s, 
                                        PurchaserState=%(purchaserState)s, PurchaserZip=%(purchaserZip)s,
                                        PurchaserCountry=%(purchaserCountry)s,
                                        PurchaserIpAddress=%(purchaserIpAddress)s,
                                        Email=%(email)s, """
                                if order.revenue > 0:
                                    sql += """Revenue=%(revenue)s, """
                                if order.serviceFees > 0:
                                    sql += """ServiceFees=%(serviceFees)s, """
                                sql += (
                                    """LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                )

                                order_success = update(sql, order_data, cnx)
                            else:
                                order_add_new = True
                                # insert new order
                                order_data["order_id"] = int(order.id)
                                order_data["ticket_socket_event_id"] = ticket_socket_event_id
                                sql = """INSERT INTO TicketSocketOrders
                                            (TicketSocketEventId, OrderId, NumTickets,
                                            PurchaseDate, PurchaseTimestamp, Phone, Shirts, EventId, UserId,
                                            PurchaserLastName, PurchaserFirstName, PurchaserCity, PurchaserState,
                                            PurchaserZip, PurchaserCountry,
                                            PurchaserIpAddress, Email"""
                                if order.revenue > 0:
                                    sql += """, Revenue"""
                                if order.serviceFees > 0:
                                    sql += """, ServiceFees"""
                                sql += """) VALUES
                                    (%(ticket_socket_event_id)s, %(order_id)s, %(numTickets)s,
                                    %(purchaseDate)s, %(purchaseTimestamp)s, %(phone)s, %(shirts)s,
                                    %(event_id)s, %(user_id)s, %(purchaserLastName)s, %(purchaserFirstName)s,
                                    %(purchaserCity)s, %(purchaserState)s, %(purchaserZip)s, %(purchaserCountry)s,
                                    %(purchaserIpAddress)s,  %(email)s"""
                                if order.revenue > 0:
                                    sql += """, %(revenue)s"""
                                if order.serviceFees > 0:
                                    sql += """, %(serviceFees)s"""
                                sql += """)"""

                                ticket_socket_order_id = insert(sql, order_data, cnx)
                                order_success = ticket_socket_order_id > 0

                            # if the update succeeded, update counters
                            if order_success:
                                if order_add_new:
                                    orders_inserted += 1
                                else:
                                    orders_updated += 1
                            else:
                                # if that failed, just mark it failed and skip orders
                                orders_failed.append(order.id)
                                update_success = False
                                continue

                            if ticket_socket_order_id and len(order.tickets) > 0:
                                order_tickets: list[int] = []

                                # clean up any migrated data that doesn't have ticket Ids
                                delete_sql = """DELETE FROM TicketSocketOrderTickets
                                            WHERE TicketSocketOrderId=%(ticket_socket_order_id)s
                                            AND TicketId IS NULL"""
                                delete_data = {
                                    "ticket_socket_order_id": ticket_socket_order_id
                                }
                                delete(delete_sql, delete_data)

                                for ticket in order.tickets:
                                    order_tickets.append(ticket.id)
                                    # compile ticket data for update
                                    ticket_data = {
                                        "ticket_type": ticket.ticket_type.strip(),
                                        "ticket_type_id": ticket.ticket_type_id,
                                        "serviceFee": (
                                            ticket.serviceFee
                                            if ticket.serviceFee is not None
                                            else 0
                                        ),
                                        "availableScans": ticket.availableScans,
                                        "barcode": ticket.barcode,
                                        "purchaseLocation": ticket.purchaseLocation,
                                        "scannedTimestamp": ticket.scannedTimestamp,
                                        "attendeeFirstName": ticket.attendeeFirstName,
                                        "attendeeLastName": ticket.attendeeLastName,
                                    }

                                    ticket_price = (
                                        ticket.price if ticket.price is not None else 0
                                    )

                                    if ticket_price > 0:
                                        ticket_data["price"] = ticket_price

                                    # determine if ticket already exists
                                    ticket_sql = """SELECT TicketSocketOrderTickets.*
                                        FROM TicketSocketOrderTickets
                                        WHERE TicketSocketOrderId=%(ticket_socket_order_id)s
                                        AND TicketId=%(ticketId)s"""

                                    data = {
                                        "ticket_socket_order_id": ticket_socket_order_id,
                                        "ticketId": ticket.id,
                                    }

                                    existing_ticket = queryOne(ticket_sql, data, cnx)

                                    ticket_success: bool = False
                                    ticket_socket_order_ticket_id: int = 0
                                    ticket_add_new: bool = False

                                    if existing_ticket:
                                        # update existing ticket
                                        ticket_socket_order_ticket_id = int(
                                            existing_ticket["Id"]
                                        )
                                        is_checked_in = int(existing_ticket["IsCheckedIn"])
                                        if is_checked_in != 1:
                                            is_checked_in = (
                                                1 if ticket.scannedTimestamp != 0 else 0
                                            )
                                        ticket_data["id"] = ticket_socket_order_ticket_id
                                        ticket_data["is_checked_in"] = is_checked_in

                                        sql = """Update TicketSocketOrderTickets
                                                SET TicketType=%(ticket_type)s,
                                                TicketSocketTicketTypeId=%(ticket_type_id)s,
                                                ServiceFee=%(serviceFee)s, 
                                                BarCode=%(barcode)s,
                                                AvailableScans=%(availableScans)s,
                                                PurchaseLocation=%(purchaseLocation)s, 
                                                ScannedTimestamp=%(scannedTimestamp)s,
                                                IsCheckedIn=%(is_checked_in)s, """
                                        if ticket_price > 0:
                                            sql += """Price=%(price)s, """
                                        sql += """LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                        ticket_success = update(sql, ticket_data, cnx)
                                    else:
                                        # insert new ticket
                                        ticket_add_new = True
                                        ticket_data["ticketId"] = int(ticket.id)
                                        ticket_data["ticket_socket_order_id"] = (
                                            ticket_socket_order_id
                                        )
                                        ticket_data["is_checked_in"] = (
                                            1 if ticket.scannedTimestamp != 0 else 0
                                        )
                                        sql = """INSERT INTO TicketSocketOrderTickets
                                            (TicketSocketOrderId, TicketId, TicketSocketTicketTypeId,
                                            TicketType, ServiceFee, BarCode, AvailableScans, PurchaseLocation,
                                            ScannedTimestamp, IsCheckedIn,
                                            AttendeeFirstName, AttendeeLastName"""
                                        if ticket_price > 0:
                                            sql += ", Price"
                                        sql += """) """
                                        sql += """VALUES (%(ticket_socket_order_id)s, %(ticketId)s,
                                            %(ticket_type_id)s, %(ticket_type)s, %(serviceFee)s, %(barcode)s,
                                            %(availableScans)s, %(purchaseLocation)s, %(scannedTimestamp)s,
                                            %(is_checked_in)s, %(attendeeFirstName)s,
                                            %(attendeeLastName)s"""
                                        if ticket_price > 0:
                                            sql += ", %(price)s"
                                        sql += """)"""
                                        ticket_socket_order_ticket_id = insert(
                                            sql, ticket_data
                                        )
                                        ticket_success = ticket_socket_order_ticket_id > 0

                                    # if the update succeeded, update counters
                                    if ticket_success:
                                        if ticket_add_new:
                                            tickets_inserted += 1
                                        else:
                                            tickets_updated += 1
                                    else:
                                        # if that failed, just mark it failed and skip orders
                                        tickets_failed.append(ticket.id)
                                        update_success = False
                                        continue
            else:
                update_success = True

            end_timer = time.time()
            duration = end_timer - start_timer

            database_duration = end_timer - service_timer
            logMessage(
                "database update complete in " + str(database_duration) + " seconds"
            )

            results = TicketSocketRefreshHistory(
                service_events_skipped,
                events_failed,
                orders_failed,
                tickets_failed,
                ticket_types_failed,
                total_events_from_service,
                events_updated,
                events_inserted,
                orders_inserted,
                orders_updated,
                orders_deleted,
                tickets_updated,
                tickets_inserted,
                ticket_types_updated,
                ticket_types_inserted,
                int(start_timer),
                int(end_timer),
                duration,
                user_id,
                seller_id,
                start,
                end,
                update_success,
                error_message,
            )
            if user_id is not None and user_id > 0:
                user_service = UserService()
                user = user_service.getUserById(user_id)
                if user is not None:
                    results.username = user.userFullname()
            else:
                results.username = "System"

            results.order_data_rows_removed = daily_order_data_rows_removed

            results.commit(cnx)

            if cnx is not None and cnx.is_connected:
                cnx.close()

        except (IndexError, MemoryError, EOFError, BufferError,
                SystemError, TimeoutError, RuntimeError) as error:
            update_success = False
            error_message: str = str(error) + "\n" + traceback.format_exc()
            logMessage(error_message)

        # alert dB if it failed
        if update_success is not True or (results is not None and results.succeeded is not True):
            subject = "Error in TS Refresh - " + datetime.now().strftime(
                "%m/%d/%Y %H:%M:%S"
            )
            if results is not None:
                html = convertToJson(results)
            else:
                html = error_message
            to = "dwbodine@gmail.com"
            to_name = "dB"
            sendEmail(to, subject, html, to_name)

        return results

    def get_ticket_socket_refresh_history(self):
        """
        Get history of TS refresh for admin screen
        """
        logs: list[TicketSocketRefreshHistory] = []

        sql = """SELECT TicketSocketRefreshHistory.*,
                CONCAT(Users.FirstName, ' ', Users.LastName) AS UserName,
                Users.UserName AS Email, Sellers.Name AS SellerName
                FROM TicketSocketRefreshHistory 
                LEFT JOIN Users ON Users.UserId = TicketSocketRefreshHistory.UserId
                LEFT JOIN Sellers ON Sellers.SellerId = TicketSocketRefreshHistory.SellerId
                ORDER BY TicketSocketRefreshHistory.StartTimer DESC"""

        rows = queryAll(sql)
        for row in rows:
            user_id = int(row["UserId"])
            if user_id == 0:
                username = "System"
            else:
                username = str(row["UserName"]) + " (" + str(row["Email"]) + ")"
            seller_id = int(row["seller_id"]) if row["seller_id"] is not None else None
            seller_name = (
                str(row["SellerName"]) if row["SellerName"] is not None else None
            )
            start = int(row["Start"]) if row["Start"] is not None else None
            end = int(row["End"]) if row["End"] is not None else None
            start_timer = int(row["StartTimer"])
            end_timer = int(row["EndTimer"])
            duration = float(row["Duration"])
            succeeded = True if int(row["Success"]) == 1 else False
            error_message = str(row["ErrorMessage"])
            service_events_skipped = str(row["ServiceEventsSkipped"])
            events_failed = str(row["EventsFailed"])
            orders_failed = str(row["OrdersFailed"])
            tickets_failed = str(row["TicketsFailed"])
            ticket_types_failed = str(row["TicketTypesFailed"])
            total_events_from_service = int(row["TotalEventsFromService"])
            events_updated = int(row["EventsUpdated"])
            events_inserted = int(row["EventsInserted"])
            orders_inserted = int(row["OrdersInserted"])
            orders_updated = int(row["OrdersUpdated"])
            orders_deleted = int(row["OrdersDeleted"])
            tickets_updated = int(row["TicketsUpdated"])
            tickets_inserted = int(row["TicketsInserted"])
            ticket_types_updated = int(row["TicketTypesUpdated"])
            ticket_types_inserted = int(row["TicketTypesInserted"])
            order_data_update_succeeded = (
                True if int(row["OrderDataUpdateSucceeded"]) == 1 else False
            )
            order_data_update_duration = float(row["OrderDataUpdateDuration"])
            total_duration = float(row["TotalDuration"])
            order_data_rows_total = int(row["OrderDataRowsTotal"])
            order_data_rows_inserted = int(row["OrderDataRowsInserted"])
            order_data_rows_updated = int(row["OrderDataRowsUpdated"])
            order_data_rows_removed = int(row["OrderDataRowsRemoved"])

            history = TicketSocketRefreshHistory(
                service_events_skipped,
                events_failed,
                orders_failed,
                tickets_failed,
                ticket_types_failed,
                total_events_from_service,
                events_updated,
                events_inserted,
                orders_inserted,
                orders_updated,
                orders_deleted,
                tickets_updated,
                tickets_inserted,
                ticket_types_updated,
                ticket_types_inserted,
                start_timer,
                end_timer,
                duration,
                user_id,
                seller_id,
                start,
                end,
                succeeded,
                error_message,
            )
            history.sellerName = seller_name
            history.userName = username
            history.orderDataUpdateSucceeded = order_data_update_succeeded
            history.orderDataUpdateDuration = order_data_update_duration
            history.orderDataRowsTotal = order_data_rows_total
            history.orderDataRowsUpdated = order_data_rows_updated
            history.orderDataRowsRemoved = order_data_rows_removed
            history.orderDataRowsInserted = order_data_rows_inserted
            history.totalDuration = total_duration
            logs.append(history)

        return logs
