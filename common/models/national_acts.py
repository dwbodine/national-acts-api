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
            self.__populate_from_seller_id_and_ticket_socket_id(
                seller_id, ticket_socket_id
            )
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
    """
    National acts specific version of TS events
    """

    ticket_socket_event_id: int = 0
    total_revenue: float = 0
    total_service_fees: float = 0
    total_tickets: int = 0
    total_checked_in: int = 0
    total_shirts: int = 0
    shirt_sales: list[ShirtSales] = []
    is_active: bool = True
    orders: list[VipOrder] = []
    external_event_id: int = None
    external_seller_id: int = None
    external_title: str = None
    external_thumbnail: str = None
    external_url: str = None
    external_venue: TicketSocketVenue = None
    disable_link_button: bool = False
    disable_link_reason: bool = False
    external_vip_link: str = None
    disable_vip_link_button: bool = False
    disable_vip_link_reason: bool = False
    seller_event_category_id: int = None
    is_vip: bool = True
    is_deleted: bool = False
    is_external: bool = False
    has_shirt_data: bool = False
    has_phone_data: bool = False
    has_non_usa_orders: bool = False
    non_usa_currency_symbol: str = None
    non_usa_currency_abbrev: str = None
    num_tickets_refunded: int = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0
    num_tickets_charged_back: int = 0
    revenue_charged_back: float = 0
    service_fee_revenue_charged_back: float = 0
    has_ticket_type_data: bool = False
    is_added_to_bands_in_town: bool = False
    seller_name: str = ""
    is_hidden: bool = False
    is_cancelled: bool = False
    cancelled_date: str = None
    announce_date: str = None

    def get_totals(self):
        """
        Rollup of orders within event
        """
        total_revenue: float = 0
        total_service_fees: float = 0
        total_tickets: int = 0
        total_shirts: int = 0
        total_tickets_refunded: int = 0
        total_tickets_charged_back: int = 0
        total_revenue_refunded: float = 0
        total_revenue_charged_back: float = 0
        total_service_fee_revenue_refunded: float = 0
        total_service_fee_revenue_charged_back: float = 0
        total_checked_in: int = 0
        shirtd: dict = {}
        for order in self.orders:
            if order.has_refunds is True:
                total_tickets_refunded += order.num_tickets_refunded
                total_revenue_refunded += order.revenue_refunded_usd
                total_service_fee_revenue_refunded += (
                    order.service_fee_revenue_refunded_usd
                )
            if order.has_chargebacks is True:
                total_tickets_charged_back += order.num_tickets_charged_back
                total_revenue_charged_back += order.revenue_charged_back_usd
                total_service_fee_revenue_charged_back += (
                    order.service_fee_revenue_charged_back_usd
                )
            if self.has_non_usa_orders is False and order.currency_abbrev != "USD":
                self.has_non_usa_orders = True
                self.non_usa_currency_abbrev = order.currency_abbrev
                self.non_usa_currency_symbol = order.currency_symbol

            if self.has_shirt_data is False and len(order.shirts) > 0:
                self.has_shirt_data = True

            if (
                self.has_phone_data is False
                and order.phone is not None
                and len(order.phone) > 0
            ):
                self.has_phone_data = True

            if order.is_deleted is not True:
                total_revenue += order.revenue_usd
                total_service_fees += order.service_fees_usd
                total_tickets += order.numTickets

                if len(order.tickets) > 0:
                    for ticket in order.tickets:
                        if ticket.is_checked_in:
                            total_checked_in += 1

                if len(order.shirts) > 0:
                    total_shirts += len(order.shirts)
                    for size in order.shirts:
                        if size in shirtd:
                            shirtd[size] = int(shirtd[size]) + 1
                        else:
                            shirtd[size] = 1

        self.total_revenue = total_revenue
        self.total_service_fees = total_service_fees
        self.total_tickets = total_tickets
        self.total_checked_in = total_checked_in
        self.total_shirts = total_shirts
        self.num_tickets_refunded = total_tickets_refunded
        self.num_tickets_charged_back = total_tickets_refunded
        self.revenue_refunded = total_revenue_refunded
        self.revenue_charged_back = total_revenue_charged_back
        self.service_fee_revenue_refunded = total_service_fee_revenue_refunded
        self.service_fee_revenue_charged_back = total_service_fee_revenue_charged_back

        self.has_ticket_type_data = len(self.ticket_types) > 0

        shirt_sales: list[ShirtSales] = []
        for size, total in shirtd.items():
            shirt_sale = ShirtSales(str(size), int(total))
            shirt_sales.append(shirt_sale)
        self.shirt_sales = shirt_sales

        # roll up external event data, if any
        if self.external_title is not None and self.external_title != "":
            self.title = self.external_title

        if self.external_venue is not None:
            if self.external_venue.name is not None and self.external_venue.name != "":
                self.venue.name = self.external_venue.name
            if (
                self.external_venue.address1 is not None
                and self.external_venue.address1 != ""
            ):
                self.venue.address1 = self.external_venue.address1
            if (
                self.external_venue.address2 is not None
                and self.external_venue.address2 != ""
            ):
                self.venue.address2 = self.external_venue.address2
            if self.external_venue.city is not None and self.external_venue.city != "":
                self.venue.city = self.external_venue.city
            if (
                self.external_venue.state is not None
                and self.external_venue.state != ""
            ):
                self.venue.state = self.external_venue.state
            if (
                self.external_venue.postal_code is not None
                and self.external_venue.postal_code != ""
            ):
                self.venue.postal_code = self.external_venue.postal_code

        if self.external_thumbnail is not None and self.external_thumbnail != "":
            self.thumbnail = self.external_thumbnail

        if self.external_vip_link is not None and self.external_vip_link != "":
            self.ticket_socket_url = self.external_vip_link


