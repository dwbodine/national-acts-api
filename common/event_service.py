"""
Event Service
"""

from datetime import datetime
import operator

from common.db import (
    db_query_all,
    db_query_one,
    db_insert,
    db_update,
    db_convert_list_to_parameters,
)
from common.models.national_acts import VipEvent, Seller, EventNote
from common.models.ticket_socket import TicketSocketVenue, TicketSocketTicketType
from common.order_service import OrderService
from common.daily_order_service import DailyOrderService


class EventService:
    """
    Service to handle all event-related activity
    """

    def get_events_and_orders(
        self,
        get_orders: bool = False,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        show_inactive: bool = False,
        search_term: str = None,
        ts_event_id: int = None,
        show_deleted: bool = False,
        exclude_start: int = None,
        exclude_end: int = None,
        exclude_external: bool = False,
        show_hidden: bool = False,
        ignore_flags: bool = False,
        show_cancelled: bool = False,
    ):
        """
        main method to fetch events and orders
        """
        events: list[VipEvent] = []

        seller_event_category_ids: list[int] = []
        if seller_id is not None:
            seller = Seller(seller_id)
            seller_event_category_ids = seller.get_seller_event_category_ids()
            # prevent against returning every event in the database
            if len(seller_event_category_ids) == 0:
                return []

        if get_orders is False and search_term is not None:
            search_term = search_term.replace("'", "''")
            search_term = search_term.replace('"', "")
            search_term = search_term.replace("=", "")
        else:
            search_term = None

        sql = """SELECT TicketSocketEvents.*,
                    ExternalEvents.EventId AS ExternalEventId, 
                    ExternalEvents.SellerId AS ExternalSellerId, 
                    ExternalEvents.Title AS ExternalTitle, 
                    ExternalEvents.Thumbnail AS ExternalThumbnail, 
                    ExternalEvents.URL AS ExternalUrl, 
                    ExternalEvents.Venue AS ExternalVenue, 
                    ExternalEvents.Address AS ExternalAddress, 
                    ExternalEvents.City AS ExternalCity, 
                    ExternalEvents.State AS ExternalState, 
                    ExternalEvents.Zip AS ExternalZip, 
                    ExternalEvents.Country AS ExternalCountry, 
                    ExternalEvents.DisableLinkButton, 
                    ExternalEvents.DisableLinkReason, 
                    ExternalEvents.ExternalVipLink, 
                    ExternalEvents.DisableVipLinkButton, 
                    ExternalEvents.DisableVipLinkReason,
                    Sellers.Name AS SellerName
                 FROM TicketSocketEvents 
                 JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId 
                 JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId
            LEFT JOIN ExternalEvents ON ExternalEvents.SellerId = Sellers.SellerId 
                AND TicketSocketEvents.EventDate = ExternalEvents.EventDate """

        if ts_event_id is None:
            if show_inactive is True:
                sql += " AND ExternalEvents.IsActive = 0"
            elif ignore_flags is not True:
                sql += " AND ExternalEvents.IsActive = 1"

        sql += " WHERE "
        data = {}

        where_clause: list[str] = []
        if ts_event_id is not None:
            where_clause.append("TicketSocketEvents.Id = %(event_id)s")
            data["event_id"] = ts_event_id
        else:
            if ignore_flags is not True:
                if show_deleted is not True:
                    where_clause.append("TicketSocketEvents.IsDeleted = 0")
                else:
                    show_inactive = True

                if show_inactive is True:
                    where_clause.append("TicketSocketEvents.IsActive = 0")
                else:
                    where_clause.append("TicketSocketEvents.IsActive = 1")

                if show_hidden is not True:
                    where_clause.append("TicketSocketEvents.IsHidden = 0")

                if show_cancelled is not True:
                    where_clause.append("TicketSocketEvents.IsCancelled = 0")
            if search_term is not None and len(search_term) > 0:
                where_clause.append(
                    """MATCH (TicketSocketEvents.Title, 
                                TicketSocketEvents.Venue, 
                                TicketSocketEvents.Address, 
                                TicketSocketEvents.City, 
                                TicketSocketEvents.State,
                                TicketSocketEvents.Country) 
                                AGAINST (%(search_term)s IN BOOLEAN MODE)"""
                )
                data["search_term"] = "*" + search_term + "*"
            if len(seller_event_category_ids) > 0:
                seller_event_category_id_str = db_convert_list_to_parameters(
                    seller_event_category_ids, data, "sellerEventCategoryId"
                )
                where_clause.append(
                    "TicketSocketEvents.SellerEventCategoryId IN "
                    + seller_event_category_id_str
                )

            if start is not None and end is not None:
                where_clause.append(
                    "TicketSocketEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif end is not None:
                where_clause.append(
                    "TicketSocketEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                data["startDate"] = datetime.now().strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif start is not None:
                where_clause.append("TicketSocketEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            elif get_orders is False or seller_id is None:
                where_clause.append("TicketSocketEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.now().strftime("%Y-%m-%d")
            if ignore_flags is not True:
                where_clause.append(
                    """COALESCE(TicketSocketEvents.AnnounceDate,
                                     CURRENT_TIMESTAMP) <= CURRENT_TIMESTAMP"""
                )

            if exclude_start is not None and exclude_end is not None:
                where_clause.append(
                    "TicketSocketEvents.EventDate NOT BETWEEN %(exclude_start)s AND %(exclude_end)s"
                )
                data["exclude_start"] = datetime.fromtimestamp(exclude_start).strftime(
                    "%Y-%m-%d"
                )
                data["exclude_end"] = datetime.fromtimestamp(exclude_end).strftime(
                    "%Y-%m-%d"
                )

        if len(where_clause) > 0:
            sql += " AND ".join(where_clause)

        sql += (
            " ORDER BY TicketSocketEvents.EventDate ASC, TicketSocketEvents.Title ASC"
        )

        sql = sql.replace("\n", "")

        event_rows = db_query_all(sql, data)
        for row in event_rows:
            event_id = int(row["EventId"])
            ticket_socket_event_id = int(row["Id"])
            vip_event = VipEvent()
            vip_event.event_id = event_id
            vip_event.title = str(row["Title"])
            vip_event.seller_name = str(row["SellerName"])
            vip_event.is_external = False
            vip_event.ticket_socket_event_id = ticket_socket_event_id
            vip_event.seller_event_category_id = int(row["SellerEventCategoryId"])
            vip_event.event_date = str(row["EventDate"])
            vip_event.announce_date = str(row["AnnounceDate"])
            vip_event.utc_time = int(row["UtcTime"])
            vip_event.display_date = (
                str(row["DisplayDate"]) if row["DisplayDate"] is not None else None
            )
            vip_event.thumbnail = (
                str(row["Thumbnail"]) if row["Thumbnail"] is not None else None
            )
            vip_event.ticket_socket_url = str(row["URL"])
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
            venue_name = str(row["Venue"]) if row["Venue"] is not None else None
            if row["ExternalVenue"] is not None:
                venue_name = str(row["ExternalVenue"])
            address = str(row["Address"]) if row["Address"] is not None else None
            if row["ExternalAddress"] is not None:
                address = str(row["ExternalAddress"])
            city = str(row["City"]) if row["City"] is not None else None
            if row["ExternalCity"] is not None:
                city = str(row["ExternalCity"])
            state = str(row["State"]) if row["State"] is not None else None
            if row["ExternalState"] is not None:
                state = str(row["ExternalState"])
            zip_code = str(row["Zip"]) if row["Zip"] is not None else None
            if row["ExternalZip"] is not None:
                zip_code = str(row["ExternalZip"])
            vip_country = str(row["Country"]) if row["Country"] is not None else None
            if row["ExternalCountry"] is not None:
                vip_country = str(row["ExternalCountry"])

            venue = TicketSocketVenue(
                venue_name, address, "", city, state, zip_code, vip_country, ""
            )
            vip_event.venue = venue
            vip_event.is_active = True if int(row["IsActive"]) == 1 else False
            vip_event.is_deleted = True if int(row["IsDeleted"]) == 1 else False
            if vip_event.is_deleted is True:
                vip_event.is_active = False
            vip_event.is_vip = True if int(row["IsVip"]) == 1 else False
            if (
                row["ExternalEventId"] is not None
                and row["ExternalEventId"] != ""
                and exclude_external is not True
            ):
                vip_event.external_event_id = int(row["ExternalEventId"])
                vip_event.external_seller_id = int(row["ExternalSellerId"])
                vip_event.external_title = str(row["ExternalTitle"])
                vip_event.external_thumbnail = str(row["ExternalThumbnail"])
                vip_event.external_url = str(row["ExternalUrl"])
                external_country = (
                    str(row["ExternalCountry"])
                    if row["ExternalCountry"] is not None
                    else None
                )
                external_venue = TicketSocketVenue(
                    str(row["ExternalVenue"]),
                    str(row["ExternalAddress"]),
                    "",
                    str(row["ExternalCity"]),
                    str(row["ExternalState"]),
                    str(row["ExternalZip"]),
                    external_country,
                    "",
                )
                vip_event.external_venue = external_venue
                vip_event.disable_link_button = str(row["DisableLinkButton"])
                vip_event.disable_link_reason = str(row["DisableLinkReason"])
                vip_event.external_vip_link = str(row["ExternalVipLink"])
                vip_event.disable_vip_link_button = str(row["DisableVipLinkButton"])
                vip_event.disable_vip_link_reason = str(row["DisableVipLinkReason"])

            if get_orders is True:
                order_service = OrderService()
                ticket_types = self.__get_ticket_types_from_event_id(
                    ticket_socket_event_id
                )
                vip_event.ticket_types = ticket_types

                notes = self.__get_event_notes(ticket_socket_event_id)
                vip_event.notes = notes

                orders = order_service.get_orders_from_event_id(
                    ticket_socket_event_id,
                    show_inactive,
                    show_deleted,
                    ignore_flags,
                )
                vip_event.orders = orders

            vip_event.get_totals()

            events.append(vip_event)

        # if not excluded, get external events without matching TicketSocketEvents
        if exclude_external is not True:
            external_sql = """SELECT ExternalEvents.*, Sellers.Name as SellerName
                                FROM ExternalEvents 
                                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                                WHERE """
            external_data = {}

            externalwhere_clause: list[str] = []
            if show_inactive is True:
                externalwhere_clause.append("ExternalEvents.IsActive = 0")
            elif ignore_flags is not True:
                externalwhere_clause.append("ExternalEvents.IsActive = 1")

            if show_hidden is not True and ignore_flags is not True:
                externalwhere_clause.append("ExternalEvents.IsHidden = 0")

            if show_cancelled is not True and ignore_flags is not True:
                externalwhere_clause.append("ExternalEvents.IsCancelled = 0")

            if search_term is not None and len(search_term) > 0:
                externalwhere_clause.append(
                    """MATCH (ExternalEvents.Title, ExternalEvents.Venue,
                              ExternalEvents.Address, ExternalEvents.City,
                              ExternalEvents.State, ExternalEvents.Country)
                              AGAINST (%(search_term)s IN BOOLEAN MODE)"""
                )
                external_data["search_term"] = "*" + search_term + "*"
            if seller_id is not None:
                externalwhere_clause.append("ExternalEvents.SellerId = %(sellerId)s")
                external_data["sellerId"] = seller_id
            if start is not None and end is not None:
                externalwhere_clause.append(
                    "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                external_data["startDate"] = datetime.fromtimestamp(start).strftime(
                    "%Y-%m-%d"
                )
                external_data["endDate"] = datetime.fromtimestamp(end).strftime(
                    "%Y-%m-%d"
                )
            elif end is not None:
                externalwhere_clause.append(
                    "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                external_data["startDate"] = datetime.now().strftime("%Y-%m-%d")
                external_data["endDate"] = datetime.fromtimestamp(end).strftime(
                    "%Y-%m-%d"
                )
            elif start is not None:
                externalwhere_clause.append("ExternalEvents.EventDate >= %(startDate)s")
                external_data["startDate"] = datetime.fromtimestamp(start).strftime(
                    "%Y-%m-%d"
                )
            else:
                externalwhere_clause.append("ExternalEvents.EventDate >= %(startDate)s")
                external_data["startDate"] = datetime.now().strftime("%Y-%m-%d")

            if len(externalwhere_clause) > 0:
                external_sql += " AND ".join(externalwhere_clause)

            external_sql += """ AND ExternalEvents.EventId NOT IN
                (SELECT DISTINCT ExternalEvents.EventId FROM ExternalEvents
                JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId 
                JOIN SellerEventCategory ON SellerEventCategory.SellerId = Sellers.SellerId 
                JOIN TicketSocketEvents ON 
                    TicketSocketEvents.SellerEventCategoryId = SellerEventCategory.SellerEventCategoryId
                    AND ExternalEvents.EventDate = TicketSocketEvents.EventDate) 
                ORDER BY ExternalEvents.EventDate ASC, ExternalEvents.Title ASC"""

            external_sql = external_sql.replace("\n", "")

            externalevent_rows = db_query_all(external_sql, external_data)
            for row in externalevent_rows:
                event_id = int(row["EventId"])
                vip_event = VipEvent()
                vip_event.event_id = event_id
                vip_event.title = str(row["Title"])
                vip_event.seller_name = str(row["SellerName"])
                vip_event.is_external = True
                vip_event.event_date = str(row["EventDate"])
                vip_event.announce_date = str(row["AnnounceDate"])
                vip_event.thumbnail = str(row["Thumbnail"])
                vip_event.external_url = str(row["URL"])
                venue = TicketSocketVenue(
                    str(row["Venue"]),
                    str(row["Address"]),
                    "",
                    str(row["City"]),
                    str(row["State"]),
                    str(row["Zip"]),
                    str(row["Country"]),
                    "",
                )
                vip_event.venue = venue
                vip_event.is_active = True if int(row["IsActive"]) == 1 else False
                vip_event.external_event_id = int(row["EventId"])
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
                    if (
                        vip_event.is_cancelled is True
                        and row["CancelledDate"] is not None
                    )
                    else None
                )
                events.append(vip_event)

        events.sort(key=operator.attrgetter("event_date", "title", "external_event_id"))

        return events

    def __get_ticket_types_from_event_id(self, ticket_socket_event_id: int):
        """
        Fetch from TicketSocketTicketTypes based on event Id
        """
        ticket_types: list[TicketSocketTicketType] = []

        sql = """SELECT TicketSocketTicketTypes.*
                    FROM TicketSocketTicketTypes
                    WHERE TicketSocketTicketTypes.TicketSocketEventId=%(ticketSocketEventId)s 
                    ORDER BY TicketSocketTicketTypes.TicketTypeName"""
        data = {"ticketSocketEventId": ticket_socket_event_id}

        rows = db_query_all(sql, data)
        for row in rows:
            ticket_type_id = int(row["TicketSocketTicketTypeId"])
            name = str(row["TicketTypeName"])
            total = int(row["TotalAvailable"])
            is_active: bool = int(row["IsActive"]) == 1
            ticket_type = TicketSocketTicketType(
                ticket_socket_event_id, ticket_type_id, name, total, is_active
            )
            ticket_types.append(ticket_type)

        return ticket_types

    def __get_event_notes(self, ticket_socket_event_id: int):
        """
        Fetch only event notes from TicketSocketEventNotes based on event Id
        """
        notes: list[EventNote] = []

        sql = """SELECT TicketSocketEventNotes.*
                    FROM TicketSocketEventNotes
                    WHERE TicketSocketEventNotes.TicketSocketEventId=%(ticketSocketEventId)s
                    AND TicketSocketOrderId IS NULL
                    ORDER BY TicketSocketEventNotes.NoteTimestamp"""
        data = {"ticketSocketEventId": ticket_socket_event_id}

        rows = db_query_all(sql, data)
        for row in rows:
            note = EventNote()
            note.note_id = int(row["TicketSocketEventNoteId"])
            note.ticket_socket_event_id = int(row["TicketSocketEventId"])
            note.ticket_socker_order_id = None
            note.note = str(row["Note"])
            note.note_timestamp = str(row["NoteTimestamp"])
            notes.append(note)

        return notes

    def disable_events(self, ticket_socket_event_ids: list[int], disabled: bool):
        """
        Marks eventIds as disabled
        """
        success: bool = True
        for ticket_socket_event_id in ticket_socket_event_ids:
            sql = """UPDATE TicketSocketEvents
                        SET IsActive=%(is_active)s,
                        LastUpdate=CURRENT_TIMESTAMP
                    WHERE Id=%(ticket_socket_event_id)s"""
            data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "is_active": 0 if disabled is True else 1,
            }
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def delete_events(self, ticket_socket_event_ids: list[int], deleted: bool):
        """
        Marks eventIds as deleted
        """
        success: bool = True
        for ticket_socket_event_id in ticket_socket_event_ids:
            sql = """UPDATE TicketSocketEvents
                        SET IsDeleted=%(isDeleted)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_event_id)s"""
            data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "isDeleted": 1 if deleted is True else 0,
            }
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def hide_events(self, ticket_socket_event_ids: list[int], hidden: bool):
        """
        Marks events as hidden
        """
        success: bool = True
        for ticket_socket_event_id in ticket_socket_event_ids:
            sql = """UPDATE TicketSocketEvents
                        SET IsHidden=%(isHidden)s,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE Id=%(ticket_socket_event_id)s"""
            data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "isHidden": 1 if hidden is True else 0,
            }
            success = db_update(sql, data)
            if success is False:
                break
        return success

    def cancel_event(
        self,
        ticket_socket_event_id: int,
        refund_service_fees: bool = False,
    ):
        """
        Cancels event, refunding all orders and/or service fees
        """
        success: bool = True
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        sql = """UPDATE TicketSocketEvents
                    SET IsCancelled=1,
                    CancelledDate=CURRENT_TIMESTAMP,
                    LastUpdate=CURRENT_TIMESTAMP
                    WHERE Id=%(ticket_socket_event_id)s"""
        success = db_update(sql, data)
        if success is True:
            success = self.refund_all_event_orders(
                ticket_socket_event_id, refund_service_fees
            )

        return success

    def refund_all_event_orders(
        self,
        ticket_socket_event_id: int,
        refund_service_fees: bool = False,
        mark_chargeback: bool = False,
    ):
        """
        Refunds all orders in an event one at a time
        """
        success: bool = True
        sql = """SELECT Id FROM TicketSocketOrders
                    WHERE TicketSocketEventId=%(ticket_socket_event_id)s"""
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        rows = db_query_all(sql, data)
        if len(rows) > 0:
            for row in rows:
                order_id = int(row["Id"])
                success = self.refund_order(
                    order_id, refund_service_fees, mark_chargeback
                )
                if success is False:
                    break
            if success is True:
                daily_order_service = DailyOrderService()
                daily_order_service.rebuild_daily_order_data_for_event(
                    ticket_socket_event_id
                )

        return success

    def update_event(self, event_to_update: VipEvent):
        """
        Update single event from admin
        """
        success: bool = True
        if event_to_update is None or event_to_update.ticket_socket_event_id <= 0:
            return False

        ticket_socket_event_id: int = event_to_update.ticket_socket_event_id
        sql = """SELECT * FROM TicketSocketEvents WHERE Id=%(ticket_socket_event_id)s"""
        data = {"ticket_socket_event_id": ticket_socket_event_id}
        existing_event: VipEvent = db_query_one(sql, data)

        if existing_event is not None:
            update_sql = """UPDATE TicketSocketEvents
                             SET IsActive=%(is_active)s, 
                             IsDeleted=%(isDeleted)s, 
                             IsAddedToBandsInTown=%(isAddedToBandsInTown)s, 
                             IsHidden=%(isHidden)s, 
                             AnnounceDate=%(announceDate)s, 
                             LastUpdate=CURRENT_TIMESTAMP 
                             WHERE Id=%(ticket_socket_event_id)s"""
            update_data = {
                "ticket_socket_event_id": ticket_socket_event_id,
                "is_active": (
                    1
                    if event_to_update.is_active is True
                    and event_to_update.is_deleted is False
                    else 0
                ),
                "isDeleted": 1 if event_to_update.is_deleted is True else 0,
                "isAddedToBandsInTown": (
                    1 if event_to_update.is_added_to_bands_in_town is True else 0
                ),
                "isHidden": 1 if event_to_update.is_hidden is True else 0,
                "announceDate": (
                    event_to_update.announce_date
                    if event_to_update.announce_date is not None
                    else None
                ),
            }
            success = db_update(update_sql, update_data)

            if (
                event_to_update.is_deleted is False
                and len(event_to_update.ticket_types) > 0
            ):
                for ticket_type in event_to_update.ticket_types:
                    ticket_type_wql = """UPDATE TicketSocketTicketTypes
                                        SET IsActive=%(is_active)s,
                                        TicketTypeName=%(ticketTypeName)s,
                                        LastUpdate=CURRENT_TIMESTAMP 
                                        WHERE TicketSocketTicketTypeId=%(ticket_type_id)s 
                                        AND TicketSocketEventId=%(ticket_socket_event_id)s"""
                    ticket_type_data = {
                        "ticket_type_id": ticket_type.ticket_type_id,
                        "ticket_socket_event_id": ticket_socket_event_id,
                        "is_active": 1 if ticket_type.is_active is True else 0,
                        "ticketTypeName": ticket_type.ticket_type_name,
                    }
                    success = db_update(ticket_type_wql, ticket_type_data)
                    if success is False:
                        break
        return success

    def add_event_note(
        self, ticket_socket_event_id: int, note: str, ticket_socket_order_id: int = None
    ):
        """
        API method to add a note specific to an event or order
        """
        sql = """INSERT INTO TicketSocketEventNotes (TicketSocketEventId, TicketSocketOrderId, Note)
                VALUES (%(ticketSocketEventId)s, %(ticketSocketOrderId)s, %(note)s)"""
        data = {
            "ticketSocketEventId": ticket_socket_event_id,
            "ticketSocketOrderId": ticket_socket_order_id,
            "note": note,
        }
        success = db_insert(sql, data)
        return success

    def rebuild_daily_order_data_for_event(self, event_id: int):
        """
        Clean out and rebuild daily order data for event
        """
        event_sql = """SELECT TicketSocketEvents.Id as TicketSocketEventId,
                            YEAR(TicketSocketEvents.EventDate) AS EventYear, 
                            SellerEventCategory.SellerId
                            FROM TicketSocketEvents
                            JOIN SellerEventCategory ON 
                             TicketSocketEvents.SellerEventCategoryId = 
                             SellerEventCategory.SellerEventCategoryId                         
                            WHERE TicketSocketEvents.Id=%(ticket_socket_event_id)s"""
        event_data = {"ticket_socket_event_id": event_id}
        event_row = db_query_one(event_sql, event_data)
        if event_row:
            event_id: int = event_row["TicketSocketEventId"]
            event_year: int = event_row["EventYear"]
            event_seller_id: int = event_row["SellerId"]

            start = datetime.strptime(
                f"{event_year}-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"
            ).timestamp()
            end = datetime(event_year, 12, 31).timestamp()

            order_service = OrderService()
            orders = order_service.get_orders(
                start=start, end=end, seller_id=event_seller_id
            )

            daily_order_service = DailyOrderService()
            daily_order_service.cleanup_daily_order_data_for_event(event_id)
            daily_order_service.update_daily_order_data(orders, start, end, None)
