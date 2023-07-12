"""Useful functions for working with csv files."""

from collections.abc import AsyncGenerator
from typing import Any

import aiocsv
import aiofiles


async def csv_file_as_rows(
    file_path: str, encoding: str = "utf-8", delimiter: str = ","
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Read csv file as rows.

    Transform each row into dict with keys from the header row.

    Args:
        file_path: str
        encoding: str
        delimiter: str

    Yields:
        dict[str, Any]:
    """
    async with aiofiles.open(file_path, encoding=encoding) as file:
        async for row in aiocsv.AsyncDictReader(file, delimiter=delimiter):
            yield row
