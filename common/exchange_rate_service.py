"""
Service to pull exchange rates for currency from Stripe
"""

import os
import json
import http.client
from datetime import datetime
import time

from common.db import db_query_one, db_insert, db_update
from common.models.exchange_rate import ExchangeRate


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

        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "x-api-key": os.getenv("STRIPE_API_KEY"),
        }

        conn = http.client.HTTPSConnection("api.striperates.com")
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        exchange_rate_value: float = 1.0
        if response.status == 200:
            json_response = json.loads(response.read())
            json_data = json_response["data"]
            usd_rate = json_data[0]["rates"]["usd"]
            exchange_rate_value = float(usd_rate) * self.exchange_rate.multiplier

        return round(exchange_rate_value, 5)

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

        utci_yr = int(utc_date_incoming.strftime("%Y"))
        utci_mo = int(utc_date_incoming.strftime("%m"))
        utci_dy = int(utc_date_incoming.strftime("%d"))
        utc_incoming_midnight_time = datetime(utci_yr, utci_mo, utci_dy)
        midnight_date = utc_incoming_midnight_time.strftime("%Y-%m-%d")

        utc_date_current = datetime.fromtimestamp(int(time.time()))
        utcc_yr = int(utc_date_current.strftime("%Y"))
        utcc_mo = int(utc_date_current.strftime("%m"))
        utcc_dy = int(utc_date_current.strftime("%d"))
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
            existing_rate = float(row["USDRate"])

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
                sql2 = """INSERT INTO ExchangeRateHistory (ExchangeRateId, MidnightDate, USDRate)
                           VALUES(%(exchangeRateId)s, %(midnightDate)s, %(currentRate)s)"""

                data2 = {
                    "exchangeRateId": self.exchange_rate.exchange_rate_id,
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
                    "exchangeRateId": self.exchange_rate.exchange_rate_id,
                    "midnightDate": midnight_date,
                    "currentRate": current_rate,
                }
                success = db_update(sql2, data2)
                if success:
                    existing_rate = current_rate

        self.exchange_rate.usd_rate = existing_rate if existing_rate != 0 else 1
        return self.exchange_rate