class DailyOrderData:
    """
    Represents one row + rollup data for table DailyOrderData
    """

    ticket_socket_order_id: int = None
    orders: int = 0
    tickets: int = 0
    ticket_revenue_usd: float = 0
    service_fees_revenue_usd: float = 0
    total_revenue_usd: float = 0
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
    is_charged_back: bool = False
    num_tickets_refunded: int = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0

    def __init__(self, purchase_date: str, ticket_socket_event_id: int):
        self.purchase_date = purchase_date
        self.ticket_socket_event_id = ticket_socket_event_id


class DashboardTotals:
    """
    Totals rolled up for Admin dashboard
    """

    tickets: int = 0
    orders: int = 0
    num_tickets_refunded: int = 0
    ticket_revenue_usd: float = 0
    service_fees_revenue_usd: float = 0
    total_revenue_usd: float = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0
    price_per_ticket: float = 0
    service_fee_per_ticket: float = 0
    daily_order_data: list[DailyOrderData] = []

    def __init__(self, year: int, month: int, day: int):
        self.year = year
        self.month = month
        self.day = day
        self.days_in_month = calendar.monthrange(year, month)[1]
        self.day_of_year = datetime.datetime(year, month, day).timetuple().tm_yday
        self.total_days_in_year = datetime.datetime(year, 12, 31).timetuple().tm_yday
        sql = "SELECT * FROM Settings WHERE Name=%(name)s"
        data = {"name": "YearlyRevenueGoal"}
        row = db_query_one(sql, data)
        self.yearly_revenue_goal = float(row["Value"])
        data = {"name": "MonthlyRevenueGoal"}
        row = db_query_one(sql, data)
        self.monthly_revenue_goal = float(row["Value"])


