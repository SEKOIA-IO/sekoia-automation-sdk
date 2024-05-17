import enum
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from dateutil.parser import isoparse

from sekoia_automation.storage import PersistentJSON


class TimeUnit(enum.Enum):
    SECOND = 1
    MILLISECOND = 2
    NANOSECOND = 3


class Checkpoint:
    def __init__(self, path: Path) -> None:
        self._context = PersistentJSON("context.json", path)

    @property
    @abstractmethod
    def offset(self) -> Any:
        raise NotImplementedError

    @offset.setter
    @abstractmethod
    def offset(self, *args, **kwargs) -> None:
        raise NotImplementedError


class CheckpointDatetimeBase(ABC, Checkpoint):
    def __init__(
        self,
        path: Path,
        start_at: timedelta = timedelta(minutes=5),
        ignore_older_than: timedelta | None = timedelta(days=30),
        lock: "Lock | None" = None,
        subkey: str | None = None,
    ) -> None:
        """
        @param start_at: if no checkpoint exist, start `{start_at}` ago
        @param ignore_older_than: if provided, make sure returned datetime will
                                  not be older than `{ignore_older_than}` ago
        @param lock: if provided, we'll acquire the lock before reading
                     the context.json and release it after
        @param subkey: support sub keys (e.g. you use multiple threads and save datetime
                       for each thread separately in one json)
        """
        super().__init__(path)

        self._most_recent_date_seen: datetime | None = None
        self._start_at = start_at
        self._ignore_older_than = ignore_older_than
        self._subkey = subkey
        self._lock = lock

    def file_to_datetime(self, date_str: str) -> datetime:
        return isoparse(date_str)

    def datetime_to_file(self, dt: datetime) -> str:
        return dt.isoformat()

    @abstractmethod
    def from_datetime(self, dt):
        raise NotImplementedError

    @abstractmethod
    def to_datetime(self, rp):
        raise NotImplementedError

    @property
    def offset(self) -> datetime:
        if self._most_recent_date_seen is None:
            if self._lock:
                self._lock.acquire()

            with self._context as cache:
                if self._subkey:
                    most_recent_date_seen_str = cache.get(self._subkey, {}).get(
                        "most_recent_date_seen"
                    )

                else:
                    most_recent_date_seen_str = cache.get("most_recent_date_seen")

            if self._lock:
                self._lock.release()

            # if undefined, retrieve events from the {self._start_at} ago
            if most_recent_date_seen_str is None:
                self._most_recent_date_seen = (
                    datetime.now(timezone.utc) - self._start_at
                )
                return self.from_datetime(self._most_recent_date_seen)

            most_recent_date_seen = self.file_to_datetime(most_recent_date_seen_str)

            if self._ignore_older_than:
                # check if the date is older than the {self._ignore_older_than} ago
                too_old = datetime.now(timezone.utc) - self._ignore_older_than
                if most_recent_date_seen < too_old:
                    most_recent_date_seen = too_old

            self._most_recent_date_seen = most_recent_date_seen

        return self.from_datetime(self._most_recent_date_seen)

    @offset.setter
    def offset(self, last_message_date: datetime) -> None:
        if last_message_date is not None:
            # convert to inner representation
            last_message_date = self.to_datetime(last_message_date)

            if self.offset is None or last_message_date > self.offset:
                self._most_recent_date_seen = last_message_date

                if self._lock:
                    self._lock.acquire()

                with self._context as cache:
                    if self._subkey:
                        if self._subkey not in cache:
                            cache[self._subkey] = {}

                        cache[self._subkey]["most_recent_date_seen"] = (
                            self.datetime_to_file(self._most_recent_date_seen)
                        )

                    else:
                        cache["most_recent_date_seen"] = self.datetime_to_file(
                            self._most_recent_date_seen
                        )

                if self._lock:
                    self._lock.release()


class CheckpointDatetime(CheckpointDatetimeBase):
    def from_datetime(self, dt):
        return dt

    def to_datetime(self, rp):
        return rp


class CheckpointTimestamp(CheckpointDatetimeBase):
    def __init__(
        self,
        path: Path,
        time_unit: TimeUnit,
        start_at: timedelta = timedelta(minutes=5),
        ignore_older_than: timedelta | None = timedelta(days=30),
        lock: "Lock | None" = None,
        subkey: str | None = None,
    ):
        super().__init__(path, start_at, ignore_older_than, lock, subkey)

        self._time_unit = time_unit

    @property
    def multiplier(self) -> float:
        if self._time_unit == TimeUnit.SECOND:
            multiplier = 1.0

        elif self._time_unit == TimeUnit.MILLISECOND:
            multiplier = 1_000.0

        elif self._time_unit == TimeUnit.NANOSECOND:
            multiplier = 1_000_000.0

        else:
            raise ValueError("There is no such time unit")

        return multiplier

    def from_datetime(self, dt) -> int:
        return round(dt.timestamp() * self.multiplier)

    def to_datetime(self, rp: float | int) -> datetime:
        # timestamp -> inner representation
        return datetime.fromtimestamp(rp / self.multiplier).astimezone(timezone.utc)


class CheckpointCursor(Checkpoint):
    def __init__(
        self,
        path: Path,
        lock: "Lock | None" = None,
        subkey: str | None = None,
    ) -> None:
        """
        @param lock: if provided, we'll acquire the lock before reading
                     the context.json and release it after
        @param subkey: support sub keys (e.g. you use multiple threads and save datetime
                       for each thread separately in one json)
        """
        super().__init__(path)

        self._cursor: Any = None
        self._subkey = subkey
        self._lock = lock

    @property
    def offset(self) -> Any:
        if self._lock:
            self._lock.acquire()

        with self._context as cache:
            if self._subkey:
                self._cursor = cache.get(self._subkey, {}).get("cursor")
            else:
                self._cursor = cache.get("cursor")

        if self._lock:
            self._lock.release()

        return self._cursor

    @offset.setter
    def offset(self, offset: str) -> None:
        if self._lock:
            self._lock.acquire()

        with self._context as cache:
            if self._subkey:
                if self._subkey not in cache:
                    cache[self._subkey] = {}

                cache[self._subkey]["cursor"] = offset

            else:
                cache["cursor"] = offset

        if self._lock:
            self._lock.release()
