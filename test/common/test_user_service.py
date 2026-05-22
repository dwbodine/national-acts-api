"""
Unit tests for common.user_service helpers.
"""

from datetime import datetime
import hashlib

from common import user_service
from common.models.messaging import SendEmailResult
from common.models.user import User, UserSeller


class FakeMessagingService:
    """
    Test double for email delivery during user-service flows.
    """

    instances = []
    result_to_return = SendEmailResult(True, None)

    def __init__(self):
        self.calls = []
        FakeMessagingService.instances.append(self)

    def send_email(self, to, subject, html, to_name):
        """
        Record outgoing email requests and return the configured result.
        """
        self.calls.append((to, subject, html, to_name))
        return FakeMessagingService.result_to_return


class FakeRoleService:
    """
    Test double for loading user-seller permissions.
    """

    instances = []
    permissions_by_user_seller_id = {}

    def __init__(self):
        self.calls = []
        FakeRoleService.instances.append(self)

    def get_user_seller_permissions(self, user_seller_id):
        """
        Return the configured permission ids for a user-seller record.
        """
        self.calls.append(user_seller_id)
        return FakeRoleService.permissions_by_user_seller_id.get(user_seller_id, [])


class FixedDateTime(datetime):
    """
    Fixed datetime helper for password-code tests.
    """

    @classmethod
    def now(cls, tz=None):
        """
        Return a fixed current datetime.
        """
        current = cls(2026, 4, 23, 12, 0, 0)
        if tz is not None:
            return tz.localize(current)
        return current


def create_user(
    user_id=7,
    username="ada@example.com",
    is_admin=False,
    first_name="Ada",
    last_name="Lovelace",
):
    """
    Create a User instance for tests.
    """
    user = User()
    user.user_id = user_id
    user.username = username
    user.is_admin = is_admin
    user.first_name = first_name
    user.last_name = last_name
    user.is_active = True
    user.notes = "Notes"
    user.mobile = "555-1111"
    user.require_reset_password = False
    user.send_email_reset = True
    user.send_text_reset = True
    user.disable_check_in = False
    user.created_at = "04/23/2026"
    user.last_update = "04/23/2026"
    user.sellers = []
    return user


def create_user_seller(
    user_seller_id=1,
    seller_id=101,
    seller_name="Seller A",
    role_id=2,
):
    """
    Create a UserSeller instance for tests.
    """
    seller = UserSeller(user_seller_id, seller_id, seller_name, 7, role_id, False)
    seller.permissions = []
    seller.routes = []
    return seller


def build_user_row(**overrides):
    """
    Create a database row for user mapping tests.
    """
    row = {
        "UserId": 7,
        "IsAdmin": 0,
        "Username": "ada@example.com",
        "FirstName": "Ada",
        "LastName": "Lovelace",
        "IsActive": 1,
        "Notes": "Notes",
        "Mobile": "555-1111",
        "RequireResetPassword": 0,
        "SendEmailReset": 1,
        "SendTextReset": 1,
        "DisableCheckIn": 0,
        "CreatedAt": "2026-04-23 10:00:00",
        "LastUpdate": "2026-04-23 11:00:00",
    }
    row.update(overrides)
    return row


def build_user_seller_row(**overrides):
    """
    Create a database row for user-seller mapping tests.
    """
    row = {
        "UserSellerId": 1,
        "SellerId": 101,
        "Name": "Seller A",
        "SellerTypeId": 7,
        "RoleId": 2,
        "HideSellerRate": 0,
    }
    row.update(overrides)
    return row


def build_password_hash(password):
    """
    Create the password hash format expected by the service.
    """
    hash_object = hashlib.sha256()
    hash_object.update(password.encode())
    return hash_object.hexdigest()


def test_login_returns_error_for_blank_credentials():
    """
    Test that login rejects blank usernames and passwords.
    """
    response = user_service.UserService().login("", "")

    assert response.user is None
    assert response.error_message == "Incorrect username or password"


def test_login_returns_reset_required_error(monkeypatch):
    """
    Test that login rejects users who must reset their password first.
    """
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {
            "Password": "hash",
            "RequireResetPassword": 1,
            "IsActive": 1,
        },
    )

    response = user_service.UserService().login("ada@example.com", "secret")

    assert response.user is None
    assert "Password reset required" in response.error_message


def test_login_returns_authenticated_user_for_valid_password(monkeypatch):
    """
    Test that login authenticates and loads the user when the password matches.
    """
    user = create_user()
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {
            "Password": build_password_hash("secret"),
            "RequireResetPassword": 0,
            "IsActive": 1,
        },
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )

    response = user_service.UserService().login("ada@example.com", "secret")

    assert response.error_message is None
    assert response.user is user
    assert response.user.is_authenticated is True


def test_login_returns_error_for_invalid_password(monkeypatch):
    """
    Test that login returns an error when the password does not match.
    """
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {
            "Password": build_password_hash("secret"),
            "RequireResetPassword": 0,
            "IsActive": 1,
        },
    )

    response = user_service.UserService().login("ada@example.com", "wrong")

    assert response.user is None
    assert response.error_message == "Incorrect username or password"


def test_login_returns_error_for_inactive_users(monkeypatch):
    """
    Test that login rejects inactive users.
    """
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {
            "Password": build_password_hash("secret"),
            "RequireResetPassword": 0,
            "IsActive": 0,
        },
    )

    response = user_service.UserService().login("ada@example.com", "secret")

    assert response.user is None
    assert response.error_message == "Incorrect username or password"


