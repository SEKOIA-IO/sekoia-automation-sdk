from typing import Generic, TypeVar

from sekoia_automation.http.rate_limiter import RateLimiterConfig
from sekoia_automation.http.retry import RetryPolicy

TResult = TypeVar("TResult")


class AbstractHttpClient(Generic[TResult]):
    """
    Abstract class for http client.

    It should be used as a base class for all http clients.
    """

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        rate_limiter_config: RateLimiterConfig | None = None,
    ):
        """
        Initialize HttpClient.

        Args:
            retry_policy: RetryPolicy | None
            rate_limiter_config: RateLimiterConfig | None
        """
        self._retry_policy = retry_policy
        self._rate_limiter_config = rate_limiter_config

    @classmethod
    def create(
        cls,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        status_forcelist: list[int] | None = None,
        max_rate: float | None = None,
        time_period: float | None = None,
    ) -> "AbstractHttpClient":
        """
        Creates SyncHttpClient.

        Args:
            max_retries: int | None
            backoff_factor: float | None
            status_forcelist: list[int] | None
            max_rate: float | None
            time_period: float | None

        Returns:
            AbstractHttpClient:
        """
        return cls(
            retry_policy=RetryPolicy.create(
                max_retries, backoff_factor, status_forcelist
            ),
            rate_limiter_config=RateLimiterConfig.create(max_rate, time_period),
        )
