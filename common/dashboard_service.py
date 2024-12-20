"""
Dashboard Service
"""

from datetime import datetime, timedelta

from common.db import db_query_all

from common.models.national_acts import (
    DailyOrderData,
    DashboardTotals,
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

        if year > 0:
            current_year = year
            month = 12
            day = 31
        else:
            current_year = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day

        now = datetime(current_year, month, day)
        dash_totals = DashboardTotals(current_year, month, day)

        start = f"{current_year}-01-01 00:00:00"
        end = now.strftime("%Y-%m-%d 23:59:59")

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
