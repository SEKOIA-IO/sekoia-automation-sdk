"""Example implementation with tests for AsyncOauthTokenAuthClient."""

import json
import time
from typing import Any

import pytest
from aioresponses import aioresponses
from faker import Faker
from pydantic.v1 import BaseModel

from sekoia_automation.http.aio.http_client import AsyncHttpClient
from sekoia_automation.http.aio.token_refresher import (
    GenericTokenRefresher,
    RefreshedToken,
)


class DummyOAuthResponse(BaseModel):
    access_token: str


class SampleTokenRefresher(GenericTokenRefresher):
    def __init__(self, auth_url: str, client_id: str, client_secret: str) -> None:
        super().__init__()

        self.auth_url = auth_url
        self.client_id = client_id
        self.client_secret = client_secret

    async def get_token(self) -> RefreshedToken[DummyOAuthResponse]:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with self.session().post(self.auth_url, json=data) as response:
            result = await response.json()

            return RefreshedToken(
                token=DummyOAuthResponse(**result),
                created_at=int(time.time()),
                ttl=3600,
            )


class AsyncOauthClientExample:
    def __init__(
        self,
        base_url: str,
        token_refresher: SampleTokenRefresher,
        http_client: AsyncHttpClient,
    ) -> None:
        self.base_url = base_url
        self.http_client = http_client
        self.token_refresher = token_refresher

    @classmethod
    async def instance(
        cls,
        client_id: str,
        client_secret: str,
        oauth_url: str,
        base_url: str,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        status_forcelist: list[int] | None = None,
        max_rate: float | None = None,
        time_period: float | None = None,
    ) -> "AsyncOauthClientExample":
        token_refresher = SampleTokenRefresher(oauth_url, client_id, client_secret)
        http_client = AsyncHttpClient.create(
            max_retries, backoff_factor, status_forcelist, max_rate, time_period
        )

        return cls(base_url, token_refresher, http_client)

    async def get_events(self) -> list[dict[str, Any]]:
        async with self.token_refresher.with_access_token() as token:
            headers = {
                "Authorization": f"Bearer {token.token.access_token}",
            }

            async with self.http_client.get(
                f"{self.base_url}/test/events", headers=headers
            ) as response:
                return await response.json()


@pytest.mark.asyncio
async def test_get_events_example_method(session_faker: Faker):
    """
    Test get_events_example_base_method.

    Args:
        session_faker: Faker
    """
    base_url = str(session_faker.uri())
    auth_url = str(base_url + "/auth")
    client_id = session_faker.word()
    client_secret = session_faker.word()
    test_token = session_faker.word()

    client = await AsyncOauthClientExample.instance(
        client_id=client_id,
        client_secret=client_secret,
        oauth_url=auth_url,
        base_url=base_url,
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[400],
    )

    data = json.loads(
        session_faker.json(
            data_columns={"test": ["name", "name", "name"]},
            num_rows=10,
        )
    )

    with aioresponses() as mocked_responses:
        request_url = f"{base_url}/test/events"

        auth_headers = {
            "Authorization": f"Bearer {test_token}",
        }

        mocked_responses.post(auth_url, payload={"access_token": test_token})
        mocked_responses.get(request_url, headers=auth_headers, status=400)
        mocked_responses.get(
            request_url, headers=auth_headers, payload=data, status=200
        )

        assert await client.get_events() == data

    await client.http_client.close()
