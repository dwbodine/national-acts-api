"""
Tests for the Flask application entry point.
"""

import importlib
import json
import logging

import dotenv

import app as app_module


def build_json_response(payload):
    """
    Create a JSON Flask response for after-request tests.
    """
    return app_module.app.response_class(
        json.dumps(payload),
        mimetype="application/json",
    )


def test_app_is_configured():
    """
    Expose the Flask app instance from the application module.
    """
    assert app_module.app.name == "app"


def test_app_reload_uses_production_env_and_clears_existing_handlers(monkeypatch):
    """
    Load production dotenv settings and clear pre-existing root handlers on reload.
    """
    load_calls = []

    class FakeLogger:  # pylint: disable=too-few-public-methods,invalid-name
        """
        Fake logger object for module reload tests.
        """

        def __init__(self, handlers=None):
            """
            Seed the logger with optional handlers.
            """
            self.handlers = handlers or []

        def setLevel(self, _level):
            """
            Accept logger level changes during reload.
            """

        def hasHandlers(self):
            """
            Report whether the logger starts with handlers.
            """
            return bool(self.handlers)

        def addHandler(self, handler):
            """
            Record handlers added during module setup.
            """
            self.handlers.append(handler)

        def removeHandler(self, handler):
            """
            Remove handlers when pytest logging tears down the test.
            """
            if handler in self.handlers:
                self.handlers.remove(handler)

        def info(self, _message):
            """
            Accept info logs emitted during reload tests.
            """

        def error(self, _message):
            """
            Accept error logs emitted during reload tests.
            """

    root_logger = FakeLogger(handlers=["existing-handler"])
    gunicorn_logger = FakeLogger(handlers=["gunicorn-handler"])
    flask_logger = FakeLogger()

    def fake_get_logger(name=None):
        """
        Return deterministic fake loggers during module reload.
        """
        if name is None:
            return root_logger
        if name == "gunicorn.error":
            return gunicorn_logger
        if name == "flask.app":
            return flask_logger
        return FakeLogger()

    def record_load_dotenv(*args, **kwargs):
        """
        Record dotenv calls made during module reload.
        """
        load_calls.append((args, kwargs))

    with monkeypatch.context() as reload_patch:
        reload_patch.setenv("FLASK_ENV", "production")
        reload_patch.setattr(logging, "getLogger", fake_get_logger)
        reload_patch.setattr(dotenv, "load_dotenv", record_load_dotenv)

        importlib.reload(app_module)

        assert load_calls == [((), {"override": True})]
        assert len(root_logger.handlers) == 2
        assert "existing-handler" not in root_logger.handlers
        assert flask_logger.handlers == gunicorn_logger.handlers

    importlib.reload(app_module)


def test_app_reload_uses_development_env_without_existing_handlers(monkeypatch):
    """
    Load the development dotenv file when not running in production.
    """
    load_calls = []

    class FakeLogger:  # pylint: disable=too-few-public-methods,invalid-name
        """
        Fake logger object for development reload tests.
        """

        def __init__(self):
            """
            Start with no handlers so the clear branch is skipped.
            """
            self.handlers = []

        def setLevel(self, _level):
            """
            Accept logger level changes during reload.
            """

        def hasHandlers(self):
            """
            Report that the logger starts without handlers.
            """
            return False

        def addHandler(self, handler):
            """
            Record handlers added during module setup.
            """
            self.handlers.append(handler)

        def removeHandler(self, handler):
            """
            Remove handlers when pytest logging tears down the test.
            """
            if handler in self.handlers:
                self.handlers.remove(handler)

        def info(self, _message):
            """
            Accept info logs emitted during reload tests.
            """

        def error(self, _message):
            """
            Accept error logs emitted during reload tests.
            """

    root_logger = FakeLogger()
    gunicorn_logger = FakeLogger()
    flask_logger = FakeLogger()

    def fake_get_logger(name=None):
        """
        Return deterministic fake loggers during development reload.
        """
        if name is None:
            return root_logger
        if name == "gunicorn.error":
            return gunicorn_logger
        if name == "flask.app":
            return flask_logger
        return FakeLogger()

    def record_load_dotenv(*args, **kwargs):
        """
        Record dotenv calls made during development reload.
        """
        load_calls.append((args, kwargs))

    with monkeypatch.context() as reload_patch:
        reload_patch.setenv("FLASK_ENV", "development")
        reload_patch.setattr(logging, "getLogger", fake_get_logger)
        reload_patch.setattr(dotenv, "load_dotenv", record_load_dotenv)

        importlib.reload(app_module)

        assert len(load_calls) == 1
        assert load_calls[0][0][0].endswith(".env.development")
        assert load_calls[0][1] == {"override": True}
        assert len(root_logger.handlers) == 2

    importlib.reload(app_module)


def test_after_request_sets_cors_headers_and_cache_controls():
    """
    Add CORS and cache-control headers even when the request has no JWT.
    """
    response = build_json_response({"ok": True})

    with app_module.app.test_request_context("/"):
        result = app_module.after_request(response)

    assert result.headers["Access-Control-Allow-Origin"] == "*"
    assert result.headers["Access-Control-Allow-Credentials"] == "true"
    assert "Authorization" in result.headers["Access-Control-Allow-Headers"]
    assert (
        result.headers["Access-Control-Allow-Methods"] == "GET,PUT,POST,DELETE,OPTIONS"
    )
    assert result.cache_control.no_cache is True
    assert result.cache_control.no_store is True
    assert result.cache_control.must_revalidate is True


