import uuid
from abc import ABC
from collections.abc import Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as wait_futures
from datetime import datetime, time
from functools import cached_property
from os.path import join as urljoin
from typing import Any

import orjson
import requests
import sentry_sdk
from pydantic import BaseModel
from requests import Response
from tenacity import (
    Retrying,
    stop_after_delay,
    wait_exponential,
)

from sekoia_automation.constants import CHUNK_BYTES_MAX_SIZE, EVENT_BYTES_MAX_SIZE
from sekoia_automation.exceptions import (
    TriggerConfigurationError,
)
from sekoia_automation.trigger import Trigger
from sekoia_automation.utils import (
    get_annotation_for,
    get_as_model,
)

# Connector are a kind of trigger that fetch events from remote sources.
# We should add the content of push_events_to_intakes
# so that we are able to send events directly from connectors


class DefaultConnectorConfiguration(BaseModel):
    intake_server: str | None = None
    intake_key: str


class Connector(Trigger, ABC):
    CONNECTOR_CONFIGURATION_FILE_NAME = "connector_configuration"
    seconds_without_events = 3600 * 6

    # Required for Pydantic to correctly type the configuration object
    configuration: DefaultConnectorConfiguration

    @property  # type: ignore[override, no-redef]
    def configuration(self) -> DefaultConnectorConfiguration:
        if self._configuration is None:
            try:
                self.configuration = self.module.load_config(
                    self.CONNECTOR_CONFIGURATION_FILE_NAME, "json"
                )
            except FileNotFoundError:
                return super().configuration  # type: ignore[return-value]
        return self._configuration  # type: ignore[return-value]

    @configuration.setter
    def configuration(self, configuration: dict) -> None:
        """
        Set the connector configuration.

        Args:
            configuration: dict
        """
        try:
            self._configuration = get_as_model(
                get_annotation_for(self.__class__, "configuration"), configuration
            )
        except Exception as e:
            raise TriggerConfigurationError(str(e))

        if isinstance(self._configuration, BaseModel):
            sentry_sdk.set_context(
                "connector_configuration", self._configuration.dict()
            )

    def __init__(self, *args, **kwargs):
        executor_max_worker = kwargs.pop("executor_max_worker", 4)
        super().__init__(*args, **kwargs)
        self._executor = ThreadPoolExecutor(executor_max_worker)

    def stop(self, *args, **kwargs):
        """
        Stop the connector
        """
        super().stop(*args, **kwargs)
        self._executor.shutdown(wait=True)

    def _retry(self):
        return Retrying(
            stop=stop_after_delay(3600),  # 1 hour without being able to send events
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )

    @cached_property
    def _http_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": self._connector_user_agent})
        return session

    @cached_property
    def _connector_user_agent(self) -> str:
        return f"sekoiaio-connector-{self.configuration.intake_key}"

    @cached_property
    def http_default_headers(self) -> dict[str, str]:
        """
        Contains dict of predefined headers.

        This headers might be used by connector in requests to third party services.

        Returns:
            dict[str, str]:
        """
        return {
            "User-Agent": "sekoiaio-connector/{}-{}".format(
                self.module.manifest.get("slug"),
                self.module.manifest.get("version"),
            ),
        }

    def _send_chunk(
        self,
        batch_api: str,
        chunk_index: int,
        chunk: list[Any],
        collect_ids: dict[int, list[str]],
    ):
        try:
            request_body = {
                "intake_key": self.configuration.intake_key,
                "jsons": chunk,
            }

            for attempt in self._retry():
                with attempt:
                    res: Response = self._http_session.post(
                        batch_api,
                        json=request_body,
                        timeout=30,
                    )
                    res.raise_for_status()
            collect_ids[chunk_index] = res.json().get("event_ids", [])
        except Exception as ex:
            message = f"Failed to forward {len(chunk)} events"
            self.log(message=message, level="error")
            self.log_exception(ex, message=message)

    def push_events_to_intakes(
        self, events: list[str], sync: bool = False
    ) -> list[str]:
        """
        Push events to intakes.

        Args:
            events: list[str]
            sync: bool

        Returns:
            list[str]
        """
        # no event to push
        if not events:
            return []

        # Reset the consecutive error count
        self._error_count = 0
        self._last_events_time = datetime.utcnow()
        if intake_server := self.configuration.intake_server:
            batch_api = urljoin(intake_server, "batch")
        else:
            batch_api = urljoin(self.intake_url, "batch")

        # Dict to collect event_ids for the API
        collect_ids: dict[int, list] = {}

        # pushing the events
        chunks = self._chunk_events(events)

        # if requested, or if the executor is down
        if sync or not self.running:
            # forward in sequence
            for chunk_index, chunk in enumerate(chunks):
                self._send_chunk(batch_api, chunk_index, chunk, collect_ids)
        else:
            # Parallelize the forwarding
            futures = [
                self._executor.submit(
                    self._send_chunk, batch_api, chunk_index, chunk, collect_ids
                )
                for chunk_index, chunk in enumerate(chunks)
            ]
            wait_futures(futures)

        # reorder event_ids according chunk index
        event_ids = [
            event_id
            for chunk_index in sorted(collect_ids.keys())
            for event_id in collect_ids[chunk_index]
        ]

        return event_ids

    def send_records(
        self,
        records: list,
        event_name: str,
        to_file: bool = True,
        records_var_name: str = "records",
    ) -> None:
        """
        Sends records to the intake.

        Optionally persists events to file.

        Args:
            records: list
            event_name: str
            to_file: bool
            records_var_name: str
        """
        if not to_file:
            self.send_event(event={records_var_name: records}, event_name=event_name)
            return

        # save event in file
        work_dir = self.data_path.joinpath(f"{self.name}_events").joinpath(
            str(uuid.uuid4())
        )
        work_dir.mkdir(parents=True, exist_ok=True)

        event_path = work_dir.joinpath("event.json")
        with event_path.open("w") as fp:
            fp.write(orjson.dumps(records).decode("utf-8"))

        # Send Event
        directory = str(work_dir.relative_to(self.data_path))
        file_path = str(event_path.relative_to(work_dir))
        self.send_event(
            event_name=event_name,
            event={f"{records_var_name}_path": file_path},
            directory=directory,
            remove_directory=True,
        )

    def _chunk_events(self, events: Sequence) -> Generator[list[Any], None, None]:
        """
        Group events by chunk.

        Args:
            sequence events: Sequence: The events to group

        Returns:
            Generator[list[Any], None, None]:
        """
        chunk: list[Any] = []
        chunk_bytes: int = 0
        nb_discarded_events: int = 0

        # iter over the events
        for event in events:
            if len(event) > EVENT_BYTES_MAX_SIZE:
                nb_discarded_events += 1
                continue

            # if the chunk is full
            if chunk_bytes + len(event) > CHUNK_BYTES_MAX_SIZE:
                # yield the current chunk and create a new one
                yield chunk
                chunk = []
                chunk_bytes = 0

            # add the event to the current chunk
            chunk.append(event)
            chunk_bytes += len(event)

        # if the last chunk is not empty
        if len(chunk) > 0:
            # yield the last chunk
            yield chunk

        # if events were discarded, log it
        if nb_discarded_events > 0:
            self.log(
                message=f"{nb_discarded_events} too long events "
                "were discarded (length > 250kb)"
            )

    def forward_events(self, events) -> None:
        try:
            chunks = self._chunk_events(events)
            _name = self.name or ""  # mypy complains about NoneType in annotation
            for records in chunks:
                self.log(message=f"Forwarding {len(records)} records", level="info")
                self.send_records(
                    records=list(records),
                    event_name=f"{_name.lower().replace(' ', '-')}_{time()!s}",
                )
        except Exception as ex:
            self.log_exception(ex, message="Failed to forward events")
