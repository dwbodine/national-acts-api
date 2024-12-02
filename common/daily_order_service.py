"""
Daily Order Service
"""

import time
from datetime import datetime

from common.db import (
    db_query_one,
    db_update,
    db_insert,
    db_delete,
)
from common.models.national_acts import (
    VipOrder,
    DailyOrderData,
    TicketSocketRefreshHistory,
)


class DailyOrderService:
    """
    Service to handle daily order-related activity
    """

    def update_daily_order_data(
        self,
        orders: list[VipOrder],
        start: int,
        end: int,
        history: TicketSocketRefreshHistory = None,
    ):
        """
        Pulls order data from the database and rolls it up to DailyOrderData
        """
        timer: float = time.time()
        duration: float = 0
        daily_order_data = self.__get_daily_order_data_from_orders(orders, start, end)
        duration = time.time() - timer

        if history is not None:
            history.order_data_rows_total = len(daily_order_data)

            if len(daily_order_data) <= 0:
                history.order_data_update_succeeded = False
                return history

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
                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
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
                                    TicketSocketOrderId, LastUpdate) VALUES (%(purchaseDate)s,
                                    %(ticketSocketEventId)s, %(orders)s, %(tickets)s,
                                    %(ticketRevenue)s, %(serviceFeeRevenue)s, %(totalRevenue)s,
                                    %(isRefunded)s, %(isChargeback)s, %(numTicketsRefunded)s,
                                    %(revenueRefunded)s, %(serviceFeeRevenueRefunded)s,
                                    %(numTicketsChargedBack)s, %(revenueChargedBack)s,
                                    %(serviceFeeRevenueChargedBack)s,
                                    %(ticketSocketOrderId)s, CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

                daily_order_data_id = db_insert(insert_sql, update_data)
                success = daily_order_data_id > 0
                if success:
                    inserts += 1
            if success is not True:
                break

        duration = time.time() - timer
        if history is not None:
            history.set_order_update_success(success, duration, inserts, updates)

        return history

    def __get_daily_order_data_from_orders(
        self, orders: list[VipOrder], start: int, end: int
    ):
        """
        extracts daily order data for update to database
        """
        daily_order_data: list[DailyOrderData] = []

        regular_orders: int = 0
        refund_orders: int = 0
        chargeback_orders: int = 0

        for order in orders:
            if order.is_deleted is True or order.is_comped is True:
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

    def cleanup_daily_order_data_for_event(self, event_id: int):
        """
        Clear out rows from DailyOrderData ahead of rebuild
        (which would be needed in refunds, cancellations and chargebacks)
        """
        sql = """DELETE FROM DailyOrderData
          WHERE TicketSocketEventId=%(ticketSocketEventId)s"""
        data = {"ticketSocketEventId": event_id}
        db_delete(sql, data)
