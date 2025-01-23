"""
Tour service module
"""

from datetime import datetime
from common.event_service import EventService
from common.models.national_acts import Seller, Tour, VipEvent
from common.db import db_delete, db_insert, db_query_all, db_update


class TourService:
    """
    Service to handle all tour-related activity
    """

    def get_all_tours(self, seller_id: int, start: int = None, end: int = None):
        """
        API method to fetch all tours
        """
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
        elif end is not None:
            where_clause.append(
                "Tour.AnnounceDate BETWEEN %(startDate)s AND %(endDate)s"
            )
            data["startDate"] = datetime.now().strftime("%Y-%m-%d")
            data["endDate"] = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
        elif start is not None:
            where_clause.append("Tour.AnnounceDate >= %(startDate)s")
            data["startDate"] = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
        if len(where_clause) > 0:
            sql += " AND ".join(where_clause)

        sql += """ ORDER BY Tour.AnnounceDate ASC, Tour.TourName ASC"""

        rows = db_query_all(sql, data)
        for row in rows:
            tour = Tour()
            tour_id = int(row["TourId"])
            tour.tour_id = tour_id
            tour.tour_name = str(row["TourName"])
            tour.is_active = True if int(row["IsActive"]) == 1 else False
            tour.announce_date = str(row["AnnounceDate"])

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
            seller_id = int(row["SellerId"])
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
            ts_event_id = (
                int(row["TicketSocketEventId"])
                if row["TicketSocketEventId"] is not None
                else None
            )
            ex_event_id = (
                int(row["ExternalEventId"])
                if row["ExternalEventId"] is not None
                else None
            )
            if ts_event_id is not None:
                evts = event_service.get_events_and_orders(
                    ts_event_id=ts_event_id, ignore_flags=True, exclude_external=True
                )
                if len(evts) > 0:
                    evt = evts[0]
            elif ex_event_id is not None:
                evt = event_service.get_external_event_by_id(ex_event_id)
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
            "tourName": tour_to_add.tour_name,
            "announceDate": tour_to_add.announce_date,
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
                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                    WHERE TourId=%(tourId)s"""
        data = {
            "tourName": tour_to_update.tour_name,
            "isActive": 1 if tour_to_update.is_active is True else 0,
            "announceDate": tour_to_update.announce_date,
            "tourId": tour_to_update.tour_id,
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
                (TourId, TicketSocketEventId, ExternalEventId)
                VALUES(%(tourId)s, %(ticketSocketEventId)s, %(externalEventId)s)"""
            event_data = {
                "tourId": tour_id,
                "ticketSocketEventId": (
                    event.ticket_socket_event_id if event.is_external is False else None
                ),
                "externalEventId": (
                    event.event_id if event.is_external is True else None
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
                "tourId": tour_id,
                "sellerId": seller.seller_id,
            }
            tour_seller_id = db_insert(seller_sql, seller_data)
            success = tour_seller_id > 0
            if success is not True:
                break
        return success
