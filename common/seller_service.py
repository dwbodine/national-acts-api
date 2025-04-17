"""
Seller service module
"""

from common.db import db_delete, db_insert, db_query_all, db_query_one, db_update
from common.models.national_acts import Seller, SellerEventCategory


class SellerService:
    """
    Data operations involving sellers
    """

    def get_user_sellers(self, user_id: int):
        """
        Get list of sellers per userId
        """
        sellers: list[Seller] = []

        sql = """SELECT SellerId, Name FROM Sellers ORDER BY Name"""
        data = None
        if user_id is not None:
            user_sql = """SELECT IF(Users.UserId > 0, 1, 0) AS IsValid, Users.IsAdmin AS IsAdmin
                            FROM Users
                            WHERE Users.UserId=%(userId)s"""
            user_data = {"userId": user_id}
            user = db_query_one(user_sql, user_data)

            if user:
                is_valid: bool = True if int(user["IsValid"]) == 1 else False
                is_admin: bool = True if int(user["IsAdmin"]) == 1 else False
                if is_valid is False:
                    return []
                if is_admin is False:
                    sql = """SELECT COALESCE(Sellers.SellerId, 0) AS SellerId, Sellers.Name
                                FROM Sellers
                                LEFT JOIN UserSeller ON UserSeller.SellerId=Sellers.SellerId
                                WHERE UserSeller.UserId=%(userId)s 
                                ORDER BY Sellers.Name"""
                    data = {"userId": user_id}
            else:
                return []

        rows = db_query_all(sql, data)
        for row in rows:
            seller_id = int(row["SellerId"])
            if seller_id > 0:
                seller = Seller(seller_id)
                sellers.append(seller)
        return sellers

    def get_all_sellers(self, show_inactive=False):
        """
        Return a list of all active sellers in the database
        """
        sellers: list[Seller] = []

        sql = """SELECT SellerId, Name FROM Sellers """

        if show_inactive is False:
            sql += """WHERE Inactive <> 1 """

        sql += """ORDER BY Name"""

        data = None

        rows = db_query_all(sql, data)
        for row in rows:
            seller_id = int(row["SellerId"])
            if seller_id > 0:
                seller = Seller(seller_id)
                sellers.append(seller)
        return sellers

    def update_seller(self, seller_to_udpdate: Seller):
        """
        Update Seller data and categories
        """

        success: bool = False
        seller_id: int = 0

        data = {
            "name": seller_to_udpdate.name,
            "sellerTypeId": seller_to_udpdate.seller_type,
            "hideInList": 1 if seller_to_udpdate.hide_in_list is True else 0,
            "inactive": 1 if seller_to_udpdate.is_active is False else 0,
            "address": (
                seller_to_udpdate.address
                if seller_to_udpdate.address is not None
                else None
            ),
            "city": (
                seller_to_udpdate.city if seller_to_udpdate.city is not None else None
            ),
            "state": (
                seller_to_udpdate.state if seller_to_udpdate.state is not None else None
            ),
            "zip": seller_to_udpdate.zip if seller_to_udpdate.zip is not None else None,
            "country": (
                seller_to_udpdate.country
                if seller_to_udpdate.country is not None
                else None
            ),
            "phone": (
                seller_to_udpdate.phone if seller_to_udpdate.phone is not None else None
            ),
            "email": (
                seller_to_udpdate.email if seller_to_udpdate.email is not None else None
            ),
            "twitter": (
                seller_to_udpdate.twitter
                if seller_to_udpdate.twitter is not None
                else None
            ),
            "facebook": (
                seller_to_udpdate.facebook
                if seller_to_udpdate.facebook is not None
                else None
            ),
            "instagram": (
                seller_to_udpdate.instagram
                if seller_to_udpdate.instagram is not None
                else None
            ),
            "youtube": (
                seller_to_udpdate.youtube
                if seller_to_udpdate.youtube is not None
                else None
            ),
            "spotify": (
                seller_to_udpdate.spotify
                if seller_to_udpdate.spotify is not None
                else None
            ),
            "website": (
                seller_to_udpdate.website
                if seller_to_udpdate.website is not None
                else None
            ),
            "websiteDisplayText": (
                seller_to_udpdate.country
                if seller_to_udpdate.website_display_text is not None
                else None
            ),
        }

        if seller_to_udpdate.seller_id > 0:
            data["sellerId"] = seller_to_udpdate.seller_id
            sql = """UPDATE Sellers SET
                        Name=%(name)s, 
                        SellerTypeId=%(sellerTypeId)s, 
                        HideInList=%(hideInList)s, 
                        Inactive=%(inactive)s, 
                        Address=%(address)s,
                        City=%(city)s,
                        State=%(state)s,
                        Zip=%(zip)s,
                        Country=%(country)s,
                        Phone=%(phone)s,
                        Email=%(email)s,
                        Twitter=%(twitter)s,
                        Facebook=%(facebook)s,
                        Instagram=%(instagram)s,
                        YouTube=%(youtube)s,
                        Spotify=%(spotify)s,
                        Website=%(website)s,
                        WebsiteDisplayText=%(websiteDisplayText)s,
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                    WHERE SellerId=%(sellerId)s"""
            success = db_update(sql, data)
            seller_id = seller_to_udpdate.seller_id if success else 0
        else:
            sql = """INSERT INTO Sellers (Name, SellerTypeId, HideInList, Inactive,
                    Address, City, State, Zip, Country, Phone, Email, Twitter, Facebook, 
                    Instagram, YouTube, Spotify, Website, WebsiteDisplayText, Created, LastUpdate)
                    VALUES (%(name)s, %(sellerTypeId)s, %(hideInList)s, %(inactive)s, 
                    %(address)s, %(city)s, %(state)s, %(zip)s, %(country)s, %(phone)s, 
                    %(email)s, %(twitter)s, %(facebook)s, %(instagram)s, %(youtube)s, 
                    %(spotify)s, %(website)s, %(websiteDisplayText)s, 
                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), 
                    CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
            seller_id = db_insert(sql, data)
            success = seller_id > 0

        if (
            success is True
            and seller_id > 0
            and len(seller_to_udpdate.seller_event_categories) > 0
        ):
            new_categories: list[SellerEventCategory] = (
                seller_to_udpdate.seller_event_categories
            )

            seller = Seller(seller_id)
            existing_categories: list[SellerEventCategory] = (
                seller.seller_event_categories
                if seller.seller_event_categories is not None
                else []
            )

            categories_updated: bool = False
            for category in new_categories:
                found_category = next(
                    (cat for cat in existing_categories if cat == category), None
                )
                if found_category is not None:
                    if (
                        found_category.event_category_id != category.event_category_id
                        or category.event_category_id == 0
                    ):
                        if (
                            category.event_category_id is not None
                            and category.event_category_id > 0
                        ):
                            update_sql = """UPDATE SellerEventCategory SET
                                EventCategoryId=%(eventCategoryId)s, 
                                LastUpdated=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"""
                            update_data = {
                                "eventCategoryId": category.event_category_id,
                                "sellerEventCategoryId": found_category.seller_event_category_id,
                            }
                            success = db_update(update_sql, update_data)
                            categories_updated = success
                        else:
                            delete_sql = """DELETE FROM SellerEventCategory
                                WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"""
                            delete_data = {
                                "sellerEventCategoryId": found_category.seller_event_category_id
                            }
                            success = db_delete(delete_sql, delete_data)
                            categories_updated = success
                elif category.event_category_id > 0 and category.ticket_socket_id > 0:
                    insert_sql = """INSERT INTO SellerEventCategory
                        (SellerId, TicketSocketId, EventCategoryId, Created, LastUpdated)
                         VALUES (%(sellerId)s, %(ticketSocketId)s, %(eventCategoryId)s,
                         CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), 
                         CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                    insert_data = {
                        "sellerId": seller_id,
                        "ticketSocketId": category.ticket_socket_id,
                        "eventCategoryId": category.event_category_id,
                    }
                    sec_id = db_insert(insert_sql, insert_data)
                    success = sec_id > 0
                    categories_updated = success
                    if categories_updated is True:
                        category.seller_event_category_id = sec_id

                if success is not True:
                    break

            if categories_updated is True:
                seller_to_udpdate.seller_event_categories = new_categories

        if success is True:
            seller_to_udpdate.seller_id = seller_id
            return seller_to_udpdate
        else:
            return None
