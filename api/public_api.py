"""
Public API routes
"""

from datetime import datetime
import os
import traceback
from flask import Blueprint, request
import pytz

from common.admin_service import AdminService
from common.event_service import EventService
from common.faq_service import FaqService
from common.page_service import PageService
from common.seller_service import SellerService
from common.utility import (
    convert_to_json,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_timezones_from_country_code,
    log_message,
)

public_api = Blueprint("public_api", __name__)


# BEGIN PUBLIC ROUTES
@public_api.route("/public/faq/<int:category_id>")
def get_faqs(category_id: int):
    """
    API method to fetch FAQ's by category_id (0 for all)
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if category_id is None:
        category_id = 0

    service = FaqService()
    faqs = service.get_faq_by_category_id(category_id)
    return convert_to_json(faqs)


@public_api.route("/public/faq_categories")
def get_faq_categories():
    """
    API method to fetch all FAQ categories
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = FaqService()
    categories = service.get_faq_categories()
    return convert_to_json(categories)


@public_api.route("/public/events")
def get_events():
    """
    API method for public website to fetch/search events
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = EventService()
    seller_id: int = get_override_int_value_or_default(
        request.args.get("sellerId"), default=None
    )
    start: int = get_override_int_value_or_default(
        request.args.get("start"), default=None
    )
    end: int = get_override_int_value_or_default(request.args.get("end"), default=None)
    exclude_start: int = get_override_int_value_or_default(
        request.args.get("excludeStart"), default=None
    )
    exclude_end: int = get_override_int_value_or_default(
        request.args.get("excludeEnd"), default=None
    )
    search_term: str = get_override_string_value_or_default(request.args.get("search"))
    event_id: int = get_override_int_value_or_default(
        request.args.get("eventId"), default=None
    )

    seller_ids: list[int] = None
    if request.args.get("sellerIds") is not None:
        seller_ids = [int(x) for x in str(request.args.get("sellerIds")).split(",")]

    results = service.get_events_and_orders(
        seller_id=seller_id,
        start=start,
        end=end,
        search_term=search_term,
        event_id=event_id,
        exclude_start=exclude_start,
        exclude_end=exclude_end,
        show_cancelled=False,
        seller_ids=seller_ids,
        is_public=True,
    )
    return convert_to_json(results)


@public_api.route("/public/page/<string:route>")
def get_page_by_route(route: str):
    """
    API method to fetch a page by route
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if route is None or len(route) == 0:
        return {"msg": "Bad Request"}, 400

    show_inactive_int: int = get_override_int_value_or_default(
        request.args.get("inactive")
    )
    show_inactive = show_inactive_int == 1

    service = PageService()
    results = service.get_page_by_route(route, show_inactive)
    return convert_to_json(results)


@public_api.route("/public/pages/<int:page_type_id>")
def get_pages_by_type(page_type_id: int):
    """
    API method to fetch all pages by page type id
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if page_type_id is None or page_type_id <= 0:
        return {"msg": "Bad Request"}, 400

    service = PageService()
    results = service.get_all_pages(is_public=True, page_type_id=page_type_id)
    return convert_to_json(results)


@public_api.route("/public/page_types")
def get_page_types():
    """
    API method to fetch all page types
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = PageService()
    results = service.get_all_page_types()
    return convert_to_json(results)


@public_api.route("/public/page_seller_types")
def get_page_seller_types():
    """
    API method to fetch all page types
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = PageService()
    results = service.get_all_page_types(seller_types_only=True)
    return convert_to_json(results)


@public_api.route("/public/sellers")
def get_sellers():
    """
    API method to fetch all sellers for public site
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SellerService()
    results = service.get_all_sellers()
    return convert_to_json(results)


@public_api.route("/public/settings")
def get_all_settings():
    """
    API method to fetch all site settings
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = AdminService()
    settings = service.get_site_settings()
    return convert_to_json(settings)


@public_api.route("/public/timezones")
def get_all_timezones():
    """
    API method to fetch all available timezones
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    country_code: str = get_override_string_value_or_default(
        request.args.get("country_code")
    )

    service = AdminService()
    countries = service.get_all_countries(country_code)
    for country in countries:
        if country.country_code is None:
            continue
        timezones = get_timezones_from_country_code(country.country_code)
        country.timezones = timezones
    return convert_to_json(countries)


@public_api.route("/public/uploadFile", methods=["POST"])
def upload_temp_file():
    """
    Uploads a file to the /tmp folder
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if "tempFile" not in request.files:
        return {"msg": "Bad Request"}, 400

    filename: str = None
    try:
        file = request.files["tempFile"]
        filename = file.filename

        # replace garbage characters from Windows/Mac
        filename = filename.replace(" ", "_")
        filename = filename.replace("(", "_")
        filename = filename.replace(")", "_")
        filename = filename.replace("__", "_")

        file.save(os.path.join("tmp", filename))
    except Exception as error:  # pylint: disable=broad-exception-caught
        filename = None
        error_message: str = str(error) + "\n" + traceback.format_exc()
        pacific_tz = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pacific_tz).strftime("%Y-%m-%d %H:%M:%S")
        log_message(f"""[{now}] - {error_message}\r\n""")

    return convert_to_json(filename)
