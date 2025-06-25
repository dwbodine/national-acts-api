"""
Report Service
"""

import os
from common.db import (
    db_query_all,
)
from common.models.national_acts import FileReport, VipEvent
from common.models.ticket_socket import TicketSocketVenue
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class ReportService:
    """
    Service to handle all report-related activity
    """

    def get_missing_venue_events(self):
        """
        Gets events with missing venue data
        """
        events: list[VipEvent] = []
        sql = """SELECT ExternalEvents.EventID,
                ExternalEvents.Title,
                ExternalEvents.EventDate,
                TicketSocketEvents.Venue,
                TicketSocketEvents.Address,
                TicketSocketEvents.City,
                TicketSocketEvents.State,
                TicketSocketEvents.Zip,
                TicketSocketEvents.Country
            FROM ExternalEvents
            JOIN TicketSocketEvents
                ON TicketSocketEvents.Id =
                    ExternalEvents.TicketSocketEventId
            WHERE ExternalEvents.ExternalEventVenueId IS NULL
            ORDER BY ExternalEvents.EventDate DESC"""

        rows = db_query_all(sql)
        for row in rows:
            event = VipEvent()
            event.external_event_id = get_override_int_value_or_default(row["EventID"])
            event.title = get_override_string_value_or_default(row["Title"])
            event.event_date = get_override_string_value_or_default(row["EventDate"])
            venue_name = get_override_string_value_or_default(row["Venue"])
            address = get_override_string_value_or_default(row["Address"])
            city = get_override_string_value_or_default(row["City"])
            state = get_override_string_value_or_default(row["State"])
            postal_code = get_override_string_value_or_default(row["Zip"])
            country_name = get_override_string_value_or_default(row["Country"])

            venue = TicketSocketVenue(
                venue_name, address, city, state, postal_code, country_name, ""
            )
            event.venue = venue
            events.append(event)

        return events

    def get_orphaned_and_missing_header_images(self):
        """
        Returns a list of orphaned header images for removal
        """
        www_path = os.getenv("WWW_PUBLIC_FOLDER")
        header_path = os.path.join(www_path, "common/headers")
        if os.name == "nt" and len(header_path) > 0:
            header_path = header_path.replace("/", "\\")

        existing_files: list[str] = []
        for filename in os.listdir(header_path):
            if os.path.isfile(os.path.join(header_path, filename)):
                existing_files.append(filename)

        sql = """SELECT DISTINCT Image
                    FROM Pages
                    WHERE COALESCE(Image, '') <> ''
                    ORDER BY Image"""
        rows = db_query_all(sql)
        database_images: list[str] = []
        for row in rows:
            image = get_override_string_value_or_default(row["Image"])
            if image is not None:
                database_images.append(image)

        orphaned_files: list[str] = []
        for file in existing_files:
            if file not in database_images:
                orphaned_files.append(file)

        missing_files: list[str] = []
        for file in database_images:
            if file not in existing_files:
                missing_files.append(file)

        report = FileReport(orphaned_files, missing_files)

        return report

    def get_orphaned_and_missing_thumbnail_images(self):
        """
        Returns a list of orphaned thumbnail images for removal
        """
        www_path = os.getenv("WWW_PUBLIC_FOLDER")
        thumb_path = os.path.join(www_path, "common/thumbnails")
        if os.name == "nt" and len(thumb_path) > 0:
            thumb_path = thumb_path.replace("/", "\\")
        existing_files: list[str] = []
        for filename in os.listdir(thumb_path):
            if os.path.isfile(os.path.join(thumb_path, filename)):
                existing_files.append(filename)

        sql = """SELECT DISTINCT Thumbnail
                    FROM Pages
                    WHERE COALESCE(Thumbnail, '') <> ''
                    ORDER BY Thumbnail"""
        rows = db_query_all(sql)
        database_images: list[str] = []
        for row in rows:
            image = get_override_string_value_or_default(row["Thumbnail"])
            if image is not None:
                database_images.append(image)

        orphaned_files: list[str] = []
        for file in existing_files:
            if file not in database_images:
                orphaned_files.append(file)

        missing_files: list[str] = []
        for file in database_images:
            if file not in existing_files:
                missing_files.append(file)

        report = FileReport(orphaned_files, missing_files)

        return report

    def get_orphaned_and_missing_preview_images(self):
        """
        Returns a list of orphaned preview images for removal
        """
        www_path = os.getenv("WWW_PUBLIC_FOLDER")
        preview_path = os.path.join(www_path, "common/preview")
        if os.name == "nt" and len(preview_path) > 0:
            preview_path = preview_path.replace("/", "\\")
        existing_files: list[str] = []
        for filename in os.listdir(preview_path):
            if os.path.isfile(os.path.join(preview_path, filename)):
                existing_files.append(filename)

        sql = """SELECT DISTINCT LinkPreviewImage
                    FROM Pages
                    WHERE COALESCE(LinkPreviewImage, '') <> ''
                    ORDER BY LinkPreviewImage"""
        rows = db_query_all(sql)
        database_images: list[str] = []
        for row in rows:
            image = get_override_string_value_or_default(row["LinkPreviewImage"])
            if image is not None:
                database_images.append(image)

        orphaned_files: list[str] = []
        for file in existing_files:
            if file not in database_images:
                orphaned_files.append(file)

        missing_files: list[str] = []
        for file in database_images:
            if file not in existing_files:
                missing_files.append(file)

        report = FileReport(orphaned_files, missing_files)

        return report

    def get_orphaned_and_missing_logo_images(self):
        """
        Returns a list of orphaned logo images for removal
        """
        www_path = os.getenv("WWW_PUBLIC_FOLDER")
        logo_path = os.path.join(www_path, "common/logos")
        if os.name == "nt" and len(logo_path) > 0:
            logo_path = logo_path.replace("/", "\\")
        existing_files: list[str] = []
        for filename in os.listdir(logo_path):
            if os.path.isfile(os.path.join(logo_path, filename)):
                existing_files.append(filename)

        sql = """SELECT DISTINCT LogoOnly
                        FROM Pages
                        WHERE COALESCE(LogoOnly, '') <> ''
                        ORDER BY LogoOnly"""
        rows = db_query_all(sql)
        database_images: list[str] = []
        for row in rows:
            image = get_override_string_value_or_default(row["LogoOnly"])
            if image is not None:
                database_images.append(image)

        orphaned_files: list[str] = []
        for file in existing_files:
            if file not in database_images:
                orphaned_files.append(file)

        missing_files: list[str] = []
        for file in database_images:
            if file not in existing_files:
                missing_files.append(file)

        report = FileReport(orphaned_files, missing_files)

        return report

    def get_orphaned_and_missing_banner_images(self):
        """
        Returns a list of orphaned banner images for removal
        """
        www_path = os.getenv("WWW_PUBLIC_FOLDER")
        banner_path = os.path.join(www_path, "common/homebanners")
        if os.name == "nt" and len(banner_path) > 0:
            banner_path = banner_path.replace("/", "\\")
        existing_files: list[str] = []
        for filename in os.listdir(banner_path):
            if os.path.isfile(os.path.join(banner_path, filename)):
                existing_files.append(filename)

        sql = """SELECT Value
                        FROM Settings
                        WHERE Name = 'HomeBanner'"""
        rows = db_query_all(sql)
        database_images: list[str] = []
        for row in rows:
            image = get_override_string_value_or_default(row["Value"])
            if image is not None:
                database_images.append(image)

        orphaned_files: list[str] = []
        for file in existing_files:
            if file not in database_images:
                orphaned_files.append(file)

        missing_files: list[str] = []
        for file in database_images:
            if file not in existing_files:
                missing_files.append(file)

        report = FileReport(orphaned_files, missing_files)

        return report
