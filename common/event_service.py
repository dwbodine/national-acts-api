"""
Event Service
"""

from datetime import datetime
import pytz

from common.calendar_service import CalendarService
from common.constants import DEFAULT_COUNTRY_ID
from common.dashboard_service import DashboardService
from common.db import (
    db_insert,
    db_query_all,
    db_query_one,
    db_update,
    db_convert_list_to_parameters,
)
from common.models.national_acts import Seller, Tour, VipEvent
from common.models.ticket_socket import (
    TicketSocketVenue,
    TicketSocketTicketType,
    Country,
)
from common.order_service import OrderService
from common.ticket_partner_service import TicketPartnerService
from common.utility import (
    get_override_float_value_or_default,
    get_timezone_abbreviation,
    get_timezones_from_country_code,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
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
        is_website: bool = False,
        is_portal: bool = False,
    ):
        """
        main method to fetch events and orders
        """
        events: list[VipEvent] = []

        pacific_tz = pytz.timezone("America/Los_Angeles")
        pac_now_ts: float = datetime.now(pacific_tz).timestamp()

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

        sql = """SELECT * FROM EventDetails"""
        data = {}

        where_clause: list[str] = []
        if event_id is not None and event_id > 0:
            where_clause.append("EventId = %(event_id)s")
            data["event_id"] = event_id
        elif tour_id is not None and tour_id > 0:
            tour_sql = "SELECT EventId FROM TourEvent WHERE TourId=%(tour_id)s"
            tour_data = {"tour_id": tour_id}
            tour_rows = db_query_all(tour_sql, tour_data)
            tour_event_ids: list[int] = []
            for tour_row in tour_rows:
                tour_event_id = get_override_int_value_or_default(
                    tour_row["EventId"], default=None
                )
                if tour_event_id is not None and tour_event_id > 0:
                    tour_event_ids.append(tour_event_id)

            if len(tour_event_ids) > 0:
                event_ids_str = db_convert_list_to_parameters(
                    tour_event_ids, data, "eventId"
                )
                where_clause.append("EventId IN " + event_ids_str)
        else:
            if len(seller_ids) > 0:
                seller_id_str = db_convert_list_to_parameters(
                    seller_ids, data, "sellerId"
                )
                where_clause.append("""(SellerId IN """ + seller_id_str + """)""")

            if ignore_flags is not True:
                if show_deleted is not True:
                    where_clause.append("COALESCE(IsDeleted, 0) = 0")
                else:
                    show_inactive = True

                if show_inactive is True:
                    where_clause.append("COALESCE(IsActive, 1) = 0")
                else:
                    where_clause.append("COALESCE(IsActive, 1) = 1")

                if show_hidden is not True:
                    where_clause.append("COALESCE(IsHidden, 0) = 0")

                if show_cancelled is not True or is_public is True:
                    where_clause.append("COALESCE(IsCancelled, 0) = 0")

            if search_term is not None and len(search_term) > 0:
                where_clause.append("""CONCAT_WS (' ', SellerName, Title, Country,
                        Venue, Address, City, State) LIKE %(searchTerm)s""")
                data["searchTerm"] = "%" + search_term + "%"

            if start is not None and end is not None:
                where_clause.append("EventDate BETWEEN %(startDate)s AND %(endDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif end is not None and end > datetime.now(pacific_tz).timestamp():
                where_clause.append("EventDate BETWEEN %(startDate)s AND %(endDate)s")
                data["startDate"] = datetime.now(pacific_tz).strftime("%Y-%m-%d")
                data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
            elif start is not None:
                where_clause.append("EventDate >= %(startDate)s")
                data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            elif is_public is True:
                where_clause.append("EventDate >= %(startDate)s")
                data["startDate"] = datetime.now(pacific_tz).strftime("%Y-%m-%d")

            if exclude_start is not None and exclude_end is not None:
                where_clause.append(
                    "EventDate NOT BETWEEN %(exclude_start)s AND %(exclude_end)s"
                )
                data["exclude_start"] = datetime.fromtimestamp(exclude_start).strftime(
                    "%Y-%m-%d"
                )
                data["exclude_end"] = datetime.fromtimestamp(exclude_end).strftime(
                    "%Y-%m-%d"
                )

        if len(where_clause) > 0:
            sql += """ WHERE """
            sql += """ AND """.join(where_clause)

        sql += """ ORDER BY EventDate,
                 EventTime,
                 MeetAndGreetTime,
                 Title"""

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
                tad_ts_dt = datetime.strptime(
                    tour_announce_date_str, "%Y-%m-%d %H:%M:%S"
                )
                tad_ts = pacific_tz.localize(tad_ts_dt).timestamp()

            # get event announce datetime (if available)
            ad_ts: float = None
            if announce_date_str is not None:
                ad_ts_dt = datetime.strptime(announce_date_str, "%Y-%m-%d %H:%M:%S")
                ad_ts = pacific_tz.localize(ad_ts_dt).timestamp()

            # for public page, skip events where the announce date has not yet passed
            if is_public is True and (ad_ts is not None or tad_ts is not None):
                if ad_ts is not None and ad_ts > pac_now_ts:
                    continue

                if ad_ts is None and tad_ts is not None and tad_ts > pac_now_ts:
                    continue

            event_id = get_override_int_value_or_default(row["EventId"])
            ticket_socket_event_id = get_override_int_value_or_default(
                row["TicketSocketEventId"], default=None
            )

            is_external: bool = (event_id > 0) and (
                ticket_socket_event_id is None or ticket_socket_event_id <= 0
            )

            if event_id == 0 or (exclude_external and is_external):
                continue

            visible_on_site = get_override_bool_value_or_default(row["IsVisibleOnSite"])

            if is_website is True and visible_on_site is False:
                continue

            visible_on_portal = get_override_bool_value_or_default(
                row["IsVisibleOnPortal"]
            )

            if is_portal is True and visible_on_portal is False:
                continue

            vip_event = VipEvent()
            vip_event.ticket_partner_id = get_override_int_value_or_default(
                row["TicketPartnerId"]
            )
            vip_event.ticket_partner_event_id = get_override_int_value_or_default(
                row["TicketPartnerEventId"]
            )
            vip_event.original_event_id = get_override_int_value_or_default(
                row["TicketSocketNativeEventId"]
            )
            vip_event.event_id = event_id
            vip_event.announce_date = announce_date_str
            vip_event.tour_announce_date = tour_announce_date_str
            vip_event.is_external = is_external
            vip_event.last_update = get_override_string_value_or_default(
                row["LastUpdate"]
            )

            # event data
            vip_event.seller_event_category_id = get_override_int_value_or_default(
                row["SellerEventCategoryId"], default=None
            )
            vip_event.is_visible_on_site = visible_on_site
            vip_event.is_visible_on_portal = visible_on_portal
            vip_event.seller_rate_percent = get_override_float_value_or_default(
                row["SellerRatePercent"]
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

            # Events.Thumbnail overrides the thumbnail from TS, but preserve both
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
            vip_event.venue_id = get_override_int_value_or_default(row["VenueId"])
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
            vip_event.seller_type = get_override_int_value_or_default(row["SellerType"])
            vip_event.exclude_from_dashboard = get_override_bool_value_or_default(
                row["ExcludeFromDashboard"]
            )
            vip_event.event_note = get_override_string_value_or_default(
                row["EventNote"]
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

            notes = calendar_service.get_event_notes(vip_event.event_id)
            vip_event.notes = notes

            if is_public is False and get_orders is True:
                ticket_types = self.__get_ticket_types_from_event_id(
                    vip_event.ticket_partner_event_id, is_portal
                )
                vip_event.ticket_types = ticket_types

                orders = order_service.get_orders_from_event_id(
                    vip_event.ticket_partner_event_id,
                    show_inactive,
                    show_deleted,
                    ignore_flags,
                )
                vip_event.orders = orders

            vip_event.get_totals()

            events.append(vip_event)

        return events

    def __get_ticket_types_from_event_id(
        self, ticket_partner_event_id: int, is_portal: bool
    ):
        """
        Fetch provider-backed ticket types through TicketTypeDetails.
        """
        ticket_types: list[TicketSocketTicketType] = []

        sql = """SELECT * FROM TicketTypeDetails
                    WHERE TicketPartnerEventId=%(ticketPartnerEventId)s
                        AND TicketSocketTicketTypeId IS NOT NULL"""

        data = {"ticketPartnerEventId": ticket_partner_event_id}

        if is_portal is True:
            sql += """ AND IsActive=1"""

        sql += """ ORDER BY TicketTypeOrder, TicketTypeName"""

        rows = db_query_all(sql, data)
        for row in rows:
            ticket_type_id = get_override_int_value_or_default(
                row["TicketSocketTicketTypeId"]
            )
            name = get_override_string_value_or_default(row["TicketTypeName"])
            total = get_override_int_value_or_default(row["TotalAvailable"])
            is_active = get_override_bool_value_or_default(row["IsActive"])
            order = get_override_int_value_or_default(row["TicketTypeOrder"], default=1)
            ticket_type = TicketSocketTicketType(
                ticket_partner_event_id, ticket_type_id, name, total, is_active, order
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
                sql = """UPDATE Events
                            SET IsActive=%(is_active)s,
                            LastUpdate=CURRENT_TIMESTAMP
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

                sql_id = """SELECT DISTINCT TicketPartnerEventId
                                FROM EventDetails
                                WHERE EventId=%(event_id)s"""
                data_id = {"event_id": event_id}
                row = db_query_one(sql_id, data_id)
                if row and "TicketPartnerEventId" in row:
                    ts_id = get_override_int_value_or_default(
                        row["TicketPartnerEventId"]
                    )
                    if ts_id is not None and ts_id > 0:
                        dashboard_service = DashboardService()
                        dashboard_service.rebuild_daily_order_data_for_event(ts_id)

        return success

    def mark_events_live_in_bands_in_town(self, event_ids: list[int]):
        """
        Marks eventIds as live in BandsInTown
        """
        success: bool = True
        if len(event_ids) > 0:
            for event_id in event_ids:
                sql = """UPDATE Events
                            SET IsAddedToBandsInTown=1,
                            LastUpdate=CURRENT_TIMESTAMP
                        WHERE EventId=%(event_id)s"""
                data = {"event_id": event_id}
                success = db_update(sql, data)
                if success is False:
                    break
        return success

    def delete_events(self, event_ids: list[int], deleted: bool):
        """
        Marks eventIds as deleted
        """
        success: bool = True
        if len(event_ids) > 0:
            for event_id in event_ids:
                sql = """UPDATE Events
                            SET IsDeleted=%(isDeleted)s,"""
                if deleted is True:
                    sql += """ IsActive=0,"""
                sql += """ LastUpdate=CURRENT_TIMESTAMP
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

                sql_id = """SELECT DISTINCT TicketPartnerEventId
                                FROM EventDetails
                                WHERE EventId=%(event_id)s"""
                data_id = {"event_id": event_id}
                row = db_query_one(sql_id, data_id)
                if row and "TicketPartnerEventId" in row:
                    ts_id = get_override_int_value_or_default(
                        row["TicketPartnerEventId"], default=None
                    )
                    if ts_id is not None and ts_id > 0:
                        dashboard_service = DashboardService()
                        dashboard_service.rebuild_daily_order_data_for_event(ts_id)

        return success

    def hide_events(self, event_ids: list[int], hidden: bool):
        """
        Marks events as hidden
        """
        success: bool = True
        if len(event_ids) > 0:
            for event_id in event_ids:
                sql = """UPDATE Events
                            SET IsHidden=%(isHidden)s,
                            LastUpdate=CURRENT_TIMESTAMP
                            WHERE EventId=%(event_id)s"""
                data = {
                    "event_id": event_id,
                    "isHidden": get_override_tinyint_value_or_default_from_bool(hidden),
                }
                success = db_update(sql, data)
                if success is False:
                    break
        return success

    def add_to_events(self, event_data: dict[str, any], evt: VipEvent, cnx: any):
        """
        Add a new event to events
        """
        # try to find venue in existing data if possible
        venue_id: int = 0
        venue_sql = """SELECT VenueID FROM Venues
            WHERE Venue=%(venue)s AND City=%(city)s LIMIT 0, 1"""
        venue_data = {
            "venue": event_data["venue"],
            "city": event_data["city"],
        }
        venue_row = db_query_one(venue_sql, venue_data)
        if venue_row:
            venue_id = get_override_int_value_or_default(venue_row["VenueID"])

        if venue_id > 0:
            event_data["venue_id"] = venue_id
        else:
            event_data["venue_id"] = None

        if evt.is_vip is True:
            event_data["url"] = None
            event_data["external_vip_link"] = get_override_string_value_or_default(
                evt.ticket_socket_url
            )
        else:
            event_data["url"] = get_override_string_value_or_default(
                evt.ticket_socket_url
            )
            event_data["external_vip_link"] = None

        sql = """INSERT INTO Events(SellerId,
            Title, EventDate, Thumbnail, URL, ExternalVipLink, 
            VenueId, IsHidden, Created, LastUpdate) VALUES
            (%(seller_id)s, %(title)s, %(eventDate)s,
            %(thumbnail)s, %(url)s, %(external_vip_link)s, %(venue_id)s, 1,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
        event_id = db_insert(sql, event_data, cnx)
        event_success = event_id > 0
        if event_success:
            event_success = (
                TicketPartnerService().ensure_event(event_id, 2, event_data["id"], cnx)
                > 0
            )

        return event_success

    def get_tours_from_recent_events(self):
        """
        Fetches recent tours based on events
        """
        recent_tours: list[Tour] = []

        sql = """SELECT
                    p.PageOrder,
                    ee.SellerId,
                    p.Route AS PageRoute,
                    p.LinkPreviewImage AS CoverImage
                FROM EventDetails ee
                JOIN Sellers s
                    ON s.SellerId = ee.SellerId
                AND s.SellerTypeId = 1
                JOIN PageSellers ps
                    ON ps.SellerId = ee.SellerId
                JOIN Pages p
                    ON p.PageId = ps.PageId
                AND p.PageTypeID = 7
                WHERE ee.EventDate >= CURDATE()
                AND ps.IsPrimary = 1
                AND COALESCE(p.LinkPreviewImage, '') != ''
                GROUP BY
                    p.PageOrder,
                    ee.SellerId,
                    p.Route
                ORDER BY p.PageOrder, MIN(ee.EventDate) ASC
                LIMIT 21;"""

        sql = sql.replace("\n", "")

        rows = db_query_all(sql)
        for row in rows:
            seller_id = get_override_int_value_or_default(row["SellerId"])
            seller = Seller(seller_id)
            sellers: list[Seller] = []
            sellers.append(seller)

            tour = Tour()
            tour.sellers = sellers
            tour.cover_image = get_override_string_value_or_default(row["CoverImage"])
            tour.href = get_override_string_value_or_default(row["PageRoute"])
            recent_tours.append(tour)

        return recent_tours

    def get_location_from_event(self, evt: VipEvent) -> str:
        """
        Returns a string location including venue name from a VipEvent object
        """
        if evt is None or evt.venue is None:
            return None

        venue = evt.venue
        location = f"{venue.name}, {venue.city}"
        if venue.state is not None:
            location += f", {venue.state}"

        if (
            venue.country is not None
            and venue.country.country_name is not None
            and venue.country.country_id != DEFAULT_COUNTRY_ID
        ):
            location += f", {venue.country.country_name}"

        return location
