from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from sekoia_automation.checkpoint import (
    CheckpointCursor,
    CheckpointDatetime,
    CheckpointTimestamp,
    TimeUnit,
)


@pytest.fixture
def fake_time():
    yield datetime(2022, 11, 5, 11, 59, 59, tzinfo=timezone.utc)


@pytest.fixture
def patch_datetime_now(fake_time):
    with patch("sekoia_automation.checkpoint.datetime") as mock_datetime:
        mock_datetime.now.return_value = fake_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        mock_datetime.fromtimestamp = lambda ts: datetime.fromtimestamp(ts)
        yield mock_datetime


def test_checkpoint_cursor(storage):
    check = CheckpointCursor(path=storage)
    assert check.offset is None

    check.offset = "cursor:123"
    assert check.offset == "cursor:123"


def test_checkpoint_datetime_without_data(storage, patch_datetime_now, fake_time):
    check = CheckpointDatetime(
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=30),
    )

    # try without any data
    datetime_expected = fake_time - timedelta(minutes=5)
    assert check.offset.isoformat() == datetime_expected.isoformat()


def test_checkpoint_datetime_old(storage, patch_datetime_now, fake_time):
    check = CheckpointDatetime(
        path=storage, start_at=timedelta(minutes=5), ignore_older_than=timedelta(days=7)
    )

    # try very old
    with check._context as cache:
        cache["most_recent_date_seen"] = "2022-02-22T16:16:46+00:00"

    datetime_expected = fake_time - timedelta(days=7)
    assert check.offset.isoformat() == datetime_expected.isoformat()


def test_checkpoint_datetime_subkey(storage, patch_datetime_now, fake_time):
    check = CheckpointDatetime(
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=30),
        subkey="thread-1",
    )

    check.offset = fake_time
    with check._context as cache:
        assert "thread-1" in cache
        assert "most_recent_date_seen" in cache["thread-1"]


def test_checkpoint_timestamp_seconds_without_data(
    storage, patch_datetime_now, fake_time
):
    check = CheckpointTimestamp(
        time_unit=TimeUnit.SECOND,
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=30),
    )

    # try without any data
    datetime_expected = fake_time - timedelta(minutes=5)
    assert check.offset == int(datetime_expected.timestamp())


def test_checkpoint_timestamp_seconds_old(storage, patch_datetime_now, fake_time):
    check = CheckpointTimestamp(
        time_unit=TimeUnit.SECOND,
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=7),
    )

    # try very old
    with check._context as cache:
        cache["most_recent_date_seen"] = "2022-02-22T16:16:46+00:00"

    datetime_expected = fake_time - timedelta(days=7)
    assert check.offset == int(datetime_expected.timestamp())


def test_checkpoint_timestamp_seconds(storage, patch_datetime_now, fake_time):
    check = CheckpointTimestamp(
        time_unit=TimeUnit.SECOND,
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=7),
    )

    # try specific checked time
    with check._context as cache:
        cache["most_recent_date_seen"] = "2024-05-16T13:36:47+03:00"

    assert check.offset == 1715855807


def test_checkpoint_timestamp_milliseconds_without_data(
    storage, patch_datetime_now, fake_time
):
    check = CheckpointTimestamp(
        time_unit=TimeUnit.MILLISECOND,
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=30),
    )

    # try without any data
    datetime_expected = fake_time - timedelta(minutes=5)
    assert check.offset == int(datetime_expected.timestamp() * 1000)


def test_checkpoint_timestamp_milliseconds_old(storage, patch_datetime_now, fake_time):
    check = CheckpointTimestamp(
        time_unit=TimeUnit.MILLISECOND,
        path=storage,
        start_at=timedelta(minutes=5),
        ignore_older_than=timedelta(days=7),
    )

    # try very old
    with check._context as cache:
        cache["most_recent_date_seen"] = "2022-02-22T16:16:46+00:00"

    datetime_expected = fake_time - timedelta(days=7)
    assert check.offset == int(datetime_expected.timestamp() * 1000)
