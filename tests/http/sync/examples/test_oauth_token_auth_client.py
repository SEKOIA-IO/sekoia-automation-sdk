"""Example implementation with tests for SyncOauthTokenAuthClient."""

import json

import requests_mock
from faker import Faker
from requests_oauthlib import OAuth2Session

from sekoia_automation.http.rate_limiter import RateLimiterConfig
from sekoia_automation.http.retry import RetryPolicy
from sekoia_automation.http.sync.http_client import SyncHttpClient


class SyncOauthClientExample(SyncHttpClient):
    def __init__(
        self,
        client_id: str,
        auth_url: str,
        scope: str,
        base_url: str,
        retry_policy: RetryPolicy | None = None,
        rate_limiter_config: RateLimiterConfig | None = None,
    ):
        super().__init__(retry_policy, rate_limiter_config)
        self.base_url = base_url
        self.client_id = client_id
        self.auth_url = auth_url
        self.scope = scope
        self.oauth_session: OAuth2Session | None = None

    def get_oauth_session(self) -> OAuth2Session:
        if self.oauth_session is not None:
            return self.oauth_session

        self.oauth_session = OAuth2Session(self.client_id, scope=self.scope)

        return self.oauth_session

    @classmethod
    def instance(
        cls,
        client_id: str,
        auth_url: str,
        scope: str,
        base_url: str,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        status_forcelist: list[int] | None = None,
        max_rate: float | None = None,
        time_period: float | None = None,
    ) -> "SyncOauthClientExample":
        return cls(
            client_id,
            auth_url,
            scope,
            base_url,
            retry_policy=RetryPolicy.create(
                max_retries, backoff_factor, status_forcelist
            ),
            rate_limiter_config=RateLimiterConfig.create(max_rate, time_period),
        )

    def get_headers(self) -> dict[str, str]:
        token = self.get_oauth_session().refresh_token(self.auth_url)

        return {
            "CientId": self.client_id,
            "AccessToken": token["access_token"],
            "OtherPayload": "hello world",
        }

    def get_events_url(self) -> str:
        return f"{self.base_url}/get/events/example"

    def get_events_example_base_method(
        self, params: dict[str, str]
    ) -> list[dict[str, str]]:
        """
        Get events from url.

        Args:
            params: dict[str, str]

        Returns:
            list[dict[str, str]]:
        """
        response = self.session().get(
            self.get_events_url(), params=params, headers=self.get_headers()
        )

        return response.json()


def test_get_events_example_method(session_faker: Faker):
    """
    Test get_events_example_base_method.

    Args:
        session_faker: Faker
    """
    base_url = str(session_faker.uri())
    auth_url = str(session_faker.uri())
    client_id = session_faker.word()

    client = SyncOauthClientExample.instance(
        auth_url=auth_url,
        client_id=client_id,
        base_url=base_url,
        scope="local",
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

        m.post(auth_url, status_code=200, json={"access_token": session_faker.word()})
        m.get(request_url, status_code=200, json=data)

        assert client.get_events_example_base_method({"key": "value"}) == data
