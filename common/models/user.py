from datetime import datetime
import hashlib
import random
from common.models.ticket_socket import *

from .. import db
from .. import utility

class UserSeller:
    def __init__(self, sellerId: int, userSellerId: int):
        self.sellerId = sellerId
        self.userSellerId = userSellerId

class User:
    userId: int = 0
    username: str = None
    password: str = None
    isAuthenticated: bool = False
    firstName: str = None
    lastName: str = None
    notes: str = None
    isActive: bool = False
    isAdmin: bool = False
    showInactiveEvents: bool = False
    sellers: list[UserSeller] = []

    def authenticate(self, username: str, password: str):
        sql = "SELECT * FROM UsersNew WHERE Username=%(username)s"
        data = {
            'username': username
        }
        row = db.queryOne(sql, data)
        
        authenticated: bool = False
        if row != {}:
            hashedPassword = str(row["Password"])
            authenticated = self.__passwordverify(password, hashedPassword)
            self.isAuthenticated = authenticated
            if self.isAuthenticated:
                self.userId = int(row["UserId"])
                self.username = username
                self.firstName = str(row["FirstName"])
                self.lastName = str(row["LastName"])
                self.isActive = True if int(row["IsActive"]) == 1 else False
                self.isAdmin = True if int(row["IsAdmin"]) == 1 else False
                self.notes = str(row["Notes"])
                if self.isAdmin == True:
                    self.showInactiveEvents = True
                else:
                    self.showInactiveEvents = True if int(row["ShowInactiveEvents"]) == 1 else False
                self.__getUserSellers()

    def validateUserName(self, username: str):
        if username == None or username.strip() == "":
            return "Please enter a username"
        username = username.strip()
        if utility.validateEmailAddress(username) == False:
            return "Username must be a valid email address"
    
        sql = "SELECT UserId FROM UsersNew WHERE Username = %(username)s"
        data = {
            'username': username
        }
        row = db.queryOne(sql, data)
        if row != {}:
            return "That username is already taken"
        return None
    
    def validatePassword(self, password: str, confirmPassword: str):
        if password == None or password.strip() == "":
            return "Please enter a password"
        password = password.strip()
        if len(password) < 6:
            return "Password must have at least 6 characters."
        if confirmPassword == None or confirmPassword.strip() == "":
            return "Please enter confirm password"
        confirmPassword = confirmPassword.strip()
        if password != confirmPassword:
            return "Passwords do not match"
        return None
    
    def registerUser(self, username: str, password: str, firstName: str, lastName: str, sellerId: int = None):
        success: bool = False
        hashedPassword = self.__passwordHash(password)
        sql = "INSERT INTO UsersNew (Username, Password, FirstName, LastName) VALUES (%(username)s, %(password)s, %(firstName)s, %(lastName)s)"
        data = {
            'username': username,
            'password': hashedPassword, 
            'firstName': firstName, 
            'lastName': lastName
        }
        userId = db.insert(sql, data)
        if userId > 0:
            success = True
            if sellerId != None and sellerId > 0:
                sql = "INSERT INTO UserSeller (UserId, SellerId) VALUES (%(userId)s, %(sellerId)s)"
                data = {
                    'userId': userId,
                    'sellerId': sellerId
                }
                id = db.insert(sql, data)
                success = (id > 0)
        return success

    def sendPasswordResetEmail(self, username: str):
        emailSent: bool = False
        sql = "SELECT UserId FROM UsersNew WHERE Username=%(username)s AND IsActive=1"
        data = {
            'username': username
        }
        row = db.queryOne(sql, data)
        if row != {}:
            userId = int(row["UserId"])
            if userId > 0:
                code = self.__generatePasswordCode(userId)
                print('code is ' + str(code))
                if code > 0:
                    html = "A password reset request has been requested for you from national-acts.com.\n\n"
                    html += "Please use this security code to confirm your email in our system:\n\n" + str(code)
                    subject = "National Acts VIP - Password Reset"
                    emailSent = utility.queueEmail(subject, html, username, 'User', None)
        return emailSent  

    def sendRegistrationEmail(self, username: str, notes: str):
        emailSent: bool = False
        sql = "SELECT Username, CreatedAt FROM UsersNew WHERE Username = %(username)s"
        data = {
            'username': username
        }
        row = db.queryOne(sql, data)
        if row != {}:
            createdAt = datetime.fromisoformat(str(row["CreatedAt"]))
            html = "<table>"
            html += "<tr><td>User Email:</td><td>" + username + "</td></tr>"
            html += "<tr><td>Submitted:</td><td>" + createdAt.strftime("%m/%d/%Y") + "</td></tr>"
            html += "<tr><td><td>Notes:</td><td>" + notes + "</td></tr>"
            html += "</table>"

            subject = "New User Registration"
            #to = "tj@national-acts.com"
            to = "dwbodine@gmail.com"

            emailSent = utility.queueEmail(subject, html, to, "New User Registration", None)

        return emailSent
    
    def validatePasswordResetCode(self, userId: int, code: int):
        isValid: bool = False
        sql = "SELECT * FROM ForgotPasswordToken WHERE UserId=%(userId)s AND Code=%(code)s AND IsExpired=0"
        data = {
            'userId': userId,
            'code': code
        }
        row = db.queryOne(sql, data)
        if row != {}:
            isValid = True

        expireSql = "UPDATE ForgotPasswordToken SET IsExpired=1 WHERE UserId=%(userId)s"
        expireData = {
            'userId': userId
        }
        db.update(expireSql, expireData)

        return isValid

    def updatePassword(self, userId: int, newPassword: str):
        if userId <= 0:
            return False
        
        sql = "UPDATE UsersNew SET Password=%(password)s WHERE UserId=%(userId)s"
        data = {
            'userId': userId,
            'password': self.__passwordHash(newPassword)
        }
        return db.update(sql, data)        

    def __generatePasswordCode(self, userId: int):
        if userId <= 0:
            return 0
        
        expireSql = "UPDATE ForgotPasswordToken SET IsExpired=1 WHERE UserId=%(userId)s"
        expireData = {
            'userId': userId
        }
        db.update(expireSql, expireData)

        createdOn = datetime.now().timestamp()
        code = random.randint(100000, 999999)

        sql = "INSERT INTO ForgotPasswordToken (UserId, Code, CreatedOn) VALUES (%(userId)s, %(code)s, %(createdOn)s)"
        data = {
            'userId': userId,
            'code': code,
            'createdOn': createdOn
        }
        id = db.insert(sql, data)
        if id > 0:
            return code
        else:
            return 0

    def __passwordverify(self, password: str, hashedPassword: str):
        hPass = self.__passwordHash(password)
        return hPass == hashedPassword
    
    def __passwordHash(self, password: str):
        hash_object = hashlib.sha256()
        hash_object.update(password.encode())
        hash_password = hash_object.hexdigest()
        return hash_password

    def getUserById(self, userId: int, fetchSellers: bool = False):
        sql = "SELECT * FROM UsersNew WHERE UserId=%(userId)s"
        data = {
            'userId': userId
        }
        row = db.queryOne(sql, data)
        if row != {}:
            self.userId = userId
            self.username = str(row["Username"])
            self.firstName = str(row["FirstName"])
            self.lastName = str(row["LastName"])
            self.isActive = True if int(row["IsActive"]) == 1 else False
            self.isAdmin = True if int(row["IsAdmin"]) == 1 else False
            self.notes = str(row["Notes"])
            if self.isAdmin == True:
                self.showInactiveEvents = True
            else:
                self.showInactiveEvents = True if int(row["ShowInactiveEvents"]) == 1 else False
            
            if fetchSellers == True:
                self.__getUserSellers()

    def __getUserSellers(self):
        if self.userId <= 0:
            return
        sql = "SELECT * FROM UserSeller WHERE UserId=%(userId)s"
        data = {
            'userId': self.userId
        }
        rows = db.queryAll(sql, data)
        sellers: list[UserSeller] = []
        for row in rows:
            sellerId = int(row["SellerId"])
            userSellerId = int(row["UserSellerId"])
            us = UserSeller(sellerId, userSellerId)
            sellers.append(us)
        self.sellers = sellers
