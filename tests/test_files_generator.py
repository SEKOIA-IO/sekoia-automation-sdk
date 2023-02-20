import json
import os
from pathlib import Path
from shutil import copytree, rmtree
from tempfile import mkdtemp

import pytest

from sekoia_automation.scripts.files_generator import FilesGenerator


@pytest.fixture
def sample_module():
    temp_directory = Path(mkdtemp())
    data_directory = Path(os.path.dirname(__file__)) / "data" / "sample_module"
    module_directory = temp_directory / "module"

    # Copy sample files to the test directory
    copytree(data_directory, module_directory)

    yield module_directory

    rmtree(temp_directory.as_posix())


def get_actual_and_expected(sample_module: Path, filename: str):
    expectations = Path(os.path.dirname(__file__)) / "expectations" / "sample_module"

    actual_file = sample_module / filename
    expected_file = expectations / filename

    with actual_file.open() as f:
        actual = f.read()

    with expected_file.open() as f:
        expected = f.read()

    if filename.endswith(".json"):
        actual = json.loads(actual)
        expected = json.loads(expected)

    return actual, expected


def test_files_generator(sample_module):
    # Execute FilesGenerator
    FilesGenerator(sample_module).execute()

    # Verify that the main file was generated
    actual, expected = get_actual_and_expected(sample_module, "main.py")
    assert actual == expected

    # A manifest should have been generated for the trigger
    actual, expected = get_actual_and_expected(
        sample_module, "trigger_sample_trigger.json"
    )
    assert actual == expected

    # A manifest should have been generated for the action
    actual, expected = get_actual_and_expected(
        sample_module, "action_sample_action.json"
    )
    assert actual == expected

    # The module manifest should have been updated
    actual, expected = get_actual_and_expected(sample_module, "manifest.json")
    assert actual == expected
