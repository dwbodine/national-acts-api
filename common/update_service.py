"""
Perform Cron job updates
"""

from datetime import datetime
import logging
import traceback
import re
import pytz
import phonenumbers
from common.dashboard_service import DashboardService
from common.db import db_query_all, db_query_one, db_update
from common.exchange_rate_service import ExchangeRateService, ExchangeRate
from common.data_refresh_service import DataRefreshService
from common.daily_order_service import DailyOrderService
from common.models.national_acts import TicketSocketRefreshHistory
from common.order_service import OrderService
from common.report_service import ReportService
from common.utility import (
    clean_up_phone_input_for_parsing,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
                        get_override_string_value_or_default(row["Symbol"]),
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
        logger.info("Starting update_all_events_from_ticket_socket")
        pacific_tz = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
        result_message: str = f"[{now}] - "

        service = DataRefreshService()
        results: TicketSocketRefreshHistory = None
        try:
            logger.info("Starting refresh_database_from_ticket_socket")
            results = service.refresh_database_from_ticket_socket()
            logger.info("refresh_database_from_ticket_socket complete")

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
            logger.error(result_message)

        logger.info(
            "update_all_events_from_ticket_socket complete, result_message = %s",
            result_message,
        )
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
                    logger.error("%s", error_message)
                    phone_formatted = None
            update_sql = """UPDATE TicketSocketOrders SET PhoneFormatted=%(phone)s,
                            LastUpdate=CURRENT_TIMESTAMP
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
                            LastUpdate=CURRENT_TIMESTAMP
                            WHERE Thumbnail=%(thumb)s and EventDate < CURRENT_DATE"""

                    success = db_update(sql, data)
                if success is not True:
                    break
        return success

    def clean_up_html(self):
        """
        Clears out the thumbnail field in old events if it says it's missing
        """
        success: bool = True

        sql = (
            """SELECT PageID, HTMLText FROM Pages WHERE COALESCE(HTMLText, '') <> ''"""
        )
        rows = db_query_all(sql)
        for row in rows:
            page_id = get_override_int_value_or_default(row["PageID"])
            html_text = get_override_string_value_or_default(row["HTMLText"])

            if html_text is not None:
                new_html = re.sub(
                    r"<!DOCTYPE[^>[]*(\[[^]]*\])?>", "", html_text, flags=re.IGNORECASE
                )
                new_html = re.sub(r"<html.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"<head.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"<meta.*?\/>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"<meta.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(
                    r"<title.*?<\/title>", "", new_html, flags=re.IGNORECASE
                )
                new_html = re.sub(r"<\/head.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"<body.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"<\/body.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"<\/html.*?>", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"\\n\\n\\n", "", new_html, flags=re.IGNORECASE)
                new_html = re.sub(r"\\n\\n", "", new_html, flags=re.IGNORECASE)
                new_html = new_html.strip()

                if len(new_html) == 0:
                    new_html = None

                if new_html != html_text:
                    update_sql = """UPDATE Pages
                                        SET HTMLText=%(html_text)s 
                                        WHERE PageID=%(page_id)s"""
                    data = {
                        "html_text": new_html,
                        "page_id": page_id,
                    }
                    success = db_update(update_sql, data)

                if success is not True:
                    break

        return success

    def rebuild_daily_order_data_for_year(self, year: int, month: int):
        """
        Fetches a list of events for the year for a seller and
        rebuilds the daily order data for them
        """
        sql = """SELECT Id FROM TicketSocketEvents
            WHERE YEAR(TicketSocketEvents.EventDate) = %(year)s 
            AND MONTH(TicketSocketEvents.EventDate) = %(month)s 
            AND EXISTS(SELECT 1 FROM TicketSocketOrders WHERE
                TicketSocketOrders.TicketSocketEventId = TicketSocketEvents.Id)"""
        data = {"year": year, "month": month}
        rows = db_query_all(sql, data)
        num_events = len(rows)
        counter = 0
        dashboard_service = DashboardService()
        for row in rows:
            event_id = get_override_int_value_or_default(row["Id"])
            dashboard_service.rebuild_daily_order_data_for_event(event_id)
            counter += 1

        return counter == num_events
