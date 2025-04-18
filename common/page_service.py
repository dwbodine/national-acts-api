"""
Page Service
"""

from datetime import datetime

from common.db import (
    db_delete,
    db_query_all,
    db_query_one,
    db_insert,
    db_update,
)
from common.models.admin import Page, PageSeller, PageType


class PageService:
    """
    Service to handle page-based activity
    """

    def get_page_by_route(self, route: str):
        """
        Fetch page and page sellers by route
        """

        page: Page = None

        route = route.replace('"', "")
        route = route.replace("'", "")
        route = route.replace(":", "")

        sql = """SELECT Pages.*, PageType.PageType AS PageTypeName,
                    PageType.Template, PageType.Component
                    FROM Pages WHERE Pages.Inactive=0 and Pages.Route=%(route)s"""
        data = {"route": route}
        row = db_query_one(sql, data)
        if row:
            page_id = int(row["PageID"])
            if page_id is not None and page_id > 0:
                page = Page()
                page.page_id = page_id
                page.route = str(row["Route"]) if row["Route"] is not None else None
                page.title = str(row["Title"]) if row["Title"] is not None else None
                page.image = str(row["Image"]) if row["Image"] is not None else None
                page.thumbnail = (
                    str(row["Thumbnail"]) if row["Thumbnail"] is not None else None
                )
                page.link_preview_image = (
                    str(row["LinkPreviewImage"])
                    if row["LinkPreviewImage"] is not None
                    else None
                )
                page.title1 = str(row["Title1"]) if row["Title1"] is not None else None
                page.subtitle1 = (
                    str(row["SubTitle1"]) if row["SubTitle1"] is not None else None
                )
                page.title2 = str(row["Title2"]) if row["Title2"] is not None else None
                page.subtitle2 = (
                    str(row["SubTitle2"]) if row["SubTitle2"] is not None else None
                )
                page.html_text = (
                    str(row["HTMLText"]) if row["HTMLText"] is not None else None
                )
                page.include_start = (
                    str(row["IncludeStart"])
                    if row["IncludeStart"] is not None
                    else None
                )
                page.include_end = (
                    str(row["IncludeEnd"]) if row["IncludeEnd"] is not None else None
                )
                page.exclude_start = (
                    str(row["ExcludeStart"])
                    if row["ExcludeStart"] is not None
                    else None
                )
                page.exclude_end = (
                    str(row["ExcludeEnd"]) if row["ExcludeEnd"] is not None else None
                )
                page.google_analytics_id = (
                    str(row["GoogleAnalyticsID"])
                    if row["GoogleAnalyticsID"] is not None
                    else None
                )

                page_type = PageType()
                page_type.page_type_id = (
                    int(row["PageTypeID"]) if row["PageTypeID"] is not None else 1
                )
                page_type.page_type_name = (
                    str(row["PageTypeName"])
                    if row["PageTypeName"] is not None
                    else None
                )
                page_type.page_type_template = (
                    str(row["Template"]) if row["Template"] is not None else None
                )
                page_type.page_type_component = (
                    str(row["Component"]) if row["Component"] is not None else None
                )
                page.page_type = page_type

        if page is not None:
            page_sellers = self.get_page_sellers(page.page_id, True)
            page.sellers = page_sellers

        return page

    def get_page_sellers(self, page_id: int, do_overrides: bool = False):
        """
        Gets a list of sellers for a page
        """
        page_sellers: list[PageSeller] = None
        sql: str = ""
        data = {"pageId": page_id}
        if do_overrides is True:
            sql = """SELECT PageSellers.*,
                    Sellers.Name AS SellerName,
                    Sellers.Address,
                    Sellers.City,
                    Sellers.State,
                    Sellers.Zip,
                    Sellers.Country,
                    Sellers.Phone,
                    Sellers.Email,
                    Sellers.Twitter,
                    Sellers.Facebook,
                    Sellers.Instagram,
                    Sellers.YouTube,
                    Sellers.Spotify,
                    Sellers.Website,
                    Sellers.WebsiteDisplayText
                    FROM PageSellers
                    JOIN Sellers ON Sellers.SellerId = PageSellers.SellerId
                    WHERE Sellers.Inactive = 0
                    ORDER BY Sellers.Name ASC
                """
        else:
            sql = """SELECT PageSellers.* from PageSellers
                WHERE PageID=%(pageId)s"""

        return page_sellers
    
    
