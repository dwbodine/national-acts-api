"""
Ticket Socket API service module
"""

import os
import json
import http.client
import time
from datetime import datetime
from typing import Any

from common.utility import fix_magic_quotes, format_phone
from common.db import db_query_all, db_query_one
from common.models.ticket_socket import (
    TicketSocketCategory,
    TicketSocketEvent,
    TicketSocketVenue,
    TicketSocketTicketType,
    TicketSocketTicket,
    TicketSocketOrder,
)


class TicketSocketService:
    """
    Service to fetch data from TicketSocket API
    """

    name: str = ""
    service_url: str = ""
    utc_offset_hours: int = 0
    exchange_rate_id: int = 1
    exchange_rate_slug: str = ""
    mulitiplier: float = 1
    currency_symbol: str = ""
    token: str = ""
    categories: list[TicketSocketCategory] = []
    events: list[TicketSocketEvent] = []

    def __init__(self, ticket_socket_id: int):
        self.ticket_socket_id = ticket_socket_id
        self.__initialize()

    def __get_ts_account_data(self):
        """
        Get stored data from this TicketSocket account
        """
        sql = """SELECT TicketSocket.AccountName, TicketSocket.ServiceUrl,
                 TicketSocket.DefaultUtcOffsetHours, TicketSocket.ExchangeRateId,  
                 ExchangeRates.Symbol, ExchangeRates.ServiceTokenId, ExchangeRates.Multiplier 
                 FROM TicketSocket 
                 INNER JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                 WHERE TicketSocketId=%(ts_id)s"""

        data = {"ts_id": self.ticket_socket_id}

        row = db_query_one(sql, data)
        if row:
            self.name = row["AccountName"]
            self.service_url = row["ServiceUrl"]
            self.service_url = self.service_url.replace("https://", "")
            self.utc_offset_hours = int(row["DefaultUtcOffsetHours"])
            self.currency_symbol = row["Symbol"]
            self.exchange_rate_id = int(row["ExchangeRateId"])
            self.exchange_rate_slug = row["ServiceTokenId"]
            self.mulitiplier = float(row["Multiplier"])

    def __get_jwt_token(self):
        """
        Gets JWT bearer token from TicketSocket for this account
        """
        uid = os.getenv("API_UID_" + str(self.ticket_socket_id))
        pwd = os.getenv("API_PWD_" + str(self.ticket_socket_id))
        pk = os.getenv("API_PK_" + str(self.ticket_socket_id))
        pk_slug = os.getenv("API_PK_SLUG_" + str(self.ticket_socket_id))

        creds = {
            "userName": uid,
            "password": pwd,
            "publicKey": pk,
            "publicKeySlug": pk_slug,
        }

        url = "/api/v1/tokens"
        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
        }

        conn = http.client.HTTPSConnection(self.service_url)
        conn.request("POST", url, json.dumps(creds), headers)
        response = conn.getresponse()

        jwt = ""
        if response.status == 200:
            json_response = json.loads(response.read())
            jwt = json_response["data"]["jwt"]

        conn.close()
        self.token = jwt

    def __initialize(self):
        self.__get_ts_account_data()
        self.__get_jwt_token()

    def get_categories(self):
        """
        Fetch list of categories from TS
        """
        url = "/api/v1/categories"
        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "Authorization": "Bearer " + self.token,
        }

        conn = http.client.HTTPSConnection(self.service_url)
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        self.categories = []
        if response.status == 200:
            json_response = json.loads(response.read())
            json_data = json_response["data"]
            for item in json_data:
                category_id: int = 0
                title: str = ""
                if "id" in item:
                    category_id = int(item["id"])
                if "title" in item:
                    title = item["title"]
                if category_id > 0 and title != "":
                    self.categories.append(
                        TicketSocketCategory(item["id"], item["title"])
                    )

        conn.close()

        return self.categories

    def get_events_and_orders(
        self,
        event_category_id: int = None,
        unix_start: int = None,
        unix_end: int = None,
    ):
        """
        Get all TS data for the specified category and time period
        """
        url = """/api/v1/events?"""
        url += """includeEnded=true&includeOffSale=true"""
        url += """&includeTicketTypes=true&limit=9999"""

        if event_category_id is not None and event_category_id > 0:
            url += "&category=" + str(event_category_id)

        if unix_start is None and unix_end is None:
            url += "&startsAfter=" + str(int(time.time()))
        else:
            if unix_start is not None:
                url += "&startsAfter=" + str(unix_start)
            if unix_end is not None:
                url += "&startsBefore=" + str(unix_end)

        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "Authorization": "Bearer " + self.token,
        }

        conn = http.client.HTTPSConnection(self.service_url, timeout=600)
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        self.events = []
        if response.status == 200:
            json_response = json.loads(response.read())
            json_data = json_response["data"]
            for item in json_data:
                # basic info
                event_id: int = 0
                title: str = ""
                if "id" in item:
                    event_id = int(item["id"])
                if "title" in item:
                    title = item["title"]

                if event_id == 0 or title == "":
                    continue

                event = TicketSocketEvent()
                event.event_id = event_id
                event.title = title

                on_sale: str = ""
                if "onsale" in item:
                    on_sale = item["onsale"]
                event.on_sale = True if on_sale == "1" else False

                categories = []
                if "categories" in item:
                    categories = item["categories"]

                if len(categories) <= 0:
                    continue

                category = categories[0]

                category_id: int = 0
                if "id" in category:
                    category_id = int(category["id"])

                if category_id <= 0:
                    continue

                event.event_category_id = category_id

                thumbnail: str = ""
                if "smallPic" in item:
                    thumbnail = item["smallPic"]
                event.thumbnail = thumbnail

                sef_url: str = ""
                if "sefUrl" in item:
                    sef_url = item["sefUrl"]

                event.ticket_socket_url = (
                    "https://" + self.service_url + "/event/" + sef_url
                )

                # venue info
                venue = ""
                if "venue" in item:
                    venue = fix_magic_quotes(item["venue"])

                custom_fields = {}
                if "custom_fields" in item:
                    custom_fields = item["custom_fields"]

                address1 = ""
                if "venueAddress1" in item and item["venueAddress1"] != "":
                    address1 = fix_magic_quotes(item["venueAddress1"])
                elif custom_fields != {} and "venueAddress1" in custom_fields:
                    address1 = fix_magic_quotes(custom_fields["venueAddress1"])

                address2 = ""
                if "venueAddress2" in item and item["venueAddress2"] != "":
                    address2 = fix_magic_quotes(item["venueAddress2"])
                elif custom_fields != {} and "venueAddress2" in custom_fields:
                    address2 = fix_magic_quotes(custom_fields["venueAddress2"])

                city = ""
                if "venueCity" in item and item["venueCity"] != "":
                    city = fix_magic_quotes(item["venueCity"])
                elif custom_fields != {} and "venueCity" in custom_fields:
                    city = fix_magic_quotes(custom_fields["venueCity"])

                state = ""
                if "venueState" in item and item["venueState"] != "":
                    state = fix_magic_quotes(item["venueState"])
                elif custom_fields != {} and "venueState" in custom_fields:
                    state = fix_magic_quotes(custom_fields["venueState"])

                zip_code = ""
                if "venuePostalCode" in item and item["venuePostalCode"] != "":
                    zip_code = fix_magic_quotes(item["venuePostalCode"])
                elif custom_fields != {} and "venuePostalCode" in custom_fields:
                    zip_code = fix_magic_quotes(custom_fields["venuePostalCode"])

                country = ""
                if "venueCountry" in item and item["venueCountry"] != "":
                    country = fix_magic_quotes(item["venueCountry"])
                elif custom_fields != {} and "venueCountry" in custom_fields:
                    country = fix_magic_quotes(custom_fields["venueCountry"])

                format_phones: bool = True
                if country != "" and country != "USA" and country != "United States":
                    format_phones = False

                timezone = ""
                if custom_fields != {} and "timezone" in custom_fields:
                    timezone = custom_fields["timezone"]

                event_venue = TicketSocketVenue(
                    venue, address1, address2, city, state, zip_code, country, timezone
                )
                event.venue = event_venue

                # date/time info
                display_date: str = ""
                if "displayStartDate" in item:
                    display_date = item["displayStartDate"]

                event.display_date = display_date

                event_utc: int = 0
                if "start" in item:
                    event_utc = int(item["start"])

                event.utc_time = event_utc

                # need at least one of them to be non-zero
                if display_date == "" and event_utc == 0:
                    continue

                # note: this is a total hack since TicketSocket returns in UTC
                # BUT does NOT return a reliable timezone value for the venue
                # (yeah this is that bad - even when it's right,
                # it's a timezone that isn't convertible using Python or well...anything)
                # So what we do instead is define a "default offset" in the database
                # that roughly gets us the right date since we're not displaying times
                # in the front end.  With any luck the "displayStartDate" comes back
                # with a valid value and we use that for our date instead

                try:
                    event_date = datetime.strptime(event.display_date, "%m/%d/%Y")
                    event.event_date = event_date.strftime("%Y-%m-%d")
                except Exception: # pylint: disable=broad-exception-caught
                    event_time: int = event.utc_time + (self.utc_offset_hours * 60 * 60)
                    event.event_date = datetime.fromtimestamp(event_time).strftime(
                        "%Y-%m-%d"
                    )

                # ticket types
                ticket_types = []
                if "ticketTypes" in item:
                    ticket_types = self.get_ticket_types_from_event(item["ticketTypes"])
                event.ticket_types = ticket_types

                # orders
                event.orders = self.get_orders_from_event_id(
                    event.event_id, format_phones
                )

                self.events.append(event)

        return self.events

    def get_ticket_types_from_event(self, ticket_types: list[Any]):
        """
        Fetch ticket types from event
        """
        if len(ticket_types) <= 0:
            return []

        ttypes: list[TicketSocketTicketType] = []
        for item in ticket_types:
            ticket_type_id = int(item["id"])
            name = str(item["name"])
            event_id = int(item["eventId"])
            total_available = int(item["quantity"])
            is_active: bool = True
            if "deleted" in item:
                is_active = int(item["deleted"]) == 0
            ttype = TicketSocketTicketType(
                event_id, ticket_type_id, name, total_available, is_active
            )
            ttypes.append(ttype)

        return ttypes

    def get_orders_from_event_id(self, event_id: int, format_phone_numbers: bool):
        """
        Get order data per event from TS
        """
        # get list of orderIds first
        order_ids = self.get_order_ids_from_event_id(event_id)

        # if there are no orders, return nothing
        if len(order_ids) <= 0:
            return []

        # common service settings
        base_url: str = "/api/v1/orders/"
        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "Authorization": "Bearer " + self.token,
        }
        conn = http.client.HTTPSConnection(self.service_url, timeout=600)

        # loop through and append orders
        orders: list[TicketSocketOrder] = []
        for order_id in order_ids:
            url = base_url + str(order_id)
            conn.request("GET", url, headers=headers)
            response = conn.getresponse()

            if response.status == 200:
                json_response = json.loads(response.read())
                json_data = json_response["data"]

                incoming_order_id: int = 0
                if "id" in json_data:
                    incoming_order_id = int(json_data["id"])

                if incoming_order_id == 0 or incoming_order_id != order_id:
                    continue

                order: TicketSocketOrder = self.__parse_response_to_order_object(
                    incoming_order_id, event_id, format_phone_numbers, json_data
                )

                orders.append(order)

        return orders

    def get_order_from_order_id(
        self, order_id: int, event_id: int = 0, format_phone_numbers: bool = True
    ):
        """
        API method to only return TS data for one order
        """
        order: TicketSocketOrder = None
        # common service settings
        base_url: str = "/api/v1/orders/"
        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "Authorization": "Bearer " + self.token,
        }
        conn = http.client.HTTPSConnection(self.service_url, timeout=600)

        url = base_url + str(order_id)
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        if response.status == 200:
            json_response = json.loads(response.read())
            json_data = json_response["data"]

            incoming_order_id: int = 0
            if "id" in json_data:
                incoming_order_id = int(json_data["id"])

            if incoming_order_id != 0 or incoming_order_id != order_id:
                order = self.__parse_response_to_order_object(
                    incoming_order_id, event_id, format_phone_numbers, json_data
                )

        return order

    def get_order_ids_from_event_id(self, event_id: int):
        """
        Fetch list of order ids from TS eventId
        """
        url = "/api/v1/orders?limit=999&eventId=" + str(event_id)

        headers = {
            "Accept": "application/json",
            "Content-type": "application/json;charset=UTF-8",
            "Authorization": "Bearer " + self.token,
        }

        conn = http.client.HTTPSConnection(self.service_url, timeout=600)
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        order_ids: list[int] = []
        if response.status == 200:
            json_response = json.loads(response.read())
            json_data = json_response["data"]
            for item in json_data:
                order_id: int = 0
                if "orderId" in item:
                    order_id = int(item["orderId"])
                if order_id != 0:
                    order_ids.append(order_id)

        return order_ids

    def __parse_response_to_order_object(
        self, order_id: int, event_id: int, format_phone_numbers: bool, json_data: any
    ):
        # get data from order
        order = TicketSocketOrder()
        order.order_id = order_id
        order.event_id = event_id

        if "cancelled" in json_data:
            order.cancelled = bool(json_data["cancelled"])

        if "deleted" in json_data:
            order.deleted = True if int(json_data["deleted"]) == 1 else False

        tickets = None
        if "tickets" in json_data:
            tickets = json_data["tickets"]

        num_tickets: int = 0
        total_count: int = 0
        if tickets is not None:
            if "totalCount" in tickets:
                total_count = int(tickets["totalCount"])

        order_revenue: float = 0
        order_service_fees: float = 0
        order_tickets = []
        if total_count > 0:
            ticket_data = tickets["data"]
            for item in ticket_data:
                # if the ticket doesn't belong to this event, move along
                # and yes that happens that an order can contain tickets to multiple events

                shirt_size: str = None
                item_event_id: int = 0
                if "eventId" in item:
                    item_event_id = int(item["eventId"])
                if item_event_id != int(event_id):
                    continue

                num_tickets += 1

                # set properties on order from ticket data if not present
                if order.user_id == 0 and "userId" in item:
                    order.user_id = int(item["userId"])
                if order.purchaser_first_name == "" and "billing_firstName" in item:
                    order.purchaser_first_name = fix_magic_quotes(
                        item["billing_firstName"]
                    )
                if order.purchaser_last_name == "" and "billing_lastName" in item:
                    order.purchaser_last_name = fix_magic_quotes(
                        item["billing_lastName"]
                    )
                if order.purchaser_city is None and "billing_city" in item:
                    order.purchaser_city = fix_magic_quotes(item["billing_city"])
                if order.purchaser_state is None and "billing_state" in item:
                    order.purchaser_state = fix_magic_quotes(item["billing_state"])
                if order.purchaser_zip_code is None and "billing_zip" in item:
                    order.purchaser_zip_code = fix_magic_quotes(item["billing_zip"])
                if order.purchaser_country is None and "billing_country" in item:
                    order.purchaser_country = fix_magic_quotes(item["billing_country"])
                if order.purchaser_ip_address is None and "remoteAddr" in item:
                    order.purchaser_ip_address = fix_magic_quotes(item["remoteAddr"])
                if order.purchase_date == "" and "purchaseDate" in item:
                    # datetime is not serializable in python,
                    # convert it to ISO-compatible string
                    purchase_date = datetime.fromtimestamp(float(item["purchaseDate"]))
                    order.purchase_date = purchase_date.strftime("%Y-%m-%d")
                    order.purchase_timestamp = purchase_date.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                if order.email == "" and "email" in item:
                    order.email = item["email"]

                # get shirt and phone data from questions
                purchaser_questions: list = []
                attendee_questions: list = []
                if "purchaserQuestions" in item:
                    purchaser_questions = list(item["purchaserQuestions"])
                if "attendeeQuestions" in item:
                    attendee_questions = list(item["attendeeQuestions"])
                questions = purchaser_questions + attendee_questions
                if len(questions) > 0:
                    for question_item in questions:
                        question: str = ""
                        if "question" in question_item:
                            question = str(question_item["question"]).lower()

                        if question == "":
                            continue

                        answer: str = ""
                        if "answerText" in question_item:
                            answer = str(question_item["answerText"])

                        if answer != "":
                            if question.find("phone") >= 0 and order.phone == "":
                                if format_phone_numbers:
                                    order.phone = format_phone(answer)
                                else:
                                    order.phone = answer
                            elif question.find("shirt") >= 0:
                                shirt_size = answer

                # create the ticket object
                price: float = 0
                if "price" in item:
                    price = float(item["price"])

                ticket_id: int = 0
                if "id" in item:
                    ticket_id = int(item["id"])
                ticket_type: str = ""
                if "ticketTypeName" in item:
                    ticket_type = item["ticketTypeName"]
                service_fee: float = 0
                if "fee1Amount" in item:
                    service_fee = float(item["fee1Amount"])
                ticket_type_id: int = 0
                if "typeId" in item:
                    ticket_type_id = int(item["typeId"])
                barcode: str = ""
                if "barcode" in item:
                    barcode = str(item["barcode"])
                available_scans: int = 0
                if "availableScans" in item:
                    available_scans = int(item["availableScans"])
                purchase_location: str = ""
                if "purchaseLocation" in item:
                    purchase_location = str(item["purchaseLocation"])
                scanned_timestamp: int = 0
                if "scannedTimestamp" in item:
                    scanned_timestamp = int(item["scannedTimestamp"])
                attendee_first_name: str = ""
                if "partyMember" in item:
                    attendee_first_name = fix_magic_quotes(item["partyMember"])
                attendee_last_name: str = ""
                if "partyMemberLastName" in item:
                    attendee_last_name = fix_magic_quotes(item["partyMemberLastName"])

                if ticket_id == 0 or ticket_type == "":
                    continue

                ticket = TicketSocketTicket()
                ticket.ticket_id = ticket_id
                ticket.ticket_type = ticket_type
                ticket.price = price
                ticket.service_fee = service_fee
                ticket.ticket_type_id = ticket_type_id
                ticket.barcode = barcode
                ticket.available_scans = available_scans
                ticket.purchase_location = purchase_location
                ticket.scanned_timestamp = scanned_timestamp
                ticket.attendee_first_name = attendee_first_name
                ticket.attendee_last_name = attendee_last_name
                if shirt_size is not None:
                    shirt_size = shirt_size.strip()
                    if shirt_size.lower() == "3xl":
                        shirt_size = "XXXL"
                    elif shirt_size.lower() == "2xl":
                        shirt_size = "XXL"
                    elif shirt_size.lower() == "extra large":
                        shirt_size = "XL"
                    elif shirt_size.lower() == "large":
                        shirt_size = "L"
                    elif shirt_size.lower() == "medium":
                        shirt_size = "M"
                    elif shirt_size.lower() == "small":
                        shirt_size = "S"
                    elif shirt_size.lower() == "extra small":
                        shirt_size = "XS"
                ticket.shirt_size = shirt_size
                order_tickets.append(ticket)

                order_revenue += price
                order_service_fees += service_fee

        if len(order_tickets) > 0:
            order.num_tickets = num_tickets
            order.tickets = order_tickets
            order.revenue = order_revenue
            order.service_fees = order_service_fees
        return order


def get_all_accounts():
    """
    Gets stored data for all TS accounts
    """
    accounts: list[TicketSocketService] = []
    sql = "SELECT TicketSocketId FROM TicketSocket ORDER BY TicketSocketId"
    rows = db_query_all(sql)
    for row in rows:
        ticket_socket_id = int(row["TicketSocketId"])
        account = TicketSocketService(ticket_socket_id)
        accounts.append(account)
    return accounts
