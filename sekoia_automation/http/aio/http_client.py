"""AsyncHttpClient."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from aiohttp import ClientResponse, ClientResponseError, ClientSession
from aiohttp.web_response import Response
from aiolimiter import AsyncLimiter

from sekoia_automation.http.http_client import AbstractHttpClient
from sekoia_automation.http.rate_limiter import RateLimiterConfig
from sekoia_automation.http.retry import RetryPolicy


class AsyncHttpClient(AbstractHttpClient[Response]):
    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        rate_limiter_config: RateLimiterConfig | None = None,
    ):
        """
        Initialize AsyncHttpClient.

        Args:
            retry_policy: RetryPolicy | None
            rate_limiter_config: AsyncLimiter | None
        """
        super().__init__(retry_policy, rate_limiter_config)
        self._session: ClientSession | None = None

        self._rate_limiter: AsyncLimiter | None = None
        if rate_limiter_config:
            self._rate_limiter = AsyncLimiter(
                max_rate=rate_limiter_config.max_rate,
                time_period=rate_limiter_config.time_period,
            )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[ClientSession, None]:
        """
        Get properly configured session with retry and async limiter.

        Yields:
            AsyncGenerator[ClientSession, None]:
        """
        async with ClientSession() as self._session:
            if self._rate_limiter:
                async with self._rate_limiter:
                    yield self._session
            else:
                yield self._session

    @asynccontextmanager
    async def get(
        self, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Get callable.

        Args:
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        async with self.request_retry("GET", url, *args, **kwargs) as result:
            yield result

    @asynccontextmanager
    async def post(
        self, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Post callable.

        Args:
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        async with self.request_retry("POST", url, *args, **kwargs) as result:
            yield result

    @asynccontextmanager
    async def put(
        self, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Put callable.

        Args:
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        async with self.request_retry("PUT", url, *args, **kwargs) as response:
            yield response

    @asynccontextmanager
    async def delete(
        self, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Delete callable.

        Args:
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        async with self.request_retry("DELETE", url, *args, **kwargs) as response:
            yield response

    @asynccontextmanager
    async def patch(
        self, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Patch callable.

        Args:
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        async with self.request_retry("PATCH", url, *args, **kwargs) as response:
            yield response

    @asynccontextmanager
    async def head(
        self, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Head callable.

        Args:
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        async with self.request_retry("HEAD", url, *args, **kwargs) as response:
            yield response

    @asynccontextmanager
    async def request_retry(
        self, method: str, url: str, *args: Any, **kwargs: Any | None
    ) -> AsyncGenerator[ClientResponse, None]:
        """
        Request callable.

        Args:
            method: str
            url: str
            args: Any
            kwargs: Optional[Any]

        Returns:
            ClientResponse:
        """
        attempts = 1
        backoff_factor = 0.1
        if self._retry_policy is not None and self._retry_policy.max_retries > 0:
            attempts = self._retry_policy.max_retries
            backoff_factor = self._retry_policy.backoff_factor

        for attempt in range(attempts):
            try:
                async with self.session() as session:
                    async with session.request(
                        method, url, *args, **kwargs
                    ) as response:
                        if (
                            self._retry_policy is not None
                            and response.status in self._retry_policy.status_forcelist
                            and attempt < self._retry_policy.max_retries - 1
                        ):
                            message = f"Status {response.status} is in forcelist"
                            raise ClientResponseError(
                                response.request_info,
                                response.history,
                                status=response.status,
                                message=message,
                            )

                        yield response

                        break
            except ClientResponseError:
                await asyncio.sleep(backoff_factor * (2**attempt))
