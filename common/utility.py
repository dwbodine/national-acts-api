"""
Utilites for Python app
"""

import json
import re
import os
import http.client
from datetime import datetime
import traceback
from types import SimpleNamespace
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To
from stringcase import camelcase, snakecase


class CamelCaseJsonEncoder(json.JSONEncoder):
    """
    Custom JSON encoder
    """

    def default(self, o):
        d = o.__dict__
        for k in list(d):
            d[(camelcase(k))] = d.pop(k)
        return {**d}


class SnakeCaseJsonEncoder(json.JSONEncoder):
    """
    Custom JSON encoder
    """

    def default(self, o):
        d = o.__dict__
        for k in list(d):
            d[(snakecase(k))] = d.pop(k)
        return {**d}


def replace_none(data):
    """
    Utility to replace JSON string 'None' with actual None value
    """
    for k, v in data.items() if isinstance(data, dict) else enumerate(data):
        if v == "None":
            data[k] = None
        elif isinstance(v, (dict, list)):
            replace_none(v)


def convert_json_to_snake_case_object(request_json: any, typed_object: any):
    """
    Serializes any JSON to a simple dictionary object
    in snake case
    """
    camel_case_json = convert_to_json(request_json)

    camel_case_event = json.loads(
        camel_case_json,
        object_hook=lambda d: SimpleNamespace(**d),
    )

    data = convert_to_snake_case(camel_case_event)

    simple_snake_case_object = json.loads(
        data, object_hook=lambda d: SimpleNamespace(**d)
    )

    replace_none(simple_snake_case_object.__dict__)

    typed_object.__dict__.update(simple_snake_case_object.__dict__)
    return typed_object


class SendEmailResult:
    """
    Class for sending email
    """

    def __init__(self, success: bool, error: str = None):
        self.success = success
        self.error = error


def send_email(
    to_email_address: str,
    subject: str,
    html_content: str,
    to_name: str = None,
    cc_emails: list[str] = None,
):
    """
    Utility to send email through Twilio
    """
    from_email = From("info@national-acts.com", "National Acts VIP")

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

    result: SendEmailResult = None
    try:
        send_grid_key = os.environ.get("SENDGRID_API_KEY")
        sg = SendGridAPIClient(send_grid_key)
        sg.send(message)
        result = SendEmailResult(True, None)
    except Exception as e:  # pylint: disable=broad-exception-caught
        result = SendEmailResult(False, str(e) + "\n" + traceback.format_exc())

    return result


def convert_to_json(obj: any):
    """
    Convert any object to JSON
    """
    return json.dumps(obj, indent=4, ensure_ascii=False, cls=CamelCaseJsonEncoder)


def convert_to_snake_case(obj: any):
    """
    Convert any object to snake-case JSON
    """
    return json.dumps(obj, indent=4, ensure_ascii=False, cls=SnakeCaseJsonEncoder)


def format_phone(raw: str):
    """
    Formatting for USA phone numbers
    """
    parsed = re.sub("[^0-9]", "", raw)
    phone = parsed
    if len(parsed) >= 10:
        if len(parsed) > 10 and parsed[0:1] == "1":
            parsed = parsed[1:11]
        else:
            parsed = parsed[0:10]
        phone = "(" + parsed[0:3] + ") " + parsed[3:6] + "-" + parsed[6:]
    elif len(parsed) >= 7:
        phone = parsed[0:3] + "-" + parsed[3:7]

    return phone


def fix_magic_quotes(raw: str):
    """
    Replace unicode magic quotes with ASCII equivalents
    """
    raw = raw.replace("\u201c", '"')
    raw = raw.replace("\u201d", '"')
    raw = raw.replace("\u2018", "'")
    raw = raw.replace("\u2019", "'")
    return raw


def add_months(current_date: datetime, months_to_add: int):
    """
    Add a number of months to a date
    """
    new_date = datetime(
        current_date.year + (current_date.month + months_to_add - 1) // 12,
        (current_date.month + months_to_add - 1) % 12 + 1,
        current_date.day,
    )
    return new_date


def validate_email_address(email: str):
    """
    Validate email address
    """
    regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
    return re.fullmatch(regex, email)


def log_message(msg: str):
    """
    Write message to the log
    """
    date_str = datetime.now().isoformat()
    print("[" + date_str + "] " + msg)


def get_https_response(
    host: str, url: str, bearer_token: str = None, api_key: str = None
):
    """
    Make consistent API GET calls
    """
    headers: dict[str, any] = {
        "Accept": "application/json",
        "Content-type": "application/json;charset=UTF-8",
    }
    if bearer_token is not None:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if api_key is not None:
        headers["x-api-key"] = api_key

    json_data = None
    try:
        conn = http.client.HTTPSConnection(
            host=host, port=443, timeout=3000, check_hostname=False
        )
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        if response.status == 200:
            json_response = json.loads(response.read())
            if "data" in json_response:
                json_data = json_response["data"]
                if json_data is not None:
                    log_message(f"get_https_response succeeded for {host}{url}")
        else:
            log_message(
                f"""post_https_response failed for {host}{url} -
                    status: {response.status}, reason: {response.reason}"""
            )
    except Exception as error:  # pylint: disable=broad-exception-caught
        json_data = None
        error_message: str = str(error) + "\n" + traceback.format_exc()
        subject = "Error in get_https_response - " + datetime.now().strftime(
            "%m/%d/%Y %H:%M:%S"
        )
        html = f"get_https_response failed for {host}{url}\n"
        html += error_message
        to = "dwbodine@gmail.com"
        to_name = "dB"
        send_email(to, subject, html, to_name)
    finally:
        if conn is not None:
            conn.close()

    return json_data


def post_https_response(
    host: str, url: str, payload: str, api_key: str = None, bearer_token: str = None
):
    """
    Make consistent API POST calls
    """
    headers: dict[str, any] = {
        "Accept": "application/json",
        "Content-type": "application/json;charset=UTF-8",
    }
    if bearer_token is not None:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if api_key is not None:
        headers["x-api-key"] = api_key

    json_data = None
    try:
        conn = http.client.HTTPSConnection(
            host=host, port=443, timeout=3000, check_hostname=False
        )
        conn.request("POST", url, payload, headers)
        response = conn.getresponse()

        if response.status == 200:
            json_response = json.loads(response.read())
            if "data" in json_response:
                json_data = json_response["data"]
        else:
            log_message(
                f"""post_https_response failed for {host}{url}
                    - status: {response.status}, reason: {response.reason}"""
            )
    except Exception as error:  # pylint: disable=broad-exception-caught
        json_data = None
        error_message: str = str(error) + "\n" + traceback.format_exc()
        subject = "Error in post_https_response - " + datetime.now().strftime(
            "%m/%d/%Y %H:%M:%S"
        )
        html = f"post_https_response failed for {host}{url}\n"
        html += error_message
        to = "dwbodine@gmail.com"
        to_name = "dB"
        send_email(to, subject, html, to_name)
    finally:
        if conn is not None:
            conn.close()

    return json_data
