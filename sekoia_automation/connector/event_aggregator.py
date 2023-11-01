import copy
import datetime
import threading
import time
from typing import Callable, Tuple

import xxhash
from ciso8601 import parse_datetime_as_naive
from pydantic import BaseModel


class Fingerprint(BaseModel):
    build_fingerprint_func: Callable[[dict], str | None]
    ttl: int


class Aggregation(BaseModel):
    start: datetime.datetime
    end: datetime.datetime
    ttl: int
    count: int
    event: dict
    fingerprint: str

    def get_aggregated_event(self):
        aggregated_event = copy.deepcopy(self.event)
        aggregated_event.setdefault("sekoiaio", {})
        aggregated_event["sekoiaio"]["repeat"] = {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "count": self.count,
            "fingerprint": self.fingerprint,
        }
        return aggregated_event


class EventAggregatorTTLThread(threading.Thread):
    f_must_stop: bool  # thread will stop if this flag is active
    on_flush_func: Callable[
        [dict], None
    ]  # function to be call when aggregation is flushed

    def __init__(
        self,
        event_aggregator: "EventAggregator",
        on_flush_func: Callable[[dict], None],
        delay: float = 10,
    ):
        super().__init__()
        self.event_aggregator = event_aggregator
        self.f_must_stop = False
        self.on_flush_func = on_flush_func
        self.delay = delay

    def stop(self) -> None:
        self.f_must_stop = True

    def run(self) -> None:
        try:
            while not self.f_must_stop:
                time.sleep(self.delay)
                for aggregated_event in self.event_aggregator.flush_all_ttl():
                    self.on_flush_func(aggregated_event)
        finally:
            for aggregated_event in self.event_aggregator.flush_all():
                self.on_flush_func(aggregated_event)


class EventAggregator:
    ttl_thread: EventAggregatorTTLThread | None
    lock: threading.Lock
    aggregation_definitions: list[Fingerprint]

    def __init__(self, aggregation_definitions: list[Fingerprint]):
        self.aggregation_definitions = aggregation_definitions
        self.aggregations: dict[str, Aggregation] = dict()
        self.lock = threading.Lock()

    def start_flush_on_ttl(
        self, on_flush_func: Callable[[dict], None], delay: float = 10
    ):
        """
        This method MUST be called to trigger the execution of the ttl thread
        """
        self.ttl_thread = EventAggregatorTTLThread(
            event_aggregator=self, on_flush_func=on_flush_func, delay=delay
        )
        self.ttl_thread.start()

    def stop(self):
        """
        Stops the ttl thread (if it runs)

        It is a blocking function.
        """
        if self.ttl_thread:
            self.ttl_thread.stop()
            self.ttl_thread.join()

    def flush_all(self) -> list[dict]:
        """
        returns all the aggregated events and remove them from the ongoing aggregations
        """
        aggregated_events = []

        # we prevent any actions on the aggregations while flushing
        with self.lock:
            for aggregation in self.aggregations.values():
                if aggregation.count > 0:
                    aggregated_events.append(aggregation.get_aggregated_event())

            self.aggregations = dict()
        return aggregated_events

    def flush_all_ttl(self) -> list[dict]:
        """
        Returns (and delete) all the events we aggregate for at least the ttl time
        """
        aggregated_events = []
        # we prevent any actions on the aggregations while flushing
        with self.lock:
            for event_hash in list(self.aggregations.keys()):
                aggregation = self.aggregations[event_hash]
                if (
                    aggregation.start + datetime.timedelta(seconds=aggregation.ttl)
                    < datetime.datetime.utcnow()
                ):
                    if aggregation.count > 0:
                        aggregated_events.append(aggregation.get_aggregated_event())

                    del self.aggregations[event_hash]

        return aggregated_events

    def get_fingerprint_hash(self, event: dict) -> Tuple[str, int] | None:
        """
        Returns the hash to fingerprint the specified event and its ttl
        """
        for fingerprint in self.aggregation_definitions:
            # building fingerprint may raise an exception
            # noinspection PyBroadException
            try:
                fingerprint_str = fingerprint.build_fingerprint_func(event)
                if fingerprint_str:
                    return xxhash.xxh3_64_hexdigest(fingerprint_str), fingerprint.ttl
            except Exception:
                pass
        return None

    def aggregate(self, event: dict) -> dict | None:
        # noinspection PyBroadException
        try:
            fingerprint_and_ttl = self.get_fingerprint_hash(event)
            # if no hash can be computed, we don't aggregate and forward the event
            if not fingerprint_and_ttl:
                return event
            event_fingerprint, ttl = fingerprint_and_ttl

            # the aggregation stores the parsed timestamp
            event_dt = parse_datetime_as_naive(event["@timestamp"])

            # if hash is already known
            with self.lock:
                if event_fingerprint in self.aggregations:
                    # update the aggregation's counter and last seen
                    self.aggregations[event_fingerprint].count += 1
                    self.aggregations[event_fingerprint].end = event_dt

                    # event is aggregated, we don't want to forward it
                    return None

                # if hash is unknown
                else:
                    # create a new aggregation with event details
                    self.aggregations[event_fingerprint] = Aggregation(
                        event=event,
                        start=event_dt,
                        end=event_dt,
                        fingerprint=event_fingerprint,
                        ttl=ttl,
                        count=0
                        # =0 prevent replay on flushing, we sent 1st occ. of event
                    )
                    # forward the first occurrence of the aggregation
                    return event
        except Exception:
            pass

        return event
