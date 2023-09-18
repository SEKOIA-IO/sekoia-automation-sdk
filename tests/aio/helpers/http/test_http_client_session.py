"""Tests for sekoia_automation.helpers.aio.http.http_client."""
import time

import pytest
from aioresponses import aioresponses
from pydantic import BaseModel

from sekoia_automation.aio.helpers.http.http_client import HttpClient
from sekoia_automation.aio.helpers.http.token_refresher import (
    GenericTokenRefresher,
    RefreshedToken,
)


class TokenResponse(BaseModel):
    """Test implementation of token response."""

    access_token: str


class TokenRefresher(GenericTokenRefresher):
    """Test implementation of GenericTokenRefresher."""

    async def get_token(self) -> RefreshedToken[TokenResponse]:
        """
        Test implementation of get_token.

        Returns:
            RefreshedToken[TokenResponse]:
        """
        async with self.session().post(url=self.auth_url, json={}) as response:
            response_data = await response.json()

            return RefreshedToken(
                token=TokenResponse(**response_data),
                created_at=int(time.time()),
                ttl=3600,
            )

    def __init__(self, client_id: str, client_secret: str, auth_url: str):
        """Initialize TokenRefresher."""
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url


class CustomHttpClient(HttpClient):
    """Complete test implementation of HttpClient with TokenRefresher."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        auth_url: str,
        base_url: str,
    ) -> None:
        """Initialize CustomHttpClient."""
        super().__init__()
        self.base_url = base_url
        self.token_refresher = TokenRefresher(
            client_id=client_id,
            client_secret=client_secret,
            auth_url=auth_url,
        )

    async def get_test_data(self, url: str) -> dict[str, str]:
        """
        Test method to get data from server with authentication.

        Args:
            url: str

        Returns:
            dict[str, str]:
        """
        async with self.token_refresher.with_access_token() as access_token:
            async with self.session() as session:
                async with session.get(
                    url=url,
                    headers={
                        "Authorization": f"Bearer {access_token.token.access_token}"
                    },
                ) as response:
                    return await response.json()


@pytest.fixture
def auth_url(session_faker):
    """
    Fixture to initialize auth_url.

    Returns:
        str:
    """
    return session_faker.uri()


@pytest.fixture
def base_url(session_faker):
    """
    Fixture to initialize base_url.

    Returns:
        str:
    """
    return session_faker.uri()


@pytest.fixture
def http_client(session_faker, auth_url, base_url):
    """
    Fixture to initialize HttpClient.

    Returns:
        CustomHttpClient:
    """
    return CustomHttpClient(
        client_id=session_faker.word(),
        client_secret=session_faker.word(),
        auth_url=auth_url,
        base_url=base_url,
    )


@pytest.mark.asyncio
async def test_http_client_get_data(session_faker, http_client, base_url, auth_url):
    """
    Test http_client get data.

    Args:
        session_faker: Faker
        http_client: CustomHttpClient
        base_url: str
        auth_url: str
    """
    token_response = TokenResponse(access_token=session_faker.word())

    get_test_data_response = {
        session_faker.word(): session_faker.word(),
        session_faker.word(): session_faker.word(),
    }

    with aioresponses() as mocked_responses:
        mocked_responses.post(auth_url, payload=token_response.dict())
        mocked_responses.get(f"{base_url}/test", payload=get_test_data_response)

        test_data = await http_client.get_test_data(url=f"{base_url}/test")

        assert test_data == get_test_data_response

        await http_client.token_refresher.close()
        await http_client.token_refresher._session.close()
        await http_client._session.close()


@pytest.mark.asyncio
async def test_http_client_get_data_async_limiter(
    session_faker,
    http_client,
    base_url,
    auth_url,
):
    """
    Test http_client get data with async_limiter.

    Args:
        session_faker: Faker
        http_client: CustomHttpClient
        base_url: str
        auth_url: str
    """
    token_response = TokenResponse(access_token=session_faker.word())

    # 1 request per 3 seconds
    http_client.set_rate_limit(1, 3)

    get_test_data_response = {
        session_faker.word(): session_faker.word(),
        session_faker.word(): session_faker.word(),
    }

    with aioresponses() as mocked_responses:
        start_query_time = time.time()
        mocked_responses.post(auth_url, payload=token_response.dict())
        mocked_responses.get(f"{base_url}/test", payload=get_test_data_response)
        await http_client.get_test_data(url=f"{base_url}/test")

        mocked_responses.post(auth_url, payload=token_response.dict())
        mocked_responses.get(f"{base_url}/test", payload=get_test_data_response)
        await http_client.get_test_data(url=f"{base_url}/test")

        end_query_time = time.time()

        assert int(end_query_time - start_query_time) == 3

        await http_client.token_refresher.close()
        await http_client.token_refresher._session.close()
        await http_client._session.close()
