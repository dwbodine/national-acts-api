"""
Tour service module
"""

from common.event_service import EventService
from common.models.national_acts import Tour, VipEvent
from common.db import db_delete, db_insert, db_query_all, db_update


class TourService:
    """
    Service to handle all tour-related activity
    """

    def get_all_tours(self):
        """
        API method to fetch all tours
        """
        tours: list[Tour] = []
        sql = """SELECT SellerTour.*, Sellers.Name AS SellerName
                    FROM SellerTour
                    JOIN Sellers on Sellers.SellerId = SellerTour.SellerId
                    ORDER BY Sellers.Name ASC, SellerTour.StartDate ASC"""

        rows = db_query_all(sql)
        for row in rows:
            tour = Tour()
            tour_id = int(row["SellerTourId"])
            tour.tour_id = tour_id
            tour.seller_id = int(row["SellerId"])
            tour.seller_name = str(row["SellerName"])
            tour.tour_name = str(row["TourName"])
            tour.is_active = True if int(row["IsActive"]) == 1 else False
            tour.start_date = str(row["StartDate"])
            tour.end_date = str(row["EndDate"])
            events = self.__get_events_by_tour_id(tour_id)
            tour.events = events
            tours.append(tour)
        return tours

    def __get_events_by_tour_id(self, tour_id: int):
        """
        Fetches all events by tour id
        """
        events: list[VipEvent] = []
        event_service = EventService()
        sql = """SELECT SellerTourEvent.*
                    FROM SellerTourEvent WHERE
                    SellerTourId=%(sellerTourId)s"""
        data = {"sellerTourId": tour_id}
        rows = db_query_all(sql, data)
        for row in rows:
            event: VipEvent = None
            if row["TicketSocketEventId"] is not None:
                event = event_service.get_events_and_orders(
                    ts_event_id=int(row["TicketSocketEventId"]),
                    ignore_flags=True,
                    get_orders=True,
                )
            elif row["ExternalEventId"] is not None:
                event = event_service.get_external_event_by_id(
                    int(row["ExternalEventId"])
                )
            if event is not None:
                events.append(event)
        return events

    def add_tour(self, tour_to_add: Tour):
        """
        Add a new tour
        """
        success: bool = True
        sql = """INSERT INTO SellerTour (SellerId, TourName, StartDate, EndDate)
                VALUES(%(sellerId)s, %(tourName)s, %(startDate)s, %(endDate)s)"""
        data = {
            "sellerId": tour_to_add.seller_id,
            "tourName": tour_to_add.tour_name,
            "startDate": tour_to_add.start_date,
            "endDate": tour_to_add.end_date,
        }
        tour_id = db_insert(sql, data)
        if tour_id > 0:
            success = self.__add_tour_events(tour_id, tour_to_add.events)
        else:
            success = False
        return success

    def update_tour(self, tour_to_update: Tour):
        """
        Update an existing tour
        """
        success: bool = True
        sql = """UPDATE SellerTour
                    SET SellerId=%(sellerId)s, 
                    TourName=%(tourName)s, 
                    IsActive=%(isActive)s, 
                    StartDate=%(startDate)s, 
                    EndDate=%(endDate)s, 
                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                    WHERE SellerTourId=%(tourId)s"""
        data = {
            "sellerId": tour_to_update.seller_id,
            "tourName": tour_to_update.tour_name,
            "isActive": 1 if tour_to_update.is_active is True else 0,
            "startDate": tour_to_update.start_date,
            "endDate": tour_to_update.end_date,
            "tourId": tour_to_update.tour_id,
        }
        success = db_update(sql, data)
        if success is True:
            delete_sql = """DELETE FROM SellerTourEvent 
                WHERE SellerTourId=%(tourId)s"""
            delete_data = {"tourId": tour_to_update.tour_id}
            success = db_delete(delete_sql, delete_data)
            success = self.__add_tour_events(
                tour_to_update.tour_id, tour_to_update.events
            )

        return success

    def __add_tour_events(self, tour_id: int, events: list[VipEvent]):
        """
        Add/replace events for a tour
        """
        success: bool = True
        for event in events:
            event_sql = """INSERT INTO SellerTourEvent
                (SellerTourId, TicketSocketEventId, ExternalEventId)
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

    def delete_tour(self, tour_id: int):
        """
        Delete an existing tour
        """
        success: bool = True
        data = {"tourId": tour_id}
        delete_event_sql = """DELETE FROM SellerTourEvent
            WHERE SellerTourId=%(tourId)s"""
        success = db_delete(delete_event_sql, data)
        if success is True:
            delete_tour_sql = """"DELETE FROM SellerTour
            WHERE SellerTourId=%(tourId)s"""
            success = db_delete(delete_tour_sql, data)
        return success
