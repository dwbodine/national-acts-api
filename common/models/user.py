"""
User models
"""


class Permission:
    """
    Single permission in system
    """

    def __init__(self, permission_id: int, permission_name: str):
        self.permission_id = permission_id
        self.permission_name = permission_name


class Role:
    """
    Single role with attached permissions in system
    """

    role_id: int = 0
    role_name: str = None
    permissions: list[Permission] = []


class UserSeller:
    """
    User seller with attached permissions
    """

    permissions: list[int] = []
    routes: list[str] = []

    def __init__(
        self,
        user_seller_id: int,
        seller_id: int,
        seller_name: str,
        seller_type: int,
        role_id: int,
        hide_seller_rate: bool,
    ):
        self.user_seller_id = user_seller_id
        self.seller_id = seller_id
        self.seller_name = seller_name
        self.seller_type = seller_type
        self.role_id = role_id
        self.hide_seller_rate = hide_seller_rate


class UserActivity:
    """
    User activity object
    """

    def __init__(
        self,
        user_activity_id: int,
        user_id: int,
        activity_type: int,
        activity_data: str,
        activity_time: str,
        activity_name: str,
        username: str,
        full_name: str,
        seller_name: str,
    ):
        self.user_activity_id = user_activity_id
        self.user_id = user_id
        self.activity_type = activity_type
        self.activity_data = activity_data
        self.activity_time = activity_time
        self.activity_name = activity_name
        self.username = username
        self.full_name = full_name
        self.seller_name = seller_name


class User:
    """
    User object
    """

    user_id: int = 0
    is_admin: bool = False
    username: str = None
    password: str = None
    is_authenticated: bool = False
    first_name: str = None
    last_name: str = None
    mobile: str = None
    notes: str = None
    is_active: bool = False
    created_at: str = None
    token: str = None
    category: str = None
    require_reset_password: bool = False
    last_update: str = None
    send_email_reset: bool = False
    send_text_reset: bool = False
    disable_check_in: bool = False
    sellers: list[UserSeller] = []

    def user_full_name(self):
        """
        Convenience method to return user's full name
        """
        return self.first_name + " " + self.last_name + " (" + self.username + ")"


class UserResponse:
    """
    User response object for API calls
    """

    def __init__(self, user: User, error_message: str = None):
        self.user = user
        self.error_message = error_message

    def has_error(self):
        """
        Returns true/false if error message is present
        """
        return self.error_message is not None and self.error_message != ""
