"""
Models specific to event/order data and National Acts' integration with TicketSocket
"""

import calendar
import datetime
import traceback
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    log_message,
)
from common.models.ticket_socket import (
    TicketSocketTicket,
    TicketSocketOrder,
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
    has_events: bool = False

    def __eq__(self, other):
        return (
            self.seller_id == other.seller_id
            and self.ticket_socket_id == other.ticket_socket_id
        )

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
        self.__find_events()

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
            self.event_category_id = get_override_int_value_or_default(
                sec["EventCategoryId"]
            )
            self.seller_event_category_id = get_override_int_value_or_default(
                sec["SellerEventCategoryId"]
            )

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
            self.seller_id = get_override_int_value_or_default(sec["SellerId"])
            self.seller_event_category_id = get_override_int_value_or_default(
                sec["SellerEventCategoryId"]
            )

    def __populate_from_seller_event_category_id(self, seller_event_category_id: int):
        self.seller_event_category_id = seller_event_category_id
        sql = """SELECT * FROM SellerEventCategory
                WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"""
        data = {"sellerEventCategoryId": self.seller_event_category_id}
        sec = db_query_one(sql, data)
        if sec:
            self.seller_id = get_override_int_value_or_default(sec["SellerId"])
            self.ticket_socket_id = get_override_int_value_or_default(
                sec["TicketSocketId"]
            )
            self.event_category_id = get_override_int_value_or_default(
                sec["EventCategoryId"]
            )

    def __find_events(self):
        sql = """SELECT COUNT(TicketSocketEvents.Id) AS NumEvents
                FROM TicketSocketEvents 
                WHERE TicketSocketEvents.SellerEventCategoryId = 
                %(sellerEventCategoryId)s"""
        data = {"sellerEventCategoryId": self.seller_event_category_id}
        row = db_query_one(sql, data)
        self.has_events = get_override_bool_value_or_default(row["NumEvents"])


class ShirtSales:
    """
    Shirt sale data
    """

    def __init__(self, size: str, total: int):
        self.size = size
        self.total = total


class Note:
    """
    Note system for event or order
    """

    note_id: int = 0
    external_event_id: int = None
    note: str = None
    note_title: str = None
    note_timestamp: str = None
    is_completed: bool = False


class VipTicket(TicketSocketTicket):
    """
    National acts specific verison of TS tickets
    """

    ticket_socket_order_id: int = 0
    ticket_socket_order_ticket_id: int = 0
    is_checked_in: bool = False
    checked_in_date: str = None
    is_refunded: bool = False
    is_active: bool = False
    refund_date: str = None
    is_charged_back: bool = False
    chargeback_date: str = None
    is_service_fee_refunded: bool = False
    attendee_phone: str = None
    attendee_email: str = None
    last_update: str = None


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
    is_comped: bool = False
    has_refunds: bool = False
    has_chargebacks: bool = False
    num_tickets: int = 0
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
    revenue: float = 0
    revenue_usd: float = 0
    service_fees: float = 0
    service_fees_usd: float = 0
    exchange_rate: float = 1.0
    currency_symbol: str = None
    currency_abbrev: str = None
    tickets: list[VipTicket] = []

    def get_totals(self):
        """
        Roll up data from tickets to order
        """
        total_revenue: float = 0
        total_service_fees: float = 0
        total_shirts: int = 0
        total_tickets: int = 0

        for ticket in self.tickets:
            total_tickets += 1
            if ticket.shirt_size is not None:
                total_shirts += 1
            if ticket.is_refunded is True:
                self.has_refunds = True
                self.num_tickets_refunded += 1
                self.revenue_refunded += ticket.price
                if ticket.is_service_fee_refunded is True:
                    self.service_fee_revenue_refunded += ticket.service_fee
                else:
                    total_service_fees += ticket.service_fee
            elif ticket.is_charged_back is True:
                self.has_chargebacks = True
                self.num_tickets_charged_back += 1
                self.revenue_charged_back += ticket.price
                self.service_fee_revenue_charged_back += ticket.service_fee
            else:
                total_revenue += ticket.price
                total_service_fees += ticket.service_fee

        self.num_tickets = total_tickets
        self.revenue = total_revenue
        self.service_fees = total_service_fees
        self.total_shirts = total_shirts

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

    # TicketSocketEvent properties
    ticket_socket_event_id: int = 0
    seller_event_category_id: int = None
    is_vip: bool = True
    is_sold_out: bool = False

    # ExternalEvent properties
    external_event_id: int = None
    seller_id: int = None
    meet_and_greet_time: str = None
    doors_open: str = None
    event_time: str = None
    external_url: str = None
    external_event_venue_id: int = None
    disable_link_button: bool = False
    disable_link_reason: str = None
    external_vip_link: str = None
    disable_vip_link_button: bool = False
    disable_vip_link_reason: str = None
    is_active: bool = True
    is_added_to_bands_in_town: bool = False
    is_hidden: bool = False
    is_cancelled: bool = False
    announce_date: str = None
    cancelled_date: str = None
    is_deleted: bool = False
    email_sent_to_vips: bool = False
    text_sent_to_vips: bool = False
    list_sent_to_band: bool = False
    list_sent_time: str = None
    list_sent_num_vips: int = None
    check_in_location: str = None
    check_in_notes: str = None
    external_thumbnail: str = None

    # collections
    notes: list[Note] = []
    orders: list[VipOrder] = []

    # other database properties
    seller_name: str = ""
    non_usa_currency_symbol: str = None
    non_usa_currency_abbrev: str = None
    tour_announce_date: str = None

    # computed properties
    is_external: bool = False
    total_revenue: float = 0
    total_service_fees: float = 0
    total_tickets: int = 0
    total_checked_in: int = 0
    total_shirts: int = 0
    shirt_sales: list[ShirtSales] = []
    has_shirt_data: bool = False
    has_phone_data: bool = False
    has_non_usa_orders: bool = False
    num_tickets_refunded: int = 0
    revenue_refunded: float = 0
    service_fee_revenue_refunded: float = 0
    num_tickets_charged_back: int = 0
    revenue_charged_back: float = 0
    service_fee_revenue_charged_back: float = 0
    has_ticket_type_data: bool = False
    num_tickets_comped: int = 0

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
        total_tickets_comped: int = 0
        total_revenue_refunded: float = 0
        total_revenue_charged_back: float = 0
        total_service_fee_revenue_refunded: float = 0
        total_service_fee_revenue_charged_back: float = 0
        total_checked_in: int = 0
        shirtd: dict = {}
        for order in self.orders:
            if order.is_comped is True:
                total_tickets_comped += order.num_tickets
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

            if self.has_shirt_data is False and order.total_shirts > 0:
                self.has_shirt_data = True

            if (
                self.has_phone_data is False
                and order.phone is not None
                and len(order.phone) > 0
            ):
                self.has_phone_data = True

            if order.is_deleted is not True and order.is_comped is not True:
                total_revenue += order.revenue_usd
                total_service_fees += order.service_fees_usd
                total_tickets += order.num_tickets

                if len(order.tickets) > 0:
                    for ticket in order.tickets:
                        if ticket.is_checked_in:
                            total_checked_in += 1

                if order.total_shirts > 0:
                    total_shirts += order.total_shirts
                    for ticket in order.tickets:
                        size = ticket.shirt_size
                        if size in shirtd:
                            shirtd[size] = int(shirtd[size]) + 1
                        else:
                            shirtd[size] = 1

        self.num_tickets_comped = total_tickets_comped
        self.total_revenue = total_revenue
        self.total_service_fees = total_service_fees
        self.total_tickets = total_tickets
        self.total_checked_in = total_checked_in
        self.total_shirts = total_shirts
        self.num_tickets_refunded = total_tickets_refunded
        self.num_tickets_charged_back = total_tickets_charged_back
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
    num_tickets_charged_back: int = 0
    revenue_refunded: float = 0
    revenue_charged_back: float = 0
    service_fee_revenue_refunded: float = 0
    service_fee_revenue_charged_back: float = 0

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
    num_tickets_charged_back: int = 0
    ticket_revenue_usd: float = 0
    service_fees_revenue_usd: float = 0
    total_revenue_usd: float = 0
    revenue_refunded: float = 0
    revenue_charged_back: float = 0
    service_fee_revenue_refunded: float = 0
    service_fee_revenue_charged_back: float = 0
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
        self.yearly_revenue_goal = get_override_float_value_or_default(row["Value"])
        data = {"name": "MonthlyRevenueGoal"}
        row = db_query_one(sql, data)
        self.monthly_revenue_goal = get_override_float_value_or_default(row["Value"])


class Seller:
    """
    Combination of internal id for TS account + TS category
    """

    hide_in_list: bool = False
    is_active: bool = True
    name: str = None
    seller_type: int = 1
    address: str = None
    city: str = None
    state: str = None
    zip: str = None
    country: str = None
    phone: str = None
    email: str = None
    twitter: str = None
    facebook: str = None
    instagram: str = None
    youtube: str = None
    spotify: str = None
    website: str = None
    website_display_text: str = None

    seller_event_categories: list[SellerEventCategory] = []

    def __init__(self, seller_id: int = None):
        if seller_id is not None:
            self.seller_id = seller_id
            self.__initialize()

    def __initialize(self):
        """
        Initialize seller from database
        """
        sql = """SELECT Sellers.*
            FROM Sellers
            WHERE Sellers.SellerId=%(sellerId)s"""
        data = {"sellerId": self.seller_id}

        row = db_query_one(sql, data)
        if row:
            self.name = get_override_string_value_or_default(row["Name"])
            self.seller_type = get_override_int_value_or_default(row["SellerTypeId"])
            self.address = get_override_string_value_or_default(row["Address"])
            self.city = get_override_string_value_or_default(row["City"])
            self.state = get_override_string_value_or_default(row["State"])
            self.zip = get_override_string_value_or_default(row["Zip"])
            self.country = get_override_string_value_or_default(row["Country"])
            self.phone = get_override_string_value_or_default(row["Phone"])
            self.email = get_override_string_value_or_default(row["Email"])
            self.twitter = get_override_string_value_or_default(row["Twitter"])
            self.facebook = get_override_string_value_or_default(row["Facebook"])
            self.instagram = get_override_string_value_or_default(row["Instagram"])
            self.youtube = get_override_string_value_or_default(row["YouTube"])
            self.spotify = get_override_string_value_or_default(row["Spotify"])
            self.website = get_override_string_value_or_default(row["Website"])
            self.website_display_text = get_override_string_value_or_default(
                row["WebsiteDisplayText"]
            )
            self.hide_in_list = get_override_bool_value_or_default(row["HideInList"])
            self.is_active = not get_override_bool_value_or_default(row["Inactive"])

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
                get_override_int_value_or_default(row["TicketSocketId"]),
                get_override_int_value_or_default(row["EventCategoryId"]),
                get_override_int_value_or_default(row["SellerEventCategoryId"]),
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
    username: str = None
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
        except Exception as error:  # pylint: disable=broad-exception-caught
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
                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                    WHERE TicketSocketRefreshHistoryId=%(ticketSocketRefreshHistoryId)s"""
        data = {
            "successVal": get_override_tinyint_value_or_default_from_bool(success),
            "ticketSocketRefreshHistoryId": get_override_int_value_or_default(
                self.ticket_socket_refresh_history_id
            ),
            "orderDataUpdateDuration": get_override_float_value_or_default(duration),
            "totalDuration": get_override_float_value_or_default(total_duration),
            "orderDataRowsTotal": get_override_int_value_or_default(
                self.order_data_rows_total
            ),
            "orderDataRowsInserted": get_override_int_value_or_default(
                self.order_data_rows_inserted
            ),
            "orderDataRowsUpdated": get_override_int_value_or_default(
                self.order_data_rows_updated
            ),
            "orderDataRowsRemoved": get_override_int_value_or_default(
                self.order_data_rows_removed
            ),
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
                 TicketTypesUpdated, TicketTypesInserted, LastUpdate) VALUES (%(userId)s, %(sellerId)s, 
                 %(start)s, %(end)s, %(startTimer)s, %(endTimer)s, %(duration)s, %(success)s,
                 %(errorMessage)s, %(serviceEventsSkipped)s, %(eventsFailed)s, 
                 %(ordersFailed)s, %(ticketsFailed)s, %(ticketTypesFailed)s,
                 %(totalEventsFromService)s, %(eventsUpdated)s, %(eventsInserted)s, %(ordersInserted)s, 
                 %(ordersUpdated)s, %(ordersDeleted)s, %(ticketsUpdated)s, %(ticketsInserted)s,  
                 %(ticketTypesUpdated)s, %(ticketTypesInserted)s,
                 CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

        data = {
            "userId": get_override_int_value_or_default(self.user_id),
            "sellerId": get_override_int_value_or_default(self.seller_id),
            "start": get_override_int_value_or_default(self.start),
            "end": get_override_int_value_or_default(self.end),
            "startTimer": get_override_int_value_or_default(self.start_timer),
            "endTimer": get_override_int_value_or_default(self.end_timer),
            "duration": get_override_float_value_or_default(self.duration),
            "success": get_override_tinyint_value_or_default_from_bool(self.succeeded),
            "errorMessage": get_override_string_value_or_default(self.error_message),
            "serviceEventsSkipped": ", ".join(self.service_events_skipped),
            "eventsFailed": (
                ", ".join(str(v) for v in self.events_failed)
                if self.events_failed is not None
                else None
            ),
            "ordersFailed": (
                ", ".join(str(v) for v in self.orders_failed)
                if self.orders_failed is not None
                else None
            ),
            "ticketsFailed": (
                ", ".join(str(v) for v in self.tickets_failed)
                if self.tickets_failed is not None
                else None
            ),
            "ticketTypesFailed": (
                ", ".join(str(v) for v in self.ticket_types_failed)
                if self.ticket_types_failed is not None
                else None
            ),
            "totalEventsFromService": get_override_int_value_or_default(
                self.total_events_from_service
            ),
            "eventsUpdated": get_override_int_value_or_default(self.events_updated),
            "eventsInserted": get_override_int_value_or_default(self.events_inserted),
            "ordersInserted": get_override_int_value_or_default(self.orders_inserted),
            "ordersUpdated": get_override_int_value_or_default(self.orders_updated),
            "ordersDeleted": get_override_int_value_or_default(self.orders_deleted),
            "ticketsUpdated": get_override_int_value_or_default(self.tickets_updated),
            "ticketsInserted": get_override_int_value_or_default(self.tickets_inserted),
            "ticketTypesUpdated": get_override_int_value_or_default(
                self.ticket_types_updated
            ),
            "ticketTypesInserted": get_override_int_value_or_default(
                self.ticket_types_inserted
            ),
        }

        self.ticket_socket_refresh_history_id = db_insert(sql, data, cnx)

        return self.ticket_socket_refresh_history_id > 0


class Tour:
    """
    Represents a tour or grouping of events
    """

    tour_id: int
    sellers: list[Seller] = []
    tour_name: str
    is_active: bool = True
    announce_date: str
    events: list[VipEvent] = []
