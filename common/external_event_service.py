"""
External Event Service
"""

from common.db import (
    db_delete,
    db_query_all,
    db_query_one,
    db_insert,
    db_update,
)
from common.models.national_acts import VipEvent
from common.models.ticket_socket import TicketSocketVenue
from common.utility import (
    create_thumbnail,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    move_temp_file_to_public_folder,
)


class ExternalEventService:
    """
    Service to handle all non-TicketSocket event-related activity
    """

    def get_external_event_by_id(self, external_event_id: int):
        """
        Fetches a single external event by Id
        """
        vip_event: VipEvent = None
        external_sql = """
            SELECT ExternalEvents.*, Sellers.Name as SellerName, ExternalEventVenues.*
                FROM ExternalEvents 
                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                LEFT JOIN ExternalEventVenues ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
                WHERE ExternalEvents.EventId=%(externalEventId)s"""
        external_data = {"externalEventId": external_event_id}

        row = db_query_one(external_sql, external_data)
        vip_event = self.build_external_event_from_dict(row)

        return vip_event

    def get_external_events_by_seller(self, seller_id: int):
        """
        Fetches all current external events
        """
        vip_events: list[VipEvent] = []
        external_sql = """
            SELECT ExternalEvents.*, Sellers.Name as SellerName, ExternalEventVenues.*
                FROM ExternalEvents 
                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                LEFT JOIN ExternalEventVenues 
                    ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
                WHERE Sellers.SellerId=%(sellerId)s AND 
                    ExternalEvents.EventDate >= CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')"""
        external_data = {"sellerId": seller_id}

        rows = db_query_all(external_sql, external_data)
        for row in rows:
            vip_event = self.build_external_event_from_dict(row)
            if vip_event is not None:
                vip_events.append(vip_event)

        return vip_events

    def update_external_event(self, event_to_update: VipEvent):
        """
        Add/update single external event
        """
        success: bool = True
        if event_to_update is None or event_to_update.is_external is not True:
            return False

        update_data = {
            "is_active": (
                1
                if event_to_update.is_active is True
                and event_to_update.is_deleted is False
                else 0
            ),
            "title": event_to_update.title,
            "is_cancelled": 1 if event_to_update.is_cancelled is True else 0,
            "isAddedToBandsInTown": (
                1 if event_to_update.is_added_to_bands_in_town is True else 0
            ),
            "isHidden": 1 if event_to_update.is_hidden is True else 0,
            "announceDate": (
                event_to_update.announce_date
                if event_to_update.announce_date is not None
                else None
            ),
            "event_date": event_to_update.event_date,
            "url": event_to_update.external_url,
            "external_event_venue_id": event_to_update.external_event_venue_id,
            "disable_link_button": (
                1 if event_to_update.disable_link_button is True else 0
            ),
            "disable_link_reason": (
                event_to_update.disable_link_reason
                if event_to_update.disable_link_reason is not None
                else None
            ),
            "external_vip_link": (
                event_to_update.external_vip_link
                if event_to_update.external_vip_link is not None
                else None
            ),
            "disable_vip_link_button": (
                1 if event_to_update.disable_vip_link_button is True else 0
            ),
            "disable_vip_link_reason": (
                event_to_update.disable_vip_link_reason
                if event_to_update.disable_vip_link_reason is not None
                else None
            ),
            "event_time": (
                event_to_update.event_time
                if event_to_update.event_time is not None
                else None
            ),
            "meet_and_greet_time": (
                event_to_update.meet_and_greet_time
                if event_to_update.meet_and_greet_time is not None
                else None
            ),
            "doors_open_time": (
                event_to_update.doors_open
                if event_to_update.doors_open is not None
                else None
            ),
            "ticket_socket_event_id": (
                event_to_update.ticket_socket_event_id
                if event_to_update.ticket_socket_event_id is not None
                and event_to_update.ticket_socket_event_id > 0
                else None
            ),
        }

        if event_to_update.thumbnail is not None:
            thumb_file = create_thumbnail(event_to_update.thumbnail)
            if thumb_file is not None:
                update_data["thumbnail"] = thumb_file
                move_temp_file_to_public_folder(thumb_file, "common/thumbnails")

        if event_to_update.event_id > 0:
            update_data["event_id"] = event_to_update.external_event_id
            update_sql = """UPDATE ExternalEvents
                             SET IsActive=%(is_active)s, 
                             TicketSocketEventId=%(ticket_socket_event_id)s,
                             Title=%(title)s,
                             EventDate=%(event_date)s,
                             EventTime=%(event_time)s,
                             MeetAndGreetTime=%(meet_and_greet_time)s,
                             DoorsOpenTime=%(doors_open_time)s,
                             URL=%(url)s,
                             ExternalEventVenueId=%(external_event_venue_id)s,
                             DisableLinkButton=%(disable_link_button)s,
                             DisableLinkReason=%(disable_link_reason)s,
                             ExternalVipLink=%(external_vip_link)s,
                             DisableVipLinkButton=%(disable_vip_link_button)s,
                             DisableVipLinkReason=%(disable_vip_link_reason)s,
                             IsAddedToBandsInTown=%(isAddedToBandsInTown)s, 
                             IsHidden=%(isHidden)s, 
                             AnnounceDate=%(announceDate)s, 
                             IsCancelled=%(is_cancelled)s, """

            if "thumbnail" in update_data:
                update_sql += """Thumbnail=%(thumbnail)s, """

            update_sql += """LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                WHERE EventId=%(event_id)s"""

            success = db_update(update_sql, update_data)
        else:
            update_data["seller_id"] = event_to_update.seller_id
            update_sql = """INSERT INTO ExternalEvents (SellerId, Title, EventDate,
                TicketSocketEventId, EventTime, MeetAndGreetTime, DoorsOpenTime, URL, 
                ExternalEventVenueId, DisableLinkButton, DisableLinkReason, ExternalVipLink, 
                DisableVipLinkButton, DisableVipLinkReason, IsActive, IsAddedToBandsInTown, 
                IsHidden, IsCancelled, AnnounceDate, Created, LastUpdate"""

            if "thumbnail" in update_data:
                update_sql += """, Thumbnail"""

            update_sql += """) VALUES (%(seller_id)s, %(title)s, %(event_date)s,
                %(ticket_socket_event_id)s, %(event_time)s, %(meet_and_greet_time)s,
                %(doors_open_time)s, %(url)s, %(external_event_venue_id)s, %(disable_link_button)s,
                %(disable_link_reason)s, %(external_vip_link)s, %(disable_vip_link_button)s,
                %(disable_vip_link_reason)s, %(is_active)s, %(isAddedToBandsInTown)s, %(isHidden)s,
                %(is_cancelled)s, %(announceDate)s, 
                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), 
                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')"""

            if "thumbnail" in update_data:
                update_sql += """, %(thumbnail)s"""

            update_sql += """)"""

            event_id = db_insert(update_sql, update_data)
            success = event_id > 0

        return success

    def disable_external_events(self, event_ids: list[int], disabled: bool):
        """
        Marks eventIds as disabled
        """
        success: bool = True
        for event_id in event_ids:
            sql = """UPDATE ExternalEvents
                        SET IsActive=%(is_active)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                    WHERE EventId=%(event_id)s"""
            data = {
                "event_id": event_id,
                "is_active": 0 if disabled is True else 1,
            }
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def delete_external_events(self, event_ids: list[int]):
        """
        Marks eventIds as deleted
        """
        success: bool = True
        for event_id in event_ids:
            sql = """DELETE FROM ExternalEvents WHERE EventId=%(event_id)s"""
            data = {"event_id": event_id}
            success = db_delete(sql, data)
            if success is False:
                break
        return success

    def hide_external_events(self, event_ids: list[int], hidden: bool):
        """
        Marks events as hidden
        """
        success: bool = True
        for event_id in event_ids:
            sql = """UPDATE ExternalEvents
                        SET IsHidden=%(isHidden)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE EventId=%(event_id)s"""
            data = {
                "event_id": event_id,
                "isHidden": 1 if hidden is True else 0,
            }
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def cancel_external_events(self, event_ids: list[int], hidden: bool):
        """
        Marks events as cancelled
        """
        success: bool = True
        for event_id in event_ids:
            sql = """UPDATE ExternalEvents
                        SET IsCancelled=%(isCancelled)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE EventId=%(event_id)s"""
            data = {
                "event_id": event_id,
                "isCancelled": 1 if hidden is True else 0,
            }
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def build_external_event_from_dict(self, row: dict):
        """
        internal method to build out external vip event
        """
        vip_event: VipEvent = None
        if row:
            event_id = get_override_int_value_or_default(row["EventId"])
            vip_event = VipEvent()
            vip_event.is_external = True
            vip_event.external_event_id = event_id
            vip_event.event_id = event_id
            ticket_socket_event_id = get_override_int_value_or_default(row["EventId"])
            vip_event.ticket_socket_event_id = (
                ticket_socket_event_id if ticket_socket_event_id > 0 else None
            )
            vip_event.event_time = get_override_string_value_or_default(
                row["EventTime"]
            )
            vip_event.doors_open = get_override_string_value_or_default(
                row["DoorsOpenTime"]
            )
            vip_event.meet_and_greet_time = get_override_string_value_or_default(
                row["MeetAndGreetTime"]
            )
            vip_event.title = get_override_string_value_or_default(row["Title"])
            vip_event.seller_name = get_override_string_value_or_default(
                row["SellerName"]
            )
            vip_event.seller_id = get_override_int_value_or_default(row["SellerId"])
            vip_event.event_date = get_override_string_value_or_default(
                row["EventDate"]
            )
            vip_event.announce_date = get_override_string_value_or_default(
                row["AnnounceDate"]
            )
            vip_event.thumbnail = get_override_string_value_or_default(row["Thumbnail"])
            vip_event.external_url = get_override_string_value_or_default(row["URL"])
            vip_event.external_event_venue_id = get_override_int_value_or_default(
                row["ExternalEventVenueId"]
            )

            if vip_event.event_time is None:
                vip_event.event_time = ""
            if vip_event.meet_and_greet_time is None:
                vip_event.meet_and_greet_time = ""

            venue = TicketSocketVenue(
                get_override_string_value_or_default(row["Venue"]),
                get_override_string_value_or_default(row["Address"]),
                get_override_string_value_or_default(row["City"]),
                get_override_string_value_or_default(row["State"]),
                get_override_string_value_or_default(row["Zip"]),
                get_override_string_value_or_default(row["Country"]),
                "",
            )
            vip_event.venue = venue

            vip_event.is_active = get_override_bool_value_or_default(row["IsActive"])

            vip_event.disable_link_button = get_override_bool_value_or_default(
                row["DisableLinkButton"]
            )
            vip_event.disable_link_reason = get_override_string_value_or_default(
                row["DisableLinkReason"]
            )
            vip_event.external_vip_link = get_override_string_value_or_default(
                row["ExternalVipLink"]
            )

            vip_event.disable_vip_link_button = get_override_bool_value_or_default(
                row["DisableVipLinkButton"]
            )
            vip_event.disable_vip_link_reason = get_override_string_value_or_default(
                row["DisableVipLinkReason"]
            )
            vip_event.is_vip = (
                True if vip_event.external_vip_link is not None else False
            )

            vip_event.is_added_to_bands_in_town = get_override_bool_value_or_default(
                row["IsAddedToBandsInTown"]
            )

            vip_event.is_hidden = get_override_bool_value_or_default(row["IsHidden"])
            vip_event.is_cancelled = get_override_bool_value_or_default(
                row["IsCancelled"]
            )
            vip_event.cancelled_date = get_override_string_value_or_default(
                row["CancelledDate"]
            )
            vip_event.is_deleted = get_override_bool_value_or_default(row["IsDeleted"])
            vip_event.email_sent_to_vips = get_override_bool_value_or_default(
                row["EmailSentToVips"]
            )
            vip_event.text_sent_to_vips = get_override_bool_value_or_default(
                row["TextSentToVips"]
            )
            vip_event.list_sent_to_band = get_override_bool_value_or_default(
                row["ListSentToBand"]
            )
            vip_event.list_sent_time = get_override_string_value_or_default(
                row["ListSentTime"]
            )
            vip_event.list_sent_num_vips = get_override_int_value_or_default(
                row["ListSentNumVips"]
            )
            vip_event.check_in_location = get_override_string_value_or_default(
                row["CheckInLocation"]
            )
            vip_event.check_in_notes = get_override_string_value_or_default(
                row["CheckInNotes"]
            )

            vip_event.get_totals()

        return vip_event
