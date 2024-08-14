from enum import Enum

class Permission:
    def __init__(self, permissionId: int, name: str):
        self.permissionId = permissionId
        self.name = name
        
class Role:
    permissions: list[Permission] = []
    def __init__(self, roleId: int, name: str):
        self.roleId = roleId
        self.name = name

class UserSeller:
    permissions: list[int] = []
    def __init__(self, sellerId: int, sellerName: str, sellerType: int, roleId: int):
        self.sellerId = sellerId
        self.sellerName = sellerName
        self.sellerType = sellerType
        self.roleId = roleId
        
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
    sellers: list[UserSeller] = []
    
    def userFullname(self):
        return self.firstName + " " + self.lastName + " (" + self.username + ")"

class UserResponse:
    def __init__(self, user: User, errorMessage: str = None):
        self.user = user
        self.errorMessage = errorMessage
        
    def hasError(self):
        return (self.errorMessage != None and self.errorMessage != "")