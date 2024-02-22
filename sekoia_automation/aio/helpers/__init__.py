"""
Package contains all utilities and useful helpers.

NOTE!!!: each package inside requires additional libraries to be installed.
"""

import asyncio
import itertools
from typing import AsyncGenerator, Any


async def limit_concurrency(aws: list, limit: int) -> AsyncGenerator[Any, None]:
    """
    Limit the number of concurrent async tasks at the same time

    :param list aws: The list of async tasks to execute
    :param: int limit: The number of concurrent async tasks allows at the same time

    """
    aws = iter(aws)
    while True:
        batch = list(itertools.islice(aws, limit))
        if not batch:
            break
        for result in await asyncio.gather(*batch):
            yield result
