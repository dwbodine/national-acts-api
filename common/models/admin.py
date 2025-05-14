"""
Models specific to site or portal administration
"""

from enum import Enum


class SiteSettingType(str, Enum):
    """
    type of global setting
    """

    IMAGE = "Image"
    NUMBER = "Number"
    TEXT = "Text"

    def __str__(self) -> str:
        return self.value


class SiteSetting:
    """
    global site-specific setting
    """

    setting_id: int
    name: str
    display_name: str
    type: SiteSettingType
    file_path: str = None
    value: str
    dirty: bool


class ExternalVenue:
    """
    setting for "external event venues"
    """

    venue_id: int
    venue: str
    address: str
    city: str
    state: str = None
    zip_code: str = None
    country: str = None
    has_events: bool = False


class PageType:
    """
    Settings for page type
    """

    page_type_id: int
    page_type_name: str
    page_type_template: str
    page_type_component: str = None


class PageSeller:
    """
    Settings for sellers on pages
    """

    page_seller_id: int = 0
    page_id: int
    seller_id: int
    display_name: str = None
    show_display_name: bool = None
    address: str = None
    city: str = None
    state: str = None
    zip: str = None
    country: str = None
    phone: str = None
    email: str = None
    twitter: str = None
    facebook: str = None
    instagram: str = None
    youtube: str = None
    spotify: str = None
    website: str = None
    website_display_text: str = None


class Page:
    """
    settings for pages
    """

    page_id: int
    route: str
    title: str
    page_type: PageType
    image: str = None
    thumbnail: str = None
    link_preview_image: str = None
    logo_only_image: str = None
    title1: str = None
    subtitle1: str = None
    title2: str = None
    subtitle2: str = None
    html_text: str = None
    is_active: bool = True
    include_start: str = None
    include_end: str = None
    exclude_start: str = None
    exclude_end: str = None
    google_analytics_id: str = None
    page_order: int = 1
    sellers: list[PageSeller] = []
