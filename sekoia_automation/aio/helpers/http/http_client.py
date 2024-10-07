"""HttpClient with ratelimiter."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aiohttp import ClientSession
from aiolimiter import AsyncLimiter


class HttpClient:
    """
    Http client with optional rate limiting.

    Example:
    >>> from sekoia_automation.http.aio.http_client import HttpClient
    >>> class CustomHttpClient(HttpClient):
    >>>     def __init__(self):
    >>>         super().__init__()
    >>>
    >>>     async def load_data(self, url: str) -> str:
    >>>         async with self.session() as session:
    >>>             async with session.get(url) as response:
    >>>                 return await response.text()
    >>>
    >>> client = CustomHttpClient()
    >>> # If rate limiter is set, it will be used
    >>> client.set_rate_limit(max_rate=10, time_period=60)
    >>> # or
    >>> client.set_rate_limiter(AsyncLimiter(max_rate=10, time_period=60))
    >>>
    >>> result = await client.load_data("https://example.com")
    """

    _session: ClientSession | None = None
    _rate_limiter: AsyncLimiter | None = None

    def __init__(
        self,
        max_rate: float | None = None,
        time_period: float | None = None,
        rate_limiter: AsyncLimiter | None = None,
    ):
        """
        Initialize HttpClient.

        Args:
            max_rate: float | None
            time_period: float | None
            rate_limiter: AsyncLimiter | None
        """
        if max_rate and time_period:
            self.set_rate_limit(max_rate, time_period)  # pragma: no cover

        if rate_limiter:
            self.set_rate_limiter(rate_limiter)  # pragma: no cover

    def set_rate_limit(self, max_rate: float, time_period: float = 60) -> None:
        """
        Set rate limiter.

        Args:
            max_rate: float
            time_period: float
        """
        self._rate_limiter = AsyncLimiter(max_rate=max_rate, time_period=time_period)

    def set_rate_limiter(self, rate_limiter: AsyncLimiter) -> None:  # pragma: no cover
        """
        Set rate limiter.

        Args:
            rate_limiter:
        """
        self._rate_limiter = rate_limiter

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[ClientSession, None]:
        """
        Get configured session with rate limiter.

        Yields:
            AsyncGenerator[ClientSession, None]:
        """
        async with ClientSession() as self._session:
            if self._rate_limiter:
                async with self._rate_limiter:
                    yield self._session
            else:
                yield self._session
