"""Example implementation with tests for AsyncBearerTokenAuthClient."""

import json
from typing import Any

import requests_mock
from faker import Faker

from sekoia_automation.http.rate_limiter import RateLimiterConfig
from sekoia_automation.http.retry import RetryPolicy
from sekoia_automation.http.sync.http_client import SyncHttpClient


class BearerBasedHttpClient(SyncHttpClient):

    def __init__(
        self,
        token: str,
        base_url: str,
        retry_policy: RetryPolicy | None = None,
        rate_limiter_config: RateLimiterConfig | None = None,
    ):
        super().__init__(retry_policy, rate_limiter_config)

        self.token = token
        self.base_url = base_url

    @classmethod
    def instance(
        cls,
        token: str,
        base_url: str,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        status_forcelist: list[int] | None = None,
        max_rate: float | None = None,
        time_period: float | None = None,
    ) -> "BearerBasedHttpClient":
        return cls(
            token,
            base_url,
            retry_policy=RetryPolicy.create(
                max_retries, backoff_factor, status_forcelist
            ),
            rate_limiter_config=RateLimiterConfig.create(max_rate, time_period),
        )

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get_events_url(self) -> str:
        return f"{self.base_url}/get/events/example"

    def get_events_example_base_method(
        self, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """
        Get events from url.

        Args:
            params: dict[str, str]

        Returns:
            list[str]:
        """
        return (
            self.session()
            .get(self.get_events_url(), params=params, headers=self.get_headers())
            .json()
        )


def test_get_events_example_method(session_faker: Faker):
    """
    Test get_events_example_base_method.

    Args:
        session_faker: Faker
    """
    base_url = str(session_faker.uri())
    token = session_faker.word()

    client = BearerBasedHttpClient.instance(
        base_url=base_url,
        token=token,
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[400, 402, 405],
    )

    data = json.loads(
        session_faker.json(
            data_columns={"test": ["name", "name", "name"]},
            num_rows=10,
        )
    )

    with requests_mock.Mocker() as m:
        request_url = client.get_events_url() + "?key=value"

        m.get(request_url, status_code=200, json=data)
        assert client.get_events_example_base_method({"key": "value"}) == data
