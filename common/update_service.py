"""
Perform Cron job updates
"""

from datetime import datetime
import traceback
from common.db import db_query_all
from common.exchange_rate_service import ExchangeRateService, ExchangeRate
from common.data_refresh_service import DataRefreshService
from common.daily_order_service import DailyOrderService
from common.models.national_acts import TicketSocketRefreshHistory
from common.order_service import OrderService
from common.utility import (
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


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
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_message: str = f"[{now}] - "
        try:
            rates: list[ExchangeRate] = []
            sql = "select * from ExchangeRates"
            rows = db_query_all(sql)
            for row in rows:
                service = ExchangeRateService(
                    ExchangeRate(
                        get_override_int_value_or_default(row["ExchangeRateId"]),
                        get_override_string_value_or_default(row["ServiceTokenId"]),
                        get_override_float_value_or_default(row["Multiplier"]),
                    )
                )
                rate = service.get_exchange_rate_by_time(unix_time, force_update)
                rates.append(rate)

            if len(rates) > 0:
                result_message += "Exchange rates update succeeded\r\n"
            else:
                result_message += "Exchange rates update failed\r\n"
        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            result_message = f"[{now}] - {error_message}\r\n"

        return result_message

    def update_all_events_from_ticket_socket(self):
        """
        Update all upcoming events/orders/tickets/ticket types from TS
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_message: str = f"[{now}] - "

        service = DataRefreshService()
        results: TicketSocketRefreshHistory = None
        try:
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

                if results.succeeded:
                    result_message += "Auto events update succeeded\r\n"
                else:
                    result_message += f"""Auto events update failed
                        - Message: {results.error_message}\r\n"""

        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            result_message = f"[{now}] - {error_message}\r\n"

        return result_message

    def update_historical_events_from_ticket_socket(self, start: int, end: int):
        """
        Update all upcoming events/orders/tickets/ticket types from TS
        """
        service = DataRefreshService()
        results = service.refresh_database_from_ticket_socket(start=start, end=end)
        if results is not None and results.succeeded is True:
            order_service = OrderService()
            orders = order_service.get_orders(start=start, end=end)

            daily_order_service = DailyOrderService()
            results = daily_order_service.update_daily_order_data(
                orders, start, end, results
            )

        return results