def test_login_returns_error_when_user_is_missing(monkeypatch):
    """
    Test that login returns a generic error when the username is not found.
    """
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: None)

    response = user_service.UserService().login("ada@example.com", "secret")

    assert response.user is None
    assert response.error_message == "Incorrect username or password"


def test_login_returns_error_when_lookup_raises(monkeypatch):
    """
    Test that login returns the fallback error when an exception is raised.
    """
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: (_ for _ in ()).throw(RuntimeError("db failed")),
    )

    response = user_service.UserService().login("ada@example.com", "secret")

    assert response.user is None
    assert response.error_message == "Error occurred during login"


def test_register_user_returns_validation_error_for_blank_first_name(monkeypatch):
    """
    Test that register_user rejects blank first names.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_username",
        lambda self, username: None,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_password",
        lambda self, password, confirm_password: None,
    )

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "",
        "Lovelace",
    )

    assert response.user is None
    assert response.error_message == "First name cannot be blank"


def test_register_user_returns_username_validation_error(monkeypatch):
    """
    Test that register_user returns username validation failures directly.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_username",
        lambda self, username: "Username must be a valid email address",
    )

    response = user_service.UserService().register_user(
        "bad-email",
        "secret1",
        "secret1",
        "Ada",
        "Lovelace",
    )

    assert response.user is None
    assert response.error_message == "Username must be a valid email address"


def test_register_user_returns_password_validation_error(monkeypatch):
    """
    Test that register_user returns password validation failures directly.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_username",
        lambda self, username: None,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_password",
        lambda self, password, confirm_password: "Passwords do not match",
    )

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret2",
        "Ada",
        "Lovelace",
    )

    assert response.user is None
    assert response.error_message == "Passwords do not match"


def test_register_user_returns_validation_error_for_blank_last_name(monkeypatch):
    """
    Test that register_user rejects blank last names.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_username",
        lambda self, username: None,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__validate_password",
        lambda self, password, confirm_password: None,
    )

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "Ada",
        "",
    )

    assert response.user is None
    assert response.error_message == "Last name cannot be blank"


def test_register_user_inserts_user_and_optional_seller(monkeypatch):
    """
    Test that register_user inserts the user and the optional seller assignment.
    """
    insert_calls = []
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        if "INSERT INTO Users" in sql:
            return 12
        return 33

    monkeypatch.setattr(user_service, "db_insert", fake_db_insert)

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "Ada",
        "Lovelace",
        seller_id=101,
    )

    assert response.error_message is None
    assert "INSERT INTO Users" in insert_calls[0][0]
    assert insert_calls[0][1]["username"] == "ada@example.com"
    assert insert_calls[1][1] == {"userId": 12, "sellerId": 101}


def test_register_user_succeeds_without_assigning_a_seller(monkeypatch):
    """
    Test that register_user succeeds when no seller assignment is requested.
    """
    insert_calls = []
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 12,
    )

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "Ada",
        "Lovelace",
        seller_id=0,
    )

    assert response.user is None
    assert response.error_message is None
    assert len(insert_calls) == 1


def test_register_user_returns_error_when_user_insert_fails(monkeypatch):
    """
    Test that register_user returns an error when the user insert fails.
    """
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(user_service, "db_insert", lambda sql, data: 0)

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "Ada",
        "Lovelace",
    )

    assert response.user is None
    assert "Error occurred during user registration" in response.error_message


def test_register_user_returns_error_when_seller_insert_fails(monkeypatch):
    """
    Test that register_user returns an error when the seller assignment insert fails.
    """
    insert_results = iter([12, 0])
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: next(insert_results),
    )

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "Ada",
        "Lovelace",
        seller_id=101,
    )

    assert response.user is None
    assert "Error occurred during user registration" in response.error_message


def test_register_user_returns_error_when_insert_raises(monkeypatch):
    """
    Test that register_user returns the fallback error when inserts raise exceptions.
    """
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: (_ for _ in ()).throw(RuntimeError("insert failed")),
    )

    response = user_service.UserService().register_user(
        "ada@example.com",
        "secret1",
        "secret1",
        "Ada",
        "Lovelace",
    )

    assert response.user is None
    assert "Error occurred during user registration" in response.error_message


def test_send_password_reset_email_rejects_blank_usernames():
    """
    Test that send_password_reset_email rejects blank usernames.
    """
    response = user_service.UserService().send_password_reset_email("")

    assert response.user is None
    assert response.error_message == "Username cannot be blank"


def test_send_password_reset_email_returns_user_not_found(monkeypatch):
    """
    Test that send_password_reset_email returns an error when the user does not exist.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: None,
    )

    response = user_service.UserService().send_password_reset_email("ada@example.com")

    assert response.user is None
    assert response.error_message == "User not found"


def test_send_password_reset_email_returns_error_when_email_send_fails(monkeypatch):
    """
    Test that send_password_reset_email returns an error when email delivery fails.
    """
    FakeMessagingService.instances = []
    FakeMessagingService.result_to_return = SendEmailResult(False, "smtp failed")
    user = create_user()
    monkeypatch.setattr(user_service, "MessagingService", FakeMessagingService)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__generate_password_code",
        lambda self, username: 123456,
    )

    response = user_service.UserService().send_password_reset_email("ada@example.com")

    assert response.user is None
    assert response.error_message == "Error occurred during password reset: smtp failed"
    assert FakeMessagingService.instances[0].calls[0][0] == "ada@example.com"


def test_send_password_reset_email_returns_error_when_code_generation_fails(
    monkeypatch,
):
    """
    Test that send_password_reset_email returns an error when no reset code is generated.
    """
    user = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__generate_password_code",
        lambda self, username: 0,
    )

    response = user_service.UserService().send_password_reset_email("ada@example.com")

    assert response.user is None
    assert response.error_message == "Error occurred during password reset"


def test_send_password_reset_email_returns_user_when_email_send_succeeds(monkeypatch):
    """
    Test that send_password_reset_email returns the user when email delivery succeeds.
    """
    FakeMessagingService.instances = []
    FakeMessagingService.result_to_return = SendEmailResult(True, None)
    user = create_user()
    monkeypatch.setattr(user_service, "MessagingService", FakeMessagingService)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__generate_password_code",
        lambda self, username: 123456,
    )

    response = user_service.UserService().send_password_reset_email("ada@example.com")

    assert response.user is user
    assert response.error_message is None


def test_send_password_reset_email_returns_error_when_lookup_raises(monkeypatch):
    """
    Test that send_password_reset_email returns the fallback error when lookups raise.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: (
            _ for _ in ()
        ).throw(RuntimeError("lookup failed")),
    )

    response = user_service.UserService().send_password_reset_email("ada@example.com")

    assert response.user is None
    assert response.error_message == "Error occurred during password reset"


