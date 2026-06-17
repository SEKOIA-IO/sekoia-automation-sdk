"""Tests for `sekoia_automation.aio.helpers.http.utils`."""

import os

import aiofiles
import pytest

from sekoia_automation.aio.helpers.files.utils import delete_file
from sekoia_automation.aio.helpers.http.utils import save_aiohttp_response


class _FakeContent:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    async def read(self, chunk_size: int) -> bytes:
        if self._offset >= len(self._data):
            return b""

        next_offset = self._offset + chunk_size
        chunk = self._data[self._offset : next_offset]
        self._offset = next_offset
        return chunk


class _FakeResponse:
    def __init__(self, data: str):
        self.content = _FakeContent(data.encode("utf-8"))


@pytest.mark.asyncio
async def test_save_response_to_temporary_file(tmp_path, session_faker):
    """
    Test save response to file.

    Args:
        tmp_path: Path
        session_faker: Faker
    """
    data = session_faker.json(
        data_columns={"test": ["name", "name", "name"]},
        num_rows=1000,
    )

    response = _FakeResponse(data)
    file_path = await save_aiohttp_response(response, temp_dir=str(tmp_path))

    assert os.path.exists(file_path)

    async with aiofiles.open(file_path, encoding="utf-8") as file:
        content = await file.read()

        assert content == data

    await delete_file(file_path)

    assert not os.path.exists(file_path)
