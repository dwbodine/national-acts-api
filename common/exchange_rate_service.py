"""
Service to pull exchange rates for currency from Stripe
"""

import os
from datetime import datetime
import time

from common.db import db_query_one, db_insert, db_update
from common.models.exchange_rate import ExchangeRate
from common.utility import (
    get_https_response,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
)


class ExchangeRateService:
    """
    Pulls exchange rate data from Stripe
    """

    def __init__(self, exchange_rate: ExchangeRate):
        self.exchange_rate = exchange_rate

    def __get_current_rate(self, unix_time: int = None):
        """
        Call to Stripe for exchange rate
        """
        url = "/rates/" + self.exchange_rate.exchange_rate_slug

        if unix_time is not None:
            exchange_date = datetime.fromtimestamp(unix_time)
            url += "/" + exchange_date.isoformat()

        exchange_rate_value: float = 1.0
        api_key = os.getenv("STRIPE_API_KEY")
        if api_key is not None:
            json_data = get_https_response(
                host="api.striperates.com", url=url, api_key=api_key
            )

            if json_data is not None and len(json_data) > 0:
                usd_rate = json_data[0]["rates"]["usd"]
                exchange_rate_value = float(usd_rate)

        return round(exchange_rate_value, 8)

    def get_exchange_rate_by_time(
        self, unix_time: int = None, force_update: bool = False
    ):
        """
        Get exchange rate from history for a specific date
        """

        if self.exchange_rate is None:
            return 1

        if unix_time is None:
            unix_time = time.time()

        utc_date_incoming = datetime.fromtimestamp(unix_time)

        utci_yr = get_override_int_value_or_default(utc_date_incoming.strftime("%Y"))
        utci_mo = get_override_int_value_or_default(utc_date_incoming.strftime("%m"))
        utci_dy = get_override_int_value_or_default(utc_date_incoming.strftime("%d"))
        utc_incoming_midnight_time = datetime(utci_yr, utci_mo, utci_dy)
        midnight_date = utc_incoming_midnight_time.strftime("%Y-%m-%d")

        utc_date_current = datetime.fromtimestamp(int(time.time()))
        utcc_yr = get_override_int_value_or_default(utc_date_current.strftime("%Y"))
        utcc_mo = get_override_int_value_or_default(utc_date_current.strftime("%m"))
        utcc_dy = get_override_int_value_or_default(utc_date_current.strftime("%d"))
        utc_current_midnight_time = datetime(utcc_yr, utcc_mo, utcc_dy)

        existing_rate: float = 0

        sql = """SELECT * FROM ExchangeRateHistory
                WHERE ExchangeRateId=%(exchangeRateId)s 
                AND MidnightDate=%(midnightDate)s"""

        data = {
            "exchangeRateId": self.exchange_rate.exchange_rate_id,
            "midnightDate": midnight_date,
        }

        row = db_query_one(sql, data)
        if row:
            existing_rate = get_override_float_value_or_default(row["USDRate"])

        success: bool = True
        if (
            force_update is True
            or existing_rate == 0
            or utc_incoming_midnight_time.timestamp()
            >= utc_current_midnight_time.timestamp()
        ):

            if force_update is not True:
                unix_time = None

            current_rate: float = self.__get_current_rate(unix_time)

            if existing_rate == 0:
                sql2 = """INSERT INTO ExchangeRateHistory
                            (ExchangeRateId, MidnightDate, USDRate, LastUpdated)
                           VALUES (%(exchangeRateId)s, %(midnightDate)s,
                           %(currentRate)s, CURRENT_TIMESTAMP)"""

                data2 = {
                    "exchangeRateId": get_override_int_value_or_default(
                        self.exchange_rate.exchange_rate_id
                    ),
                    "midnightDate": midnight_date,
                    "currentRate": current_rate,
                }
                exchange_rate_id = db_insert(sql2, data2)
                if exchange_rate_id > 0:
                    existing_rate = current_rate
            elif current_rate != existing_rate:
                sql2 = """UPDATE ExchangeRateHistory SET USDRate=%(currentRate)s,
                            LastUpdated=CURRENT_TIMESTAMP 
                            WHERE ExchangeRateId=%(exchangeRateId)s
                            AND MidnightDate=%(midnightDate)s"""

                data2 = {
                    "exchangeRateId": get_override_int_value_or_default(
                        self.exchange_rate.exchange_rate_id
                    ),
                    "midnightDate": midnight_date,
                    "currentRate": current_rate,
                }
                success = db_update(sql2, data2)
                if success:
                    existing_rate = current_rate

        self.exchange_rate.usd_rate = existing_rate if existing_rate != 0 else 1
        return self.exchange_rate