def test_validate_password_reset_code_rejects_blank_usernames():
    """
    Test that validate_password_reset_code rejects blank usernames.
    """
    response = user_service.UserService().validate_password_reset_code("", 123456)

    assert response.user is None
    assert response.error_message == "Username cannot be blank"


def test_validate_password_reset_code_returns_user_not_found(monkeypatch):
    """
    Test that validate_password_reset_code returns a user-not-found error for missing users.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: None,
    )

    response = user_service.UserService().validate_password_reset_code(
        "ada@example.com",
        123456,
    )

    assert response.user is None
    assert response.error_message == "User not found"


def test_validate_password_reset_code_returns_invalid_code(monkeypatch):
    """
    Test that validate_password_reset_code rejects unknown reset codes.
    """
    user = create_user(user_id=12)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})

    response = user_service.UserService().validate_password_reset_code(
        "ada@example.com",
        123456,
    )

    assert response.user is None
    assert response.error_message == "Invalid code"


def test_validate_password_reset_code_returns_user_for_valid_codes(monkeypatch):
    """
    Test that validate_password_reset_code returns the user when the code matches.
    """
    user = create_user(user_id=12)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {"ForgotPasswordTokenId": 1},
    )

    response = user_service.UserService().validate_password_reset_code(
        "ada@example.com",
        123456,
    )

    assert response.user is user
    assert response.error_message is None


def test_validate_password_reset_code_returns_error_when_lookup_raises(monkeypatch):
    """
    Test that validate_password_reset_code returns the fallback error when lookups raise.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False, return_password=False: create_user(),
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: (_ for _ in ()).throw(RuntimeError("db failed")),
    )

    response = user_service.UserService().validate_password_reset_code(
        "ada@example.com",
        123456,
    )

    assert response.user is None
    assert response.error_message == "Error occurred during password reset"


def test_reset_password_updates_password_when_code_is_valid(monkeypatch):
    """
    Test that reset_password expires tokens and updates the stored password.
    """
    update_calls = []
    expired_usernames = []
    user = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "validate_password_reset_code",
        lambda self, username, code: user_service.UserResponse(user, None),
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: expired_usernames.append(username),
    )
    monkeypatch.setattr(
        user_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    response = user_service.UserService().reset_password(
        "ada@example.com",
        123456,
        "secret1",
        "secret1",
    )

    assert response.user is user
    assert response.error_message is None
    assert expired_usernames == ["ada@example.com"]
    assert update_calls[0][1]["username"] == "ada@example.com"


def test_reset_password_returns_validation_errors_before_lookup():
    """
    Test that reset_password returns password validation errors before checking the code.
    """
    response = user_service.UserService().reset_password(
        "ada@example.com",
        123456,
        "short",
        "short",
    )

    assert response.user is None
    assert response.error_message == "Password must have at least 6 characters."


def test_reset_password_returns_existing_error_responses(monkeypatch):
    """
    Test that reset_password returns the reset-code response when it already has an error.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "validate_password_reset_code",
        lambda self, username, code: user_service.UserResponse(None, "Invalid code"),
    )

    response = user_service.UserService().reset_password(
        "ada@example.com",
        123456,
        "secret1",
        "secret1",
    )

    assert response.user is None
    assert response.error_message == "Invalid code"


def test_reset_password_returns_error_when_update_fails(monkeypatch):
    """
    Test that reset_password returns an error when the password update fails.
    """
    user = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "validate_password_reset_code",
        lambda self, username, code: user_service.UserResponse(user, None),
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: None,
    )
    monkeypatch.setattr(user_service, "db_update", lambda sql, data: False)

    response = user_service.UserService().reset_password(
        "ada@example.com",
        123456,
        "secret1",
        "secret1",
    )

    assert response.user is None
    assert response.error_message == "Error occurred during password reset"


def test_reset_password_secured_returns_validation_errors():
    """
    Test that reset_password_secured returns password validation errors directly.
    """
    response = user_service.UserService().reset_password_secured(
        "ada@example.com",
        "short",
        "short",
    )

    assert response.user is None
    assert response.error_message == "Password must have at least 6 characters."


def test_reset_password_secured_returns_error_when_update_fails(monkeypatch):
    """
    Test that reset_password_secured returns an error when the password update fails.
    """
    user = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: None,
    )
    monkeypatch.setattr(user_service, "db_update", lambda sql, data: False)

    response = user_service.UserService().reset_password_secured(
        "ada@example.com",
        "secret1",
        "secret1",
    )

    assert response.user is None
    assert response.error_message == "Error occurred during password reset"


def test_reset_password_secured_returns_user_when_update_succeeds(monkeypatch):
    """
    Test that reset_password_secured returns the user when the password update succeeds.
    """
    user = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: None,
    )
    monkeypatch.setattr(user_service, "db_update", lambda sql, data: True)

    response = user_service.UserService().reset_password_secured(
        "ada@example.com",
        "secret1",
        "secret1",
    )

    assert response.user is user
    assert response.error_message is None


def test_register_returns_existing_user_error(monkeypatch):
    """
    Test that register rejects usernames that already exist.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_user_name",
        lambda self, username, fetch_sellers=False: create_user(username=username),
    )

    response = user_service.UserService().register(
        "ada@example.com",
        "Ada",
        "Lovelace",
        101,
        "secret1",
        "secret1",
    )

    assert response.user is None
    assert (
        response.error_message
        == "There is already a user in the system with that email"
    )


