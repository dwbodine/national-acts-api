"""
Unit tests for common.messaging_service helpers.
"""

from datetime import datetime

from common import messaging_service


class FixedDateTime(datetime):
    """
    Fixed datetime helper for token timestamp tests.
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


class FakeMail:
    """
    Test double for SendGrid Mail objects.
    """

    def __init__(self, from_email, to_emails, subject, html_content):
        self.from_email = from_email
        self.to_emails = to_emails
        self.subject = subject
        self.html_content = html_content
        self.cc_emails = []
        self.reply_to = None

    def add_cc(self, email):
        """
        Record cc recipients added to the message.
        """
        self.cc_emails.append(email)


class FakeSendGridClient:
    """
    Test double for the SendGrid API client.
    """

    instances = []

    def __init__(self, api_key):
        self.api_key = api_key
        self.sent_messages = []
        FakeSendGridClient.instances.append(self)

    def send(self, message):
        """
        Record sent messages.
        """
        self.sent_messages.append(message)


def test_generate_google_auth_token_returns_negative_one_for_blank_google_id():
    """
    Test that generate_google_auth_token rejects blank Google ids.
    """
    service = messaging_service.MessagingService()

    token_id = service.generate_google_auth_token("   ")

    assert token_id == -1


def test_generate_google_auth_token_inserts_token_with_two_minute_expiration(
    monkeypatch,
):
    """
    Test that generate_google_auth_token stores the token with a two-minute expiration.
    """
    calls = []
    monkeypatch.setattr(messaging_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        messaging_service,
        "db_insert",
        lambda sql, data: calls.append((sql, data)) or 42,
    )

    token_id = messaging_service.MessagingService().generate_google_auth_token("abc123")

    assert token_id == 42
    assert calls[0][1] == {
        "google_id": "abc123",
        "expiration": "2026-04-23 15:02:00",
    }


def test_generate_google_auth_token_returns_zero_when_insert_fails(monkeypatch):
    """
    Test that generate_google_auth_token returns zero when persistence fails.
    """
    monkeypatch.setattr(messaging_service, "datetime", FixedDateTime)
    monkeypatch.setattr(messaging_service, "db_insert", lambda sql, data: 0)

    token_id = messaging_service.MessagingService().generate_google_auth_token("abc123")

    assert token_id == 0


def test_validate_google_auth_token_rejects_invalid_inputs():
    """
    Test that validate_google_auth_token rejects missing Google ids and token ids.
    """
    service = messaging_service.MessagingService()

    assert service.validate_google_auth_token(None, 5) == -1
    assert service.validate_google_auth_token("abc123", 0) == -1


def test_validate_google_auth_token_redeems_valid_token(monkeypatch):
    """
    Test that validate_google_auth_token redeems unexpired tokens and returns valid.
    """
    query_calls = []
    update_calls = []
    monkeypatch.setattr(messaging_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        messaging_service,
        "db_query_one",
        lambda sql, data: query_calls.append((sql, data))
        or {"Expiration": "2026-04-23 12:05:00"},
    )
    monkeypatch.setattr(
        messaging_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    valid = messaging_service.MessagingService().validate_google_auth_token("abc123", 9)

    assert valid == 1
    assert query_calls[0][1] == {"google_id": "abc123", "token_id": 9}
    assert update_calls[0][1] == {"google_id": "abc123", "token_id": 9}


def test_validate_google_auth_token_returns_expired_code_for_old_tokens(monkeypatch):
    """
    Test that validate_google_auth_token returns -3 when the token is expired.
    """
    monkeypatch.setattr(messaging_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        messaging_service,
        "db_query_one",
        lambda sql, data: {"Expiration": "2026-04-23 11:55:00"},
    )

    valid = messaging_service.MessagingService().validate_google_auth_token("abc123", 9)

    assert valid == -3


def test_validate_google_auth_token_returns_zero_when_expiration_is_missing(
    monkeypatch,
):
    """
    Test that validate_google_auth_token returns zero when the expiration field is blank.
    """
    monkeypatch.setattr(
        messaging_service,
        "db_query_one",
        lambda sql, data: {"Expiration": None},
    )

    valid = messaging_service.MessagingService().validate_google_auth_token("abc123", 9)

    assert valid == 0


def test_validate_google_auth_token_returns_zero_when_row_is_missing(monkeypatch):
    """
    Test that validate_google_auth_token returns zero when the token row is not found.
    """
    monkeypatch.setattr(messaging_service, "db_query_one", lambda sql, data: None)

    valid = messaging_service.MessagingService().validate_google_auth_token("abc123", 9)

    assert valid == 0


def test_validate_google_auth_token_returns_zero_when_redeem_update_fails(monkeypatch):
    """
    Test that validate_google_auth_token returns zero when redeem persistence fails.
    """
    monkeypatch.setattr(messaging_service, "datetime", FixedDateTime)
    monkeypatch.setattr(
        messaging_service,
        "db_query_one",
        lambda sql, data: {"Expiration": "2026-04-23 12:05:00"},
    )
    monkeypatch.setattr(messaging_service, "db_update", lambda sql, data: False)

    valid = messaging_service.MessagingService().validate_google_auth_token("abc123", 9)

    assert valid == 0


def test_send_email_builds_message_with_defaults_cc_and_reply_to(monkeypatch):
    """
    Test that send_email builds the message with defaults, cc recipients, and reply-to.
    """
    FakeSendGridClient.instances = []
    monkeypatch.setenv("SENDGRID_API_KEY", "sendgrid-key")
    monkeypatch.setattr(messaging_service, "Mail", FakeMail)
    monkeypatch.setattr(
        messaging_service,
        "From",
        lambda email, name: ("from", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "To",
        lambda email, name: ("to", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "ReplyTo",
        lambda email, name: ("reply_to", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "SendGridAPIClient",
        FakeSendGridClient,
    )

    result = messaging_service.MessagingService().send_email(
        "user@example.com",
        "Hello",
        "<p>World</p>",
        to_name="Ada",
        cc_emails=["copy1@example.com", "copy2@example.com"],
        reply_to="support@example.com",
    )

    assert result.success is True
    assert result.error is None
    assert FakeSendGridClient.instances[0].api_key == "sendgrid-key"
    message = FakeSendGridClient.instances[0].sent_messages[0]
    assert message.from_email == (
        "from",
        "info@nationalactsvip.com",
        "National Acts VIP Customer Service",
    )
    assert message.to_emails == ("to", "user@example.com", "Ada")
    assert message.subject == "Hello"
    assert message.html_content == "<p>World</p>"
    assert message.cc_emails == ["copy1@example.com", "copy2@example.com"]
    assert message.reply_to == (
        "reply_to",
        "support@example.com",
        "support@example.com",
    )


def test_send_email_uses_plain_to_address_without_name_and_custom_reply_name(
    monkeypatch,
):
    """
    Test that send_email keeps the raw recipient and preserves a provided reply-to name.
    """
    FakeSendGridClient.instances = []
    monkeypatch.setenv("SENDGRID_API_KEY", "sendgrid-key")
    monkeypatch.setattr(messaging_service, "Mail", FakeMail)
    monkeypatch.setattr(
        messaging_service,
        "From",
        lambda email, name: ("from", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "ReplyTo",
        lambda email, name: ("reply_to", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "SendGridAPIClient",
        FakeSendGridClient,
    )

    result = messaging_service.MessagingService().send_email(
        "user@example.com",
        "Hello",
        "<p>World</p>",
        reply_to="reply@example.com",
        reply_to_name="Reply Name",
        from_address="custom@example.com",
        from_name="Custom Sender",
    )

    assert result.success is True
    message = FakeSendGridClient.instances[0].sent_messages[0]
    assert message.from_email == ("from", "custom@example.com", "Custom Sender")
    assert message.to_emails == "user@example.com"
    assert message.reply_to == ("reply_to", "reply@example.com", "Reply Name")


def test_send_email_leaves_reply_to_empty_when_none_is_provided(monkeypatch):
    """
    Test that send_email leaves reply-to unset when no reply address is provided.
    """
    FakeSendGridClient.instances = []
    monkeypatch.setenv("SENDGRID_API_KEY", "sendgrid-key")
    monkeypatch.setattr(messaging_service, "Mail", FakeMail)
    monkeypatch.setattr(
        messaging_service,
        "From",
        lambda email, name: ("from", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "SendGridAPIClient",
        FakeSendGridClient,
    )

    result = messaging_service.MessagingService().send_email(
        "user@example.com",
        "Hello",
        "<p>World</p>",
    )

    assert result.success is True
    message = FakeSendGridClient.instances[0].sent_messages[0]
    assert message.reply_to is None


def test_send_email_returns_error_result_when_sendgrid_raises(monkeypatch):
    """
    Test that send_email returns an error result when SendGrid raises an exception.
    """

    class RaisingSendGridClient:
        """
        Test double that raises when send is called.
        """

        def __init__(self, api_key):
            self.api_key = api_key

        def send(self, message):
            """
            Raise a test exception.
            """
            raise RuntimeError("boom")

    monkeypatch.setenv("SENDGRID_API_KEY", "sendgrid-key")
    monkeypatch.setattr(messaging_service, "Mail", FakeMail)
    monkeypatch.setattr(
        messaging_service,
        "From",
        lambda email, name: ("from", email, name),
    )
    monkeypatch.setattr(
        messaging_service,
        "SendGridAPIClient",
        RaisingSendGridClient,
    )

    result = messaging_service.MessagingService().send_email(
        "user@example.com",
        "Hello",
        "<p>World</p>",
        from_address="custom@example.com",
        from_name="Custom Sender",
        reply_to="reply@example.com",
        reply_to_name="Reply Name",
    )

    assert result.success is False
    assert "boom" in result.error
    assert "Traceback" in result.error
