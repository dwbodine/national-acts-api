"""
Route tests for user and ticket-orders APIs.
"""

from types import SimpleNamespace

import pytest

from api import ticket_orders_api, user_api
from common.models.user import User, UserResponse


def create_user(user_id=7, username="ada@example.com", is_admin=False):
    """
    Create a user object for API route tests.
    """
    user = User()
    user.user_id = user_id
    user.username = username
    user.first_name = "Ada"
    user.last_name = "Lovelace"
    user.is_admin = is_admin
    user.is_authenticated = True
    user.sellers = []
    return user


def build_service(**methods):
    """
    Create a simple service object for route tests.
    """
    return lambda: SimpleNamespace(**methods)


def test_user_login_requires_api_key(client):
    """
    Return 401 when the login route is missing the user API key.
    """
    response = client.post("/user/login", json={})

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_user_login_returns_authenticated_user(
    monkeypatch, client, parse_json_response
):
    """
    Return the authenticated user with an access token after successful login.
    """
    user = create_user()

    class FakeUserService:
        """
        Fake user service for login requests.
        """

        def login(self, username, password):
            """
            Return a successful login response for the posted credentials.
            """
            assert username == "ada@example.com"
            assert password == "secret1"
            return UserResponse(user, None)

    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(user_api, "UserService", FakeUserService)

    response = client.post(
        "/user/login",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com", "password": "secret1"},
    )

    body = parse_json_response(response)

    assert response.status_code == 200
    assert body["userId"] == 7
    assert body["username"] == "ada@example.com"
    assert body["isAuthenticated"] is True
    assert body["token"]


