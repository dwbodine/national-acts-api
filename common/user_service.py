from datetime import datetime
import hashlib
import random
from common.models.ticket_socket import *
from common.models.user import *
import traceback
from . import db
from . import utility

class UserService:
    # PUBLIC METHODS
    def login(self, username: str, password: str):
        try:
            user: User = None
            errorMessage: str = None
            isValidInput: bool = True

            if username == None or username == "" or password == None or password == "":
                isValidInput = False
                errorMessage = "Incorrect username or password"
                
            if isValidInput:
                #check to see if they exist first and pull data
                sql = "SELECT Password, RequireResetPassword FROM UsersNew WHERE Username=%(username)s"
                data = {
                    'username': username
                }
                row = db.queryOne(sql, data)
                
                if row != {}:
                    requireReset = True if int(row["RequireResetPassword"]) == 1 else False
                    if requireReset:
                        errorMessage = "Password reset required - please click on \"Forgot Password?\" to proceed"    
                    else:
                        hashedPassword = str(row["Password"])
                        authenticated = self.__passwordverify(password, hashedPassword)
                        if authenticated:
                            user = self.__retrieveUserFromDatabase(username=username, fetchSellers=True)
                            user.isAuthenticated = True
                else:
                    errorMessage = "Incorrect username or password"
                    
        except Exception as err:
            user = None
            errorMessage: str = "Error occurred during login"
            print(f"Unexpected {err=}, {type(err)=}")
                
        return UserResponse(user, errorMessage)    
    
    def registerUser(self, username: str, password: str, confirmPassword: str, firstName: str, lastName: str, sellerId: int = None):
        try:
            # validate input
            usernameError = self.__validateUserName(username)
            if usernameError != None:
                return UserResponse(None, usernameError)

            passwordError = self.__validatePassword(password, confirmPassword)
            if passwordError != None:
                return UserResponse(None, passwordError)
            
            if firstName == None or firstName == "":
                return UserResponse(None, "First name cannot be blank")
            
            if lastName == None or lastName == "":
                return UserResponse(None, "Last name cannot be blank")
            
            user: User = None
            errorMessage: str = None        
            
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
                if sellerId != None and sellerId > 0:
                    sql = "INSERT INTO UserSeller (UserId, SellerId) VALUES (%(userId)s, %(sellerId)s)"
                    data = {
                        'userId': userId,
                        'sellerId': sellerId
                    }
                    id = db.insert(sql, data)
                    if id <= 0:
                        errorMessage = "Error occurred during user registration, please contact your administrator"
            else:
                errorMessage = "Error occurred during user registration, please contact your administrator"
        except Exception as err:
            user = None
            errorMessage = "Error occurred during user registration, please contact your administrator"
            print(f"Unexpected {err=}, {type(err)=}")
        
        return UserResponse(user, errorMessage)

    def sendPasswordResetEmail(self, username: str):
        try:
            if username == "" or username == "":
                return UserResponse(None, "Username cannot be blank")
            
            errorMessage: str = None        
            user = self.__retrieveUserFromDatabase(username=username)
            if user != None:
                code = self.__generatePasswordCode(user.username)
                if code > 0:
                    html = "A password reset request has been requested for you from national-acts.com.\n\n"
                    html += "Please use this security code to confirm your email in our system:\n\n" + str(code)
                    subject = "National Acts VIP - Password Reset"
                    toName = user.firstName + " " + user.lastName
                    result = utility.sendEmail(username, subject, html, toName)
                    if result.success != True:
                        user = None
                        errorMessage = "Error occurred during password reset: " + result.error
                else:
                    user = None
                    errorMessage = "Error occurred during password reset"
            else:
                errorMessage = "User not found"
        except Exception as err:
            user = None
            errorMessage = "Error occurred during password reset"
            print(f"Unexpected {err=}, {type(err)=}")
        
        return UserResponse(user, errorMessage)

    def validatePasswordResetCode(self, username: str, code: int):
        try:
            if username == None or username == "":
                return UserResponse(None, "Username cannot be blank")
            
            errorMessage: str = None
            user: User = None
            userId: int = 0
            
            user = self.__retrieveUserFromDatabase(username=username)
            
            if user == None:
                return UserResponse(None, "User not found")
            
            userId = user.userId
            
            sql = """SELECT * FROM ForgotPasswordToken WHERE UserId=%(userId)s AND Code=%(code)s AND IsExpired=0"""
            data = {
                'userId': userId,
                'code': code
            }
            print(sql)
            print(data)
            row = db.queryOne(sql, data)
            if row == {}:
                user = None
                errorMessage = "Invalid code"
        except Exception as err:
            user = None
            errorMessage = "Error occurred during password reset"
            print(f"Unexpected {err=}, {type(err)=}")

        return UserResponse(user, errorMessage)
    
    def resetPassword(self, username: str, code: int, password: str, confirmPassword: str):
        passwordError = self.__validatePassword(password, confirmPassword)
        if passwordError != None:
            return UserResponse(None, passwordError)
        
        response = self.validatePasswordResetCode(username, code)
        
        if response.hasError():
            return response    
        
        user = response.user
        errorMessage: str = None        
        
        self.__expireAllUserTokens(username)
        
        sql = "UPDATE UsersNew SET Password=%(password)s, RequireResetPassword=0 WHERE Username=%(username)s"
        data = {
            'username': username,
            'password': self.__passwordHash(password)
        }
        success = db.update(sql, data)     
        if success != True:
            user = None
            errorMessage = "Error occurred during password reset"
            
        return UserResponse(user, errorMessage)   
    
    def resetPasswordSecured(self, username: str, password: str, confirmPassword: str):
        passwordError = self.__validatePassword(password, confirmPassword)
        if passwordError != None:
            return UserResponse(None, passwordError)
        
        user = self.__retrieveUserFromDatabase(username=username)
        errorMessage: str = None        
        
        self.__expireAllUserTokens(username)
        
        sql = "UPDATE UsersNew SET Password=%(password)s, RequireResetPassword=0 WHERE Username=%(username)s"
        data = {
            'username': username,
            'password': self.__passwordHash(password)
        }
        success = db.update(sql, data)     
        if success != True:
            user = None
            errorMessage = "Error occurred during password reset"
            
        return UserResponse(user, errorMessage)     
    
    def register(self, username: str, firstName: str, lastName: str, sellerId: int, password: str, confirmPassword: str, notes: str = None):
        passwordError = self.__validatePassword(password, confirmPassword)
        if passwordError != None:
            return UserResponse(None, passwordError)
        
        user: User = self.getUserByUserName(username=username)
        
        if user != None:
            return UserResponse(None, "There is already a user in the system with that email")
        
        errorMessage: str = None        
        
        sql = """INSERT INTO UsersNew (Username, FirstName, LastName, Password, Notes) 
                    VALUES (%(username)s, %(firstName)s, %(lastName)s, %(password)s, %(notes)s)"""
        data = {
            'username': username,
            'firstName': firstName,
            'lastName': lastName,
            'password': self.__passwordHash(password),
            'notes': notes
        }
        userId = db.insert(sql, data)
        
        if userId <= 0:
            user = None
            errorMessage = "Error occurred while registering user"
            
        sql2 = """INSERT INTO UserSeller (UserId, SellerId) VALUES (%(userId)s, %(sellerId)s)"""
        data2 = {
            'userId': userId,
            'sellerId': sellerId
        }
        userSellerId = db.insert(sql2, data2)
        
        regEmailResult = self.__sendRegistrationEmail(username)
        
        if regEmailResult.success != True:
            user = None
            errorMessage = regEmailResult.error
        
        user = self.getUserById(userId)        
            
        return UserResponse(user, errorMessage)         
    
    def getUserById(self, userId: int, fetchSellers: bool = False):
        return self.__retrieveUserFromDatabase(userId=userId, fetchSellers=fetchSellers)
    
    def getUserByUserName(self, username: str, fetchSellers: bool = False):
        return self.__retrieveUserFromDatabase(username=username, fetchSellers=fetchSellers)
    
    def __expireAllUserTokens(self, username: str):
        expireSql = "UPDATE ForgotPasswordToken SET IsExpired=1 WHERE UserId IN (SELECT UserId FROM UsersNew WHERE Username=%(username)s)"
        expireData = {
            'username': username
        }
        db.update(expireSql, expireData)    

    def __generatePasswordCode(self, username: str):
        if username == None or username == "":
            return 0
                
        self.__expireAllUserTokens(username)
        
        user = self.__retrieveUserFromDatabase(username=username)
        
        if user == None:
            return 0

        createdOn = datetime.now().timestamp()
        code = random.randint(100000, 999999)

        sql = "INSERT INTO ForgotPasswordToken (UserId, Code, CreatedOn) VALUES (%(userId)s, %(code)s, %(createdOn)s)"
        data = {
            'userId': user.userId,
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
    
    def __retrieveUserFromDatabase(self, userId: int = None, username: str = None, fetchSellers: bool = False):
        sql: str = None
        data = {}
        user: User = None
        if userId != None and userId > 0:
            sql = "SELECT * FROM UsersNew WHERE UserId=%(userId)s"
            data = {
                'userId': userId
            }
        elif username != None and username != "":
            sql = "SELECT * FROM UsersNew WHERE Username=%(username)s"
            data = {
                'username': username
            }
        
        if sql != None:
            row = db.queryOne(sql, data)
            if row != {}:
                user = User()
                user.userId = int(row["UserId"])
                user.username = str(row["Username"])
                user.firstName = str(row["FirstName"])
                user.lastName = str(row["LastName"])
                user.isActive = True if int(row["IsActive"]) == 1 else False
                user.isAdmin = True if int(row["IsAdmin"]) == 1 else False
                user.notes = str(row["Notes"])
                createdAt = datetime.fromisoformat(str(row["CreatedAt"]))
                user.createdAt = createdAt.strftime("%m/%d/%Y")
                if user.isAdmin == True:
                    user.showInactiveEvents = True
                else:
                    user.showInactiveEvents = True if int(row["ShowInactiveEvents"]) == 1 else False
                
                if fetchSellers == True:
                    sellers = self.__getUserSellers(user.userId, user.isAdmin)
                    user.sellers = sellers
        return user

    def __getUserSellers(self, userId: int, isAdmin: bool):
        sellers: list[UserSeller] = []
        if userId == None or userId <= 0:
            return sellers
        
        data = {}
        sql = "SELECT s.SellerId, s.Name FROM Sellers s"
        if isAdmin == False:
            sql += " JOIN UserSeller us on us.SellerId = s.SellerId WHERE us.UserId=%(userId)s AND s.Inactive <> 1"            
            data = {
                'userId': userId
            }
        
        sql += " ORDER BY s.Name ASC"
        
        rows = db.queryAll(sql, data)
        
        for row in rows:
            sellerId = int(row["SellerId"])
            sellerName = str(row["Name"])
            us = UserSeller(sellerId, sellerName)
            sellers.append(us)
        return sellers
    
    
    def __validateUserName(self, username: str):
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
    
    def __validatePassword(self, password: str, confirmPassword: str):
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
    
    def __sendRegistrationEmail(self, username: str):
        result = utility.SendEmailResult(True, None)
        user = self.__retrieveUserFromDatabase(username=username)
        if user != None:            
            html = "<table>"
            html += "<tr><td>User Email:</td><td>" + username + "</td></tr>"
            html += "<tr><td>Submitted:</td><td>" + user.createdAt + "</td></tr>"
            html += "<tr><td><td>Notes:</td><td>" + user.notes + "</td></tr>"
            html += "</table>"

            subject = "New User Registration"
            #to = "tj@national-acts.com"
            to = "dwbodine@gmail.com"

            result = utility.sendEmail(to, subject, html, "New User Registration")
        else:
            result.success = False
            result.error = "Could not find new user in database"
        return result 