"""
Dashboard Service
"""

from datetime import datetime
import pytz

from common.daily_order_service import DailyOrderService
from common.db import db_query_all, db_query_one

from common.models.national_acts import (
    DailyOrderData,
    DashboardTotals,
)
from common.order_service import OrderService
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class DashboardService:
    """
    Service to handle dashboard-related activity
    """

    def get_dashboard_data(self, year: int = 0):
        """
        Fetch most data needed for admin dashboard display
        """
        daily_order_data: list[DailyOrderData] = []
        month: int = 0
        day: int = 0
        current_year: int = 0
        now = None
        pacific_tz = pytz.timezone("America/Los_Angeles")

        if year > 0:
            current_year = year
            month = 12
            day = 31
        else:
            current_year = datetime.now(pacific_tz).year
            month = datetime.now(pacific_tz).month
            day = datetime.now(pacific_tz).day

        now = datetime(current_year, month, day)
        dash_totals = DashboardTotals(current_year, month, day)

        start = f"{current_year}-01-01 00:00:00"
        end = now.strftime("%Y-%m-%d 23:59:59")

        sql = """SELECT DailyOrderData.*,
                    COALESCE(ExternalEvents.Title, TicketSocketEvents.Title) AS Title,
                    COALESCE(ExternalEvents.EventDate, TicketSocketEvents.EventDate) AS EventDate,
                    COALESCE(ExternalEventVenues.Venue, TicketSocketEvents.Venue) AS Venue,
                    COALESCE(ExternalEventVenues.City, TicketSocketEvents.City) AS City,
                    COALESCE(ExternalEventVenues.State, TicketSocketEvents.State) AS State,
                    COALESCE(ExternalEventVenues.Zip, TicketSocketEvents.Zip) AS Zip, 
                    COALESCE(Country.CountryName, TicketSocketEvents.Country) AS Country,                    
                    Sellers.Name AS SellerName,
                    Sellers.SellerId,
                    TicketSocket.TicketSocketId,
                    TicketSocket.AccountName 
                    FROM DailyOrderData 
                    JOIN ExternalEvents 
                        ON ExternalEvents.TicketSocketEventId
                            = DailyOrderData.TicketSocketEventId 
                    JOIN TicketSocketEvents 
                        ON TicketSocketEvents.Id
                            = DailyOrderData.TicketSocketEventId 
                    JOIN SellerEventCategory 
                        ON SellerEventCategory.SellerEventCategoryId
                            = TicketSocketEvents.SellerEventCategoryId 
                    JOIN TicketSocket 
                        ON TicketSocket.TicketSocketId
                            = SellerEventCategory.TicketSocketId 
                    LEFT JOIN ExternalEventVenues
                        ON ExternalEventVenues.VenueID
                            = ExternalEvents.ExternalEventVenueId
                    LEFT JOIN Country ON
                        Country.CountryId = 
                            ExternalEventVenues.CountryId
                    JOIN Sellers
                        ON Sellers.SellerId = ExternalEvents.SellerId 
                 WHERE DailyOrderData.PurchaseDate
                    BETWEEN %(start)s and %(end)s 
                    ORDER BY DailyOrderData.PurchaseDate, Sellers.Name"""
        data = {"start": start, "end": end}

        rows = db_query_all(sql, data)
        for row in rows:
            purchase_date = get_override_string_value_or_default(row["PurchaseDate"])
            ticket_socket_event_id = get_override_int_value_or_default(
                row["TicketSocketEventId"]
            )
            exchange_rate = get_override_float_value_or_default(row["ExchangeRate"])
            currency_symbol = get_override_string_value_or_default(
                row["CurrencySymbol"]
            )
            order_data = DailyOrderData(
                purchase_date, ticket_socket_event_id, exchange_rate, currency_symbol
            )
            order_data.last_update = get_override_string_value_or_default(
                row["LastUpdate"]
            )
            order_data.event_title = get_override_string_value_or_default(row["Title"])
            order_data.event_date = get_override_string_value_or_default(
                row["EventDate"]
            )
            order_data.seller_id = get_override_int_value_or_default(row["SellerId"])
            order_data.seller_name = get_override_string_value_or_default(
                row["SellerName"]
            )
            order_data.venue = get_override_string_value_or_default(row["Venue"])
            order_data.city = get_override_string_value_or_default(row["City"])
            order_data.state = get_override_string_value_or_default(row["State"])
            order_data.country = get_override_string_value_or_default(row["Country"])
            order_data.zip = get_override_string_value_or_default(row["Zip"])
            order_data.tickets = get_override_int_value_or_default(row["Tickets"])
            order_data.orders = get_override_int_value_or_default(row["Orders"])
            order_data.ticket_revenue = get_override_float_value_or_default(
                row["TicketRevenue"]
            )
            order_data.ticket_revenue_usd = (
                order_data.ticket_revenue * order_data.exchange_rate
            )
            order_data.service_fees_revenue = get_override_float_value_or_default(
                row["ServiceFeeRevenue"]
            )
            order_data.service_fees_revenue_usd = (
                order_data.service_fees_revenue * order_data.exchange_rate
            )
            order_data.total_revenue = get_override_float_value_or_default(
                row["TotalRevenue"]
            )
            order_data.total_revenue_usd = (
                order_data.total_revenue * order_data.exchange_rate
            )
            order_data.ticket_socket_id = get_override_int_value_or_default(
                row["TicketSocketId"]
            )
            order_data.ticket_socket_order_id = get_override_int_value_or_default(
                row["TicketSocketOrderId"], default=None
            )
            order_data.is_refunded = get_override_bool_value_or_default(
                row["IsRefunded"]
            )
            if order_data.is_refunded is True:
                order_data.num_tickets_refunded = get_override_int_value_or_default(
                    row["NumTicketsRefunded"]
                )
                order_data.revenue_refunded = get_override_float_value_or_default(
                    row["RevenueRefunded"]
                )
                order_data.revenue_refunded_usd = (
                    order_data.revenue_refunded * order_data.exchange_rate
                )
                order_data.service_fee_revenue_refunded = (
                    get_override_float_value_or_default(
                        row["ServiceFeeRevenueRefunded"]
                    )
                )
                order_data.service_fee_revenue_refunded_usd = (
                    order_data.service_fee_revenue_refunded * order_data.exchange_rate
                )

            order_data.is_charged_back = get_override_bool_value_or_default(
                row["IsChargeback"]
            )
            if order_data.is_charged_back is True:
                order_data.num_tickets_charged_back = get_override_int_value_or_default(
                    row["NumTicketsChargedBack"]
                )
                order_data.revenue_charged_back = get_override_float_value_or_default(
                    row["RevenueChargedBack"]
                )
                order_data.revenue_charged_back_usd = (
                    order_data.revenue_charged_back * order_data.exchange_rate
                )
                order_data.service_fee_revenue_charged_back = (
                    get_override_float_value_or_default(
                        row["ServiceFeeRevenueChargedBack"]
                    )
                )
                order_data.service_fee_revenue_charged_back_usd = (
                    order_data.service_fee_revenue_charged_back
                    * order_data.exchange_rate
                )

            dash_totals.tickets += order_data.tickets
            dash_totals.orders += order_data.orders
            dash_totals.num_tickets_refunded += order_data.num_tickets_refunded
            dash_totals.num_tickets_charged_back += order_data.num_tickets_charged_back
            dash_totals.revenue_refunded += order_data.revenue_refunded
            dash_totals.revenue_refunded_usd += order_data.revenue_refunded_usd
            dash_totals.revenue_charged_back += order_data.revenue_charged_back
            dash_totals.revenue_charged_back_usd += order_data.revenue_charged_back_usd
            dash_totals.service_fee_revenue_refunded += (
                order_data.service_fee_revenue_refunded
            )
            dash_totals.service_fee_revenue_refunded_usd += (
                order_data.service_fee_revenue_refunded_usd
            )
            dash_totals.service_fee_revenue_charged_back += (
                order_data.service_fee_revenue_charged_back
            )
            dash_totals.service_fee_revenue_charged_back_usd += (
                order_data.service_fee_revenue_charged_back_usd
            )
            dash_totals.ticket_revenue += order_data.ticket_revenue
            dash_totals.ticket_revenue_usd += order_data.ticket_revenue_usd
            dash_totals.service_fees_revenue += order_data.service_fees_revenue
            dash_totals.service_fees_revenue_usd += order_data.service_fees_revenue_usd
            dash_totals.total_revenue += order_data.total_revenue
            dash_totals.total_revenue_usd += order_data.total_revenue_usd

            daily_order_data.append(order_data)

        dash_totals.daily_order_data = daily_order_data
        if dash_totals.tickets > 0:
            dash_totals.price_per_ticket = (
                dash_totals.ticket_revenue_usd
            ) / dash_totals.tickets
            dash_totals.service_fee_per_ticket = (
                dash_totals.service_fees_revenue_usd
            ) / dash_totals.tickets
        else:
            dash_totals.price_per_ticket = 0
            dash_totals.service_fee_per_ticket = 0
        return dash_totals

    def rebuild_daily_order_data_for_event(self, event_id: int):
        """
        Clean out and rebuild daily order data for event
        """
        event_sql = """SELECT TicketSocketEvents.Id as TicketSocketEventId,
                            YEAR(TicketSocketEvents.EventDate) AS EventYear, 
                            SellerEventCategory.SellerId,
                            COALESCE(ExternalEvents.ExcludeFromDashboard, 0) AS ExcludeFromDashboard
                            FROM TicketSocketEvents
                            JOIN SellerEventCategory ON 
                             TicketSocketEvents.SellerEventCategoryId = 
                             SellerEventCategory.SellerEventCategoryId                         
                            LEFT JOIN ExternalEvents ON
                             ExternalEvents.TicketSocketEventId = TicketSocketEvents.Id
                            WHERE TicketSocketEvents.Id=%(ticket_socket_event_id)s"""
        event_data = {"ticket_socket_event_id": event_id}
        event_row = db_query_one(event_sql, event_data)
        if event_row:
            event_id: int = get_override_int_value_or_default(
                event_row["TicketSocketEventId"]
            )
            hide_from_dashboard = get_override_bool_value_or_default(
                event_row["ExcludeFromDashboard"]
            )

            do_service = DailyOrderService()
            do_service.cleanup_daily_order_data_for_event(event_id)

            if not hide_from_dashboard:
                event_year: int = get_override_int_value_or_default(
                    event_row["EventYear"]
                )
                event_seller_id: int = get_override_int_value_or_default(
                    event_row["SellerId"]
                )

                start = datetime.strptime(
                    f"{event_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
                ).timestamp()
                end = datetime(event_year, 12, 31).timestamp()

                or_service = OrderService()
                orders = or_service.get_orders(
                    start=start, end=end, seller_id=event_seller_id
                )

                if len(orders) > 0:
                    do_service.update_daily_order_data(orders, start, end, None)
