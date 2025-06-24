"""
Event Service
"""

from datetime import datetime

from common.calendar_service import CalendarService
from common.db import (
    db_insert,
    db_query_all,
    db_query_one,
    db_update,
    db_convert_list_to_parameters,
)
from common.models.national_acts import VipEvent
from common.models.ticket_socket import (
    TicketSocketVenue,
    TicketSocketTicketType,
    Country,
)
from common.order_service import OrderService
from common.daily_order_service import DailyOrderService
from common.utility import (
    get_country_from_country_name,
    get_timezone_abbreviation,
    get_timezones_from_country_code,
    resize_tmp_image,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    move_temp_file_to_public_folder,
    remove_file,
)


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
        event_id: int = None,
        show_deleted: bool = False,
        exclude_start: int = None,
        exclude_end: int = None,
        exclude_external: bool = False,
        show_hidden: bool = False,
        ignore_flags: bool = False,
        show_cancelled: bool = True,
        seller_ids: list[int] = None,
        tour_id: int = None,
        is_public: bool = False,
    ):
        """
        main method to fetch events and orders
        """
        events: list[VipEvent] = []
        now_ts: float = datetime.now().timestamp()

        if seller_ids is None:
            seller_ids = []

        if len(seller_ids) == 0 and seller_id is not None:
            seller_ids.append(seller_id)

        if get_orders is False and search_term is not None:
            search_term = search_term.replace("'", "''")
            search_term = search_term.replace('"', "")
            search_term = search_term.replace("=", "")
            search_term = search_term.strip()
        else:
            search_term = None

        sql = """SELECT Sellers.SellerId AS SellerId,
                    Sellers.Name AS SellerName,
                    ExternalEvents.EventId AS ExternalEventId, 
                    TicketSocketEvents.Id AS TicketSocketEventId,                    
                    COALESCE(ExternalEvents.EventDate, TicketSocketEvents.EventDate) AS EventDate,
                    TicketSocketEvents.SellerEventCategoryId AS SellerEventCategoryId,
                    TicketSocketEvents.IsVip AS IsVip,
                    ExternalEvents.EventTime AS EventTime,
                    ExternalEvents.MeetAndGreetTime AS MeetAndGreetTime,
                    ExternalEvents.DoorsOpenTime AS DoorsOpenTime,
                    COALESCE(ExternalEvents.Title, TicketSocketEvents.Title) AS Title,
                    COALESCE(ExternalEventVenues.Venue, TicketSocketEvents.Venue) AS Venue,
                    COALESCE(ExternalEventVenues.Address, TicketSocketEvents.Address) AS Address,
                    COALESCE(ExternalEventVenues.City, TicketSocketEvents.City) AS City,
                    COALESCE(ExternalEventVenues.State, TicketSocketEvents.State) AS State,
                    COALESCE(ExternalEventVenues.Zip, TicketSocketEvents.Zip) AS Zip,
                    COALESCE(Country.CountryName, TicketSocketEvents.Country) AS Country,
                    ExternalEventVenues.TimeZone AS TimeZone,
                    Country.CountryId AS CountryId,
                    Country.CountryCode AS CountryCode,
                    COALESCE(ExternalEvents.EmailSentToVips, 0) AS EmailSentToVips,
                    COALESCE(ExternalEvents.TextSentToVips, 0) AS TextSentToVips,
                    COALESCE(ExternalEvents.ListSentToBand, 0) AS ListSentToBand,
                    ExternalEvents.ListSentTime AS ListSentTime,
                    COALESCE(ExternalEvents.ListSentNumVips, 0) AS ListSentNumVips,
                    ExternalEvents.CheckInLocation AS CheckInLocation,
                    ExternalEvents.CheckInNotes AS CheckInNotes,                    
                    ExternalEvents.AnnounceDate AS AnnounceDate,
                    ExternalEvents.IsAddedToBandsInTown AS IsAddedToBandsInTown,                    
                    ExternalEvents.URL AS ExternalUrl,
                    ExternalEvents.Thumbnail AS ExternalThumbnail,                    
                    ExternalEvents.ExternalEventVenueId AS ExternalEventVenueId,
                    ExternalEvents.DisableLinkButton AS DisableLinkButton,
                    ExternalEvents.DisableLinkReason AS DisableLinkReason, 
                    ExternalEvents.ExternalVipLink AS ExternalVipLink,
                    ExternalEvents.DisableVipLinkButton AS DisableVipLinkButton, 
                    ExternalEvents.DisableVipLinkReason AS DisableVipLinkReason,
                    ExternalEvents.IsActive AS IsActive,    
                    ExternalEvents.IsDeleted AS IsDeleted,     
                    ExternalEvents.IsHidden AS IsHidden,    
                    ExternalEvents.IsCancelled AS IsCancelled,
                    ExternalEvents.CancelledDate AS CancelledDate,   
                    TicketSocketEvents.EventId AS EventId,                    
                    TicketSocketEvents.URL AS URL,
                    TicketSocketEvents.Thumbnail,                 
                    Tour.AnnounceDate AS TourAnnounceDate,
                    COALESCE(Tour.IsActive, 0) AS IsTourActive,
                    COALESCE(TicketSocketEvents.IsSoldOut, 0) AS IsSoldOut
                 FROM ExternalEvents
            JOIN Sellers ON Sellers.SellerId = ExternalEvents.SellerId
            LEFT JOIN TicketSocketEvents ON TicketSocketEvents.Id = ExternalEvents.TicketSocketEventId
            LEFT JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
            LEFT JOIN ExternalEventVenues ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
            LEFT JOIN Country ON Country.CountryId = ExternalEventVenues.CountryId
            LEFT JOIN TourEvent ON TourEvent.ExternalEventId = ExternalEvents.EventId
            LEFT JOIN Tour ON Tour.TourId = TourEvent.TourId            
            WHERE """
        data = {}

        where_clause: list[str] = []
        if event_id is not None and event_id > 0:
            where_clause.append("ExternalEvents.EventId = %(event_id)s")
            data["event_id"] = event_id
        elif tour_id is not None and tour_id > 0:
            tour_sql = "SELECT ExternalEventId FROM TourEvent WHERE TourId=%(tour_id)s"
            tour_data = {"tour_id": tour_id}
            tour_rows = db_query_all(tour_sql, tour_data)
            tour_event_ids: list[int] = []
            for tour_row in tour_rows:
                tour_event_id = get_override_int_value_or_default(
                    tour_row["ExternalEventId"], default=None
                )
                if tour_event_id is not None and tour_event_id > 0:
                    tour_event_ids.append(tour_event_id)

            if len(tour_event_ids) > 0:
                event_ids_str = db_convert_list_to_parameters(
                    tour_event_ids, data, "eventId"
                )
                where_clause.append("ExternalEvents.EventId IN " + event_ids_str)
        else:
            if len(seller_ids) > 0:
                seller_id_str = db_convert_list_to_parameters(
                    seller_ids, data, "sellerId"
                )
                where_clause.append(
                    """(ExternalEvents.SellerId IN """ + seller_id_str + """)"""
                )

            if ignore_flags is not True:
                if show_deleted is not True:
                    where_clause.append("COALESCE(ExternalEvents.IsDeleted, 0) = 0")
                else:
                    show_inactive = True

                if show_inactive is True:
                    where_clause.append("COALESCE(ExternalEvents.IsActive, 1) = 0")
                else:
                    where_clause.append("COALESCE(ExternalEvents.IsActive, 1) = 1")

                if show_hidden is not True:
                    where_clause.append("COALESCE(ExternalEvents.IsHidden, 0) = 0")

                if show_cancelled is not True:
                    where_clause.append("COALESCE(ExternalEvents.IsCancelled, 0) = 0")

            if search_term is not None and len(search_term) > 0:
                where_clause.append(
                    """CONCAT_WS (' ', Sellers.Name, 
                                COALESCE(ExternalEvents.Title, TicketSocketEvents.Title),
                                COALESCE(Country.CountryName, ''),
                                COALESCE(ExternalEventVenues.Venue, ''),
                                COALESCE(ExternalEventVenues.Address, ''),
                                COALESCE(ExternalEventVenues.City, ''),
                                COALESCE(ExternalEventVenues.State, ''),
                                COALESCE(TicketSocketEvents.Venue, ''),
                                COALESCE(TicketSocketEvents.Address, ''),
                                COALESCE(TicketSocketEvents.City, ''),
                                COALESCE(TicketSocketEvents.State, ''),
                                COALESCE(TicketSocketEvents.Country, '')) 
                                LIKE ('%"""
                    + search_term
                    + """%')"""
                )

            if start is not None and end is not None:
                where_clause.append(
                    "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif end is not None and end > datetime.now().timestamp():
                where_clause.append(
                    "ExternalEvents.EventDate BETWEEN %(startDate)s AND %(endDate)s"
                )
                data["startDate"] = datetime.now().strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif start is not None:
                where_clause.append("ExternalEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            elif is_public is True:
                where_clause.append("ExternalEvents.EventDate >= %(startDate)s")
                data["startDate"] = datetime.now().strftime("%Y-%m-%d")

            if exclude_start is not None and exclude_end is not None:
                where_clause.append(
                    "ExternalEvents.EventDate NOT BETWEEN %(exclude_start)s AND %(exclude_end)s"
                )
                data["exclude_start"] = datetime.fromtimestamp(exclude_start).strftime(
                    "%Y-%m-%d"
                )
                data["exclude_end"] = datetime.fromtimestamp(exclude_end).strftime(
                    "%Y-%m-%d"
                )

        if len(where_clause) > 0:
            sql += " AND ".join(where_clause)

        sql += """ ORDER BY ExternalEvents.EventDate,
                 ExternalEvents.EventTime,
                 ExternalEvents.MeetAndGreetTime, 
                 COALESCE(ExternalEvents.Title, TicketSocketEvents.Title)"""

        sql = sql.replace("\n", "")

        event_rows = db_query_all(sql, data)

        calendar_service = CalendarService()
        order_service = OrderService()

        for row in event_rows:
            tour_announce_date_str = get_override_string_value_or_default(
                row["TourAnnounceDate"]
            )

            announce_date_str = get_override_string_value_or_default(
                row["AnnounceDate"]
            )

            is_tour_active = get_override_bool_value_or_default(row["IsTourActive"])

            # get tour announce datetime from active tours only
            tad_ts: float = None
            if is_tour_active is True and tour_announce_date_str is not None:
                tad_ts = datetime.strptime(
                    tour_announce_date_str, "%Y-%m-%d %H:%M:%S"
                ).timestamp()

            # get event announce datetime (if available)
            ad_ts: float = None
            if announce_date_str is not None:
                ad_ts = datetime.strptime(
                    announce_date_str, "%Y-%m-%d %H:%M:%S"
                ).timestamp()

            # for public page, skip events where the announce date has not yet passed
            if is_public is True and (ad_ts is not None or tad_ts is not None):
                if ad_ts is not None:
                    if ad_ts > now_ts:
                        continue
                elif tad_ts is not None:
                    if tad_ts > now_ts:
                        continue

            external_event_id = get_override_int_value_or_default(
                row["ExternalEventId"]
            )
            event_id = get_override_int_value_or_default(row["EventId"])
            ticket_socket_event_id = get_override_int_value_or_default(
                row["TicketSocketEventId"], default=None
            )

            is_external: bool = (external_event_id > 0) and (
                ticket_socket_event_id is None or ticket_socket_event_id <= 0
            )

            if external_event_id == 0 or (exclude_external and is_external):
                continue

            vip_event = VipEvent()
            vip_event.external_event_id = external_event_id
            vip_event.ticket_socket_event_id = ticket_socket_event_id
            vip_event.event_id = event_id
            vip_event.announce_date = announce_date_str
            vip_event.tour_announce_date = tour_announce_date_str
            vip_event.is_external = is_external

            # event data
            vip_event.seller_event_category_id = get_override_int_value_or_default(
                row["SellerEventCategoryId"], default=None
            )
            vip_event.event_date = get_override_string_value_or_default(
                row["EventDate"]
            )
            vip_event.title = get_override_string_value_or_default(row["Title"])
            thumbnail = get_override_string_value_or_default(row["Thumbnail"])
            external_thumbnail = get_override_string_value_or_default(
                row["ExternalThumbnail"]
            )
            vip_event.is_sold_out = get_override_bool_value_or_default(row["IsSoldOut"])

            # ExternalEvents.Thumbnail overrides the thumbnail from TS, but preserve both
            if external_thumbnail is not None:
                vip_event.thumbnail = external_thumbnail
                vip_event.external_thumbnail = external_thumbnail
            else:
                vip_event.thumbnail = thumbnail
                vip_event.external_thumbnail = None

            vip_event.ticket_socket_url = get_override_string_value_or_default(
                row["URL"]
            )
            vip_event.cancelled_date = get_override_string_value_or_default(
                row["CancelledDate"]
            )
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
            vip_event.meet_and_greet_time = get_override_string_value_or_default(
                row["MeetAndGreetTime"]
            )
            vip_event.doors_open = get_override_string_value_or_default(
                row["DoorsOpenTime"]
            )
            vip_event.external_url = get_override_string_value_or_default(
                row["ExternalUrl"]
            )
            vip_event.event_time = get_override_string_value_or_default(
                row["EventTime"]
            )
            vip_event.external_event_venue_id = get_override_int_value_or_default(
                row["ExternalEventVenueId"]
            )
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
            vip_event.seller_id = get_override_int_value_or_default(row["SellerId"])
            vip_event.seller_name = get_override_string_value_or_default(
                row["SellerName"]
            )
            if vip_event.external_vip_link is not None:
                vip_event.ticket_socket_url = vip_event.external_vip_link

            # venue data
            venue_name = get_override_string_value_or_default(row["Venue"])
            address = get_override_string_value_or_default(row["Address"])
            city = get_override_string_value_or_default(row["City"])
            state = get_override_string_value_or_default(row["State"])
            zip_code = get_override_string_value_or_default(row["Zip"])
            vip_country = get_override_string_value_or_default(row["Country"])
            country_id = get_override_int_value_or_default(row["CountryId"])
            country_code = get_override_string_value_or_default(row["CountryCode"])
            timezone_code = get_override_string_value_or_default(row["TimeZone"])
            timezone = get_timezone_abbreviation(timezone_code, vip_event.event_date)
            country: Country = None
            if country_code is not None:
                country = Country(country_id, vip_country, country_code)
                if is_public is not True:
                    timezones = get_timezones_from_country_code(
                        country_code, vip_event.event_date
                    )
                    country.timezones = timezones

            venue = TicketSocketVenue(
                venue_name, address, city, state, zip_code, country, timezone
            )
            vip_event.venue = venue

            # flags
            vip_event.is_vip = get_override_bool_value_or_default(row["IsVip"])
            vip_event.is_added_to_bands_in_town = get_override_bool_value_or_default(
                row["IsAddedToBandsInTown"]
            )
            vip_event.is_hidden = get_override_bool_value_or_default(row["IsHidden"])
            vip_event.is_cancelled = get_override_bool_value_or_default(
                row["IsCancelled"]
            )

            vip_event.is_active = get_override_bool_value_or_default(row["IsActive"])

            vip_event.is_deleted = get_override_bool_value_or_default(row["IsDeleted"])
            if vip_event.is_deleted is True:
                vip_event.is_active = False

            notes = calendar_service.get_event_notes(vip_event.external_event_id)
            vip_event.notes = notes

            if is_public is False and get_orders is True:
                ticket_types = self.__get_ticket_types_from_event_id(
                    ticket_socket_event_id
                )
                vip_event.ticket_types = ticket_types

                orders = order_service.get_orders_from_event_id(
                    ticket_socket_event_id,
                    show_inactive,
                    show_deleted,
                    ignore_flags,
                )
                vip_event.orders = orders

            vip_event.get_totals()

            events.append(vip_event)

        return events

    def get_ticket_socket_events_only(self, seller_id: int = None):
        """
        Fetch only TS events for association with External Events
        """
        events: list[VipEvent] = []
        sql = """SELECT SellerEventCategory.SellerId, TicketSocketEvents.*
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
            vip_event.event_id = get_override_int_value_or_default(row["EventId"])
            vip_event.title = get_override_string_value_or_default(row["Title"])
            vip_event.event_date = get_override_string_value_or_default(
                row["EventDate"]
            )
            vip_event.thumbnail = get_override_string_value_or_default(row["Thumbnail"])
            vip_event.ticket_socket_url = get_override_string_value_or_default(
                row["URL"]
            )

            country_name = get_override_string_value_or_default(row["Country"])
            country = get_country_from_country_name(country_name)

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
                get_override_string_value_or_default(row["State"]),
                get_override_string_value_or_default(row["Zip"]),
                country,
                "",
            )
            vip_event.is_vip = get_override_bool_value_or_default(row["IsVip"])
            vip_event.is_sold_out = get_override_bool_value_or_default(row["IsSoldOut"])
            events.append(vip_event)
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
            ticket_type_id = get_override_int_value_or_default(
                row["TicketSocketTicketTypeId"]
            )
            name = get_override_string_value_or_default(row["TicketTypeName"])
            total = get_override_int_value_or_default(row["TotalAvailable"])
            is_active = get_override_bool_value_or_default(row["IsActive"])
            ticket_type = TicketSocketTicketType(
                ticket_socket_event_id, ticket_type_id, name, total, is_active
            )
            ticket_types.append(ticket_type)

        return ticket_types

    def disable_events(self, event_ids: list[int], disabled: bool):
        """
        Marks eventIds as disabled
        """
        success: bool = True
        if len(event_ids) > 0:
            for event_id in event_ids:
                sql = """UPDATE ExternalEvents
                            SET IsActive=%(is_active)s,
                            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE EventId=%(event_id)s"""
                data = {
                    "event_id": event_id,
                    "is_active": get_override_tinyint_value_or_default_from_bool(
                        not disabled
                    ),
                }
                success = db_update(sql, data)
                if success is False:
                    break
                else:
                    sql_id = """SELECT TicketSocketEventId
                                    FROM ExternalEvents 
                                    WHERE EventId=%(event_id)s"""
                    data_id = {"event_id": event_id}
                    row = db_query_one(sql_id, data_id)
                    if "TicketSocketEventId" in row:
                        ts_id = get_override_int_value_or_default(
                            row["TicketSocketEventId"]
                        )
                        if ts_id is not None and ts_id > 0:
                            self.rebuild_daily_order_data_for_event(ts_id)

        return success

    def delete_events(self, event_ids: list[int], deleted: bool):
        """
        Marks eventIds as deleted
        """
        success: bool = True
        if len(event_ids) > 0:
            for event_id in event_ids:
                sql = """UPDATE ExternalEvents
                            SET IsDeleted=%(isDeleted)s,"""
                if deleted is True:
                    sql += """ IsActive=0,"""
                sql += """ LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE EventId=%(event_id)s"""
                data = {
                    "event_id": event_id,
                    "isDeleted": get_override_tinyint_value_or_default_from_bool(
                        deleted
                    ),
                }
                success = db_update(sql, data)
                if success is False:
                    break
                else:
                    sql_id = """SELECT TicketSocketEventId
                                    FROM ExternalEvents 
                                    WHERE EventId=%(event_id)s"""
                    data_id = {"event_id": event_id}
                    row = db_query_one(sql_id, data_id)
                    ts_id = get_override_int_value_or_default(
                        row["TicketSocketEventId"], default=None
                    )
                    if ts_id is not None and ts_id > 0:
                        self.rebuild_daily_order_data_for_event(ts_id)

        return success

    def hide_events(self, event_ids: list[int], hidden: bool):
        """
        Marks events as hidden
        """
        success: bool = True
        if len(event_ids) > 0:
            for event_id in event_ids:
                sql = """UPDATE ExternalEvents
                            SET IsHidden=%(isHidden)s,
                            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                            WHERE EventId=%(event_id)s"""
                data = {
                    "event_id": event_id,
                    "isHidden": get_override_tinyint_value_or_default_from_bool(hidden),
                }
                success = db_update(sql, data)
                if success is False:
                    break
        return success

    def cancel_event(
        self,
        event_id: int,
        is_cancelled: bool = False,
    ):
        """
        Marks event as cancelled or not
        """
        success: bool = True
        data = {"event_id": event_id}
        sql = ""
        if is_cancelled is True:
            sql = """UPDATE ExternalEvents
                        SET IsCancelled=1,
                        CancelledDate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                        WHERE EventId=%(event_id)s"""
        else:
            sql = """UPDATE ExternalEvents
                        SET IsCancelled=0,
                        CancelledDate=NULL,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
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
            success = self.cancel_event(event_id, True)

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
                    self.rebuild_daily_order_data_for_event(ticket_socket_event_id)

        return success

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
            existing_events = self.get_events_and_orders(
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
        }

        if event_to_update.external_thumbnail is not None:
            is_new_thumbnail: bool = False
            if existing_event is not None:
                is_new_thumbnail = (
                    event_to_update.external_thumbnail
                    != existing_event.external_thumbnail
                )
            else:
                is_new_thumbnail = True

            if is_new_thumbnail is True:
                event_date_str: str = ""
                event_time = get_override_string_value_or_default(
                    event_to_update.event_time
                )
                if event_time is not None:
                    event_date = datetime.strptime(
                        event_to_update.event_time, "%Y-%m-%d %H:%M:%S"
                    )
                    event_date_str = event_date.strftime("%Y%m%d%H%M%S")
                else:
                    event_date = datetime.strptime(
                        event_to_update.event_date, "%Y-%m-%d"
                    )
                    event_date_str = event_date.strftime("%Y%m%d")

                image_id = f"{event_date_str}_{event_to_update.seller_id}"
                thumb_file = resize_tmp_image(
                    event_to_update.external_thumbnail, image_id
                )
                if thumb_file is not None:
                    update_data["thumbnail"] = get_override_string_value_or_default(
                        thumb_file
                    )
                    move_temp_file_to_public_folder(thumb_file, "common/thumbnails")
                    if existing_event is not None:
                        existing_thumbnail = get_override_string_value_or_default(
                            existing_event.external_thumbnail
                        )
                        if existing_thumbnail is not None:
                            remove_file(existing_thumbnail, "common/thumbnails")
        elif existing_event is not None:
            existing_thumbnail = get_override_string_value_or_default(
                existing_event.external_thumbnail
            )
            if existing_thumbnail is not None:
                remove_file(existing_thumbnail, "common/thumbnails")

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
                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
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
                EmailSentToVips, TextSentToVips, Thumbnail, Created, LastUpdate) VALUES
                (%(seller_id)s, %(title)s, %(event_date)s,%(ticket_socket_event_id)s,
                %(event_time)s, %(meet_and_greet_time)s,%(doors_open_time)s, %(url)s,
                %(external_event_venue_id)s, %(disable_link_button)s,
                %(disable_link_reason)s, %(external_vip_link)s, %(disable_vip_link_button)s,
                %(disable_vip_link_reason)s, %(is_active)s, %(isAddedToBandsInTown)s, %(isDeleted)s, 
                %(isHidden)s, %(announceDate)s, %(checkInLocation)s, %(checkInNotes)s,
                %(emailSentToVips)s, %(textSentToVips)s, %(thumbnail)s, 
                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), 
                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

            event_id = db_insert(update_sql, update_data)
            success = event_id > 0

        if (
            ticket_socket_event_id is not None
            and event_to_update.is_deleted is False
            and len(event_to_update.ticket_types) > 0
        ):
            for ticket_type in event_to_update.ticket_types:
                ticket_type_wql = """UPDATE TicketSocketTicketTypes
                                    SET IsActive=%(is_active)s,
                                    TicketTypeName=%(ticketTypeName)s,
                                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
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
                }
                success = db_update(ticket_type_wql, ticket_type_data)
                if success is False:
                    break

            if success is True:
                self.rebuild_daily_order_data_for_event(ticket_socket_event_id)
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
                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                    ListSentNumVips=%(numVips)s, """

        data = {
            "numVips": num_vips,
            "event_id": event_id,
            "listSent": 1 if is_sent is True else 0,
        }

        if is_sent is True:
            sql += """ListSentTime=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')"""
        else:
            sql += """ListSentTime=NULL"""

        sql += """ WHERE EventId=%(event_id)s"""

        success = db_update(sql, data)
        if success:
            events = self.get_events_and_orders(
                event_id=event_id,
                ignore_flags=True,
                exclude_external=True,
                get_orders=True,
            )
            if events is not None and len(events) > 0:
                updated_event = events[0]
        return updated_event
