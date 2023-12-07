import os
import json
import time
from datetime import datetime
import operator

from . import utility
from . import db
from common.ticket_socket_service import *
from common.models.national_acts import *
from common.models.ticket_socket import *

class SellerService:
    def getUserSellers(self, userId: int):
        sellers: list[Seller] = []

        sql = """SELECT SellerId FROM Sellers"""
        data = None
        if userId != None:
            userSql = """SELECT IF(UserId > 0, 1, 0) AS IsValid, COALESCE(IsAdmin, 0) AS IsAdmin
                            FROM Users
                            WHERE UserId=%(userId)s"""
            userData = {
                'userId': userId
            }
            user = db.queryOne(userSql, userData)

            if user != {}:
                isValid: bool = True if int(user['IsValid']) == 1 else False
                isAdmin: bool = True if int(user['IsAdmin']) == 1 else False
                if isValid == False:
                    return []
                if isAdmin == False:
                    sql = """SELECT COALESCE(Sellers.SellerId, 0) AS SellerId
                                FROM Sellers
                                LEFT JOIN UserSeller ON UserSeller.SellerId=Sellers.SellerId
                                WHERE UserSeller.UserId=%(userId)s"""
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