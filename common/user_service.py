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
                sql = "SELECT Password, RequireResetPassword FROM Users WHERE Username=%(username)s"
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
            utility.logMessage(f"Unexpected {err=}, {type(err)=}")
                
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
            sql = "INSERT INTO Users (Username, Password, FirstName, LastName) VALUES (%(username)s, %(password)s, %(firstName)s, %(lastName)s)"
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
            utility.logMessage(f"Unexpected {err=}, {type(err)=}")
        
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
            utility.logMessage(f"Unexpected {err=}, {type(err)=}")
        
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
            row = db.queryOne(sql, data)
            if row == {}:
                user = None
                errorMessage = "Invalid code"
        except Exception as err:
            user = None
            errorMessage = "Error occurred during password reset"
            utility.logMessage(f"Unexpected {err=}, {type(err)=}")

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
        
        sql = "UPDATE Users SET Password=%(password)s, RequireResetPassword=0 WHERE Username=%(username)s"
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
        
        sql = "UPDATE Users SET Password=%(password)s, RequireResetPassword=0 WHERE Username=%(username)s"
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
        
        sql = """INSERT INTO Users (Username, FirstName, LastName, Password, Notes) 
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
    
    def getAllUsers(self):
        users: list[User] = []
        sql: str = """SELECT Users.* FROM Users"""
        rows = db.queryAll(sql)
        for row in rows:
            user = User()
            user.userId = int(row["UserId"])
            user.isAdmin = True if int(row["IsAdmin"]) == 1 else False
            user.username = str(row["Username"])
            user.firstName = str(row["FirstName"])
            user.lastName = str(row["LastName"])
            user.isActive = True if int(row["IsActive"]) == 1 else False                
            user.notes = str(row["Notes"])
            createdAt = datetime.fromisoformat(str(row["CreatedAt"]))
            user.createdAt = createdAt.strftime("%m/%d/%Y")
            
            sellers = self.__getUserSellers(user.userId, user.isAdmin)
            user.sellers = sellers
            if user.isAdmin:
                user.category = "Admin"
            elif len(user.sellers) > 1:
                user.category = "Multiple"
            elif len(user.sellers) > 0:
                user.category = user.sellers[0].sellerName    
            users.append(user)            
        return users
    
    def getAllPermissions(self):
        permissions: list[Permission] = []
        sql = """SELECT * FROM Permissions"""
        rows = db.queryAll(sql)
        for row in rows:
            permissionId = int(row["PermissionId"])
            name = str(row["PermissionName"])
            permission = Permission(permissionId, name)
            permissions.append(permission)
        return permissions
    
    def getAllRoles(self):
        roles: list[Role] = []
        sql = """SELECT * FROM Roles"""
        rows = db.queryAll(sql)
        for row in rows:
            roleId = int(row["RoleId"])
            roleName = str(row["RoleName"])
            role = Role(roleId, roleName)
            permissions = self.__getPermissionsForRole(roleId)
            role.permissions = permissions
            roles.append(role)
        return roles  
    
    def getRoleById(self, roleId: int):
        role: Role = None
        sql = """SELECT * FROM Roles WHERE RoleId=%(roleId)s"""
        data = {
            'roleId': roleId
        }
        row = db.queryOne(sql, data)
        if row != {}:
            roleId = int(row["RoleId"])
            roleName = str(row["RoleName"])
            role = Role(roleId, roleName)
            permissions = self.__getPermissionsForRole(roleId)
            role.permissions = permissions
        return role
    
    def updateRole(self, roleToUpdate: Role):
        success: bool = True
        if roleToUpdate == None:
            return False
        existingRole: Role = self.getRoleById(roleToUpdate.roleId)
        if existingRole != None:
            roleId = existingRole.roleId
            updateSql = """UPDATE Roles SET RoleName=%(roleName)s, LastUpdate=CURRENT_TIMESTAMP WHERE RoleId=%(roleId)s"""
            updateData = {
                'roleName': roleToUpdate.roleName,
                'roleId': roleId
            }
            success = db.update(updateSql, updateData)
            if success == True:
                success = self.__assignPermissionsToRole(roleId, roleToUpdate.permissions)
        else:
            insertSql = """INSERT INTO Roles (RoleName) VALUES (%(roleName)s)"""    
            insertData = {
                'roleName': roleToUpdate.roleName
            }
            roleId = db.insert(insertSql, insertData)
            if roleId > 1:
                success = self.__assignPermissionsToRole(roleId, roleToUpdate.permissions)
        return success            
            
    def updateUser(self, userToUpdate: User):
        success: bool = True
        if userToUpdate == None or userToUpdate.userId == None or userToUpdate.userId <= 0:
            return False
        userId: int = userToUpdate.userId
        existingUser: User = self.__retrieveUserFromDatabase(userId=userId)
        if existingUser != None:
            username = existingUser.username
            if userToUpdate.username != None and userToUpdate.username != "":
                username = userToUpdate.username
            sendTextReset = userToUpdate.sendTextReset
            if userToUpdate.mobile == None or userToUpdate.mobile == "":
                sendTextReset = False
            updateSql = """UPDATE Users SET IsAdmin=%(isAdmin)s, 
                           Username=%(username)s, 
                           FirstName=%(firstName)s, 
                           LastName=%(lastName)s, 
                           Mobile=%(mobile)s,
                           Notes=%(notes)s, 
                           IsActive=%(isActive)s, 
                           RequireResetPassword=%(requireResetPassword)s, 
                           SendEmailReset=%(sendEmailReset)s,
                           SendTextReset=%(sendTextReset)s, 
                           LastUpdate=CURRENT_TIMESTAMP 
                           WHERE UserId=%(userId)s"""
            updateData = {
                'isAdmin': 1 if userToUpdate.isAdmin else 0, 
                'username': username, 
                'firstName': userToUpdate.firstName,
                'lastName': userToUpdate.lastName,
                'mobile': userToUpdate.mobile,
                'notes': userToUpdate.notes,
                'isActive': 1 if userToUpdate.isActive else 0,
                'requireResetPassword': 1 if userToUpdate.requireResetPassword else 0, 
                'sendEmailReset': 1 if userToUpdate.sendEmailReset else 0, 
                'sendTextReset': 1 if sendTextReset else 0, 
                'userId': userId
            }
            success = db.update(updateSql, updateData)
            if success == True:
                success = self.__assignUserToSellers(userId, userToUpdate.isAdmin, userToUpdate.sellers)
        else:
            success = False                
        return success
    
    def logUserActivity(self, userId: int, activityId: int, activityData: str):
        sql = ""
        data = {
            'userId': userId,
            'activityId': activityId
        }
        if len(activityData) > 0:            
            sql = """INSERT INTO UserActivity (UserId, ActivityId, ActivityData) 
                        VALUES (%(userId)s, %(activityId)s, %(activityData)s)"""
            data["activityData"] = activityData
        else:
            sql = """INSERT INTO UserActivity (UserId, ActivityId) 
                        VALUES (%(userId)s, %(activityId)s)"""
            
        success = db.update(sql, data)
        return success
    
    def getUserActivity(self, start: int, end: int, userId: int = None, activityType: int = None):
        activities: list[UserActivity] = []
        sql = """SELECT UserActivity.*, Activity.ActivityName, Users.Username 
                    FROM UserActivity 
                    JOIN Activity ON Activity.ActivityId=UserActivity.ActivityId 
                    JOIN Users ON Users.UserId=UserActivity.UserId 
                    WHERE UserActivity.Timestamp BETWEEN %(startDate)s AND %(endDate)s"""
        data = {
            'startDate': datetime.fromtimestamp(start).strftime('%Y-%m-%d'),
            'endDate': datetime.fromtimestamp(end).strftime('%Y-%m-%d')
        }
        
        whereClause: list[str] = []
        
        if userId != None:
            whereClause.append("UserActivity.UserId = %(userId)s")
            data["userId"] = userId
            
        if activityType != None:
            whereClause.append("UserActivity.ActivityId = %(activityId)s")
            data["activityId"] = activityType
        
        if len(whereClause) > 0:
            sql += " AND ".join(whereClause)
            
        sql += " ORDER BY UserActivity.Timestamp ASC, Username ASC"          
        rows = db.queryAll(sql, data)
        for row in rows:
            aUserId = int(row["UserId"])
            activityType = int(row["ActivityId"])
            activityName = str(row["ActivityName"])
            username = str(row["Username"])
            activityData = str(row["ActivityData"])
            activityTime = str(row["Timestamp"])
            activity = UserActivity(aUserId, activityType, activityData, activityTime, activityName, username)
            activities.append(activity)
            
        return activities
                
    def __getPermissionsForRole(self, roleId: int):
        permissions: list[Permission] = []
        if roleId == None:
            return permissions
        
        sql = ""
        if roleId > 1:
            sql = """SELECT Permissions.PermissionId, Permissions.PermissionName 
                    FROM Permissions 
                    JOIN RolePermissions ON RolePermissions.PermissionId = Permissions.PermissionId 
                    WHERE RolePermissions.RoleId=%(roleId)s"""
        else:
            sql = """SELECT Permissions.PermissionId, Permissions.PermissionName 
                    FROM Permissions"""
                    
        data = {
            'roleId': roleId
        }
        rows = db.queryAll(sql, data)
        for row in rows:
            permissionId = int(row["PermissionId"])
            permissionName = str(row["PermissionName"])
            permission = Permission(permissionId, permissionName)
            permissions.append(permission)
        return permissions
    
    def __assignUserToSellers(self, userId: int, isAdmin: bool, newSellers: list[UserSeller]):
        success: bool = True
        existingUser: User = self.__retrieveUserFromDatabase(userId=userId, fetchSellers=True)
        if existingUser != None:
            if isAdmin == True:
                deleteSellerSql = """DELETE FROM UserSeller WHERE UserId=%(userId)s"""
                deleteSellerData = {
                    'userId': userId
                }
                success = db.delete(deleteSellerSql, deleteSellerData)
            else:
                newSellerIds = [seller.sellerId for seller in newSellers]
                for existingSeller in existingUser.sellers:
                    existingSellerId = existingSeller.sellerId
                    if existingSellerId in newSellerIds:
                        newSeller: UserSeller = self.__getUserSellerFromListById(newSellers, existingSellerId)
                        if existingSeller.roleId != newSeller.roleId:
                            updateRoleSql = """UPDATE UserSeller SET RoleId=%(roleId)s WHERE UserSellerId=%(userSellerId)s"""
                            updateRoleData = {
                                'roleId': newSeller.roleId,
                                'userSellerId': existingSellerId
                            }
                            success = db.update(updateRoleSql, updateRoleData)
                        newSellerIds.remove(existingSellerId)
                    else:
                        deleteSellerSql = """DELETE FROM UserSeller WHERE UserSellerId=%(userSellerId)s"""
                        deleteSellerData = {
                            'userSellerId': existingSellerId
                        }
                        success = db.delete(deleteSellerSql, deleteSellerData)
                if newSellerIds.count > 0:
                    for newSellerId in newSellerIds:
                        if newSellerId > 0:
                            newSeller: UserSeller = self.__getUserSellerFromListById(newSellers, newSellerId)
                            if newSeller != None:
                                insertSellerSql = """INSERT INTO UserSeller (UserId, SellerId, RoleId) VALUES (%(userId)s, %(sellerId)s, %(RoleId)s)"""
                                insertSellerData = {
                                    'userId': userId,
                                    'sellerId': newSellerId,
                                    'roleId': newSeller.roleId
                                }
                                userSellerId = db.insert(insertSellerSql, insertSellerData)
        else:
            success = False
        return success
                        
    def __assignPermissionsToRole(self, roleId: int, newPermissions: list[Permission]):
        existingRole = self.getRoleById(roleId)
        success: bool = True
        if existingRole != None:
            newPermissionIds = [permission.permissionId for permission in newPermissions]
            for existingPermission in existingRole.permissions:
                existingPermissionId = existingPermission.permissionId
                if existingPermissionId in newPermissionIds:
                    newPermission: Permission = self.__getPermissionFromListById(newPermissions, existingPermissionId)
                    newPermissionIds.remove(existingPermissionId)
                else:
                    deleteRoleSql = """DELETE FROM RolePermissions WHERE RoleId=%(roleId)s AND PermissionId=%(permissionId)s"""
                    deleteRoleData = {
                        'permissionId': existingPermissionId,
                        'roleId': roleId
                    }
                    success = db.delete(deleteRoleSql, deleteRoleData)
            if newPermissions.count > 0:
                for newPermissionId in newPermissions:
                    if newPermissionId > 0:
                        newPermission: Permission = self.__getPermissionFromListById(newPermissions, newPermissionId)
                        if newPermission != None:
                            insertPermissionSql = """INSERT INTO RolePermissions (RoleId, PermissionId) VALUES (%(roleId)s, %(permissionId)s)"""
                            insertPermissionData = {
                                'roleId': roleId,
                                'permissionId': newPermissionId
                            }
                            rolePermissionId = db.insert(insertPermissionSql, insertPermissionData)
                            success = (rolePermissionId > 0)
        return success
            
    def __getUserSellerFromListById(sellers: list[UserSeller], userSellerId: int):
        userSeller: UserSeller = None
        for seller in sellers:
            if seller.sellerId == userSellerId:
                userSeller = seller
                break
        return userSeller
    
    def __getPermissionFromListById(permissions: list[Permission], permissionId: int):
        permission: Permission = None
        for p in permissions:
            if p.permissionId == permissionId:
                permission = p
                break
        return permission
    
    def __expireAllUserTokens(self, username: str):
        expireSql = "UPDATE ForgotPasswordToken SET IsExpired=1 WHERE UserId IN (SELECT UserId FROM Users WHERE Username=%(username)s)"
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
            sql = """SELECT Users.*
                        FROM Users 
                        WHERE Users.UserId=%(userId)s"""
            data = {
                'userId': userId
            }
        elif username != None and username != "":
            sql = """SELECT Users.* 
                        FROM Users 
                        WHERE Users.Username=%(username)s"""
            data = {
                'username': username
            }
        
        if sql != None:
            row = db.queryOne(sql, data)
            if row != {}:
                user = User()
                user.userId = int(row["UserId"])
                user.isAdmin = True if int(row["IsAdmin"]) == 1 else False
                user.username = str(row["Username"])
                user.firstName = str(row["FirstName"])
                user.lastName = str(row["LastName"])
                user.isActive = True if int(row["IsActive"]) == 1 else False                
                user.notes = str(row["Notes"])
                user.mobile = str(row["Mobile"])
                user.requireResetPassword = True if int(row["RequireResetPassword"]) else False
                user.sendEmailReset = True if int(row["SendEmailReset"]) else False 
                user.sendTextReset = True if int(row["SendTextReset"]) else False 
                createdAt = datetime.fromisoformat(str(row["CreatedAt"]))
                lastUpdate = datetime.fromisoformat(str(row["LastUpdate"]))
                user.createdAt = createdAt.strftime("%m/%d/%Y")
                user.lastUpdate = lastUpdate.strftime("%m/%d/%Y")
                
                if fetchSellers == True:
                    sellers = self.__getUserSellers(user.userId, user.isAdmin)
                    user.sellers = sellers
                    if user.isAdmin:
                        user.category = "Admin"
                    elif len(user.sellers) > 1:
                        user.category = "Multiple"
                    elif len(user.sellers) > 0:
                        user.category = user.sellers[0].sellerName    
                    
        return user

    def __getUserSellers(self, userId: int, isAdmin: bool):
        sellers: list[UserSeller] = []
        if userId == None or userId <= 0:
            return sellers
        
        data = {}
        sql = ""
        if isAdmin == False:
            sql = """SELECT UserSeller.UserSellerId, Sellers.SellerId, Sellers.Name, Sellers.SellerTypeId, UserSeller.RoleId 
                        FROM Sellers
                        JOIN UserSeller on UserSeller.SellerId = Sellers.SellerId 
                        WHERE UserSeller.UserId=%(userId)s AND Sellers.Inactive <> 1
                        ORDER BY Sellers.Name ASC"""            
            data = {
                'userId': userId
            }
        else:
            sql = "SELECT 0 as UserSellerId, Sellers.SellerId, Sellers.Name, Sellers.SellerTypeId, 1 AS RoleId FROM Sellers ORDER BY Sellers.Name ASC"
        
        rows = db.queryAll(sql, data)
        
        for row in rows:
            userSellerId = int(row["UserSellerId"])
            sellerId = int(row["SellerId"])
            sellerName = str(row["Name"])
            sellerType = int(row["SellerTypeId"])
            roleId = int(row["RoleId"])
            us = UserSeller(sellerId, sellerName, sellerType, roleId)
            if isAdmin == False:
                permissions = self.__getUserSellerPermissions(userSellerId)
                us.permissions = permissions
            sellers.append(us)
            
        return sellers
    
    def __getUserSellerPermissions(self, userSellerId: int):
        permissions: list[int] = []
        if userSellerId == None or userSellerId <= 1:
            return permissions
        
        sql = """SELECT Permissions.PermissionId FROM Permissions
                    JOIN RolePermissions ON RolePermissions.PermissionId = Permissions.PermissionId 
                    JOIN UserSeller ON UserSeller.RoleId = RolePermissions.RoleId 
                    WHERE UserSeller.UserSellerId=%(userSellerId)s 
                    ORDER BY Permissions.PermissionId"""
        data = {
            'userSellerId': userSellerId
        }
        
        rows = db.queryAll(sql, data)
        
        for row in rows:
            permissionId = int(row["PermissionId"])
            permissions.append(permissionId)
            
        return permissions
    
    def __validateUserName(self, username: str):
        if username == None or username.strip() == "":
            return "Please enter a username"
        username = username.strip()
        if utility.validateEmailAddress(username) == False:
            return "Username must be a valid email address"
    
        sql = "SELECT UserId FROM Users WHERE Username = %(username)s"
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
            to = "tj@national-acts.com"
            #to = "dwbodine@gmail.com"

            result = utility.sendEmail(to, subject, html, "New User Registration")
        else:
            result.success = False
            result.error = "Could not find new user in database"
        return result 