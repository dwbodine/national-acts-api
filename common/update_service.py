"""
Perform Cron job updates
"""

from datetime import datetime
import pytz
import traceback
import phonenumbers
from common.db import db_query_all, db_query_one, db_update
from common.exchange_rate_service import ExchangeRateService, ExchangeRate
from common.data_refresh_service import DataRefreshService
from common.daily_order_service import DailyOrderService
from common.models.national_acts import TicketSocketRefreshHistory
from common.order_service import OrderService
from common.report_service import ReportService
from common.utility import (
    clean_up_phone_input_for_parsing,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    log_message,
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
        pacific_tz = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
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
        pacific_tz = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
        result_message: str = f"[{now}] - "

        service = DataRefreshService()
        results: TicketSocketRefreshHistory = None
        try:
            results = service.refresh_database_from_ticket_socket()

            if results is not None and results.succeeded is True:
                current_year = datetime.now(pacific_tz).year
                month = datetime.now(pacific_tz).month
                day = datetime.now(pacific_tz).day

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

    def format_all_phone_numbers(self):
        """
        Reformat all existing phone numbers in the database using Python phonenumbers library
        """
        success: bool = True
        sql = """SELECT TicketSocketOrders.Id,
                TicketSocketOrders.Phone, 
                COALESCE(Country.CountryCode, 'US') AS CountryCode
                FROM TicketSocketOrders 
                JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId
                JOIN ExternalEvents ON ExternalEvents.TicketSocketEventId = TicketSocketEvents.Id
                LEFT JOIN ExternalEventVenues ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
                LEFT JOIN Country ON Country.CountryId = ExternalEventVenues.CountryId
                WHERE TicketSocketOrders.Phone IS NOT NULL"""
        rows = db_query_all(sql)
        for row in rows:
            order_id = get_override_int_value_or_default(row["Id"])
            phone = get_override_string_value_or_default(row["Phone"])
            country_code = get_override_string_value_or_default(row["CountryCode"])
            phone = clean_up_phone_input_for_parsing(phone)
            phone_formatted: str = None
            if phone is not None and len(phone) > 0:
                try:
                    z = phonenumbers.parse(phone, country_code)
                    if phonenumbers.is_possible_number(z):
                        phone_formatted = phonenumbers.format_number(
                            z,
                            phonenumbers.PhoneNumberFormat.INTERNATIONAL,
                        )
                except Exception as error:  # pylint: disable=broad-exception-caught
                    error_message: str = str(error) + "\n" + traceback.format_exc()
                    pacific_tz = pytz.timezone("America/Los_Angeles")
                    now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
                    log_message(f"""[{now}] - {error_message}\r\n""")
                    phone_formatted = None
            update_sql = """UPDATE TicketSocketOrders SET PhoneFormatted=%(phone)s,
                            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                            WHERE Id=%(order_id)s"""
            update_data = {"phone": phone_formatted, "order_id": order_id}
            success = db_update(update_sql, update_data)
            if success is not True:
                break
        return success

    def clear_out_missing_thumbnails(self):
        """
        Clears out the thumbnail field in old events if it says it's missing
        """
        success: bool = True
        service = ReportService()
        report = service.get_orphaned_and_missing_thumbnail_images()
        if report.missing is not None and len(report.missing) > 0:
            for missing_image in report.missing:
                data = {"thumb": missing_image}
                find_sql = """SELECT * FROM ExternalEvents WHERE Thumbnail=%(thumb)s LIMIT 0, 1"""
                row = db_query_one(find_sql, data)
                if row:
                    sql = """UPDATE ExternalEvents SET Thumbnail=NULL,
                            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                            WHERE Thumbnail=%(thumb)s and EventDate < CURRENT_DATE"""

                    success = db_update(sql, data)
                if success is not True:
                    break
        return success
