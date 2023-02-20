import uuid
from collections.abc import Generator, Sequence
from datetime import time
from functools import cached_property
from typing import Any
from urllib.parse import urljoin

import orjson
import requests
from pydantic import BaseModel
from requests import Response
from tenacity import Retrying, stop_after_attempt, wait_exponential

from sekoia_automation.constants import CHUNK_BYTES_MAX_SIZE, EVENT_BYTES_MAX_SIZE
from sekoia_automation.trigger import Trigger

# Connector are a kind of trigger that fetch events from remote sources.
# We should add the content of push_events_to_intakes
# so that we are able to send events directly from connectors


class DefaultConnectorConfiguration(BaseModel):
    intake_server: str = "https://intake.sekoia.io"
    intake_key: str
    chunk_size: int = 1000


class Connector(Trigger):
    configuration: DefaultConnectorConfiguration

    def _retry(self):
        return Retrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )

    @cached_property
    def __connector_user_agent(self):
        return f"sekoiaio-connector-{self.configuration.intake_key}"

    def push_events_to_intakes(self, events: list[str]) -> list:
        # no event to push
        if not events:
            return []

        intake_host = self.configuration.intake_server
        batch_api = urljoin(intake_host, "/batch")

        event_ids: list = []

        # pushing the events
        chunks = self._chunk_events(events, self.configuration.chunk_size)
        for chunk in chunks:
            try:
                request_body = {
                    "intake_key": self.configuration.intake_key,
                    "jsons": chunk,
                }

                for attempt in self._retry():
                    with attempt:
                        res: Response = requests.post(
                            batch_api,
                            json=request_body,
                            headers={"User-Agent": self.__connector_user_agent},
                        )
                if res.status_code > 299:
                    self.log(f"Intake rejected events: {res.text}", level="error")
                    res.raise_for_status()
                event_ids += res.json().get("event_ids", [])
            except Exception as ex:
                self.log_exception(
                    ex, message=f"Failed to forward {len(events)} events"
                )

        return event_ids

    def send_records(
        self,
        records: list,
        event_name: str,
        to_file: bool = True,
        records_var_name: str = "records",
    ):
        if not to_file:
            self.send_event(event={records_var_name: records}, event_name=event_name)
            return

        # save event in file
        work_dir = self._data_path.joinpath(f"{self.name}_events").joinpath(
            str(uuid.uuid4())
        )
        work_dir.mkdir(parents=True, exist_ok=True)

        event_path = work_dir.joinpath("event.json")
        with event_path.open("w") as fp:
            fp.write(orjson.dumps(records).decode("utf-8"))

        # Send Event
        directory = str(work_dir.relative_to(self._data_path))
        file_path = str(event_path.relative_to(work_dir))
        self.send_event(
            event_name=event_name,
            event={f"{records_var_name}_path": file_path},
            directory=directory,
            remove_directory=True,
        )

    def _chunk_events(
        self, events: Sequence, chunk_size: int
    ) -> Generator[list[Any], None, None]:
        """Group events by chunk.

        :param sequence events: The events to group
        :param int chunk_size: The size of the chunk
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
            if (
                len(chunk) >= chunk_size
                or chunk_bytes + len(event) > CHUNK_BYTES_MAX_SIZE
            ):
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
                "were discarded (length > 64kb)"
            )

    def forward_events(self, events):
        try:
            chunks = self._chunk_events(events, self.configuration.chunk_size)
            for records in chunks:
                self.log(message=f"Forwarding {len(records)} records", level="info")
                self.send_records(
                    records=list(records),
                    event_name=f"{self.name.lower().replace(' ', '-')}_{str(time())}",
                )
        except Exception as ex:
            self.log_exception(ex, message="Failed to forward events")
