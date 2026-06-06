"""
Admin service module
"""

import os

from datetime import datetime
import pytz
from common.constants import ImageType
from common.dashboard_service import DashboardService
from common.db import db_delete, db_query_all, db_insert, db_query_one, db_update
from common.event_service import EventService
from common.models.admin import ExternalVenue, SiteSetting, SiteSettingType
from common.models.national_acts import TicketSocketRefreshHistory, VipEvent
from common.models.ticket_socket import (
    Country,
    TicketSocketAccount,
    TicketSocketVenue,
    Timezone,
)
from common.order_service import OrderService
from common.ticket_socket_service import TicketSocketService
from common.utility import (
    get_bucket_name_from_image_type,
    get_country_from_country_name,
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    get_timezones_from_country_code,
    remove_file,
)


class AdminService:
    """
    Service to handle miscellaneous site admin functions
    """

    def get_site_settings(self):
        """
        Fetch all site settings from database
        """
        settings: list[SiteSetting] = []
        sql = "SELECT * FROM Settings ORDER BY Name ASC"
        rows = db_query_all(sql)
        for row in rows:
            setting = SiteSetting()
            setting.setting_id = get_override_int_value_or_default(row["ID"])
            setting.name = get_override_string_value_or_default(row["Name"])
            setting.display_name = get_override_string_value_or_default(
                row["DisplayName"]
            )
            setting.type = get_override_string_value_or_default(row["Type"])
            setting.value = get_override_string_value_or_default(row["Value"])
            setting.file_path = get_override_string_value_or_default(row["FilePath"])
            setting.dirty = False
            settings.append(setting)

        return settings

    def update_setting(self, setting: SiteSetting):
        """
        Add or update site setting to database
        """
        if setting is None:
            return False

        success: bool = True
        data = {
            "name": get_override_string_value_or_default(setting.name),
            "displayName": get_override_string_value_or_default(setting.display_name),
            "type": get_override_string_value_or_default(setting.type),
            "value": get_override_string_value_or_default(setting.value),
        }
        orig_value: str = None
        if setting.setting_id is None or setting.setting_id <= 0:
            sql = """INSERT INTO Settings (Name, DisplayName, Type, Value)
                     VALUES(%(name)s, %(displayName)s, %(type)s, %(value)s)"""
            setting_id = db_insert(sql, data)
            success = setting_id > 0
        else:
            orig_sql = """SELECT Value FROM Settings WHERE ID=%(setting_id)s"""
            orig_data = {"setting_id": setting.setting_id}
            orig_row = db_query_one(orig_sql, orig_data)
            if orig_row:
                orig_value = get_override_string_value_or_default(orig_row["Value"])

            sql = """UPDATE Settings
                        SET Name=%(name)s, 
                        DisplayName=%(displayName)s,
                        Type=%(type)s, 
                        Value=%(value)s, 
                        LastUpdated=CURRENT_TIMESTAMP
                        WHERE ID=%(setting_id)s"""
            data["setting_id"] = get_override_int_value_or_default(setting.setting_id)
            success = db_update(sql, data)

            if (
                setting.type == SiteSettingType.IMAGE
                and orig_value is not None
                and orig_value != setting.value
            ):
                bucket_name = get_bucket_name_from_image_type(ImageType.HOMEBANNERS)
                remove_file(orig_value, bucket_name)

        return success

    def get_ticket_socket_accounts(self):
        """
        Fetch current ticket socket account data
        """
        accounts: list[TicketSocketAccount] = []
        sql = "SELECT TicketSocketId FROM TicketSocket ORDER BY TicketSocketId"
        rows = db_query_all(sql)
        for row in rows:
            ticket_socket_id = get_override_int_value_or_default(row["TicketSocketId"])
            service = TicketSocketService(ticket_socket_id)
            account = TicketSocketAccount()
            account.ticket_socket_id = ticket_socket_id
            account.name = get_override_string_value_or_default(service.name)
            account.currency_symbol = get_override_string_value_or_default(
                service.currency_symbol
            )
            account.exchange_rate_id = get_override_int_value_or_default(
                service.exchange_rate_id
            )
            account.exchange_rate_slug = get_override_string_value_or_default(
                service.exchange_rate_slug
            )
            account.service_url = get_override_string_value_or_default(
                service.service_url
            )
            account.utc_offset_hours = get_override_int_value_or_default(
                service.utc_offset_hours
            )
            account.categories = service.get_categories()
            accounts.append(account)
        return accounts

    def get_all_accounts(self):
        """
        Gets stored data for all TS accounts
        """
        accounts: list[TicketSocketService] = []
        sql = "SELECT TicketSocketId FROM TicketSocket ORDER BY TicketSocketId"
        rows = db_query_all(sql)
        for row in rows:
            ticket_socket_id = get_override_int_value_or_default(row["TicketSocketId"])
            account = TicketSocketService(ticket_socket_id)
            accounts.append(account)
        return accounts

    def get_external_venues(self, search_term: str = None):
        """
        Fetch all external venues from database
        """
        venues: list[ExternalVenue] = []
        sql = """SELECT ExternalEventVenues.VenueID,
            ExternalEventVenues.Venue,
            ExternalEventVenues.Address,
            ExternalEventVenues.City,
            ExternalEventVenues.State,
            ExternalEventVenues.Zip,
            ExternalEventVenues.CountryId,
            ExternalEventVenues.TimeZone,
            Country.CountryName,
            Country.CountryCode,
            (SELECT 1 FROM ExternalEvents
                WHERE ExternalEvents.ExternalEventVenueId = 
                ExternalEventVenues.VenueID Limit 0, 1) as HasEvents
            FROM ExternalEventVenues 
            LEFT JOIN Country on Country.CountryId = ExternalEventVenues.CountryId """
        if search_term is not None and len(search_term) >= 3:
            sql += """WHERE CONCAT_WS (' ', COALESCE(Country.CountryName, ''),
                    COALESCE(ExternalEventVenues.Venue, ''),
                    COALESCE(ExternalEventVenues.Address, ''),
                    COALESCE(ExternalEventVenues.City, ''),
                    COALESCE(ExternalEventVenues.State, ''))
                    LIKE ('%""" + search_term + """%') """
        sql += """ORDER BY Venue ASC"""
        sql = sql.replace("\n", "")
        rows = db_query_all(sql)
        for row in rows:
            venue = ExternalVenue()
            venue.venue_id = get_override_int_value_or_default(row["VenueID"])
            venue.venue = get_override_string_value_or_default(row["Venue"])
            venue.address = get_override_string_value_or_default(row["Address"])
            venue.city = get_override_string_value_or_default(row["City"])
            venue.state = get_override_string_value_or_default(row["State"])
            venue.zip_code = get_override_string_value_or_default(row["Zip"])
            timezone = Timezone()
            timezone.timezone = get_override_string_value_or_default(row["TimeZone"])
            venue.timezone = timezone
            country_id = get_override_int_value_or_default(row["CountryId"])
            country_name = get_override_string_value_or_default(row["CountryName"])
            country_code = get_override_string_value_or_default(row["CountryCode"])
            if country_id is not None and country_code is not None:
                country = Country(country_id, country_name, country_code)
                timezones = get_timezones_from_country_code(country_code)
                country.timezones = timezones
                venue.country = country
            venue.has_events = get_override_bool_value_or_default(row["HasEvents"])
            venues.append(venue)

        return venues

    def update_external_venue(self, venue: ExternalVenue):
        """
        Add a venue to the database
        """

        success = False
        sql = ""
        default_country_id = get_override_int_value_or_default(
            os.getenv("DEFAULT_COUNTRY_ID"), default=None
        )
        country_id = default_country_id
        if venue.country is not None and venue.country.country_id is not None:
            country_id = get_override_int_value_or_default(
                venue.country.country_id, default_country_id
            )
        data = {
            "venue": get_override_string_value_or_default(venue.venue),
            "address": get_override_string_value_or_default(venue.address),
            "city": get_override_string_value_or_default(venue.city),
            "state": get_override_string_value_or_default(venue.state),
            "zip": get_override_string_value_or_default(venue.zip_code),
            "country_id": country_id,
            "timezone": get_override_string_value_or_default(venue.timezone.timezone),
        }

        if venue.venue_id is None or venue.venue_id == 0:
            sql = """INSERT INTO ExternalEventVenues
                        (Venue, Address, City, State, Zip, CountryId, TimeZone)
                     VALUES(%(venue)s, %(address)s, %(city)s, %(state)s,
                     %(zip)s, %(country_id)s, %(timezone)s)"""
            venue_id = db_insert(sql, data)
            success = venue_id > 0
            venue.venue_id = venue_id
        else:
            data["venue_id"] = get_override_int_value_or_default(venue.venue_id)
            sql = """UPDATE ExternalEventVenues SET Venue=%(venue)s,
                        Address=%(address)s,
                        City=%(city)s, 
                        State=%(state)s,
                        Zip=%(zip)s,
                        CountryId=%(country_id)s,
                        TimeZone=%(timezone)s
                        WHERE VenueID=%(venue_id)s"""
            success = db_update(sql, data)
        return venue if success is True else None

    def delete_external_venue(self, venue_id: int):
        """
        Remove a venue from the database
        """

        sql = """DELETE FROM ExternalEventVenues WHERE VenueID=%(venue_id)s"""
        data = {"venue_id": venue_id}
        db_delete(sql, data)
        return True

    def get_all_countries(self, country_code: str = None):
        """
        Gets stored data for countries
        """
        countries: list[Country] = []
        data = {}
        sql = """SELECT * FROM Country"""
        if country_code is not None:
            sql += """ WHERE CountryCode=%(country_code)s"""
            data["country_code"] = country_code
        sql += """ ORDER BY CountryName ASC"""
        rows = db_query_all(sql, data)
        for row in rows:
            country_id = get_override_int_value_or_default(row["CountryId"])
            country_name = get_override_string_value_or_default(row["CountryName"])
            country_code = get_override_string_value_or_default(row["CountryCode"])
            country = Country(country_id, country_name, country_code)
            if country.country_code is None:
                continue
            timezones = get_timezones_from_country_code(country_code)
            country.timezones = timezones
            countries.append(country)
        return countries

    def get_ticket_socket_refresh_history(self):
        """
        Get history of TS refresh for admin screen
        """
        logs: list[TicketSocketRefreshHistory] = []

        sql = """SELECT TicketSocketRefreshHistory.*,
                CONCAT(Users.FirstName, ' ', Users.LastName) AS UserName,
                Users.UserName AS Email, Sellers.Name AS SellerName
                FROM TicketSocketRefreshHistory 
                LEFT JOIN Users ON Users.UserId = TicketSocketRefreshHistory.UserId
                LEFT JOIN Sellers ON Sellers.SellerId = TicketSocketRefreshHistory.SellerId
                ORDER BY TicketSocketRefreshHistory.StartTimer DESC"""

        rows = db_query_all(sql)
        for row in rows:
            user_id = get_override_int_value_or_default(row["UserId"])
            if user_id == 0:
                username = "System"
            else:
                username = (
                    get_override_string_value_or_default(row["UserName"])
                    + " ("
                    + get_override_string_value_or_default(row["Email"])
                    + ")"
                )
            seller_id = get_override_int_value_or_default(row["SellerId"], default=None)
            seller_name = get_override_string_value_or_default(row["SellerName"])
            start = get_override_int_value_or_default(row["Start"], default=None)
            end = get_override_int_value_or_default(row["End"], default=None)
            start_timer = get_override_int_value_or_default(row["StartTimer"])
            end_timer = get_override_int_value_or_default(row["EndTimer"])
            duration = get_override_float_value_or_default(row["Duration"])
            succeeded = get_override_bool_value_or_default(row["Success"])
            error_message = get_override_string_value_or_default(row["ErrorMessage"])
            service_events_skipped = get_override_string_value_or_default(
                row["ServiceEventsSkipped"]
            )
            events_failed = get_override_string_value_or_default(row["EventsFailed"])
            orders_failed = get_override_string_value_or_default(row["OrdersFailed"])
            tickets_failed = get_override_string_value_or_default(row["TicketsFailed"])
            ticket_types_failed = get_override_string_value_or_default(
                row["TicketTypesFailed"]
            )
            total_events_from_service = get_override_int_value_or_default(
                row["TotalEventsFromService"]
            )
            events_updated = get_override_int_value_or_default(row["EventsUpdated"])
            events_inserted = get_override_int_value_or_default(row["EventsInserted"])
            orders_inserted = get_override_int_value_or_default(row["OrdersInserted"])
            orders_updated = get_override_int_value_or_default(row["OrdersUpdated"])
            orders_deleted = get_override_int_value_or_default(row["OrdersDeleted"])
            tickets_updated = get_override_int_value_or_default(row["TicketsUpdated"])
            tickets_inserted = get_override_int_value_or_default(row["TicketsInserted"])
            ticket_types_updated = get_override_int_value_or_default(
                row["TicketTypesUpdated"]
            )
            ticket_types_inserted = get_override_int_value_or_default(
                row["TicketTypesInserted"]
            )
            order_data_update_succeeded = get_override_bool_value_or_default(
                row["OrderDataUpdateSucceeded"]
            )
            order_data_update_duration = get_override_float_value_or_default(
                row["OrderDataUpdateDuration"]
            )
            total_duration = get_override_float_value_or_default(row["TotalDuration"])
            order_data_rows_total = get_override_int_value_or_default(
                row["OrderDataRowsTotal"]
            )
            order_data_rows_inserted = get_override_int_value_or_default(
                row["OrderDataRowsInserted"]
            )
            order_data_rows_updated = get_override_int_value_or_default(
                row["OrderDataRowsUpdated"]
            )
            order_data_rows_removed = get_override_int_value_or_default(
                row["OrderDataRowsRemoved"]
            )

            history = TicketSocketRefreshHistory(
                service_events_skipped,
                events_failed,
                orders_failed,
                tickets_failed,
                ticket_types_failed,
                total_events_from_service,
                events_updated,
                events_inserted,
                orders_inserted,
                orders_updated,
                orders_deleted,
                tickets_updated,
                tickets_inserted,
                ticket_types_updated,
                ticket_types_inserted,
                start_timer,
                end_timer,
                duration,
                user_id,
                seller_id,
                start,
                end,
                succeeded,
                error_message,
            )
            history.seller_name = seller_name
            history.username = username
            history.order_data_update_succeeded = order_data_update_succeeded
            history.order_data_update_duration = order_data_update_duration
            history.order_data_rows_total = order_data_rows_total
            history.order_data_rows_updated = order_data_rows_updated
            history.order_data_rows_removed = order_data_rows_removed
            history.order_data_rows_inserted = order_data_rows_inserted
            history.total_duration = total_duration
            logs.append(history)

        return logs

    def get_ticket_socket_events_only(self, seller_id: int = None):
        """
        Fetch only TS events for association with External Events
        """
        events: list[VipEvent] = []
        sql = """SELECT SellerEventCategory.SellerId,
                SellerEventCategory.IsVisibleOnSite,
                SellerEventCategory.IsVisibleOnPortal,
                TicketSocketEvents.*
            FROM TicketSocketEvents
            JOIN SellerEventCategory 
                ON SellerEventCategory.SellerEventCategoryId =
                TicketSocketEvents.SellerEventCategoryId """

        data = {}

        if seller_id is not None:
            sql += """ WHERE SellerEventCategory.SellerId=%(seller_id)s"""
            data["seller_id"] = seller_id

        sql += " ORDER BY TicketSocketEvents.EventDate, TicketSocketEvents.Title"

        rows = db_query_all(sql, data)
        for row in rows:
            vip_event = VipEvent()
            vip_event.ticket_socket_event_id = get_override_int_value_or_default(
                row["Id"]
            )
            vip_event.is_visible_on_site = get_override_bool_value_or_default(
                row["IsVisibleOnSite"]
            )
            vip_event.is_visible_on_portal = get_override_bool_value_or_default(
                row["IsVisibleOnPortal"]
            )
            vip_event.event_id = get_override_int_value_or_default(row["EventId"])
            vip_event.title = get_override_string_value_or_default(row["Title"])
            vip_event.event_date = get_override_string_value_or_default(
                row["EventDate"]
            )
            vip_event.thumbnail = get_override_string_value_or_default(row["Thumbnail"])
            vip_event.ticket_socket_url = get_override_string_value_or_default(
                row["URL"]
            )

            state = get_override_string_value_or_default(row["State"])
            zip_code = get_override_string_value_or_default(row["Zip"])
            country_name = get_override_string_value_or_default(row["Country"])
            country = get_country_from_country_name(country_name, state, zip_code)

            if country is not None and country.country_code is not None:
                timezones = get_timezones_from_country_code(
                    country.country_code, vip_event.event_date
                )
                country.timezones = timezones
            else:
                country = Country(None, country_name, None)

            vip_event.venue = TicketSocketVenue(
                get_override_string_value_or_default(row["Venue"]),
                get_override_string_value_or_default(row["Address"]),
                get_override_string_value_or_default(row["City"]),
                state,
                zip_code,
                country,
                "",
            )
            vip_event.is_vip = get_override_bool_value_or_default(row["IsVip"])
            vip_event.is_sold_out = get_override_bool_value_or_default(row["IsSoldOut"])
            events.append(vip_event)
        return events

    def cancel_event(
        self,
        event_ids: list[int],
        is_cancelled: bool = False,
    ):
        """
        Marks event as cancelled or not
        """
        success: bool = True
        pacific_tz = pytz.timezone("America/Los_Angeles")
        if len(event_ids) > 0:
            for event_id in event_ids:
                data = {
                    "event_id": event_id,
                    "cancelled_date": datetime.now(pacific_tz).strftime("%Y-%m-%d"),
                }
                sql = ""
                if is_cancelled is True:
                    sql = """UPDATE ExternalEvents
                                SET IsCancelled=1,
                                CancelledDate=%(cancelled_date)s,
                                LastUpdate=CURRENT_TIMESTAMP
                                WHERE EventId=%(event_id)s"""
                else:
                    sql = """UPDATE ExternalEvents
                                SET IsCancelled=0,
                                CancelledDate=NULL,
                                LastUpdate=CURRENT_TIMESTAMP
                                WHERE EventId=%(event_id)s"""

                success = db_update(sql, data)

        return success

    def refund_all_event_orders(
        self,
        event_id: int,
        refund_service_fees: bool = False,
        mark_cancelled: bool = False,
    ):
        """
        Refunds all orders in an event one at a time
        """
        success: bool = True

        if mark_cancelled is True:
            success = self.cancel_event([event_id], True)

        if success is True:
            sql = """SELECT TicketSocketOrders.Id AS OrderId,
                        TicketSocketEvents.Id AS EventId
                        FROM TicketSocketOrders
                        JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId
                        JOIN ExternalEvents ON ExternalEvents.TicketSocketEventId = TicketSocketEvents.Id
                        WHERE ExternalEvents.EventId=%(event_id)s"""
            data = {"event_id": event_id}
            rows = db_query_all(sql, data)
            ticket_socket_event_id: int = None
            if len(rows) > 0:
                for row in rows:
                    order_id = get_override_int_value_or_default(row["OrderId"])
                    if ticket_socket_event_id is None:
                        ticket_socket_event_id = get_override_int_value_or_default(
                            row["EventId"]
                        )
                    order_service = OrderService()
                    success = order_service.refund_order(
                        order_id, refund_service_fees, False
                    )
                    if success is False:
                        break
                if success is True and ticket_socket_event_id is not None:
                    dashboard_service = DashboardService()
                    dashboard_service.rebuild_daily_order_data_for_event(
                        ticket_socket_event_id
                    )

        return success

    def send_list_to_band(self, event_id: int, is_sent: bool):
        """
        Mark that the VIP list has been sent to the band
        """
        updated_event: VipEvent = None
        num_vips: int = 0
        if is_sent is True:
            event_sql = """SELECT COUNT(TicketSocketOrderTickets.Id) AS NumVips
                            FROM TicketSocketOrderTickets
                            JOIN TicketSocketOrders 
                                ON TicketSocketOrders.Id =
                                    TicketSocketOrderTickets.TicketSocketOrderId         
                            JOIN TicketSocketEvents
                                ON TicketSocketEvents.Id = 
                                    TicketSocketOrders.TicketSocketEventId
                            JOIN ExternalEvents
                                ON ExternalEvents.TicketSocketEventId = 
                                    TicketSocketEvents.Id
                            WHERE ExternalEvents.EventId=%(event_id)s
                            AND TicketSocketOrders.IsDeleted <> 1
                            AND TicketSocketOrderTickets.IsActive = 1
                            AND TicketSocketOrderTickets.IsRefunded = 0
                            AND TicketSocketOrderTickets.IsChargedBack = 0
                            GROUP BY ExternalEvents.EventId"""
            event_data = {"event_id": event_id}
            row = db_query_one(event_sql, event_data)
            if row:
                num_vips = get_override_int_value_or_default(row["NumVips"])

        sql = """UPDATE ExternalEvents
                    SET ListSentToBand=%(listSent)s,
                    LastUpdate=CURRENT_TIMESTAMP,
                    ListSentNumVips=%(numVips)s, """

        data = {
            "numVips": num_vips,
            "event_id": event_id,
            "listSent": 1 if is_sent is True else 0,
        }

        if is_sent is True:
            sql += """ListSentTime=CURRENT_TIMESTAMP"""
        else:
            sql += """ListSentTime=NULL"""

        sql += """ WHERE EventId=%(event_id)s"""

        success = db_update(sql, data)
        if success:
            event_service = EventService()
            events = event_service.get_events_and_orders(
                event_id=event_id,
                ignore_flags=True,
                exclude_external=True,
                get_orders=True,
            )
            if events is not None and len(events) > 0:
                updated_event = events[0]
        return updated_event

    def update_event(self, event_to_update: VipEvent):
        """
        Update single event from admin
        """
        success: bool = True
        if event_to_update is None:
            return False

        ticket_socket_event_id: int = get_override_int_value_or_default(
            event_to_update.ticket_socket_event_id, default=None
        )
        if ticket_socket_event_id is not None and ticket_socket_event_id <= 0:
            ticket_socket_event_id = None

        existing_event: VipEvent = None
        if event_to_update.external_event_id > 0:
            event_service = EventService()
            existing_events = event_service.get_events_and_orders(
                get_orders=False,
                ignore_flags=True,
                event_id=event_to_update.external_event_id,
            )
            if len(existing_events) > 0:
                existing_event = existing_events[0]

        update_data = {
            "ticket_socket_event_id": ticket_socket_event_id,
            "title": get_override_string_value_or_default(event_to_update.title),
            "event_date": get_override_string_value_or_default(
                event_to_update.event_date
            ),
            "meet_and_greet_time": get_override_string_value_or_default(
                event_to_update.meet_and_greet_time
            ),
            "doors_open_time": get_override_string_value_or_default(
                event_to_update.doors_open
            ),
            "event_time": get_override_string_value_or_default(
                event_to_update.event_time
            ),
            "is_active": get_override_tinyint_value_or_default_from_bool(
                event_to_update.is_active
            ),
            "isDeleted": get_override_tinyint_value_or_default_from_bool(
                event_to_update.is_deleted
            ),
            "isAddedToBandsInTown": get_override_tinyint_value_or_default_from_bool(
                event_to_update.is_added_to_bands_in_town
            ),
            "isHidden": get_override_tinyint_value_or_default_from_bool(
                event_to_update.is_hidden
            ),
            "announceDate": get_override_string_value_or_default(
                event_to_update.announce_date
            ),
            "checkInLocation": get_override_string_value_or_default(
                event_to_update.check_in_location
            ),
            "checkInNotes": get_override_string_value_or_default(
                event_to_update.check_in_notes
            ),
            "emailSentToVips": get_override_tinyint_value_or_default_from_bool(
                event_to_update.email_sent_to_vips
            ),
            "textSentToVips": get_override_tinyint_value_or_default_from_bool(
                event_to_update.text_sent_to_vips
            ),
            "url": get_override_string_value_or_default(event_to_update.external_url),
            "external_event_venue_id": get_override_int_value_or_default(
                event_to_update.external_event_venue_id
            ),
            "disable_link_button": get_override_tinyint_value_or_default_from_bool(
                event_to_update.disable_link_button
            ),
            "disable_link_reason": get_override_string_value_or_default(
                event_to_update.disable_link_reason
            ),
            "external_vip_link": get_override_string_value_or_default(
                event_to_update.external_vip_link
            ),
            "disable_vip_link_button": get_override_tinyint_value_or_default_from_bool(
                event_to_update.disable_vip_link_button
            ),
            "disable_vip_link_reason": get_override_string_value_or_default(
                event_to_update.disable_vip_link_reason
            ),
            "thumbnail": get_override_string_value_or_default(
                event_to_update.external_thumbnail
            ),
            "excludeFromDashboard": get_override_tinyint_value_or_default_from_bool(
                event_to_update.exclude_from_dashboard
            ),
            "isCancelled": get_override_tinyint_value_or_default_from_bool(
                event_to_update.is_cancelled
            ),
        }

        if existing_event is not None:
            update_data["event_id"] = get_override_int_value_or_default(
                event_to_update.external_event_id
            )
            update_sql = """UPDATE ExternalEvents
                            SET TicketSocketEventId=%(ticket_socket_event_id)s, 
                                Title=%(title)s,
                                EventDate=%(event_date)s,
                                MeetAndGreetTime=%(meet_and_greet_time)s,
                                DoorsOpenTime=%(doors_open_time)s,
                                EventTime=%(event_time)s,
                                URL=%(url)s,
                                ExternalEventVenueId=%(external_event_venue_id)s,
                                DisableLinkButton=%(disable_link_button)s,
                                DisableLinkReason=%(disable_link_reason)s,
                                ExternalVipLink=%(external_vip_link)s,
                                DisableVipLinkButton=%(disable_vip_link_button)s,
                                DisableVipLinkReason=%(disable_vip_link_reason)s,
                                IsActive=%(is_active)s, 
                                IsDeleted=%(isDeleted)s, 
                                IsAddedToBandsInTown=%(isAddedToBandsInTown)s, 
                                IsHidden=%(isHidden)s, 
                                AnnounceDate=%(announceDate)s, 
                                CheckInLocation=%(checkInLocation)s,
                                CheckInNotes=%(checkInNotes)s,
                                EmailSentToVips=%(emailSentToVips)s,
                                TextSentToVips=%(textSentToVips)s,
                                Thumbnail=%(thumbnail)s,
                                ExcludeFromDashboard=%(excludeFromDashboard)s,
                                IsCancelled=%(isCancelled)s,
                                LastUpdate=CURRENT_TIMESTAMP
                            WHERE EventId=%(event_id)s"""

            success = db_update(update_sql, update_data)
        else:
            update_data["seller_id"] = get_override_int_value_or_default(
                event_to_update.seller_id
            )
            update_sql = """INSERT INTO ExternalEvents (SellerId, Title, EventDate,
                TicketSocketEventId, EventTime, MeetAndGreetTime, DoorsOpenTime, URL, 
                ExternalEventVenueId, DisableLinkButton, DisableLinkReason, ExternalVipLink, 
                DisableVipLinkButton, DisableVipLinkReason, IsActive, IsAddedToBandsInTown, 
                IsDeleted, IsHidden, AnnounceDate, CheckInLocation, CheckInNotes, 
                EmailSentToVips, TextSentToVips, Thumbnail, ExcludeFromDashboard, IsCancelled,
                Created, LastUpdate) VALUES
                (%(seller_id)s, %(title)s, %(event_date)s,%(ticket_socket_event_id)s,
                %(event_time)s, %(meet_and_greet_time)s,%(doors_open_time)s, %(url)s,
                %(external_event_venue_id)s, %(disable_link_button)s,
                %(disable_link_reason)s, %(external_vip_link)s, %(disable_vip_link_button)s,
                %(disable_vip_link_reason)s, %(is_active)s, %(isAddedToBandsInTown)s, %(isDeleted)s, 
                %(isHidden)s, %(announceDate)s, %(checkInLocation)s, %(checkInNotes)s,
                %(emailSentToVips)s, %(textSentToVips)s, %(thumbnail)s, %(excludeFromDashboard)s,
                %(isCancelled)s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""

            event_id = db_insert(update_sql, update_data)
            success = event_id > 0

        if (
            ticket_socket_event_id is not None
            and event_to_update.is_deleted is False
            and len(event_to_update.ticket_types) > 0
        ):

            ticket_types = sorted(
                event_to_update.ticket_types,
                key=lambda x: (
                    x.ticket_type_order,
                    x.ticket_type_id,
                    x.ticket_type_name,
                ),
            )

            order: int = 1
            for ticket_type in ticket_types:
                ticket_type_wql = """UPDATE TicketSocketTicketTypes
                                    SET IsActive=%(is_active)s,
                                    TicketTypeName=%(ticketTypeName)s,
                                    TicketTypeOrder=%(order)s,
                                    LastUpdate=CURRENT_TIMESTAMP 
                                    WHERE TicketSocketTicketTypeId=%(ticket_type_id)s 
                                    AND TicketSocketEventId=%(ticket_socket_event_id)s"""
                ticket_type_data = {
                    "ticket_type_id": get_override_int_value_or_default(
                        ticket_type.ticket_type_id
                    ),
                    "ticket_socket_event_id": ticket_socket_event_id,
                    "is_active": get_override_tinyint_value_or_default_from_bool(
                        ticket_type.is_active
                    ),
                    "ticketTypeName": get_override_string_value_or_default(
                        ticket_type.ticket_type_name
                    ),
                    "order": order,
                }
                success = db_update(ticket_type_wql, ticket_type_data)
                order += 1
                if success is False:
                    break

            if success is True:
                dashboard_service = DashboardService()
                dashboard_service.rebuild_daily_order_data_for_event(
                    ticket_socket_event_id
                )
        return success
