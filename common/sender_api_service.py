"""
Sender API module
"""

from datetime import datetime
import pytz
import time
import os
import traceback
import requests

from common import db
from common.models.sender_api import Subscriber
from common.utility import (
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    log_message,
)


class SenderApiService:
    """
    Service to interact with Sender API
    """

    def get_subscriber_by_email(self, email: str):
        """
        Get all subscribers from Sender API
        """
        subscriber: Subscriber = None

        host = os.getenv("SENDER_BASE_URL")
        url = f"{host}/subscribers/{email}"
        token = os.getenv("SENDER_API_KEY")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = requests.request("GET", url, headers=headers, timeout=3000)
            subscriber_json = response.json()
            if subscriber_json is not None and "data" in subscriber_json:
                data = subscriber_json["data"]
                subscriber = Subscriber()
                subscriber.id = get_override_string_value_or_default(data["id"])
                subscriber.email = get_override_string_value_or_default(data["email"])
                subscriber.first_name = get_override_string_value_or_default(
                    data["firstname"]
                )
                subscriber.last_name = get_override_string_value_or_default(
                    data["lastname"]
                )
                subscriber.phone = get_override_string_value_or_default(data["phone"])
                if data["columns"] is not None:
                    for column in data["columns"]:
                        if column["title"] == "Band":
                            subscriber.band = get_override_string_value_or_default(
                                column["value"]
                            )
                        elif column["title"] == "Venue":
                            subscriber.venue = get_override_string_value_or_default(
                                column["value"]
                            )
                        elif column["title"] == "Venue Address":
                            subscriber.venue_address = (
                                get_override_string_value_or_default(column["value"])
                            )
                        elif column["title"] == "Venue City":
                            subscriber.venue_city = (
                                get_override_string_value_or_default(column["value"])
                            )
                        elif column["title"] == "Venue State":
                            subscriber.venue_state = (
                                get_override_string_value_or_default(column["value"])
                            )
                        elif column["title"] == "Venue Zip":
                            subscriber.venue_zip = get_override_string_value_or_default(
                                column["value"]
                            )
                        elif column["title"] == "Venue Country":
                            subscriber.venue_country = (
                                get_override_string_value_or_default(column["value"])
                            )
                        elif column["title"] == "Purchaser Zip":
                            subscriber.purchaser_zip = (
                                get_override_string_value_or_default(column["value"])
                            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            pacific_tz = pytz.timezone("America/Los_Angeles")
            now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
            log_message(f"""[{now}] - {error_message}\r\n""")

        return subscriber

    def create_subscriber(self, subscriber: Subscriber):
        """
        Create new subscriber in Sender API
        """

        host = os.getenv("SENDER_BASE_URL")
        url = f"{host}/subscribers"
        token = os.getenv("SENDER_API_KEY")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        fields = {
            "{$purchaser_zip}": get_override_string_value_or_default(
                subscriber.purchaser_zip
            ),
            "{$venue}": get_override_string_value_or_default(subscriber.venue),
            "{$venue_address}": get_override_string_value_or_default(
                subscriber.venue_address
            ),
            "{$venue_city}": get_override_string_value_or_default(
                subscriber.venue_city
            ),
            "{$venue_state}": get_override_string_value_or_default(
                subscriber.venue_state
            ),
            "{$venue_zip}": get_override_string_value_or_default(subscriber.venue_zip),
            "{$venue_country}": get_override_string_value_or_default(
                subscriber.venue_country
            ),
            "{$band}": get_override_string_value_or_default(subscriber.band),
        }

        payload = {
            "email": get_override_string_value_or_default(subscriber.email),
            "firstname": get_override_string_value_or_default(subscriber.first_name),
            "lastname": get_override_string_value_or_default(subscriber.last_name),
            "phone": get_override_string_value_or_default(subscriber.phone),
            "fields": fields,
        }

        response = requests.request(
            "POST", url, headers=headers, json=payload, timeout=3000
        )
        response_json = response.json()

        success: bool = False
        if response_json is not None and "success" in response_json:
            success = bool(response_json["success"])

        if success is False:
            fail_msg = f"Error creating subscriber {subscriber.email}"
            err_msg: str = None
            if response_json is not None:
                err_msg = (
                    response_json["message"]
                    if response_json["message"] is not None
                    else None
                )
            if err_msg is not None:
                fail_msg += " - " + err_msg
                if err_msg.lower().find("phone") >= 0: # invalid phone, clear out and try again
                    self.clear_subscriber_phone(subscriber.order_id)
                elif err_msg.lower().find("email") >= 0: # invalid email, cannot be a subscriber
                    self.update_subscriber_order(subscriber.order_id)
            print(fail_msg)

        return success

    def update_subscriber(self, subscriber: Subscriber):
        """
        Update existing subscriber in Sender API
        """

        host = os.getenv("SENDER_BASE_URL")
        url = f"{host}/subscribers/{subscriber.id}"
        token = os.getenv("SENDER_API_KEY")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        fields = {
            "{$purchaser_zip}": get_override_string_value_or_default(
                subscriber.purchaser_zip
            ),
            "{$venue}": get_override_string_value_or_default(subscriber.venue),
            "{$venue_address}": get_override_string_value_or_default(
                subscriber.venue_address
            ),
            "{$venue_city}": get_override_string_value_or_default(
                subscriber.venue_city
            ),
            "{$venue_state}": get_override_string_value_or_default(
                subscriber.venue_state
            ),
            "{$venue_zip}": get_override_string_value_or_default(subscriber.venue_zip),
            "{$venue_country}": get_override_string_value_or_default(
                subscriber.venue_country
            ),
            "{$band}": get_override_string_value_or_default(subscriber.band),
        }

        payload = {
            "email": get_override_string_value_or_default(subscriber.email),
            "firstname": get_override_string_value_or_default(subscriber.first_name),
            "lastname": get_override_string_value_or_default(subscriber.last_name),
            "phone": get_override_string_value_or_default(subscriber.phone),
            "fields": fields,
        }

        response = requests.request(
            "PATCH", url, headers=headers, json=payload, timeout=3000
        )
        response_json = response.json()

        success: bool = False
        if response_json is not None and "success" in response_json:
            success = bool(response_json["success"])

        if success is False:
            fail_msg = f"Error updating subscriber {subscriber.email}"
            err_msg: str = None
            if response_json is not None:
                err_msg = (
                    response_json["message"]
                    if response_json["message"] is not None
                    else None
                )
            if err_msg is not None:
                fail_msg += " - " + err_msg
                if err_msg.lower().find("phone") >= 0: # invalid phone, clear out and try again
                    self.clear_subscriber_phone(subscriber.order_id)
                elif err_msg.lower().find("email") >= 0: # invalid email, cannot be a subscriber
                    self.update_subscriber_order(subscriber.order_id)
            print(fail_msg)

        return success

    def update_sender_subscribers(self):
        """
        Update SenderAPI with subscribers from database
        """
        stored_subscribers = self.get_sender_subscribers_from_db(500)

        subscribers_processed: int = 0
        subscribers_updated: int = 0
        subscribers_added: int = 0
        existing_subscribers_with_error: list[str] = []
        new_subscribers_with_error: list[str] = []

        if len(stored_subscribers) > 0:
            try:
                for db_subscriber in stored_subscribers:
                    existing_subscriber = self.get_subscriber_by_email(
                        db_subscriber.email
                    )

                    subscribers_processed += 1
                    if existing_subscriber is not None:
                        db_subscriber.id = existing_subscriber.id
                        success = self.update_subscriber(db_subscriber)
                        if success is True:
                            subscribers_updated += 1
                        else:
                            existing_subscribers_with_error.append(db_subscriber.email)
                    else:
                        success = self.create_subscriber(db_subscriber)
                        if success is True:
                            subscribers_added += 1
                        else:
                            new_subscribers_with_error.append(db_subscriber.email)

                    if success is True and db_subscriber.order_id > 0:
                        success = self.update_subscriber_order(db_subscriber.order_id)

                    time.sleep(1.5)

            except Exception as error:  # pylint: disable=broad-exception-caught
                error_message: str = str(error) + "\n" + traceback.format_exc()
                pacific_tz = pytz.timezone("America/Los_Angeles")
                now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
                log_message(f"""[{now}] - {error_message}\r\n""")

        results = {
            "total_subscribers_fetched": len(stored_subscribers),
            "subscribers_processed": subscribers_processed,
            "subscribers_added": subscribers_added,
            "subscribers_updated": subscribers_updated,
            "existing_subscribers_with_error": existing_subscribers_with_error,
            "new_subscribers_with_error": new_subscribers_with_error,
        }

        return results

    def update_subscriber_order(self, order_id: int):
        """
        Sets the order as already updated with Sender
        """
        sql = """UPDATE TicketSocketOrders SET IsSenderUpdated=1,
            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
            WHERE Id=%(orderId)s"""
        data = {"orderId": order_id}
        return db.db_update(sql, data)

    def clear_subscriber_phone(self, order_id: int):
        """
        Clears out the phone number if it errors out with Sender
        """
        sql = """UPDATE TicketSocketOrders SET Phone=NULL,
            IsSenderUpdated=0,
            LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
            WHERE Id=%(orderId)s"""
        data = {"orderId": order_id}
        return db.db_update(sql, data)

    def get_missing_subscribers_csv(self):
        """
        Gets all subscribers from database and converts to CSV
        """
        missing_subscribers: list[Subscriber] = []
        stored_subscribers = self.get_sender_subscribers_from_db()
        for db_subscriber in stored_subscribers:
            existing_subscriber = self.get_subscriber_by_email(db_subscriber.email)
            if existing_subscriber is None:
                missing_subscribers.append(db_subscriber)
            time.sleep(1)

        return self.get_subscribers_csv(missing_subscribers)

    def get_sender_subscribers_csv(self):
        """
        Gets all subscribers from database and converts to CSV
        """
        stored_subscribers = self.get_sender_subscribers_from_db()
        return self.get_subscribers_csv(stored_subscribers)

    def get_subscribers_csv(self, stored_subscribers: list[Subscriber]):
        """
        Convert subscribers into CSV
        """
        f = open("subscribers.csv", "w", encoding="utf-8")

        csv: str = (
            '"Email","First name","Last name","Phone number","Purchaser Zip","Venue",'
        )
        csv += '"Venue Address","Venue City","Venue State","Venue Zip","Venue Country","Band"'
        csv += "\n"
        f.write(csv)
        if len(stored_subscribers) > 0:
            for s in stored_subscribers:
                email = get_override_string_value_or_default(s.email, default="")
                first_name = get_override_string_value_or_default(
                    s.first_name, default=""
                )
                last_name = get_override_string_value_or_default(
                    s.last_name, default=""
                )
                phone = get_override_string_value_or_default(s.phone, default="")
                purchaser_zip = get_override_string_value_or_default(
                    s.purchaser_zip, default=""
                )
                venue = get_override_string_value_or_default(s.venue, default="")
                venue_address = get_override_string_value_or_default(
                    s.venue_address, default=""
                )
                venue_city = get_override_string_value_or_default(
                    s.venue_city, default=""
                )
                venue_state = get_override_string_value_or_default(
                    s.venue_state, default=""
                )
                venue_zip = get_override_string_value_or_default(
                    s.venue_zip, default=""
                )
                venue_country = get_override_string_value_or_default(
                    s.venue_country, default=""
                )
                band = get_override_string_value_or_default(s.band, default="")

                csv = f'"{email}","{first_name}","{last_name}","{phone}",'
                csv += f'"{purchaser_zip}","{venue}","{venue_address}","{venue_city}",'
                csv += f'"{venue_state}","{venue_zip}","{venue_country}","{band}"'
                csv += "\n"
                f.write(csv)

        f.close()

        return True

    def get_sender_subscribers_from_db(self, limit: int = 0):
        """
        Build list of subscribers from TicketSocketOrders
        """

        try:
            data = {}

            stored_subscribers: list[Subscriber] = []

            sql = """SELECT DISTINCT TicketSocketOrders.PurchaserLastName,
                        TicketSocketOrders.PurchaserFirstName, 
                        TicketSocketOrders.Email,
                        COALESCE(TicketSocketOrders.PhoneFormatted, TicketSocketOrders.Phone) as Phone,
                        TicketSocketOrders.PurchaserZip,
                        COALESCE(ExternalEventVenues.Venue, TicketSocketEvents.Venue) as Venue,
                        COALESCE(ExternalEventVenues.Address, TicketSocketEvents.Address) AS VenueAddress,
                        COALESCE(ExternalEventVenues.City, TicketSocketEvents.City) AS VenueCity,
                        COALESCE(ExternalEventVenues.State, TicketSocketEvents.State) AS VenueState,
                        COALESCE(ExternalEventVenues.Zip, TicketSocketEvents.Zip) AS VenueZip,
                        COALESCE(Country.CountryName, TicketSocketEvents.Country) AS VenueCountry,
                        Sellers.Name as Band,
                        TicketSocketOrders.Id as OrderId 
                    FROM TicketSocketOrders 
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
                    JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId
                    LEFT JOIN ExternalEvents ON ExternalEvents.TicketSocketEventId = TicketSocketEvents.Id
                    LEFT JOIN ExternalEventVenues ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
                    LEFT JOIN Country ON Country.CountryId = ExternalEventVenues.CountryId
                    WHERE COALESCE(TicketSocketOrders.Email, '') <> ''
                    AND TicketSocketOrders.IsDeleted <> 1
                    AND TicketSocketOrders.IsSenderUpdated <> 1 
                    ORDER BY TicketSocketOrders.PurchaseDate DESC
                    """

            if limit > 0:
                sql += """ LIMIT 0, %(limit)s"""
                data["limit"] = limit

            rows = db.db_query_all(sql, data)
            for row in rows:
                new_sub = Subscriber()
                new_sub.email = get_override_string_value_or_default(row["Email"])
                new_sub.first_name = get_override_string_value_or_default(
                    row["PurchaserFirstName"]
                )
                new_sub.last_name = get_override_string_value_or_default(
                    row["PurchaserLastName"]
                )
                new_sub.purchaser_zip = get_override_string_value_or_default(
                    row["PurchaserZip"], default=""
                )
                new_sub.venue = get_override_string_value_or_default(
                    row["Venue"], default=""
                )
                new_sub.venue_address = get_override_string_value_or_default(
                    row["VenueAddress"], default=""
                )
                new_sub.venue_city = get_override_string_value_or_default(
                    row["VenueCity"], default=""
                )
                new_sub.venue_state = get_override_string_value_or_default(
                    row["VenueState"], default=""
                )
                new_sub.venue_zip = get_override_string_value_or_default(
                    row["VenueZip"], default=""
                )
                venue_country = get_override_string_value_or_default(
                    row["VenueCountry"], default=""
                )
                new_sub.venue_country = venue_country

                new_sub.phone = get_override_string_value_or_default(
                    row["Phone"], default=""
                )

                new_sub.band = get_override_string_value_or_default(
                    row["Band"], default=""
                )
                new_sub.order_id = get_override_int_value_or_default(row["OrderId"])

                stored_subscribers.append(new_sub)

        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            pacific_tz = pytz.timezone("America/Los_Angeles")
            now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
            log_message(f"""[{now}] - {error_message}\r\n""")

        return stored_subscribers
