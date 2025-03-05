"""
External Event Service
"""

from common.db import (
    db_query_all,
    db_query_one,
    db_insert,
    db_update,
)
from common.models.national_acts import VipEvent
from common.models.ticket_socket import TicketSocketVenue


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
            "title": event_to_update.external_title,
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
            "thumbnail": (
                event_to_update.external_thumbnail
                if event_to_update.external_thumbnail is not None
                else None
            ),
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
        }

        if event_to_update.event_id > 0:
            update_data["event_id"] = event_to_update.external_event_id
            update_sql = """UPDATE ExternalEvents
                             SET IsActive=%(is_active)s, 
                             Title=%(title)s,
                             EventDate=%(event_date)s,
                             Thumbnail=%(thumbnail)s,
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
                             IsCancelled=%(is_cancelled)s,
                             LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                             WHERE EventId=%(event_id)s"""

            success = db_update(update_sql, update_data)
        else:
            update_data["seller_id"] = event_to_update.external_seller_id
            update_sql = """INSERT INTO ExternalEvents (SellerId, Title, EventDate,
                Thumbnail, URL, ExternalEventVenueId, DisableLinkButton, DisableLinkReason,
                ExternalVipLink, DisableVipLinkButton, DisableVipLinkReason, Created, 
                LastUpdate, IsActive, IsAddedToBandsInTown, IsHidden, IsCancelled, 
                AnnounceDate) VALUES (%(seller_id)s, %(title)s, %(event_date)s, 
                %(thumbnail)s, %(url)s, %(external_event_venue_id)s, %(disable_link_button)s, 
                %(disable_link_reason)s, %(external_vip_link)s, %(disable_vip_link_button)s,
                %(disable_vip_link_reason)s, CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), 
                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), %(is_active)s, 
                %(isAddedToBandsInTown)s, %(isHidden)s, %(is_cancelled)s, %(announceDate)s)"""

            event_id = db_insert(update_sql, update_data)
            success = event_id > 0
        return success

    def build_external_event_from_dict(self, row: dict):
        """
        internal method to build out external vip event
        """
        vip_event: VipEvent = None
        if row:
            event_id = int(row["EventId"]) if row["EventId"] is not None else 0
            vip_event = VipEvent()
            vip_event.event_id = event_id
            vip_event.title = str(row["Title"])
            vip_event.seller_name = str(row["SellerName"])
            vip_event.is_external = True
            vip_event.event_date = str(row["EventDate"])
            vip_event.announce_date = str(row["AnnounceDate"])
            vip_event.thumbnail = str(row["Thumbnail"])
            vip_event.external_url = str(row["URL"])
            vip_event.external_event_venue_id = int(row["ExternalEventVenueId"])
            venue = TicketSocketVenue(
                str(row["Venue"]),
                str(row["Address"]),
                str(row["City"]),
                str(row["State"]),
                str(row["Zip"]),
                str(row["Country"]),
                "",
            )
            vip_event.venue = venue
            vip_event.is_active = True if int(row["IsActive"]) == 1 else False
            vip_event.external_event_id = (
                int(row["EventId"]) if row["EventId"] is not None else 0
            )
            vip_event.external_seller_id = int(row["SellerId"])
            vip_event.disable_link_button = str(row["DisableLinkButton"])
            vip_event.disable_link_reason = str(row["DisableLinkReason"])
            vip_event.external_vip_link = str(row["ExternalVipLink"])
            vip_event.is_vip = (
                True
                if (
                    vip_event.external_vip_link is not None
                    and vip_event.external_vip_link != ""
                )
                else False
            )
            vip_event.disable_vip_link_button = str(row["DisableVipLinkButton"])
            vip_event.disable_vip_link_reason = str(row["DisableVipLinkReason"])
            vip_event.is_added_to_bands_in_town = (
                True if int(row["IsAddedToBandsInTown"]) == 1 else False
            )
            vip_event.is_hidden = True if int(row["IsHidden"]) == 1 else False
            vip_event.is_cancelled = True if int(row["IsCancelled"]) == 1 else False
            vip_event.cancelled_date = (
                str(row["CancelledDate"])
                if (vip_event.is_cancelled is True and row["CancelledDate"] is not None)
                else None
            )
            vip_event.get_totals()

        return vip_event
