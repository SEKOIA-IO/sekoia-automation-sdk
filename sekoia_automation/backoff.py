"""
Backoff helpers pacing the trigger and connector run loops.

Thin `tenacity` factories: a loop that restarts a failed cycle needs a growing
pause, otherwise a permanent failure busy-loops. The stop event is used both as
the stop condition and as the sleep, so SIGTERM stays immediate mid-backoff.
"""

import asyncio
from collections.abc import Awaitable, Callable
from threading import Event

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    Retrying,
    sleep_using_event,
    stop_when_event_set,
    wait_exponential_jitter,
)

DEFAULT_MAX_DELAY = 300.0

# Absolute seconds, not a fraction of the delay. Tenacity's 1s default is too
# small to desynchronize a fleet failing against the same endpoint.
DEFAULT_JITTER = 30.0

BeforeSleep = Callable[[RetryCallState], None] | None
AsyncBeforeSleep = Callable[[RetryCallState], Awaitable[None] | None] | None


def error_backoff(
    stop_event: Event,
    before_sleep: BeforeSleep = None,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
) -> Retrying:
    """
    Build the controller pacing a synchronous run loop.

    The delay grows across consecutive failures; a fresh controller resets it.
    """
    return Retrying(
        stop=stop_when_event_set(stop_event),
        wait=wait_exponential_jitter(max=max_delay, jitter=jitter),
        sleep=sleep_using_event(stop_event),
        before_sleep=before_sleep,
        # Leave the loop quietly when stopped instead of raising RetryError.
        retry_error_callback=lambda _: None,
    )


def async_error_backoff(
    stop_event: Event,
    before_sleep: AsyncBeforeSleep = None,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
) -> AsyncRetrying:
    """
    Build the controller pacing an asynchronous run loop.

    `sleep_using_event` is synchronous, so the wait runs in a worker thread and
    still returns as soon as the stop event is set.
    """

    async def sleep(seconds: float) -> None:
        await asyncio.to_thread(stop_event.wait, seconds)

    return AsyncRetrying(
        stop=stop_when_event_set(stop_event),
        wait=wait_exponential_jitter(max=max_delay, jitter=jitter),
        sleep=sleep,
        before_sleep=before_sleep,
        retry_error_callback=lambda _: None,
    )
