"""
Report API routes
"""

from flask import Blueprint
from flask_jwt_extended import jwt_required

from common.common_api import get_user_from_jwt
from common.report_service import ReportService
from common.utility import convert_to_json

report_api = Blueprint("report_api", __name__)


@report_api.route("/reports/getMissingVenueEvents")
@jwt_required()
def get_missing_venues():
    """
    API method to fetch External Events missing venue data
    """
    user = get_user_from_jwt()
    if user is None or user.is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = ReportService()
    events = service.get_missing_venue_events()
    return convert_to_json(events)


@report_api.route("/reports/headerImages")
def header_image_report():
    """
    Report to show missing/orphaned header images
    """
    service = ReportService()
    report = service.get_orphaned_and_missing_header_images()
    return convert_to_json(report)


@report_api.route("/reports/thumbnailImages")
def thumbnail_image_report():
    """
    Report to show missing/orphaned thumbnail images
    """
    service = ReportService()
    report = service.get_orphaned_and_missing_thumbnail_images()
    return convert_to_json(report)


@report_api.route("/reports/previewImages")
def preview_image_report():
    """
    Report to show missing/orphaned preview images
    """
    service = ReportService()
    report = service.get_orphaned_and_missing_preview_images()
    return convert_to_json(report)


@report_api.route("/reports/logos")
def logo_image_report():
    """
    Report to show missing/orphaned logos
    """
    service = ReportService()
    report = service.get_orphaned_and_missing_logo_images()
    return convert_to_json(report)


@report_api.route("/reports/banners")
def banner_image_report():
    """
    Report to show missing/orphaned banners
    """
    service = ReportService()
    report = service.get_orphaned_and_missing_banner_images()
    return convert_to_json(report)
