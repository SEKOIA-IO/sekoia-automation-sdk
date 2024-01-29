"""Tests for `sekoia_automation.aio.helpers.http.token_refresher`."""

import asyncio
import time
from asyncio import Lock
from typing import ClassVar

import pytest
from aioresponses import aioresponses
from pydantic import BaseModel

from sekoia_automation.aio.helpers.http.token_refresher import (
    GenericTokenRefresher,
    RefreshedToken,
)


class CustomTokenResponse(BaseModel):
    """Test implementation of token response."""

    access_token: str
    signature: str
    random_field: str


class CustomTokenRefresher(GenericTokenRefresher):
    """
    Test implementation of GenericTokenRefresher.

    Contains some additional feature like default ttl and singleton impl.
    """

    _instances: ClassVar[dict[str, "CustomTokenRefresher"]] = {}
    _locks: ClassVar[dict[str, Lock]] = {}

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        auth_url: str,
        ttl: int = 60,
    ) -> None:
        """
        Initialize CustomTokenRefresher.

        Args:
            client_id: str
            client_secret: str
            auth_url: str
            ttl: int
        """
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url
        self.ttl = ttl

    @classmethod
    async def get_instance(
        cls,
        client_id: str,
        client_secret: str,
        auth_url: str,
    ) -> "CustomTokenRefresher":
        """
        Get instance of CustomTokenRefresher.

        Totally safe to use in async environment. Use lock to prevent multiple
        instances creation. Get instance from cls._instances if it already exists
        based on client_id, client_secret and auth_url.

        Args:
            client_id: str
            client_secret: str
            auth_url: str

        Returns:
            CustomTokenRefresher:
        """
        refresher_unique_key = str((client_id, client_secret, auth_url))
        if not cls._locks.get(refresher_unique_key):
            cls._locks[refresher_unique_key] = asyncio.Lock()

        if not cls._instances.get(refresher_unique_key):
            async with cls._locks[refresher_unique_key]:
                if not cls._instances.get(refresher_unique_key):
                    cls._instances[refresher_unique_key] = CustomTokenRefresher(
                        client_id,
                        client_secret,
                        auth_url,
                    )

        return cls._instances[refresher_unique_key]

    async def get_token(self) -> RefreshedToken[CustomTokenResponse]:
        """
        Get token from server test implementation.

        Returns:
            RefreshedToken[CustomTokenResponse]:
        """

        async with self.session().post(url=self.auth_url, json={}) as response:
            response_data = await response.json()
            ttl = self.ttl
            if (response_data.get("expires_in") or 0) > 0:
                ttl = int(response_data.get("expires_in"))

            return RefreshedToken(
                token=CustomTokenResponse(**response_data),
                created_at=int(time.time()),
                ttl=ttl,
            )


@pytest.mark.asyncio
async def test_token_refresher_1(session_faker):
    """
    Test token refresher with ttl from class.

    Args:
        session_faker: Faker
    """
    token_response = CustomTokenResponse(
        access_token=session_faker.word(),
        signature=session_faker.word(),
        random_field=session_faker.word(),
    )

    client_id = session_faker.word()
    client_secret = session_faker.word()
    auth_url = session_faker.uri()

    token_refresher = await CustomTokenRefresher.get_instance(
        client_id,
        client_secret,
        auth_url,
    )

    assert token_refresher == await CustomTokenRefresher.get_instance(
        client_id,
        client_secret,
        auth_url,
    )

    with aioresponses() as mocked_responses:
        mocked_responses.post(auth_url, payload=token_response.dict())
        await token_refresher._refresh_token()

        assert token_refresher._token is not None
        assert token_refresher._token.token.access_token == token_response.access_token
        assert token_refresher._token.token.signature == token_response.signature
        assert token_refresher._token.token.random_field == token_response.random_field
        assert token_refresher._token.ttl == 60

        await token_refresher._session.close()
        await token_refresher.close()


@pytest.mark.asyncio
async def test_token_refresher_2(session_faker):
    """
    Test token refresher with ttl from server response.

    Args:
        session_faker: Faker
    """
    token_response = {
        "access_token": session_faker.word(),
        "signature": session_faker.word(),
        "random_field": session_faker.word(),
        "expires_in": session_faker.pyint(),
    }

    client_id = session_faker.word()
    client_secret = session_faker.word()
    auth_url = session_faker.uri()

    with aioresponses() as mocked_responses:
        token_refresher = CustomTokenRefresher(
            client_id,
            client_secret,
            auth_url,
        )

        mocked_responses.post(auth_url, payload=token_response)
        await token_refresher._refresh_token()

        assert token_refresher._token is not None
        assert token_refresher._token.token.access_token == token_response.get(
            "access_token"
        )
        assert token_refresher._token.token.signature == token_response.get("signature")
        assert token_refresher._token.token.random_field == token_response.get(
            "random_field"
        )
        assert token_refresher._token.ttl == token_response.get("expires_in")

        await token_refresher._session.close()
        await token_refresher.close()


@pytest.mark.asyncio
async def test_token_refresher_with_token(session_faker):
    """
    Test token refresher with ttl from server response.

    Args:
        session_faker: Faker
    """
    token_response = {
        "access_token": session_faker.word(),
        "signature": session_faker.word(),
        "random_field": session_faker.word(),
        "expires_in": session_faker.pyint(),
    }

    client_id = session_faker.word()
    client_secret = session_faker.word()
    auth_url = session_faker.uri()

    with aioresponses() as mocked_responses:
        token_refresher = CustomTokenRefresher(
            client_id,
            client_secret,
            auth_url,
        )

        mocked_responses.post(auth_url, payload=token_response)
        async with token_refresher.with_access_token() as generated_token:
            assert generated_token.token.access_token == token_response.get(
                "access_token"
            )
            assert generated_token.token.signature == token_response.get("signature")
            assert generated_token.token.random_field == token_response.get(
                "random_field"
            )
            assert generated_token.ttl == token_response.get("expires_in")

        await token_refresher._session.close()
        await token_refresher.close()
