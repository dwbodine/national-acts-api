"""
User service module
"""

from datetime import datetime
import logging
import hashlib
import random
import traceback
import pytz

from common.messaging_service import MessagingService
from common.models.messaging import SendEmailResult
from common.models.user import (
    UserResponse,
    User,
    UserSeller,
)
from common.db import db_query_all, db_query_one, db_update, db_insert, db_delete
from common.role_service import RoleService
from common.utility import (
    get_override_bool_value_or_default,
    get_override_float_value_or_default,
    get_override_int_value_or_default,
    get_override_string_value_or_default,
    get_override_tinyint_value_or_default_from_bool,
    validate_email_address,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
                sql = """SELECT Password, RequireResetPassword, IsActive
                            FROM Users WHERE Username=%(username)s"""
                data = {"username": username}
                row = db_query_one(sql, data)

                if row:
                    require_reset = get_override_bool_value_or_default(
                        row["RequireResetPassword"]
                    )
                    is_active = get_override_bool_value_or_default(row["IsActive"])

                    if require_reset:
                        error_message = """Password reset required -
                         please click on "Forgot Password?" to proceed"""
                    elif is_active is not True:
                        error_message = """Incorrect username or password"""
                    else:
                        hashed_password = get_override_string_value_or_default(
                            row["Password"]
                        )
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
                else:
                    error_message = "Incorrect username or password"

        except Exception as err:  # pylint: disable=broad-exception-caught
            user = None
            error_message: str = "Error occurred during login"
            log_message: str = str(err) + "\n" + traceback.format_exc()
            logger.error("%s", log_message)

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
            sql = """INSERT INTO Users (Username, Password, FirstName, LastName, LastUpdate)
                        VALUES (%(username)s, %(password)s, %(firstName)s, %(lastName)s,
                        CURRENT_TIMESTAMP)"""
            data = {
                "username": username,
                "password": hashed_password,
                "firstName": first_name,
                "lastName": last_name,
            }
            user_id = db_insert(sql, data)
            if user_id > 0:
                if seller_id is not None and seller_id > 0:
                    sql = """INSERT INTO UserSeller (UserId, SellerId, LastUpdate)
                            VALUES (%(userId)s, %(sellerId)s,
                            CURRENT_TIMESTAMP)"""
                    data = {"userId": user_id, "sellerId": seller_id}
                    user_seller_id = db_insert(sql, data)
                    if user_seller_id <= 0:
                        error_message = """Error occurred during user registration,
                            please contact your administrator"""
            else:
                error_message = """Error occurred during user registration,
                            please contact your administrator"""
        except Exception as err:  # pylint: disable=broad-exception-caught
            user = None
            error_message = """Error occurred during user registration,
                            please contact your administrator"""
            log_message: str = str(err) + "\n" + traceback.format_exc()
            logger.error("%s", log_message)

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
                        from nationalactsvip.com.\n\nPlease use this security code
                        to confirm your email in our system:\n\n{str(code)}"""
                    subject = "National Acts VIP Customer Service - Password Reset"
                    to_name = user.first_name + " " + user.last_name
                    service = MessagingService()
                    result = service.send_email(username, subject, html, to_name)
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
        except Exception as err:  # pylint: disable=broad-exception-caught
            user = None
            error_message = "Error occurred during password reset"
            log_message: str = str(err) + "\n" + traceback.format_exc()
            logger.error("%s", log_message)

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
        except Exception as err:  # pylint: disable=broad-exception-caught
            user = None
            error_message = "Error occurred during password reset"
            log_message: str = str(err) + "\n" + traceback.format_exc()
            logger.error("%s", log_message)

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

        sql = """INSERT INTO Users (Username, FirstName, LastName, Password, Notes, LastUpdate)
                     VALUES (%(username)s, %(firstName)s, %(lastName)s, %(password)s, %(notes)s,
                     CURRENT_TIMESTAMP)"""
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
            return UserResponse(user, error_message)

        sql2 = """INSERT INTO UserSeller (UserId, SellerId, LastUpdate)
                    VALUES (%(userId)s, %(sellerId)s,
                    CURRENT_TIMESTAMP)"""
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
        sql: str = (
            """SELECT Users.* FROM Users ORDER BY Users.FirstName, Users.LastName, Users.Username"""
        )
        rows = db_query_all(sql)
        for row in rows:
            user = User()
            user.user_id = get_override_int_value_or_default(row["UserId"])
            user.is_admin = get_override_bool_value_or_default(row["IsAdmin"])
            user.username = get_override_string_value_or_default(row["Username"])
            user.first_name = get_override_string_value_or_default(row["FirstName"])
            user.last_name = get_override_string_value_or_default(row["LastName"])
            user.is_active = get_override_bool_value_or_default(row["IsActive"])
            user.notes = get_override_string_value_or_default(row["Notes"])
            user.mobile = get_override_string_value_or_default(row["Mobile"])
            user.require_reset_password = get_override_bool_value_or_default(
                row["RequireResetPassword"]
            )
            user.send_email_reset = get_override_bool_value_or_default(
                row["SendEmailReset"]
            )
            user.send_text_reset = get_override_bool_value_or_default(
                row["SendTextReset"]
            )
            user.disable_check_in = get_override_bool_value_or_default(
                row["DisableCheckIn"]
            )
            created_at = datetime.fromisoformat(
                get_override_string_value_or_default(row["CreatedAt"])
            )
            last_update = datetime.fromisoformat(
                get_override_string_value_or_default(row["LastUpdate"])
            )
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

    def update_user(self, user_to_update: User):
        """
        Update existing user (does not create)
        """
        success: bool = False
        if user_to_update is None or user_to_update.user_id is None:
            return False

        user_id: int = user_to_update.user_id
        send_text_reset = user_to_update.send_text_reset
        if (
            user_to_update.mobile is None
            or user_to_update.mobile == ""
            or user_to_update.mobile == "None"
        ):
            send_text_reset = False
            user_to_update.mobile = ""
        existing_user: User = None
        update_data = {
            "isAdmin": get_override_tinyint_value_or_default_from_bool(
                user_to_update.is_admin
            ),
            "firstName": get_override_string_value_or_default(
                user_to_update.first_name
            ),
            "lastName": get_override_string_value_or_default(user_to_update.last_name),
            "mobile": get_override_string_value_or_default(user_to_update.mobile),
            "notes": get_override_string_value_or_default(user_to_update.notes),
            "isActive": get_override_tinyint_value_or_default_from_bool(
                user_to_update.is_active
            ),
            "requireResetPassword": get_override_tinyint_value_or_default_from_bool(
                user_to_update.require_reset_password
            ),
            "sendEmailReset": get_override_tinyint_value_or_default_from_bool(
                user_to_update.send_email_reset
            ),
            "disableCheckin": get_override_tinyint_value_or_default_from_bool(
                user_to_update.disable_check_in
            ),
            "sendTextReset": get_override_tinyint_value_or_default_from_bool(
                send_text_reset
            ),
        }

        hashed_password = None
        if user_to_update.password is not None and user_to_update.password != "":
            password = get_override_string_value_or_default(user_to_update.password)
            hashed_password = self.__password_hash(password)

        if user_id > 0:
            existing_user = self.__retrieve_user_from_database(
                user_id=user_id, return_password=True
            )
            if existing_user is not None:
                update_data["userId"] = get_override_string_value_or_default(user_id)
                if (
                    hashed_password is not None
                    and hashed_password != existing_user.password
                ):
                    update_data["password"] = hashed_password
                else:
                    update_data["password"] = existing_user.password

                update_sql = """UPDATE Users SET IsAdmin=%(isAdmin)s,
                            FirstName=%(firstName)s, 
                            LastName=%(lastName)s, 
                            Mobile=%(mobile)s,
                            Notes=%(notes)s, 
                            IsActive=%(isActive)s, 
                            RequireResetPassword=%(requireResetPassword)s, 
                            SendEmailReset=%(sendEmailReset)s,
                            SendTextReset=%(sendTextReset)s, 
                            DisableCheckIn=%(disableCheckin)s, 
                            Password=%(password)s,
                            LastUpdate=CURRENT_TIMESTAMP 
                            WHERE UserId=%(userId)s"""

                success = db_update(update_sql, update_data)
            else:
                success = False
        else:
            update_data["username"] = get_override_string_value_or_default(
                user_to_update.username
            )

            update_data["password"] = hashed_password

            insert_sql = """INSERT INTO Users (Username, Password, IsAdmin, FirstName, LastName,
                            Mobile, Notes, IsActive, RequireResetPassword, SendEmailReset, SendTextReset, 
                            DisableCheckIn) VALUES (
                            %(username)s, %(password)s, %(isAdmin)s, %(firstName)s, %(lastName)s, 
                            %(mobile)s, %(notes)s, %(isActive)s, %(requireResetPassword)s, %(sendEmailReset)s,
                            %(sendTextReset)s, %(disableCheckin)s)"""
            user_id = db_insert(insert_sql, update_data)
            success = user_id > 0

        if success is True:
            success = self.__assign_user_to_sellers(
                user_id, user_to_update.is_admin, user_to_update.sellers
            )

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
        except Exception as err:  # pylint: disable=broad-exception-caught
            success = False
            log_message: str = str(err) + "\n" + traceback.format_exc()
            logger.error("%s", log_message)

        return success

    def get_user_seller_by_event_id(self, user_id: int, event_id: int):
        """
        Get user seller from event_id and user_id
        """
        user_seller: UserSeller = None

        user = self.__retrieve_user_from_database(user_id=user_id, fetch_sellers=True)

        sql = """SELECT SellerId
                 FROM ExternalEvents 
                 WHERE ExternalEvents.EventId=%(event_id)s"""

        data = {"event_id": event_id}

        row = db_query_one(sql, data)
        event_seller_id = 0
        if row:
            event_seller_id = get_override_int_value_or_default(row["SellerId"])

        if event_seller_id > 0:
            for seller in user.sellers:
                if seller.seller_id == event_seller_id:
                    user_seller = seller
                    break

        return user_seller

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
                                "roleId": get_override_int_value_or_default(
                                    new_seller.role_id
                                ),
                                "userSellerId": get_override_int_value_or_default(
                                    existing_seller.user_seller_id
                                ),
                            }
                            success = db_update(update_role_sql, update_role_data)
                        new_seller_ids.remove(existing_seller_id)
                    else:
                        delete_seller_sql = """DELETE FROM UserSeller
                                            WHERE UserSellerId=%(userSellerId)s"""
                        delete_seller_data = {
                            "userSellerId": existing_seller.user_seller_id
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
                                                (UserId, SellerId, RoleId, LastUpdate)
                                                VALUES (%(userId)s, %(sellerId)s, %(roleId)s,
                                                CURRENT_TIMESTAMP)"""
                                insert_seller_data = {
                                    "userId": get_override_int_value_or_default(
                                        user_id
                                    ),
                                    "sellerId": get_override_int_value_or_default(
                                        new_seller_id
                                    ),
                                    "roleId": get_override_int_value_or_default(
                                        new_seller.role_id
                                    ),
                                }
                                user_seller_id = db_insert(
                                    insert_seller_sql, insert_seller_data
                                )
                                success = user_seller_id > 0
        else:
            success = False
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

        pacific_tz = pytz.timezone("America/Los_Angeles")
        created_on = datetime.now(pacific_tz).timestamp()
        code = random.randint(100000, 999999)

        sql = """INSERT INTO ForgotPasswordToken
                (UserId, Code, CreatedOn, LastUpdate)
                VALUES (%(userId)s, %(code)s, %(createdOn)s,
                CURRENT_TIMESTAMP)"""
        data = {
            "userId": get_override_int_value_or_default(user.user_id),
            "code": get_override_int_value_or_default(code),
            "createdOn": get_override_float_value_or_default(created_on),
        }
        token_id = db_insert(sql, data)
        if token_id > 0:
            return code
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
        self,
        user_id: int = None,
        username: str = None,
        fetch_sellers: bool = False,
        return_password: bool = False,
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
                user.user_id = get_override_int_value_or_default(row["UserId"])
                user.is_admin = get_override_bool_value_or_default(row["IsAdmin"])
                user.username = get_override_string_value_or_default(row["Username"])
                user.first_name = get_override_string_value_or_default(row["FirstName"])
                user.last_name = get_override_string_value_or_default(row["LastName"])
                user.is_active = get_override_bool_value_or_default(row["IsActive"])
                user.notes = get_override_string_value_or_default(row["Notes"])
                user.mobile = get_override_string_value_or_default(row["Mobile"])
                if return_password is True:
                    user.password = get_override_string_value_or_default(
                        row["Password"]
                    )
                user.require_reset_password = get_override_bool_value_or_default(
                    row["RequireResetPassword"]
                )
                user.send_email_reset = get_override_bool_value_or_default(
                    row["SendEmailReset"]
                )
                user.send_text_reset = get_override_bool_value_or_default(
                    row["SendTextReset"]
                )
                user.disable_check_in = get_override_bool_value_or_default(
                    row["DisableCheckIn"]
                )
                created_at = datetime.fromisoformat(
                    get_override_string_value_or_default(row["CreatedAt"])
                )
                last_update = datetime.fromisoformat(
                    get_override_string_value_or_default(row["LastUpdate"])
                )
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
                        Sellers.Name, Sellers.SellerTypeId, UserSeller.RoleId,
                        Sellers.HideSellerRate
                         FROM Sellers
                        JOIN UserSeller on UserSeller.SellerId = Sellers.SellerId 
                        WHERE UserSeller.UserId=%(userId)s AND Sellers.Inactive <> 1
                        ORDER BY Sellers.Name ASC"""
            data = {"userId": user_id}
        else:
            sql = """SELECT 0 as UserSellerId, Sellers.SellerId,
                    Sellers.Name, Sellers.SellerTypeId, 1 AS RoleId,
                    Sellers.HideSellerRate
                    FROM Sellers ORDER BY Sellers.Name ASC"""

        rows = db_query_all(sql, data)

        for row in rows:
            user_seller_id = get_override_int_value_or_default(row["UserSellerId"])
            seller_id = get_override_int_value_or_default(row["SellerId"])
            seller_name = get_override_string_value_or_default(row["Name"])
            seller_type = get_override_int_value_or_default(row["SellerTypeId"])
            role_id = get_override_int_value_or_default(row["RoleId"])
            hide_seller_rate = get_override_bool_value_or_default(row["HideSellerRate"])
            us = UserSeller(
                user_seller_id,
                seller_id,
                seller_name,
                seller_type,
                role_id,
                hide_seller_rate,
            )
            routes = self.__get_user_seller_routes(seller_id)
            us.routes = routes
            if is_admin is False:
                role_service = RoleService()
                permissions = role_service.get_user_seller_permissions(user_seller_id)
                us.permissions = permissions
            sellers.append(us)

        return sellers

    def __get_user_seller_routes(self, seller_id: int):
        """
        Get available page routes for seller (if any)
        """
        routes: list[str] = []
        sql = """SELECT DISTINCT Pages.Route
                    FROM Pages 
                    JOIN PageSellers ON PageSellers.PageId = Pages.PageID
                    WHERE PageSellers.SellerId=%(seller_id)s 
                    ORDER BY Pages.Route"""
        data = {"seller_id": seller_id}
        rows = db_query_all(sql, data)
        for row in rows:
            route = get_override_string_value_or_default(row["Route"])
            routes.append(route)
        return routes

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
            notes = get_override_string_value_or_default(user.notes, default="")
            html = "<table>"
            html += "<tr><td>User Email:</td><td>" + username + "</td></tr>"
            html += "<tr><td>Submitted:</td><td>" + user.created_at + "</td></tr>"
            html += "<tr><td><td>Notes:</td><td>" + notes + "</td></tr>"
            html += "</table>"

            subject = "New User Registration"
            to = "tj@nationalactsvip.com"
            # to = "dwbodine@gmail.com"
            service = MessagingService()

            result = service.send_email(to, subject, html, "New User Registration")
        else:
            result.success = False
            result.error = "Could not find new user in database"
        return result
