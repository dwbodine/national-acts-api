"""
Unit tests for common.exchange_rate_service helpers.
"""

from datetime import datetime

from common import exchange_rate_service
from common.models.exchange_rate import ExchangeRate


def create_exchange_rate():
    """
    Create an ExchangeRate instance for tests.
    """
    return ExchangeRate(7, "cad", "C$")


def test_get_current_rate_returns_default_when_api_key_is_missing(monkeypatch):
    """
    Test that the current-rate lookup falls back to 1.0 without a Stripe API key.
    """
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(exchange_rate_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(exchange_rate_service, "db_insert", lambda sql, data: 99)

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())

    result = service.get_exchange_rate_by_time(target_ts)

    assert result.usd_rate == 1.0


def test_get_current_rate_uses_stripe_response_and_rounds(monkeypatch):
    """
    Test that the current-rate lookup uses the Stripe response and rounds to 8 decimals.
    """
    target_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    calls = []
    monkeypatch.setenv("STRIPE_API_KEY", "stripe-key")
    monkeypatch.setattr(
        exchange_rate_service,
        "get_https_response",
        lambda host, url, api_key: calls.append((host, url, api_key))
        or [{"rates": {"usd": "1.234567891"}}],
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: {"USDRate": 1.0},
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_update",
        lambda sql, data: True,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())

    result = service.get_exchange_rate_by_time(target_ts, force_update=True)

    assert result.usd_rate == 1.23456789
    assert calls == [
        (
            "api.striperates.com",
            "/rates/cad/2026-04-23T12:00:00",
            "stripe-key",
        )
    ]


def test_get_current_rate_returns_default_when_stripe_response_is_empty(monkeypatch):
    """
    Test that the current-rate lookup falls back to 1.0 when Stripe returns no data.
    """
    target_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    monkeypatch.setenv("STRIPE_API_KEY", "stripe-key")
    monkeypatch.setattr(
        exchange_rate_service,
        "get_https_response",
        lambda host, url, api_key: [],
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: {"USDRate": 2.0},
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_update",
        lambda sql, data: True,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())

    result = service.get_exchange_rate_by_time(target_ts, force_update=True)

    assert result.usd_rate == 1.0


def test_get_exchange_rate_by_time_returns_one_when_exchange_rate_is_none():
    """
    Test that get_exchange_rate_by_time returns 1 when no exchange-rate model exists.
    """
    service = exchange_rate_service.ExchangeRateService(None)

    result = service.get_exchange_rate_by_time()

    assert result == 1


def test_get_exchange_rate_by_time_defaults_unix_time_to_now(monkeypatch):
    """
    Test that get_exchange_rate_by_time uses the current timestamp when unix_time is missing.
    """
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: {"USDRate": 1.44},
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_update",
        lambda sql, data: True,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())
    monkeypatch.setattr(
        service,
        "_ExchangeRateService__get_current_rate",
        lambda unix_time=None: 1.44,
    )

    result = service.get_exchange_rate_by_time()

    assert result.usd_rate == 1.44


def test_get_exchange_rate_by_time_uses_existing_historical_rate(monkeypatch):
    """
    Test that get_exchange_rate_by_time reuses a stored historical rate for past dates.
    """
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    calls = []
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: calls.append((sql, data)) or {"USDRate": 1.44},
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())

    result = service.get_exchange_rate_by_time(target_ts)

    assert result.usd_rate == 1.44
    assert calls[0][1] == {
        "exchangeRateId": 7,
        "midnightDate": "2026-04-20",
    }


def test_get_exchange_rate_by_time_inserts_missing_rate(monkeypatch):
    """
    Test that get_exchange_rate_by_time inserts a new history row when no rate exists.
    """
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    insert_calls = []
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(exchange_rate_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(
        exchange_rate_service,
        "db_insert",
        lambda sql, data: insert_calls.append((sql, data)) or 55,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())
    monkeypatch.setattr(
        service,
        "_ExchangeRateService__get_current_rate",
        lambda unix_time=None: 1.66,
    )

    result = service.get_exchange_rate_by_time(target_ts)

    assert result.usd_rate == 1.66
    assert insert_calls[0][1] == {
        "exchangeRateId": 7,
        "midnightDate": "2026-04-20",
        "currentRate": 1.66,
    }


def test_get_exchange_rate_by_time_updates_existing_rate_when_forced(monkeypatch):
    """
    Test that get_exchange_rate_by_time updates an existing history row when forced.
    """
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    update_calls = []
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: {"USDRate": 1.1},
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())
    monkeypatch.setattr(
        service,
        "_ExchangeRateService__get_current_rate",
        lambda unix_time=None: 1.25,
    )

    result = service.get_exchange_rate_by_time(target_ts, force_update=True)

    assert result.usd_rate == 1.25
    assert update_calls[0][1] == {
        "exchangeRateId": 7,
        "midnightDate": "2026-04-20",
        "currentRate": 1.25,
    }


def test_get_exchange_rate_by_time_keeps_existing_rate_when_current_rate_matches(
    monkeypatch,
):
    """
    Test that get_exchange_rate_by_time skips updates when the current rate is unchanged.
    """
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    update_calls = []
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: {"USDRate": 1.25},
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_update",
        lambda sql, data: update_calls.append((sql, data)) or True,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())
    monkeypatch.setattr(
        service,
        "_ExchangeRateService__get_current_rate",
        lambda unix_time=None: 1.25,
    )

    result = service.get_exchange_rate_by_time(target_ts, force_update=True)

    assert result.usd_rate == 1.25
    assert not update_calls


def test_get_exchange_rate_by_time_keeps_existing_rate_when_update_fails(monkeypatch):
    """
    Test that get_exchange_rate_by_time keeps the stored rate when an update fails.
    """
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(
        exchange_rate_service,
        "db_query_one",
        lambda sql, data: {"USDRate": 1.1},
    )
    monkeypatch.setattr(
        exchange_rate_service,
        "db_update",
        lambda sql, data: False,
    )

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())
    monkeypatch.setattr(
        service,
        "_ExchangeRateService__get_current_rate",
        lambda unix_time=None: 1.25,
    )

    result = service.get_exchange_rate_by_time(target_ts, force_update=True)

    assert result.usd_rate == 1.1


def test_get_exchange_rate_by_time_defaults_to_one_when_insert_does_not_persist(
    monkeypatch,
):
    """
    Test that get_exchange_rate_by_time falls back to 1 when a new insert does not persist.
    """
    target_ts = int(datetime(2026, 4, 20, 12, 0, 0).timestamp())
    current_ts = int(datetime(2026, 4, 23, 12, 0, 0).timestamp())
    monkeypatch.setattr(exchange_rate_service.time, "time", lambda: current_ts)
    monkeypatch.setattr(exchange_rate_service, "db_query_one", lambda sql, data: {})
    monkeypatch.setattr(exchange_rate_service, "db_insert", lambda sql, data: 0)

    service = exchange_rate_service.ExchangeRateService(create_exchange_rate())
    monkeypatch.setattr(
        service,
        "_ExchangeRateService__get_current_rate",
        lambda unix_time=None: 1.77,
    )

    result = service.get_exchange_rate_by_time(target_ts)

    assert result.usd_rate == 1
