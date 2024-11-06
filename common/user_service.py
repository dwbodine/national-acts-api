"""
User service module
"""

from datetime import datetime
import hashlib
import random

from common.models.user import (
    UserResponse,
    User,
    Role,
    Permission,
    UserActivity,
    UserSeller,
)
from common.db import db_query_all, db_query_one, db_update, db_insert, db_delete
from common.utility import (
    log_message,
    send_email,
    validate_email_address,
    SendEmailResult,
)


class UserService:
    """
    Service to deal with user operations
    """

    # PUBLIC METHODS
    def login(self, username: str, password: str):
        """
        securely login user and create token
        """
        try:
            user: User = None
            error_message: str = None
            is_valid_input: bool = True

            if username is None or username == "" or password is None or password == "":
                is_valid_input = False
                error_message = "Incorrect username or password"

            if is_valid_input:
                # check to see if they exist first and pull data
                sql = "SELECT Password, RequireResetPassword FROM Users WHERE Username=%(username)s"
                data = {"username": username}
                row = db_query_one(sql, data)

                if row:
                    require_reset = (
                        True if int(row["RequireResetPassword"]) == 1 else False
                    )
                    if require_reset:
                        error_message = """Password reset required -
                         please click on "Forgot Password?" to proceed"""
                    else:
                        hashed_password = str(row["Password"])
                        authenticated = self.__password_verify(
                            password, hashed_password
                        )
                        if authenticated:
                            user = self.__retrieve_user_from_database(
                                username=username, fetch_sellers=True
                            )
                            user.is_authenticated = True
                else:
                    error_message = "Incorrect username or password"

        except RuntimeError as err:
            user = None
            error_message: str = "Error occurred during login"
            log_message(f"Unexpected {err=}, {type(err)=}")

        return UserResponse(user, error_message)

    def register_user(
        self,
        username: str,
        password: str,
        confirm_password: str,
        first_name: str,
        last_name: str,
        seller_id: int = None,
    ):
        """
        Register a new user
        """
        try:
            # validate input
            username_error = self.__validate_username(username)
            if username_error is not None:
                return UserResponse(None, username_error)

            password_error = self.__validate_password(password, confirm_password)
            if password_error is not None:
                return UserResponse(None, password_error)

            if first_name is None or first_name == "":
                return UserResponse(None, "First name cannot be blank")

            if last_name is None or last_name == "":
                return UserResponse(None, "Last name cannot be blank")

            user: User = None
            error_message: str = None

            hashed_password = self.__password_hash(password)
            sql = """INSERT INTO Users (Username, Password, FirstName, LastName)
                        VALUES (%(username)s, %(password)s, %(firstName)s, %(lastName)s)"""
            data = {
                "username": username,
                "password": hashed_password,
                "firstName": first_name,
                "lastName": last_name,
            }
            user_id = db_insert(sql, data)
            if user_id > 0:
                if seller_id is not None and seller_id > 0:
                    sql = """INSERT INTO UserSeller (UserId, SellerId)
                            VALUES (%(userId)s, %(sellerId)s)"""
                    data = {"userId": user_id, "sellerId": seller_id}
                    user_seller_id = db_insert(sql, data)
                    if user_seller_id <= 0:
                        error_message = """Error occurred during user registration,
                            please contact your administrator"""
            else:
                error_message = """Error occurred during user registration,
                            please contact your administrator"""
        except RuntimeError as err:
            user = None
            error_message = """Error occurred during user registration,
                            please contact your administrator"""
            log_message(f"Unexpected {err=}, {type(err)=}")

        return UserResponse(user, error_message)

    def send_password_reset_email(self, username: str):
        """
        Sends an email to the user with the password reset code
        """
        try:
            if username is None or username == "":
                return UserResponse(None, "Username cannot be blank")

            error_message: str = None
            user = self.__retrieve_user_from_database(username=username)
            if user is not None:
                code = self.__generate_password_code(user.username)
                if code > 0:
                    html = f"""A password reset request has been requested for you
                        from national-acts.com.\n\nPlease use this security code
                        to confirm your email in our system:\n\n{str(code)}"""
                    subject = "National Acts VIP - Password Reset"
                    to_name = user.first_name + " " + user.last_name
                    result = send_email(username, subject, html, to_name)
                    if result.success is not True:
                        user = None
                        error_message = (
                            "Error occurred during password reset: " + result.error
                        )
                else:
                    user = None
                    error_message = "Error occurred during password reset"
            else:
                error_message = "User not found"
        except RuntimeError as err:
            user = None
            error_message = "Error occurred during password reset"
            log_message(f"Unexpected {err=}, {type(err)=}")

        return UserResponse(user, error_message)

    def validate_password_reset_code(self, username: str, code: int):
        """
        Validate reset code against value stored for user in database
        """
        try:
            if username is None or username == "":
                return UserResponse(None, "Username cannot be blank")

            error_message: str = None
            user: User = None
            user_id: int = 0

            user = self.__retrieve_user_from_database(username=username)

            if user is None:
                return UserResponse(None, "User not found")

            user_id = user.user_id

            sql = """SELECT * FROM ForgotPasswordToken
                        WHERE UserId=%(userId)s
                        AND Code=%(code)s AND IsExpired=0"""
            data = {"userId": user_id, "code": code}
            row = db_query_one(sql, data)
            if not row:
                user = None
                error_message = "Invalid code"
        except RuntimeError as err:
            user = None
            error_message = "Error occurred during password reset"
            log_message(f"Unexpected {err=}, {type(err)=}")

        return UserResponse(user, error_message)

    def reset_password(
        self, username: str, code: int, password: str, confirm_password: str
    ):
        """
        Reset user password
        """
        password_error = self.__validate_password(password, confirm_password)
        if password_error is not None:
            return UserResponse(None, password_error)

        response = self.validate_password_reset_code(username, code)

        if response.has_error():
            return response

        user = response.user
        error_message: str = None

        self.__expire_all_user_tokens(username)

        sql = """UPDATE Users SET Password=%(password)s,
                RequireResetPassword=0, LastUpdate=CURRENT_TIMESTAMP
                WHERE Username=%(username)s"""
        data = {"username": username, "password": self.__password_hash(password)}
        success = db_update(sql, data)
        if success is not True:
            user = None
            error_message = "Error occurred during password reset"

        return UserResponse(user, error_message)

    def reset_password_secured(
        self, username: str, password: str, confirm_password: str
    ):
        """
        Reset password for user already logged in
        """
        password_error = self.__validate_password(password, confirm_password)
        if password_error is not None:
            return UserResponse(None, password_error)

        user = self.__retrieve_user_from_database(username=username)
        error_message: str = None

        self.__expire_all_user_tokens(username)

        sql = """UPDATE Users SET Password=%(password)s,
                RequireResetPassword=0, LastUpdate=CURRENT_TIMESTAMP
                WHERE Username=%(username)s"""
        data = {"username": username, "password": self.__password_hash(password)}
        success = db_update(sql, data)
        if success is not True:
            user = None
            error_message = "Error occurred during password reset"

        return UserResponse(user, error_message)

    def register(
        self,
        username: str,
        first_name: str,
        last_name: str,
        seller_id: int,
        password: str,
        confirm_password: str,
        notes: str = None,
    ):
        """
        Start user registration
        """
        password_error = self.__validate_password(password, confirm_password)
        if password_error is not None:
            return UserResponse(None, password_error)

        user: User = self.get_user_by_user_name(username=username)

        if user is not None:
            return UserResponse(
                None, "There is already a user in the system with that email"
            )

        error_message: str = None

        sql = """INSERT INTO Users (Username, FirstName, LastName, Password, Notes)
                     VALUES (%(username)s, %(firstName)s, %(lastName)s, %(password)s, %(notes)s)"""
        data = {
            "username": username,
            "firstName": first_name,
            "lastName": last_name,
            "password": self.__password_hash(password),
            "notes": notes,
        }
        user_id = db_insert(sql, data)

        if user_id <= 0:
            user = None
            error_message = "Error occurred while registering user"

        sql2 = """INSERT INTO UserSeller (UserId, SellerId) VALUES (%(userId)s, %(sellerId)s)"""
        data2 = {"userId": user_id, "sellerId": seller_id}
        user_seller_id = db_insert(sql2, data2)

        if user_seller_id > 0:
            reg_email_result = self.__send_registration_email(username)

            if reg_email_result.success is not True:
                user = None
                error_message = reg_email_result.error

            user = self.get_user_by_id(user_id)
        else:
            user = None
            error_message = (
                """Error occurred while updating sellers during registration"""
            )

        return UserResponse(user, error_message)

    def get_user_by_id(self, user_id: int, fetch_sellers: bool = False):
        """
        Fetch user by user_id
        """
        return self.__retrieve_user_from_database(
            user_id=user_id, fetch_sellers=fetch_sellers
        )

    def get_user_by_user_name(self, username: str, fetch_sellers: bool = False):
        """
        Fetch user by username
        """
        return self.__retrieve_user_from_database(
            username=username, fetch_sellers=fetch_sellers
        )

    def get_all_users(self):
        """
        Get all users in the system
        """
        users: list[User] = []
        sql: str = """SELECT Users.* FROM Users"""
        rows = db_query_all(sql)
        for row in rows:
            user = User()
            user.user_id = int(row["UserId"])
            user.is_admin = True if int(row["IsAdmin"]) == 1 else False
            user.username = str(row["Username"])
            user.first_name = str(row["FirstName"])
            user.last_name = str(row["LastName"])
            user.is_active = True if int(row["IsActive"]) == 1 else False
            user.notes = str(row["Notes"])
            user.mobile = str(row["Mobile"])
            user.require_reset_password = (
                True if int(row["RequireResetPassword"]) == 1 else False
            )
            user.send_email_reset = True if int(row["SendEmailReset"]) == 1 else False
            user.send_text_reset = True if int(row["SendTextReset"]) == 1 else False
            user.disable_check_in = True if int(row["DisableCheckIn"]) == 1 else False
            created_at = datetime.fromisoformat(str(row["CreatedAt"]))
            last_update = datetime.fromisoformat(str(row["LastUpdate"]))
            user.created_at = created_at.strftime("%m/%d/%Y")
            user.last_update = last_update.strftime("%m/%d/%Y")

            sellers = self.__get_user_sellers(user.user_id, user.is_admin)
            user.sellers = sellers
            if user.is_admin:
                user.category = "Admin"
            elif len(user.sellers) > 1:
                user.category = "Multiple"
            elif len(user.sellers) > 0:
                user.category = user.sellers[0].seller_name
            users.append(user)
        return users

    def get_all_permissions(self):
        """
        Get all permissions in the system
        """
        permissions: list[Permission] = []
        sql = """SELECT * FROM Permissions ORDER BY PermissionName"""
        rows = db_query_all(sql)
        for row in rows:
            permission_id = int(row["PermissionId"])
            name = str(row["PermissionName"])
            permission = Permission(permission_id, name)
            permissions.append(permission)
        return permissions

    def get_all_roles(self):
        """
        Get all roles in the system
        """
        roles: list[Role] = []
        sql = """SELECT * FROM Roles ORDER BY RoleId"""
        rows = db_query_all(sql)
        for row in rows:
            role_id = int(row["RoleId"])
            role_name = str(row["RoleName"])
            role = Role()
            role.role_id = role_id
            role.role_name = role_name
            permissions = self.__get_permissions_for_role(role_id)
            role.permissions = permissions
            roles.append(role)
        return roles

    def get_role_by_id(self, role_id: int):
        """
        Get role by role_id
        """
        role: Role = None
        sql = """SELECT * FROM Roles WHERE RoleId=%(roleId)s"""
        data = {"roleId": role_id}
        row = db_query_one(sql, data)
        if row:
            role_id = int(row["RoleId"])
            role_name = str(row["RoleName"])
            role = Role()
            role.role_id = role_id
            role.role_name = role_name
            permissions = self.__get_permissions_for_role(role_id)
            role.permissions = permissions
        return role

    def update_role(self, role_to_update: Role):
        """
        Update or Create role
        """
        success: bool = True
        if role_to_update is None:
            return False
        existing_role: Role = None
        if role_to_update.roleId > 0:
            existing_role = self.get_role_by_id(role_to_update.roleId)
        if existing_role is not None:
            role_id = existing_role.role_id
            update_sql = """UPDATE Roles SET RoleName=%(roleName)s,
                        LastUpdate=CURRENT_TIMESTAMP WHERE RoleId=%(roleId)s"""
            update_data = {"roleName": role_to_update.roleName, "roleId": role_id}
            success = db_update(update_sql, update_data)
            if success is True:
                success = self.__assign_permissions_to_role_id(
                    role_id, role_to_update.permissions
                )
        else:
            insert_sql = """INSERT INTO Roles (RoleName) VALUES (%(roleName)s)"""
            insert_data = {"roleName": role_to_update.roleName}
            role_id = db_insert(insert_sql, insert_data)
            if role_id > 1:
                success = self.__assign_permissions_to_role_id(
                    role_id, role_to_update.permissions
                )
        return success

    def delete_roles(self, role_ids_to_delete: list[int]):
        """
        Delete list of roles
        """
        success: bool = True
        if len(role_ids_to_delete) > 0:
            role_id_list = ",".join(str(x) for x in role_ids_to_delete)
            delete_permission_sql = (
                """DELETE FROM RolePermissions WHERE RoleId IN (%(roleList)s)"""
            )
            delete_role_data = {"roleList": role_id_list}
            success = db_delete(delete_permission_sql, delete_role_data)
            if success is True:
                delete_row_sql = """DELETE FROM Roles WHERE RoleId IN (%(roleList)s)"""
                success = db_delete(delete_row_sql, delete_role_data)
        return success

    def update_user(self, user_to_update: User):
        """
        Update existing user (does not create)
        """
        success: bool = True
        if (
            user_to_update is None
            or user_to_update.user_id is None
            or user_to_update.user_id <= 0
        ):
            return False
        user_id: int = user_to_update.user_id
        existing_user: User = self.__retrieve_user_from_database(user_id=user_id)
        if existing_user is not None:
            username = existing_user.username
            if user_to_update.username is not None and user_to_update.username != "":
                username = user_to_update.username
            send_text_reset = user_to_update.send_text_reset
            if (
                user_to_update.mobile is None
                or user_to_update.mobile == ""
                or user_to_update.mobile == "None"
            ):
                send_text_reset = False
                user_to_update.mobile = ""
            update_sql = """UPDATE Users SET IsAdmin=%(isAdmin)s,
                           Username=%(username)s, 
                           FirstName=%(firstName)s, 
                           LastName=%(lastName)s, 
                           Mobile=%(mobile)s,
                           Notes=%(notes)s, 
                           IsActive=%(isActive)s, 
                           RequireResetPassword=%(requireResetPassword)s, 
                           SendEmailReset=%(sendEmailReset)s,
                           SendTextReset=%(sendTextReset)s, 
                           DisableCheckIn=%(disableCheckin)s, 
                           LastUpdate=CURRENT_TIMESTAMP 
                           WHERE UserId=%(userId)s"""
            update_data = {
                "isAdmin": 1 if user_to_update.is_admin else 0,
                "username": username,
                "firstName": user_to_update.first_name,
                "lastName": user_to_update.last_name,
                "mobile": user_to_update.mobile,
                "notes": user_to_update.notes,
                "isActive": 1 if user_to_update.is_active else 0,
                "requireResetPassword": (
                    1 if user_to_update.require_reset_password else 0
                ),
                "sendEmailReset": 1 if user_to_update.send_email_reset else 0,
                "disableCheckin": 1 if user_to_update.disable_check_in else 0,
                "sendTextReset": 1 if send_text_reset else 0,
                "userId": user_id,
            }
            success = db_update(update_sql, update_data)
            if success is True:
                success = self.__assign_user_to_sellers(
                    user_id, user_to_update.is_admin, user_to_update.sellers
                )
        else:
            success = False
        return success

    def delete_user(self, user_id: int):
        """
        Delete user from system
        """
        success: bool = False
        data = {"userId": user_id}

        try:
            user_seller_sql = """DELETE FROM UserSeller WHERE UserId=%(userId)s"""
            success = db_delete(user_seller_sql, data)

            user_activity_sql = """DELETE FROM UserActivity WHERE UserId=%(userId)s"""
            success = db_delete(user_activity_sql, data)

            user_sql = """DELETE FROM Users WHERE UserId=%(userId)s"""
            success = db_delete(user_sql, data)
        except RuntimeError as err:
            success = False
            log_message(f"Unexpected {err=}, {type(err)=}")

        return success

    def log_user_activity(self, user_id: int, activity_id: int, activity_data: str):
        """
        Log user activity from the UI
        """
        sql = ""
        data = {"userId": user_id, "activityId": activity_id}
        if len(activity_data) > 0:
            sql = """INSERT INTO UserActivity (UserId, ActivityId, ActivityData)
                         VALUES (%(userId)s, %(activityId)s, %(activityData)s)"""
            data["activityData"] = activity_data
        else:
            sql = """INSERT INTO UserActivity (UserId, ActivityId)
                         VALUES (%(userId)s, %(activityId)s)"""

        success = db_update(sql, data)
        return success

    def get_user_activity(
        self,
        start: int,
        end: int,
        user_id: int = None,
        activity_type: int = None,
        filter_admins: bool = False,
    ):
        """
        Get a report of user activity
        """
        activities: list[UserActivity] = []
        sql = """SELECT UserActivity.*, Activity.ActivityName, Users.Username
                     FROM UserActivity 
                    JOIN Activity ON Activity.ActivityId=UserActivity.ActivityId 
                    JOIN Users ON Users.UserId=UserActivity.UserId 
                    WHERE UserActivity.Timestamp BETWEEN %(startDate)s AND %(endDate)s"""
        data = {
            "startDate": datetime.fromtimestamp(start).strftime("%Y-%m-%d"),
            "endDate": datetime.fromtimestamp(end).strftime("%Y-%m-%d"),
        }

        where_clause: list[str] = []

        if user_id is not None:
            where_clause.append("UserActivity.UserId = %(userId)s")
            data["userId"] = user_id

        if activity_type is not None:
            where_clause.append("UserActivity.ActivityId = %(activityId)s")
            data["activityId"] = activity_type

        if filter_admins is True:
            where_clause.append("Users.IsAdmin <> 1")

        if len(where_clause) > 0:
            sql += " AND "
            sql += " AND ".join(where_clause)

        sql += " ORDER BY UserActivity.Timestamp DESC, Username ASC"

        rows = db_query_all(sql, data)
        for row in rows:
            activity_user_id = int(row["UserId"])
            activity_type = int(row["ActivityId"])
            activity_name = str(row["ActivityName"])
            username = str(row["Username"])
            activity_data = str(row["ActivityData"])
            activity_time = str(row["Timestamp"])
            activity = UserActivity(
                activity_user_id,
                activity_type,
                activity_data,
                activity_time,
                activity_name,
                username,
            )
            activities.append(activity)

        return activities

    def get_user_seller_by_event_id(self, user_id: int, event_id: int):
        """
        Get user seller from event_id and user_id
        """
        user_seller: UserSeller = None

        user = self.__retrieve_user_from_database(user_id=user_id, fetch_sellers=True)

        sql = """SELECT SellerEventCategory.SellerId
                 FROM TicketSocketEvents 
                JOIN SellerEventCategory
                    ON SellerEventCategory.SellerEventCategoryId
                        = TicketSocketEvents.SellerEventCategoryId 
                WHERE TicketSocketEvents.Id=%(ticketSocketEventId)s"""

        data = {"ticketSocketEventId": event_id}

        row = db_query_one(sql, data)
        event_seller_id = 0
        if row:
            event_seller_id = int(row["SellerId"])

        if event_seller_id > 0:
            for seller in user.sellers:
                if seller.seller_id == event_seller_id:
                    user_seller = seller
                    break

        return user_seller

    def __get_permissions_for_role(self, role_id: int):
        permissions: list[Permission] = []
        if role_id is None:
            return permissions

        sql = ""
        if role_id > 1:
            sql = """SELECT Permissions.PermissionId, Permissions.PermissionName
                     FROM Permissions 
                    JOIN RolePermissions
                        ON RolePermissions.PermissionId = Permissions.PermissionId 
                    WHERE RolePermissions.RoleId=%(roleId)s"""
        else:
            sql = """SELECT Permissions.PermissionId, Permissions.PermissionName
                     FROM Permissions"""

        data = {"roleId": role_id}
        rows = db_query_all(sql, data)
        for row in rows:
            permission_id = int(row["PermissionId"])
            permission_name = str(row["PermissionName"])
            permission = Permission(permission_id, permission_name)
            permissions.append(permission)
        return permissions

    def __assign_user_to_sellers(
        self, user_id: int, is_admin: bool, new_sellers: list[UserSeller]
    ):
        """
        Update list of sellers for user
        """
        success: bool = True
        existing_user: User = self.__retrieve_user_from_database(
            user_id=user_id, fetch_sellers=True
        )
        if existing_user is not None:
            if is_admin is True:
                delete_seller_sql = """DELETE FROM UserSeller WHERE UserId=%(userId)s"""
                delete_seller_data = {"userId": user_id}
                db_delete(delete_seller_sql, delete_seller_data)
            else:
                new_seller_ids = [seller.seller_id for seller in new_sellers]
                for existing_seller in existing_user.sellers:
                    existing_seller_id = existing_seller.seller_id
                    if existing_seller_id in new_seller_ids:
                        new_seller: UserSeller = self.__get_user_seller_from_list_by_id(
                            new_sellers, existing_seller_id
                        )
                        if existing_seller.role_id != new_seller.role_id:
                            update_role_sql = """UPDATE UserSeller SET RoleId=%(roleId)s,
                                                 LastUpdate=CURRENT_TIMESTAMP
                                                 WHERE UserSellerId=%(userSellerId)s"""
                            update_role_data = {
                                "roleId": new_seller.role_id,
                                "userSellerId": existing_seller.userSellerId,
                            }
                            success = db_update(update_role_sql, update_role_data)
                        new_seller_ids.remove(existing_seller_id)
                    else:
                        delete_seller_sql = """DELETE FROM UserSeller
                                            WHERE UserSellerId=%(userSellerId)s"""
                        delete_seller_data = {
                            "userSellerId": existing_seller.userSellerId
                        }
                        success = db_delete(delete_seller_sql, delete_seller_data)
                if len(new_seller_ids) > 0:
                    for new_seller_id in new_seller_ids:
                        if new_seller_id > 0:
                            new_seller: UserSeller = (
                                self.__get_user_seller_from_list_by_id(
                                    new_sellers, new_seller_id
                                )
                            )
                            if new_seller is not None:
                                insert_seller_sql = """INSERT INTO UserSeller
                                                (UserId, SellerId, RoleId)
                                                VALUES (%(userId)s, %(sellerId)s, %(roleId)s)"""
                                insert_seller_data = {
                                    "userId": user_id,
                                    "sellerId": new_seller_id,
                                    "roleId": new_seller.role_id,
                                }
                                user_seller_id = db_insert(
                                    insert_seller_sql, insert_seller_data
                                )
                                success = user_seller_id > 0
        else:
            success = False
        return success

    def __assign_permissions_to_role_id(
        self, role_id: int, new_permissions: list[Permission]
    ):
        """
        Update permissions for selected role
        """
        existing_role = self.get_role_by_id(role_id)
        success: bool = True
        if existing_role is not None:
            new_permission_ids = [
                permission.permission_id for permission in new_permissions
            ]
            for existing_permission in existing_role.permissions:
                existing_permission_id = existing_permission.permission_id
                if existing_permission_id in new_permission_ids:
                    new_permission_ids.remove(existing_permission_id)
                else:
                    delete_row_sql = """DELETE FROM RolePermissions
                                    WHERE RoleId=%(roleId)s
                                    AND PermissionId=%(permissionId)s"""
                    delete_role_data = {
                        "permissionId": existing_permission_id,
                        "roleId": role_id,
                    }
                    success = db_delete(delete_row_sql, delete_role_data)
            if len(new_permission_ids) > 0:
                for new_permission_id in new_permission_ids:
                    if new_permission_id > 0:
                        new_permission: Permission = (
                            self.__get_permission_from_list_by_id(
                                new_permissions, new_permission_id
                            )
                        )
                        if new_permission is not None:
                            insert_permission_sql = """INSERT INTO RolePermissions
                                                    (RoleId, PermissionId)
                                                    VALUES (%(roleId)s, %(permissionId)s)"""
                            insert_permission_data = {
                                "roleId": role_id,
                                "permissionId": new_permission_id,
                            }
                            role_permission_id = db_insert(
                                insert_permission_sql, insert_permission_data
                            )
                            success = role_permission_id > 0
        return success

    def __get_user_seller_from_list_by_id(
        self, sellers: list[UserSeller], user_seller_id: int
    ):
        """
        Filter one user seller from list by id
        """
        user_seller: UserSeller = None
        for seller in sellers:
            if seller.seller_id == user_seller_id:
                user_seller = seller
                break
        return user_seller

    def __get_permission_from_list_by_id(
        self, permissions: list[Permission], permission_id: int
    ):
        """
        Filter one permission from list by id
        """
        permission: Permission = None
        for p in permissions:
            if p.permission_id == permission_id:
                permission = p
                break
        return permission

    def __expire_all_user_tokens(self, username: str):
        """
        Clean up all user's forgot password tokens
        """
        expire_sql = """UPDATE ForgotPasswordToken SET IsExpired=1,
                        LastUpdate=CURRENT_TIMESTAMP
                        WHERE UserId IN
                        (SELECT UserId FROM Users WHERE Username=%(username)s)"""
        expire_data = {"username": username}
        db_update(expire_sql, expire_data)

    def __generate_password_code(self, username: str):
        """
        Generate and store 6-digit reset password code
        """
        if username is None or username == "":
            return 0

        self.__expire_all_user_tokens(username)

        user = self.__retrieve_user_from_database(username=username)

        if user is None:
            return 0

        created_on = datetime.now().timestamp()
        code = random.randint(100000, 999999)

        sql = """INSERT INTO ForgotPasswordToken
                (UserId, Code, CreatedOn)
                VALUES (%(userId)s, %(code)s, %(createdOn)s)"""
        data = {"userId": user.user_id, "code": code, "createdOn": created_on}
        token_id = db_insert(sql, data)
        if token_id > 0:
            return code
        else:
            return 0

    def __password_verify(self, password: str, hashed_password: str):
        """
        Verify plain-text password against encrypted stored value
        """
        generated_hashed_password = self.__password_hash(password)
        return generated_hashed_password == hashed_password

    def __password_hash(self, password: str):
        """
        Create encrypted hashed password
        """
        hash_object = hashlib.sha256()
        hash_object.update(password.encode())
        hash_password = hash_object.hexdigest()
        return hash_password

    def __retrieve_user_from_database(
        self, user_id: int = None, username: str = None, fetch_sellers: bool = False
    ):
        """
        Fetch user from database by 1. user_id then 2. username
        """
        sql: str = None
        data = {}
        user: User = None
        if user_id is not None and user_id > 0:
            sql = """SELECT Users.*
                        FROM Users 
                        WHERE Users.UserId=%(userId)s"""
            data = {"userId": user_id}
        elif username is not None and username != "":
            sql = """SELECT Users.*
                         FROM Users 
                        WHERE Users.Username=%(username)s"""
            data = {"username": username}

        if sql is not None:
            row = db_query_one(sql, data)
            if row:
                user = User()
                user.user_id = int(row["UserId"])
                user.is_admin = True if int(row["IsAdmin"]) == 1 else False
                user.username = str(row["Username"])
                user.first_name = str(row["FirstName"])
                user.last_name = str(row["LastName"])
                user.is_active = True if int(row["IsActive"]) == 1 else False
                user.notes = str(row["Notes"])
                user.mobile = str(row["Mobile"])
                user.require_reset_password = (
                    True if int(row["RequireResetPassword"]) else False
                )
                user.send_email_reset = True if int(row["SendEmailReset"]) else False
                user.send_text_reset = True if int(row["SendTextReset"]) else False
                user.disable_check_in = True if int(row["DisableCheckIn"]) else False
                created_at = datetime.fromisoformat(str(row["CreatedAt"]))
                last_update = datetime.fromisoformat(str(row["LastUpdate"]))
                user.created_at = created_at.strftime("%m/%d/%Y")
                user.last_update = last_update.strftime("%m/%d/%Y")

                if fetch_sellers is True:
                    sellers = self.__get_user_sellers(user.user_id, user.is_admin)
                    user.sellers = sellers
                    if user.is_admin:
                        user.category = "Admin"
                    elif len(user.sellers) > 1:
                        user.category = "Multiple"
                    elif len(user.sellers) > 0:
                        user.category = user.sellers[0].seller_name

        return user

    def __get_user_sellers(self, user_id: int, is_admin: bool):
        """
        Get list of assigned sellers for user (all for admin)
        """
        sellers: list[UserSeller] = []
        if user_id is None or user_id <= 0:
            return sellers

        data = {}
        sql = ""
        if is_admin is False:
            sql = """SELECT UserSeller.UserSellerId, Sellers.SellerId,
                        Sellers.Name, Sellers.SellerTypeId, UserSeller.RoleId
                         FROM Sellers
                        JOIN UserSeller on UserSeller.SellerId = Sellers.SellerId 
                        WHERE UserSeller.UserId=%(userId)s AND Sellers.Inactive <> 1
                        ORDER BY Sellers.Name ASC"""
            data = {"userId": user_id}
        else:
            sql = """SELECT 0 as UserSellerId, Sellers.SellerId,
                    Sellers.Name, Sellers.SellerTypeId, 1 AS RoleId
                    FROM Sellers ORDER BY Sellers.Name ASC"""

        rows = db_query_all(sql, data)

        for row in rows:
            user_seller_id = int(row["UserSellerId"])
            seller_id = int(row["SellerId"])
            seller_name = str(row["Name"])
            seller_type = int(row["SellerTypeId"])
            role_id = int(row["RoleId"])
            us = UserSeller(
                user_seller_id, seller_id, seller_name, seller_type, role_id
            )
            if is_admin is False:
                permissions = self.__get_user_seller_permissions(user_seller_id)
                us.permissions = permissions
            sellers.append(us)

        return sellers

    def __get_user_seller_permissions(self, user_seller_id: int):
        """
        Get permissions for user by seller
        """
        permissions: list[int] = []
        if user_seller_id is None or user_seller_id <= 1:
            return permissions

        sql = """SELECT Permissions.PermissionId FROM Permissions
                    JOIN RolePermissions ON RolePermissions.PermissionId = Permissions.PermissionId 
                    JOIN UserSeller ON UserSeller.RoleId = RolePermissions.RoleId 
                    WHERE UserSeller.UserSellerId=%(userSellerId)s 
                    ORDER BY Permissions.PermissionId"""
        data = {"userSellerId": user_seller_id}

        rows = db_query_all(sql, data)

        for row in rows:
            permission_id = int(row["PermissionId"])
            permissions.append(permission_id)

        return permissions

    def __validate_username(self, username: str):
        """
        Validate username
        """
        if username is None or username.strip() == "":
            return "Please enter a username"
        username = username.strip()
        if validate_email_address(username) is False:
            return "Username must be a valid email address"

        sql = "SELECT UserId FROM Users WHERE Username = %(username)s"
        data = {"username": username}
        row = db_query_one(sql, data)
        if row:
            return "That username is already taken"
        return None

    def __validate_password(self, password: str, confirm_password: str):
        """
        Validate password
        """
        if password is None or password.strip() == "":
            return "Please enter a password"
        password = password.strip()
        if len(password) < 6:
            return "Password must have at least 6 characters."
        if confirm_password is None or confirm_password.strip() == "":
            return "Please enter confirm password"
        confirm_password = confirm_password.strip()
        if password != confirm_password:
            return "Passwords do not match"
        return None

    def __send_registration_email(self, username: str):
        """
        Send notice to TJ that a new user has registered
        """
        result = SendEmailResult(True, None)
        user = self.__retrieve_user_from_database(username=username)
        if user is not None:
            html = "<table>"
            html += "<tr><td>User Email:</td><td>" + username + "</td></tr>"
            html += "<tr><td>Submitted:</td><td>" + user.created_at + "</td></tr>"
            html += "<tr><td><td>Notes:</td><td>" + user.notes + "</td></tr>"
            html += "</table>"

            subject = "New User Registration"
            to = "tj@national-acts.com"
            # to = "dwbodine@gmail.com"

            result = send_email(to, subject, html, "New User Registration")
        else:
            result.success = False
            result.error = "Could not find new user in database"
        return result
