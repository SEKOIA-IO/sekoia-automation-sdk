from threading import Event

import pytest

from sekoia_automation import backoff
from sekoia_automation.backoff import async_error_backoff, error_backoff


@pytest.fixture
def recorded_delays(monkeypatch):
    """Record every delay the synchronous controller waits for."""
    delays: list[float] = []
    monkeypatch.setattr(backoff, "sleep_using_event", lambda event: delays.append)
    return delays


@pytest.fixture
def recorded_async_delays(monkeypatch):
    """Record every delay the asynchronous controller waits for."""
    delays: list[float] = []

    async def to_thread(_wait, seconds):
        delays.append(seconds)

    monkeypatch.setattr(backoff.asyncio, "to_thread", to_thread)
    return delays


def test_error_backoff_waits_between_consecutive_failures(recorded_delays):
    attempts = 0

    for attempt in error_backoff(Event(), max_delay=60, jitter=0):
        with attempt:
            attempts += 1
            if attempts < 4:
                raise ValueError("boom")

    assert attempts == 4
    # No pause before the first attempt.
    assert recorded_delays == [1, 2, 4]


def test_error_backoff_caps_the_delay(recorded_delays):
    attempts = 0

    for attempt in error_backoff(Event(), max_delay=3, jitter=0):
        with attempt:
            attempts += 1
            if attempts < 5:
                raise ValueError("boom")

    assert recorded_delays == [1, 2, 3, 3]


def test_error_backoff_resets_on_a_new_controller(recorded_delays):
    stop_event = Event()

    for _ in range(2):
        attempts = 0
        for attempt in error_backoff(stop_event, max_delay=60, jitter=0):
            with attempt:
                attempts += 1
                if attempts < 3:
                    raise ValueError("boom")

    # Second controller restarts from 1s instead of carrying the first streak.
    assert recorded_delays == [1, 2, 1, 2]


def test_error_backoff_leaves_the_loop_when_stopped(recorded_delays):
    stop_event = Event()
    stop_event.set()
    attempts = 0

    # No RetryError: a stopped item must leave the loop quietly.
    for attempt in error_backoff(stop_event, max_delay=60, jitter=0):
        with attempt:
            attempts += 1
            raise ValueError("boom")

    assert attempts == 1
    assert recorded_delays == []


def test_error_backoff_calls_before_sleep(recorded_delays):
    seen: list[str] = []
    attempts = 0

    for attempt in error_backoff(
        Event(),
        before_sleep=lambda state: seen.append(str(state.outcome.exception())),
        max_delay=60,
        jitter=0,
    ):
        with attempt:
            attempts += 1
            if attempts < 3:
                raise ValueError("boom")

    assert seen == ["boom", "boom"]


def test_error_backoff_adds_jitter(recorded_delays):
    attempts = 0

    for attempt in error_backoff(Event(), max_delay=60, jitter=10):
        with attempt:
            attempts += 1
            if attempts < 4:
                raise ValueError("boom")

    assert len(recorded_delays) == 3
    for expected, actual in zip([1, 2, 4], recorded_delays, strict=True):
        assert expected <= actual <= expected + 10


@pytest.mark.asyncio
async def test_async_error_backoff_waits_between_consecutive_failures(
    recorded_async_delays,
):
    attempts = 0

    async for attempt in async_error_backoff(Event(), max_delay=60, jitter=0):
        with attempt:
            attempts += 1
            if attempts < 4:
                raise ValueError("boom")

    assert attempts == 4
    assert recorded_async_delays == [1, 2, 4]


@pytest.mark.asyncio
async def test_async_error_backoff_leaves_the_loop_when_stopped(
    recorded_async_delays,
):
    stop_event = Event()
    stop_event.set()
    attempts = 0

    async for attempt in async_error_backoff(stop_event, max_delay=60, jitter=0):
        with attempt:
            attempts += 1
            raise ValueError("boom")

    assert attempts == 1
    assert recorded_async_delays == []
