import os
from pathlib import Path
from shutil import copytree, rmtree
from tempfile import mkdtemp

import pytest
from sekoia_automation.scripts.check_compliance import CheckCompliance


@pytest.fixture
def sample_module():
    temp_directory = Path(mkdtemp())
    data_directory = Path(os.path.dirname(__file__)) / ".." / "data" / "sample_module"
    module_directory = temp_directory / "automation-library" / "module"

    # Copy sample files to the test directory
    copytree(data_directory, module_directory)

    yield module_directory

    rmtree(temp_directory.as_posix())


def test_compliance(sample_module):
    c = CheckCompliance(path=sample_module)
    c.run()
