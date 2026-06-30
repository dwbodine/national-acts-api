"""
Models specific to site or portal administration
"""

from enum import Enum

from common.models.national_acts import VipEvent
from common.models.ticket_socket import Country, Timezone


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
    country: Country = None
    has_events: bool = False
    timezone: Timezone = None


class PageType:
    """
    Settings for page type
    """

    page_type_id: int
    page_type_name: str


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
    country: Country = None
    phone: str = None
    email: str = None
    twitter: str = None
    facebook: str = None
    instagram: str = None
    youtube: str = None
    spotify: str = None
    website: str = None
    website_display_text: str = None
    seller_name: str = None


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
    extra_html_head: str = None
    extra_html_body: str = None
    is_active: bool = True
    use_include_dates: bool = False
    include_start: str = None
    include_end: str = None
    use_exclude_dates: bool = False
    exclude_start: str = None
    exclude_end: str = None
    google_analytics_id: str = None
    page_order: int = 1
    last_update: str = None
    sellers: list[PageSeller] = []
    events: list[VipEvent] = []


class FaqCategory:
    """
    Model for FAQ category
    """

    category_id: int
    category_name: str


class Faq:
    """
    Model for FAQ
    """

    faq_id: int
    category: FaqCategory
    order: int
    question: str
    answer: str


class FeaturedArtist:
    """
    Model for featured artists
    """

    def __init__(
        self,
        featured_artist_id: int = 0,
        featured_artist_order: int = None,
        page_seller_id: int = None,
        title: str = None,
        background_image: str = None,
        preview_image: str = None,
        logo_image: str = None,
        href: str = None,
        last_update: str = None,
    ):
        self.featured_artist_id = featured_artist_id
        self.featured_artist_order = featured_artist_order
        self.page_seller_id = page_seller_id
        self.title = title
        self.background_image = background_image
        self.preview_image = preview_image
        self.logo_image = logo_image
        self.href = href
        self.last_update = last_update


class FanMomentKey:
    """
    Model for fan moment keys
    """

    moment_date: str = None
    seller_id: int = None
    event_id: int = None
    filename: str = None
    seller_name: str = None
    event_title: str = None
    event_location: str = None

    def __str__(self) -> str:
        return f"{self.moment_date}_{self.seller_id}_{self.event_id}"


class FanMoment:
    """
    Model for fan moments
    """

    key: FanMomentKey
    images: list[str] = None

    @property
    def moment_date(self) -> str:
        """
        Moment date from the grouped S3 key.
        """
        return self.key.moment_date if self.key is not None else None

    @property
    def seller_id(self) -> int:
        """
        Seller id from the grouped S3 key.
        """
        return self.key.seller_id if self.key is not None else None

    @property
    def event_id(self) -> int:
        """
        Event id from the grouped S3 key.
        """
        return self.key.event_id if self.key is not None else None

    @property
    def seller_name(self) -> str:
        """
        Seller display name from the grouped S3 key.
        """
        return self.key.seller_name if self.key is not None else None

    @property
    def event_title(self) -> str:
        """
        Event title from the grouped S3 key.
        """
        return self.key.event_title if self.key is not None else None

    @property
    def event_location(self) -> str:
        """
        Event location from the grouped S3 key.
        """
        return self.key.event_location if self.key is not None else None
