"""
Utilites for Python app
"""

import json
import logging
import re
import os
import http.client
from datetime import datetime, timezone
import traceback
from types import SimpleNamespace
import boto3
from pytz import country_timezones
import pytz
from stringcase import camelcase, snakecase
from PIL import Image

from common.constants import (
    EVENT_THUMBNAIL_IMAGE_WIDTH,
    FEATURED_ARTIST_IMAGE_WIDTH,
    HEADER_IMAGE_WIDTH,
    HOMEBANNER_IMAGE_WIDTH,
    LOGO_IMAGE_WIDTH,
    PREVIEW_IMAGE_WIDTH,
    THUMBNAIL_IMAGE_WIDTH,
    US_STATES,
    ImageType,
)
from common.db import db_query_one
from common.messaging_service import MessagingService
from common.models.ticket_socket import Country, Timezone, TicketSocketOrder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


def resize_and_move_temp_file_to_s3(
    temp_filename: str, bucket_name: str, max_width: int, is_png: bool = False
) -> str:
    """
    Move a file from the API /tmp directory to an AWS S3 bucket

    """
    filename: str = None

    # using os.path so that this will work in both Linux and Windows
    api_path = os.getenv("API_FILE_PATH")  # absolute path to /tmp in api

    temp_dir = os.path.join(api_path, "tmp")

    # replace Linux relative path separators for Windows
    if os.name == "nt" and len(temp_dir) > 0:
        temp_dir = temp_dir.replace("/", "\\")

    # resize image to specified width
    image_file = resize_tmp_image(temp_filename, max_width)

    if image_file is not None:
        filename = image_file
        origin_file = os.path.join(temp_dir, image_file)

        # only attempt upload if we can find the resized temp file
        if os.path.exists(origin_file) and bucket_name is not None:
            s3_client = boto3.client("s3")

            extra_args = {"ContentType": "image/jpeg"}
            if is_png is True:
                extra_args = {"ContentType": "image/png"}

            try:
                # upload to s3
                s3_client.upload_file(
                    origin_file, bucket_name, image_file, ExtraArgs=extra_args
                )
                # delete the temp file
                os.remove(origin_file)
            except Exception as error:  # pylint: disable=broad-exception-caught
                filename = None
                error_message: str = str(error) + "\n" + traceback.format_exc()
                logger.error("%s", error_message)

    return filename


def list_s3_images(bucket_name: str):
    """
    Lists all images in an S3 bucket
    """
    s3 = boto3.client("s3")

    valid_extensions = (".jpg", ".jpeg", ".png")

    response = s3.list_objects_v2(Bucket=bucket_name)

    if "Contents" not in response:
        return []

    return [
        obj["Key"]
        for obj in response["Contents"]
        if obj["Key"].lower().endswith(valid_extensions)
    ]


def remove_file(file_name: str, bucket_name: str):
    """
    Remove a file from s3 that has had its reference deleted from the database
    """
    logging.info("removing file %s from bucket %s", file_name, bucket_name)
    success: bool = False
    s3_client = boto3.client("s3")
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=file_name)
        success = True
    except Exception as error:  # pylint: disable=broad-exception-caught
        success = False
        error_message: str = str(error) + "\n" + traceback.format_exc()
        logger.error("%s", error_message)
    return success


