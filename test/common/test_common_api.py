"""
Unit tests for common.common_api helpers.
"""

from flask import Flask

from common import common_api


class FakeUserService:
    """
    Test double for looking up users from JWT usernames.
    """

    user_to_return = None
    calls = []

    def __init__(self):
        pass

    def get_user_by_user_name(self, username):
        """
        Record the requested username and return the configured user.
        """
        FakeUserService.calls.append(username)
        return FakeUserService.user_to_return


def test_get_user_from_jwt_returns_none_without_authorization_header():
    """
    Test that get_user_from_jwt returns None when the auth header is missing.
    """
    flask_app = Flask(__name__)

    with flask_app.test_request_context("/"):
        user = common_api.get_user_from_jwt()

    assert user is None


def test_get_user_from_jwt_loads_user_from_jwt_subject(monkeypatch):
    """
    Test that get_user_from_jwt loads the user for the JWT subject when auth is present.
    """
    flask_app = Flask(__name__)
    FakeUserService.calls = []
    fake_user = type("FakeUser", (), {"is_admin": True})()
    FakeUserService.user_to_return = fake_user
    monkeypatch.setattr(common_api, "get_jwt", lambda: {"sub": "admin@example.com"})
    monkeypatch.setattr(common_api, "UserService", FakeUserService)

    with flask_app.test_request_context(
        "/",
        headers={"Authorization": "Bearer token"},
    ):
        user = common_api.get_user_from_jwt()

    assert user is fake_user
    assert FakeUserService.calls == ["admin@example.com"]


def test_get_user_from_jwt_returns_none_when_jwt_lookup_raises(monkeypatch):
    """
    Test that get_user_from_jwt returns None and logs when JWT parsing fails.
    """
    flask_app = Flask(__name__)
    errors = []
    monkeypatch.setattr(
        common_api,
        "get_jwt",
        lambda: (_ for _ in ()).throw(RuntimeError("bad jwt")),
    )
    monkeypatch.setattr(
        common_api.logger, "error", lambda message: errors.append(message)
    )

    with flask_app.test_request_context(
        "/",
        headers={"Authorization": "Bearer token"},
    ):
        user = common_api.get_user_from_jwt()

    assert user is None
    assert errors
    assert "bad jwt" in errors[0]


def test_is_admin_logged_in_returns_false_without_user(monkeypatch):
    """
    Test that is_admin_logged_in returns False when no user is resolved from JWT.
    """
    monkeypatch.setattr(common_api, "get_user_from_jwt", lambda: None)

    assert common_api.is_admin_logged_in() is False


def test_is_admin_logged_in_returns_true_for_admin_user(monkeypatch):
    """
    Test that is_admin_logged_in returns True when the resolved user is an admin.
    """
    fake_user = type("FakeUser", (), {"is_admin": True})()
    monkeypatch.setattr(common_api, "get_user_from_jwt", lambda: fake_user)

    assert common_api.is_admin_logged_in() is True


def test_is_admin_logged_in_returns_false_for_non_admin_user(monkeypatch):
    """
    Test that is_admin_logged_in returns False when the resolved user is not an admin.
    """
    fake_user = type("FakeUser", (), {"is_admin": False})()
    monkeypatch.setattr(common_api, "get_user_from_jwt", lambda: fake_user)

    assert common_api.is_admin_logged_in() is False
