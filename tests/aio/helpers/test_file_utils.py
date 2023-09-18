"""Tests for file `sekoia_automation.aio.helpers.files` module."""

import csv
import os

import pytest

from sekoia_automation.aio.helpers.files.csv import csv_file_as_rows
from sekoia_automation.aio.helpers.files.utils import delete_file


@pytest.fixture
def csv_content(session_faker) -> str:
    """
    Generate csv content.

    Args:
        session_faker: Faker
    """
    number_of_columns = session_faker.random.randint(1, 10)
    number_of_rows = session_faker.random.randint(1, 50)

    columns = [session_faker.word().upper() for _ in range(number_of_columns)]
    rows = [
        ",".join([session_faker.word() for _ in range(number_of_columns)])
        for _ in range(number_of_rows)
    ]

    return "\n".join([",".join(columns), *rows])


@pytest.fixture
def random_text(session_faker) -> str:
    """
    Fixture for random text.

    Args:
        session_faker: Faker
    """
    nb_sentences = session_faker.pyint(min_value=2, max_value=10)

    return session_faker.paragraph(nb_sentences=nb_sentences)


@pytest.mark.asyncio
async def test_delete_file(tmp_path, session_faker, random_text):
    """
    Test delete_file.

    Args:
        tmp_path: Path
        session_faker: Faker
        random_text: str
    """
    file_path = os.path.join(tmp_path, session_faker.word())
    with open(file_path, "w+") as file:
        file.write(random_text)

    assert os.path.exists(file_path)

    await delete_file(file_path)

    assert not os.path.exists(file_path)


@pytest.mark.asyncio
async def test_csv_file_content(tmp_path, session_faker, csv_content):
    """
    Test read file content as csv.

    Args:
        tmp_path: Path
        session_faker: Faker
        csv_content: str
    """
    file_path = os.path.join(tmp_path, session_faker.word())
    with open(file_path, "w+") as file:
        file.write(csv_content)

    result = []
    async for row in csv_file_as_rows(file_path):
        result.append(row)

    assert result == list(csv.DictReader(csv_content.splitlines(), delimiter=","))

    await delete_file(file_path)

    assert not os.path.exists(file_path)
