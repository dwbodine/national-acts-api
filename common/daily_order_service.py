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
from common.models.exchange_rate import ExchangeRate
from common.models.national_acts import (
    VipOrder,
    DailyOrderData,
    TicketSocketRefreshHistory,
)
from common.utility import (
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    get_pacific_purchase_date_from_order,
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
                "ticketRevenue": order_data.ticket_revenue,
                "serviceFeeRevenue": order_data.service_fees_revenue,
                "totalRevenue": order_data.total_revenue,
                "isRefunded": get_override_tinyint_value_or_default_from_bool(
                    order_data.is_refunded
                ),
                "isChargeback": get_override_tinyint_value_or_default_from_bool(
                    order_data.is_charged_back
                ),
                "numTicketsRefunded": order_data.num_tickets_refunded,
                "revenueRefunded": order_data.revenue_refunded,
                "serviceFeeRevenueRefunded": order_data.service_fee_revenue_refunded,
                "numTicketsChargedBack": order_data.num_tickets_charged_back,
                "revenueChargedBack": order_data.revenue_charged_back,
                "serviceFeeRevenueChargedBack": order_data.service_fee_revenue_charged_back,
                "ticketSocketOrderId": order_data.ticket_socket_order_id,
                "exchangeRate": order_data.exchange_rate,
                "currencySymbol": order_data.currency_symbol,
            }

            if existing_data:
                daily_order_data_id = int(existing_data["DailyOrderDataId"])
                update_sql = """UPDATE DailyOrderData
                                SET Orders=%(orders)s,
                                Tickets=%(tickets)s,
                                ExchangeRate=%(exchangeRate)s,
                                CurrencySymbol=%(currencySymbol)s,
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
                                    Orders, Tickets, ExchangeRate, CurrencySymbol,
                                    TicketRevenue, ServiceFeeRevenue, TotalRevenue, IsRefunded,
                                    IsChargeback, NumTicketsRefunded, RevenueRefunded,
                                    ServiceFeeRevenueRefunded, NumTicketsChargedBack,
                                    RevenueChargedBack, ServiceFeeRevenueChargedBack,
                                    TicketSocketOrderId, LastUpdate) VALUES (%(purchaseDate)s,
                                    %(ticketSocketEventId)s, %(orders)s, %(tickets)s,
                                    %(exchangeRate)s, %(currencySymbol)s, %(ticketRevenue)s,
                                    %(serviceFeeRevenue)s, %(totalRevenue)s, %(isRefunded)s,
                                    %(isChargeback)s, %(numTicketsRefunded)s, %(revenueRefunded)s,
                                    %(serviceFeeRevenueRefunded)s, %(numTicketsChargedBack)s,
                                    %(revenueChargedBack)s, %(serviceFeeRevenueChargedBack)s,
                                    %(ticketSocketOrderId)s,
                                    CURRENT_TIMESTAMP)"""

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

        for order in orders:
            # skip deleted or comped orders
            if order.is_deleted is True or order.is_comped is True:
                continue

            purchase_date_pacific = get_pacific_purchase_date_from_order(order)
            ticket_socket_event_id: int = order.ticket_socket_event_id
            ticket_socket_order_id: int = order.ticket_socket_order_id

            # daily order data is keyed off of purchase timestamp for purchases,
            # refund date for refunds and chargeback date for chargebacks
            purchase_timestamp = datetime.strptime(
                purchase_date_pacific, "%Y-%m-%d"
            ).timestamp()

            order_data: DailyOrderData = None
            found_index: int = -1

            refund_order_data: DailyOrderData = None
            found_refund_index: int = -1

            chargeback_order_data: DailyOrderData = None
            found_chargeback_index: int = -1

            # see if we don't have an entry for this event already
            for do_idx, do in enumerate(daily_order_data):
                if do.ticket_socket_event_id == ticket_socket_event_id:
                    if (
                        order.has_refunds is True
                        and do.ticket_socket_order_id == ticket_socket_order_id
                    ):
                        refund_order_data = do
                        found_refund_index = do_idx
                    elif (
                        order.has_chargebacks is True
                        and do.ticket_socket_order_id == ticket_socket_order_id
                    ):
                        chargeback_order_data = do
                        found_chargeback_index = do_idx
                    elif do.purchase_date == purchase_date_pacific:
                        order_data = do
                        found_index = do_idx
                        break

            # handle adding entry for refund/chargeback if we don't have it
            if order.has_refunds is True and refund_order_data is None:
                for ticket in order.tickets:
                    if ticket.is_refunded is True and refund_order_data is None:
                        refund_date = None
                        for ticket in order.tickets:
                            if ticket.refund_date is not None:
                                refund_date = ticket.refund_date
                                break
                        exchange_rate: ExchangeRate = None
                        if refund_date is not None:
                            exchange_rate = self.get_exchange_rate_for_order_by_date(
                                ticket_socket_order_id, refund_date
                            )
                        usd_rate = (
                            exchange_rate.usd_rate if exchange_rate is not None else 1
                        )
                        symbol = (
                            exchange_rate.currency_symbol
                            if exchange_rate is not None
                            else "$"
                        )
                        refund_order_data = DailyOrderData(
                            ticket.refund_date,
                            ticket_socket_event_id,
                            usd_rate,
                            symbol,
                        )
                        refund_order_data.ticket_socket_order_id = (
                            ticket_socket_order_id
                        )
                        refund_order_data.is_refunded = True
                        refund_order_data.is_charged_back = False
                    elif ticket.is_refunded is not True and order_data is None:
                        exchange_rate: ExchangeRate = (
                            self.get_exchange_rate_for_order_by_date(
                                ticket_socket_event_id, purchase_date_pacific
                            )
                        )
                        usd_rate = (
                            exchange_rate.usd_rate if exchange_rate is not None else 1
                        )
                        symbol = (
                            exchange_rate.currency_symbol
                            if exchange_rate is not None
                            else "$"
                        )
                        order_data = DailyOrderData(
                            purchase_date_pacific,
                            ticket_socket_event_id,
                            usd_rate,
                            symbol,
                        )
                        order_data.ticket_socket_order_id = None
                        order_data.is_refunded = False
                        order_data.is_charged_back = False
            elif order.has_chargebacks is True and chargeback_order_data is None:
                for ticket in order.tickets:
                    if ticket.is_charged_back and chargeback_order_data is None:
                        chargeback_date = None
                        for ticket in order.tickets:
                            if ticket.chargeback_date is not None:
                                chargeback_date = ticket.chargeback_date
                                break
                        exchange_rate: ExchangeRate = None
                        if chargeback_date is not None:
                            exchange_rate = self.get_exchange_rate_for_order_by_date(
                                ticket_socket_order_id, chargeback_date
                            )
                        usd_rate = (
                            exchange_rate.usd_rate if exchange_rate is not None else 1
                        )
                        symbol = (
                            exchange_rate.currency_symbol
                            if exchange_rate is not None
                            else "$"
                        )
                        chargeback_order_data = DailyOrderData(
                            ticket.chargeback_date,
                            ticket_socket_event_id,
                            usd_rate,
                            symbol,
                        )
                        chargeback_order_data.ticket_socket_order_id = (
                            ticket_socket_order_id
                        )
                        chargeback_order_data.is_refunded = False
                        chargeback_order_data.is_charged_back = True
                    elif ticket.is_charged_back is not True and order_data is None:
                        exchange_rate = self.get_exchange_rate_for_order_by_date(
                            ticket_socket_order_id, purchase_date_pacific
                        )
                        usd_rate = (
                            exchange_rate.usd_rate if exchange_rate is not None else 1
                        )
                        symbol = (
                            exchange_rate.currency_symbol
                            if exchange_rate is not None
                            else "$"
                        )
                        order_data = DailyOrderData(
                            purchase_date_pacific,
                            ticket_socket_event_id,
                            usd_rate,
                            symbol,
                        )
                        order_data.ticket_socket_order_id = None
                        order_data.is_refunded = False
                        order_data.is_charged_back = False

            # handle adding entry for purchase if we don't have it
            if order_data is None and (start <= purchase_timestamp <= end):
                exchange_rate = self.get_exchange_rate_for_order_by_date(
                    ticket_socket_order_id, purchase_date_pacific
                )
                usd_rate = exchange_rate.usd_rate if exchange_rate is not None else 1
                symbol = (
                    exchange_rate.currency_symbol if exchange_rate is not None else "$"
                )
                order_data = DailyOrderData(
                    purchase_date_pacific, ticket_socket_event_id, usd_rate, symbol
                )
                order_data.ticket_socket_order_id = None
                order_data.is_refunded = False
                order_data.is_charged_back = False

            if refund_order_data is not None:
                refund_order_data.num_tickets_refunded += order.num_tickets_refunded
                refund_order_data.revenue_refunded += order.revenue_refunded
                refund_order_data.service_fee_revenue_refunded += (
                    order.service_fee_revenue_refunded
                )
                if found_refund_index >= 0:
                    daily_order_data[found_refund_index] = refund_order_data
                else:
                    daily_order_data.append(refund_order_data)

            if chargeback_order_data is not None:
                chargeback_order_data.num_tickets_charged_back += (
                    order.num_tickets_charged_back
                )
                chargeback_order_data.revenue_charged_back += order.revenue_charged_back
                chargeback_order_data.service_fee_revenue_charged_back += (
                    order.service_fee_revenue_charged_back
                )
                if found_chargeback_index >= 0:
                    daily_order_data[found_chargeback_index] = chargeback_order_data
                else:
                    daily_order_data.append(chargeback_order_data)

            if order_data is not None:
                order_data.orders += 1
                order_data.tickets += order.num_tickets
                order_data.ticket_revenue += order.revenue
                order_data.service_fees_revenue += order.service_fees
                order_data.total_revenue += order.revenue + order.service_fees
                if found_index >= 0:
                    daily_order_data[found_index] = order_data
                else:
                    daily_order_data.append(order_data)

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

    def get_exchange_rate_for_order_by_date(
        self, ticket_socket_order_id: int, midnight_date: str
    ) -> ExchangeRate:
        """
        Used to pull an exchange rate for an order by a specific date -
        helpful in calculating USD for purchase or refunds
        """
        sql = """SELECT COALESCE(ExchangeRateHistory.USDRate, 1.0) AS ExchangeRate,
                ExchangeRates.ServiceTokenId AS ExchangeRateSlug,
                ExchangeRates.Symbol AS CurrencySymbol,
                ExchangeRates.Multiplier AS Multiplier,
                ExchangeRates.ExchangeRateId AS ExchangeRateId
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
                LEFT JOIN ExchangeRateHistory ON ExchangeRateHistory.ExchangeRateId = ExchangeRates.ExchangeRateId
                WHERE TicketSocketOrders.Id=%(ticket_socket_order_id)s and ExchangeRateHistory.MidnightDate=%(midnight_date)s
                LIMIT 0,1"""

        data = {
            "ticket_socket_order_id": ticket_socket_order_id,
            "midnight_date": midnight_date,
        }

        row = db_query_one(sql, data)
        exchange_rate: ExchangeRate = None
        if row:
            exchange_rate_usd = get_override_float_value_or_default(row["ExchangeRate"])
            exchange_rate_slug = get_override_string_value_or_default(
                row["ExchangeRateSlug"]
            )
            exchange_rate_symbol = get_override_string_value_or_default(
                row["CurrencySymbol"]
            )
            exchange_rate_id = get_override_int_value_or_default(row["ExchangeRateId"])
            multiplier = get_override_float_value_or_default(row["Multiplier"])
            exchange_rate = ExchangeRate(
                exchange_rate_id, exchange_rate_slug, exchange_rate_symbol
            )
            if multiplier > 0:
                exchange_rate.usd_rate = exchange_rate_usd * multiplier
        return exchange_rate
