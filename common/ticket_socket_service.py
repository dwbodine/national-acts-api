"""
Ticket Socket API service module
"""

import os
import logging
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import pytz

from common.utility import (
    fix_magic_quotes,
    get_country_from_country_name,
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    post_https_response,
    get_https_response,
)
from common.db import db_query_one
from common.models.ticket_socket import (
    Country,
    TicketSocketCategory,
    TicketSocketEvent,
    TicketSocketVenue,
    TicketSocketTicketType,
    TicketSocketTicket,
    TicketSocketOrder,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class TicketSocketService:
    """
    Service to fetch data from TicketSocket API
    """

    name: str = ""
    service_url: str = ""
    utc_offset_hours: int = 0
    exchange_rate_id: int = 1
    exchange_rate_slug: str = ""
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
                 ExchangeRates.Symbol, ExchangeRates.ServiceTokenId 
                 FROM TicketSocket 
                 INNER JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                 WHERE TicketSocketId=%(ts_id)s"""

        data = {"ts_id": self.ticket_socket_id}

        row = db_query_one(sql, data)
        if row:
            self.name = get_override_string_value_or_default(row["AccountName"])
            self.service_url = get_override_string_value_or_default(row["ServiceUrl"])
            self.service_url = self.service_url.replace("https://", "")
            self.utc_offset_hours = get_override_int_value_or_default(
                row["DefaultUtcOffsetHours"]
            )
            self.currency_symbol = get_override_string_value_or_default(row["Symbol"])
            self.exchange_rate_id = get_override_int_value_or_default(
                row["ExchangeRateId"]
            )
            self.exchange_rate_slug = get_override_string_value_or_default(
                row["ServiceTokenId"]
            )

    def __get_jwt_token(self):
        """
        Gets JWT bearer token from TicketSocket for this account
        """
        ticket_id_str: str = get_override_string_value_or_default(self.ticket_socket_id)
        uid = os.getenv("API_UID_" + ticket_id_str)
        pwd = os.getenv("API_PWD_" + ticket_id_str)
        pk = os.getenv("API_PK_" + ticket_id_str)
        pk_slug = os.getenv("API_PK_SLUG_" + ticket_id_str)

        creds = {
            "userName": uid,
            "password": pwd,
            "publicKey": pk,
            "publicKeySlug": pk_slug,
        }

        url: str = "/api/v1/tokens"
        payload: str = json.dumps(creds)
        jwt: str = None

        json_data = post_https_response(host=self.service_url, url=url, payload=payload)
        if json_data is not None:
            jwt = json_data["jwt"]
            self.token = jwt

    def __initialize(self):
        self.__get_ts_account_data()
        self.__get_jwt_token()

    def get_categories(self):
        """
        Fetch list of categories from TS
        """
        self.categories = []

        if self.service_url is None or self.token is None:
            logger.error(
                "service url or token not present for ticket_socket_id %s",
                self.ticket_socket_id,
            )
            return []

        json_data = get_https_response(
            host=self.service_url, url="/api/v1/categories", bearer_token=self.token
        )

        if json_data is not None:
            for item in json_data:
                category_id: int = 0
                title: str = None
                if "id" in item:
                    category_id = get_override_int_value_or_default(item["id"])
                if "title" in item:
                    title = get_override_string_value_or_default(item["title"])
                if category_id > 0 and title is not None and title != "":
                    self.categories.append(
                        TicketSocketCategory(item["id"], item["title"])
                    )

        return self.categories

    def get_events_and_orders(
        self,
        unix_start: int,
        unix_end: int = None,
        event_category_id: int = None,
    ):
        """
        Get all TS data for the specified category and time period
        """

        self.events = []
        if self.service_url is None or self.token is None:
            logger.error(
                "service url or token not present for ticket_socket_id %s",
                self.ticket_socket_id,
            )
            return self.events

        url = """/api/v1/events?"""
        url += """includeEnded=true&includeOffSale=true"""
        url += """&includeTicketTypes=true&limit=9999"""
        url += "&startsAfter=" + str(unix_start)

        if unix_end is not None:
            url += "&startsBefore=" + str(unix_end)

        if event_category_id is not None and event_category_id > 0:
            url += "&category=" + str(event_category_id)

        events_timer = time.time()
        json_data = get_https_response(
            host=self.service_url, url=url, bearer_token=self.token
        )
        logger.info(
            "TicketSocket event list fetched ticket_socket_id=%s category=%s "
            "raw_events=%s duration=%.2fs",
            self.ticket_socket_id,
            event_category_id,
            len(json_data) if json_data is not None else 0,
            time.time() - events_timer,
        )

        self.events = []
        if json_data is not None:
            parse_timer = time.time()
            for item in json_data:
                # basic info
                event_id: int = 0
                title: str = ""
                if "id" in item:
                    event_id = get_override_int_value_or_default(item["id"])
                if "title" in item:
                    title = get_override_string_value_or_default(item["title"])

                if event_id == 0 or title is None or title == "":
                    continue

                event = TicketSocketEvent()
                event.event_id = event_id
                event.title = title

                categories = []
                if "categories" in item:
                    categories = item["categories"]

                if len(categories) <= 0:
                    continue

                category = categories[0]

                category_id: int = 0
                if "id" in category:
                    category_id = get_override_int_value_or_default(category["id"])

                if category_id <= 0:
                    continue

                event.event_category_id = category_id

                thumbnail: str = None
                if "smallPic" in item:
                    thumbnail = get_override_string_value_or_default(item["smallPic"])
                event.thumbnail = thumbnail

                sef_url: str = None
                if "sefUrl" in item:
                    sef_url = get_override_string_value_or_default(item["sefUrl"])

                if sef_url is not None:
                    event.ticket_socket_url = (
                        "https://" + self.service_url + "/event/" + sef_url
                    )

                # venue info
                venue = None
                if "venue" in item:
                    venue = get_override_string_value_or_default(item["venue"])

                if venue is not None:
                    venue = fix_magic_quotes(venue)

                custom_fields = {}
                if "custom_fields" in item:
                    custom_fields = item["custom_fields"]
                elif "customFields" in item:
                    custom_fields = item["customFields"]

                address1 = None
                if "venueAddress1" in item:
                    address1 = get_override_string_value_or_default(
                        item["venueAddress1"]
                    )
                elif custom_fields != {} and "venueAddress1" in custom_fields:
                    address1 = get_override_string_value_or_default(
                        custom_fields["venueAddress1"]
                    )

                if address1 is not None:
                    address1 = fix_magic_quotes(address1)

                address2 = None
                if "venueAddress2" in item:
                    address2 = get_override_string_value_or_default(
                        item["venueAddress2"]
                    )
                elif custom_fields != {} and "venueAddress2" in custom_fields:
                    address2 = get_override_string_value_or_default(
                        custom_fields["venueAddress2"]
                    )

                if address2 is not None:
                    address2 = fix_magic_quotes(address2)
                    if address1 is not None and address1 != "":
                        address1 += ", " + address2
                    else:
                        address1 = address2

                city = None
                if "venueCity" in item:
                    city = get_override_string_value_or_default(item["venueCity"])
                elif custom_fields != {} and "venueCity" in custom_fields:
                    city = get_override_string_value_or_default(
                        custom_fields["venueCity"]
                    )

                if city is not None:
                    city = fix_magic_quotes(city)

                state = None
                if "venueState" in item:
                    state = get_override_string_value_or_default(item["venueState"])
                elif custom_fields != {} and "venueState" in custom_fields:
                    state = get_override_string_value_or_default(
                        custom_fields["venueState"]
                    )

                if state is not None:
                    state = fix_magic_quotes(state)

                zip_code = None
                if "venuePostalCode" in item:
                    zip_code = get_override_string_value_or_default(
                        item["venuePostalCode"]
                    )
                elif custom_fields != {} and "venuePostalCode" in custom_fields:
                    zip_code = get_override_string_value_or_default(
                        custom_fields["venuePostalCode"]
                    )

                if zip_code is not None:
                    zip_code = fix_magic_quotes(zip_code)

                country_name = None
                if "venueCountry" in item:
                    country_name = get_override_string_value_or_default(
                        item["venueCountry"]
                    )
                elif custom_fields != {} and "venueCountry" in custom_fields:
                    country_name = get_override_string_value_or_default(
                        custom_fields["venueCountry"]
                    )

                if country_name is not None:
                    country_name = fix_magic_quotes(country_name)

                timezone = None
                if custom_fields != {} and "timezone" in custom_fields:
                    timezone_str = get_override_string_value_or_default(
                        custom_fields["timezone"]
                    )
                    try:  # validate against pytz timezone that we are using
                        timezone = pytz.timezone(timezone_str).zone
                    except:  # pylint: disable=bare-except
                        timezone = None

                country = get_country_from_country_name(country_name, state, zip_code)
                if country is None:
                    country = Country(None, country_name, None)

                event_venue = TicketSocketVenue(
                    venue, address1, city, state, zip_code, country, timezone
                )
                event.venue = event_venue

                # date/time info
                display_date: str = None
                if "displayStartDate" in item:
                    display_date = get_override_string_value_or_default(
                        item["displayStartDate"]
                    )

                event_utc: int = 0
                if "start" in item:
                    event_utc = get_override_int_value_or_default(item["start"])

                # need at least one of them to be non-zero
                if display_date is None and event_utc == 0:
                    continue

                # note: this is a total hack since TicketSocket returns in UTC
                # BUT does NOT return a reliable timezone value for the venue
                # (yeah this is that bad - even when it's right,
                # it's a timezone that isn't convertible using Python or well...anything)
                # So what we do instead is define a "default offset" in the database
                # that roughly gets us the right date since we're not displaying times
                # from TS in the front end.  With any luck the "displayStartDate" comes back
                # with a valid value and we use that for our date instead

                try:
                    event_date = datetime.strptime(display_date, "%m/%d/%Y")
                    event.event_date = event_date.strftime("%Y-%m-%d")
                except Exception:  # pylint: disable=broad-exception-caught
                    event_time: int = event_utc + (self.utc_offset_hours * 60 * 60)
                    event.event_date = datetime.fromtimestamp(event_time).strftime(
                        "%Y-%m-%d"
                    )

                # ticket types
                ticket_types = []
                if "ticketTypes" in item:
                    ticket_types = self.get_ticket_types_from_event(item["ticketTypes"])
                event.ticket_types = ticket_types

                # orders
                event.orders = self.get_orders_from_event_id(event.event_id)

                self.events.append(event)
            logger.info(
                "TicketSocket events parsed ticket_socket_id=%s category=%s "
                "events=%s orders=%s duration=%.2fs",
                self.ticket_socket_id,
                event_category_id,
                len(self.events),
                sum(len(event.orders) for event in self.events),
                time.time() - parse_timer,
            )

        return self.events

    def get_ticket_types_from_event(self, ticket_types: list[Any]):
        """
        Fetch ticket types from event
        """
        if len(ticket_types) <= 0:
            return []

        ttypes: list[TicketSocketTicketType] = []
        order: int = 1
        for item in ticket_types:
            ticket_type_id = get_override_int_value_or_default(item["id"])

            # strip out anything in the name contained in parentheses
            name = get_override_string_value_or_default(item["name"])
            if name is not None and len(name) > 0:
                name = re.sub(r"\([^()]*\)", "", name)
                name = name.replace("  ", " ")
                name = name.strip()

            event_id = get_override_int_value_or_default(item["eventId"])
            total_available = get_override_int_value_or_default(item["quantity"])
            is_active: bool = True
            if "deleted" in item:
                is_active = not get_override_bool_value_or_default(item["deleted"])
            ttype = TicketSocketTicketType(
                event_id, ticket_type_id, name, total_available, is_active, order
            )
            ttypes.append(ttype)
            order += 1

        return ttypes

    def get_orders_from_event_id(self, event_id: int):
        """
        Get order data per event from TS
        """
        # get list of orderIds first
        order_ids = self.get_order_ids_from_event_id(event_id)

        # if there are no orders, return nothing
        if self.service_url is None or self.token is None:
            logger.error(
                "service url or token not present for ticket_socket_id %s",
                self.ticket_socket_id,
            )
            return []

        if len(order_ids) <= 0:
            return []

        def fetch_order(order_id: int):
            return self.get_order_from_order_id(order_id, event_id)

        worker_count = self.__get_order_fetch_worker_count(len(order_ids))
        orders: list[TicketSocketOrder] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for order in executor.map(fetch_order, order_ids):
                if order is not None:
                    orders.append(order)

        return orders

    def __get_order_fetch_worker_count(self, order_count: int):
        """
        Keep external API concurrency useful but bounded.
        """
        configured_worker_count = get_override_int_value_or_default(
            os.getenv("TS_ORDER_FETCH_WORKERS"), default=8
        )
        if configured_worker_count <= 0:
            configured_worker_count = 1
        return min(configured_worker_count, order_count)

    def get_order_from_order_id(self, order_id: int, event_id: int = 0):
        """
        API method to only return TS data for one order
        """
        if self.service_url is None or self.token is None:
            logger.error(
                "service url or token not present for ticket_socket_id %s",
                self.ticket_socket_id,
            )
            return None

        order: TicketSocketOrder = None

        url = "/api/v1/orders/" + str(order_id)

        json_data = get_https_response(
            host=self.service_url, url=url, bearer_token=self.token
        )

        if json_data is not None:
            incoming_order_id: int = 0
            if "id" in json_data:
                incoming_order_id = get_override_int_value_or_default(json_data["id"])

            if incoming_order_id > 0 and incoming_order_id == order_id:
                order = self.__parse_response_to_order_object(
                    incoming_order_id, event_id, json_data
                )

        return order

    def get_order_ids_from_event_id(self, event_id: int):
        """
        Fetch list of order ids from TS eventId
        """

        if self.service_url is None or self.token is None:
            logger.error(
                "service url or token not present for ticket_socket_id %s",
                self.ticket_socket_id,
            )
            return []

        order_ids: list[int] = []

        url = f"/api/v1/orders?eventId={str(event_id)}&limit=9999"

        json_data = get_https_response(
            host=self.service_url, url=url, bearer_token=self.token
        )

        if json_data is not None:
            for item in json_data:
                order_id: int = 0
                if "orderId" in item:
                    order_id = get_override_int_value_or_default(item["orderId"])
                if order_id != 0:
                    order_ids.append(order_id)

        return order_ids

    def __parse_response_to_order_object(
        self, order_id: int, event_id: int, json_data: any
    ):
        # get data from order
        order = TicketSocketOrder()
        order.order_id = order_id
        order.event_id = event_id

        if "cancelled" in json_data:
            order.cancelled = bool(json_data["cancelled"])

        if "deleted" in json_data:
            order.deleted = get_override_bool_value_or_default(json_data["deleted"])

        tickets = None
        if "tickets" in json_data:
            tickets = json_data["tickets"]

        total_count: int = 0
        if tickets is not None:
            if "totalCount" in tickets:
                total_count = get_override_int_value_or_default(tickets["totalCount"])

        order_tickets = []
        if total_count > 0:
            ticket_data = tickets["data"]
            for item in ticket_data:
                # if the ticket doesn't belong to this event, move along
                # and yes that happens that an order can contain tickets to multiple events
                item_event_id: int = 0
                if "eventId" in item:
                    item_event_id = get_override_int_value_or_default(item["eventId"])

                if item_event_id <= 0 or item_event_id != int(event_id):
                    continue

                if order.purchase_date is None and "purchaseDate" in item:
                    # datetime is not serializable in python,

                    purchase_unix_timestamp = get_override_int_value_or_default(
                        item["purchaseDate"]
                    )

                    purchase_date = datetime.fromtimestamp(
                        float(purchase_unix_timestamp)
                    )
                    order.purchase_date = purchase_date.strftime("%Y-%m-%d")
                    order.purchase_timestamp = purchase_date.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    order.purchase_unix_timestamp = purchase_unix_timestamp

                # must have a purchase date to continue
                if order.purchase_date is None:
                    continue

                shirt_size: str = None
                # set properties on order from ticket data if not present
                if order.user_id == 0 and "userId" in item:
                    order.user_id = get_override_int_value_or_default(item["userId"])
                if (
                    order.purchaser_first_name is None
                    or order.purchaser_first_name == ""
                ) and "billing_firstName" in item:
                    order.purchaser_first_name = get_override_string_value_or_default(
                        item["billing_firstName"]
                    )
                    if order.purchaser_first_name is not None:
                        order.purchaser_first_name = fix_magic_quotes(
                            order.purchaser_first_name
                        )
                if (
                    order.purchaser_last_name is None or order.purchaser_last_name == ""
                ) and "billing_lastName" in item:
                    order.purchaser_last_name = get_override_string_value_or_default(
                        item["billing_lastName"]
                    )
                    if order.purchaser_last_name is not None:
                        order.purchaser_last_name = fix_magic_quotes(
                            order.purchaser_last_name
                        )
                if order.purchaser_city is None and "billing_city" in item:
                    order.purchaser_city = get_override_string_value_or_default(
                        item["billing_city"]
                    )
                    if order.purchaser_city is not None:
                        order.purchaser_city = fix_magic_quotes(order.purchaser_city)
                if order.purchaser_state is None and "billing_state" in item:
                    order.purchaser_state = get_override_string_value_or_default(
                        item["billing_state"]
                    )
                    if order.purchaser_state is not None:
                        order.purchaser_state = fix_magic_quotes(order.purchaser_state)
                if order.purchaser_zip_code is None and "billing_zip" in item:
                    order.purchaser_zip_code = get_override_string_value_or_default(
                        item["billing_zip"]
                    )
                    if order.purchaser_zip_code is not None:
                        order.purchaser_zip_code = fix_magic_quotes(
                            order.purchaser_zip_code
                        )
                if order.purchaser_country is None and "billing_country" in item:
                    order.purchaser_country = get_override_string_value_or_default(
                        item["billing_country"]
                    )
                    if order.purchaser_country is not None:
                        order.purchaser_country = fix_magic_quotes(
                            order.purchaser_country
                        )
                if order.purchaser_ip_address is None and "remoteAddr" in item:
                    order.purchaser_ip_address = get_override_string_value_or_default(
                        item["remoteAddr"]
                    )
                    if order.purchaser_ip_address is not None:
                        order.purchaser_ip_address = fix_magic_quotes(
                            order.purchaser_ip_address
                        )

                if (order.email is None or order.email == "") and "email" in item:
                    order.email = get_override_string_value_or_default(item["email"])

                if (order.phone is None or order.phone == "") and "phone" in item:
                    order.phone = get_override_string_value_or_default(item["phone"])

                if (
                    order.phone is None or order.phone == ""
                ) and "billing_phone" in item:
                    order.phone = get_override_string_value_or_default(
                        item["billing_phone"]
                    )

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
                        question: str = None
                        if "question" in question_item:
                            question = get_override_string_value_or_default(
                                question_item["question"]
                            )
                            if question is not None:
                                question = question.lower()

                        if question is None or question == "":
                            continue

                        answer: str = None
                        if "answerText" in question_item:
                            answer = get_override_string_value_or_default(
                                question_item["answerText"]
                            )

                        if answer is not None and answer != "":
                            if question.find("phone") >= 0 and (
                                order.phone is None or order.phone == ""
                            ):
                                order.phone = get_override_string_value_or_default(
                                    answer
                                )
                            elif question.find("shirt") >= 0:
                                shirt_size = answer

                # create the ticket object
                price: float = 0
                if "price" in item:
                    price = get_override_float_value_or_default(item["price"])

                ticket_id: int = 0
                if "id" in item:
                    ticket_id = get_override_int_value_or_default(item["id"])

                ticket_type: str = None
                if "ticketTypeName" in item:
                    ticket_type = get_override_string_value_or_default(
                        item["ticketTypeName"]
                    )

                service_fee: float = 0
                if "fee1Amount" in item:
                    service_fee = get_override_float_value_or_default(
                        item["fee1Amount"]
                    )

                ticket_type_id: int = 0
                if "typeId" in item:
                    ticket_type_id = get_override_int_value_or_default(item["typeId"])

                barcode: str = None
                if "barcode" in item:
                    barcode = get_override_string_value_or_default(item["barcode"])

                available_scans: int = 0
                if "availableScans" in item:
                    available_scans = get_override_int_value_or_default(
                        item["availableScans"]
                    )

                purchase_location: str = None
                if "purchaseLocation" in item:
                    purchase_location = get_override_string_value_or_default(
                        item["purchaseLocation"]
                    )

                scanned_timestamp: int = 0
                if "scannedTimestamp" in item:
                    scanned_timestamp = get_override_int_value_or_default(
                        item["scannedTimestamp"]
                    )

                attendee_first_name: str = None
                if "partyMember" in item:
                    attendee_first_name = get_override_string_value_or_default(
                        item["partyMember"]
                    )
                    if attendee_first_name is not None:
                        attendee_first_name = fix_magic_quotes(attendee_first_name)
                attendee_last_name: str = None
                if "partyMemberLastName" in item:
                    attendee_last_name = get_override_string_value_or_default(
                        item["partyMemberLastName"]
                    )
                    if attendee_last_name is not None:
                        attendee_last_name = fix_magic_quotes(attendee_last_name)

                if ticket_id == 0 or ticket_type is None or ticket_type == "":
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
                    if len(shirt_size) > 0:
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

        if len(order_tickets) > 0:
            order.tickets = order_tickets
        return order