class Seller:
    """
    Combination of internal id for TS account + TS category
    """

    hide_in_list: bool = False
    is_active: bool = True
    name: str = None
    seller_type: int = 1

    seller_event_categories: list[SellerEventCategory] = []

    def __init__(self, seller_id: int):
        self.seller_id = seller_id
        self.__initialize()

    def __initialize(self):
        """
        Initialize seller from database
        """
        sql = """SELECT * FROM Sellers
                 WHERE SellerId=%(sellerId)s"""
        data = {"sellerId": self.seller_id}

        row = db_query_one(sql, data)
        if row:
            self.name = str(row["Name"])
            self.seller_type = int(row["SellerTypeId"])
            self.hide_in_list = int(row["HideInList"]) == 1
            self.is_active = int(row["Inactive"]) != 1
            self.__get_seller_event_categories()

    def __get_seller_event_categories(self):
        """
        Fetch all categories from sellerId
        """
        sql = """SELECT SellerEventCategory.*
                  FROM SellerEventCategory
                 WHERE SellerId=%(sellerId)s"""
        data = {"sellerId": self.seller_id}

        seller_event_categories = []
        rows = db_query_all(sql, data)
        for row in rows:
            sec = SellerEventCategory(
                self.seller_id,
                int(row["TicketSocketId"]),
                int(row["EventCategoryId"]),
                int(row["SellerEventCategoryId"]),
            )
            seller_event_categories.append(sec)
        self.seller_event_categories = seller_event_categories

    def get_seller_event_category(self, ticket_socket_id: int):
        """
        Get event category assocaited with seller/TS account
        """
        if len(self.seller_event_categories) == 0:
            return None

        seller_event_category = None
        for sec in self.seller_event_categories:
            if sec.ticket_socket_id == ticket_socket_id:
                seller_event_category = sec
                break

        return seller_event_category

    def get_seller_event_category_ids(self):
        """
        Get seller event category id's from list of categories
        """
        ids: list[int] = []
        if len(self.seller_event_categories) > 0:
            for sec in self.seller_event_categories:
                ids.append(sec.seller_event_category_id)
        return ids


