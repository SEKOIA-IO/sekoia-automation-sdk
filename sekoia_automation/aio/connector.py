"""Contains connector with async version."""

import asyncio
import time
from abc import ABC
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from posixpath import join as urljoin

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

    configuration: DefaultConnectorConfiguration  # type: ignore[override]

    _session: ClientSession | None = None
    _rate_limiter: AsyncLimiter | None = None

    def __init__(
        self,
        module: Module | None = None,
        data_path: Path | None = None,
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

    def get_rate_limiter(self) -> AsyncLimiter:
        """
        Get or initialize rate limiter.

        Returns:
            AsyncLimiter:
        """
        if self._rate_limiter is None:
            self._rate_limiter = AsyncLimiter(1, 1)

        return self._rate_limiter

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[ClientSession, None]:  # pragma: no cover
        """
        Get or initialize client session if it is not initialized yet.

        Returns:
            ClientSession:
        """
        if self._session is None:
            self._session = ClientSession()

        async with self.get_rate_limiter():
            yield self._session

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

    @property
    def _batchapi_url(self):
        if intake_server := self.configuration.intake_server:
            return urljoin(intake_server, "batch")
        else:
            return urljoin(self.intake_url, "batch")

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
        self._last_events_time = datetime.utcnow()

        result_ids = []

        chunks = self._chunk_events(events)

        async with self.session() as session:
            forwarders = [
                self._async_send_chunk(session, self._batchapi_url, chunk_index, chunk)
                for chunk_index, chunk in enumerate(chunks)
            ]
            async for ids in limit_concurrency(forwarders, self.max_concurrency_tasks):
                result_ids.extend(ids)

        return result_ids

    async def async_iterate(
        self,
    ) -> AsyncGenerator[tuple[list[EventType], datetime | None], None]:
        """Iterate over events."""
        raise NotImplementedError  # To avoid type checking error

    async def async_next_run(self) -> None:
        processing_start = time.time()

        result_last_event_date: datetime | None = None
        total_number_of_events = 0
        async for data in self.async_iterate():  # type: ignore
            events, last_event_date = data
            if last_event_date:  # pragma: no cover
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
        self.put_forward_events_duration(
            intake_key=self.configuration.intake_key,
            duration=processing_time,
        )

        # Metric about processing count
        self.put_forwarded_events(
            intake_key=self.configuration.intake_key, count=total_number_of_events
        )

        # Metric about events lag
        if result_last_event_date:
            lag = (datetime.utcnow() - result_last_event_date).total_seconds()
            self.put_events_lag(intake_key=self.configuration.intake_key, lag=lag)

        # Compute the remaining sleeping time.
        # If greater than 0 and no messages where fetched, pause the connector
        delta_sleep = (self.frequency or 0) - processing_time
        if total_number_of_events == 0 and delta_sleep > 0:
            self.log(message=f"Next batch in the future. Waiting {delta_sleep} seconds")

            await asyncio.sleep(delta_sleep)

    async def on_shutdown(self) -> None:
        """
        Called when connector is finishing processing.

        Can be used for some resources cleanup.

        Basically it emits shutdown event.
        """

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

        if self._session:
            await self._session.close()

        await self.on_shutdown()

    def run(self) -> None:  # pragma: no cover
        """Runs Connector."""
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.async_run())