def test_register_returns_error_when_user_insert_fails(monkeypatch):
    """
    Test that register stops and returns an error when user creation fails.
    """
    insert_calls = []
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_user_name",
        lambda self, username, fetch_sellers=False: None,
    )

    def fake_db_insert(sql, data):
        insert_calls.append((sql, data))
        return 0

    monkeypatch.setattr(user_service, "db_insert", fake_db_insert)

    response = user_service.UserService().register(
        "ada@example.com",
        "Ada",
        "Lovelace",
        101,
        "secret1",
        "secret1",
    )

    assert response.user is None
    assert response.error_message == "Error occurred while registering user"
    assert len(insert_calls) == 1


def test_register_returns_password_validation_errors():
    """
    Test that register returns password validation errors before doing lookups.
    """
    response = user_service.UserService().register(
        "ada@example.com",
        "Ada",
        "Lovelace",
        101,
        "short",
        "short",
    )

    assert response.user is None
    assert response.error_message == "Password must have at least 6 characters."


def test_register_returns_error_when_user_seller_insert_fails(monkeypatch):
    """
    Test that register returns an error when the seller assignment insert fails.
    """
    insert_results = iter([11, 0])
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_user_name",
        lambda self, username, fetch_sellers=False: None,
    )
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: next(insert_results),
    )

    response = user_service.UserService().register(
        "ada@example.com",
        "Ada",
        "Lovelace",
        101,
        "secret1",
        "secret1",
    )

    assert response.user is None
    assert (
        "Error occurred while updating sellers during registration"
        in response.error_message
    )


def test_register_returns_error_when_registration_email_fails(monkeypatch):
    """
    Test that register returns the email error when sending the registration email fails.
    """
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_user_name",
        lambda self, username, fetch_sellers=False: None,
    )
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: 11,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__send_registration_email",
        lambda self, username: SendEmailResult(False, "smtp failed"),
    )
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_id",
        lambda self, user_id, fetch_sellers=False: create_user(user_id=user_id),
    )

    response = user_service.UserService().register(
        "ada@example.com",
        "Ada",
        "Lovelace",
        101,
        "secret1",
        "secret1",
    )

    assert response.user is not None
    assert response.error_message == "smtp failed"


def test_register_returns_user_when_registration_succeeds(monkeypatch):
    """
    Test that register returns the created user when the flow succeeds.
    """
    created_user = create_user(user_id=11)
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_user_name",
        lambda self, username, fetch_sellers=False: None,
    )
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: 11,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__send_registration_email",
        lambda self, username: SendEmailResult(True, None),
    )
    monkeypatch.setattr(
        user_service.UserService,
        "get_user_by_id",
        lambda self, user_id, fetch_sellers=False: created_user,
    )

    response = user_service.UserService().register(
        "ada@example.com",
        "Ada",
        "Lovelace",
        101,
        "secret1",
        "secret1",
    )

    assert response.user is created_user
    assert response.error_message is None


def test_get_user_by_id_fetches_sellers_routes_and_permissions(monkeypatch):
    """
    Test that get_user_by_id loads sellers, routes, permissions, and category details.
    """
    FakeRoleService.instances = []
    FakeRoleService.permissions_by_user_seller_id = {1: [2, 3], 2: [4]}
    monkeypatch.setattr(user_service, "RoleService", FakeRoleService)

    def fake_db_query_one(sql, _data):
        if "FROM Users" in sql:
            return build_user_row(UserId=7)
        return {}

    def fake_db_query_all(sql, data):
        if "JOIN UserSeller on UserSeller.SellerId" in sql:
            return [
                build_user_seller_row(UserSellerId=1, SellerId=101, Name="Seller A"),
                build_user_seller_row(UserSellerId=2, SellerId=202, Name="Seller B"),
            ]
        if "FROM Pages" in sql:
            if data["seller_id"] == 101:
                return [{"Route": "seller-a"}]
            return [{"Route": "seller-b-1"}, {"Route": "seller-b-2"}]
        return []

    monkeypatch.setattr(user_service, "db_query_one", fake_db_query_one)
    monkeypatch.setattr(user_service, "db_query_all", fake_db_query_all)

    user = user_service.UserService().get_user_by_id(7, fetch_sellers=True)

    assert user is not None
    assert user.user_id == 7
    assert len(user.sellers) == 2
    assert user.category == "Multiple"
    assert user.sellers[0].routes == ["seller-a"]
    assert user.sellers[1].routes == ["seller-b-1", "seller-b-2"]
    assert user.sellers[0].permissions == [2, 3]
    assert user.sellers[1].permissions == [4]
    assert FakeRoleService.instances[0].calls == [1]
    assert FakeRoleService.instances[1].calls == [2]


