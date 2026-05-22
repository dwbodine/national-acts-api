"""
Class for Twilio/SendGrid/messaging
"""

from datetime import datetime
import os
import traceback
import pytz

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, ReplyTo

from common.db import db_insert, db_query_one, db_update
from common.models.messaging import SendEmailResult


class MessagingService:
    """
    API methods for Twilio/SendGrid/messaging
    """

    def generate_google_auth_token(self, google_id: str):
        """
        Generates a new Google Auth Token for spam prevention
        """
        pacific_tz = pytz.timezone("America/Los_Angeles")
        if google_id is None or len(google_id.strip()) == 0:
            return -1

        success: bool = True
        token_id: int = 0

        sql = """INSERT INTO GAuth (GoogleID, Expiration, Issued)
            VALUES (%(google_id)s, %(expiration)s,
            CURRENT_TIMESTAMP)"""

        time = datetime.now(pacific_tz).timestamp() + 120
        expiration = datetime.fromtimestamp(time).strftime("%Y-%m-%d %H:%M:%S")

        data = {"google_id": google_id, "expiration": expiration}
        token_id = db_insert(sql, data)
        success = token_id > 0
        return token_id if success is True else 0

    def validate_google_auth_token(self, google_id: str, token_id: int):
        """
        Validate Google Auth token to prevent spam in contact form
        """
        pacific_tz = pytz.timezone("America/Los_Angeles")
        if (
            google_id is None
            or len(google_id.strip()) == 0
            or token_id is None
            or token_id == 0
        ):
            return -1

        valid: int = 0
        success: bool = True
        sql = """SELECT Expiration FROM GAuth
                    WHERE GoogleID=%(google_id)s
                    AND TokenID=%(token_id)s
                    AND Redeemed IS NULL"""
        data = {"google_id": google_id, "token_id": token_id}

        row = db_query_one(sql, data)
        if row:
            time_str = (
                str(row["Expiration"]).strip()
                if row["Expiration"] is not None
                else None
            )
            if time_str is not None:
                time_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                time: float = pacific_tz.localize(time_dt).timestamp()
                now = datetime.now(pacific_tz).timestamp()
                if time > now:
                    valid = 1
                else:
                    valid = -3

        if valid == 1:
            update_sql = """UPDATE GAuth
                            SET Redeemed=CURRENT_TIMESTAMP
                            WHERE TokenID=%(token_id)s AND GoogleID=%(google_id)s"""
            success = db_update(update_sql, data)

        return valid if success is True else 0

    def send_email(
        self,
        to_email_address: str,
        subject: str,
        html_content: str,
        to_name: str = None,
        cc_emails: list[str] = None,
        reply_to: str = None,
        reply_to_name: str = None,
        from_address: str = None,
        from_name: str = None,
    ):
        """
        Utility to send email through Twilio yep yep yep
        """
        if from_address is None:
            from_address = "info@nationalactsvip.com"
        if from_name is None:
            from_name = "National Acts VIP Customer Service"
        from_email = From(from_address, from_name)

        if to_name is not None and to_name != "":
            to_email = To(to_email_address, to_name)
        else:
            to_email = to_email_address

        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )

        if cc_emails is not None:
            for email in cc_emails:
                message.add_cc(email)

        if reply_to is not None:
            if reply_to_name is None:
                reply_to_name = reply_to
            message.reply_to = ReplyTo(reply_to, reply_to_name)

        result: SendEmailResult = None
        try:
            send_grid_key = os.environ.get("SENDGRID_API_KEY")
            sg = SendGridAPIClient(send_grid_key)
            sg.send(message)
            result = SendEmailResult(True, None)
        except Exception as e:  # pylint: disable=broad-exception-caught
            result = SendEmailResult(False, str(e) + "\n" + traceback.format_exc())

        return result
