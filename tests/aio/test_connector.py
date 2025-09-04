"""Test async connector."""

from collections.abc import AsyncGenerator
from datetime import datetime
from posixpath import join as urljoin
from unittest.mock import Mock, patch

import pytest
from aiolimiter import AsyncLimiter
from aioresponses import aioresponses
from faker import Faker
from tenacity import Retrying, stop_after_attempt

from sekoia_automation.aio.connector import AsyncConnector


class DummyAsyncConnector(AsyncConnector):
    trigger_activation: str | None = None

    events: list[list[str]] | None = None

    def set_events(self, events: list[list[str]]) -> None:
        self.events = events

    async def async_iterate(
        self,
    ) -> AsyncGenerator[tuple[list[str], datetime | None], None]:
        if self.events is None:
            raise RuntimeError("Events are not set")

        for event in self.events:
            yield event, None


@pytest.fixture
def async_connector(storage, mocked_trigger_logs, faker: Faker):
    with patch("sentry_sdk.set_tag"):
        async_connector = DummyAsyncConnector(data_path=storage)

        async_connector.trigger_activation = "2022-03-14T11:16:14.236930Z"
        async_connector.configuration = {
            "intake_key": "",
            "intake_server": faker.uri(),
        }

        async_connector.log = Mock()
        async_connector.log_exception = Mock()

        yield async_connector

        async_connector.stop()


@pytest.mark.asyncio
async def test_async_connector_client_session(async_connector: DummyAsyncConnector):
    """
    Test async connector client_session.

    Args:
        async_connector: DummyAsyncConnector
    """
    other_instance = DummyAsyncConnector()

    assert async_connector._session is None
    assert other_instance._session is None

    async with async_connector.session() as session_1:
        async with other_instance.session() as session_2:
            assert session_1 != session_2

            assert async_connector._rate_limiter is not None and isinstance(
                async_connector._rate_limiter, AsyncLimiter
            )

            assert other_instance._rate_limiter is not None and isinstance(
                other_instance._rate_limiter, AsyncLimiter
            )


@pytest.mark.asyncio
async def test_async_connector_push_single_event(
    async_connector: DummyAsyncConnector, faker: Faker
):
    """
    Test async connector push events.

    Args:
        async_connector: DummyAsyncConnector
        faker: Faker
    """
    events = [
        faker.json(
            data_columns={
                "Spec": "@1.0.1",
                "ID": "pyint",
                "Details": {"Name": "name", "Address": "address"},
            },
            num_rows=1,
        )
    ]

    single_event_id = faker.uuid4()

    request_url = urljoin(async_connector.configuration.intake_server, "batch")

    with aioresponses() as mocked_responses:
        mocked_responses.post(
            request_url,
            status=200,
            payload={"received": True, "event_ids": [single_event_id]},
        )

        result = await async_connector.push_data_to_intakes(events)

        assert result == [single_event_id]


@pytest.mark.asyncio
async def test_async_connector_push_multiple_events(
    async_connector: DummyAsyncConnector, faker: Faker
):
    """
    Test async connector push events.

    Args:
        async_connector: DummyAsyncConnector
        faker: Faker
    """
    events = [
        faker.json(
            data_columns={
                "Spec": "@1.0.1",
                "ID": "pyint",
                "Details": {"Name": "name", "Address": "address"},
            },
            num_rows=1,
        )
        for _ in range(100)
    ]

    single_event_id = faker.uuid4()

    request_url = urljoin(async_connector.configuration.intake_server, "batch")

    with (
        aioresponses() as mocked_responses,
        patch("sekoia_automation.connector.CHUNK_BYTES_MAX_SIZE", 128),
    ):
        for _ in range(100):
            mocked_responses.post(
                request_url,
                status=200,
                payload={"received": True, "event_ids": [single_event_id]},
            )

        result = await async_connector.push_data_to_intakes(events)

        assert result == [single_event_id for _ in range(100)]


@pytest.mark.asyncio
async def test_async_connector_raise_error(
    async_connector: DummyAsyncConnector, faker: Faker
):
    """
    Test async connector push events.

    Args:
        async_connector: DummyAsyncConnector
        faker: Faker
    """
    events = [
        faker.json(
            data_columns={
                "Spec": "@1.0.1",
                "ID": "pyint",
                "Details": {"Name": "name", "Address": "address"},
            },
            num_rows=1,
        )
    ]

    async_connector._retry = lambda: Retrying(
        reraise=True,
        stop=stop_after_attempt(1),
    )

    request_url = urljoin(async_connector.configuration.intake_server, "batch")

    with (
        aioresponses() as mocked_responses,
        patch("sekoia_automation.connector.CHUNK_BYTES_MAX_SIZE", 128),
    ):
        for _ in range(2):
            mocked_responses.post(
                request_url,
                status=400,
                payload={"message_error": "custom message"},
            )

        expected_error = 'Chunk 0 error: {"message_error": "custom message"}'

        try:
            await async_connector.push_data_to_intakes(events)

        except Exception as e:
            assert isinstance(e, RuntimeError)
            assert str(e) == expected_error


@pytest.mark.asyncio
async def test_async_connector_async_next_run(
    async_connector: DummyAsyncConnector, faker: Faker
):
    """
    Test async connector push events.

    Args:
        async_connector: DummyAsyncConnector
        faker: Faker
    """
    single_event_id = faker.uuid4()

    # We expect 3 chunks of events
    test_events = [
        [faker.uuid4(), faker.uuid4()],
        [faker.uuid4(), faker.uuid4(), faker.uuid4()],
        [faker.uuid4(), faker.uuid4(), faker.uuid4(), faker.uuid4()],
    ]

    async_connector.set_events(test_events)

    request_url = urljoin(async_connector.configuration.intake_server, "batch")

    with aioresponses() as mocked_responses:
        mocked_responses.post(
            request_url,
            status=200,
            payload={"received": True, "event_ids": [single_event_id]},
        )

        mocked_responses.post(
            request_url,
            status=200,
            payload={"received": True, "event_ids": [single_event_id]},
        )

        mocked_responses.post(
            request_url,
            status=200,
            payload={"received": True, "event_ids": [single_event_id]},
        )

        await async_connector.async_next_run()


@pytest.mark.parametrize(
    "base_url,expected_batchapi_url",
    [
        ("http://intake.fake.url/", "http://intake.fake.url/batch"),
        ("http://fake.url/intake/", "http://fake.url/intake/batch"),
        ("http://fake.url/intake", "http://fake.url/intake/batch"),
    ],
)
def test_async_connector_batchapi_url(
    storage, mocked_trigger_logs, base_url: str, expected_batchapi_url: str
):
    with patch("sentry_sdk.set_tag"):
        async_connector = DummyAsyncConnector(data_path=storage)

        async_connector.trigger_activation = "2022-03-14T11:16:14.236930Z"
        async_connector.configuration = {
            "intake_key": "",
            "intake_server": base_url,
        }

        assert async_connector._batchapi_url == expected_batchapi_url
