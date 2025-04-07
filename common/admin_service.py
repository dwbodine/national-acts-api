"""
Admin service module
"""

from common.db import db_delete, db_query_all, db_insert, db_update
from common.models.admin import ExternalVenue, SiteSetting, SiteSettingType
from common.models.ticket_socket import TicketSocketAccount
from common.ticket_socket_service import TicketSocketService
from common.utility import move_temp_file_to_public_folder


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
            setting.setting_id = int(row["ID"])
            setting.name = str(row["Name"])
            setting.display_name = str(row["DisplayName"])
            setting.type = str(row["Type"])
            setting.value = str(row["Value"])
            setting.file_path = str(row["FilePath"])
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
            "name": setting.name,
            "displayName": setting.display_name,
            "type": setting.type,
            "value": setting.value,
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
            data["setting_id"] = setting.setting_id
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
            ticket_socket_id = int(row["TicketSocketId"])
            service = TicketSocketService(ticket_socket_id)
            account = TicketSocketAccount()
            account.ticket_socket_id = ticket_socket_id
            account.name = service.name
            account.currency_symbol = service.currency_symbol
            account.exchange_rate_id = service.exchange_rate_id
            account.exchange_rate_slug = service.exchange_rate_slug
            account.mulitiplier = service.mulitiplier
            account.service_url = service.service_url
            account.utc_offset_hours = service.utc_offset_hours
            account.categories = service.get_categories()
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
            venue.venue_id = int(row["VenueID"])
            venue.venue = str(row["Venue"])
            venue.address = str(row["Address"])
            venue.city = str(row["City"])
            venue.state = str(row["State"]) if row["State"] is not None else None
            venue.zip_code = str(row["Zip"]) if row["Zip"] is not None else None
            venue.country = str(row["Country"]) if row["Country"] is not None else None
            venue.has_events = True if row["HasEvents"] is not None else False
            venues.append(venue)

        return venues

    def update_external_venue(self, venue: ExternalVenue):
        """
        Add a venue to the database
        """

        success = False
        sql = ""
        data = {
            "venue": venue.venue,
            "address": venue.address,
            "city": venue.city,
            "state": venue.state if venue.state is not None else None,
            "zip": venue.zip_code if venue.zip_code is not None else None,
            "country": venue.country if venue.country is not None else None,
        }

        if venue.venue_id is None or venue.venue_id == 0:
            sql = """INSERT INTO ExternalEventVenues (Venue, Address, City, State, Zip, Country)
                        VALUES(%(venue)s, %(address)s, %(city)s, %(state)s, %(zip)s, %(country)s)"""
            venue_id = db_insert(sql, data)
            success = venue_id > 0
            venue.venue_id = venue_id
        else:
            data["venue_id"] = venue.venue_id
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
