"""
Public API routes
"""

import os
from flask import Blueprint, request

from common.event_service import EventService
from common.seller_service import SellerService
from common.utility import convert_to_json

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
    start: int = None
    end: int = None
    exclude_start: int = None
    exclude_end: int = None
    search_term: str = None
    ts_event_id: int = None
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
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
        False,
        seller_id,
        start,
        end,
        False,
        search_term,
        ts_event_id,
        False,
        exclude_start,
        exclude_end,
        False,
        False,
        False,
        False,
    )
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


# END PUBLIC ROUTES
