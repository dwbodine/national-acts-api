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
from common.utility import (
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
)


class PageService:
    """
    Service to handle page-based activity
    """

    page_seller_type_ids: list[int] = [7, 14, 15, 16, 17, 18, 19]

    def get_all_pages(self):
        """
        Get all pages
        """
        pages: list[Page] = []

        sql = """SELECT Pages.*, PageType.PageType AS PageTypeName,
                    PageType.Template, PageType.Component
                    FROM Pages ORDER BY Pages.Title ASC, Pages.Inactive DESC"""
        rows = db_query_all(sql)
        for row in rows:
            page = self.__get_page_from_row_object(row)
            if page is not None:
                if (
                    page.page_type is not None
                    and page.page_type.page_type_id in self.page_seller_type_ids
                ):
                    page_sellers = self.get_page_sellers(page.page_id)
                    page.sellers = page_sellers
                pages.append(page)

        return pages

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
        page = self.__get_page_from_row_object(row)

        if (
            page is not None
            and page.page_type is not None
            and page.page_type.page_type_id in self.page_seller_type_ids
        ):
            page_sellers = self.get_page_sellers(page.page_id, True)
            page.sellers = page_sellers

        return page

    def get_page_sellers(self, page_id: int, is_public: bool = False):
        """
        Gets a list of sellers for a page
        """
        page_sellers: list[PageSeller] = []
        sql: str = ""
        data = {"pageId": page_id}

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
                WHERE PageSellers.PageId=%(pageId)s"""

        if is_public is True:
            sql += """ AND Inactive = 0"""

        sql += """ ORDER BY Sellers.Name ASC"""
        rows = db_query_all(sql, data)
        for row in rows:
            page_seller_id = get_override_int_value_or_default(row["PageSellerId"])
            if page_seller_id == 0:
                continue
            page_seller = PageSeller()
            page_seller.page_seller_id = page_seller_id
            page_seller.page_id = page_id

            seller_name = str(row["SellerName"])
            show_display_name = get_override_bool_value_or_default(
                row["ShowDisplayName"]
            )
            display_name = get_override_string_value_or_default(row["DisplayName"])

            page_seller.show_display_name = show_display_name

            if is_public is True:
                if show_display_name is True and display_name is not None:
                    page_seller.display_name = display_name
                else:
                    page_seller.display_name = seller_name
            else:
                page_seller.display_name = display_name

            default_address = row["Address"] if is_public is True else None
            page_seller.address = get_override_string_value_or_default(
                row["AddressOverride"], default_address
            )
            default_city = row["City"] if is_public is True else None
            page_seller.city = get_override_string_value_or_default(
                row["CityOverride"], default_city
            )
            default_state = row["State"] if is_public is True else None
            page_seller.state = get_override_string_value_or_default(
                row["StateOverride"], default_state
            )
            default_zip = row["Zip"] if is_public is True else None
            page_seller.zip = get_override_string_value_or_default(
                row["ZipOverride"], default_zip
            )
            default_country = row["Country"] if is_public is True else None
            page_seller.country = get_override_string_value_or_default(
                row["CountryOverride"], default_country
            )
            default_address = row["Address"] if is_public is True else None
            page_seller.phone = get_override_string_value_or_default(
                row["PhoneOverride"], row["Phone"]
            )
            default_email = row["Email"] if is_public is True else None
            page_seller.email = get_override_string_value_or_default(
                row["EmailOverride"], default_email
            )
            default_twitter = row["Twitter"] if is_public is True else None
            page_seller.twitter = get_override_string_value_or_default(
                row["TwitterOverride"], default_twitter
            )
            default_facebook = row["Facebook"] if is_public is True else None
            page_seller.facebook = get_override_string_value_or_default(
                row["FacebookOverride"], default_facebook
            )
            default_instagram = row["Instagram"] if is_public is True else None
            page_seller.instagram = get_override_string_value_or_default(
                row["InstagramOverride"], default_instagram
            )
            default_youtube = row["YouTube"] if is_public is True else None
            page_seller.youtube = get_override_string_value_or_default(
                row["YouTubeOverride"], default_youtube
            )
            default_spotify = row["Spotify"] if is_public is True else None
            page_seller.spotify = get_override_string_value_or_default(
                row["SpotifyOverride"], default_spotify
            )
            default_website = row["Website"] if is_public is True else None
            page_seller.website = get_override_string_value_or_default(
                row["WebsiteOverride"], default_website
            )
            default_website_display_text = (
                row["WebsiteDisplayText"] if is_public is True else None
            )
            page_seller.website_display_text = get_override_string_value_or_default(
                row["WebsiteDisplayTextOverride"], default_website_display_text
            )

            page_sellers.append(page_seller)

        return page_sellers

    def update_page(self, page_to_update: Page):
        """
        Updates page data
        """
        if page_to_update is None:
            return None

        success: bool = False
        page_id = page_to_update.page_id
        data = {
            "route": get_override_string_value_or_default(page_to_update.route),
            "title": get_override_string_value_or_default(page_to_update.title),
            "pageTypeId": get_override_int_value_or_default(
                page_to_update.page_type.page_type_id, 1
            ),
            "image": get_override_string_value_or_default(page_to_update.image),
            "thumbnail": get_override_string_value_or_default(page_to_update.thumbnail),
            "linkPreviewImage": get_override_string_value_or_default(
                page_to_update.link_preview_image
            ),
            "logoOnly": get_override_string_value_or_default(
                page_to_update.logo_only_image
            ),
            "title1": get_override_string_value_or_default(page_to_update.title1),
            "subtitle1": get_override_string_value_or_default(page_to_update.subtitle1),
            "title2": get_override_string_value_or_default(page_to_update.title2),
            "subtitle2": get_override_string_value_or_default(page_to_update.subtitle2),
            "htmlText": get_override_string_value_or_default(page_to_update.html_text),
            "inactive": 1 if page_to_update.is_active is False else 0,
            "includeStart": get_override_string_value_or_default(
                page_to_update.include_start
            ),
            "includeEnd": get_override_string_value_or_default(
                page_to_update.include_end
            ),
            "excludeStart": get_override_string_value_or_default(
                page_to_update.exclude_start
            ),
            "excludeEnd": get_override_string_value_or_default(
                page_to_update.exclude_end
            ),
            "googleAnalyticsId": get_override_string_value_or_default(
                page_to_update.google_analytics_id
            ),
        }

        if page_id > 0:
            data["pageId"] = page_id
            sql = """UPDATE Pages SET Route=%(route)s,
                Title=%(title)s, PageTypeID=%(pageTypeId)s, Image=%(image)s, 
                Thumbnail=%(thumbnail)s, LinkPreviewImage=%(linkPreviewImage)s, 
                LogoOnly=%(logoOnly)s, Title1=%(title1)s, SubTitle1=%(subtitle1)s,
                Title2=%(title2)s, SubTitle2=%(subtitle2)s, HTMLText=%(htmlText)s,
                Inactive=%(inactive)s, IncludeStart=%(includeStart)s,
                IncludeEnd=%(includeEnd)s, ExcludeStart=%(excludeStart)s,
                ExcludeEnd=%(excludeEnd)s, GoogleAnalyticsID=%(googleAnalyticsId)s
                WHERE PageID=%(pageId)s"""
            success = db_update(sql, data)
        else:
            sql = """INSERT INTO Pages (Route, Title, PageTypeID, Image, Thumbnail,
                LinkPreviewImage, LogoOnly, Title1, SubTitle1, Title2, SubTitle2,
                HTMLText, Inactive, IncludeStart, IncludeEnd, ExcludeStart,
                ExcludeEnd, GoogleAnalyticsID) VALUES (%(route)s, %(title)s,
                %(pageTypeId)s, %(image)s, %(thumbnail)s, %(linkPreviewImage)s,
                %(logoOnly)s, %(title1)s, %(subtitle1)s, %(title2)s, %(subtitle2)s,
                %(htmlText)s, %(inactive)s, %(includeStart)s, %(includeEnd)s,
                %(excludeStart)s, %(excludeEnd)s, %(googleAnalyticsId)s)"""
            page_id = db_insert(sql, data)
            success = page_id > 0

        if (
            success is True
            and page_id > 0
            and page_to_update.sellers is not None
            and len(page_to_update.sellers) > 0
        ):
            new_sellers: list[PageSeller] = page_to_update.sellers
            existing_sellers = self.get_page_sellers(page_id)

            sellers_updated: bool = False
            for seller in new_sellers:
                found_seller = next(
                    (
                        sl
                        for sl in existing_sellers
                        if sl.page_seller_id == seller.page_seller_id
                    ),
                    None,
                )
                if found_seller is not None:
                    if (
                        found_seller.seller_id != seller.seller_id
                        or seller.seller_id == 0
                    ):
                        if seller.seller_id is not None and seller.seller_id > 0:
                            update_sql = """UPDATE PageSellers SET
                                SellerId=%(sellerId)s, 
                                PageId=%(pageId)s,
                                DisplayName=%(displayName)s,
                                ShowDisplayName=%(showDisplayName)s,
                                AddressOverride=%(address)s,
                                CityOverride=%(city)s,
                                StateOverride=%(state)s,
                                ZipOverride=%(zip)s,
                                CountryOverride=%(country)s,
                                PhoneOverride=%(phone)s,
                                EmailOverride=%(email)s,
                                TwitterOverride=%(twitter)s,
                                FacebookOverride=%(facebook)s,
                                InstagramOverride=%(instagram)s,
                                YouTubeOverride=%(youtube)s,
                                SpotifyOverride=%(spotify)s,
                                WebsiteOverride=%(website)s,
                                WebsiteDisplayTextOverride=%(websiteDisplayText)s,                                
                                LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                WHERE PageSellerId=%(pageSellerId)s"""
                            update_data = {
                                "sellerId": seller.seller_id,
                                "pageId": page_id,
                                "displayName": get_override_string_value_or_default(
                                    seller.display_name
                                ),
                                "showDisplayName": (
                                    1 if seller.show_display_name is True else 0
                                ),
                                "address": get_override_string_value_or_default(
                                    seller.address
                                ),
                                "city": get_override_string_value_or_default(
                                    seller.city
                                ),
                                "state": get_override_string_value_or_default(
                                    seller.state
                                ),
                                "zip": get_override_string_value_or_default(seller.zip),
                                "country": get_override_string_value_or_default(
                                    seller.country
                                ),
                                "phone": get_override_string_value_or_default(
                                    seller.phone
                                ),
                                "email": get_override_string_value_or_default(
                                    seller.email
                                ),
                                "twitter": get_override_string_value_or_default(
                                    seller.twitter
                                ),
                                "facebook": get_override_string_value_or_default(
                                    seller.facebook
                                ),
                                "instagram": get_override_string_value_or_default(
                                    seller.instagram
                                ),
                                "youtube": get_override_string_value_or_default(
                                    seller.youtube
                                ),
                                "spotify": get_override_string_value_or_default(
                                    seller.spotify
                                ),
                                "website": get_override_string_value_or_default(
                                    seller.website
                                ),
                                "websiteDisplayText": get_override_string_value_or_default(
                                    seller.website_display_text
                                ),
                                "pageSellerId": found_seller.page_seller_id,
                            }
                            success = db_update(update_sql, update_data)
                            sellers_updated = success
                        else:
                            delete_sql = """DELETE FROM PageSellers
                                WHERE PageSellerId=%(pageSellerId)s"""
                            delete_data = {"pageSellerId": found_seller.page_seller_id}
                            success = db_delete(delete_sql, delete_data)
                            sellers_updated = success
                elif seller.seller_id > 0:
                    insert_sql = """INSERT INTO PageSellers
                        (SellerId, PageId, DisplayName, ShowDisplayName, AddressOverride,
                        CityOverride, StateOverride, ZipOverride, CountryOverride, PhoneOverride,
                        EmailOverride, TwitterOverride, FacebookOverride, InstagramOverride,
                        YouTubeOverride, SpotifyOverride, WebsiteOverride, WebsiteDisplayTextOverride,
                        LastUpdated) VALUES (%(sellerId)s, %(pageId)s, %(displayName)s, %(address)s,
                        %(city)s, %(state)s, %(zip)s, %(country)s, %(phone)s, %(email)s,
                        %(twitter)s, %(facebook)s, %(instagram)s, %(youtube)s, %(spotify)s, %(website)s,
                        %(websiteDisplayText)s, CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                    insert_data = {
                        "sellerId": seller.seller_id,
                        "pageId": page_id,
                        "displayName": get_override_string_value_or_default(
                            seller.display_name
                        ),
                        "showDisplayName": (
                            1 if seller.show_display_name is True else 0
                        ),
                        "address": get_override_string_value_or_default(
                            seller.address
                        ),
                        "city": get_override_string_value_or_default(
                            seller.city
                        ),
                        "state": get_override_string_value_or_default(
                            seller.state
                        ),
                        "zip": get_override_string_value_or_default(seller.zip),
                        "country": get_override_string_value_or_default(
                            seller.country
                        ),
                        "phone": get_override_string_value_or_default(
                            seller.phone
                        ),
                        "email": get_override_string_value_or_default(
                            seller.email
                        ),
                        "twitter": get_override_string_value_or_default(
                            seller.twitter
                        ),
                        "facebook": get_override_string_value_or_default(
                            seller.facebook
                        ),
                        "instagram": get_override_string_value_or_default(
                            seller.instagram
                        ),
                        "youtube": get_override_string_value_or_default(
                            seller.youtube
                        ),
                        "spotify": get_override_string_value_or_default(
                            seller.spotify
                        ),
                        "website": get_override_string_value_or_default(
                            seller.website
                        ),
                        "websiteDisplayText": get_override_string_value_or_default(
                            seller.website_display_text
                        )
                    }
                    ps_id = db_insert(insert_sql, insert_data)
                    success = ps_id > 0
                    sellers_updated = success
                    if sellers_updated is True:
                        seller.page_seller_id = ps_id

                if success is not True:
                    break

            if sellers_updated is True:
                page_to_update.sellers = new_sellers

        return page_to_update if success is True else None

    def __get_page_from_row_object(self, row: dict = None):
        page: Page = None
        if row:
            page_id = get_override_int_value_or_default(row["PageID"])
            if page_id > 0:
                page = Page()
                page.page_id = page_id
                page.route = get_override_string_value_or_default(row["Route"])
                page.title = get_override_string_value_or_default(row["Title"])
                page.image = get_override_string_value_or_default(row["Image"])
                page.thumbnail = get_override_string_value_or_default(row["Thumbnail"])
                page.link_preview_image = get_override_string_value_or_default(
                    row["LinkPreviewImage"]
                )
                page.title1 = get_override_string_value_or_default(row["Title1"])
                page.subtitle1 = get_override_string_value_or_default(row["SubTitle1"])
                page.title2 = get_override_string_value_or_default(row["Title2"])
                page.subtitle2 = get_override_string_value_or_default(row["SubTitle2"])
                page.html_text = get_override_string_value_or_default(row["HTMLText"])
                page.include_start = get_override_string_value_or_default(
                    row["IncludeStart"]
                )
                page.include_end = get_override_string_value_or_default(
                    row["IncludeEnd"]
                )
                page.exclude_start = get_override_string_value_or_default(
                    row["ExcludeStart"]
                )
                page.exclude_end = get_override_string_value_or_default(
                    row["ExcludeEnd"]
                )
                page.google_analytics_id = get_override_string_value_or_default(
                    row["GoogleAnalyticsID"]
                )

                page_type = PageType()
                page_type.page_type_id = get_override_int_value_or_default(
                    row["PageTypeID"]
                )
                page_type.page_type_name = get_override_string_value_or_default(
                    row["PageTypeName"]
                )
                page_type.page_type_template = get_override_string_value_or_default(
                    row["Template"]
                )
                page_type.page_type_component = get_override_string_value_or_default(
                    row["Component"]
                )
                page.page_type = page_type

        return page
