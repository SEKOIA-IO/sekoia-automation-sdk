"""SyncHttpClient."""

from requests.adapters import HTTPAdapter, Retry
from requests.models import Response
from requests.sessions import Session
from requests_ratelimiter import LimiterSession

from sekoia_automation.http.http_client import AbstractHttpClient
from sekoia_automation.http.rate_limiter import RateLimiterConfig
from sekoia_automation.http.retry import RetryPolicy


class SyncHttpClient(AbstractHttpClient[Response]):
    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        rate_limiter_config: RateLimiterConfig | None = None,
    ):
        """
        Initialize SyncHttpClient.

        Args:
            retry_policy: RetryPolicy | None
            rate_limiter_config: RateLimiterConfig | None
        """
        super().__init__(retry_policy, rate_limiter_config)
        self._session: Session | None = None

    def _pure_session(self) -> Session:
        """
        Get pure session.

        Returns:
            Generator[Session, None, None]:
        """
        if self._session is None:
            self._session = Session()

        return self._session

    def session(self) -> Session | LimiterSession:
        if self._session is not None:
            return self._session

        retry_strategy = (
            Retry(
                total=self._retry_policy.max_retries,
                backoff_factor=self._retry_policy.backoff_factor,
                status_forcelist=self._retry_policy.status_forcelist,
            )
            if self._retry_policy
            else Retry(0)
        )

        self._session = Session()

        self._session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
        self._session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

        if self._rate_limiter_config is not None:
            rate_value = (
                self._rate_limiter_config.max_rate
                / self._rate_limiter_config.time_period
            )

            self._session = LimiterSession(
                per_second=int(rate_value),
                per_minute=int(rate_value * 60),
                per_hour=int(rate_value * 60 * 60),
                per_day=int(rate_value * 60 * 60 * 24),
                per_month=int(rate_value * 60 * 60 * 24 * 30),
            )

        return self._session
