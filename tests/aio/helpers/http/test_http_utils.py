"""Tests for `sekoia_automation.aio.helpers.http.utils`."""
import os

import aiofiles
import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from sekoia_automation.aio.helpers.files.utils import delete_file
from sekoia_automation.aio.helpers.http.utils import save_aiohttp_response


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
    with aioresponses() as mocked_responses:
        url = session_faker.uri()
        mocked_responses.get(
            url=url,
            status=200,
            body=data,
            headers={"Content-Length": f"{len(data)}"},
        )

        async with ClientSession() as session:
            async with session.get(url) as response:
                file_path = await save_aiohttp_response(
                    response, temp_dir=str(tmp_path)
                )

    assert os.path.exists(file_path)

    async with aiofiles.open(file_path, encoding="utf-8") as file:
        content = await file.read()

        assert content == data

    await delete_file(file_path)

    assert not os.path.exists(file_path)
