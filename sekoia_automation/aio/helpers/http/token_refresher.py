"""Auth token refresher wrapper with token schema."""

import asyncio
import time
from asyncio import Task
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Generic, TypeVar

from aiohttp import ClientSession
from pydantic import BaseModel
from pydantic.generics import GenericModel

HttpTokenT = TypeVar("HttpTokenT", bound=BaseModel)


class RefreshedToken(GenericModel, Generic[HttpTokenT]):
    """Model to work with auth token with additional info."""

    token: HttpTokenT
    created_at: int
    ttl: int

    def is_valid(self) -> bool:
        """
        Check if token is not expired yet and valid.

        Returns:
            bool:
        """
        return not self.is_expired()

    def is_expired(self) -> bool:
        """
        Check if token is expired.

        Returns:
            bool:
        """
        return self.created_at + self.ttl < (time.time() - 1)


RefreshedTokenT = TypeVar("RefreshedTokenT", bound=RefreshedToken)


class GenericTokenRefresher(Generic[RefreshedTokenT]):
    """
    Contains access token refresher logic.

    Example of usage:
    >>> # Define schema for token response from server
    >>> class HttpToken(BaseModel):
    >>>     access_token: str
    >>>     signature: str
    >>>
    >>> # Define TokenRefresher class with necessary logic
    >>> class CustomTokenRefresher(GenericTokenRefresher):
    >>>     def __init__(self, client_id: str, client_secret: str, auth_url: str):
    >>>         super().__init__()
    >>>         ...
    >>>     def get_token(self) -> RefreshedToken[HttpToken]:
    >>>         ...
    >>>
    >>> token_refresher = GenericTokenRefresher[RefreshedToken[HttpToken]]()
    >>>
    >>> async with token_refresher.with_access_token() as access_token:
    >>>     print(access_token)
    """

    _session: ClientSession | None = None

    def __init__(self):
        """Initialize GenericTokenRefresher."""

        self._token: RefreshedTokenT | None = None
        self._token_refresh_task: Task[None] | None = None

    def session(self) -> ClientSession:
        """
        Initialize client session.

        Singleton client session to work with token refresh logic.

        Returns:
            ClientSession:
        """
        if not self._session:
            self._session = ClientSession()

        return self._session

    async def get_token(self) -> RefreshedTokenT:
        """
        Get new token logic.

        Main method to get new token.

        Returns:
            RefreshedTokenT: instance of RefreshedToken
        """
        raise NotImplementedError(
            "You should implement `get_token` method in child class"
        )

    async def _refresh_token(self) -> None:
        """
        Refresh token logic.

        Also triggers token refresh task.
        """
        self._token = await self.get_token()
        await self._schedule_token_refresh(self._token.ttl)

    async def _schedule_token_refresh(self, expires_in: int) -> None:
        """
        Schedule token refresh.

        Args:
            expires_in: int
        """
        await self.close()

        async def _refresh() -> None:
            await asyncio.sleep(expires_in)
            await self._refresh_token()

        self._token_refresh_task = asyncio.create_task(_refresh())

    async def close(self) -> None:
        """
        Cancel token refresh task.
        """
        if self._token_refresh_task:
            self._token_refresh_task.cancel()

    @asynccontextmanager
    async def with_access_token(self) -> AsyncGenerator[RefreshedTokenT, None]:
        """
        Get access token.

        Yields:
            RefreshedTokenT:
        """
        if self._token is None:
            await self._refresh_token()

        if not self._token:
            raise ValueError("Token can not be initialized")

        yield self._token
