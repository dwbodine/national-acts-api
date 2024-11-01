"""
Seller service module
"""

from common.db import db_query_all, db_query_one
from common.models.national_acts import Seller


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
