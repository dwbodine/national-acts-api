from . import db
from common.ticket_socket_service import *
from common.models.national_acts import *
from common.models.ticket_socket import *

class SellerService:
    def getUserSellers(self, userId: int):
        sellers: list[Seller] = []

        sql = """SELECT SellerId, Name FROM Sellers ORDER BY Name"""
        data = None
        if userId != None:
            userSql = """SELECT IF(Users.UserId > 0, 1, 0) AS IsValid, COALESCE(UserRole.RoleId, 2) AS RoleId
                            FROM Users
                            LEFT JOIN UserRole ON UsersNew.UserId = UserRole.UserId 
                            WHERE Users.UserId=%(userId)s"""
            userData = {
                'userId': userId
            }
            user = db.queryOne(userSql, userData)

            if user != {}:
                isValid: bool = True if int(user['IsValid']) == 1 else False
                isAdmin: bool = True if int(user['RoleId']) == 1 else False
                if isValid == False:
                    return []
                if isAdmin == False:
                    sql = """SELECT COALESCE(Sellers.SellerId, 0) AS SellerId, Sellers.Name
                                FROM Sellers
                                LEFT JOIN UserSeller ON UserSeller.SellerId=Sellers.SellerId
                                WHERE UserSeller.UserId=%(userId)s 
                                ORDER BY Sellers.Name"""
                    data = {
                        'userId': userId
                    }
            else:
                return []

        rows = db.queryAll(sql, data)
        for row in rows:
            sellerId = int(row["SellerId"])
            if sellerId > 0:
                seller = Seller(sellerId)
                sellers.append(seller)
        return sellers
    
    def getAllSellers(self):
        sellers: list[Seller] = []

        sql = """SELECT SellerId, Name FROM Sellers WHERE Inactive <> 1 ORDER BY Name"""
        data = None
        
        rows = db.queryAll(sql, data)
        for row in rows:
            sellerId = int(row["SellerId"])
            if sellerId > 0:
                seller = Seller(sellerId)
                seller.name = str(row["Name"])
                sellers.append(seller)
        return sellers