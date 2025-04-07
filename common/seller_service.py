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

    def get_all_sellers(self):
        """
        Return a list of all active sellers in the database
        """
        sellers: list[Seller] = []

        sql = """SELECT SellerId, Name FROM Sellers WHERE Inactive <> 1 ORDER BY Name"""
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
        }

        if seller_to_udpdate.seller_id > 0:
            data["sellerId"] = seller_to_udpdate.seller_id
            sql = """UPDATE Sellers SET
                        Name=%(name)s, 
                        SellerTypeId=%(sellerTypeId)s, 
                        HideInList=%(hideInList)s, 
                        Inactive=%(inactive)s, 
                        LastUpdate=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00') 
                    WHERE SellerId=%(sellerId)s"""
            success = db_update(sql, data)
            seller_id = seller_to_udpdate.seller_id if success else 0
        else:
            sql = """INSERT INTO Sellers (Name, SellerTypeId, HideInList, Inactive, Created)
                    VALUES (%(name)s, %(sellerTypeId)s, %(hideInList)s, %(inactive)s, 
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

            for category in new_categories:
                found_category = next(
                    (cat for cat in existing_categories if cat == category), None
                )
                if found_category is not None:
                    if found_category.event_category_id != category.event_category_id:
                        if category.event_category_id is not None:
                            update_sql = """UPDATE SellerEventCategory SET
                                EventCategoryId=%(eventCategoryId)s, 
                                LastUpdated=CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00')
                                WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"""
                            update_data = {
                                "eventCategoryId": category.event_category_id,
                                "sellerEventCategoryId": found_category.seller_event_category_id,
                            }
                            success = db_update(update_sql, update_data)
                        else:
                            delete_sql = """DELETE FROM SellerEventCategory
                                WHERE SellerEventCategoryId=%(sellerEventCategoryId)s"""
                            delete_data = {
                                "sellerEventCategoryId": found_category.seller_event_category_id
                            }
                            success = db_delete(delete_sql, delete_data)
                else:
                    insert_sql = """INSERT INTO SellerEventCategory
                        (SellerId, TicketSocketId, EventCategoryId, Created, LastUpdated)
                         VALUES (%(sellerId)s, %(ticketSocketId)s, %(eventCategoryId)s,
                         CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'), 
                         CONVERT_TZ(CURRENT_TIMESTAMP,'+00:00','-1:00'))"""
                    insert_data = {
                        "sellerId": category.seller_id,
                        "ticketSocketId": category.ticket_socket_id,
                        "eventCategoryId": category.event_category_id,
                    }
                    sec_id = db_insert(insert_sql, insert_data)
                    success = sec_id > 0

                if success is not True:
                    break

        if success is True:
            seller_to_udpdate.seller_id = seller_id
            return seller_to_udpdate
        else:
            return None
