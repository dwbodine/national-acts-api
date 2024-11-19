"""
Perform Cron job updates
"""

from datetime import datetime
from common.db import db_query_all
from common.exchange_rate_service import ExchangeRateService, ExchangeRate
from common.data_refresh_service import DataRefreshService
from common.daily_order_service import DailyOrderService
from common.order_service import OrderService


class UpdateService:
    """
    Service to perform update/migration tasks
    """

    def update_all_exchange_rates_from_stripe(
        self, unix_time: int = None, force_update: bool = False
    ):
        """
        Update all exchange rates from Stripe
        """
        rates: list[ExchangeRate] = []
        sql = "select * from ExchangeRates"
        rows = db_query_all(sql)
        for row in rows:
            service = ExchangeRateService(
                ExchangeRate(
                    int(row["ExchangeRateId"]),
                    row["ServiceTokenId"],
                    float(row["Multiplier"]),
                )
            )
            rate = service.get_exchange_rate_by_time(unix_time, force_update)
            rates.append(rate)
        return rates

    def update_all_events_from_ticket_socket(self):
        """
        Update all upcoming events/orders/tickets/ticket types from TS
        """
        service = DataRefreshService()
        results = service.refresh_database_from_ticket_socket()
        if results is not None and results.succeeded is True:
            current_year = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day

            start = datetime.strptime(
                f"{current_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
            ).timestamp()
            end = datetime(current_year, month, day).timestamp()

            order_service = OrderService()
            orders = order_service.get_orders(start=start, end=end)

            daily_order_service = DailyOrderService()
            results = daily_order_service.update_daily_order_data(
                orders, start, end, results
            )

        return results
