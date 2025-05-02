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
    get_override_tinyint_value_or_default_from_bool,
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
            ticket_socket_event_id = get_override_int_value_or_default(
                row["TicketSocketEventId"]
            )
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
