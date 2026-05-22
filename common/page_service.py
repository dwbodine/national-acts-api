"""
Page Service
"""

from datetime import datetime
import operator
import logging
from common.constants import PAGE_SELLER_TYPE_IDS, ImageType
from common.db import (
    db_delete,
    db_query_all,
    db_query_one,
    db_insert,
    db_update,
)
from common.event_service import EventService
from common.models.admin import FeaturedArtist, Page, PageSeller, PageType
from common.models.national_acts import VipEvent
from common.models.ticket_socket import Country
from common.utility import (
    get_bucket_name_from_image_type,
    get_override_bool_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    remove_file,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PageService:
    """
    Service to handle page-based activity
    """

    def get_all_pages(self, is_public: bool = False, page_type_id: int = None):
        """
        Get all pages, optionally by type
        """
        pages: list[Page] = []

        data = {}
        sql = """SELECT Pages.*, PageType.PageType AS PageTypeName
                    FROM Pages 
                    JOIN PageType ON Pages.PageTypeID = PageType.PageTypeID"""

        if page_type_id is not None and page_type_id > 0:
            sql += """ WHERE Pages.PageTypeID=%(page_type_id)s"""
            data["page_type_id"] = page_type_id
            if is_public is True:
                sql += """ AND Pages.Inactive=0"""
        elif is_public is True:
            sql += """ WHERE Pages.Inactive=0"""

        if page_type_id is not None and page_type_id > 0:
            sql += """ ORDER BY Pages.PageOrder ASC, Pages.LastUpdated DESC"""
        else:
            sql += """ ORDER BY Pages.Title ASC, Pages.Inactive DESC"""

        rows = db_query_all(sql, data)
        for row in rows:
            page = self.__get_page_from_row_object(row)
            if page is not None:
                if (
                    page.page_type is not None
                    and page.page_type.page_type_id in PAGE_SELLER_TYPE_IDS
                ):
                    page_sellers = self.get_page_sellers(page.page_id, is_public)
                    page.sellers = page_sellers
                pages.append(page)

        return pages

    def get_page_by_route(
        self, route: str, show_inactive: bool = False, is_website: bool = False
    ):
        """
        Fetch page and page sellers by route
        """
        page: Page = None

        route = route.replace('"', "")
        route = route.replace("'", "")
        route = route.replace(":", "")

        sql = """SELECT Pages.*, PageType.PageType AS PageTypeName
                    FROM Pages 
                    JOIN PageType ON PageType.PageTypeID = Pages.PageTypeID
                    WHERE Pages.Route=%(route)s"""

        if show_inactive is False:
            sql += " AND Pages.Inactive = 0"

        data = {"route": route}
        row = db_query_one(sql, data)
        page = self.__get_page_from_row_object(row)

        if (
            page is not None
            and page.page_type is not None
            and page.page_type.page_type_id in PAGE_SELLER_TYPE_IDS
        ):
            page_sellers = self.get_page_sellers(page.page_id, True)
            page.sellers = page_sellers

            page_events: list[VipEvent] = []
            event_service = EventService()
            if page.sellers is not None and len(page.sellers) > 0:
                for seller in page.sellers:
                    start: int = None
                    end: int = None
                    if page.use_include_dates is True:
                        if page.include_start is not None:
                            start = datetime.strptime(
                                page.include_start, "%Y-%m-%d %H:%M:%S"
                            ).timestamp()

                        if page.include_end is not None:
                            end = datetime.strptime(
                                page.include_end, "%Y-%m-%d %H:%M:%S"
                            ).timestamp()

                    exclude_start: int = None
                    exclude_end: int = None
                    if page.use_exclude_dates is True:
                        if page.exclude_start is not None:
                            exclude_start = datetime.strptime(
                                page.exclude_start, "%Y-%m-%d %H:%M:%S"
                            ).timestamp()
                            exclude_start += 7 * 60 * 60

                        if page.exclude_end is not None:
                            exclude_end = datetime.strptime(
                                page.exclude_end, "%Y-%m-%d %H:%M:%S"
                            ).timestamp()
                            exclude_end += 7 * 60 * 60

                    seller_events = event_service.get_events_and_orders(
                        is_public=True,
                        get_orders=False,
                        seller_id=seller.seller_id,
                        start=start,
                        end=end,
                        exclude_start=exclude_start,
                        exclude_end=exclude_end,
                        is_website=is_website,
                    )
                    if seller_events is not None and len(seller_events) > 0:
                        page_events = page_events + seller_events

                page_events.sort(
                    key=operator.attrgetter(
                        "event_date",
                        "event_time",
                        "meet_and_greet_time",
                        "title",
                    )
                )
                page.events = page_events

        return page

    def get_page_sellers(self, page_id: int = None, is_public: bool = False):
        """
        Gets a list of sellers for a page
        """
        page_sellers: list[PageSeller] = []
        sql: str = ""
        data = {}

        if page_id is not None:
            data["pageId"] = page_id

        sql = """SELECT DISTINCT PageSellers.PageSellerId,
                PageSellers.SellerId,
                PageSellers.PageId,
                PageSellers.DisplayName,
                PageSellers.ShowDisplayName,
                PageSellers.AddressOverride,
                PageSellers.CityOverride,
                PageSellers.StateOverride,
                PageSellers.ZipOverride,
                PageSellers.CountryIdOverride,
                PageSellers.PhoneOverride,
                PageSellers.EmailOverride,
                PageSellers.TwitterOverride,
                PageSellers.FacebookOverride,
                PageSellers.InstagramOverride,
                PageSellers.YouTubeOverride,
                PageSellers.SpotifyOverride,
                PageSellers.WebsiteOverride,
                PageSellers.WebsiteDisplayTextOverride,
                pc.CountryName AS CountryNameOverride,
                pc.CountryCode AS CountryCodeOverride,
                Sellers.Name AS SellerName,
                Sellers.Address,
                Sellers.City,
                Sellers.State,
                Sellers.Zip,
                Sellers.CountryId,
                sc.CountryName as CountryName,
                sc.CountryCode as CountryCode,
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
                LEFT JOIN Country pc on pc.CountryId = PageSellers.CountryIdOverride
                LEFT JOIN Country sc on sc.CountryId = Sellers.CountryId"""

        if page_id is not None:
            sql += """ WHERE PageSellers.PageId=%(pageId)s"""
        else:
            sql += """
                LEFT JOIN Pages ON Pages.PageID = PageSellers.PageId 
                    WHERE Pages.PageTypeID = 7"""

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

            page_seller.seller_id = get_override_int_value_or_default(row["SellerId"])

            seller_name = get_override_string_value_or_default(row["SellerName"])
            show_display_name = get_override_bool_value_or_default(
                row["ShowDisplayName"]
            )
            display_name = get_override_string_value_or_default(row["DisplayName"])

            page_seller.show_display_name = show_display_name
            page_seller.seller_name = seller_name

            if is_public is True:
                if show_display_name is True and display_name is not None:
                    page_seller.display_name = display_name
                else:
                    page_seller.display_name = seller_name
            else:
                page_seller.display_name = display_name

            default_address: str = None
            if is_public is True:
                default_address = get_override_string_value_or_default(row["Address"])
            page_seller.address = get_override_string_value_or_default(
                row["AddressOverride"], default_address
            )

            default_city: str = None
            if is_public is True:
                default_city = get_override_string_value_or_default(row["City"])
            page_seller.city = get_override_string_value_or_default(
                row["CityOverride"], default_city
            )

            default_state: str = None
            if is_public is True:
                default_state = get_override_string_value_or_default(row["State"])
            page_seller.state = get_override_string_value_or_default(
                row["StateOverride"], default_state
            )

            default_zip: str = None
            if is_public is True:
                default_zip = get_override_string_value_or_default(row["Zip"])
            page_seller.zip = get_override_string_value_or_default(
                row["ZipOverride"], default_zip
            )

            default_country_id: int = None
            if is_public is True:
                default_country_id = get_override_int_value_or_default(
                    row["CountryId"], None
                )
            country_id = get_override_int_value_or_default(
                row["CountryIdOverride"], default_country_id
            )

            default_country_name: str = None
            if is_public is True:
                default_country_name = get_override_string_value_or_default(
                    row["CountryName"]
                )
            country_name = get_override_string_value_or_default(
                row["CountryNameOverride"], default_country_name
            )

            default_country_code: str = None
            if is_public is True:
                default_country_code = get_override_string_value_or_default(
                    row["CountryCode"]
                )
            country_code = get_override_string_value_or_default(
                row["CountryCodeOverride"], default_country_code
            )

            if country_id is not None:
                page_seller.country = Country(country_id, country_name, country_code)

            default_address: str = None
            if is_public is True:
                default_address = get_override_string_value_or_default(row["Address"])
            page_seller.phone = get_override_string_value_or_default(
                row["PhoneOverride"], row["Phone"]
            )

            default_email: str = None
            if is_public is True:
                default_email = get_override_string_value_or_default(row["Email"])
            page_seller.email = get_override_string_value_or_default(
                row["EmailOverride"], default_email
            )

            default_twitter: str = None
            if is_public is True:
                default_twitter = get_override_string_value_or_default(row["Twitter"])
            page_seller.twitter = get_override_string_value_or_default(
                row["TwitterOverride"], default_twitter
            )

            default_facebook: str = None
            if is_public is True:
                default_facebook = get_override_string_value_or_default(row["Facebook"])
            page_seller.facebook = get_override_string_value_or_default(
                row["FacebookOverride"], default_facebook
            )

            default_instagram: str = None
            if is_public is True:
                default_instagram = get_override_string_value_or_default(
                    row["Instagram"]
                )
            page_seller.instagram = get_override_string_value_or_default(
                row["InstagramOverride"], default_instagram
            )

            default_youtube: str = None
            if is_public is True:
                default_youtube = get_override_string_value_or_default(row["YouTube"])
            page_seller.youtube = get_override_string_value_or_default(
                row["YouTubeOverride"], default_youtube
            )

            default_spotify: str = None
            if is_public is True:
                default_spotify = get_override_string_value_or_default(row["Spotify"])
            page_seller.spotify = get_override_string_value_or_default(
                row["SpotifyOverride"], default_spotify
            )

            default_website: str = None
            if is_public is True:
                default_website = get_override_string_value_or_default(row["Website"])
            page_seller.website = get_override_string_value_or_default(
                row["WebsiteOverride"], default_website
            )

            default_website_display_text: str = None
            if is_public is True:
                default_website_display_text = get_override_string_value_or_default(
                    row["WebsiteDisplayText"]
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
        if page_to_update is None or page_to_update.route is None:
            return None

        existing_image: str = None
        existing_thumbnail: str = None
        existing_preview: str = None
        existing_logo: str = None
        if page_to_update.page_id > 0:
            existing_page = self.get_page_by_route(
                page_to_update.route, show_inactive=True
            )
            if existing_page is not None:
                existing_image = get_override_string_value_or_default(
                    existing_page.image
                )
                existing_thumbnail = get_override_string_value_or_default(
                    existing_page.thumbnail
                )
                existing_preview = get_override_string_value_or_default(
                    existing_page.link_preview_image
                )
                existing_logo = get_override_string_value_or_default(
                    existing_page.logo_only_image
                )

        image_str: str = get_override_string_value_or_default(page_to_update.image)
        thumbnail_str: str = get_override_string_value_or_default(
            page_to_update.thumbnail
        )
        preview_str: str = get_override_string_value_or_default(
            page_to_update.link_preview_image
        )
        logo_str: str = get_override_string_value_or_default(
            page_to_update.logo_only_image
        )

        success: bool = False
        page_id = page_to_update.page_id
        data = {
            "route": get_override_string_value_or_default(page_to_update.route),
            "title": get_override_string_value_or_default(page_to_update.title),
            "pageTypeId": get_override_int_value_or_default(
                page_to_update.page_type.page_type_id, 1
            ),
            "image": image_str,
            "thumbnail": thumbnail_str,
            "linkPreviewImage": preview_str,
            "logoOnly": logo_str,
            "title1": get_override_string_value_or_default(page_to_update.title1),
            "subtitle1": get_override_string_value_or_default(page_to_update.subtitle1),
            "title2": get_override_string_value_or_default(page_to_update.title2),
            "subtitle2": get_override_string_value_or_default(page_to_update.subtitle2),
            "htmlText": get_override_string_value_or_default(page_to_update.html_text),
            "inactive": get_override_tinyint_value_or_default_from_bool(
                not page_to_update.is_active
            ),
            "useIncludeDates": get_override_tinyint_value_or_default_from_bool(
                page_to_update.use_include_dates
            ),
            "includeStart": get_override_string_value_or_default(
                page_to_update.include_start
            ),
            "includeEnd": get_override_string_value_or_default(
                page_to_update.include_end
            ),
            "useExcludeDates": get_override_tinyint_value_or_default_from_bool(
                page_to_update.use_exclude_dates
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
            "extraHtmlHead": get_override_string_value_or_default(
                page_to_update.extra_html_head
            ),
            "extraHtmlBody": get_override_string_value_or_default(
                page_to_update.extra_html_body
            ),
        }

        # clean up old images
        if existing_image is not None and (existing_image != image_str):
            bucket_name = get_bucket_name_from_image_type(ImageType.HEADERS)
            remove_file(existing_image, bucket_name)

        if existing_thumbnail is not None and (existing_thumbnail != thumbnail_str):
            bucket_name = get_bucket_name_from_image_type(ImageType.THUMBNAILS)
            remove_file(existing_thumbnail, bucket_name)

        if existing_preview is not None and (existing_preview != preview_str):
            bucket_name = get_bucket_name_from_image_type(ImageType.PREVIEWS)
            remove_file(existing_preview, bucket_name)

        if existing_logo is not None and (existing_logo != logo_str):
            bucket_name = get_bucket_name_from_image_type(ImageType.LOGOS)
            remove_file(existing_logo, bucket_name)

        if page_id > 0:
            data["pageId"] = page_id
            sql = """UPDATE Pages SET Route=%(route)s,
                Title=%(title)s, PageTypeID=%(pageTypeId)s, Image=%(image)s, 
                Thumbnail=%(thumbnail)s, LinkPreviewImage=%(linkPreviewImage)s, 
                LogoOnly=%(logoOnly)s, Title1=%(title1)s, SubTitle1=%(subtitle1)s,
                Title2=%(title2)s, SubTitle2=%(subtitle2)s, HTMLText=%(htmlText)s,
                Inactive=%(inactive)s, UseIncludeDates=%(useIncludeDates)s,
                IncludeStart=%(includeStart)s, IncludeEnd=%(includeEnd)s,
                UseExcludeDates=%(useExcludeDates)s, ExcludeStart=%(excludeStart)s,
                ExcludeEnd=%(excludeEnd)s, GoogleAnalyticsID=%(googleAnalyticsId)s,
                ExtraHTMLHead=%(extraHtmlHead)s, ExtraHTMLBody=%(extraHtmlBody)s,
                LastUpdated=CURRENT_TIMESTAMP
                WHERE PageID=%(pageId)s"""
            success = db_update(sql, data)
        else:
            sql = """INSERT INTO Pages (Route, Title, PageTypeID, Image, Thumbnail,
                LinkPreviewImage, LogoOnly, Title1, SubTitle1, Title2, SubTitle2,
                HTMLText, Inactive, UseIncludeDates, IncludeStart, IncludeEnd,
                UseExcludeDates, ExcludeStart, ExcludeEnd, GoogleAnalyticsID,
                ExtraHTMLHead, ExtraHTMLBody, LastUpdated) VALUES (%(route)s, 
                %(title)s, %(pageTypeId)s, %(image)s, %(thumbnail)s,
                %(linkPreviewImage)s, %(logoOnly)s, %(title1)s, %(subtitle1)s,
                %(title2)s, %(subtitle2)s, %(htmlText)s, %(inactive)s,
                %(useIncludeDates)s, %(includeStart)s, %(includeEnd)s,
                %(useExcludeDates)s, %(excludeStart)s, %(excludeEnd)s,
                %(googleAnalyticsId)s, %(extraHtmlHead)s, %(extraHtmlBody)s,
                CURRENT_TIMESTAMP)"""
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
            # check for updates/adds in new sellers list
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
                    update_sql = """UPDATE PageSellers SET
                        SellerId=%(sellerId)s, 
                        PageId=%(pageId)s,
                        DisplayName=%(displayName)s,
                        ShowDisplayName=%(showDisplayName)s,
                        AddressOverride=%(address)s,
                        CityOverride=%(city)s,
                        StateOverride=%(state)s,
                        ZipOverride=%(zip)s,
                        CountryIdOverride=%(country_id)s,
                        PhoneOverride=%(phone)s,
                        EmailOverride=%(email)s,
                        TwitterOverride=%(twitter)s,
                        FacebookOverride=%(facebook)s,
                        InstagramOverride=%(instagram)s,
                        YouTubeOverride=%(youtube)s,
                        SpotifyOverride=%(spotify)s,
                        WebsiteOverride=%(website)s,
                        WebsiteDisplayTextOverride=%(websiteDisplayText)s,                                
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE PageSellerId=%(pageSellerId)s"""
                    update_data = {
                        "sellerId": get_override_int_value_or_default(seller.seller_id),
                        "pageId": page_id,
                        "displayName": (
                            get_override_string_value_or_default(seller.display_name)
                            if hasattr(seller, "display_name")
                            else None
                        ),
                        "showDisplayName": (
                            get_override_tinyint_value_or_default_from_bool(
                                seller.show_display_name
                            )
                            if hasattr(seller, "show_display_name")
                            else False
                        ),
                        "address": (
                            get_override_string_value_or_default(seller.address)
                            if hasattr(seller, "address")
                            else None
                        ),
                        "city": (
                            get_override_string_value_or_default(seller.city)
                            if hasattr(seller, "city")
                            else None
                        ),
                        "state": (
                            get_override_string_value_or_default(seller.state)
                            if hasattr(seller, "state")
                            else None
                        ),
                        "zip": (
                            get_override_string_value_or_default(seller.zip)
                            if hasattr(seller, "zip")
                            else None
                        ),
                        "country_id": (
                            get_override_int_value_or_default(
                                seller.country.country_id, None
                            )
                            if hasattr(seller, "country")
                            else None
                        ),
                        "phone": (
                            get_override_string_value_or_default(seller.phone)
                            if hasattr(seller, "phone")
                            else None
                        ),
                        "email": (
                            get_override_string_value_or_default(seller.email)
                            if hasattr(seller, "email")
                            else None
                        ),
                        "twitter": (
                            get_override_string_value_or_default(seller.twitter)
                            if hasattr(seller, "twitter")
                            else None
                        ),
                        "facebook": (
                            get_override_string_value_or_default(seller.facebook)
                            if hasattr(seller, "facebook")
                            else None
                        ),
                        "instagram": (
                            get_override_string_value_or_default(seller.instagram)
                            if hasattr(seller, "instagram")
                            else None
                        ),
                        "youtube": (
                            get_override_string_value_or_default(seller.youtube)
                            if hasattr(seller, "youtube")
                            else None
                        ),
                        "spotify": (
                            get_override_string_value_or_default(seller.spotify)
                            if hasattr(seller, "spotify")
                            else None
                        ),
                        "website": (
                            get_override_string_value_or_default(seller.website)
                            if hasattr(seller, "website")
                            else None
                        ),
                        "websiteDisplayText": (
                            get_override_string_value_or_default(
                                seller.website_display_text
                            )
                            if hasattr(seller, "website_display_text")
                            else None
                        ),
                        "pageSellerId": get_override_int_value_or_default(
                            found_seller.page_seller_id
                        ),
                    }
                    success = db_update(update_sql, update_data)
                    sellers_updated = success

                elif seller.seller_id > 0:
                    insert_sql = """INSERT INTO PageSellers
                        (SellerId, PageId, DisplayName, ShowDisplayName, AddressOverride,
                        CityOverride, StateOverride, ZipOverride, CountryIdOverride, PhoneOverride,
                        EmailOverride, TwitterOverride, FacebookOverride, InstagramOverride,
                        YouTubeOverride, SpotifyOverride, WebsiteOverride, WebsiteDisplayTextOverride,
                        LastUpdate) VALUES (%(sellerId)s, %(pageId)s, %(displayName)s, %(showDisplayName)s, 
                        %(address)s, %(city)s, %(state)s, %(zip)s, %(country_id)s, %(phone)s, %(email)s,
                        %(twitter)s, %(facebook)s, %(instagram)s, %(youtube)s, %(spotify)s, %(website)s,
                        %(websiteDisplayText)s, CURRENT_TIMESTAMP)"""
                    insert_data = {
                        "sellerId": get_override_int_value_or_default(seller.seller_id),
                        "pageId": page_id,
                        "displayName": (
                            get_override_string_value_or_default(seller.display_name)
                            if hasattr(seller, "display_name")
                            else None
                        ),
                        "showDisplayName": (
                            get_override_tinyint_value_or_default_from_bool(
                                seller.show_display_name
                            )
                            if hasattr(seller, "show_display_name")
                            else False
                        ),
                        "address": (
                            get_override_string_value_or_default(seller.address)
                            if hasattr(seller, "address")
                            else None
                        ),
                        "city": (
                            get_override_string_value_or_default(seller.city)
                            if hasattr(seller, "city")
                            else None
                        ),
                        "state": (
                            get_override_string_value_or_default(seller.state)
                            if hasattr(seller, "state")
                            else None
                        ),
                        "zip": (
                            get_override_string_value_or_default(seller.zip)
                            if hasattr(seller, "zip")
                            else None
                        ),
                        "country_id": (
                            get_override_int_value_or_default(
                                seller.country.country_id, None
                            )
                            if hasattr(seller, "country") and seller.country is not None
                            else None
                        ),
                        "phone": (
                            get_override_string_value_or_default(seller.phone)
                            if hasattr(seller, "phone")
                            else None
                        ),
                        "email": (
                            get_override_string_value_or_default(seller.email)
                            if hasattr(seller, "email")
                            else None
                        ),
                        "twitter": (
                            get_override_string_value_or_default(seller.twitter)
                            if hasattr(seller, "twitter")
                            else None
                        ),
                        "facebook": (
                            get_override_string_value_or_default(seller.facebook)
                            if hasattr(seller, "facebook")
                            else None
                        ),
                        "instagram": (
                            get_override_string_value_or_default(seller.instagram)
                            if hasattr(seller, "instagram")
                            else None
                        ),
                        "youtube": (
                            get_override_string_value_or_default(seller.youtube)
                            if hasattr(seller, "youtube")
                            else None
                        ),
                        "spotify": (
                            get_override_string_value_or_default(seller.spotify)
                            if hasattr(seller, "spotify")
                            else None
                        ),
                        "website": (
                            get_override_string_value_or_default(seller.website)
                            if hasattr(seller, "website")
                            else None
                        ),
                        "websiteDisplayText": (
                            get_override_string_value_or_default(
                                seller.website_display_text
                            )
                            if hasattr(seller, "website_display_text")
                            else None
                        ),
                    }
                    ps_id = db_insert(insert_sql, insert_data)
                    success = ps_id > 0
                    sellers_updated = success
                    if sellers_updated is True:
                        seller.page_seller_id = ps_id

                if success is not True:
                    break

            # check for deletes
            for seller in existing_sellers:
                found_seller = next(
                    (
                        sl
                        for sl in new_sellers
                        if sl.page_seller_id == seller.page_seller_id
                    ),
                    None,
                )
                if found_seller is None:
                    delete_sql = """DELETE FROM PageSellers
                        WHERE PageSellerId=%(pageSellerId)s"""
                    delete_data = {
                        "pageSellerId": get_override_int_value_or_default(
                            seller.page_seller_id
                        )
                    }
                    success = db_delete(delete_sql, delete_data)
                    sellers_updated = success

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
                page.is_active = not get_override_bool_value_or_default(row["Inactive"])
                page.route = get_override_string_value_or_default(row["Route"])
                page.title = get_override_string_value_or_default(row["Title"])
                page.page_order = get_override_int_value_or_default(row["PageOrder"])
                page.image = get_override_string_value_or_default(row["Image"])
                page.thumbnail = get_override_string_value_or_default(row["Thumbnail"])
                page.link_preview_image = get_override_string_value_or_default(
                    row["LinkPreviewImage"]
                )
                page.logo_only_image = get_override_string_value_or_default(
                    row["LogoOnly"]
                )
                page.title1 = get_override_string_value_or_default(row["Title1"])
                page.subtitle1 = get_override_string_value_or_default(row["SubTitle1"])
                page.title2 = get_override_string_value_or_default(row["Title2"])
                page.subtitle2 = get_override_string_value_or_default(row["SubTitle2"])
                page.html_text = get_override_string_value_or_default(row["HTMLText"])
                page.extra_html_head = get_override_string_value_or_default(
                    row["ExtraHTMLHead"]
                )
                page.extra_html_body = get_override_string_value_or_default(
                    row["ExtraHTMLBody"]
                )
                page.use_include_dates = get_override_bool_value_or_default(
                    row["UseIncludeDates"]
                )
                page.include_start = get_override_string_value_or_default(
                    row["IncludeStart"]
                )
                page.include_end = get_override_string_value_or_default(
                    row["IncludeEnd"]
                )
                page.use_exclude_dates = get_override_bool_value_or_default(
                    row["UseExcludeDates"]
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
                page.last_update = get_override_string_value_or_default(
                    row["LastUpdated"]
                )

                page_type = PageType()
                page_type.page_type_id = get_override_int_value_or_default(
                    row["PageTypeID"]
                )
                page_type.page_type_name = get_override_string_value_or_default(
                    row["PageTypeName"]
                )
                page.page_type = page_type

        return page

    def get_all_page_types(self, seller_types_only: bool = False):
        """
        Gets all page types
        """
        sql = """SELECT * FROM PageType"""
        if seller_types_only is True:
            sql += f""" WHERE PageTypeID in
                 ({','.join(str(item) for item in PAGE_SELLER_TYPE_IDS)})"""
        sql += """ ORDER BY PageType ASC"""
        rows = db_query_all(sql)

        page_types: list[PageType] = []

        for row in rows:
            page_type = PageType()
            page_type.page_type_id = get_override_int_value_or_default(
                row["PageTypeID"]
            )
            page_type.page_type_name = get_override_string_value_or_default(
                row["PageType"]
            )
            page_types.append(page_type)

        return page_types

    def update_seller_page_order(self, pages: list[Page]):
        """
        Updates just the page order for seller type pages
        """
        success: bool = True
        for page in pages:
            page_order: int = page.page_order
            if (
                page_order is None
                or page.page_type is None
                or page.page_type.page_type_id not in PAGE_SELLER_TYPE_IDS
            ):
                continue
            sql = """UPDATE Pages
                        SET PageOrder=%(page_order)s,
                        LastUpdated=CURRENT_TIMESTAMP 
                        WHERE PageID=%(page_id)s"""
            data = {"page_order": page_order, "page_id": page.page_id}
            success = db_update(sql, data)
            if success is not True:
                break
        return success

    def update_featured_artist_order(self, featured_artists: list[FeaturedArtist]):
        """
        Updates just the order for featured artists
        """
        success: bool = True
        for fa in featured_artists:
            fa_order: int = fa.featured_artist_order
            if fa_order is None or fa.featured_artist_id is None:
                continue
            sql = """UPDATE FeaturedArtists
                        SET FeaturedArtistOrder=%(fa_order)s,
                        LastUpdate=CURRENT_TIMESTAMP 
                        WHERE FeaturedArtistId=%(fa_id)s"""
            data = {"fa_order": fa_order, "fa_id": fa.featured_artist_id}
            success = db_update(sql, data)
            if success is not True:
                break
        return success

    def update_featured_artist(self, featured_artist: FeaturedArtist):
        """
        Updates the featured artist
        """
        success: bool = True

        if (
            featured_artist is None
            or featured_artist.featured_artist_order is None
            or featured_artist.page_seller_id is None
        ):
            return False

        existing_bg_image: str = None
        if (
            featured_artist.featured_artist_id is not None
            and featured_artist.featured_artist_id > 0
        ):
            existing_sql = """SELECT * FROM FeaturedArtists
                                WHERE FeaturedArtistId=%(fa_id)s"""
            existing_data = {"fa_id": featured_artist.featured_artist_id}

            existing_artist_row = db_query_one(existing_sql, existing_data)

            if existing_artist_row:
                existing_bg_image = get_override_string_value_or_default(
                    existing_artist_row["BackgroundImage"]
                )

        background_image: str = get_override_string_value_or_default(
            featured_artist.background_image
        )

        sql = """UPDATE FeaturedArtists
                    SET PageSellerId=%(page_seller_id)s,
                    BackgroundImage=%(background_image)s,
                    LastUpdate=CURRENT_TIMESTAMP 
                    WHERE FeaturedArtistOrder=%(fa_order)s"""
        data = {
            "background_image": background_image,
            "page_seller_id": get_override_int_value_or_default(
                featured_artist.page_seller_id
            ),
            "fa_order": get_override_int_value_or_default(
                featured_artist.featured_artist_order
            ),
        }
        success = db_update(sql, data)

        if existing_bg_image is not None and (existing_bg_image != background_image):
            bucket_name = get_bucket_name_from_image_type(ImageType.FEATURED_ARTISTS)
            remove_file(existing_bg_image, bucket_name)

        return featured_artist if success is True else None
