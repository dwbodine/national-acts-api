"""
Public API routes
"""

import os
from datetime import datetime, timedelta
from flask import Blueprint, request

from common.admin_service import AdminService
from common.constants import ImageType
from common.event_service import EventService
from common.faq_service import FaqService
from common.moments_service import MomentsService
from common.page_service import PageService
from common.public_service import PublicService
from common.seller_service import SellerService
from common.sender_api_service import SenderApiService
from common.utility import (
    convert_to_json,
    get_bucket_name_from_image_type,
    get_image_width_from_image_type,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_timezones_from_country_code,
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

    is_website: bool = False
    if request.args.get("site") is not None:
        is_website = get_override_bool_value_or_default(request.args.get("site"))

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
        is_website=is_website,
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

    show_inactive: bool = False
    if request.args.get("inactive") is not None:
        show_inactive = get_override_bool_value_or_default(request.args.get("inactive"))

    is_website: bool = False
    if request.args.get("site") is not None:
        is_website = get_override_bool_value_or_default(request.args.get("site"))

    service = PageService()
    results = service.get_page_by_route(route, show_inactive, is_website)
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


@public_api.route("/public/uploadImage/<string:image_type_str>", methods=["POST"])
def upload_image(image_type_str: str):
    """
    Uploads a file to a specified S3 bucket
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    if (
        len(request.files) == 0
        or "tempFile" not in request.files
        or image_type_str is None
    ):
        return {"msg": "Bad Request"}, 400

    try:
        image_type = ImageType(image_type_str)
    except ValueError:
        return {"msg": "Bad Request"}, 400

    bucket_name = get_bucket_name_from_image_type(image_type)
    max_width = get_image_width_from_image_type(image_type)
    subfolder: str = get_override_string_value_or_default(request.args.get("subfolder"))

    service = PublicService()
    filename: str = service.upload_image_to_bucket(
        request, bucket_name, max_width, subfolder
    )
    return convert_to_json(filename)


@public_api.route("/public/tours")
def get_all_tours():
    """
    API method to fetch all tours
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    event_service = EventService()
    tours = event_service.get_tours_from_recent_events()
    return convert_to_json(tours)


@public_api.route("/public/featuredArtists")
def get_featured_artists():
    """
    API method to fetch all featured artists
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    public_service = PublicService()
    artists = public_service.get_featured_artists()
    return convert_to_json(artists)


@public_api.route("/public/addOrConfirmSubscriber", methods=["POST"])
def add_or_confirm_subscriber():
    """
    API method to add or confirm a subscriber
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    data = request.get_json()
    email = get_override_string_value_or_default(data.get("email"))

    if email is None:
        return {"msg": "Bad Request"}, 400

    sender_service = SenderApiService()
    subscriber_id = sender_service.add_subscriber_from_email(email)
    return convert_to_json(subscriber_id)


@public_api.route("/public/getAllMomentDates")
def get_all_moment_dates():
    """
    API method to fetch all moment dates
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    seller_id: int = get_override_int_value_or_default(
        request.args.get("seller_id"), default=None
    )

    moments_service = MomentsService()
    moment_dates = moments_service.get_available_moment_dates(seller_id)
    return convert_to_json(moment_dates)


@public_api.route("/public/getAllMomentSellers")
def get_all_moment_sellers():
    """
    API method to fetch all moment sellers
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    moment_date: str = get_override_string_value_or_default(request.args.get("date"))

    moments_service = MomentsService()
    moment_sellers = moments_service.get_available_moment_sellers(moment_date)
    return convert_to_json(moment_sellers)


@public_api.route("/public/getAllMomentEvents")
def get_all_moment_events():
    """
    API method to fetch all moment events
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    moment_date: str = get_override_string_value_or_default(request.args.get("date"))

    seller_id: int = get_override_int_value_or_default(
        request.args.get("sellerId"), default=None
    )

    moments_service = MomentsService()
    moment_events = moments_service.get_available_moment_events(moment_date, seller_id)
    return convert_to_json(moment_events)


@public_api.route("/public/moments/filter")
def get_filtered_moment_events():
    """
    API method to fetch fan moments by filter
    """
    # secured by public api key
    sender_key = get_override_string_value_or_default(request.headers.get("x-api-key"))
    api_key = get_override_string_value_or_default(os.environ.get("PUBLIC_API_KEY"))

    if sender_key is None or api_key is None or sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    start_date: str = get_override_string_value_or_default(
        request.args.get("startDate")
    )
    end_date: str = get_override_string_value_or_default(request.args.get("endDate"))
    if start_date is not None and end_date is None:
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d") + timedelta(hours=23, minutes=59)
        ).strftime("%Y-%m-%d")
    elif end_date is not None:
        end_date = (
            datetime.strptime(end_date, "%Y-%m-%d") + timedelta(hours=23, minutes=59)
        ).strftime("%Y-%m-%d")

    seller_id: int = get_override_int_value_or_default(
        request.args.get("sellerId"), default=None
    )

    event_id: int = get_override_int_value_or_default(
        request.args.get("eventId"), default=None
    )

    moments_service = MomentsService()
    fan_moments = moments_service.filter_moments(
        start_date=start_date,
        end_date=end_date,
        seller_id=seller_id,
        event_id=event_id,
    )
    return convert_to_json(fan_moments)
