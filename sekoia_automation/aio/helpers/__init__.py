"""
Package contains all utilities and useful helpers.

NOTE!!!: each package inside requires additional libraries to be installed.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any


async def limit_concurrency(tasks: list, limit: int) -> AsyncGenerator[Any, None]:
    """
    Limit the number of concurrent async tasks at the same time

    :param list tasks: The list of async tasks to execute
    :param: int limit: The number of concurrent async tasks allows at the same time

    """
    semaphore = asyncio.Semaphore(limit)

    async def sem_coro(task):
        async with semaphore:
            return await task

    for result in await asyncio.gather(*map(sem_coro, tasks)):
        yield result
