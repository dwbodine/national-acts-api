"""
Perform Cron job updates
"""

from common.db import db_query_all
from common.exchange_rate_service import ExchangeRateService, ExchangeRate
from common.event_service import EventService


class UpdateService:
    """
    Service to perform update/migration tasks
    """

    def update_all_exchange_rates_from_stripe(self):
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
            rate = service.get_exchange_rate_by_time()
            rates.append(rate)
        return rates

    def update_all_events_from_ticket_socket(self):
        """
        Update all upcoming events/orders/tickets/ticket types from TS
        """
        service = EventService()
        results = service.refresh_database_from_ticket_socket()
        if results is not None and results.succeeded is True:
            results = service.update_daily_order_data(results)

        return results