def test_user_log_activity_uses_jwt_user(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Use the authenticated JWT user when logging activity.
    """
    captured = {}

    class FakeUserActivityService:
        """
        Fake activity service for user activity logs.
        """

        def log_user_activity(self, user_id, activity_type, activity_data):
            """
            Record the logged-in user's activity event.
            """
            captured["args"] = (user_id, activity_type, activity_data)
            return True

    monkeypatch.setattr(user_api, "get_user_from_jwt", lambda: create_user(user_id=12))
    monkeypatch.setattr(
        user_api,
        "UserActivityService",
        FakeUserActivityService,
    )

    response = client.post(
        "/user/logUserActivity",
        headers=auth_headers(role="user", user_id=12),
        json={"activityType": 4, "activityData": "Viewed event"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is True
    assert captured["args"] == (12, 4, "Viewed event")


def test_user_get_user_seller_from_event_id_returns_service_result(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return the service result for a user-seller lookup by event id.
    """

    class FakeUserService:
        """
        Fake user service for event-based seller lookups.
        """

        def get_user_seller_by_event_id(self, user_id, event_id):
            """
            Return a fake seller mapping for the given event.
            """
            assert (user_id, event_id) == (7, 44)
            return {"sellerId": 101}

    monkeypatch.setattr(user_api, "UserService", FakeUserService)

    response = client.get(
        "/user/getUserSellerFromEventId/7/44",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"sellerId": 101}


def test_user_register_requires_required_fields(monkeypatch, client):
    """
    Return 400 when the registration route is missing required data.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")

    response = client.post(
        "/user/register",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


def test_user_profile_returns_loaded_user(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return the requested user profile for authenticated callers.
    """

    class FakeUserService:
        """
        Fake user service for profile lookups.
        """

        def get_user_by_id(self, user_id, fetch_sellers):
            """
            Return a fake user profile.
            """
            assert (user_id, fetch_sellers) == (7, True)
            return create_user(user_id=7)

    monkeypatch.setattr(user_api, "UserService", FakeUserService)

    response = client.get("/user/profile/7", headers=auth_headers(role="user"))

    assert response.status_code == 200
    assert parse_json_response(response)["userId"] == 7


def test_user_reset_password_secured_returns_service_response(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Forward secured password reset requests to the user service.
    """

    class FakeUserService:
        """
        Fake user service for secured password resets.
        """

        def reset_password_secured(self, username, password, confirm_password):
            """
            Record a secured password reset request.
            """
            assert (username, password, confirm_password) == (
                "ada@example.com",
                "secret1",
                "secret1",
            )
            return UserResponse(create_user(), None)

    monkeypatch.setattr(user_api, "UserService", FakeUserService)

    response = client.post(
        "/user/resetPasswordSecured",
        headers=auth_headers(role="user"),
        json={
            "username": "ada@example.com",
            "password": "secret1",
            "confirmPassword": "secret1",
        },
    )

    assert response.status_code == 200
    assert parse_json_response(response)["user"]["userId"] == 7


def test_user_get_sellers_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Return user sellers when the caller provides the user API key.
    """

    class FakeSellerService:
        """
        Fake seller service for user-seller lists.
        """

        def get_user_sellers(self, user_id):
            """
            Return fake sellers for the requested user.
            """
            assert user_id == 7
            return [{"sellerId": 101}]

    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(user_api, "SellerService", FakeSellerService)

    response = client.get(
        "/user/sellers/7",
        headers={"x-api-key": "user-key"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == [{"sellerId": 101}]


def test_user_send_password_reset_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Return the password-reset service response for valid requests.
    """

    class FakeUserService:
        """
        Fake user service for password reset emails.
        """

        def send_password_reset_email(self, username):
            """
            Record a password-reset email request.
            """
            assert username == "ada@example.com"
            return {"success": True}

    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(user_api, "UserService", FakeUserService)

    response = client.post(
        "/user/sendPasswordReset",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"success": True}


def test_user_validate_reset_code_returns_service_result(
    monkeypatch, client, parse_json_response
):
    """
    Return the reset-code validation result from the user service.
    """

    class FakeUserService:
        """
        Fake user service for reset-code validation.
        """

        def validate_password_reset_code(self, username, code):
            """
            Record a reset-code validation request.
            """
            assert (username, code) == ("ada@example.com", 123456)
            return {"valid": True}

    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(user_api, "UserService", FakeUserService)

    response = client.post(
        "/user/validateResetCode",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com", "code": 123456},
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"valid": True}


def test_ticket_orders_requires_admin(monkeypatch, client, auth_headers):
    """
    Return 401 when a non-admin user requests ticket orders.
    """
    monkeypatch.setattr(ticket_orders_api, "is_admin_logged_in", lambda: False)

    response = client.get("/ticket_orders", headers=auth_headers(role="user"))

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_ticket_orders_returns_country_data(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return ticket-order data from the admin service for admin users.
    """

    class FakeAdminService:
        """
        Fake admin service for ticket-order data.
        """

        def get_all_countries(self):
            """
            Return fake ticket-order data.
            """
            return [{"countryId": 1, "countryCode": "US"}]

    monkeypatch.setattr(ticket_orders_api, "is_admin_logged_in", lambda: True)
    monkeypatch.setattr(ticket_orders_api, "AdminService", FakeAdminService)

    response = client.get("/ticket_orders", headers=auth_headers())

    assert response.status_code == 200
    assert parse_json_response(response) == [{"countryId": 1, "countryCode": "US"}]


def test_user_get_user_seller_from_event_id_rejects_invalid_ids(client, auth_headers):
    """
    Return 400 when the user-seller lookup receives zero-valued ids.
    """
    response = client.get(
        "/user/getUserSellerFromEventId/0/44",
        headers=auth_headers(role="user"),
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


def test_user_log_activity_returns_false_without_valid_context(
    monkeypatch, client, auth_headers, parse_json_response
):
    """
    Return false when activity logging does not have a valid JWT user.
    """
    monkeypatch.setattr(user_api, "get_user_from_jwt", lambda: None)

    response = client.post(
        "/user/logUserActivity",
        headers=auth_headers(role="user"),
        json={"activityType": 4, "activityData": "Viewed event"},
    )

    assert response.status_code == 200
    assert parse_json_response(response) is False


def test_user_login_rejects_missing_credentials(monkeypatch, client):
    """
    Return 400 when the login route is missing the username or password.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")

    response = client.post(
        "/user/login",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


def test_user_login_returns_service_error_message(monkeypatch, client):
    """
    Return the user-service error message when login fails.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(
        user_api,
        "UserService",
        build_service(
            login=lambda username, password: UserResponse(None, "Account locked")
        ),
    )

    response = client.post(
        "/user/login",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com", "password": "secret1"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Account locked"}


def test_user_login_rejects_unauthenticated_user(monkeypatch, client):
    """
    Return 401 when the login response does not contain an authenticated user.
    """
    user = create_user()
    user.is_authenticated = False
    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(
        user_api,
        "UserService",
        build_service(login=lambda username, password: UserResponse(user, None)),
    )

    response = client.post(
        "/user/login",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com", "password": "secret1"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Invalid username or password"}


def test_user_login_returns_internal_error_when_token_creation_fails(
    monkeypatch, client
):
    """
    Return 500 when JWT token creation does not produce an access token.
    """
    user = create_user()
    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(
        user_api,
        "UserService",
        build_service(login=lambda username, password: UserResponse(user, None)),
    )
    monkeypatch.setattr(user_api, "create_access_token", lambda **kwargs: None)

    response = client.post(
        "/user/login",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com", "password": "secret1"},
    )

    assert response.status_code == 500
    assert response.get_json() == {"msg": "Unable to create access token"}


def test_user_logout_returns_success_message(client):
    """
    Return the logout success response and clear JWT cookies.
    """
    response = client.post("/user/logout")

    assert response.status_code == 200
    assert response.get_json() == {"msg": "logout successful"}


def test_user_profile_rejects_invalid_user_id(client, auth_headers):
    """
    Return 400 when the profile route receives a non-positive user id.
    """
    response = client.get("/user/profile/0", headers=auth_headers(role="user"))

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad Request"}


def test_user_register_requires_api_key(client):
    """
    Return 401 when the registration route is missing the user API key.
    """
    response = client.post("/user/register", json={})

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_user_register_returns_service_response(
    monkeypatch, client, parse_json_response
):
    """
    Return the registration result from the user service for valid requests.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(
        user_api,
        "UserService",
        build_service(
            register=lambda username, first_name, last_name, seller_id, password, confirm_password, notes: {
                "registered": True,
                "sellerId": seller_id,
            }
        ),
    )

    response = client.post(
        "/user/register",
        headers={"x-api-key": "user-key"},
        json={
            "username": "ada@example.com",
            "firstName": "Ada",
            "lastName": "Lovelace",
            "sellerId": "12",
            "password": "secret1",
            "confirmPassword": "secret1",
            "notes": "Important client",
        },
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"registered": True, "sellerId": "12"}


def test_user_reset_password_requires_api_key(client):
    """
    Return 401 when the reset-password route is missing the user API key.
    """
    response = client.post("/user/resetPassword", json={})

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_user_reset_password_validates_required_fields(monkeypatch, client):
    """
    Return 400 when reset-password is missing required fields.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")

    response = client.post(
        "/user/resetPassword",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


def test_user_reset_password_returns_service_response(
    monkeypatch, client, parse_json_response
):
    """
    Return the reset-password service result for valid requests.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")
    monkeypatch.setattr(
        user_api,
        "UserService",
        build_service(
            reset_password=lambda username, code, password, confirm_password: {
                "reset": True,
                "code": code,
            }
        ),
    )

    response = client.post(
        "/user/resetPassword",
        headers={"x-api-key": "user-key"},
        json={
            "username": "ada@example.com",
            "password": "secret1",
            "confirmPassword": "secret1",
            "code": 123456,
        },
    )

    assert response.status_code == 200
    assert parse_json_response(response) == {"reset": True, "code": 123456}


def test_user_reset_password_secured_validates_required_fields(client, auth_headers):
    """
    Return 400 when the secured reset-password route is missing fields.
    """
    response = client.post(
        "/user/resetPasswordSecured",
        headers=auth_headers(role="user"),
        json={"username": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("/user/sellers/7", None),
        ("/user/sendPasswordReset", {"username": "ada@example.com"}),
        ("/user/validateResetCode", {"username": "ada@example.com", "code": 1}),
    ],
)
def test_user_api_key_routes_require_auth(client, route, payload):
    """
    Return 401 when user API-key routes are called without the correct key.
    """
    request_kwargs = {}
    if payload is not None:
        request_kwargs["json"] = payload

    method = client.get if payload is None else client.post
    response = method(route, **request_kwargs)

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Unauthorized"}


def test_user_get_sellers_rejects_invalid_user_id(monkeypatch, client):
    """
    Return 400 when the seller-list route receives a non-positive user id.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")

    response = client.get(
        "/user/sellers/0",
        headers={"x-api-key": "user-key"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


def test_user_send_password_reset_requires_username(monkeypatch, client):
    """
    Return 400 when the password-reset email route is missing the username.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")

    response = client.post(
        "/user/sendPasswordReset",
        headers={"x-api-key": "user-key"},
        json={},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}


def test_user_validate_reset_code_requires_valid_payload(monkeypatch, client):
    """
    Return 400 when reset-code validation is missing the username or code.
    """
    monkeypatch.setenv("USER_API_KEY", "user-key")

    response = client.post(
        "/user/validateResetCode",
        headers={"x-api-key": "user-key"},
        json={"username": "ada@example.com", "code": 0},
    )

    assert response.status_code == 400
    assert response.get_json() == {"msg": "Bad request"}
