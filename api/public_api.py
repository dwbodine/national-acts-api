"""
Public API routes
"""

from datetime import datetime
import os
import traceback
from flask import Blueprint, request

from common.admin_service import AdminService
from common.event_service import EventService
from common.page_service import PageService
from common.seller_service import SellerService
from common.utility import convert_to_json, log_message

public_api = Blueprint("public_api", __name__)


# BEGIN PUBLIC ROUTES
@public_api.route("/public/events")
def get_events():
    """
    API method for public website to fetch/search events
    """
    # secured by public api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("PUBLIC_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = EventService()
    seller_id: int = None
    seller_ids: list[int] = None
    start: int = None
    end: int = None
    exclude_start: int = None
    exclude_end: int = None
    search_term: str = None
    ts_event_id: int = None
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("sellerIds") is not None:
        seller_ids = [int(x) for x in str(request.args.get("sellerIds")).split(",")]
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))
    if request.args.get("excludeStart") is not None:
        exclude_start = int(request.args.get("excludeStart"))
    if request.args.get("excludeEnd") is not None:
        exclude_end = int(request.args.get("excludeEnd"))
    if request.args.get("search") is not None:
        search_term = str(request.args.get("search"))
    if request.args.get("tsEventId") is not None:
        ts_event_id = int(request.args.get("tsEventId"))
    results = service.get_events_and_orders(
        seller_id=seller_id,
        start=start,
        end=end,
        search_term=search_term,
        ts_event_id=ts_event_id,
        exclude_start=exclude_start,
        exclude_end=exclude_end,
        show_cancelled=False,
        seller_ids=seller_ids,
    )
    return convert_to_json(results)


@public_api.route("/public/page/<string:route>")
def get_page(route: str):
    """
    API method to fetch a page by route
    """
    # secured by public api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("PUBLIC_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = PageService()
    results = service.get_page_by_route(route)
    return convert_to_json(results)


@public_api.route("/public/sellers")
def get_sellers():
    """
    API method to fetch all sellers for public site
    """
    # secured by public api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("PUBLIC_API_KEY"))

    if sender_key != api_key:
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
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("PUBLIC_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = AdminService()
    settings = service.get_site_settings()
    return convert_to_json(settings)


@public_api.route("/public/uploadFile", methods=["POST"])
def upload_temp_file():
    """
    Uploads a file to the /tmp folder
    """
    if "tempFile" not in request.files:
        return {"msg": "Bad Request"}, 400

    filename: str = None
    try:
        file = request.files["tempFile"]
        filename = file.filename
        file.save(os.path.join("tmp", filename))
    except Exception as error:  # pylint: disable=broad-exception-caught
        filename = None
        error_message: str = str(error) + "\n" + traceback.format_exc()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message(f"""[{now}] - {error_message}\r\n""")

    return convert_to_json(filename)