def test_after_request_refreshes_near_expiring_tokens(monkeypatch):
    """
    Attach a refreshed access token when the current JWT is near expiration.
    """
    monkeypatch.setattr(app_module, "get_jwt", lambda: {"exp": 0})
    monkeypatch.setattr(app_module, "get_jwt_identity", lambda: "ada@example.com")
    monkeypatch.setattr(
        app_module,
        "create_access_token",
        lambda identity: f"token-for-{identity}",
    )

    response = build_json_response({"userId": 7})

    with app_module.app.test_request_context(
        "/",
        headers={"Authorization": "Bearer abc"},
    ):
        result = app_module.after_request(response)

    assert result.get_json() == {
        "userId": 7,
        "access_token": "token-for-ada@example.com",
    }


def test_after_request_leaves_non_expiring_tokens_unchanged(monkeypatch):
    """
    Leave the response body unchanged when the JWT is not close to expiring.
    """
    monkeypatch.setattr(app_module, "get_jwt", lambda: {"exp": 9999999999})

    response = build_json_response({"userId": 7})

    with app_module.app.test_request_context(
        "/",
        headers={"Authorization": "Bearer abc"},
    ):
        result = app_module.after_request(response)

    assert result.get_json() == {"userId": 7}


def test_after_request_ignores_non_dict_json_payloads(monkeypatch):
    """
    Skip token injection when the response JSON payload is not a dictionary.
    """
    monkeypatch.setattr(app_module, "get_jwt", lambda: {"exp": 0})
    monkeypatch.setattr(app_module, "get_jwt_identity", lambda: "ada@example.com")
    monkeypatch.setattr(
        app_module,
        "create_access_token",
        lambda identity: f"token-for-{identity}",
    )

    response = build_json_response(["item"])

    with app_module.app.test_request_context(
        "/",
        headers={"Authorization": "Bearer abc"},
    ):
        result = app_module.after_request(response)

    assert result.get_json() == ["item"]


def test_after_request_logs_missing_jwt_errors(monkeypatch):
    """
    Log an informational message when JWT state is unavailable.
    """
    info_messages = []

    def record_info(message):
        """
        Record info messages emitted by the after-request hook.
        """
        info_messages.append(message)

    def raise_runtime_error():
        """
        Raise a runtime error to simulate missing JWT state.
        """
        raise RuntimeError("no jwt")

    monkeypatch.setattr(app_module.root_logger, "info", record_info)
    monkeypatch.setattr(app_module, "get_jwt", raise_runtime_error)

    response = build_json_response({"ok": True})

    with app_module.app.test_request_context(
        "/",
        headers={"Authorization": "Bearer abc"},
    ):
        result = app_module.after_request(response)

    assert result.get_json() == {"ok": True}
    assert info_messages == ["JWT not found"]


def test_after_request_logs_unexpected_errors(monkeypatch):
    """
    Log unexpected after-request failures without breaking the response.
    """
    error_messages = []

    def record_error(message):
        """
        Record error messages emitted by the after-request hook.
        """
        error_messages.append(message)

    def raise_value_error():
        """
        Raise an unexpected error during JWT handling.
        """
        raise ValueError("boom")

    monkeypatch.setattr(app_module.root_logger, "error", record_error)
    monkeypatch.setattr(app_module, "get_jwt", raise_value_error)

    response = build_json_response({"ok": True})

    with app_module.app.test_request_context(
        "/",
        headers={"Authorization": "Bearer abc"},
    ):
        result = app_module.after_request(response)

    assert result.get_json() == {"ok": True}
    assert len(error_messages) == 1
    assert "boom" in error_messages[0]


def test_health_returns_database_available_message(monkeypatch):
    """
    Return the healthy database message and close the open connection.
    """
    closed = {"value": False}

    class FakeConnection:
        """
        Fake database connection for health-check tests.
        """

        open = True

        def close(self):
            """
            Record that the health check closed the connection.
            """
            closed["value"] = True

    def get_connection():
        """
        Return an open fake connection for the health check.
        """
        return FakeConnection()

    monkeypatch.setattr(app_module, "db_get_connection", get_connection)

    with app_module.app.test_client() as client:
        response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Server is up and database available" in body
    assert closed["value"] is True


def test_health_returns_database_failed_message_for_closed_connection(monkeypatch):
    """
    Return the closed-connection health message when the database is not open.
    """

    class FakeConnection:
        """
        Fake closed database connection for health-check tests.
        """

        open = False

    def get_connection():
        """
        Return a closed fake connection for the health check.
        """
        return FakeConnection()

    monkeypatch.setattr(app_module, "db_get_connection", get_connection)

    with app_module.app.test_client() as client:
        response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Server is up but database connection failed" in body


def test_health_returns_database_not_available_when_connection_is_none(monkeypatch):
    """
    Return the unavailable-database message when no connection object is returned.
    """

    def get_connection():
        """
        Return no connection object for the health check.
        """
        return None

    monkeypatch.setattr(app_module, "db_get_connection", get_connection)

    with app_module.app.test_client() as client:
        response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Server is up but database not available" in body


def test_health_returns_exception_message_when_connection_raises(monkeypatch):
    """
    Return the formatted database exception message when connection setup fails.
    """

    def raise_connection_error():
        """
        Raise a database connection error for the health check.
        """
        raise RuntimeError("db down")

    monkeypatch.setattr(app_module, "db_get_connection", raise_connection_error)

    with app_module.app.test_client() as client:
        response = client.get("/")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Server is up" in body
    assert "database connection failed with message" in body
    assert "db down" in body
    assert "<br />" in body
