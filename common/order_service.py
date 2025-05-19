"""
Order Service
"""

from datetime import datetime, timedelta

from common.db import (
    db_query_all,
    db_query_one,
    db_update,
    db_insert,
    db_convert_list_to_parameters,
)
from common.daily_order_service import DailyOrderService
from common.models.national_acts import VipEvent, VipOrder, VipTicket, Seller
from common.models.ticket_socket import TicketSocketTicketType
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
)


class OrderService:
    """
    Service to handle all order-related activity
    """

    def get_orders(
        self,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        show_inactive: bool = False,
        show_deleted: bool = False,
        ignore_flags: bool = False,
        ts_order_id: int = None,
        search_term: str = None
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

        if ts_order_id is None and search_term is None and (
            midnight_start is not None and midnight_end is not None
        ):
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
        elif ts_order_id is None and search_term is None and (
            end is not None or start is not None or seller_id is None
        ):
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
                    COALESCE(ExternalEvents.Title, TicketSocketEvents.Title) as EventTitle, 
                    TicketSocketEvents.EventDate, 
                    Sellers.Name AS SellerName, 
                    Sellers.SellerId, 
                    COALESCE(ExternalEventVenues.Venue, TicketSocketEvents.Venue) AS Venue, 
                    COALESCE(ExternalEventVenues.Address, TicketSocketEvents.Address) AS EventAddress, 
                    COALESCE(ExternalEventVenues.City, TicketSocketEvents.City) AS EventCity, 
                    COALESCE(ExternalEventVenues.State, TicketSocketEvents.State) AS EventState, 
                    COALESCE(ExternalEventVenues.Zip, TicketSocketEvents.Zip) AS EventZip, 
                    COALESCE(ExternalEventVenues.Country, TicketSocketEvents.Country) AS EventCountry 
                    FROM TicketSocketOrders
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN ExternalEvents ON ExternalEvents.TicketSocketEventId = TicketSocketEvents.Id
                    JOIN ExternalEventVenues ON ExternalEvents.ExternalEventVenueId = ExternalEventVenues.VenueID
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
                    JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId 
                    JOIN TicketSocket ON TicketSocket.TicketSocketId = SellerEventCategory.TicketSocketId
                    JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                    LEFT JOIN ExchangeRateHistory ON ExchangeRateHistory.ExchangeRateId = ExchangeRates.ExchangeRateId 
                        AND ExchangeRateHistory.MidnightDate = TicketSocketOrders.PurchaseDate"""

        sql += " WHERE "
        data = {}

        where_clause: list[str] = []
        if ts_order_id is not None and ts_order_id > 0:
            where_clause.append("TicketSocketOrders.Id = %(order_id)s")
            data["order_id"] = ts_order_id
        elif search_term is not None and len(search_term) > 0:
            where_clause.append(
                """CONCAT_WS (' ', Sellers.Name, 
                            COALESCE(ExternalEvents.Title, TicketSocketEvents.Title),
                            COALESCE(TicketSocketOrders.OrderId, ''),
                            COALESCE(TicketSocketOrders.PurchaserLastName, ''),
                            COALESCE(TicketSocketOrders.PurchaserFirstName, ''),
                            COALESCE(TicketSocketOrders.Email, ''),
                            COALESCE(ExternalEventVenues.Country, TicketSocketEvents.Country, '')) 
                            LIKE ('%"""
                + search_term
                + """%')"""
            )
        else:
            if ignore_flags is not True:
                if show_deleted is not True:
                    where_clause.append("TicketSocketOrders.IsDeleted = 0")
                else:
                    show_inactive = True

                if show_inactive is True:
                    where_clause.append("TicketSocketOrders.IsActive = 0")
                else:
                    where_clause.append("TicketSocketOrders.IsActive = 1")

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
            elif end is not None and end > datetime.now().timestamp():
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

        if search_term is not None:
            sql += """ ORDER BY TicketSocketOrders.PurchaserLastName ASC,
                    TicketSocketOrders.PurchaserFirstName ASC, 
                    TicketSocketOrders.Email ASC"""
        else:
            sql += """ ORDER BY TicketSocketOrders.PurchaseDate ASC,
                    TicketSocketEvents.EventDate ASC, 
                    TicketSocketEvents.Title ASC"""

        sql = sql.replace("\n", "")

        order_rows = db_query_all(sql, data)
        for row in order_rows:
            order_id = get_override_int_value_or_default(row["OrderId"])
            event_id = get_override_int_value_or_default(row["EventId"])
            ticket_socket_order_id = get_override_int_value_or_default(row["Id"])
            order = VipOrder()
            order.order_id = order_id
            order.event_id = event_id
            order.event_title = get_override_string_value_or_default(row["EventTitle"])
            order.venue = get_override_string_value_or_default(row["Venue"])
            order.event_address = get_override_string_value_or_default(
                row["EventAddress"]
            )
            order.event_city = get_override_string_value_or_default(row["EventCity"])
            order.event_state = get_override_string_value_or_default(row["EventState"])
            order.event_zip = get_override_string_value_or_default(row["EventZip"])
            order.event_country = get_override_string_value_or_default(
                row["EventCountry"]
            )
            order.event_date = get_override_string_value_or_default(row["EventDate"])
            order.seller_name = get_override_string_value_or_default(row["SellerName"])
            order.seller_id = get_override_int_value_or_default(row["SellerId"])
            order.ticket_socket_event_id = get_override_int_value_or_default(
                row["TicketSocketEventId"]
            )
            order.ticket_socket_order_id = ticket_socket_order_id
            order.purchase_date = get_override_string_value_or_default(
                row["PurchaseDate"]
            )
            order.purchase_timestamp = get_override_string_value_or_default(
                row["PurchaseTimestamp"]
            )
            order.user_id = get_override_int_value_or_default(row["UserId"])
            order.phone = get_override_string_value_or_default(row["Phone"])
            order.email = get_override_string_value_or_default(row["Email"])
            order.purchaser_last_name = get_override_string_value_or_default(
                row["PurchaserLastName"]
            )
            order.purchaser_first_name = get_override_string_value_or_default(
                row["PurchaserFirstName"]
            )
            order.purchaser_city = get_override_string_value_or_default(
                row["PurchaserCity"]
            )
            order.purchaser_state = get_override_string_value_or_default(
                row["PurchaserState"]
            )
            order.purchaser_zip_code = get_override_string_value_or_default(
                row["PurchaserZip"]
            )
            order.purchaser_country = get_override_string_value_or_default(
                row["PurchaserCountry"]
            )
            order.purchaser_ip_address = get_override_string_value_or_default(
                row["PurchaserIpAddress"]
            )
            order.exchange_rate = get_override_float_value_or_default(
                row["ExchangeRate"]
            )
            order.currency_abbrev = get_override_string_value_or_default(
                row["CurrencyAbbrev"]
            )
            order.currency_symbol = get_override_string_value_or_default(row["Symbol"])
            order.is_active = get_override_bool_value_or_default(row["IsActive"])
            order.is_deleted = get_override_bool_value_or_default(row["IsDeleted"])
            order.is_comped = get_override_bool_value_or_default(row["IsComped"])

            if order.is_deleted is True:
                order.is_active = False

            tickets = self.get_tickets_from_order_id(
                ticket_socket_order_id, ignore_flags
            )
            order.tickets = tickets
            order.get_totals()
            orders.append(order)
        return orders

    def get_orders_from_event_id(
        self,
        ticket_socket_event_id: int,
        show_inactive: bool = False,
        show_deleted: bool = False,
        ignore_flags: bool = False,
    ):
        """
        Get orders from TicketSocketEventId
        """
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
            order_id = get_override_int_value_or_default(row["OrderId"])
            event_id = get_override_int_value_or_default(row["EventId"])
            ticket_socket_order_id = get_override_int_value_or_default(row["Id"])
            order = VipOrder()
            order.order_id = order_id
            order.event_id = event_id
            order.venue = get_override_string_value_or_default(row["Venue"])
            order.event_title = get_override_string_value_or_default(row["EventTitle"])
            order.event_address = get_override_string_value_or_default(
                row["EventAddress"]
            )
            order.event_city = get_override_string_value_or_default(row["EventCity"])
            order.event_state = get_override_string_value_or_default(row["EventState"])
            order.event_zip = get_override_string_value_or_default(row["EventZip"])
            order.event_country = get_override_string_value_or_default(
                row["EventCountry"]
            )
            order.event_date = get_override_string_value_or_default(row["EventDate"])
            order.seller_name = get_override_string_value_or_default(row["SellerName"])
            order.seller_id = get_override_int_value_or_default(row["SellerId"])
            order.ticket_socket_event_id = ticket_socket_event_id
            order.ticket_socket_order_id = ticket_socket_order_id
            order.purchase_date = get_override_string_value_or_default(
                row["PurchaseDate"]
            )
            order.purchase_timestamp = get_override_string_value_or_default(
                row["PurchaseTimestamp"]
            )
            order.user_id = get_override_int_value_or_default(row["UserId"])
            order.phone = get_override_string_value_or_default(row["Phone"])
            order.email = get_override_string_value_or_default(row["Email"])
            order.purchaser_last_name = get_override_string_value_or_default(
                row["PurchaserLastName"]
            )
            order.purchaser_first_name = get_override_string_value_or_default(
                row["PurchaserFirstName"]
            )
            order.purchaser_city = get_override_string_value_or_default(
                row["PurchaserCity"]
            )
            order.purchaser_state = get_override_string_value_or_default(
                row["PurchaserState"]
            )
            order.purchaser_zip_code = get_override_string_value_or_default(
                row["PurchaserZip"]
            )
            order.purchaser_country = get_override_string_value_or_default(
                row["PurchaserCountry"]
            )
            order.purchaser_ip_address = get_override_string_value_or_default(
                row["PurchaserIpAddress"]
            )
            order.exchange_rate = get_override_float_value_or_default(
                row["ExchangeRate"]
            )
            order.currency_abbrev = get_override_string_value_or_default(
                row["CurrencyAbbrev"]
            )
            order.currency_symbol = get_override_string_value_or_default(row["Symbol"])
            order.is_active = get_override_bool_value_or_default(row["IsActive"])
            order.is_deleted = get_override_bool_value_or_default(row["IsDeleted"])
            order.is_comped = get_override_bool_value_or_default(row["IsComped"])

            if order.is_deleted is True:
                order.is_active = False

            tickets = self.get_tickets_from_order_id(
                ticket_socket_order_id, ignore_flags
            )
            order.tickets = tickets
            order.get_totals()
            orders.append(order)
        return orders

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
            event_id: int = get_override_int_value_or_default(
                event_row["TicketSocketEventId"]
            )
            event_year: int = get_override_int_value_or_default(event_row["EventYear"])
            event_seller_id: int = get_override_int_value_or_default(
                event_row["SellerId"]
            )

            start = datetime.strptime(
                f"{event_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
            ).timestamp()
            end = datetime(event_year, 12, 31).timestamp()

            orders = self.get_orders(start=start, end=end, seller_id=event_seller_id)

            daily_order_service = DailyOrderService()
            daily_order_service.cleanup_daily_order_data_for_event(event_id)

            daily_order_service.update_daily_order_data(orders, start, end, None)

    def get_tickets_from_order_id(
        self, ticket_socket_order_id: int, ignore_flags: bool = False
    ):
        """
        Get tickets from TicketSocketOrderId
        """
        tickets: list[VipTicket] = []
        sql = """SELECT * FROM TicketSocketOrderTickets
                    WHERE TicketSocketOrderId=%(ticket_socket_order_id)s"""
        if ignore_flags is not True:
            sql += """ AND IsActive=1"""
        data = {"ticket_socket_order_id": ticket_socket_order_id}

        rows = db_query_all(sql, data)
        for row in rows:
            ticket_id: int = get_override_int_value_or_default(row["TicketId"])
            ticket = VipTicket()
            ticket.ticket_id = ticket_id
            ticket.is_active = get_override_bool_value_or_default(row["IsActive"])
            ticket.ticket_type = get_override_string_value_or_default(row["TicketType"])
            ticket.price = get_override_float_value_or_default(row["Price"])
            ticket.service_fee = get_override_float_value_or_default(row["ServiceFee"])
            ticket.ticket_type_id = get_override_int_value_or_default(
                row["TicketSocketTicketTypeId"]
            )
            ticket.barcode = get_override_string_value_or_default(row["BarCode"])
            ticket.available_scans = get_override_int_value_or_default(
                row["AvailableScans"]
            )
            ticket.purchase_location = get_override_string_value_or_default(
                row["PurchaseLocation"]
            )
            ticket.scanned_timestamp = get_override_int_value_or_default(
                row["ScannedTimestamp"]
            )
            ticket.attendee_first_name = get_override_string_value_or_default(
                row["AttendeeFirstName"]
            )
            ticket.attendee_last_name = get_override_string_value_or_default(
                row["AttendeeLastName"]
            )
            ticket.last_update = get_override_string_value_or_default(row["LastUpdate"])
            ticket.attendee_phone = get_override_string_value_or_default(
                row["AttendeePhone"]
            )
            ticket.attendee_email = get_override_string_value_or_default(
                row["AttendeeEmail"]
            )
            ticket.shirt_size = get_override_string_value_or_default(row["ShirtSize"])
            ticket.ticket_socket_order_id = ticket_socket_order_id
            ticket.ticket_socket_order_ticket_id = get_override_int_value_or_default(
                row["Id"]
            )
            is_refunded: bool = get_override_bool_value_or_default(row["IsRefunded"])
            ticket.is_service_fee_refunded = get_override_bool_value_or_default(
                row["IsServiceFeeRefunded"]
            )
            ticket.is_refunded = is_refunded
            ticket.refund_date = get_override_string_value_or_default(row["RefundDate"])
            is_checked_in = get_override_bool_value_or_default(row["IsCheckedIn"])
            ticket.is_checked_in = is_checked_in
            ticket.checked_in_date = get_override_string_value_or_default(
                row["CheckedInDate"]
            )
            is_charged_back: bool = get_override_bool_value_or_default(
                row["IsChargedBack"]
            )
            ticket.is_charged_back = is_charged_back
            ticket.chargeback_date = get_override_string_value_or_default(
                row["ChargebackDate"]
            )
            tickets.append(ticket)
        return tickets

    def disable_orders(self, ticket_socket_order_ids: list[int], disabled: bool):
        """
        Marks orders as disabled
        """
        success: bool = True
        for ticket_socket_order_id in ticket_socket_order_ids:
            sql = """UPDATE TicketSocketOrders
                        SET IsActive=%(is_active)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE Id=%(ticket_socket_order_id)s"""
            data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "is_active": get_override_tinyint_value_or_default_from_bool(
                    not disabled
                ),
            }
            success = db_update(sql, data)
            if success is False:
                break
            else:
                self.rebuild_daily_order_data_for_order(ticket_socket_order_id)
        return success

    def delete_orders(self, ticket_socket_order_ids: list[int], deleted: bool):
        """
        Marks orders as deleted
        """
        success: bool = True
        for ticket_socket_order_id in ticket_socket_order_ids:
            sql = """UPDATE TicketSocketOrders
                        SET IsDeleted=%(isDeleted)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE Id=%(ticket_socket_order_id)s"""
            data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "isDeleted": get_override_tinyint_value_or_default_from_bool(deleted),
            }
            success = db_update(sql, data)
            if success is False:
                break
            else:
                self.rebuild_daily_order_data_for_order(ticket_socket_order_id)
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
                        CheckedInDate=%(checkedInDate)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE Id=%(ticket_socket_order_ticket_id)s"""
            data = {
                "ticket_socket_order_ticket_id": ticket_socket_order_ticket_id,
                "checkedIn": get_override_tinyint_value_or_default_from_bool(
                    checked_in
                ),
                "checkedInDate": (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if checked_in is True
                    else None
                ),
            }
            success = db_update(sql, data)
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
        ticket_sql = """UPDATE TicketSocketOrderTickets
                SET LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')"""
        if mark_chargeback is True:
            ticket_sql += """, IsChargedBack=1, IsRefunded=0,
                            ChargebackDate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                            RefundDate=NULL"""
        else:
            ticket_sql += """, IsRefunded=1, IsChargedBack=0,
                            RefundDate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                            ChargebackDate=NULL"""
        if refund_service_fees is True or mark_chargeback is True:
            ticket_sql += """, IsServiceFeeRefunded=1"""
        ticket_sql += """ WHERE TicketSocketOrderId=%(ticket_socket_order_id)s"""
        ticket_data = {"ticket_socket_order_id": ticket_socket_order_id}
        success = db_update(ticket_sql, ticket_data)

        if success is True:
            self.rebuild_daily_order_data_for_order(ticket_socket_order_id)

        return success

    def refund_ticket(
        self, ticket_socket_order_ticket_id: int, refund_service_fees: bool = False
    ):
        """
        Refunds a single ticket
        """
        ticket_sql = """UPDATE TicketSocketOrderTickets
                    SET LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                    IsRefunded=1, IsChargedBack=0,
                    RefundDate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                    ChargebackDate=NULL"""
        if refund_service_fees is True:
            ticket_sql += """, IsServiceFeeRefunded=1"""
        ticket_sql += """ WHERE Id=%(ticket_socket_order_ticket_id)s"""
        ticket_data = {"ticket_socket_order_ticket_id": ticket_socket_order_ticket_id}
        success = db_update(ticket_sql, ticket_data)

        if success is True:
            self.rebuild_daily_order_data_for_ticket(ticket_socket_order_ticket_id)

        return success

    def update_order(self, order_to_update: VipOrder):
        """
        Update single order from admin
        """
        success: bool = True
        ticket_socket_order_id: int = get_override_int_value_or_default(
            order_to_update.ticket_socket_order_id
        )

        if order_to_update is None or ticket_socket_order_id <= 0:
            return False

        sql = """SELECT * FROM TicketSocketOrders WHERE Id=%(ticket_socket_order_id)s"""
        data = {"ticket_socket_order_id": ticket_socket_order_id}
        existing_order: VipOrder = db_query_one(sql, data)

        if existing_order is not None:
            update_sql = """UPDATE TicketSocketOrders
                             SET IsActive=%(is_active)s, 
                             IsDeleted=%(isDeleted)s, 
                             IsComped=%(isComped)s,
                             LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                             WHERE Id=%(ticket_socket_order_id)s"""
            update_data = {
                "ticket_socket_order_id": ticket_socket_order_id,
                "is_active": get_override_tinyint_value_or_default_from_bool(
                    order_to_update.is_active
                ),
                "isDeleted": get_override_tinyint_value_or_default_from_bool(
                    order_to_update.is_deleted
                ),
                "isComped": get_override_tinyint_value_or_default_from_bool(
                    order_to_update.is_comped
                ),
            }
            success = db_update(update_sql, update_data)
            if order_to_update.is_deleted is False and len(order_to_update.tickets) > 0:
                for ticket in order_to_update.tickets:
                    order_ticket_data = {
                        "ticketId": get_override_int_value_or_default(
                            ticket.ticket_socket_order_ticket_id
                        ),
                        "ticket_socket_order_id": get_override_int_value_or_default(
                            ticket.ticket_socket_order_id
                        ),
                        "price": get_override_float_value_or_default(ticket.price),
                        "serviceFee": get_override_float_value_or_default(
                            ticket.service_fee
                        ),
                        "is_checked_in": get_override_tinyint_value_or_default_from_bool(
                            ticket.is_checked_in
                        ),
                        "attendeeFirstName": get_override_string_value_or_default(
                            ticket.attendee_first_name
                        ),
                        "attendeeLastName": get_override_string_value_or_default(
                            ticket.attendee_last_name
                        ),
                        "attendeeEmail": get_override_string_value_or_default(
                            ticket.attendee_email
                        ),
                        "attendeePhone": get_override_string_value_or_default(
                            ticket.attendee_phone
                        ),
                        "shirtSize": get_override_string_value_or_default(
                            ticket.shirt_size
                        ),
                        "isActive": get_override_tinyint_value_or_default_from_bool(
                            ticket.is_active
                        ),
                    }

                    order_ticket_sql = """UPDATE TicketSocketOrderTickets
                                            SET Price=%(price)s, 
                                            IsActive=%(isActive)s,
                                            ServiceFee=%(serviceFee)s, 
                                            IsCheckedIn=%(is_checked_in)s, 
                                            AttendeeFirstName=%(attendeeFirstName)s,
                                            AttendeeLastName=%(attendeeLastName)s,
                                            AttendeePhone=%(attendeePhone)s,
                                            AttendeeEmail=%(attendeeEmail)s,
                                            ShirtSize=%(shirtSize)s,"""

                    if ticket.is_refunded is True:
                        order_ticket_data["refundDate"] = (
                            get_override_string_value_or_default(ticket.refund_date)
                        )
                        order_ticket_sql += """ RefundDate=%(refundDate)s,"""
                    elif ticket.is_charged_back is True:
                        order_ticket_data["chargebackDate"] = (
                            get_override_string_value_or_default(ticket.chargeback_date)
                        )
                        order_ticket_sql += """ ChargebackDate=%(chargebackDate)s,"""

                    order_ticket_sql += """
                            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                            WHERE Id=%(ticketId)s 
                            AND TicketSocketOrderId=%(ticket_socket_order_id)s"""

                    success = db_update(order_ticket_sql, order_ticket_data)
                    if success is False:
                        break
            if success is True:
                self.rebuild_daily_order_data_for_order(ticket_socket_order_id)

        return success

    def add_comped_order(self, event_id: int, num_tickets: int):
        """
        Add a comped order from admin
        """
        success: bool = True
        ticket_socket_event_id: int = 0

        if event_id <= 0 or num_tickets <= 0:
            return False

        sql = """SELECT TicketSocketEventId FROM ExternalEvents WHERE EventId=%(event_id)s"""
        data = {"event_id": event_id}
        existing_event: VipEvent = db_query_one(sql, data)
        if existing_event:
            ticket_socket_event_id = get_override_int_value_or_default(
                existing_event["TicketSocketEventId"]
            )

        if ticket_socket_event_id > 0:
            type_test = """SELECT * FROM TicketSocketTicketTypes
                            WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                            AND TicketSocketTicketTypeId=0"""
            type_test_data = {"ticket_socket_event_id": ticket_socket_event_id}
            existing_type: TicketSocketTicketType = db_query_one(
                type_test, type_test_data
            )
            if existing_type:
                type_sql = """UPDATE TicketSocketTicketTypes SET IsActive=1,
                             LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                             WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                            AND TicketSocketTicketTypeId=0"""
                success = db_update(type_sql, type_test_data)
            else:
                type_sql = """INSERT INTO TicketSocketTicketTypes (
                            TicketSocketTicketTypeId, TicketSocketEventId,
                            TicketTypeName, TotalAvailable, LastUpdate)
                             VALUES (0, %(ticket_socket_event_id)s, 'Comp', 0,
                             CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                type_id = db_insert(type_sql, type_test_data)
                success = type_id >= 0

            if success is not True:
                return False

            add_sql = """INSERT INTO TicketSocketOrders (
                             IsComped, EventId, OrderId, PurchaseDate,
                             UserId, PurchaserFirstName, PurchaserLastName,
                             TicketSocketEventId, LastUpdate
                             ) VALUES (
                                 1, 0, 0, CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                                 0, 'Comped', 'Order', %(ticket_socket_event_id)s,
                                 CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                             )"""
            add_data = {"ticket_socket_event_id": ticket_socket_event_id}
            order_id = db_insert(add_sql, add_data)
            success = True if order_id > 0 else False
            if success is True:
                ticket_sql = """INSERT INTO TicketSocketOrderTickets (TicketSocketOrderId,
                        TicketSocketTicketTypeId, TicketId, TicketType, LastUpdate) VALUES (
                            %(order_id)s, 0, %(ticketId)s, 'Comp',
                            CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

                for x in range(0, num_tickets):
                    ticket_id = x + order_id
                    ticket_data = {"order_id": order_id, "ticketId": ticket_id}
                    new_ticket_id = db_insert(ticket_sql, ticket_data)
                    success = new_ticket_id > 0
                    if success is not True:
                        break
                if success is True:
                    self.rebuild_daily_order_data_for_order(order_id)

        return success