class TicketSocketRefreshHistory:
    """
    Represents a row in the TS refreh history table
    """

    seller_name: str = None
    user_name: str = None
    ticket_socket_refresh_history_id: int = None
    order_data_rows_removed: int = 0
    order_data_rows_updated: int = 0
    order_data_rows_inserted: int = 0
    order_data_rows_total: int = 0
    order_data_update_succeeded: bool = False
    order_data_update_duration: float = 0
    total_duration: float = 0

    def __init__(
        self,
        service_events_skipped: list[int],
        events_failed: list[int],
        orders_failed: list[int],
        tickets_failed: list[int],
        ticket_types_failed: list[int],
        total_events_from_service: int,
        events_updated: int,
        events_inserted: int,
        orders_inserted: int,
        orders_updated: int,
        orders_deleted: int,
        tickets_updated: int,
        tickets_inserted: int,
        ticket_types_updated: int,
        ticket_types_inserted: int,
        start_timer: int,
        end_timer: int,
        duration: float,
        user_id: int = 0,
        seller_id: int = 0,
        start: int = 0,
        end: int = 0,
        succeeded: bool = False,
        error_message: str = None,
    ):
        self.service_events_skipped = service_events_skipped
        self.events_failed = events_failed
        self.orders_failed = orders_failed
        self.tickets_failed = tickets_failed
        self.ticket_types_failed = ticket_types_failed
        self.total_events_from_service = total_events_from_service
        self.events_updated = events_updated
        self.events_inserted = events_inserted
        self.orders_inserted = orders_inserted
        self.orders_updated = orders_updated
        self.orders_deleted = orders_deleted
        self.tickets_updated = tickets_updated
        self.tickets_inserted = tickets_inserted
        self.ticket_types_updated = ticket_types_updated
        self.ticket_types_inserted = ticket_types_inserted
        self.user_id = user_id
        self.seller_id = seller_id
        self.start = start
        self.end = end
        self.start_timer = start_timer
        self.end_timer = end_timer
        self.duration = duration
        self.succeeded = succeeded
        self.error_message = error_message

    def __get_seller_name(self):
        """
        Get formatted seller name from Seller object
        """
        if self.seller_id is not None:
            seller = Seller(self.seller_id)
            self.seller_name = seller.name + " (SellerId: " + str(self.seller_id) + ")"

    def cleanup(self, cnx=None):
        """
        Clean up old history rows in the table
        """
        success: bool = True

        try:
            week_ago: int = self.end_timer - (24 * 60 * 60)
            sql = """DELETE FROM TicketSocketRefreshHistory WHERE EndTimer <= %(weekAgo)s"""
            data = {"weekAgo": week_ago}
            db_delete(sql, data, cnx)
        except RuntimeError as error:
            success = False
            error_message: str = str(error) + "\n" + traceback.format_exc()
            log_message(error_message)

        return success

    def set_order_update_success(
        self, success: bool, duration: float, inserts: int, updates: int, cnx=None
    ):
        """
        Set success for order update and rollup values
        """
        if self.ticket_socket_refresh_history_id <= 0:
            self.order_data_update_succeeded = False
            return

        self.order_data_update_succeeded = success
        self.order_data_update_duration = duration
        self.order_data_rows_inserted = inserts
        self.order_data_rows_updated = updates
        total_duration = self.duration + duration
        self.total_duration = total_duration

        sql = """UPDATE TicketSocketRefreshHistory SET OrderDataUpdateSucceeded=%(successVal)s,
                     OrderDataUpdateDuration=%(orderDataUpdateDuration)s, TotalDuration=%(totalDuration)s, 
                    OrderDataRowsTotal=%(orderDataRowsTotal)s, OrderDataRowsInserted=%(orderDataRowsInserted)s, 
                    OrderDataRowsUpdated=%(orderDataRowsUpdated)s, OrderDataRowsRemoved=%(orderDataRowsRemoved)s, 
                    LastUpdate=CURRENT_TIMESTAMP 
                    WHERE TicketSocketRefreshHistoryId=%(ticketSocketRefreshHistoryId)s"""
        data = {
            "successVal": 1 if success is True else 0,
            "ticketSocketRefreshHistoryId": self.ticket_socket_refresh_history_id,
            "orderDataUpdateDuration": duration,
            "totalDuration": total_duration,
            "orderDataRowsTotal": self.order_data_rows_total,
            "orderDataRowsInserted": self.order_data_rows_inserted,
            "orderDataRowsUpdated": self.order_data_rows_updated,
            "orderDataRowsRemoved": self.order_data_rows_removed,
        }
        db_update(sql, data, cnx)

    def commit(self, cnx=None):
        """
        Create new row in history table
        """
        if self.end_timer > 0:
            self.cleanup(cnx)

        self.__get_seller_name()

        sql = """INSERT INTO TicketSocketRefreshHistory (UserId, SellerId, Start,
                 End, StartTimer, EndTimer, Duration, Success, ErrorMessage,
                 ServiceEventsSkipped,  EventsFailed, OrdersFailed, TicketsFailed,
                 TicketTypesFailed, TotalEventsFromService, EventsUpdated, EventsInserted,  
                 OrdersInserted, OrdersUpdated, OrdersDeleted, TicketsUpdated, TicketsInserted,  
                 TicketTypesUpdated, TicketTypesInserted) VALUES (%(userId)s, %(sellerId)s, 
                 %(start)s, %(end)s, %(startTimer)s, %(endTimer)s, %(duration)s, %(success)s,
                 %(errorMessage)s, %(serviceEventsSkipped)s, %(eventsFailed)s, 
                 %(ordersFailed)s, %(ticketsFailed)s, %(ticketTypesFailed)s,
                 %(totalEventsFromService)s, %(eventsUpdated)s, %(eventsInserted)s, %(ordersInserted)s, 
                 %(ordersUpdated)s, %(ordersDeleted)s, %(ticketsUpdated)s, %(ticketsInserted)s,  
                 %(ticketTypesUpdated)s, %(ticketTypesInserted)s)"""

        data = {
            "userId": self.user_id,
            "sellerId": self.seller_id,
            "start": self.start,
            "end": self.end,
            "startTimer": self.start_timer,
            "endTimer": self.end_timer,
            "duration": self.duration,
            "success": 1 if self.succeeded is True else 0,
            "errorMessage": self.error_message,
            "serviceEventsSkipped": ", ".join(self.service_events_skipped),
            "eventsFailed": ", ".join(str(v) for v in self.events_failed),
            "ordersFailed": ", ".join(str(v) for v in self.orders_failed),
            "ticketsFailed": ", ".join(str(v) for v in self.tickets_failed),
            "ticketTypesFailed": ", ".join(str(v) for v in self.ticket_types_failed),
            "totalEventsFromService": self.total_events_from_service,
            "eventsUpdated": self.events_updated,
            "eventsInserted": self.events_inserted,
            "ordersInserted": self.orders_inserted,
            "ordersUpdated": self.orders_updated,
            "ordersDeleted": self.orders_deleted,
            "ticketsUpdated": self.tickets_updated,
            "ticketsInserted": self.tickets_inserted,
            "ticketTypesUpdated": self.ticket_types_updated,
            "ticketTypesInserted": self.ticket_types_inserted,
        }

        self.ticket_socket_refresh_history_id = db_insert(sql, data, cnx)

        return self.ticket_socket_refresh_history_id > 0