def test_get_all_users_sets_categories_based_on_admin_and_sellers(monkeypatch):
    """
    Test that get_all_users assigns Admin, Multiple, and seller-name categories.
    """
    monkeypatch.setattr(
        user_service,
        "db_query_all",
        lambda sql: [
            build_user_row(UserId=1, IsAdmin=1, Username="admin@example.com"),
            build_user_row(UserId=2, Username="multi@example.com"),
            build_user_row(UserId=3, Username="single@example.com"),
        ],
    )

    def fake_get_user_sellers(_self, user_id, is_admin):
        if is_admin:
            return [create_user_seller(seller_name="Seller A")]
        if user_id == 2:
            return [
                create_user_seller(seller_name="Seller A"),
                create_user_seller(
                    user_seller_id=2, seller_id=202, seller_name="Seller B"
                ),
            ]
        return [create_user_seller(seller_name="Solo Seller")]

    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        fake_get_user_sellers,
    )

    users = user_service.UserService().get_all_users()

    assert [user.category for user in users] == ["Admin", "Multiple", "Solo Seller"]


def test_get_all_users_leaves_category_blank_when_there_are_no_sellers(monkeypatch):
    """
    Test that get_all_users leaves the category unset when a non-admin has no sellers.
    """
    monkeypatch.setattr(
        user_service,
        "db_query_all",
        lambda sql: [build_user_row(UserId=4, Username="none@example.com")],
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        lambda self, user_id, is_admin: [],
    )

    users = user_service.UserService().get_all_users()

    assert len(users) == 1
    assert users[0].category is None


def test_get_user_by_user_name_uses_username_lookup(monkeypatch):
    """
    Test that get_user_by_user_name forwards the username lookup to the database helper.
    """
    calls = []
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: calls.append(
            (user_id, username, fetch_sellers)
        )
        or create_user(username=username),
    )

    user = user_service.UserService().get_user_by_user_name(
        "ada@example.com",
        fetch_sellers=True,
    )

    assert user.username == "ada@example.com"
    assert calls == [(None, "ada@example.com", True)]


def test_update_user_updates_existing_user_and_clears_text_reset_without_mobile(
    monkeypatch,
):
    """
    Test that update_user updates existing users and disables text reset when mobile is blank.
    """
    update_calls = []
    assign_calls = []
    user_to_update = create_user()
    user_to_update.mobile = None
    user_to_update.send_text_reset = True
    user_to_update.sellers = [create_user_seller()]
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False, return_password=False: create_user(),
    )
    monkeypatch.setattr(
        user_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__assign_user_to_sellers",
        lambda self, user_id, is_admin, sellers: assign_calls.append(
            (user_id, is_admin, sellers)
        )
        or True,
    )

    success = user_service.UserService().update_user(user_to_update)

    assert success is True
    assert update_calls[0][1]["mobile"] is None
    assert update_calls[0][1]["sendTextReset"] == 0
    assert assign_calls == [(7, False, user_to_update.sellers)]


def test_update_user_replaces_existing_password_when_changed(monkeypatch):
    """
    Test that update_user writes a new password hash when the submitted password changes.
    """
    update_calls = []
    user_to_update = create_user()
    user_to_update.password = "secret2"
    existing_user = create_user()
    existing_user.password = build_password_hash("secret1")
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False, return_password=False: existing_user,
    )
    monkeypatch.setattr(
        user_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__assign_user_to_sellers",
        lambda self, user_id, is_admin, sellers: True,
    )

    success = user_service.UserService().update_user(user_to_update)

    assert success is True
    assert update_calls[0][1]["password"] == build_password_hash("secret2")


def test_update_user_returns_false_for_invalid_inputs():
    """
    Test that update_user returns False for missing users and missing user ids.
    """
    assert user_service.UserService().update_user(None) is False
    assert user_service.UserService().update_user(create_user(user_id=None)) is False


def test_update_user_returns_false_when_existing_user_is_missing(monkeypatch):
    """
    Test that update_user returns False when the existing user cannot be found.
    """
    user_to_update = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False, return_password=False: None,
    )

    success = user_service.UserService().update_user(user_to_update)

    assert success is False


def test_update_user_returns_false_when_existing_user_update_fails(monkeypatch):
    """
    Test that update_user returns False when the existing user update fails.
    """
    user_to_update = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False, return_password=False: create_user(),
    )
    monkeypatch.setattr(user_service, "db_update", lambda sql, data: False)

    success = user_service.UserService().update_user(user_to_update)

    assert success is False


def test_update_user_inserts_new_user_and_assigns_sellers(monkeypatch):
    """
    Test that update_user inserts new users and then assigns sellers.
    """
    insert_calls = []
    assign_calls = []
    user_to_update = create_user(user_id=0, username="new@example.com")
    user_to_update.password = "secret1"
    user_to_update.sellers = [create_user_seller()]
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 22,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__assign_user_to_sellers",
        lambda self, user_id, is_admin, sellers: assign_calls.append(
            (user_id, is_admin, sellers)
        )
        or True,
    )

    success = user_service.UserService().update_user(user_to_update)

    assert success is True
    assert "INSERT INTO Users" in insert_calls[0][0]
    assert insert_calls[0][1]["username"] == "new@example.com"
    assert assign_calls == [(22, False, user_to_update.sellers)]


def test_update_user_returns_false_when_new_user_insert_fails(monkeypatch):
    """
    Test that update_user returns False when a new user insert fails.
    """
    user_to_update = create_user(user_id=0, username="new@example.com")
    user_to_update.password = "secret1"
    monkeypatch.setattr(user_service, "db_insert", lambda sql, data: 0)

    success = user_service.UserService().update_user(user_to_update)

    assert success is False


