import asyncio

from sekoia_automation.aio.helpers import get_or_create_event_loop


def test_get_or_create_event_loop_creates_one_when_the_thread_has_none():
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None
    asyncio.set_event_loop(None)

    try:
        loop = get_or_create_event_loop()
        assert asyncio.get_event_loop() is loop
        loop.close()
    finally:
        asyncio.set_event_loop(previous_loop)


def test_get_or_create_event_loop_keeps_the_current_loop():
    loop = asyncio.new_event_loop()
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None
    asyncio.set_event_loop(loop)

    try:
        assert get_or_create_event_loop() is loop
    finally:
        asyncio.set_event_loop(previous_loop)
        loop.close()
