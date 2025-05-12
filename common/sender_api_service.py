"""
Sender API module
"""

from datetime import datetime
import time
import os
import traceback
import requests

from common import db
from common.models.sender_api import Subscriber
from common.utility import log_message


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
                subscriber.id = data["id"]
                subscriber.email = data["email"]
                subscriber.first_name = data["firstname"]
                subscriber.last_name = data["lastname"]
                subscriber.phone = data["phone"]
                if data["columns"] is not None:
                    for column in data["columns"]:
                        if column["title"] == "Band":
                            subscriber.band = column["value"]
                        elif column["title"] == "Venue":
                            subscriber.venue = column["value"]
                        elif column["title"] == "Venue Address":
                            subscriber.venue_address = column["value"]
                        elif column["title"] == "Venue City":
                            subscriber.venue_city = column["value"]
                        elif column["title"] == "Venue State":
                            subscriber.venue_state = column["value"]
                        elif column["title"] == "Venue Zip":
                            subscriber.venue_zip = column["value"]
                        elif column["title"] == "Venue Country":
                            subscriber.venue_country = column["value"]
                        elif column["title"] == "Purchaser Zip":
                            subscriber.purchaser_zip = column["value"]
        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            "{$purchaser_zip}": subscriber.purchaser_zip,
            "{$venue}": subscriber.venue,
            "{$venue_address}": subscriber.venue_address,
            "{$venue_city}": subscriber.venue_city,
            "{$venue_state}": subscriber.venue_state,
            "{$venue_zip}": subscriber.venue_zip,
            "{$venue_country}": subscriber.venue_country,
            "{$band}": subscriber.band,
        }

        payload = {
            "email": subscriber.email,
            "firstname": subscriber.first_name,
            "lastname": subscriber.last_name,
            "phone": subscriber.phone,
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
            print("false")

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
            "{$purchaser_zip}": subscriber.purchaser_zip,
            "{$venue}": subscriber.venue,
            "{$venue_address}": subscriber.venue_address,
            "{$venue_city}": subscriber.venue_city,
            "{$venue_state}": subscriber.venue_state,
            "{$venue_zip}": subscriber.venue_zip,
            "{$venue_country}": subscriber.venue_country,
            "{$band}": subscriber.band,
        }

        payload = {
            "email": subscriber.email,
            "firstname": subscriber.first_name,
            "lastname": subscriber.last_name,
            "phone": subscriber.phone,
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
            print("false")

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
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                email = s.email if s.email is not None else ""
                first_name = s.first_name if s.first_name is not None else ""
                last_name = s.last_name if s.last_name is not None else ""
                phone = s.phone if s.phone is not None else ""
                purchaser_zip = s.purchaser_zip if s.purchaser_zip is not None else ""
                venue = s.venue if s.venue is not None else ""
                venue_address = s.venue_address if s.venue_address is not None else ""
                venue_city = s.venue_city if s.venue_city is not None else ""
                venue_state = s.venue_state if s.venue_state is not None else ""
                venue_zip = s.venue_zip if s.venue_zip is not None else ""
                venue_country = s.venue_country if s.venue_country is not None else ""
                band = s.band if s.band is not None else ""

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
                        TicketSocketOrders.Phone,
                        TicketSocketOrders.PurchaserZip,
                        COALESCE(ExternalEventVenues.Venue, TicketSocketEvents.Venue) as Venue,
                        TicketSocketEvents.Address AS VenueAddress,
                        TicketSocketEvents.City AS VenueCity,
                        TicketSocketEvents.State AS VenueState,
                        TicketSocketEvents.Zip AS VenueZip,
                        TicketSocketEvents.Country AS VenueCountry,
                        ExternalEventVenues.Address AS ExternalAddress, 
                        ExternalEventVenues.City AS ExternalCity, 
                        ExternalEventVenues.State AS ExternalState, 
                        ExternalEventVenues.Zip AS ExternalZip, 
                        ExternalEventVenues.Country AS ExternalCountry, 
                        Sellers.Name as Band,
                        TicketSocketOrders.Id as OrderId 
                    FROM TicketSocketOrders 
                    JOIN TicketSocketEvents ON TicketSocketEvents.Id = TicketSocketOrders.TicketSocketEventId 
                    JOIN SellerEventCategory ON SellerEventCategory.SellerEventCategoryId = TicketSocketEvents.SellerEventCategoryId
                    JOIN Sellers ON Sellers.SellerId = SellerEventCategory.SellerId
                    LEFT JOIN ExternalEvents ON ExternalEvents.TicketSocketEventId = TicketSocketEvents.Id
                    LEFT JOIN ExternalEventVenues ON ExternalEventVenues.VenueID = ExternalEvents.ExternalEventVenueId
                    WHERE COALESCE(TicketSocketOrders.Email, '') <> ''
                    AND TicketSocketOrders.IsDeleted <> 1
                    AND TicketSocketOrders.IsSenderUpdated <> 1 
                    AND NOT EXISTS (SELECT 1 FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=TicketSocketOrders.Id and IsRefunded=1)
                    """

            if limit > 0:
                sql += """ LIMIT 0, %(limit)s"""
                data["limit"] = limit

            rows = db.db_query_all(sql, data)
            for row in rows:
                new_sub = Subscriber()
                new_sub.email = str(row["Email"])
                new_sub.first_name = (
                    str(row["PurchaserFirstName"])
                    if row["PurchaserFirstName"] is not None
                    else ""
                )
                new_sub.last_name = (
                    str(row["PurchaserLastName"])
                    if row["PurchaserLastName"] is not None
                    else ""
                )
                new_sub.purchaser_zip = (
                    str(row["PurchaserZip"]) if row["PurchaserZip"] is not None else ""
                )
                new_sub.venue = str(row["Venue"]) if row["Venue"] is not None else None
                venue_address = (
                    str(row["VenueAddress"]) if row["VenueAddress"] is not None else ""
                )
                external_address = (
                    str(row["ExternalAddress"])
                    if row["ExternalAddress"] is not None
                    else ""
                )
                new_sub.venue_address = (
                    external_address if external_address is not None else venue_address
                )
                venue_city = (
                    str(row["VenueCity"]) if row["VenueCity"] is not None else ""
                )
                external_city = (
                    str(row["ExternalCity"]) if row["ExternalCity"] is not None else ""
                )
                new_sub.venue_city = (
                    external_city if external_city is not None else venue_city
                )
                venue_state = (
                    str(row["VenueState"]) if row["VenueState"] is not None else ""
                )
                external_state = (
                    str(row["ExternalState"])
                    if row["ExternalState"] is not None
                    else ""
                )
                new_sub.venue_state = (
                    external_state if external_state is not None else venue_state
                )
                venue_zip = str(row["VenueZip"]) if row["VenueZip"] is not None else ""
                external_zip = (
                    str(row["ExternalZip"]) if row["ExternalZip"] is not None else ""
                )
                new_sub.venue_zip = (
                    external_zip if external_zip is not None else venue_zip
                )
                venue_country = (
                    str(row["VenueCountry"]) if row["VenueCountry"] is not None else ""
                )
                external_country = (
                    str(row["ExternalCountry"])
                    if row["ExternalCountry"] is not None
                    else ""
                )
                new_sub.venue_country = (
                    external_country if external_country is not None else venue_country
                )

                phone = str(row["Phone"]) if row["Phone"] is not None else ""

                if (
                    venue_country == "USA"
                    or venue_country == "United States"
                    or venue_country == "Canada"
                ):
                    new_sub.phone = (
                        self.__format_us_or_canada_phone_number_for_sender_api(phone)
                    )
                else:
                    new_sub.phone = None

                new_sub.band = str(row["Band"]) if row["Band"] is not None else ""
                new_sub.order_id = (
                    int(row["OrderId"]) if row["OrderId"] is not None else 0
                )

                stored_subscribers.append(new_sub)

        except Exception as error:  # pylint: disable=broad-exception-caught
            error_message: str = str(error) + "\n" + traceback.format_exc()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message(f"""[{now}] - {error_message}\r\n""")

        return stored_subscribers

    def __format_us_or_canada_phone_number_for_sender_api(self, phone: str):
        if phone is None or phone.strip() == "":
            return ""

        phone = phone.replace("+1", "")
        phone = phone.replace("(", "")
        phone = phone.replace(")", "")
        phone = phone.replace("-", "")
        phone = phone.replace(" ", "")
        return f"+1{phone}"
