"""
Class for ticket orders
"""

import datetime

from common.db import db_delete, db_insert, db_query_all, db_query_one, db_update
from common.event_service import EventService
from common.models.national_acts import TicketCheckIn, TicketCheckInStatus
from common.models.ticket_order import (
    TicketOrder,
    TicketOrderAgeLimit,
    TicketOrderPriceLevel,
)
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    get_pacific_timestamp_from_utc_datetime_string,
)


class TicketOrdersService:
    """
    API methods for ticket orders
    """

    def get_ticket_orders(self, show_fulfilled: bool = None, show_paid: bool = None):
        """
        Retrieval method for ticket orders
        """
        event_service = EventService()
        orders: list[TicketOrder] = []
        sql = """SELECT TicketOrders.*,
                    TicketOrderAgeLimit.TicketOrderAgeLimitName,
                    Events.EventID
                    FROM TicketOrders
                    JOIN TicketOrderAgeLimit ON 
                        TicketOrderAgeLimit.TicketOrderAgeLimitId =
                        TicketOrders.TicketOrderAgeLimitId
                    JOIN (SELECT DISTINCT EventId FROM EventDetails) Events ON
                        Events.EventID =
                        TicketOrders.ExternalEventId
                    """
        if show_fulfilled is True and show_paid is True:
            sql += """ WHERE TicketOrders.IsFulfilled=1 AND TicketOrders.IsPaid=1"""
        elif show_fulfilled is True:
            sql += """ WHERE TicketOrders.IsFulfilled=1 AND TicketOrders.IsPaid=0"""
        elif show_fulfilled is False and show_paid is False:
            sql += """ WHERE TicketOrders.IsFulfilled=0 AND TicketOrders.IsPaid=0"""
        rows = db_query_all(sql)
        for row in rows:
            order = self.__get_order_data_from_row(row, event_service)
            if order is not None:
                orders.append(order)

        return orders

    def get_ticket_order_by_id(self, order_id: int):
        """
        Retrieve single order by id
        """

        if order_id is None or order_id == 0:
            return None

        sql = """SELECT TicketOrders.*,
                    TicketOrderAgeLimit.TicketOrderAgeLimitName,
                    Events.EventID
                    FROM TicketOrders
                    JOIN TicketOrderAgeLimit ON 
                        TicketOrderAgeLimit.TicketOrderAgeLimitId =
                        TicketOrders.TicketOrderAgeLimitId
                    JOIN (SELECT DISTINCT EventId FROM EventDetails) Events ON
                        Events.EventID =
                        TicketOrders.ExternalEventId
                    WHERE TicketOrders.TicketOrderId=%(order_id)s
                    """
        data = {"order_id": order_id}
        order: TicketOrder = None
        row = db_query_one(sql, data)
        if row:
            event_service = EventService()
            order = self.__get_order_data_from_row(row, event_service)
        return order

    def __get_order_data_from_row(self, row: dict, event_service: EventService):
        """
        Get order data from database row
        """
        order_id = get_override_int_value_or_default(row["TicketOrderId"])
        if order_id is None or order_id == 0:
            return None

        order = TicketOrder()
        order.order_id = order_id
        order.order_date = get_override_string_value_or_default(row["TicketOrderDate"])
        order.is_hologram = get_override_bool_value_or_default(row["IsHologram"])
        age_limit_id = get_override_int_value_or_default(row["TicketOrderAgeLimitId"])
        if age_limit_id > 0:
            age_limit = TicketOrderAgeLimit()
            age_limit.age_limit_id = age_limit_id
            age_limit.age_limit_name = get_override_string_value_or_default(
                row["TicketOrderAgeLimitName"]
            )
            order.age_limit = age_limit
        event_id = get_override_int_value_or_default(row["EventID"])
        if event_id > 0:
            event = event_service.get_events_and_orders(
                event_id=event_id, ignore_flags=True
            )
            order.event = event
        order.shipping_name = get_override_string_value_or_default(row["ShippingName"])
        order.shipping_address = get_override_string_value_or_default(
            row["ShippingAddress"]
        )
        order.shipping_city = get_override_string_value_or_default(row["ShippingCity"])
        order.shipping_state = get_override_string_value_or_default(
            row["ShippingState"]
        )
        order.shipping_zip = get_override_string_value_or_default(row["ShippingZip"])
        order.shipping_country = get_override_string_value_or_default(
            row["ShippingCountry"]
        )
        order.contact_name = get_override_string_value_or_default(row["ContactName"])
        order.contact_email = get_override_string_value_or_default(row["ContactEmail"])
        order.contact_phone = get_override_string_value_or_default(row["ContactPhone"])
        cc_emails_str = get_override_string_value_or_default(row["CCEmails"])
        if cc_emails_str is not None and len(cc_emails_str.strip()) > 0:
            order.contact_cc_emails = cc_emails_str.split(",")
        order.ticket_note = get_override_string_value_or_default(row["TicketNote"])
        order.order_note = get_override_string_value_or_default(row["OrderNote"])
        order.is_fulfulled = get_override_bool_value_or_default(row["IsFulfilled"])
        order.is_paid = get_override_bool_value_or_default(row["IsPaid"])
        order.notes = get_override_string_value_or_default(row["Notes"])
        order.ship_date = get_override_string_value_or_default(row["ShipDate"])
        order.paid_date = get_override_string_value_or_default(row["PaidDate"])
        levels = self.__get_ticket_price_levels(order_id)
        if levels is not None and len(levels) > 0:
            order.price_levels = levels
        return order

    def __get_ticket_price_levels(self, order_id: int):
        """
        Get price level data from database
        """
        sql = """SELECT TicketOrderPriceLevel.*
                    FROM TicketOrderPriceLevel
                    WHERE TicketOrderId=%(order_id)s"""
        data = {"order_id": order_id}
        levels: list[TicketOrderPriceLevel] = []
        rows = db_query_all(sql, data)
        for row in rows:
            to_price_level_id = get_override_int_value_or_default(
                row["TicketOrderPriceLevelId"]
            )
            if to_price_level_id == 0:
                continue
            level = TicketOrderPriceLevel()
            level.ticket_order_price_level_id = to_price_level_id
            level.level_id = get_override_int_value_or_default(row["PriceLevelId"])
            level.level_name = get_override_string_value_or_default(
                row["PriceLevelName"]
            )
            level.quantity = get_override_int_value_or_default(
                row["PriceLevelQuantity"]
            )
            level.price = get_override_float_value_or_default(row["PriceLevelPrice"])
            level.per_ticket_charge = get_override_float_value_or_default(
                row["PerTicketCharge"]
            )
            levels.append(level)
        return levels

    def update_order(self, order_to_update: TicketOrder):
        """
        Updates/Inserts orders
        """
        if order_to_update is None:
            return None

        success: bool = False
        order_id = order_to_update.order_id

        cc_emails: str = None
        if len(order_to_update.contact_cc_emails) > 0:
            cc_emails = ",".join(order_to_update.contact_cc_emails)

        data = {
            "date": get_override_string_value_or_default(order_to_update.order_date),
            "eventId": get_override_int_value_or_default(
                order_to_update.event.event_id
            ),
            "ageLimitId": get_override_int_value_or_default(
                order_to_update.age_limit.age_limit_id
            ),
            "isHologram": get_override_tinyint_value_or_default_from_bool(
                order_to_update.is_hologram
            ),
            "shippingName": get_override_string_value_or_default(
                order_to_update.shipping_name
            ),
            "shippingAddress": get_override_string_value_or_default(
                order_to_update.shipping_address
            ),
            "shippingCity": get_override_string_value_or_default(
                order_to_update.shipping_city
            ),
            "shippingState": get_override_string_value_or_default(
                order_to_update.shipping_state
            ),
            "shippingZip": get_override_string_value_or_default(
                order_to_update.shipping_zip
            ),
            "shippingCountry": get_override_string_value_or_default(
                order_to_update.shipping_country
            ),
            "contactEmail": get_override_string_value_or_default(
                order_to_update.contact_email
            ),
            "contactName": get_override_string_value_or_default(
                order_to_update.contact_name
            ),
            "contactPhone": get_override_string_value_or_default(
                order_to_update.contact_phone
            ),
            "contactCCEmails": cc_emails,
            "ticketNote": get_override_string_value_or_default(
                order_to_update.ticket_note
            ),
            "orderNote": get_override_string_value_or_default(
                order_to_update.order_note
            ),
            "notes": get_override_string_value_or_default(order_to_update.notes),
            "isFulfilled": get_override_tinyint_value_or_default_from_bool(
                order_to_update.is_fulfulled
            ),
            "isPaid": get_override_tinyint_value_or_default_from_bool(
                order_to_update.is_paid
            ),
            "shippingCharge": get_override_float_value_or_default(
                order_to_update.charged_shipping
            ),
            "shipDate": get_override_string_value_or_default(order_to_update.ship_date),
            "paidDate": get_override_string_value_or_default(order_to_update.paid_date),
        }

        if order_id > 0:
            data["order_id"] = order_id
            sql = """UPDATE TicketOrders SET TicketOrderDate=%(date)s,
                ExternalEventId=%(eventId)s, TicketOrderAgeLimitId=%(ageLimitId)s, 
                IsHologram=%(isHologram)s, ShippingName=%(shippingName)s, 
                ShippingAddress=%(shippingAddress)s, ShippingCity=%(shippingCity)s,
                ShippingState=%(shippingState)s, ShippingZip=%(shippingZip)s,
                ShippingCountry=%(shippingCountry)s, ContactEmail=%(contactEmail)s,
                ContactName=%(contactName)s, ContactPhone=%(contactPhone)s,
                IsFulfilled=%(isFulfilled)s, IsPaid=%(isPaid)s,
                ShippingCharge=%(shippingCharge)s, Notes=%(notes)s,
                ShipDate=%(shipDate)s, PaidDate=%(paidDate)s,
                CCEmails=%(contactCCEmails)s, 
                LastUpdate=CURRENT_TIMESTAMP
                WHERE TicketOrderId=%(order_id)s"""
            success = db_update(sql, data)
        else:
            sql = """INSERT INTO TicketOrders (TicketOrderDate, ExternalEventId,
                TicketOrderAgeLimitId, IsHologram, ShippingName, ShippingAddress,
                ShippingCity, ShippingState, ShippingZip, ShippingCountry,
                ContactEmail, ContactName, ContactPhone, IsFulfilled, IsPaid,
                ShippingCharge, Notes, ShipDate, PaidDate, CCEmails, 
                LastUpdated) VALUES (%(date)s, %(eventId)s, %(ageLimitId)s,
                %(isHologram)s, %(shippingName)s, %(shippingAddress)s,
                %(shippingCity)s, %(shippingState)s, %(shippingZip)s,
                %(shippingCountry)s, %(contactEmail)s, %(contactName)s,
                %(contactPhone)s, %(isFulfilled)s, %(isPaid)s, %(shippingCharge)s,
                %(notes)s, %(shipDate)s, %(paidDate)s, %(contactCCEmails)s, 
                CURRENT_TIMESTAMP)"""
            order_id = db_insert(sql, data)
            success = order_id > 0

        if (
            success is True
            and order_id > 0
            and order_to_update.price_levels is not None
            and len(order_to_update.price_levels) > 0
        ):
            new_levels: list[TicketOrderPriceLevel] = order_to_update.price_levels
            existing_levels = self.__get_ticket_price_levels(order_id)

            levels_updated: bool = False
            # check for updates/adds in new price levels list
            for level in new_levels:
                found_level = next(
                    (
                        sl
                        for sl in existing_levels
                        if sl.ticket_order_price_level_id
                        == level.ticket_order_price_level_id
                    ),
                    None,
                )
                if found_level is not None:
                    update_sql = """UPDATE TicketOrderPriceLevels SET
                        TicketOrderId=%(order_id)s,
                        PriceLevelId=%(level_id)s,
                        PriceLevelName=%(name)s, 
                        PriceLevelQuantity=%(quantity)s,
                        PriceLevelPrice=%(price)s,
                        PerTicketCharge=%(perTicketCharge)s,                                 
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE TicketOrderPriceLevelId=%(to_price_level_id)s"""
                    update_data = {
                        "name": level.level_name,
                        "quantity": level.quantity,
                        "price": level.price,
                        "perTicketCharge": level.per_ticket_charge,
                        "order_id": order_id,
                        "level_id": level.level_id,
                        "to_price_level_id": found_level.ticket_order_price_level_id,
                    }
                    success = db_update(update_sql, update_data)
                    levels_updated = success
                elif level.level_id > 0:
                    insert_sql = """INSERT INTO TicketOrderPriceLevels
                        (TicketOrderId, PriceLevelId, PriceLevelName,
                        PriceLevelQuantity, PriceLevelPrice, PerTicketCharge, LastUpdate)
                        VALUES (%(order_id)s, %(level_id)s, %(name)s, %(quantity)s, 
                        %(price)s, %(perTicketCharge)s, 
                        CURRENT_TIMESTAMP)"""
                    insert_data = {
                        "order_id": order_id,
                        "level_id": level.level_id,
                        "name": level.level_name,
                        "quantity": level.quantity,
                        "price": level.price,
                        "perTicketCharge": level.per_ticket_charge,
                    }

                    pl_id = db_insert(insert_sql, insert_data)
                    success = pl_id > 0
                    levels_updated = success
                    if levels_updated is True:
                        level.ticket_order_price_level_id = pl_id

                if success is not True:
                    break

            # check for deletes
            for level in existing_levels:
                found_level = next(
                    (
                        sl
                        for sl in new_levels
                        if sl.ticket_order_price_level_id
                        == level.ticket_order_price_level_id
                    ),
                    None,
                )
                if found_level is None:
                    delete_sql = """DELETE FROM TicketOrderPriceLevel
                        WHERE TicketOrderPriceLevelId=%(to_price_level_id)s"""
                    delete_data = {
                        "to_price_level_id": get_override_int_value_or_default(
                            level.ticket_order_price_level_id
                        )
                    }
                    success = db_delete(delete_sql, delete_data)
                    levels_updated = success

                if success is not True:
                    break

            if levels_updated is True:
                order_to_update.price_levels = new_levels

        return order_to_update if success is True else None

    def check_in_ticket(self, bar_code: str, event_id: int) -> TicketCheckIn:
        """
        Check in a ticket
        """
        response = TicketCheckIn()

        if bar_code is None or len(bar_code.strip()) == 0:
            response.check_in_status = TicketCheckInStatus.ERROR
            response.error_message = "Ticket ID is required"
            return response

        sql = """SELECT tsot.Id, tsot.IsCheckedIn, tsot.CheckedInDate, tsot.IsActive, e.EventId
                    FROM TicketSocketOrderTickets tsot
                    LEFT JOIN TicketPartnerOrderTickets tpot ON tpot.PartnerTicketId = tsot.Id
                    LEFT JOIN TicketPartnerOrders tpo
                        ON tpo.TicketPartnerOrderId = tpot.TicketPartnerOrderId
                    LEFT JOIN TicketPartnerEvents tpe
                        ON tpe.TicketPartnerEventId = tpo.TicketPartnerEventId
                        AND tpe.TicketPartnerId = 2
                    LEFT JOIN Events e ON e.EventId = tpe.EventId
                    WHERE tsot.BarCode=%(bar_code)s"""
        data = {"bar_code": bar_code}
        result = db_query_one(sql, data)

        if not result:
            response.check_in_status = TicketCheckInStatus.INVALID_TICKET
            response.error_message = "Ticket ID not found"
            return response

        ticket_event_id = get_override_int_value_or_default(
            result["EventId"], default=None
        )
        if ticket_event_id is None or ticket_event_id != event_id:
            response.check_in_status = TicketCheckInStatus.INVALID_TICKET
            response.error_message = "Ticket ID does not match event"
            return response

        ticket_id = get_override_string_value_or_default(result["Id"])
        response.ticket_id = bar_code

        is_checked = get_override_bool_value_or_default(result["IsCheckedIn"])
        is_active = get_override_bool_value_or_default(result["IsActive"])
        checked_in_date = get_override_string_value_or_default(result["CheckedInDate"])

        if not is_active:
            response.check_in_status = TicketCheckInStatus.ERROR
            response.error_message = "Ticket is not active"
            return response

        if is_checked:
            response.check_in_status = TicketCheckInStatus.ALREADY_CHECKED_IN
            response.check_in_time = (
                get_pacific_timestamp_from_utc_datetime_string(checked_in_date)
                if checked_in_date is not None
                else None
            )
            return response

        current_timestamp = datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        sql = """UPDATE TicketSocketOrderTickets SET IsCheckedIn=1,
                    CheckedInDate=%(current_timestamp)s,
                    LastUpdate=CURRENT_TIMESTAMP
                    WHERE Id=%(ticket_id)s"""
        data = {"ticket_id": ticket_id, "current_timestamp": current_timestamp}
        success = db_update(sql, data)

        if success is not True:
            response.check_in_status = TicketCheckInStatus.ERROR
            response.error_message = f"Failed to check in ticket {ticket_id}"
        else:
            response.check_in_status = TicketCheckInStatus.SUCCESS
            response.check_in_time = get_pacific_timestamp_from_utc_datetime_string(
                current_timestamp
            )

        return response