def test_update_user_returns_false_when_seller_assignment_fails(monkeypatch):
    """
    Test that update_user returns False when seller assignment fails after a successful update.
    """
    user_to_update = create_user()
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False, return_password=False: create_user(),
    )
    monkeypatch.setattr(user_service, "db_update", lambda sql, data: True)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__assign_user_to_sellers",
        lambda self, user_id, is_admin, sellers: False,
    )

    success = user_service.UserService().update_user(user_to_update)

    assert success is False


def test_delete_user_deletes_user_sellers_activity_and_user(monkeypatch):
    """
    Test that delete_user deletes related rows before deleting the user record.
    """
    delete_calls = []
    monkeypatch.setattr(
        user_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    success = user_service.UserService().delete_user(7)

    assert success is True
    assert "DELETE FROM UserSeller" in delete_calls[0][0]
    assert "DELETE FROM UserActivity" in delete_calls[1][0]
    assert "DELETE FROM Users" in delete_calls[2][0]
    assert delete_calls[0][1] == {"userId": 7}


def test_delete_user_returns_false_when_delete_raises(monkeypatch):
    """
    Test that delete_user returns False when a delete raises an exception.
    """
    monkeypatch.setattr(
        user_service,
        "db_delete",
        lambda sql, data: (_ for _ in ()).throw(RuntimeError("delete failed")),
    )

    success = user_service.UserService().delete_user(7)

    assert success is False


def test_get_user_seller_by_event_id_returns_matching_seller(monkeypatch):
    """
    Test that get_user_seller_by_event_id returns the seller assigned to the event.
    """
    user = create_user()
    user.sellers = [
        create_user_seller(seller_id=101, seller_name="Seller A"),
        create_user_seller(user_seller_id=2, seller_id=202, seller_name="Seller B"),
    ]
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {"SellerId": 202},
    )

    seller = user_service.UserService().get_user_seller_by_event_id(7, 44)

    assert seller is not None
    assert seller.seller_id == 202
    assert seller.seller_name == "Seller B"


def test_get_user_seller_by_event_id_returns_none_without_event_sellers(monkeypatch):
    """
    Test that get_user_seller_by_event_id returns None when the event has no seller.
    """
    user = create_user()
    user.sellers = [create_user_seller(seller_id=101, seller_name="Seller A")]
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: {})

    seller = user_service.UserService().get_user_seller_by_event_id(7, 44)

    assert seller is None


def test_get_user_seller_by_event_id_returns_none_when_user_lacks_that_seller(
    monkeypatch,
):
    """
    Test that get_user_seller_by_event_id returns None when the user is not assigned to the event seller.
    """
    user = create_user()
    user.sellers = [create_user_seller(seller_id=101, seller_name="Seller A")]
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: user,
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: {"SellerId": 202},
    )

    seller = user_service.UserService().get_user_seller_by_event_id(7, 44)

    assert seller is None


def test_assign_user_to_sellers_returns_false_when_existing_user_is_missing(
    monkeypatch,
):
    """
    Test that assigning sellers returns False when the user cannot be loaded.
    """
    assign = getattr(user_service.UserService(), "_UserService__assign_user_to_sellers")
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: None,
    )

    success = assign(7, False, [])

    assert success is False


def test_assign_user_to_sellers_deletes_all_sellers_for_admins(monkeypatch):
    """
    Test that assigning sellers for admins clears all existing seller rows.
    """
    delete_calls = []
    assign = getattr(user_service.UserService(), "_UserService__assign_user_to_sellers")
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: create_user(
            user_id=user_id,
            is_admin=True,
        ),
    )
    monkeypatch.setattr(
        user_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )

    success = assign(7, True, [])

    assert success is True
    assert delete_calls[0][1] == {"userId": 7}


def test_assign_user_to_sellers_updates_deletes_and_inserts_for_non_admins(monkeypatch):
    """
    Test that assigning sellers updates roles, deletes removed sellers, and inserts new ones.
    """
    update_calls = []
    delete_calls = []
    insert_calls = []
    assign = getattr(user_service.UserService(), "_UserService__assign_user_to_sellers")
    existing_user = create_user()
    existing_user.sellers = [
        create_user_seller(user_seller_id=1, seller_id=101, role_id=2),
        create_user_seller(user_seller_id=2, seller_id=202, role_id=3),
    ]
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: existing_user,
    )
    monkeypatch.setattr(
        user_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        user_service,
        "db_delete",
        lambda sql, data: delete_calls.append((sql, data)) or True,
    )
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 55,
    )

    success = assign(
        7,
        False,
        [
            create_user_seller(user_seller_id=0, seller_id=101, role_id=4),
            create_user_seller(user_seller_id=0, seller_id=303, role_id=5),
            create_user_seller(user_seller_id=0, seller_id=0, role_id=6),
        ],
    )

    assert success is True
    assert update_calls[0][1]["roleId"] == 4
    assert delete_calls[0][1] == {"userSellerId": 2}
    assert insert_calls[0][1]["sellerId"] == 303