def resize_tmp_image(image_name: str, resize_width: int = 0):
    """
    Resizes an image in the /tmp folder using Pillow
    """
    pacific_tz = pytz.timezone("America/Los_Angeles")
    image_id: str = datetime.now(pacific_tz).strftime("%Y%m%d%H%M%S")
    api_path = os.getenv("API_FILE_PATH")  # absolute path to /tmp in api
    temp_dir = os.path.join(api_path, "tmp")

    image_path = os.path.join(temp_dir, image_name)
    resize_file_name: str = None

    if os.path.exists(image_path):
        try:
            image = Image.open(image_path)
            filename = image.filename

            last_index = filename.rfind(".")
            if last_index < 0:
                logger.error(
                    "resize_tmp_image - image_path did not have file extension"
                )
                return None
            resize_file_path = (
                f"{filename[0:last_index]}_{image_id}{filename[last_index:]}"
            )

            # default to square(ish) thumbnail if no width given
            if resize_width <= 0:
                resize_width = int(os.getenv("THUMBNAIL_SIZE"))

            # only resize if image width is larger than desired
            if image.width > resize_width:
                # get current dimensions
                width = image.width
                height = image.height

                # manually calculate ratio
                ratio = image.height / image.width
                width = resize_width
                height = width * ratio

                # set dimensions and resize
                size = width, height
                image.thumbnail(size, Image.Resampling.LANCZOS)
            image.save(resize_file_path, image.format)
            image.close()
            if not os.path.exists(resize_file_path):
                logger.error(
                    "resize_tmp_image - resize_file_path does not exist: %s",
                    resize_file_path,
                )
                resize_file_name = None
            else:
                resize_file_name = os.path.basename(resize_file_path)
                os.remove(image_path)
        except Exception as error:  # pylint: disable=broad-exception-caught
            resize_file_name = None
            error_message: str = str(error) + "\n" + traceback.format_exc()
            logger.error("%s", error_message)
    else:
        logger.error("resize_tmp_image - pathname does not exist: %s", image_path)

    return resize_file_name


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
    conn: http.client.HTTPSConnection = None
    try:
        conn = http.client.HTTPSConnection(host=host, port=443, timeout=300)
        conn.request("GET", url, headers=headers)
        response = conn.getresponse()

        if response.status == 200:
            json_response = json.loads(response.read())
            if "data" in json_response:
                json_data = json_response["data"]
        else:
            logger.error(
                """post_https_response failed for %s%s -
                    status: %s, reason: %s""",
                host,
                url,
                response.status,
                response.reason,
            )
    except Exception as error:  # pylint: disable=broad-exception-caught
        json_data = None
        error_message: str = str(error) + "\n" + traceback.format_exc()
        pacific_tz = pytz.timezone("America/Los_Angeles")
        subject = "Error in get_https_response - " + datetime.now(pacific_tz).strftime(
            "%m/%d/%Y %H:%M:%S"
        )
        html = f"get_https_response failed for {host}{url}\n"
        html += error_message
        to = "dwbodine@gmail.com"
        to_name = "dB"
        service = MessagingService()
        service.send_email(to, subject, html, to_name)
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
    conn: http.client.HTTPSConnection = None
    try:
        conn = http.client.HTTPSConnection(host=host, port=443, timeout=300)
        conn.request("POST", url, payload, headers)
        response = conn.getresponse()

        if response.status == 200:
            json_response = json.loads(response.read())
            if "data" in json_response:
                json_data = json_response["data"]
        else:
            logger.error(
                """post_https_response failed for %s%s
                    - status: %s, reason: %s""",
                host,
                url,
                response.status,
                response.reason,
            )
    except Exception as error:  # pylint: disable=broad-exception-caught
        json_data = None
        error_message: str = str(error) + "\n" + traceback.format_exc()
        pacific_tz = pytz.timezone("America/Los_Angeles")
        subject = "Error in post_https_response - " + datetime.now(pacific_tz).strftime(
            "%m/%d/%Y %H:%M:%S"
        )
        html = f"post_https_response failed for {host}{url}\n"
        html += error_message
        to = "dwbodine@gmail.com"
        to_name = "dB"
        service = MessagingService()
        service.send_email(to, subject, html, to_name)
    finally:
        if conn is not None:
            conn.close()

    return json_data


def get_override_string_value_or_default(
    override: any = None, default: any = None
) -> str:
    """
    Get string value from override vs. default
    """
    if override is not None and str(override).strip() != "":
        override_val = str(override).strip()
        return override_val if len(override_val) > 0 else None
    if default is not None:
        return str(default).strip()
    return None


def get_override_int_value_or_default(override: any = None, default: int = 0) -> int:
    """
    Get integer value from override vs. default
    """
    if override is not None:
        return int(override)
    if default is not None:
        return int(default)
    return None


def get_override_float_value_or_default(
    override: any = None, default: any = None
) -> float:
    """
    Get float value from override vs. default
    """
    if override is not None:
        return float(override)
    if default is not None:
        return float(default)
    return 0


def get_override_tinyint_value_or_default_from_bool(
    override: bool = None, default: bool = None
) -> int:
    """
    Get database tinyint value from override vs. default
    """
    if override is not None:
        return 1 if override is True else 0
    if default is not None:
        return 1 if default is True else 0
    return 0


