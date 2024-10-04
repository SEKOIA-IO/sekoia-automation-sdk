"""Contains connector with async version."""

import asyncio
import time
from abc import ABC
from asyncio import AbstractEventLoop, get_event_loop
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from aiohttp import ClientSession
from aiolimiter import AsyncLimiter

from sekoia_automation.aio.helpers import limit_concurrency
from sekoia_automation.connector import (
    Connector,
    DefaultConnectorConfiguration,
    EventType,
)
from sekoia_automation.module import Module


class AsyncConnector(Connector, ABC):
    """Async version of Connector."""

    configuration: DefaultConnectorConfiguration

    _event_loop: AbstractEventLoop

    _session: ClientSession | None = None
    _rate_limiter: AsyncLimiter | None = None

    def __init__(
        self,
        module: Module | None = None,
        data_path: Path | None = None,
        event_loop: AbstractEventLoop | None = None,
        *args,
        **kwargs,
    ):
        """
        Initialize AsyncConnector.

        Optionally accepts event_loop to use, otherwise will use default event loop.

        Args:
            module: Module | None
            data_path: Path | None
            event_loop: AbstractEventLoop | None
        """
        self.max_concurrency_tasks = kwargs.pop("max_concurrency_tasks", 1000)
        super().__init__(module=module, data_path=data_path, *args, **kwargs)

        self._event_loop = event_loop or get_event_loop()

    @classmethod
    def set_client_session(cls, session: ClientSession) -> None:
        """
        Set client session.

        Args:
            session: ClientSession
        """
        cls._session = session

    @classmethod
    def set_rate_limiter(cls, rate_limiter: AsyncLimiter) -> None:
        """
        Set rate limiter.

        Args:
            rate_limiter:
        """
        cls._rate_limiter = rate_limiter

    @classmethod
    def get_rate_limiter(cls) -> AsyncLimiter:
        """
        Get or initialize rate limiter.

        Returns:
            AsyncLimiter:
        """
        if cls._rate_limiter is None:
            cls._rate_limiter = AsyncLimiter(1, 1)

        return cls._rate_limiter

    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncGenerator[ClientSession, None]:  # pragma: no cover
        """
        Get or initialize client session if it is not initialized yet.

        Returns:
            ClientSession:
        """
        if cls._session is None:
            cls._session = ClientSession()

        async with cls.get_rate_limiter():
            yield cls._session

    async def async_close(self) -> None:
        """Close session."""
        if self._session:
            await self._session.close()

    async def _async_send_chunk(
        self, session: ClientSession, url: str, chunk_index: int, chunk: list[str]
    ) -> list[str]:
        """
        Send one chunk of events to intakes

        Args:
            session: ClientSession
            url: str
            chunk_index: int
            chunk: list[str]

        Returns:
            list[str]
        """
        request_body = {
            "intake_key": self.configuration.intake_key,
            "jsons": chunk,
        }

        events_ids = []

        for attempt in self._retry():
            with attempt:
                async with session.post(
                    url,
                    headers={"User-Agent": self._connector_user_agent},
                    json=request_body,
                ) as response:
                    if response.status >= 300:
                        error = await response.text()
                        error_message = f"Chunk {chunk_index} error: {error}"
                        exception = RuntimeError(error_message)

                        self.log_exception(exception)

                    result = await response.json()
                    events_ids.extend(result.get("event_ids", []))

        return events_ids

    async def push_data_to_intakes(
        self, events: Sequence[EventType]
    ) -> list[str]:  # pragma: no cover
        """
        Custom method to push events to intakes.

        Args:
            events: list[str]

        Returns:
            list[str]:
        """
        if intake_server := self.configuration.intake_server:
            batch_api = urljoin(intake_server, "batch")
        else:
            batch_api = urljoin(self.intake_url, "batch")

        result_ids = []

        chunks = self._chunk_events(events)

        async with self.session() as session:
            forwarders = [
                self._async_send_chunk(session, batch_api, chunk_index, chunk)
                for chunk_index, chunk in enumerate(chunks)
            ]
            async for ids in limit_concurrency(forwarders, self.max_concurrency_tasks):
                result_ids.extend(ids)

        return result_ids

    async def async_iterate(
        self,
    ) -> AsyncGenerator[tuple[list[EventType], datetime | None], None]:
        """Iterate over events."""
        yield [], None  # To avoid type checking error

    async def async_next_run(self) -> None:
        processing_start = time.time()

        result_last_event_date: datetime | None = None
        total_number_of_events = 0
        async for data in self.async_iterate():
            events, last_event_date = data
            if last_event_date:
                if (
                    not result_last_event_date
                    or last_event_date > result_last_event_date
                ):
                    result_last_event_date = last_event_date

            if events:
                total_number_of_events += len(events)
                await self.push_data_to_intakes(events)

        processing_end = time.time()
        processing_time = processing_end - processing_start

        # Metric about processing time
        self._forward_events_duration.labels(
            intake_key=self.configuration.intake_key
        ).observe(processing_time)

        # Metric about processing count
        self._outcoming_events.labels(intake_key=self.configuration.intake_key).inc(
            total_number_of_events
        )

        # Metric about events lag
        if result_last_event_date:
            lag = (datetime.utcnow() - result_last_event_date).total_seconds()
            self._events_lag.labels(intake_key=self.configuration.intake_key).set(lag)

        # Compute the remaining sleeping time.
        # If greater than 0 and no messages where fetched, pause the connector
        delta_sleep = (self.frequency or 0) - processing_time
        if total_number_of_events == 0 and delta_sleep > 0:
            self.log(message=f"Next batch in the future. Waiting {delta_sleep} seconds")

            await asyncio.sleep(delta_sleep)

    # Put infinite arg only to have testing easier
    async def async_run(self) -> None:  # pragma: no cover
        """Runs Connector."""
        while self.running:
            try:
                await self.async_next_run()
            except Exception as e:
                self.log_exception(
                    e,
                    message=f"Error while running connector {self.connector_name}",
                )

                if self.frequency:
                    await asyncio.sleep(self.frequency)

    def run(self) -> None:  # pragma: no cover
        """Runs Connector."""
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.async_run())
        loop.run_until_complete(self.async_close())