def test_assign_user_to_sellers_keeps_matching_roles_without_updates(monkeypatch):
    """
    Test that assigning sellers removes matched seller ids without updating equal roles.
    """
    update_calls = []
    assign = getattr(user_service.UserService(), "_UserService__assign_user_to_sellers")
    existing_user = create_user()
    existing_user.sellers = [
        create_user_seller(user_seller_id=1, seller_id=101, role_id=2)
    ]
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: existing_user,
    )
    monkeypatch.setattr(
        user_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    success = assign(
        7, False, [create_user_seller(user_seller_id=0, seller_id=101, role_id=2)]
    )

    assert success is True
    assert not update_calls


def test_assign_user_to_sellers_returns_false_when_insert_fails(monkeypatch):
    """
    Test that assigning sellers returns False when inserting a new seller fails.
    """
    assign = getattr(user_service.UserService(), "_UserService__assign_user_to_sellers")
    existing_user = create_user()
    existing_user.sellers = []
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: existing_user,
    )
    monkeypatch.setattr(user_service, "db_insert", lambda sql, data: 0)

    success = assign(7, False, [create_user_seller(user_seller_id=0, seller_id=303)])

    assert success is False


def test_assign_user_to_sellers_skips_missing_new_seller_lookups(monkeypatch):
    """
    Test that assigning sellers skips ids whose seller lookup returns None.
    """
    assign = getattr(user_service.UserService(), "_UserService__assign_user_to_sellers")
    existing_user = create_user()
    existing_user.sellers = []
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: existing_user,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_seller_from_list_by_id",
        lambda self, sellers, user_seller_id: None,
    )

    success = assign(7, False, [create_user_seller(user_seller_id=0, seller_id=303)])

    assert success is True


def test_get_user_seller_from_list_by_id_returns_matches_and_none():
    """
    Test that the seller-list lookup returns a match when present and None otherwise.
    """
    lookup = getattr(
        user_service.UserService(),
        "_UserService__get_user_seller_from_list_by_id",
    )
    sellers = [create_user_seller(seller_id=101), create_user_seller(seller_id=202)]

    found = lookup(sellers, 202)
    missing = lookup(sellers, 303)

    assert found.seller_id == 202
    assert missing is None


def test_expire_all_user_tokens_updates_all_rows(monkeypatch):
    """
    Test that expiring all user tokens issues the expected update.
    """
    update_calls = []
    expire = getattr(user_service.UserService(), "_UserService__expire_all_user_tokens")
    monkeypatch.setattr(
        user_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    expire("ada@example.com")

    assert "UPDATE ForgotPasswordToken SET IsExpired=1" in update_calls[0][0]
    assert update_calls[0][1] == {"username": "ada@example.com"}


def test_generate_password_code_handles_blank_and_missing_users(monkeypatch):
    """
    Test that generating password codes returns zero for blank usernames and missing users.
    """
    generate = getattr(
        user_service.UserService(), "_UserService__generate_password_code"
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: None,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: None,
    )

    assert generate("") == 0
    assert generate("ada@example.com") == 0


def test_generate_password_code_returns_zero_when_insert_fails(monkeypatch):
    """
    Test that generating password codes returns zero when the token insert fails.
    """
    generate = getattr(
        user_service.UserService(), "_UserService__generate_password_code"
    )
    monkeypatch.setattr(user_service, "datetime", FixedDateTime)
    monkeypatch.setattr(user_service.random, "randint", lambda start, end: 123456)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: None,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: create_user(),
    )
    monkeypatch.setattr(user_service, "db_insert", lambda sql, data: 0)

    code = generate("ada@example.com")

    assert code == 0


def test_generate_password_code_inserts_and_returns_the_generated_code(monkeypatch):
    """
    Test that generating password codes stores the token and returns the generated code.
    """
    insert_calls = []
    generate = getattr(
        user_service.UserService(), "_UserService__generate_password_code"
    )
    monkeypatch.setattr(user_service, "datetime", FixedDateTime)
    monkeypatch.setattr(user_service.random, "randint", lambda start, end: 123456)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__expire_all_user_tokens",
        lambda self, username: None,
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: create_user(),
    )
    monkeypatch.setattr(
        user_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 9,
    )

    code = generate("ada@example.com")

    assert code == 123456
    assert insert_calls[0][1]["userId"] == 7
    assert insert_calls[0][1]["code"] == 123456


def test_password_hash_and_verify_round_trip():
    """
    Test that password hashing and verification round-trip correctly.
    """
    service = user_service.UserService()
    password_hash = getattr(service, "_UserService__password_hash")("secret1")
    verify = getattr(service, "_UserService__password_verify")

    assert verify("secret1", password_hash) is True
    assert verify("wrong", password_hash) is False


def test_retrieve_user_from_database_handles_missing_inputs_and_rows(monkeypatch):
    """
    Test that retrieving a user returns None when no lookup criteria or row are provided.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(user_service, "db_query_one", lambda sql, data: None)

    assert retrieve() is None
    assert retrieve(user_id=7) is None


def test_retrieve_user_from_database_loads_username_based_users_and_seller_categories(
    monkeypatch,
):
    """
    Test that retrieving a user by username can load sellers and assign categories.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(
        user_service, "db_query_one", lambda sql, data: build_user_row()
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        lambda self, user_id, is_admin: [
            create_user_seller(seller_name="Seller A"),
            create_user_seller(user_seller_id=2, seller_id=202, seller_name="Seller B"),
        ],
    )

    user = retrieve(username="ada@example.com", fetch_sellers=True)

    assert user is not None
    assert user.username == "ada@example.com"
    assert user.category == "Multiple"


def test_retrieve_user_from_database_sets_single_seller_categories(monkeypatch):
    """
    Test that retrieving a user with one seller uses that seller name as the category.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(
        user_service, "db_query_one", lambda sql, data: build_user_row()
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        lambda self, user_id, is_admin: [create_user_seller(seller_name="Solo Seller")],
    )

    user = retrieve(user_id=7, fetch_sellers=True)

    assert user is not None
    assert user.category == "Solo Seller"


def test_retrieve_user_from_database_can_skip_seller_loading(monkeypatch):
    """
    Test that retrieving a user can map the row without fetching seller assignments.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(
        user_service, "db_query_one", lambda sql, data: build_user_row()
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        lambda self, user_id, is_admin: (_ for _ in ()).throw(
            AssertionError("seller lookup should not be called")
        ),
    )

    user = retrieve(user_id=7, fetch_sellers=False)

    assert user is not None
    assert not user.sellers
    assert user.category is None


