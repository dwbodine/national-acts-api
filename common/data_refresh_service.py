"""
Data Refresh Service
"""

import time
from datetime import datetime
import traceback
import phonenumbers

from common.db import (
    db_query_all,
    db_query_one,
    db_update,
    db_insert,
    db_get_connection,
    db_delete,
)
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    log_message,
    convert_to_json,
    send_email,
)
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
    Service to handle all data refreshing from TicketSocket
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
            ticket_socket_id = get_override_int_value_or_default(row["TicketSocketId"])
            is_vip_service = get_override_bool_value_or_default(row["IsVip"])
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
                        "title": get_override_string_value_or_default(evt.title),
                        "eventDate": get_override_string_value_or_default(
                            evt.event_date
                        ),
                        "url": get_override_string_value_or_default(
                            evt.ticket_socket_url
                        ),
                        "venue": get_override_string_value_or_default(evt.venue.name),
                        "address": get_override_string_value_or_default(address),
                        "city": get_override_string_value_or_default(evt.venue.city),
                        "state": get_override_string_value_or_default(evt.venue.state),
                        "zip": get_override_string_value_or_default(
                            evt.venue.postal_code
                        ),
                        "country": get_override_string_value_or_default(
                            evt.venue.country.country_name
                        ),
                        "thumbnail": get_override_string_value_or_default(
                            evt.thumbnail
                        ),
                        "isVip": get_override_tinyint_value_or_default_from_bool(
                            evt.is_vip
                        ),
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
                        ticket_socket_event_id = get_override_int_value_or_default(
                            existing_event["Id"]
                        )

                        event_data["id"] = ticket_socket_event_id
                        sql = """UPDATE TicketSocketEvents SET Title=%(title)s,
                                EventDate=%(eventDate)s, URL=%(url)s,
                                Venue=%(venue)s, Address=%(address)s, City=%(city)s,
                                State=%(state)s, Zip=%(zip)s, Country=%(country)s,
                                Thumbnail=%(thumbnail)s, IsVip=%(isVip)s,
                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                WHERE Id=%(id)s"""
                        event_success = db_update(sql, event_data, cnx)

                        # double-check date in External Events
                        ex_sql = """SELECT * FROM ExternalEvents WHERE TicketSocketEventId=%(id)s"""
                        ex_data = {"id": ticket_socket_event_id}
                        ex_row = db_query_one(ex_sql, ex_data, cnx)
                        if ex_row:
                            # this should always be the case and is just
                            # here to fix the event date if it's off
                            ex_event_date = get_override_string_value_or_default(
                                ex_row["EventDate"]
                            )
                            ex_id = get_override_int_value_or_default(ex_row["EventId"])
                            if evt.event_date != ex_event_date:
                                ex_sql2 = """UPDATE ExternalEvents SET EventDate=%(event_date)s,
                                    LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                    WHERE EventId=%(id)s"""
                                ex_data2 = {"event_date": evt.event_date, "id": ex_id}
                                event_success = db_update(ex_sql2, ex_data2, cnx)
                        else:
                            # but..if by some unforseen circumstance,
                            # there is no matching ExternalEvent then add it
                            event_data["seller_id"] = get_override_int_value_or_default(
                                evt.seller_id
                            )
                            event_data["id"] = ticket_socket_event_id
                            event_success = self.__add_to_external_events(
                                event_data, evt, cnx
                            )
                    else:
                        event_add_new = True
                        # insert new event
                        event_data["event_id"] = get_override_int_value_or_default(
                            evt.event_id
                        )
                        event_data["sellerEventCategoryId"] = (
                            get_override_int_value_or_default(
                                evt.seller_event_category_id
                            )
                        )
                        sql = """INSERT INTO TicketSocketEvents (SellerEventCategoryId,
                                    EventId, Title, EventDate, URL, Venue, Address,
                                    City, State, Zip, Country, 
                                    Thumbnail, IsVip, Created, LastUpdate) 
                                    VALUES (%(sellerEventCategoryId)s, %(event_id)s, %(title)s,
                                    %(eventDate)s, %(url)s, %(venue)s, %(address)s,
                                    %(city)s, %(state)s, %(zip)s, %(country)s, 
                                    %(thumbnail)s, %(isVip)s,
                                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
                                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                        ticket_socket_event_id = db_insert(sql, event_data, cnx)
                        event_success = ticket_socket_event_id > 0

                        # automatically add new events to external events table
                        if event_success is True:
                            event_data["seller_id"] = get_override_int_value_or_default(
                                evt.seller_id
                            )
                            event_data["id"] = ticket_socket_event_id
                            event_success = self.__add_to_external_events(
                                event_data, evt, cnx
                            )

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

                    total_tickets_available: int = 0
                    total_tickets_sold: int = 0

                    if ticket_socket_event_id and len(evt.ticket_types) > 0:
                        event_ticket_types: list[int] = []
                        for ticket_type in evt.ticket_types:
                            event_ticket_types.append(ticket_type.ticket_type_id)

                            tickets_available: int = get_override_int_value_or_default(
                                ticket_type.total_available
                            )

                            total_tickets_available += tickets_available

                            ticket_type_data = {
                                "ticketSocketTicketTypeId": get_override_int_value_or_default(
                                    ticket_type.ticket_type_id
                                ),
                                "ticket_socket_event_id": ticket_socket_event_id,
                                "ticketTypeName": get_override_string_value_or_default(
                                    ticket_type.ticket_type_name
                                ),
                                "totalAvailable": tickets_available,
                                "is_active": get_override_tinyint_value_or_default_from_bool(
                                    ticket_type.is_active
                                ),
                            }

                            ticket_type_sql = """SELECT
                                    TicketSocketTicketTypes.*
                                    FROM TicketSocketTicketTypes 
                                    WHERE TicketSocketEventId=%(ticket_socket_event_id)s
                                    AND TicketSocketTicketTypeId=%(ticketSocketTicketTypeId)s"""
                            ticket_type_sql_data = {
                                "ticketSocketTicketTypeId": get_override_int_value_or_default(
                                    ticket_type.ticket_type_id
                                ),
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
                            order_comped: bool = False
                            order_deleted: bool = False
                            order_active: bool = True

                            if order.event_id != evt.event_id:
                                continue
                            event_orders.append(order.order_id)
                            # compile order data for update

                            order_data = {
                                "purchaseDate": get_override_string_value_or_default(
                                    order.purchase_date
                                ),
                                "purchaseTimestamp": get_override_string_value_or_default(
                                    order.purchase_timestamp
                                ),
                                "user_id": get_override_string_value_or_default(
                                    order.user_id
                                ),
                                "event_id": get_override_int_value_or_default(
                                    order.event_id
                                ),
                                "purchaserLastName": get_override_string_value_or_default(
                                    order.purchaser_last_name
                                ),
                                "purchaserFirstName": get_override_string_value_or_default(
                                    order.purchaser_first_name
                                ),
                                "purchaserCity": get_override_string_value_or_default(
                                    order.purchaser_city
                                ),
                                "purchaserState": get_override_string_value_or_default(
                                    order.purchaser_state
                                ),
                                "purchaserZip": get_override_string_value_or_default(
                                    order.purchaser_zip_code
                                ),
                                "purchaserCountry": get_override_string_value_or_default(
                                    order.purchaser_country
                                ),
                                "purchaserIpAddress": get_override_string_value_or_default(
                                    order.purchaser_ip_address
                                ),
                                "email": get_override_string_value_or_default(
                                    order.email
                                ),
                            }

                            # determine if order already exists
                            order_sql = """SELECT *
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

                            # format phone before attempting to update
                            phone = get_override_string_value_or_default(order.phone)
                            phone_formatted: str = None
                            if phone is not None and len(phone) > 0:
                                try:
                                    region = (
                                        evt.venue.country.country_code
                                        if evt.venue is not None
                                        and evt.venue.country is not None
                                        else None
                                    )
                                    if region is not None:
                                        z = phonenumbers.parse(phone, region)
                                        if phonenumbers.is_possible_number(z):
                                            phone_formatted = phonenumbers.format_number(
                                                z,
                                                phonenumbers.PhoneNumberFormat.INTERNATIONAL,
                                            )
                                except (
                                    Exception  # pylint: disable=broad-exception-caught
                                ):
                                    # if phonenumbers can't format it, then never mind
                                    phone_formatted = None

                            if existing_order:
                                existing_phone_formatted = (
                                    get_override_string_value_or_default(
                                        existing_order["PhoneFormatted"]
                                    )
                                )
                                existing_phone = get_override_string_value_or_default(
                                    existing_order["Phone"]
                                )
                                if phone is not None and existing_phone != phone:
                                    order_data["phone"] = phone
                                else:
                                    order_data["phone"] = existing_phone

                                if (
                                    phone_formatted is not None
                                    and existing_phone_formatted != phone_formatted
                                ):
                                    order_data["phone_formatted"] = phone_formatted
                                else:
                                    order_data["phone_formatted"] = (
                                        existing_phone_formatted
                                    )

                                order_comped = get_override_bool_value_or_default(
                                    existing_order["IsComped"]
                                )
                                order_deleted = get_override_bool_value_or_default(
                                    existing_order["IsDeleted"]
                                )
                                order_active = get_override_bool_value_or_default(
                                    existing_order["IsActive"]
                                )

                                ticket_socket_order_id = (
                                    get_override_int_value_or_default(
                                        existing_order["Id"]
                                    )
                                )
                                order_data["id"] = ticket_socket_order_id
                                # if purchase date changed, clear out daily order data for event
                                order_purchase_timestamp = datetime.strptime(
                                    get_override_string_value_or_default(
                                        order.purchase_date
                                    ),
                                    "%Y-%m-%d",
                                ).timestamp()

                                existing_purchase_timestamp = datetime.strptime(
                                    get_override_string_value_or_default(
                                        existing_order["PurchaseDate"]
                                    ),
                                    "%Y-%m-%d",
                                ).timestamp()

                                if (
                                    order_purchase_timestamp
                                    != existing_purchase_timestamp
                                ):
                                    check_cleanup_data = {
                                        "ticket_socket_event_id": ticket_socket_event_id,
                                        "purchaseDate": get_override_string_value_or_default(
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
                                        Phone=%(phone)s, PhoneFormatted=%(phone_formatted)s,
                                        EventId=%(event_id)s,
                                        UserId=%(user_id)s, PurchaserLastName=%(purchaserLastName)s,
                                        PurchaserFirstName=%(purchaserFirstName)s, PurchaserCity=%(purchaserCity)s, 
                                        PurchaserState=%(purchaserState)s, PurchaserZip=%(purchaserZip)s,
                                        PurchaserCountry=%(purchaserCountry)s,
                                        PurchaserIpAddress=%(purchaserIpAddress)s, Email=%(email)s,
                                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                        WHERE Id=%(id)s"""

                                sql = sql.replace("\n", "")

                                order_success = db_update(sql, order_data, cnx)
                            else:
                                order_add_new = True
                                order_data["phone"] = phone
                                order_data["phone_formatted"] = phone_formatted
                                # insert new order
                                order_data["order_id"] = (
                                    get_override_int_value_or_default(order.order_id)
                                )
                                order_data["ticket_socket_event_id"] = (
                                    ticket_socket_event_id
                                )
                                sql = """INSERT INTO TicketSocketOrders
                                            (TicketSocketEventId, OrderId,
                                            PurchaseDate, PurchaseTimestamp, Phone, PhoneFormatted,
                                            EventId, UserId,
                                            PurchaserLastName, PurchaserFirstName, PurchaserCity, PurchaserState,
                                            PurchaserZip, PurchaserCountry,
                                            PurchaserIpAddress, Email, LastUpdate) VALUES
                                    (%(ticket_socket_event_id)s, %(order_id)s,
                                    %(purchaseDate)s, %(purchaseTimestamp)s, %(phone)s, %(phone_formatted)s, 
                                    %(event_id)s, %(user_id)s, %(purchaserLastName)s, %(purchaserFirstName)s,
                                    %(purchaserCity)s, %(purchaserState)s, %(purchaserZip)s, %(purchaserCountry)s,
                                    %(purchaserIpAddress)s,  %(email)s,
                                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""

                                sql = sql.replace("\n", "")

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
                                        "ticket_type": get_override_string_value_or_default(
                                            ticket.ticket_type
                                        ),
                                        "ticket_type_id": get_override_int_value_or_default(
                                            ticket.ticket_type_id
                                        ),
                                        "serviceFee": get_override_float_value_or_default(
                                            ticket.service_fee
                                        ),
                                        "availableScans": get_override_int_value_or_default(
                                            ticket.available_scans
                                        ),
                                        "barcode": get_override_string_value_or_default(
                                            ticket.barcode
                                        ),
                                        "purchaseLocation": get_override_string_value_or_default(
                                            ticket.purchase_location
                                        ),
                                        "scannedTimestamp": get_override_int_value_or_default(
                                            ticket.scanned_timestamp
                                        ),
                                        "attendeeFirstName": get_override_string_value_or_default(
                                            ticket.attendee_first_name
                                        ),
                                        "attendeeLastName": get_override_string_value_or_default(
                                            ticket.attendee_last_name
                                        ),
                                        "shirtSize": get_override_string_value_or_default(
                                            ticket.shirt_size
                                        ),
                                    }

                                    ticket_price = get_override_float_value_or_default(
                                        ticket.price
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
                                        ticket_socket_order_ticket_id = (
                                            get_override_int_value_or_default(
                                                existing_ticket["Id"]
                                            )
                                        )
                                        ticket_data["id"] = (
                                            ticket_socket_order_ticket_id
                                        )

                                        is_refunded: bool = (
                                            get_override_bool_value_or_default(
                                                existing_ticket["IsRefunded"]
                                            )
                                        )
                                        is_charged_back: bool = (
                                            get_override_bool_value_or_default(
                                                existing_ticket["IsChargedBack"]
                                            )
                                        )
                                        is_active: bool = (
                                            get_override_bool_value_or_default(
                                                existing_ticket["IsActive"]
                                            )
                                        )

                                        if (
                                            order_active is True
                                            and order_deleted is False
                                            and order_comped is False
                                            and is_active is True
                                            and is_refunded is False
                                            and is_charged_back is False
                                        ):
                                            total_tickets_sold += 1

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
                                        ticket_data["ticketId"] = (
                                            get_override_int_value_or_default(
                                                ticket.ticket_id
                                            )
                                        )
                                        ticket_data["ticket_socket_order_id"] = (
                                            ticket_socket_order_id
                                        )
                                        ticket_data["is_checked_in"] = (
                                            get_override_tinyint_value_or_default_from_bool(
                                                ticket.scanned_timestamp != 0
                                            )
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

                    if (
                        ticket_socket_event_id
                        and total_tickets_sold > 0
                        and total_tickets_available > 0
                    ):
                        is_sold_out: bool = (
                            total_tickets_sold >= total_tickets_available
                        )
                        sql = """UPDATE TicketSocketEvents SET IsSoldOut=%(sold_out)s,
                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                 WHERE Id=%(ticket_socket_event_id)s"""
                        data = {
                            "ticket_socket_event_id": ticket_socket_event_id,
                            "sold_out": get_override_tinyint_value_or_default_from_bool(
                                is_sold_out
                            ),
                        }
                        db_update(sql, data)

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

    def __add_to_external_events(
        self, event_data: dict[str, any], evt: VipEvent, cnx: any
    ):
        """
        Add a new event to external events
        """
        # try to find venue in existing data if possible
        venue_id: int = 0
        venue_sql = """SELECT VenueID FROM ExternalEventVenues
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

        sql = """INSERT INTO ExternalEvents(TicketSocketEventId, SellerId,
            Title, EventDate, Thumbnail, URL, ExternalVipLink, 
            ExternalEventVenueId, Created, LastUpdate) VALUES
            (%(id)s, %(seller_id)s, %(title)s, %(eventDate)s,
            %(thumbnail)s, %(url)s, %(external_vip_link)s, %(venue_id)s, 
            CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'),
            CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
        external_event_id = db_insert(sql, event_data, cnx)
        event_success = external_event_id > 0

        return event_success
