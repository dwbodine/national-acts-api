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
