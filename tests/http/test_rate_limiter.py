"""Test rate limiter."""

from sekoia_automation.http.rate_limiter import RateLimiterConfig


def test_rate_limiter_config_create_with_values():
    """Test rate limiter configuration creation with values."""

    config = RateLimiterConfig.create(max_rate=5.0, time_period=10.0)
    assert config is not None
    assert config.max_rate == 5.0
    assert config.time_period == 10.0


def test_rate_limiter_config_create_with_defaults():
    """Test rate limiter configuration creation with default values."""

    config = RateLimiterConfig.create(max_rate=None, time_period=None)
    assert config is None


def test_rate_limiter_config_create_with_none_max_rate():
    """Test rate limiter configuration creation with None max rate."""

    config = RateLimiterConfig.create(max_rate=None, time_period=10.0)
    assert config is not None
    assert config.time_period == 10.0


def test_rate_limiter_config_create_with_none_time_period():
    """Test rate limiter configuration creation with None time period."""

    config = RateLimiterConfig.create(max_rate=5.0, time_period=None)
    assert config is not None
    assert config.max_rate == 5.0
