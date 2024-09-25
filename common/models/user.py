from enum import Enum

class Permission:
    def __init__(self, permissionId: int, permissionName: str):
        self.permissionId = permissionId
        self.permissionName = permissionName
        
class Role:
    permissions: list[Permission] = []
    def __init__(self, roleId: int, roleName: str):
        self.roleId = roleId
        self.roleName = roleName

class UserSeller:
    permissions: list[int] = []
    def __init__(self, userSellerId: int, sellerId: int, sellerName: str, sellerType: int, roleId: int):
        self.userSellerId = userSellerId
        self.sellerId = sellerId
        self.sellerName = sellerName
        self.sellerType = sellerType
        self.roleId = roleId
        
class UserActivity:
    def __init__(self, userId: int, activityType: int, activityData: str, activityTime: str, activityName: str, username: str):
        self.userId = userId
        self.activityType = activityType
        self.activityData = activityData 
        self.activityTime = activityTime
        self.activityName = activityName
        self.username = username
        
class User:
    userId: int = 0
    isAdmin: bool = False
    username: str = None
    password: str = None
    isAuthenticated: bool = False
    firstName: str = None
    lastName: str = None
    mobile: str = None
    notes: str = None
    isActive: bool = False
    createdAt: str = None
    token: str = None
    category: str = None
    requireResetPassword: bool = False
    lastUpdate: str = None
    sendEmailReset: bool = False
    sendTextReset: bool = False
    disableCheckIn: bool = False
    sellers: list[UserSeller] = []
    
    def userFullname(self):
        return self.firstName + " " + self.lastName + " (" + self.username + ")"

class UserResponse:
    def __init__(self, user: User, errorMessage: str = None):
        self.user = user
        self.errorMessage = errorMessage
        
    def hasError(self):
        return (self.errorMessage != None and self.errorMessage != "")