def get_override_bool_value_or_default(
    override: any = None, default: any = None
) -> bool:
    """
    Get integer value from override vs. default
    """
    if override is not None:
        return int(override) >= 1
    if default is not None:
        return int(default) >= 1
    return False


def clean_up_phone_input_for_parsing(phone: str) -> str:
    """
    Cleans a phone input up for parsing
    """
    if phone is None or len(phone.strip()) == 0:
        return None
    phone = phone.replace("(", "")
    phone = phone.replace(")", "")
    phone = phone.replace("-", "")
    phone = phone.replace(" ", "")
    phone = phone.replace(":", "")
    phone = phone.replace("O", "0")
    phone = phone.replace("o", "0")
    phone = re.sub(r"[a-zA-Z]", "", phone)
    phone = phone.strip()
    return phone


def get_timezones_from_country_code(country_code: str, time: str = None):
    """
    Programatically return timezone data by country code
    """
    timezones: list[Timezone] = []
    zones = country_timezones[country_code]
    for zone in zones:
        zone_tz = Timezone()
        zone_tz.timezone = zone
        display_name = zone
        abbrev = get_timezone_abbreviation(zone, time)
        if abbrev is not None:
            display_name = f"{zone} ({abbrev})"
        zone_tz.display_name = display_name
        timezones.append(zone_tz)
    return timezones


def get_timezone_abbreviation(timezone_str: str, time: str = None):
    """
    Get the local abbreviation for a timezone
    """
    if timezone_str is None:
        return None
    ab_tz = pytz.timezone(timezone_str)
    datetime_object: datetime = None
    if time is not None:
        timestamp = datetime.strptime(time, "%Y-%m-%d").timestamp()
        datetime_object = datetime.fromtimestamp(timestamp, ab_tz)
    else:
        datetime_object = datetime.now(ab_tz)
    timezone_abbreviation = datetime_object.strftime("%Z")
    return timezone_abbreviation


def verify_usa_zip_code(zip_code):
    """
    Verifies if a given string is a valid USA ZIP code (5-digit or ZIP+4).
    """
    pattern = r"^\d{5}(?:-\d{4})?$"
    return re.match(pattern, zip_code) is not None


def validate_usa_state_and_zip(state: str, zip_code: str):
    """
    Will return "USA" if a state and zip belong in the USA
    """
    country_name = None
    if state is not None and len(state) > 0 and verify_usa_zip_code(zip_code):
        if state in US_STATES:  # US venues will often come in with no country name
            country_name = "USA"
    return country_name


def get_country_from_country_name(country_name: str, state: str, zip_code: str):
    """
    Helper method to get Country object from country name
    """
    if country_name is None or len(country_name) == 0:
        country_name = validate_usa_state_and_zip(state, zip_code)
        if country_name is None or len(country_name) == 0:
            return None

    if country_name.lower().startswith("united states") or country_name.lower() == "us":
        country_name = "USA"
    elif (
        country_name.lower() == "england"
        or country_name.lower() == "wales"
        or country_name.lower() == "scotland"
        or country_name.lower() == "northern ireland"
    ):
        country_name = "UK"

    country: Country = None
    sql = """SELECT * FROM Country WHERE LCASE(CountryName)=%(country_name)s"""
    data = {"country_name": country_name.lower()}
    row = db_query_one(sql, data)
    if row:
        country_id = get_override_int_value_or_default(row["CountryId"])
        country_name = get_override_string_value_or_default(row["CountryName"])
        country_code = get_override_string_value_or_default(row["CountryCode"])
        if country_code is not None:
            country = Country(country_id, country_name, country_code)
    return country


def get_country_from_country_id(country_id: int):
    """
    Helper method to get Country object from country id
    """
    if country_id is None or country_id == 0:
        country_id = int(os.getenv("DEFAULT_COUNTRY_ID"))
    country: Country = None
    sql = """SELECT * FROM Country WHERE CountryId=%(country_id)s"""
    data = {"country_id": country_id}
    row = db_query_one(sql, data)
    if row:
        country_id = get_override_int_value_or_default(row["CountryId"])
        country_name = get_override_string_value_or_default(row["CountryName"])
        country_code = get_override_string_value_or_default(row["CountryCode"])
        if country_code is not None:
            country = Country(country_id, country_name, country_code)
    return country


