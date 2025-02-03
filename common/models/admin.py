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
    type: SiteSettingType
    value: str
    dirty: bool
