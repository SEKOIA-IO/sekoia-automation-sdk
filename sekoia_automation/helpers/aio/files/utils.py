"""Wrappers to perform base operations with files."""

from aiofiles import os as aio_os


async def delete_file(file_name: str) -> None:
    """
    Delete file.

    Args:
        file_name: str
    """
    await aio_os.remove(file_name)
