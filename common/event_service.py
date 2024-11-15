"""
Event Service
"""

import time
from datetime import datetime, timedelta
import operator
import traceback

from common.db import (
    db_query_all,
    db_query_one,
    db_update,
    db_insert,
    db_convert_list_to_parameters,
    db_get_connection,
    db_delete,
)
from common.utility import log_message, convert_to_json, send_email
from common.ticket_socket_service import TicketSocketService
from common.models.national_acts import (
    VipEvent,
    VipOrder,
    VipTicket,
    Seller,
    SellerEventCategory,
    DailyOrderData,
    TicketSocketRefreshHistory,
    DashboardTotals,
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
    ):
        """
        main method to fetch events and orders
        """
        events: list[VipEvent] = []

        seller_event_category_ids: list[int] = []
        if seller_id is not None:
            seller = Seller(seller_id)
            seller_event_category_ids = seller.get_seller_event_category_ids()
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
                seller_event_category_id_str = db_convert_list_to_parameters(
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
            if ignore_flags is not True:
                where_clause.append(
                    """COALESCE(TicketSocketEvents.AnnounceDate,
                                     CURRENT_TIMESTAMP) <= CURRENT_TIMESTAMP"""
                )

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

        event_rows = db_query_all(sql, data)
        for row in event_rows:
            event_id = int(row["EventId"])
            ticket_socket_event_id = int(row["Id"])
            vip_event = VipEvent()
            vip_event.event_id = event_id
            vip_event.title = str(row["Title"])
            vip_event.seller_name = str(row["SellerName"])
            vip_event.is_external = False
            vip_event.ticket_socket_event_id = ticket_socket_event_id
            vip_event.seller_event_category_id = int(row["SellerEventCategoryId"])
            vip_event.event_date = str(row["EventDate"])
            vip_event.announce_date = str(row["AnnounceDate"])
            vip_event.utc_time = int(row["UtcTime"])
            vip_event.display_date = (
                str(row["DisplayDate"]) if row["DisplayDate"] is not None else None
            )
            vip_event.thumbnail = (
                str(row["Thumbnail"]) if row["Thumbnail"] is not None else None
            )
            vip_event.ticket_socket_url = str(row["URL"])
            vip_event.is_added_to_bands_in_town = (
                True if int(row["IsAddedToBandsInTown"]) == 1 else False
            )
            vip_event.is_hidden = True if int(row["IsHidden"]) == 1 else False
            vip_event.is_cancelled = True if int(row["IsCancelled"]) == 1 else False
            vip_event.cancelled_date = (
                str(row["CancelledDate"])
                if (vip_event.is_cancelled is True and row["CancelledDate"] is not None)
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
            vip_event.on_sale = True if int(row["OnSale"]) == 1 else False
            vip_event.is_active = True if int(row["IsActive"]) == 1 else False
            vip_event.is_deleted = True if int(row["IsDeleted"]) == 1 else False
            if vip_event.is_deleted is True:
                vip_event.is_active = False
            vip_event.is_vip = True if int(row["IsVip"]) == 1 else False
            if (
                row["ExternalEventId"] is not None
                and row["ExternalEventId"] != ""
                and exclude_external is not True
            ):
                vip_event.external_event_id = int(row["ExternalEventId"])
                vip_event.external_seller_id = int(row["ExternalSellerId"])
                vip_event.external_title = str(row["ExternalTitle"])
                vip_event.external_thumbnail = str(row["ExternalThumbnail"])
                vip_event.external_url = str(row["ExternalUrl"])
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
                vip_event.external_venue = external_venue
                vip_event.disable_link_button = str(row["DisableLinkButton"])
                vip_event.disable_link_reason = str(row["DisableLinkReason"])
                vip_event.external_vip_link = str(row["ExternalVipLink"])
                vip_event.disable_vip_link_button = str(row["DisableVipLinkButton"])
                vip_event.disable_vip_link_reason = str(row["DisableVipLinkReason"])

            if get_orders is True:
                ticket_types = self.__get_ticket_types_from_event_id(
                    ticket_socket_event_id
                )
                vip_event.ticket_types = ticket_types
                orders = self.__get_orders_from_event_id(
                    ticket_socket_event_id,
                    show_inactive,
                    show_deleted,
                    ignore_flags,
                )
                vip_event.orders = orders

            vip_event.get_totals()

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
                externalwhere_clause.append("ExternalEvents.SellerId = %(sellerId)s")
                external_data["sellerId"] = seller_id
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

            externalevent_rows = db_query_all(external_sql, external_data)
            for row in externalevent_rows:
                event_id = int(row["EventId"])
                vip_event = VipEvent()
                vip_event.event_id = event_id
                vip_event.title = str(row["Title"])
                vip_event.seller_name = str(row["SellerName"])
                vip_event.is_external = True
                vip_event.event_date = str(row["EventDate"])
                vip_event.announce_date = str(row["AnnounceDate"])
                vip_event.thumbnail = str(row["Thumbnail"])
                vip_event.external_url = str(row["URL"])
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
                vip_event.external_event_id = int(row["EventId"])
                vip_event.external_seller_id = int(row["SellerId"])
                vip_event.disable_link_button = str(row["DisableLinkButton"])
                vip_event.disable_link_reason = str(row["DisableLinkReason"])
                vip_event.external_vip_link = str(row["ExternalVipLink"])
                vip_event.is_vip = (
                    True
                    if (
                        vip_event.external_vip_link is not None
                        and vip_event.external_vip_link != ""
                    )
                    else False
                )
                vip_event.disable_vip_link_button = str(row["DisableVipLinkButton"])
                vip_event.disable_vip_link_reason = str(row["DisableVipLinkReason"])
                vip_event.is_added_to_bands_in_town = (
                    True if int(row["IsAddedToBandsInTown"]) == 1 else False
                )
                vip_event.is_hidden = True if int(row["IsHidden"]) == 1 else False
                vip_event.is_cancelled = True if int(row["IsCancelled"]) == 1 else False
                vip_event.cancelled_date = (
                    str(row["CancelledDate"])
                    if (
                        vip_event.is_cancelled is True
                        and row["CancelledDate"] is not None
                    )
                    else None
                )
                events.append(vip_event)

        events.sort(key=operator.attrgetter("event_date", "title", "external_event_id"))

        return events

    def get_orders(
        self,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        show_inactive: bool = False,
        show_deleted: bool = False,
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
            midnight_end_date = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(
                days=1
            )
            midnight_end = midnight_end_date.strftime("%Y-%m-%d")

        seller_event_category_ids: list[int] = []
        if seller_id is not None:
            seller = Seller(seller_id)
            seller_event_category_ids = seller.get_seller_event_category_ids()
            # prevent against returning every event in the database
            if len(seller_event_category_ids) == 0:
                return []

        sql = ""

        if midnight_start is not None and midnight_end is not None:
            sql += """
                WITH
                RefundOrders AS (
                SELECT DISTINCT
                    TicketSocketOrderTickets.TicketSocketOrderId As RefundOrderId
                FROM
                    TicketSocketOrderTickets
                        WHERE (
                            TicketSocketOrderTickets.IsRefunded = 1 
                                AND TicketSocketOrderTickets.RefundDate 
                                BETWEEN %(startDate)s AND %(endDate)s
                        ) OR (
                            TicketSocketOrderTickets.IsChargedBack = 1 
                                AND TicketSocketOrderTickets.ChargebackDate 
                                BETWEEN %(startDate)s AND %(endDate)s
                        )
                )"""
        elif end is not None or start is not None or seller_id is None:
            sql += """
                WITH
                RefundOrders AS (
                SELECT DISTINCT
                    TicketSocketOrderTickets.TicketSocketOrderId As RefundOrderId
                FROM
                    TicketSocketOrderTickets
                        WHERE (
                            TicketSocketOrderTickets.IsRefunded = 1 
                                AND TicketSocketOrderTickets.RefundDate >= %(startDate)s
                        ) OR(
                            TicketSocketOrderTickets.IsChargedBack = 1 
                                AND TicketSocketOrderTickets.ChargebackDate >= %(startDate)s
                        )
                )"""
        sql += """
                SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate,
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

            if show_cancelled is not True:
                where_clause.append("TicketSocketEvents.IsCancelled = 0")

        if len(seller_event_category_ids) > 0:
            seller_event_category_id_str = db_convert_list_to_parameters(
                seller_event_category_ids, data, "sellerEventCategoryId"
            )
            where_clause.append(
                "TicketSocketEvents.SellerEventCategoryId IN "
                + seller_event_category_id_str
            )

        both_dates_sql = """(TicketSocketOrders.PurchaseDate
                            BETWEEN %(startDate)s AND %(endDate)s OR
                            TicketSocketOrders.Id in (
                                SELECT RefundOrderId FROM RefundOrders
                            ))"""

        start_date_sql = """(TicketSocketOrders.PurchaseDate >= %(startDate)s OR
                            TicketSocketOrders.Id in (
                                SELECT RefundOrderId FROM RefundOrders
                            ))"""

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

        order_rows = db_query_all(sql, data)
        for row in order_rows:
            order_id = int(row["OrderId"])
            event_id = int(row["EventId"])
            ticket_socket_order_id = int(row["Id"])
            order = VipOrder()
            order.order_id = order_id
            order.event_id = event_id
            order.event_title = str(row["EventTitle"])
            order.venue = str(row["Venue"])
            order.event_address = str(row["EventAddress"])
            order.event_city = str(row["EventCity"])
            order.event_state = str(row["EventState"])
            order.event_zip = str(row["EventZip"])
            order.event_country = str(row["EventCountry"])
            order.event_date = str(row["EventDate"])
            order.seller_name = str(row["SellerName"])
            order.seller_id = int(row["SellerId"])
            order.ticket_socket_event_id = int(row["TicketSocketEventId"])
            order.ticket_socket_order_id = ticket_socket_order_id
            order.num_tickets = int(row["NumTickets"])
            order.purchase_date = str(row["PurchaseDate"])
            order.purchase_timestamp = str(row["PurchaseTimestamp"])
            order.user_id = int(row["UserId"])
            order.phone = str(row["Phone"]) if row["Phone"] is not None else None
            order.email = str(row["Email"]) if row["Email"] is not None else None
            order.purchaser_last_name = (
                str(row["PurchaserLastName"])
                if row["PurchaserLastName"] is not None
                else None
            )
            order.purchaser_first_name = (
                str(row["PurchaserFirstName"])
                if row["PurchaserFirstName"] is not None
                else None
            )
            order.purchaser_city = (
                str(row["PurchaserCity"]) if row["PurchaserCity"] is not None else None
            )
            order.purchaser_state = (
                str(row["PurchaserState"])
                if row["PurchaserState"] is not None
                else None
            )
            order.purchaser_zip_code = (
                str(row["PurchaserZip"]) if row["PurchaserZip"] is not None else None
            )
            order.purchaser_country = (
                str(row["PurchaserCountry"])
                if row["PurchaserCountry"] is not None
                else None
            )
            order.purchaser_ip_address = (
                str(row["PurchaserIpAddress"])
                if row["PurchaserIpAddress"] is not None
                else None
            )
            order.revenue = float(row["Revenue"])
            order.service_fees = float(row["ServiceFees"])
            order.exchange_rate = float(row["ExchangeRate"])
            order.currency_abbrev = str(row["CurrencyAbbrev"])
            order.currency_symbol = str(row["Symbol"])
            order.is_active = True if int(row["IsActive"]) == 1 else False
            order.is_deleted = True if int(row["IsDeleted"]) == 1 else False

            if order.is_deleted is True:
                order.is_active = False

            tickets = self.__get_tickets_from_order_id(
                ticket_socket_order_id, ignore_flags
            )
            order.tickets = tickets
            order.get_totals()
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
        chargeback_orders: int = 0

        for order in orders:
            if order.is_deleted is True:
                continue

            purchase_timestamp = datetime.strptime(
                order.purchase_date, "%Y-%m-%d"
            ).timestamp()

            order_data: DailyOrderData = None
            found_index: int = -1

            refund_order_data: DailyOrderData = None
            found_refund_index: int = -1

            chargeback_order_data: DailyOrderData = None
            found_chargeback_index: int = -1

            for idx, x in enumerate(daily_order_data):
                if x.ticket_socket_event_id == order.ticket_socket_event_id:
                    if (
                        order.has_refunds is True
                        and x.ticket_socket_order_id == order.ticket_socket_order_id
                    ):
                        refund_order_data = x
                        found_refund_index = idx
                    elif (
                        order.has_chargebacks is True
                        and x.ticket_socket_order_id == order.ticket_socket_order_id
                    ):
                        chargeback_order_data = x
                        found_chargeback_index = idx
                    elif x.purchase_date == order.purchase_date:
                        order_data = x
                        found_index = idx
                        break

            if order.has_refunds is True and refund_order_data is None:
                for ticket in order.tickets:
                    if ticket.is_refunded is True and refund_order_data is None:
                        refund_order_data = DailyOrderData(
                            ticket.refund_date, order.ticket_socket_event_id
                        )
                        refund_order_data.ticket_socket_order_id = (
                            order.ticket_socket_order_id
                        )
                        refund_order_data.is_refunded = True
                        refund_order_data.is_charged_back = False
                    elif ticket.is_refunded is not True and order_data is None:
                        order_data = DailyOrderData(
                            order.purchase_date, order.ticket_socket_event_id
                        )
                        order_data.ticket_socket_order_id = None
                        order_data.is_refunded = False
                        order_data.is_charged_back = False
            elif order.has_chargebacks is True and chargeback_order_data is None:
                for ticket in order.tickets:
                    if ticket.is_charged_back and chargeback_order_data is None:
                        chargeback_order_data = DailyOrderData(
                            ticket.chargeback_date, order.ticket_socket_event_id
                        )
                        chargeback_order_data.ticket_socket_order_id = (
                            order.ticket_socket_order_id
                        )
                        chargeback_order_data.is_refunded = False
                        chargeback_order_data.is_charged_back = True
                    elif ticket.is_charged_back is not True and order_data is None:
                        order_data = DailyOrderData(
                            order.purchase_date, order.ticket_socket_event_id
                        )
                        order_data.ticket_socket_order_id = None
                        order_data.is_refunded = False
                        order_data.is_charged_back = False

            if order_data is None and (
                purchase_timestamp >= start and purchase_timestamp <= end
            ):
                order_data = DailyOrderData(
                    order.purchase_date, order.ticket_socket_event_id
                )
                order_data.ticket_socket_order_id = None
                order_data.is_refunded = False
                order_data.is_charged_back = False

            if refund_order_data is not None:
                refund_order_data.num_tickets_refunded += order.num_tickets_refunded
                refund_order_data.revenue_refunded += order.revenue_refunded_usd
                refund_order_data.service_fee_revenue_refunded += (
                    order.service_fee_revenue_refunded_usd
                )

            if chargeback_order_data is not None:
                chargeback_order_data.num_tickets_charged_back += (
                    order.num_tickets_charged_back
                )
                chargeback_order_data.revenue_charged_back += (
                    order.revenue_charged_back_usd
                )
                chargeback_order_data.service_fee_revenue_charged_back += (
                    order.service_fee_revenue_charged_back_usd
                )

            if order_data is not None:
                order_data.orders += 1
                order_data.tickets += order.num_tickets
                order_data.ticket_revenue_usd += order.revenue_usd
                order_data.service_fees_revenue_usd += order.service_fees_usd
                order_data.total_revenue_usd += (
                    order.revenue_usd + order.service_fees_usd
                )

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

            if chargeback_order_data is not None:
                chargeback_orders += 1
                if found_chargeback_index >= 0:
                    daily_order_data[found_chargeback_index] = chargeback_order_data
                else:
                    daily_order_data.append(chargeback_order_data)

        return daily_order_data

    def update_daily_order_data(
        self,
        history: TicketSocketRefreshHistory = None,
        year: int = 0,
        seller_id: int = None,
    ):
        """
        Pulls order data from the database and rolls it up to DailyOrderData
        """
        log_message("Starting update of daily order data")
        timer: float = time.time()
        duration: float = 0
        daily_order_data = self.get_daily_order_data_from_orders(year, seller_id)
        duration = time.time() - timer
        log_message(f"Daily order data fetch completed in {duration} seconds")

        if history is not None:
            history.order_data_rows_total = len(daily_order_data)

            if len(daily_order_data) <= 0:
                history.order_data_update_succeeded = False
                return history

        log_message("Daily order data - starting database update")

        success = True
        updates: int = 0
        inserts: int = 0
        for order_data in daily_order_data:
            sql = """SELECT DailyOrderDataId FROM DailyOrderData
                        WHERE TicketSocketEventId=%(ticketSocketEventId)s
                        AND PurchaseDate=DATE(%(purchaseDate)s)"""
            data = {
                "ticketSocketEventId": order_data.ticket_socket_event_id,
                "purchaseDate": order_data.purchase_date,
            }

            if order_data.ticket_socket_order_id is not None:
                sql += """ AND TicketSocketOrderId=%(ticketSocketOrderId)s"""
                data["ticketSocketOrderId"] = order_data.ticket_socket_order_id
            else:
                sql += """ AND TicketSocketOrderId IS NULL"""

            existing_data = db_query_one(sql, data)

            update_data = {
                "purchaseDate": order_data.purchase_date,
                "ticketSocketEventId": order_data.ticket_socket_event_id,
                "orders": order_data.orders,
                "tickets": order_data.tickets,
                "ticketRevenue": order_data.ticket_revenue_usd,
                "serviceFeeRevenue": order_data.service_fees_revenue_usd,
                "totalRevenue": order_data.total_revenue_usd,
                "isRefunded": 1 if order_data.is_refunded is True else 0,
                "isChargeback": 1 if order_data.is_charged_back is True else 0,
                "numTicketsRefunded": order_data.num_tickets_refunded,
                "revenueRefunded": order_data.revenue_refunded,
                "serviceFeeRevenueRefunded": order_data.service_fee_revenue_refunded,
                "numTicketsChargedBack": order_data.num_tickets_charged_back,
                "revenueChargedBack": order_data.revenue_charged_back,
                "serviceFeeRevenueChargedBack": order_data.service_fee_revenue_charged_back,
                "ticketSocketOrderId": order_data.ticket_socket_order_id,
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
                                NumTicketsChargedBack=%(numTicketsChargedBack)s,
                                RevenueChargedBack=%(revenueChargedBack)s,
                                ServiceFeeRevenueChargedBack=%(serviceFeeRevenueChargedBack)s,
                                TicketSocketOrderId=%(ticketSocketOrderId)s, 
                                LastUpdate=CURRENT_TIMESTAMP
                                WHERE DailyOrderDataId=%(dailyOrderDataId)s"""
                update_data["dailyOrderDataId"] = daily_order_data_id
                success = db_update(update_sql, update_data)
                if success:
                    updates += 1
            else:
                insert_sql = """INSERT INTO DailyOrderData (PurchaseDate, TicketSocketEventId,
                                    Orders, Tickets, TicketRevenue, ServiceFeeRevenue,
                                    TotalRevenue, IsRefunded, IsChargeback, NumTicketsRefunded,
                                    RevenueRefunded, ServiceFeeRevenueRefunded, NumTicketsChargedBack,
                                    RevenueChargedBack, ServiceFeeRevenueChargedBack,
                                    TicketSocketOrderId) VALUES (%(purchaseDate)s,
                                    %(ticketSocketEventId)s, %(orders)s, %(tickets)s,
                                    %(ticketRevenue)s, %(serviceFeeRevenue)s, %(totalRevenue)s,
                                    %(isRefunded)s, %(isChargeback)s, %(numTicketsRefunded)s,
                                    %(revenueRefunded)s, %(serviceFeeRevenueRefunded)s,
                                    %(numTicketsChargedBack)s, %(revenueChargedBack)s,
                                    %(serviceFeeRevenueChargedBack)s,
                                    %(ticketSocketOrderId)s )"""

                daily_order_data_id = db_insert(insert_sql, update_data)
                success = daily_order_data_id > 0
                if success:
                    inserts += 1
            if success is not True:
                break

        duration = time.time() - timer
        if history is not None:
            history.set_order_update_success(success, duration, inserts, updates)

        log_message(f"Daily order data - update complete in {duration} seconds")

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

        rows = db_query_all(sql, data)
        for row in rows:
            purchase_date = str(row["PurchaseDate"])
            ticket_socket_event_id = int(row["TicketSocketEventId"])
            order_data = DailyOrderData(purchase_date, ticket_socket_event_id)
            order_data.event_title = str(row["EventTitle"])
            order_data.event_date = str(row["EventDate"])
            order_data.seller_id = int(row["SellerId"])
            order_data.seller_name = str(row["SellerName"])
            order_data.venue = str(row["Venue"])
            order_data.city = str(row["City"])
            order_data.state = str(row["State"])
            order_data.country = str(row["Country"])
            order_data.zip = str(row["Zip"])
            order_data.tickets = int(row["Tickets"])
            order_data.orders = int(row["Orders"])
            order_data.ticket_revenue_usd = float(row["TicketRevenue"])
            order_data.service_fees_revenue_usd = float(row["ServiceFeeRevenue"])
            order_data.total_revenue_usd = float(row["TotalRevenue"])
            order_data.ticket_socket_id = int(row["TicketSocketId"])
            order_data.ticket_socket_order_id = (
                int(row["TicketSocketOrderId"])
                if row["TicketSocketOrderId"] is not None
                else None
            )
            order_data.is_refunded = True if int(row["IsRefunded"]) == 1 else False
            if order_data.is_refunded is True:
                order_data.num_tickets_refunded = int(row["NumTicketsRefunded"])
                order_data.revenue_refunded = float(row["RevenueRefunded"])
                order_data.service_fee_revenue_refunded = float(
                    row["ServiceFeeRevenueRefunded"]
                )

            order_data.is_charged_back = (
                True if int(row["IsChargeback"]) == 1 else False
            )
            if order_data.is_charged_back is True:
                order_data.num_tickets_charged_back = int(row["NumTicketsChargedBack"])
                order_data.revenue_charged_back = float(row["RevenueChargedBack"])
                order_data.service_fee_revenue_charged_back = float(
                    row["ServiceFeeRevenueChargedBack"]
                )

            dash_totals.tickets += order_data.tickets
            dash_totals.orders += order_data.orders
            dash_totals.num_tickets_refunded += order_data.num_tickets_refunded
            dash_totals.num_tickets_charged_back += order_data.num_tickets_charged_back
            dash_totals.revenue_refunded += order_data.revenue_refunded
            dash_totals.revenue_charged_back += order_data.revenue_charged_back
            dash_totals.service_fee_revenue_refunded += (
                order_data.service_fee_revenue_refunded
            )
            dash_totals.service_fee_revenue_charged_back += (
                order_data.service_fee_revenue_charged_back
            )
            dash_totals.ticket_revenue_usd += order_data.ticket_revenue_usd
            dash_totals.service_fees_revenue_usd += order_data.service_fees_revenue_usd
            dash_totals.total_revenue_usd += order_data.total_revenue_usd

            daily_order_data.append(order_data)

        dash_totals.daily_order_data = daily_order_data
        dash_totals.price_per_ticket = (
            (dash_totals.ticket_revenue_usd)
        ) / dash_totals.tickets
        dash_totals.service_fee_per_ticket = (
            dash_totals.service_fees_revenue_usd
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

        rows = db_query_all(sql, data)
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

        if show_inactive is not True and ignore_flags is not True:
            sql += """ AND TicketSocketOrders.IsActive = 1"""

        sql += """ ORDER BY TicketSocketOrders.PurchaserLastName ASC,
                    TicketSocketOrders.PurchaserFirstName ASC"""

        rows = db_query_all(sql, data)
        for row in rows:
            order_id = int(row["OrderId"])
            event_id = int(row["EventId"])
            ticket_socket_order_id = int(row["Id"])
            order = VipOrder()
            order.order_id = order_id
            order.event_id = event_id
            order.venue = str(row["Venue"])
            order.event_title = str(row["EventTitle"])
            order.event_address = str(row["EventAddress"])
            order.event_city = str(row["EventCity"])
            order.event_state = str(row["EventState"])
            order.event_zip = str(row["EventZip"])
            order.event_country = str(row["EventCountry"])
            order.event_date = str(row["EventDate"])
            order.seller_name = str(row["SellerName"])
            order.seller_id = int(row["SellerId"])
            order.ticket_socket_event_id = ticket_socket_event_id
            order.ticket_socket_order_id = ticket_socket_order_id
            order.num_tickets = int(row["NumTickets"])
            order.purchase_date = str(row["PurchaseDate"])
            order.purchase_timestamp = str(row["PurchaseTimestamp"])
            order.user_id = int(row["UserId"])
            order.phone = str(row["Phone"]) if row["Phone"] is not None else None
            order.email = str(row["Email"]) if row["Email"] is not None else None
            order.purchaser_last_name = (
                str(row["PurchaserLastName"])
                if row["PurchaserLastName"] is not None
                else None
            )
            order.purchaser_first_name = (
                str(row["PurchaserFirstName"])
                if row["PurchaserFirstName"] is not None
                else None
            )
            order.purchaser_city = (
                str(row["PurchaserCity"]) if row["PurchaserCity"] is not None else None
            )
            order.purchaser_state = (
                str(row["PurchaserState"])
                if row["PurchaserState"] is not None
                else None
            )
            order.purchaser_zip_code = (
                str(row["PurchaserZip"]) if row["PurchaserZip"] is not None else None
            )
            order.purchaser_country = (
                str(row["PurchaserCountry"])
                if row["PurchaserCountry"] is not None
                else None
            )
            order.purchaser_ip_address = (
                str(row["PurchaserIpAddress"])
                if row["PurchaserIpAddress"] is not None
                else None
            )
            order.revenue = float(row["Revenue"])
            order.service_fees = float(row["ServiceFees"])
            order.exchange_rate = float(row["ExchangeRate"])
            order.currency_abbrev = str(row["CurrencyAbbrev"])
            order.currency_symbol = str(row["Symbol"])
            order.is_active = True if int(row["IsActive"]) == 1 else False
            order.is_deleted = True if int(row["IsDeleted"]) == 1 else False

            if order.is_deleted is True:
                order.is_active = False

            tickets = self.__get_tickets_from_order_id(
                ticket_socket_order_id, ignore_flags
            )
            order.tickets = tickets
            order.get_totals()
            orders.append(order)
        return orders

    def __get_tickets_from_order_id(
        self, ticket_socket_order_id: int, ignore_flags: bool = False
    ):
        tickets: list[VipTicket] = []
        sql = """SELECT * FROM TicketSocketOrderTickets
                    WHERE TicketSocketOrderId=%(ticket_socket_order_id)s"""
        if ignore_flags is not True:
            sql += """ AND IsActive=1"""
        data = {"ticket_socket_order_id": ticket_socket_order_id}

        rows = db_query_all(sql, data)
        for row in rows:
            ticket_id: int = 0
            if row["TicketId"] is not None and row["TicketId"] != "":
                ticket_id = int(row["TicketId"])
            ticket = VipTicket()
            ticket.ticket_id = ticket_id
            ticket.is_active = True if int(row["IsActive"]) == 1 else False
            ticket.ticket_type = str(row["TicketType"])
            ticket.price = float(row["Price"])
            ticket.service_fee = float(row["ServiceFee"])
            ticket.ticket_type_id = int(row["TicketSocketTicketTypeId"])
            ticket.barcode = str(row["BarCode"])
            ticket.available_scans = int(row["AvailableScans"])
            ticket.purchase_location = str(row["PurchaseLocation"])
            ticket.scanned_timestamp = int(row["ScannedTimestamp"])
            ticket.attendee_first_name = str(row["AttendeeFirstName"])
            ticket.attendee_last_name = str(row["AttendeeLastName"])
            ticket.shirt_size = (
                str(row["ShirtSize"]) if row["ShirtSize"] is not None else None
            )
            ticket.ticket_socket_order_id = ticket_socket_order_id
            ticket.ticket_socket_order_ticket_id = int(row["Id"])
            ticket.is_checked_in = True if int(row["IsCheckedIn"]) == 1 else False
            is_refunded: bool = True if int(row["IsRefunded"]) == 1 else False
            ticket.is_service_fee_refunded = (
                True if int(row["IsServiceFeeRefunded"]) == 1 else False
            )
            ticket.is_refunded = is_refunded
            ticket.refund_date = (
                str(row["RefundDate"])
                if (is_refunded is True and row["RefundDate"] is not None)
                else None
            )
            is_charged_back: bool = True if int(row["IsChargedBack"]) == 1 else False
            ticket.is_charged_back = is_charged_back
            ticket.chargeback_date = (
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
            success = db_update(sql, data)
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
            success = db_update(sql, data)
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
            success = db_update(sql, data)
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
            success = db_update(sql, data)
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
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def check_in_tickets(
        self, ticket_socket_order_ticket_ids: list[int], checked_in: bool
    ):
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
            success = db_update(sql, data)
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
        success = db_update(sql, data)
        if success is True:
            success = self.refund_all_event_orders(
                ticket_socket_event_id, refund_service_fees
            )

        return success

    def refund_all_event_orders(
        self,
        ticket_socket_event_id: int,
        refund_service_fees: bool = False,
        mark_chargeback: bool = False,
    ):
        """
        Refunds all orders in an event one at a time
        """
        success: bool = True
        sql = """SELECT Id FROM TicketSocketOrders
                    WHERE TicketSocketEventId=%(ticket_socket_event_id)s"""
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        rows = db_query_all(sql, data)
        if len(rows) > 0:
            for row in rows:
                order_id = int(row["Id"])
                success = self.refund_order(
                    order_id, refund_service_fees, mark_chargeback
                )
                if success is False:
                    break
            if success is True:
                self.rebuild_daily_order_data_for_event(ticket_socket_event_id)
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
        if refund_service_fees is True or mark_chargeback is True:
            ticket_sql += """, IsServiceFeeRefunded=1"""
        ticket_sql += """ WHERE TicketSocketOrderId=%(ticket_socket_order_id)s"""
        ticket_data = {"ticket_socket_order_id": ticket_socket_order_id}
        success = db_update(ticket_sql, ticket_data)

        return success

    def refund_ticket(
        self, ticket_socket_order_ticket_id: int, refund_service_fees: bool = False
    ):
        """
        Refunds a single ticket
        """
        ticket_sql = """UPDATE TicketSocketOrderTickets SET LastUpdate=CURRENT_TIMESTAMP,
                    IsRefunded=1, IsChargedBack=0,
                    RefundDate=CURRENT_TIMESTAMP, ChargebackDate=NULL"""
        if refund_service_fees is True:
            ticket_sql += """, IsServiceFeeRefunded=1"""
        ticket_sql += """ WHERE Id=%(ticket_socket_order_ticket_id)s"""
        ticket_data = {"ticket_socket_order_ticket_id": ticket_socket_order_ticket_id}
        success = db_update(ticket_sql, ticket_data)

        if success is True:
            self.rebuild_daily_order_data_for_ticket(ticket_socket_order_ticket_id)

        return success

    def update_event(self, event_to_update: VipEvent):
        """
        Update single event from admin
        """
        success: bool = True
        if event_to_update is None or event_to_update.ticket_socket_event_id <= 0:
            return False

        ticket_socket_event_id: int = event_to_update.ticket_socket_event_id
        sql = """SELECT * FROM TicketSocketEvents WHERE Id=%(ticket_socket_event_id)s"""
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        existing_event: VipEvent = db_query_one(sql, data)

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
                    if event_to_update.is_active is True
                    and event_to_update.is_deleted is False
                    else 0
                ),
                "isDeleted": 1 if event_to_update.is_deleted is True else 0,
                "isAddedToBandsInTown": (
                    1 if event_to_update.is_added_to_bands_in_town is True else 0
                ),
                "isHidden": 1 if event_to_update.is_hidden is True else 0,
                "announceDate": (
                    event_to_update.announce_date
                    if event_to_update.announce_date is not None
                    else None
                ),
            }
            success = db_update(update_sql, update_data)

            if (
                event_to_update.is_deleted is False
                and len(event_to_update.ticket_types) > 0
            ):
                for ticket_type in event_to_update.ticket_types:
                    ticket_type_wql = """UPDATE TicketSocketTicketTypes
                                        SET IsActive=%(is_active)s, LastUpdate=CURRENT_TIMESTAMP 
                                        WHERE TicketSocketTicketTypeId=%(ticket_type_id)s 
                                        AND TicketSocketEventId=%(ticket_socket_event_id)s"""
                    ticket_type_data = {
                        "ticket_type_id": ticket_type.ticket_type_id,
                        "ticket_socket_event_id": ticket_socket_event_id,
                        "is_active": 1 if ticket_type.is_active is True else 0,
                    }
                    success = db_update(ticket_type_wql, ticket_type_data)
                    if success is False:
                        break
        return success

    def update_order(self, order_to_update: VipOrder):
        """
        Update single order from admin
        """
        success: bool = True
        if order_to_update is None or order_to_update.ticket_socket_order_id <= 0:
            return False

        ticket_socket_order_id: int = order_to_update.ticket_socket_order_id
        sql = """SELECT * FROM TicketSocketOrders WHERE Id=%(ticket_socket_order_id)s"""
        data = {"ticket_socket_order_id": ticket_socket_order_id}
        existing_order: VipOrder = db_query_one(sql, data)

        if existing_order is not None:
            update_sql = """UPDATE TicketSocketOrders
                             SET IsActive=%(is_active)s, 
                             IsDeleted=%(isDeleted)s, 
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
                    order_to_update.service_fees
                    if order_to_update.service_fees != "None"
                    else 0
                ),
                "is_active": 1 if order_to_update.is_active is True else 0,
                "isDeleted": 1 if order_to_update.is_deleted is True else 0,
            }
            success = db_update(update_sql, update_data)
            if order_to_update.is_deleted is False and len(order_to_update.tickets) > 0:
                for ticket in order_to_update.tickets:
                    order_ticket_sql = """UPDATE TicketSocketOrderTickets
                                            SET Price=%(price)s, 
                                            ServiceFee=%(serviceFee)s, 
                                            IsCheckedIn=%(is_checked_in)s, 
                                            LastUpdate=CURRENT_TIMESTAMP 
                                            WHERE Id=%(ticketId)s 
                                            AND TicketSocketOrderId=%(ticket_socket_order_id)s"""
                    order_ticket_data = {
                        "ticketId": ticket.ticket_socket_order_ticket_id,
                        "ticket_socket_order_id": ticket.ticket_socket_order_id,
                        "price": ticket.price,
                        "serviceFee": ticket.service_fee,
                        "is_checked_in": 1 if ticket.is_checked_in is True else 0,
                    }
                    success = db_update(order_ticket_sql, order_ticket_data)
                    if success is False:
                        break
            if success is True:
                self.rebuild_daily_order_data_for_order(ticket_socket_order_id)
        return success

    def rebuild_daily_order_data_for_ticket(self, ticket_id: int):
        """
        Clean out daily order data for order attached to ticket
        """
        order_sql = """SELECT TicketSocketOrderId
                        FROM TicketSocketOrderTickets
                        WHERE Id=%(ticketId)s"""
        order_data = {"ticketId": ticket_id}
        row = db_query_one(order_sql, order_data)
        if row:
            order_id = int(row["TicketSocketOrderId"])
            if order_id > 0:
                self.rebuild_daily_order_data_for_order(order_id)

    def rebuild_daily_order_data_for_event(self, event_id: int):
        """
        Clean out and rebuild daily order data for event
        """
        event_sql = """SELECT TicketSocketEvents.Id as TicketSocketEventId,
                            YEAR(TicketSocketEvents.EventDate) AS EventYear, 
                            SellerEventCategory.SellerId
                            FROM TicketSocketEvents
                            JOIN SellerEventCategory ON 
                             TicketSocketEvents.SellerEventCategoryId = 
                             SellerEventCategory.SellerEventCategoryId                         
                            WHERE TicketSocketEvents.Id=%(ticket_socket_event_id)s"""
        event_data = {"ticket_socket_event_id": event_id}
        event_row = db_query_one(event_sql, event_data)
        if event_row:
            event_id: int = event_row["TicketSocketEventId"]
            event_year: int = event_row["EventYear"]
            event_seller_id: int = event_row["SellerId"]
            self.__cleanup_daily_order_data_for_event(event_id)
            self.update_daily_order_data(year=event_year, seller_id=event_seller_id)

    def rebuild_daily_order_data_for_order(self, order_id: int):
        """
        Clean out and rebuild daily order data for order
        """
        event_sql = """SELECT TicketSocketEvents.Id AS TicketSocketEventId,
                            YEAR(TicketSocketEvents.EventDate) AS EventYear, 
                            SellerEventCategory.SellerId
                            FROM TicketSocketEvents
                            JOIN TicketSocketOrders ON
                             TicketSocketOrders.TicketSocketEventId = 
                             TicketSocketEvents.Id        
                            JOIN SellerEventCategory ON 
                             TicketSocketEvents.SellerEventCategoryId = 
                             SellerEventCategory.SellerEventCategoryId                         
                            WHERE TicketSocketOrders.Id=%(ticket_socket_order_id)s"""
        event_data = {"ticket_socket_order_id": order_id}
        event_row = db_query_one(event_sql, event_data)
        if event_row:
            event_id: int = event_row["TicketSocketEventId"]
            event_year: int = event_row["EventYear"]
            event_seller_id: int = event_row["SellerId"]
            self.__cleanup_daily_order_data_for_event(event_id)
            self.update_daily_order_data(year=event_year, seller_id=event_seller_id)

    def __cleanup_daily_order_data_for_event(self, event_id: int):
        """
        Clear out rows from DailyOrderData ahead of rebuild
        (which would be needed in refunds, cancellations and chargebacks)
        """
        sql = """DELETE FROM DailyOrderData
          WHERE TicketSocketEventId=%(ticketSocketEventId)s"""
        data = {"ticketSocketEventId": event_id}
        db_delete(sql, data)

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
        rows = db_query_all(ts_sql)

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
                seller_event_category = seller.get_seller_event_category(
                    ticket_socket_id
                )

                # if we are restricting by seller and the seller doesn't have
                # a category on this TS service, just skip it or the service will
                # return everything for everyone in the time period
                if seller_event_category is not None:
                    event_category_id = seller_event_category.event_category_id
                else:
                    continue

            events = tss.get_events_and_orders(event_category_id, start, end)

            if len(events) > 0:
                for event in events:
                    # convert ts events to vip events
                    vip_event = VipEvent()
                    vip_event.__dict__.update(event.__dict__)
                    vip_event.is_vip = is_vip_service

                    # populate sellerEventCategoryId, which is required on our end
                    if seller_event_category is not None:
                        vip_event.seller_event_category_id = (
                            seller_event_category.seller_event_category_id
                        )
                    elif vip_event.event_category_id is not None:
                        seller_ec_temp = SellerEventCategory(
                            None, ticket_socket_id, vip_event.event_category_id
                        )
                        vip_event.seller_event_category_id = (
                            seller_ec_temp.seller_event_category_id
                        )

                    # if this combo of TS and category does not exist on our side,
                    # we can't update this event
                    if vip_event.seller_event_category_id is None:
                        continue

                    # convert the orders
                    orders: list[VipEvent] = []
                    for order in event.orders:
                        vip_order = VipOrder()
                        vip_order.__dict__.update(order.__dict__)
                        orders.append(vip_order)

                    vip_event.orders = orders

                    all_events.append(vip_event)

        return all_events

    def refresh_database_from_ticket_socket(
        self,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        user_id: int = 0,
    ):
        """
        Calls out to TS and refreshes objects in database
        """
        # log_message('starting TS update')
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
            log_message("retrieving events from TicketSocket Service")
            all_events = self.retrieve_ticket_socket_events_for_update(
                seller_id, start, end
            )
            # log_message('events retrieved')

            service_timer = time.time()
            service_duration = service_timer - start_timer
            log_message("Service fetch done in " + str(service_duration) + " seconds")

            # get total number of events grabbed from service
            total_events_from_service = len(all_events)

            log_message("starting database update - opening connection")
            # get one database connection
            cnx = db_get_connection()

            if total_events_from_service > 0:

                service_events: list[int] = []
                for evt in all_events:
                    if evt.seller_event_category_id <= 0:
                        service_events_skipped.append(
                            evt.title
                            + " - eventId "
                            + str(evt.event_id)
                            + " ("
                            + evt.ticket_socket_url
                            + ")"
                        )
                        continue

                    service_events.append(evt.event_id)
                    # compile event data for update
                    address = evt.venue.address1
                    if evt.venue and evt.venue.address2:
                        address += " " + evt.venue.address2

                    event_data = {
                        "title": evt.title.strip(),
                        "eventDate": evt.event_date.strip(),
                        "utcTime": evt.utc_time,
                        "url": evt.ticket_socket_url.strip(),
                        "venue": evt.venue.name.strip(),
                        "address": address.strip(),
                        "city": evt.venue.city.strip(),
                        "state": evt.venue.state.strip(),
                        "zip": evt.venue.postal_code.strip(),
                        "country": (
                            evt.venue.country.strip()
                            if evt.venue.country is not None
                            else None
                        ),
                        "onsale": 1 if evt.on_sale else 0,
                        "thumbnail": (
                            evt.thumbnail.strip() if evt.thumbnail is not None else None
                        ),
                        "displayDate": (
                            evt.display_date.strip()
                            if evt.display_date is not None
                            else None
                        ),
                        "isVip": 1 if evt.is_vip else 0,
                    }

                    # determine if event already exists
                    event_sql = """SELECT * FROM TicketSocketEvents
                                    WHERE EventId=%(event_id)s
                                    AND SellerEventCategoryId=%(sellerEventCategoryId)s"""

                    data = {
                        "event_id": evt.event_id,
                        "sellerEventCategoryId": evt.seller_event_category_id,
                    }

                    existing_event = db_query_one(event_sql, data, cnx)

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
                        event_success = db_update(sql, event_data, cnx)
                    else:
                        event_add_new = True
                        # insert new event
                        event_data["event_id"] = int(evt.event_id)
                        event_data["sellerEventCategoryId"] = int(
                            evt.seller_event_category_id
                        )
                        sql = """INSERT INTO TicketSocketEvents (SellerEventCategoryId,
                                    EventId, Title, EventDate, UtcTime,
                                    URL, Venue, Address, City, State, Zip, Country, 
                                    OnSale, Thumbnail, DisplayDate, IsVip) 
                                    VALUES (%(sellerEventCategoryId)s, %(event_id)s, %(title)s,
                                    %(eventDate)s, %(utcTime)s, %(url)s, %(venue)s, %(address)s,
                                    %(city)s, %(state)s, %(zip)s, %(country)s, 
                                    %(onsale)s, %(thumbnail)s, %(displayDate)s, %(isVip)s)"""
                        ticket_socket_event_id = db_insert(sql, event_data, cnx)
                        event_success = ticket_socket_event_id > 0

                    # if the update succeeded, update counters
                    if event_success:
                        if event_add_new:
                            events_inserted += 1
                        else:
                            events_updated += 1
                    else:
                        # if that failed, just mark it failed and skip orders
                        events_failed.append(evt.event_id)
                        update_success = False
                        continue

                    if ticket_socket_event_id and len(evt.ticket_types) > 0:
                        event_ticket_types: list[int] = []
                        for ticket_type in evt.ticket_types:
                            event_ticket_types.append(ticket_type.ticket_type_id)

                            ticket_type_data = {
                                "ticketSocketTicketTypeId": ticket_type.ticket_type_id,
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "ticketTypeName": ticket_type.ticket_type_name,
                                "totalAvailable": ticket_type.total_available,
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

                            existing_ticket_type = db_query_one(
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
                                ticket_type_success = db_update(
                                    sql, ticket_type_data, cnx
                                )
                            else:
                                ticket_type_add_new = True
                                # insert new ticket type
                                sql = """INSERT INTO TicketSocketTicketTypes
                                        (TicketSocketTicketTypeId, TicketSocketEventId,
                                            TicketTypeName, TotalAvailable, IsActive)
                                                VALUES (%(ticketSocketTicketTypeId)s,
                                                %(ticket_socket_event_id)s, %(ticketTypeName)s,
                                                %(totalAvailable)s, %(is_active)s)"""
                                ticket_socket_type_id = db_insert(
                                    sql, ticket_type_data, cnx
                                )
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
                            if order.event_id != evt.event_id:
                                continue
                            event_orders.append(order.order_id)
                            # compile order data for update

                            order_data = {
                                "numTickets": order.num_tickets,
                                "purchaseDate": order.purchase_date.strip(),
                                "purchaseTimestamp": order.purchase_timestamp.strip(),
                                "phone": (
                                    order.phone.strip()
                                    if order.phone is not None
                                    else None
                                ),
                                "user_id": order.user_id,
                                "event_id": order.event_id,
                                "purchaserLastName": (
                                    order.purchaser_last_name.strip()
                                    if order.purchaser_last_name is not None
                                    else None
                                ),
                                "purchaserFirstName": (
                                    order.purchaser_first_name.strip()
                                    if order.purchaser_first_name is not None
                                    else None
                                ),
                                "purchaserCity": (
                                    order.purchaser_city.strip()
                                    if (
                                        order.purchaser_city is not None
                                        and order.purchaser_city != ""
                                    )
                                    else None
                                ),
                                "purchaserState": (
                                    order.purchaser_state.strip()
                                    if (
                                        order.purchaser_state is not None
                                        and order.purchaser_state != ""
                                    )
                                    else None
                                ),
                                "purchaserZip": (
                                    order.purchaser_zip_code.strip()
                                    if (
                                        order.purchaser_zip_code is not None
                                        and order.purchaser_zip_code != ""
                                    )
                                    else None
                                ),
                                "purchaserCountry": (
                                    order.purchaser_country.strip()
                                    if (
                                        order.purchaser_country is not None
                                        and order.purchaser_country != ""
                                    )
                                    else None
                                ),
                                "purchaserIpAddress": (
                                    order.purchaser_ip_address.strip()
                                    if (
                                        order.purchaser_ip_address is not None
                                        and order.purchaser_ip_address != ""
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

                            if order.service_fees > 0:
                                order_data["serviceFees"] = order.service_fees

                            # determine if order already exists
                            order_sql = """SELECT TicketSocketOrders.*
                                            FROM TicketSocketOrders
                                            WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                            AND OrderId=%(order_id)s"""

                            data = {
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "order_id": order.order_id,
                            }

                            existing_order = db_query_one(order_sql, data, cnx)

                            order_success: bool = False
                            ticket_socket_order_id: int = 0
                            order_add_new: bool = False

                            if existing_order:
                                ticket_socket_order_id = int(existing_order["Id"])
                                order_data["id"] = ticket_socket_order_id
                                # if purchase date changed, clear out daily order data for event
                                order_purchase_timestamp = datetime.strptime(
                                    order.purchase_date, "%Y-%m-%d"
                                ).timestamp()
                                existing_purchase_timestamp = datetime.strptime(
                                    str(existing_order["PurchaseDate"]), "%Y-%m-%d"
                                ).timestamp()
                                if (
                                    order_purchase_timestamp
                                    != existing_purchase_timestamp
                                ):
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
                                    rows = db_query_all(
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
                                            del_success = db_delete(
                                                cleanup_sql, cleanup_data
                                            )
                                            if del_success is True:
                                                daily_order_data_rows_removed += 1

                                # update existing order
                                sql = """UPDATE TicketSocketOrders SET NumTickets=%(numTickets)s,
                                        PurchaseDate=%(purchaseDate)s, PurchaseTimestamp=%(purchaseTimestamp)s,
                                        Phone=%(phone)s, EventId=%(event_id)s,
                                        UserId=%(user_id)s, PurchaserLastName=%(purchaserLastName)s,
                                        PurchaserFirstName=%(purchaserFirstName)s, PurchaserCity=%(purchaserCity)s, 
                                        PurchaserState=%(purchaserState)s, PurchaserZip=%(purchaserZip)s,
                                        PurchaserCountry=%(purchaserCountry)s,
                                        PurchaserIpAddress=%(purchaserIpAddress)s,
                                        Email=%(email)s, """
                                if order.revenue > 0:
                                    sql += """Revenue=%(revenue)s, """
                                if order.service_fees > 0:
                                    sql += """ServiceFees=%(serviceFees)s, """
                                sql += (
                                    """LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                )

                                order_success = db_update(sql, order_data, cnx)
                            else:
                                order_add_new = True
                                # insert new order
                                order_data["order_id"] = int(order.order_id)
                                order_data["ticket_socket_event_id"] = (
                                    ticket_socket_event_id
                                )
                                sql = """INSERT INTO TicketSocketOrders
                                            (TicketSocketEventId, OrderId, NumTickets,
                                            PurchaseDate, PurchaseTimestamp, Phone, EventId, UserId,
                                            PurchaserLastName, PurchaserFirstName, PurchaserCity, PurchaserState,
                                            PurchaserZip, PurchaserCountry,
                                            PurchaserIpAddress, Email"""
                                if order.revenue > 0:
                                    sql += """, Revenue"""
                                if order.service_fees > 0:
                                    sql += """, ServiceFees"""
                                sql += """) VALUES
                                    (%(ticket_socket_event_id)s, %(order_id)s, %(numTickets)s,
                                    %(purchaseDate)s, %(purchaseTimestamp)s, %(phone)s,
                                    %(event_id)s, %(user_id)s, %(purchaserLastName)s, %(purchaserFirstName)s,
                                    %(purchaserCity)s, %(purchaserState)s, %(purchaserZip)s, %(purchaserCountry)s,
                                    %(purchaserIpAddress)s,  %(email)s"""
                                if order.revenue > 0:
                                    sql += """, %(revenue)s"""
                                if order.service_fees > 0:
                                    sql += """, %(serviceFees)s"""
                                sql += """)"""

                                ticket_socket_order_id = db_insert(sql, order_data, cnx)
                                order_success = ticket_socket_order_id > 0

                            # if the update succeeded, update counters
                            if order_success:
                                if order_add_new:
                                    orders_inserted += 1
                                else:
                                    orders_updated += 1
                            else:
                                # if that failed, just mark it failed and skip orders
                                orders_failed.append(order.order_id)
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
                                db_delete(delete_sql, delete_data)

                                for ticket in order.tickets:
                                    order_tickets.append(ticket.ticket_id)
                                    # compile ticket data for update
                                    ticket_data = {
                                        "ticket_type": ticket.ticket_type.strip(),
                                        "ticket_type_id": ticket.ticket_type_id,
                                        "serviceFee": (
                                            ticket.service_fee
                                            if ticket.service_fee is not None
                                            else 0
                                        ),
                                        "availableScans": ticket.available_scans,
                                        "barcode": ticket.barcode,
                                        "purchaseLocation": ticket.purchase_location,
                                        "scannedTimestamp": ticket.scanned_timestamp,
                                        "attendeeFirstName": ticket.attendee_first_name,
                                        "attendeeLastName": ticket.attendee_last_name,
                                        "shirtSize": ticket.shirt_size if len(ticket.shirt_size) > 0 else None
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
                                        "ticketId": ticket.ticket_id,
                                    }

                                    existing_ticket = db_query_one(
                                        ticket_sql, data, cnx
                                    )

                                    ticket_success: bool = False
                                    ticket_socket_order_ticket_id: int = 0
                                    ticket_add_new: bool = False

                                    if existing_ticket:
                                        # update existing ticket
                                        ticket_socket_order_ticket_id = int(
                                            existing_ticket["Id"]
                                        )
                                        is_checked_in = int(
                                            existing_ticket["IsCheckedIn"]
                                        )
                                        if is_checked_in != 1:
                                            is_checked_in = (
                                                1
                                                if ticket.scanned_timestamp != 0
                                                else 0
                                            )
                                        ticket_data["id"] = (
                                            ticket_socket_order_ticket_id
                                        )
                                        ticket_data["is_checked_in"] = is_checked_in

                                        sql = """UPDATE TicketSocketOrderTickets
                                                SET TicketType=%(ticket_type)s,
                                                TicketSocketTicketTypeId=%(ticket_type_id)s,
                                                BarCode=%(barcode)s,
                                                AvailableScans=%(availableScans)s,
                                                PurchaseLocation=%(purchaseLocation)s, 
                                                ScannedTimestamp=%(scannedTimestamp)s,
                                                AttendeeFirstName=%(attendeeFirstName)s,
                                                AttendeeLastName=%(attendeeLastName)s,
                                                IsCheckedIn=%(is_checked_in)s,
                                                ShirtSize=%(shirtSize)s,
                                                LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(id)s"""
                                        ticket_success = db_update(
                                            sql, ticket_data, cnx
                                        )
                                    else:
                                        # insert new ticket
                                        ticket_add_new = True
                                        ticket_data["ticketId"] = int(ticket.ticket_id)
                                        ticket_data["ticket_socket_order_id"] = (
                                            ticket_socket_order_id
                                        )
                                        ticket_data["is_checked_in"] = (
                                            1 if ticket.scanned_timestamp != 0 else 0
                                        )
                                        sql = """INSERT INTO TicketSocketOrderTickets
                                            (TicketSocketOrderId, TicketId, TicketSocketTicketTypeId,
                                            TicketType, ServiceFee, BarCode, AvailableScans, PurchaseLocation,
                                            ScannedTimestamp, IsCheckedIn,
                                            AttendeeFirstName, AttendeeLastName, ShirtSize"""
                                        if ticket_price > 0:
                                            sql += ", Price"
                                        sql += """) """
                                        sql += """VALUES (%(ticket_socket_order_id)s, %(ticketId)s,
                                            %(ticket_type_id)s, %(ticket_type)s, %(serviceFee)s, %(barcode)s,
                                            %(availableScans)s, %(purchaseLocation)s, %(scannedTimestamp)s,
                                            %(is_checked_in)s, %(attendeeFirstName)s,
                                            %(attendeeLastName)s, %(shirtSize)s"""
                                        if ticket_price > 0:
                                            sql += ", %(price)s"
                                        sql += """)"""
                                        ticket_socket_order_ticket_id = db_insert(
                                            sql, ticket_data
                                        )
                                        ticket_success = (
                                            ticket_socket_order_ticket_id > 0
                                        )

                                    # if the update succeeded, update counters
                                    if ticket_success:
                                        if ticket_add_new:
                                            tickets_inserted += 1
                                        else:
                                            tickets_updated += 1
                                    else:
                                        # if that failed, just mark it failed and skip orders
                                        tickets_failed.append(ticket.ticket_id)
                                        update_success = False
                                        continue
            else:
                update_success = True

            end_timer = time.time()
            duration = end_timer - start_timer

            database_duration = end_timer - service_timer
            log_message(
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
                user = user_service.get_user_by_id(user_id)
                if user is not None:
                    results.username = user.user_full_name()
            else:
                results.username = "System"

            results.order_data_rows_removed = daily_order_data_rows_removed

            results.commit(cnx)

            if cnx is not None and cnx.is_connected:
                cnx.close()

        except (
            IndexError,
            MemoryError,
            EOFError,
            BufferError,
            SystemError,
            TimeoutError,
            RuntimeError,
        ) as error:
            update_success = False
            error_message: str = str(error) + "\n" + traceback.format_exc()
            log_message(error_message)

        # alert dB if it failed
        if update_success is not True or (
            results is not None and results.succeeded is not True
        ):
            subject = "Error in TS Refresh - " + datetime.now().strftime(
                "%m/%d/%Y %H:%M:%S"
            )
            if results is not None:
                html = convert_to_json(results)
            else:
                html = error_message
            to = "dwbodine@gmail.com"
            to_name = "dB"
            send_email(to, subject, html, to_name)

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

        rows = db_query_all(sql)
        for row in rows:
            user_id = int(row["UserId"])
            if user_id == 0:
                username = "System"
            else:
                username = str(row["UserName"]) + " (" + str(row["Email"]) + ")"
            seller_id = int(row["SellerId"]) if row["SellerId"] is not None else None
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
            history.seller_name = seller_name
            history.username = username
            history.order_data_update_succeeded = order_data_update_succeeded
            history.order_data_update_duration = order_data_update_duration
            history.order_data_rows_total = order_data_rows_total
            history.order_data_rows_updated = order_data_rows_updated
            history.order_data_rows_removed = order_data_rows_removed
            history.order_data_rows_inserted = order_data_rows_inserted
            history.total_duration = total_duration
            logs.append(history)

        return logs
