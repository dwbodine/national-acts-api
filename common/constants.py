"""
Constants file
"""

from enum import StrEnum

PAGE_SELLER_TYPE_IDS: list[int] = [7, 14, 15, 16, 17, 18, 19]
ARTIST_SELLER_TYPE: int = 7
US_STATES: list[str] = [
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
]


class ImageType(StrEnum):
    """
    Enum to translate to S3 bucket
    """

    HEADERS = "headers"
    HOMEBANNERS = "homebanners"
    LOGOS = "logos"
    PREVIEWS = "previews"
    THUMBNAILS = "thumbnails"
    EVENT_THUMBNAILS = "event_thumbnails"
    FEATURED_ARTISTS = "featured-artist"


HEADER_IMAGE_WIDTH: int = 1600
HOMEBANNER_IMAGE_WIDTH: int = 1600
LOGO_IMAGE_WIDTH: int = 400
PREVIEW_IMAGE_WIDTH: int = 400
THUMBNAIL_IMAGE_WIDTH: int = 400
EVENT_THUMBNAIL_IMAGE_WIDTH: int = 100
FEATURED_ARTIST_IMAGE_WIDTH: int = 260
DEFAULT_COUNTRY_ID: int = 235