def get_bucket_name_from_image_type(  # pylint: disable=too-many-return-statements
    image_type: ImageType,
) -> str:
    """
    Helper method to translate "iamge type" enum to the appropriate S3 bucket
    """
    match image_type:
        case ImageType.HEADERS:
            return os.getenv("S3_BUCKET_HEADERS")
        case ImageType.HOMEBANNERS:
            return os.getenv("S3_BUCKET_HOMEBANNERS")
        case ImageType.LOGOS:
            return os.getenv("S3_BUCKET_LOGOS")
        case ImageType.PREVIEWS:
            return os.getenv("S3_BUCKET_PREVIEW")
        case ImageType.THUMBNAILS:
            return os.getenv("S3_BUCKET_THUMBNAILS")
        case ImageType.EVENT_THUMBNAILS:
            return os.getenv("S3_BUCKET_THUMBNAILS")
        case ImageType.FEATURED_ARTISTS:
            return os.getenv("S3_BUCKET_FEATURED_ARTISTS")
        case _:
            return None


def get_image_width_from_image_type(  # pylint: disable=too-many-return-statements
    image_type: ImageType,
) -> int:
    """
    Helper method to translate "image type" into the appropriate max width
    """
    match image_type:
        case ImageType.HEADERS:
            return HEADER_IMAGE_WIDTH
        case ImageType.HOMEBANNERS:
            return HOMEBANNER_IMAGE_WIDTH
        case ImageType.LOGOS:
            return LOGO_IMAGE_WIDTH
        case ImageType.PREVIEWS:
            return PREVIEW_IMAGE_WIDTH
        case ImageType.THUMBNAILS:
            return THUMBNAIL_IMAGE_WIDTH
        case ImageType.EVENT_THUMBNAILS:
            return EVENT_THUMBNAIL_IMAGE_WIDTH
        case ImageType.FEATURED_ARTISTS:
            return FEATURED_ARTIST_IMAGE_WIDTH
        case _:
            return 0


def get_pacific_purchase_date_from_order(order: TicketSocketOrder) -> str:
    """
    Convert the UTC unix purchase timestamp to a Pacific calendar date.
    Falls back to the stored purchase_date when the unix timestamp is absent.
    """
    pacific_tz = pytz.timezone("America/Los_Angeles")
    if order.purchase_unix_timestamp is not None and order.purchase_unix_timestamp > 0:
        purchase_datetime = datetime.fromtimestamp(
            float(order.purchase_unix_timestamp), tz=pytz.utc
        ).astimezone(pacific_tz)
        return purchase_datetime.strftime("%Y-%m-%d")
    return order.purchase_date


def get_pacific_purchase_timestamp_from_order(order: TicketSocketOrder) -> str:
    """
    Convert the UTC unix purchase timestamp to a Pacific calendar timestamp.
    Falls back to the stored purchase_date when the unix timestamp is absent.
    """
    pacific_tz = pytz.timezone("America/Los_Angeles")
    if order.purchase_unix_timestamp is not None and order.purchase_unix_timestamp > 0:
        purchase_datetime = datetime.fromtimestamp(
            float(order.purchase_unix_timestamp), tz=pytz.utc
        ).astimezone(pacific_tz)
        return purchase_datetime.strftime("%Y-%m-%d %H:%M:%S")
    return order.purchase_timestamp


def get_pacific_date_from_unix_timestamp(unix_timestamp: float) -> str:
    """
    Convert the UTC string timestamp to a Pacific calendar date.
    """
    pacific_tz = pytz.timezone("America/Los_Angeles")
    pacific_datetime = datetime.fromtimestamp(unix_timestamp, tz=pytz.utc).astimezone(
        pacific_tz
    )
    return pacific_datetime.strftime("%Y-%m-%d")


def get_pacific_date_from_utc_string(utc_date_string: str) -> str:
    """
    Convert the Unix timestamp to a Pacific calendar date.
    """
    unix_timestamp = (
        datetime.strptime(utc_date_string, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    return get_pacific_date_from_unix_timestamp(unix_timestamp)


def get_pacific_date_from_utc_datetime_string(utc_datetime_string: str) -> str:
    """
    Convert the Unix timestamp to a Pacific calendar date.
    """
    unix_timestamp = (
        datetime.strptime(utc_datetime_string, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    return get_pacific_date_from_unix_timestamp(unix_timestamp)
