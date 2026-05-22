"""
Tour service module
"""

from datetime import datetime
import pytz
from common.event_service import EventService
from common.models.national_acts import Seller, Tour, VipEvent
from common.db import db_delete, db_insert, db_query_all, db_update
from common.utility import (
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
)


class TourService:
    """
    Service to handle all tour-related activity
    """

    def get_all_tours(self, seller_id: int, start: int = None, end: int = None):
        """
        API method to fetch all tours
        """
        pacific_tz = pytz.timezone("America/Los_Angeles")
        tours: list[Tour] = []
        sql = """SELECT Tour.*
                    FROM Tour 
                    WHERE EXISTS (SELECT 1 FROM TourSeller WHERE
                        TourId=Tour.TourId and SellerId=%(seller_id)s)"""
        data = {"seller_id": seller_id}

        where_clause: list[str] = []

        if start is not None and end is not None:
            where_clause.append(
                "Tour.AnnounceDate BETWEEN %(startDate)s AND %(endDate)s"
            )
            data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
        elif end is not None and end > datetime.now(pacific_tz).timestamp():
            where_clause.append(
                "Tour.AnnounceDate BETWEEN %(startDate)s AND %(endDate)s"
            )
            data["startDate"] = datetime.now(pacific_tz).strftime("%Y-%m-%d")
            data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
        elif start is not None:
            where_clause.append("Tour.AnnounceDate >= %(startDate)s")
            data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
        if len(where_clause) > 0:
            sql += " AND " + " AND ".join(where_clause)

        sql += """ ORDER BY Tour.AnnounceDate ASC, Tour.TourName ASC"""

        rows = db_query_all(sql, data)
        for row in rows:
            tour = Tour()
            tour_id = get_override_int_value_or_default(row["TourId"])
            tour.tour_id = tour_id
            tour.tour_name = get_override_string_value_or_default(row["TourName"])
            tour.is_active = get_override_bool_value_or_default(row["IsActive"])
            tour.announce_date = get_override_string_value_or_default(
                row["AnnounceDate"]
            )

            sellers = self.__get_sellers_by_tour_id(tour_id)
            tour.sellers = sellers

            events = self.__get_events_by_tour_id(tour_id)
            tour.events = events

            tours.append(tour)
        return tours

    def __get_sellers_by_tour_id(self, tour_id: int):
        """
        Fetches all sellers by tour id
        """
        sellers: list[Seller] = []

        sql = """SELECT DISTINCT TourSeller.SellerId
                    FROM TourSeller 
                    WHERE TourId=%(tourId)s"""
        data = {"tourId": tour_id}
        rows = db_query_all(sql, data)
        for row in rows:
            seller_id = get_override_int_value_or_default(row["SellerId"])
            seller: Seller = Seller(seller_id)

            if seller is not None:
                sellers.append(seller)
        return sellers

    def __get_events_by_tour_id(self, tour_id: int):
        """
        Fetches all events by tour id
        """
        events: list[VipEvent] = []
        event_service = EventService()
        sql = """SELECT TourEvent.*
                    FROM TourEvent 
                    WHERE TourId=%(tourId)s"""
        data = {"tourId": tour_id}
        rows = db_query_all(sql, data)
        for row in rows:
            evt: VipEvent = None
            event_id = get_override_int_value_or_default(row["ExternalEventId"])
            if event_id is not None and event_id > 0:
                evts = event_service.get_events_and_orders(
                    event_id=event_id,
                    ignore_flags=True,
                    exclude_external=False,
                    get_orders=False,
                    is_portal=True,
                )
                if len(evts) > 0:
                    evt = evts[0]
            if evt is not None:
                events.append(evt)
        return events

    def add_tour(self, tour_to_add: Tour):
        """
        Add a new tour
        """
        success: bool = True
        sql = """INSERT INTO Tour (TourName, AnnounceDate)
                VALUES(%(tourName)s, %(announceDate)s)"""
        data = {
            "tourName": get_override_string_value_or_default(tour_to_add.tour_name),
            "announceDate": get_override_string_value_or_default(
                tour_to_add.announce_date
            ),
        }
        tour_id = db_insert(sql, data)
        if tour_id > 0:
            success = self.__update_tour_sellers(tour_id, tour_to_add.sellers)
            if success is True:
                success = self.__update_tour_events(tour_id, tour_to_add.events)
        else:
            success = False
        return success

    def update_tour(self, tour_to_update: Tour):
        """
        Update an existing tour
        """
        success: bool = True
        sql = """UPDATE Tour
                    SET TourName=%(tourName)s, 
                    IsActive=%(isActive)s, 
                    AnnounceDate=%(announceDate)s, 
                    LastUpdate=CURRENT_TIMESTAMP 
                    WHERE TourId=%(tourId)s"""
        data = {
            "tourName": get_override_string_value_or_default(tour_to_update.tour_name),
            "isActive": get_override_tinyint_value_or_default_from_bool(
                tour_to_update.is_active
            ),
            "announceDate": get_override_string_value_or_default(
                tour_to_update.announce_date
            ),
            "tourId": get_override_int_value_or_default(tour_to_update.tour_id),
        }
        success = db_update(sql, data)
        if success is True:
            success = self.__update_tour_sellers(
                tour_to_update.tour_id, tour_to_update.sellers
            )
            if success is True:
                success = self.__update_tour_events(
                    tour_to_update.tour_id, tour_to_update.events
                )

        return success

    def __update_tour_events(self, tour_id: int, events: list[VipEvent]):
        """
        Add/replace events for a tour
        """
        success: bool = True
        delete_sql = """DELETE FROM TourEvent
                 WHERE TourId=%(tourId)s"""
        delete_data = {"tourId": tour_id}
        db_delete(delete_sql, delete_data)
        for event in events:
            event_sql = """INSERT INTO TourEvent
                (TourId, ExternalEventId)
                VALUES(%(tourId)s, %(externalEventId)s)"""
            event_data = {
                "tourId": get_override_int_value_or_default(tour_id),
                "externalEventId": get_override_int_value_or_default(
                    event.external_event_id
                ),
            }
            tour_event_id = db_insert(event_sql, event_data)
            success = tour_event_id > 0
            if success is not True:
                break
        return success

    def __update_tour_sellers(self, tour_id: int, sellers: list[Seller]):
        """
        Add/replace events for a tour
        """
        success: bool = True
        delete_sql = """DELETE FROM TourSeller
                 WHERE TourId=%(tourId)s"""
        delete_data = {"tourId": tour_id}
        db_delete(delete_sql, delete_data)
        for seller in sellers:
            seller_sql = """INSERT INTO TourSeller
                (TourId, SellerId)
                VALUES(%(tourId)s, %(sellerId)s)"""
            seller_data = {
                "tourId": get_override_int_value_or_default(tour_id),
                "sellerId": get_override_int_value_or_default(seller.seller_id),
            }
            tour_seller_id = db_insert(seller_sql, seller_data)
            success = tour_seller_id > 0
            if success is not True:
                break
        return success
