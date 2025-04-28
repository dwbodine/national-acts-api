"""
Data Refresh Service
"""

import time
from datetime import datetime
import traceback

from common.db import (
    db_query_all,
    db_query_one,
    db_update,
    db_insert,
    db_get_connection,
    db_delete,
)
from common.utility import log_message, convert_to_json, send_email
from common.ticket_socket_service import TicketSocketService
from common.models.national_acts import (
    VipEvent,
    VipOrder,
    Seller,
    SellerEventCategory,
    TicketSocketRefreshHistory,
)
from common.user_service import UserService


class DataRefreshService:
    """
    Service to handle all event-related activity
    """

    def retrieve_ticket_socket_events_for_update(
        self, seller_id: int = None, start: int = None, end: int = None
    ):
        """
        Call TS API to retrieve updated event/order/ticket/ticket type data
        """
        # go get seller information from database
        seller: Seller = None

        if seller_id is not None:
            seller = Seller(seller_id)

        # fetch TS data
        ts_sql = "SELECT TicketSocketId, IsVip FROM TicketSocket"
        rows = db_query_all(ts_sql)

        # query events across all TS services
        all_events: list[VipEvent] = []
        for row in rows:
            ticket_socket_id = int(row["TicketSocketId"])
            is_vip_service = int(row["IsVip"]) == 1
            tss = TicketSocketService(ticket_socket_id)

            # get event category for this TS account, if the seller has one
            event_category_id: int = None
            seller_event_category: SellerEventCategory = None
            if seller is not None:
                seller_event_category = seller.get_seller_event_category(
                    ticket_socket_id
                )

                # if we are restricting by seller and the seller doesn't have
                # a category on this TS service, just skip it or the service will
                # return everything for everyone in the time period
                if seller_event_category is not None:
                    event_category_id = seller_event_category.event_category_id
                else:
                    continue

            events = tss.get_events_and_orders(event_category_id, start, end)

            if len(events) > 0:
                for event in events:
                    # convert ts events to vip events
                    vip_event = VipEvent()
                    vip_event.__dict__.update(event.__dict__)
                    vip_event.is_vip = is_vip_service

                    # populate sellerEventCategoryId, which is required on our end
                    if seller_event_category is not None:
                        vip_event.seller_id = seller_event_category.seller_id
                        vip_event.seller_event_category_id = (
                            seller_event_category.seller_event_category_id
                        )
                    elif vip_event.event_category_id is not None:
                        seller_ec_temp = SellerEventCategory(
                            None, ticket_socket_id, vip_event.event_category_id
                        )
                        vip_event.seller_id = seller_ec_temp.seller_id
                        vip_event.seller_event_category_id = (
                            seller_ec_temp.seller_event_category_id
                        )

                    # if this combo of TS and category does not exist on our side,
                    # we can't update this event
                    if vip_event.seller_event_category_id is None:
                        continue

                    # convert the orders
                    orders: list[VipEvent] = []
                    for order in event.orders:
                        vip_order = VipOrder()
                        vip_order.__dict__.update(order.__dict__)
                        orders.append(vip_order)

                    vip_event.orders = orders

                    all_events.append(vip_event)

        return all_events

    def refresh_database_from_ticket_socket(
        self,
        seller_id: int = None,
        start: int = None,
        end: int = None,
        user_id: int = 0,
    ):
        """
        Calls out to TS and refreshes objects in database
        """
        # log_message('starting TS update')
        update_success: bool = True
        error_message: str = None

        # initialize counters
        start_timer: float = time.time()
        end_timer: float = 0
        duration: float = 0

        service_events_skipped: list[str] = []
        events_failed: list[int] = []
        orders_failed: list[int] = []
        ticket_types_failed: list[int] = []
        tickets_failed: list[int] = []
        total_events_from_service: int = 0
        events_updated: int = 0
        events_inserted: int = 0
        orders_inserted: int = 0
        orders_updated: int = 0
        orders_deleted: int = 0
        tickets_updated: int = 0
        tickets_inserted: int = 0
        ticket_types_updated: int = 0
        ticket_types_inserted: int = 0
        daily_order_data_rows_removed: int = 0
        results: TicketSocketRefreshHistory = None

        try:
            # log_message("retrieving events from TicketSocket Service")
            all_events = self.retrieve_ticket_socket_events_for_update(
                seller_id, start, end
            )
            # log_message('events retrieved')

            # service_timer = time.time()
            # service_duration = service_timer - start_timer
            # log_message("Service fetch done in " + str(service_duration) + " seconds")

            # get total number of events grabbed from service
            total_events_from_service = len(all_events)

            # log_message("starting database update - opening connection")
            # get one database connection
            cnx = db_get_connection()

            if total_events_from_service > 0:

                service_events: list[int] = []
                for evt in all_events:
                    if evt.seller_event_category_id <= 0:
                        service_events_skipped.append(
                            evt.title
                            + " - eventId "
                            + str(evt.event_id)
                            + " ("
                            + evt.ticket_socket_url
                            + ")"
                        )
                        continue

                    service_events.append(evt.event_id)
                    # compile event data for update
                    address = evt.venue.address1

                    event_data = {
                        "title": evt.title.strip(),
                        "eventDate": evt.event_date.strip(),
                        "url": evt.ticket_socket_url.strip(),
                        "venue": evt.venue.name.strip(),
                        "address": address.strip(),
                        "city": evt.venue.city.strip(),
                        "state": evt.venue.state.strip(),
                        "zip": evt.venue.postal_code.strip(),
                        "country": (
                            evt.venue.country.strip()
                            if evt.venue.country is not None
                            else None
                        ),
                        "thumbnail": (
                            evt.thumbnail.strip() if evt.thumbnail is not None else None
                        ),
                        "displayDate": (
                            evt.display_date.strip()
                            if evt.display_date is not None
                            else None
                        ),
                        "isVip": 1 if evt.is_vip else 0,
                    }

                    # determine if event already exists
                    event_sql = """SELECT * FROM TicketSocketEvents
                                    WHERE EventId=%(event_id)s
                                    AND SellerEventCategoryId=%(sellerEventCategoryId)s"""

                    data = {
                        "event_id": evt.event_id,
                        "sellerEventCategoryId": evt.seller_event_category_id,
                    }

                    existing_event = db_query_one(event_sql, data, cnx)

                    event_success: bool = False
                    ticket_socket_event_id: int = 0
                    event_add_new: bool = False

                    if existing_event:
                        # update existing event
                        ticket_socket_event_id = int(existing_event["Id"])
                        event_data["id"] = ticket_socket_event_id
                        sql = """UPDATE TicketSocketEvents SET Title=%(title)s,
                                EventDate=%(eventDate)s, URL=%(url)s,
                                Venue=%(venue)s, Address=%(address)s, City=%(city)s,
                                State=%(state)s, Zip=%(zip)s, Country=%(country)s,
                                Thumbnail=%(thumbnail)s,
                                DisplayDate=%(displayDate)s, IsVip=%(isVip)s,
                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                WHERE Id=%(id)s"""
                        event_success = db_update(sql, event_data, cnx)
                    else:
                        event_add_new = True
                        # insert new event
                        event_data["event_id"] = int(evt.event_id)
                        event_data["sellerEventCategoryId"] = int(
                            evt.seller_event_category_id
                        )
                        sql = """INSERT INTO TicketSocketEvents (SellerEventCategoryId,
                                    EventId, Title, EventDate, URL, Venue, Address,
                                    City, State, Zip, Country, 
                                    Thumbnail, DisplayDate, IsVip, Created, LastUpdate) 
                                    VALUES (%(sellerEventCategoryId)s, %(event_id)s, %(title)s,
                                    %(eventDate)s, %(url)s, %(venue)s, %(address)s,
                                    %(city)s, %(state)s, %(zip)s, %(country)s, 
                                    %(thumbnail)s, %(displayDate)s, %(isVip)s,
                                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                        ticket_socket_event_id = db_insert(sql, event_data, cnx)
                        event_success = ticket_socket_event_id > 0

                        # automatically add new events to external events table
                        if event_success is True:
                            event_data["seller_id"] = int(evt.seller_id)
                            event_data["id"] = ticket_socket_event_id

                            if evt.is_vip is True:
                                event_data["url"] = None
                                event_data["external_vip_link"] = (
                                    evt.ticket_socket_url.strip()
                                )
                            else:
                                event_data["url"] = evt.ticket_socket_url.strip()
                                event_data["external_vip_link"] = None

                            sql = """INSERT INTO ExternalEvents(TicketSocketEventId, SellerId,
                                Title, EventDate, Thumbnail, URL, ExternalVipLink, Created,
                                LastUpdate) VALUES (%(id)s, %(seller_id)s, %(title)s,
                                %(eventDate)s, %(thumbnail)s, %(url)s, %(external_vip_link)s,
                                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                            external_event_id = db_insert(sql, event_data, cnx)
                            event_success = external_event_id > 0

                    # if the update succeeded, update counters
                    if event_success:
                        if event_add_new:
                            events_inserted += 1
                        else:
                            events_updated += 1
                    else:
                        # if that failed, just mark it failed and skip orders
                        events_failed.append(evt.event_id)
                        update_success = False
                        continue

                    if ticket_socket_event_id and len(evt.ticket_types) > 0:
                        event_ticket_types: list[int] = []
                        for ticket_type in evt.ticket_types:
                            event_ticket_types.append(ticket_type.ticket_type_id)

                            ticket_type_data = {
                                "ticketSocketTicketTypeId": ticket_type.ticket_type_id,
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "ticketTypeName": ticket_type.ticket_type_name,
                                "totalAvailable": ticket_type.total_available,
                                "is_active": 1 if ticket_type.is_active else 0,
                            }

                            ticket_type_sql = """SELECT
                                    TicketSocketTicketTypes.*
                                    FROM TicketSocketTicketTypes 
                                    WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                    AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                            ticket_type_sql_data = {
                                "ticketSocketTicketTypeId": ticket_type.ticket_type_id,
                                "ticket_socket_event_id": ticket_socket_event_id,
                            }

                            existing_ticket_type = db_query_one(
                                ticket_type_sql, ticket_type_sql_data, cnx
                            )

                            ticket_type_success: bool = False
                            ticket_socket_type_id: int = 0
                            ticket_type_add_new: bool = False

                            if existing_ticket_type:
                                # update existing ticket type
                                sql = """UPDATE TicketSocketTicketTypes
                                        SET TicketTypeName=%(ticketTypeName)s,
                                        TotalAvailable=%(totalAvailable)s,
                                        IsActive=%(is_active)s, 
                                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                                        WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                        AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                                ticket_type_success = db_update(
                                    sql, ticket_type_data, cnx
                                )
                            else:
                                ticket_type_add_new = True
                                # insert new ticket type
                                sql = """INSERT INTO TicketSocketTicketTypes
                                        (TicketSocketTicketTypeId, TicketSocketEventId,
                                            TicketTypeName, TotalAvailable, IsActive, LastUpdate)
                                                VALUES (%(ticketSocketTicketTypeId)s,
                                                %(ticket_socket_event_id)s, %(ticketTypeName)s,
                                                %(totalAvailable)s, %(is_active)s,
                                                CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                                ticket_socket_type_id = db_insert(
                                    sql, ticket_type_data, cnx
                                )
                                ticket_type_success = ticket_socket_type_id > 0

                            # if the update succeeded, update counters
                            if ticket_type_success:
                                if ticket_type_add_new:
                                    ticket_types_inserted += 1
                                else:
                                    ticket_types_updated += 1
                            else:
                                # if that failed, mark it
                                ticket_types_failed.append(ticket_type.ticket_type_id)

                    if ticket_socket_event_id and len(evt.orders) > 0:
                        event_orders: list[int] = []
                        for order in evt.orders:
                            if order.event_id != evt.event_id:
                                continue
                            event_orders.append(order.order_id)
                            # compile order data for update

                            order_data = {
                                "purchaseDate": order.purchase_date.strip(),
                                "purchaseTimestamp": order.purchase_timestamp.strip(),
                                "phone": (
                                    order.phone.strip()
                                    if order.phone is not None
                                    else None
                                ),
                                "user_id": order.user_id,
                                "event_id": order.event_id,
                                "purchaserLastName": (
                                    order.purchaser_last_name.strip()
                                    if order.purchaser_last_name is not None
                                    else None
                                ),
                                "purchaserFirstName": (
                                    order.purchaser_first_name.strip()
                                    if order.purchaser_first_name is not None
                                    else None
                                ),
                                "purchaserCity": (
                                    order.purchaser_city.strip()
                                    if (
                                        order.purchaser_city is not None
                                        and order.purchaser_city != ""
                                    )
                                    else None
                                ),
                                "purchaserState": (
                                    order.purchaser_state.strip()
                                    if (
                                        order.purchaser_state is not None
                                        and order.purchaser_state != ""
                                    )
                                    else None
                                ),
                                "purchaserZip": (
                                    order.purchaser_zip_code.strip()
                                    if (
                                        order.purchaser_zip_code is not None
                                        and order.purchaser_zip_code != ""
                                    )
                                    else None
                                ),
                                "purchaserCountry": (
                                    order.purchaser_country.strip()
                                    if (
                                        order.purchaser_country is not None
                                        and order.purchaser_country != ""
                                    )
                                    else None
                                ),
                                "purchaserIpAddress": (
                                    order.purchaser_ip_address.strip()
                                    if (
                                        order.purchaser_ip_address is not None
                                        and order.purchaser_ip_address != ""
                                    )
                                    else None
                                ),
                                "email": (
                                    order.email.strip()
                                    if order.email is not None
                                    else None
                                ),
                            }

                            # determine if order already exists
                            order_sql = """SELECT TicketSocketOrders.*
                                            FROM TicketSocketOrders
                                            WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                            AND OrderId=%(order_id)s"""

                            data = {
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "order_id": order.order_id,
                            }

                            existing_order = db_query_one(order_sql, data, cnx)

                            order_success: bool = False
                            ticket_socket_order_id: int = 0
                            order_add_new: bool = False

                            if existing_order:
                                ticket_socket_order_id = int(existing_order["Id"])
                                order_data["id"] = ticket_socket_order_id
                                # if purchase date changed, clear out daily order data for event
                                order_purchase_timestamp = datetime.strptime(
                                    order.purchase_date, "%Y-%m-%d"
                                ).timestamp()
                                existing_purchase_timestamp = datetime.strptime(
                                    str(existing_order["PurchaseDate"]), "%Y-%m-%d"
                                ).timestamp()
                                if (
                                    order_purchase_timestamp
                                    != existing_purchase_timestamp
                                ):
                                    check_cleanup_data = {
                                        "ticket_socket_event_id": ticket_socket_event_id,
                                        "purchaseDate": str(
                                            existing_order["PurchaseDate"]
                                        ),
                                    }
                                    check_cleanup_sql = """SELECT DailyOrderData.DailyOrderDataId
                                            FROM DailyOrderData
                                            WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                            AND PurchaseDate=DATE(%(purchaseDate)s)"""
                                    rows = db_query_all(
                                        check_cleanup_sql, check_cleanup_data
                                    )
                                    if len(rows) > 0:
                                        for row in rows:
                                            cleanup_sql = """DELETE FROM DailyOrderData
                                                    WHERE DailyOrderDataId=%(dailyOrderDataId)s"""
                                            cleanup_data = {
                                                "dailyOrderDataId": int(
                                                    row["DailyOrderDataId"]
                                                )
                                            }
                                            del_success = db_delete(
                                                cleanup_sql, cleanup_data
                                            )
                                            if del_success is True:
                                                daily_order_data_rows_removed += 1

                                # update existing order
                                sql = """UPDATE TicketSocketOrders
                                        SET PurchaseDate=%(purchaseDate)s,
                                        PurchaseTimestamp=%(purchaseTimestamp)s,
                                        Phone=%(phone)s, EventId=%(event_id)s,
                                        UserId=%(user_id)s, PurchaserLastName=%(purchaserLastName)s,
                                        PurchaserFirstName=%(purchaserFirstName)s, PurchaserCity=%(purchaserCity)s, 
                                        PurchaserState=%(purchaserState)s, PurchaserZip=%(purchaserZip)s,
                                        PurchaserCountry=%(purchaserCountry)s,
                                        PurchaserIpAddress=%(purchaserIpAddress)s, Email=%(email)s,
                                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                        WHERE Id=%(id)s"""

                                order_success = db_update(sql, order_data, cnx)
                            else:
                                order_add_new = True
                                # insert new order
                                order_data["order_id"] = int(order.order_id)
                                order_data["ticket_socket_event_id"] = (
                                    ticket_socket_event_id
                                )
                                sql = """INSERT INTO TicketSocketOrders
                                            (TicketSocketEventId, OrderId,
                                            PurchaseDate, PurchaseTimestamp, Phone, EventId, UserId,
                                            PurchaserLastName, PurchaserFirstName, PurchaserCity, PurchaserState,
                                            PurchaserZip, PurchaserCountry,
                                            PurchaserIpAddress, Email, LastUpdate) VALUES
                                    (%(ticket_socket_event_id)s, %(order_id)s,
                                    %(purchaseDate)s, %(purchaseTimestamp)s, %(phone)s,
                                    %(event_id)s, %(user_id)s, %(purchaserLastName)s, %(purchaserFirstName)s,
                                    %(purchaserCity)s, %(purchaserState)s, %(purchaserZip)s, %(purchaserCountry)s,
                                    %(purchaserIpAddress)s,  %(email)s,
                                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

                                ticket_socket_order_id = db_insert(sql, order_data, cnx)
                                order_success = ticket_socket_order_id > 0

                            # if the update succeeded, update counters
                            if order_success:
                                if order_add_new:
                                    orders_inserted += 1
                                else:
                                    orders_updated += 1
                            else:
                                # if that failed, just mark it failed and skip orders
                                orders_failed.append(order.order_id)
                                update_success = False
                                continue

                            if ticket_socket_order_id and len(order.tickets) > 0:
                                order_tickets: list[int] = []

                                # clean up any migrated data that doesn't have ticket Ids
                                delete_sql = """DELETE FROM TicketSocketOrderTickets
                                            WHERE TicketSocketOrderId=%(ticket_socket_order_id)s
                                            AND TicketId IS NULL"""
                                delete_data = {
                                    "ticket_socket_order_id": ticket_socket_order_id
                                }
                                db_delete(delete_sql, delete_data)

                                for ticket in order.tickets:
                                    order_tickets.append(ticket.ticket_id)
                                    # compile ticket data for update
                                    ticket_data = {
                                        "ticket_type": ticket.ticket_type.strip(),
                                        "ticket_type_id": ticket.ticket_type_id,
                                        "serviceFee": (
                                            ticket.service_fee
                                            if ticket.service_fee is not None
                                            else 0
                                        ),
                                        "availableScans": ticket.available_scans,
                                        "barcode": ticket.barcode,
                                        "purchaseLocation": ticket.purchase_location,
                                        "scannedTimestamp": ticket.scanned_timestamp,
                                        "attendeeFirstName": ticket.attendee_first_name,
                                        "attendeeLastName": ticket.attendee_last_name,
                                        "shirtSize": (
                                            ticket.shirt_size
                                            if ticket.shirt_size is not None
                                            and len(ticket.shirt_size) > 0
                                            else None
                                        ),
                                    }

                                    ticket_price = (
                                        ticket.price if ticket.price is not None else 0
                                    )

                                    if ticket_price > 0:
                                        ticket_data["price"] = ticket_price

                                    # determine if ticket already exists
                                    ticket_sql = """SELECT TicketSocketOrderTickets.*
                                        FROM TicketSocketOrderTickets
                                        WHERE TicketSocketOrderId=%(ticket_socket_order_id)s
                                        AND TicketId=%(ticketId)s"""

                                    data = {
                                        "ticket_socket_order_id": ticket_socket_order_id,
                                        "ticketId": ticket.ticket_id,
                                    }

                                    existing_ticket = db_query_one(
                                        ticket_sql, data, cnx
                                    )

                                    ticket_success: bool = False
                                    ticket_socket_order_ticket_id: int = 0
                                    ticket_add_new: bool = False

                                    if existing_ticket:
                                        # update existing ticket
                                        ticket_socket_order_ticket_id = int(
                                            existing_ticket["Id"]
                                        )
                                        ticket_data["id"] = (
                                            ticket_socket_order_ticket_id
                                        )

                                        sql = """UPDATE TicketSocketOrderTickets
                                                SET TicketType=%(ticket_type)s,
                                                TicketSocketTicketTypeId=%(ticket_type_id)s,
                                                BarCode=%(barcode)s,
                                                AvailableScans=%(availableScans)s,
                                                PurchaseLocation=%(purchaseLocation)s, 
                                                ScannedTimestamp=%(scannedTimestamp)s,
                                                AttendeeFirstName=%(attendeeFirstName)s,
                                                AttendeeLastName=%(attendeeLastName)s,
                                                ShirtSize=%(shirtSize)s"""
                                        if ticket_price > 0:
                                            sql += ", Price=%(price)s"
                                        sql += """,
                                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                                WHERE Id=%(id)s"""
                                        ticket_success = db_update(
                                            sql, ticket_data, cnx
                                        )
                                    else:
                                        # insert new ticket
                                        ticket_add_new = True
                                        ticket_data["ticketId"] = int(ticket.ticket_id)
                                        ticket_data["ticket_socket_order_id"] = (
                                            ticket_socket_order_id
                                        )
                                        ticket_data["is_checked_in"] = (
                                            1 if ticket.scanned_timestamp != 0 else 0
                                        )
                                        sql = """INSERT INTO TicketSocketOrderTickets
                                            (TicketSocketOrderId, TicketId, TicketSocketTicketTypeId,
                                            TicketType, ServiceFee, BarCode, AvailableScans, PurchaseLocation,
                                            ScannedTimestamp, 
                                            AttendeeFirstName, AttendeeLastName, ShirtSize"""
                                        if ticket_price > 0:
                                            sql += ", Price"
                                        sql += """, LastUpdate) """
                                        sql += """VALUES (%(ticket_socket_order_id)s, %(ticketId)s,
                                            %(ticket_type_id)s, %(ticket_type)s, %(serviceFee)s, %(barcode)s,
                                            %(availableScans)s, %(purchaseLocation)s, %(scannedTimestamp)s,
                                            %(attendeeFirstName)s,
                                            %(attendeeLastName)s, %(shirtSize)s"""
                                        if ticket_price > 0:
                                            sql += ", %(price)s"
                                        sql += """,
                                            CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                                        ticket_socket_order_ticket_id = db_insert(
                                            sql, ticket_data
                                        )
                                        ticket_success = (
                                            ticket_socket_order_ticket_id > 0
                                        )

                                    # if the update succeeded, update counters
                                    if ticket_success:
                                        if ticket_add_new:
                                            tickets_inserted += 1
                                        else:
                                            tickets_updated += 1
                                    else:
                                        # if that failed, just mark it failed and skip orders
                                        tickets_failed.append(ticket.ticket_id)
                                        update_success = False
                                        continue
            else:
                update_success = True

            end_timer = time.time()
            duration = end_timer - start_timer

            # database_duration = end_timer - service_timer
            # log_message(
            #    "database update complete in " + str(database_duration) + " seconds"
            # )

            results = TicketSocketRefreshHistory(
                service_events_skipped,
                events_failed,
                orders_failed,
                tickets_failed,
                ticket_types_failed,
                total_events_from_service,
                events_updated,
                events_inserted,
                orders_inserted,
                orders_updated,
                orders_deleted,
                tickets_updated,
                tickets_inserted,
                ticket_types_updated,
                ticket_types_inserted,
                int(start_timer),
                int(end_timer),
                duration,
                user_id,
                seller_id,
                start,
                end,
                update_success,
                error_message,
            )
            if user_id is not None and user_id > 0:
                user_service = UserService()
                user = user_service.get_user_by_id(user_id)
                if user is not None:
                    results.username = user.user_full_name()
            else:
                results.username = "System"

            results.order_data_rows_removed = daily_order_data_rows_removed

            results.commit(cnx)

            if cnx is not None and cnx.is_connected:
                cnx.close()

        except Exception as error:  # pylint: disable=broad-exception-caught
            update_success = False
            error_message: str = str(error) + "\n" + traceback.format_exc()
            log_message(error_message)

        # alert dB if it failed
        if update_success is not True or (
            results is not None and results.succeeded is not True
        ):
            subject = "Error in TS Refresh - " + datetime.now().strftime(
                "%m/%d/%Y %H:%M:%S"
            )
            if results is not None:
                html = convert_to_json(results)
            else:
                html = error_message
            to = "dwbodine@gmail.com"
            to_name = "dB"
            send_email(to, subject, html, to_name)

        return results

    def get_ticket_socket_refresh_history(self):
        """
        Get history of TS refresh for admin screen
        """
        logs: list[TicketSocketRefreshHistory] = []

        sql = """SELECT TicketSocketRefreshHistory.*,
                CONCAT(Users.FirstName, ' ', Users.LastName) AS UserName,
                Users.UserName AS Email, Sellers.Name AS SellerName
                FROM TicketSocketRefreshHistory 
                LEFT JOIN Users ON Users.UserId = TicketSocketRefreshHistory.UserId
                LEFT JOIN Sellers ON Sellers.SellerId = TicketSocketRefreshHistory.SellerId
                ORDER BY TicketSocketRefreshHistory.StartTimer DESC"""

        rows = db_query_all(sql)
        for row in rows:
            user_id = int(row["UserId"])
            if user_id == 0:
                username = "System"
            else:
                username = str(row["UserName"]) + " (" + str(row["Email"]) + ")"
            seller_id = int(row["SellerId"]) if row["SellerId"] is not None else None
            seller_name = (
                str(row["SellerName"]) if row["SellerName"] is not None else None
            )
            start = int(row["Start"]) if row["Start"] is not None else None
            end = int(row["End"]) if row["End"] is not None else None
            start_timer = int(row["StartTimer"])
            end_timer = int(row["EndTimer"])
            duration = float(row["Duration"])
            succeeded = True if int(row["Success"]) == 1 else False
            error_message = str(row["ErrorMessage"])
            service_events_skipped = str(row["ServiceEventsSkipped"])
            events_failed = str(row["EventsFailed"])
            orders_failed = str(row["OrdersFailed"])
            tickets_failed = str(row["TicketsFailed"])
            ticket_types_failed = str(row["TicketTypesFailed"])
            total_events_from_service = int(row["TotalEventsFromService"])
            events_updated = int(row["EventsUpdated"])
            events_inserted = int(row["EventsInserted"])
            orders_inserted = int(row["OrdersInserted"])
            orders_updated = int(row["OrdersUpdated"])
            orders_deleted = int(row["OrdersDeleted"])
            tickets_updated = int(row["TicketsUpdated"])
            tickets_inserted = int(row["TicketsInserted"])
            ticket_types_updated = int(row["TicketTypesUpdated"])
            ticket_types_inserted = int(row["TicketTypesInserted"])
            order_data_update_succeeded = (
                True if int(row["OrderDataUpdateSucceeded"]) == 1 else False
            )
            order_data_update_duration = float(row["OrderDataUpdateDuration"])
            total_duration = float(row["TotalDuration"])
            order_data_rows_total = int(row["OrderDataRowsTotal"])
            order_data_rows_inserted = int(row["OrderDataRowsInserted"])
            order_data_rows_updated = int(row["OrderDataRowsUpdated"])
            order_data_rows_removed = int(row["OrderDataRowsRemoved"])

            history = TicketSocketRefreshHistory(
                service_events_skipped,
                events_failed,
                orders_failed,
                tickets_failed,
                ticket_types_failed,
                total_events_from_service,
                events_updated,
                events_inserted,
                orders_inserted,
                orders_updated,
                orders_deleted,
                tickets_updated,
                tickets_inserted,
                ticket_types_updated,
                ticket_types_inserted,
                start_timer,
                end_timer,
                duration,
                user_id,
                seller_id,
                start,
                end,
                succeeded,
                error_message,
            )
            history.seller_name = seller_name
            history.username = username
            history.order_data_update_succeeded = order_data_update_succeeded
            history.order_data_update_duration = order_data_update_duration
            history.order_data_rows_total = order_data_rows_total
            history.order_data_rows_updated = order_data_rows_updated
            history.order_data_rows_removed = order_data_rows_removed
            history.order_data_rows_inserted = order_data_rows_inserted
            history.total_duration = total_duration
            logs.append(history)

        return logs