def test_retrieve_user_from_database_can_return_password(monkeypatch):
    """
    Test that retrieving a user includes the password when requested.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: build_user_row(Password="  hashed-password  "),
    )

    user = retrieve(user_id=7, return_password=True)

    assert user is not None
    assert user.password == "hashed-password"


def test_retrieve_user_from_database_leaves_category_blank_when_no_sellers(
    monkeypatch,
):
    """
    Test that retrieving a user with no sellers leaves the category unset.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(
        user_service, "db_query_one", lambda sql, data: build_user_row()
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        lambda self, user_id, is_admin: [],
    )

    user = retrieve(user_id=7, fetch_sellers=True)

    assert user is not None
    assert user.category is None


def test_retrieve_user_from_database_sets_admin_categories(monkeypatch):
    """
    Test that retrieving an admin user sets the Admin category when sellers are fetched.
    """
    retrieve = getattr(
        user_service.UserService(), "_UserService__retrieve_user_from_database"
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: build_user_row(IsAdmin=1),
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_sellers",
        lambda self, user_id, is_admin: [create_user_seller(seller_name="Seller A")],
    )

    user = retrieve(user_id=7, fetch_sellers=True)

    assert user is not None
    assert user.category == "Admin"


def test_get_user_sellers_returns_empty_for_invalid_user_ids():
    """
    Test that getting user sellers returns an empty list for invalid user ids.
    """
    get_sellers = getattr(user_service.UserService(), "_UserService__get_user_sellers")

    sellers = get_sellers(0, False)

    assert not sellers


def test_get_user_sellers_loads_admin_sellers_without_permissions(monkeypatch):
    """
    Test that getting admin sellers skips permission loading.
    """
    FakeRoleService.instances = []
    get_sellers = getattr(user_service.UserService(), "_UserService__get_user_sellers")
    monkeypatch.setattr(user_service, "RoleService", FakeRoleService)
    monkeypatch.setattr(
        user_service,
        "db_query_all",
        lambda sql, data: [build_user_seller_row(UserSellerId=0, RoleId=1)],
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__get_user_seller_routes",
        lambda self, seller_id: ["route-a"],
    )

    sellers = get_sellers(7, True)

    assert len(sellers) == 1
    assert sellers[0].routes == ["route-a"]
    assert not sellers[0].permissions
    assert not FakeRoleService.instances


def test_get_user_seller_routes_returns_all_routes(monkeypatch):
    """
    Test that getting user seller routes returns the ordered route list.
    """
    get_routes = getattr(
        user_service.UserService(), "_UserService__get_user_seller_routes"
    )
    monkeypatch.setattr(
        user_service,
        "db_query_all",
        lambda sql, data: [{"Route": "alpha"}, {"Route": "beta"}],
    )

    routes = get_routes(101)

    assert routes == ["alpha", "beta"]


def test_validate_username_handles_blank_invalid_taken_and_available_values(
    monkeypatch,
):
    """
    Test that validating usernames covers blank, invalid, taken, and available cases.
    """
    validate = getattr(user_service.UserService(), "_UserService__validate_username")
    monkeypatch.setattr(
        user_service, "validate_email_address", lambda username: "@" in username
    )
    monkeypatch.setattr(
        user_service,
        "db_query_one",
        lambda sql, data: (
            {"UserId": 7} if data["username"] == "taken@example.com" else {}
        ),
    )

    assert validate("   ") == "Please enter a username"
    assert validate("bad-email") == "Username must be a valid email address"
    assert validate("taken@example.com") == "That username is already taken"
    assert validate("free@example.com") is None


def test_validate_password_handles_all_validation_paths():
    """
    Test that validating passwords covers blank, short, confirm, mismatch, and valid inputs.
    """
    validate = getattr(user_service.UserService(), "_UserService__validate_password")

    assert validate("", "") == "Please enter a password"
    assert validate("short", "short") == "Password must have at least 6 characters."
    assert validate("secret1", "") == "Please enter confirm password"
    assert validate("secret1", "secret2") == "Passwords do not match"
    assert validate("secret1", "secret1") is None


def test_send_registration_email_returns_error_for_missing_users(monkeypatch):
    """
    Test that sending registration emails returns an error when the user cannot be found.
    """
    send_registration_email = getattr(
        user_service.UserService(),
        "_UserService__send_registration_email",
    )
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: None,
    )

    result = send_registration_email("ada@example.com")

    assert result.success is False
    assert result.error == "Could not find new user in database"


def test_send_registration_email_sends_expected_email(monkeypatch):
    """
    Test that sending registration emails builds and sends the expected email body.
    """
    FakeMessagingService.instances = []
    FakeMessagingService.result_to_return = SendEmailResult(True, None)
    send_registration_email = getattr(
        user_service.UserService(),
        "_UserService__send_registration_email",
    )
    monkeypatch.setattr(user_service, "MessagingService", FakeMessagingService)
    monkeypatch.setattr(
        user_service.UserService,
        "_UserService__retrieve_user_from_database",
        lambda self, user_id=None, username=None, fetch_sellers=False: create_user(),
    )

    result = send_registration_email("ada@example.com")

    assert result.success is True
    assert FakeMessagingService.instances[0].calls[0][0] == "tj@nationalactsvip.com"
