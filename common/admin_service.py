"""
Admin service module
"""

import os
from common.db import db_delete, db_query_all, db_insert, db_query_one, db_update
from common.models.admin import ExternalVenue, SiteSetting, SiteSettingType
from common.models.national_acts import TicketSocketRefreshHistory
from common.models.ticket_socket import Country, TicketSocketAccount, Timezone
from common.ticket_socket_service import TicketSocketService
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_timezones_from_country_code,
    move_temp_file_to_public_folder,
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
                        LastUpdated=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE ID=%(setting_id)s"""
            data["setting_id"] = get_override_int_value_or_default(setting.setting_id)
            success = db_update(sql, data)

        # move temp image to final place
        if setting.type == SiteSettingType.IMAGE:
            move_temp_file_to_public_folder(setting.value, setting.file_path)
            if orig_value is not None:
                remove_file(orig_value, setting.file_path)

        return success

    def get_ticket_socket_accounts(self):
        """
        Fetch current ticket socket account data
        """
        accounts: list[TicketSocketAccount] = []
        sql = "SELECT TicketSocketId FROM TicketSocket"
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
            account.mulitiplier = get_override_float_value_or_default(
                service.mulitiplier
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
            sql += (
                """WHERE CONCAT_WS (' ', COALESCE(Country.CountryName, ''),
                    COALESCE(ExternalEventVenues.Venue, ''),
                    COALESCE(ExternalEventVenues.Address, ''),
                    COALESCE(ExternalEventVenues.City, ''),
                    COALESCE(ExternalEventVenues.State, ''))
                    LIKE ('%"""
                + search_term
                + """%') """
            )
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
        data = {
            "venue": get_override_string_value_or_default(venue.venue),
            "address": get_override_string_value_or_default(venue.address),
            "city": get_override_string_value_or_default(venue.city),
            "state": get_override_string_value_or_default(venue.state),
            "zip": get_override_string_value_or_default(venue.zip_code),
            "country_id": get_override_string_value_or_default(
                venue.country.country_id, int(os.getenv("DEFAULT_COUNTRY_ID"))
            ),
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
