from typing import Optional

from pydantic import BaseModel


class RateLimiterConfig(BaseModel):
    """Rate limiter configuration for http requests."""

    max_rate: float
    time_period: float

    @classmethod
    def create(
        cls, max_rate: float | None = None, time_period: float | None = None
    ) -> Optional["RateLimiterConfig"]:
        """
        Creates rate limiter configuration.

        All parameters are optional.
        If all the parameters is None, the function will return None.
        Otherwise, it will return a RateLimiterConfig object.

        Default values:
            - max_rate: 1.0
            - time_period: 1.0

        Args:
            max_rate: float
            time_period: float

        Returns:
            Optional["RateLimiterConfig"]:
        """
        if not max_rate and not time_period:
            return None

        return cls(max_rate=max_rate or 1.0, time_period=time_period or 1.0)
