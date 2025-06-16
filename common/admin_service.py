"""
Admin service module
"""

from common.db import db_delete, db_query_all, db_insert, db_update
from common.models.admin import ExternalVenue, SiteSetting, SiteSettingType
from common.models.ticket_socket import Country, TicketSocketAccount
from common.ticket_socket_service import TicketSocketService
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    move_temp_file_to_public_folder,
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
        if setting.setting_id is None or setting.setting_id <= 0:
            sql = """INSERT INTO Settings (Name, DisplayName, Type, Value)
                     VALUES(%(name)s, %(displayName)s, %(type)s, %(value)s)"""
            setting_id = db_insert(sql, data)
            success = setting_id > 0
        else:
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

    def get_external_venues(self):
        """
        Fetch all external venues from database
        """
        venues: list[ExternalVenue] = []
        sql = """SELECT ExternalEventVenues.*,
            (SELECT 1 FROM ExternalEvents
                WHERE ExternalEvents.ExternalEventVenueId = 
                ExternalEventVenues.VenueID Limit 0, 1) as HasEvents
            FROM ExternalEventVenues ORDER BY Venue ASC"""
        rows = db_query_all(sql)
        for row in rows:
            venue = ExternalVenue()
            venue.venue_id = get_override_int_value_or_default(row["VenueID"])
            venue.venue = get_override_string_value_or_default(row["Venue"])
            venue.address = get_override_string_value_or_default(row["Address"])
            venue.city = get_override_string_value_or_default(row["City"])
            venue.state = get_override_string_value_or_default(row["State"])
            venue.zip_code = get_override_string_value_or_default(row["Zip"])
            venue.country = get_override_string_value_or_default(row["Country"])
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
            "country": get_override_string_value_or_default(venue.country),
        }

        if venue.venue_id is None or venue.venue_id == 0:
            sql = """INSERT INTO ExternalEventVenues (Venue, Address, City, State, Zip, Country)
                        VALUES(%(venue)s, %(address)s, %(city)s, %(state)s, %(zip)s, %(country)s)"""
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
                        Country=%(country)s
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

    def get_all_countries(self):
        """
        Gets stored data for countries
        """
        countries: list[Country] = []
        sql = """SELECT * FROM Country ORDER BY CountryName ASC"""
        rows = db_query_all(sql)
        for row in rows:
            country_id = get_override_int_value_or_default(row["CountryId"])
            country_name = get_override_string_value_or_default(row["CountryName"])
            country_code = get_override_string_value_or_default(row["CountryCode"])
            country = Country(country_id, country_name, country_code)
            if country.country_code is None:
                continue
            countries.append(country)
        return countries
