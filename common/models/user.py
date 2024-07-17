from enum import Enum

class UserSeller:
    permissions: list[int] = []
    def __init__(self, sellerId: int, sellerName: str, sellerType: int):
        self.sellerId = sellerId
        self.sellerName = sellerName
        self.sellerType = sellerType
        
class User:
    userId: int = 0
    isAdmin: bool = False
    username: str = None
    password: str = None
    isAuthenticated: bool = False
    firstName: str = None
    lastName: str = None
    notes: str = None
    isActive: bool = False
    createdAt: str = None
    token: str = None
    sellers: list[UserSeller] = []
    
    def userFullname(self):
        return self.firstName + " " + self.lastName + " (" + self.username + ")"

class UserResponse:
    def __init__(self, user: User, errorMessage: str = None):
        self.user = user
        self.errorMessage = errorMessage
        
    def hasError(self):
        return (self.errorMessage != None and self.errorMessage != "")