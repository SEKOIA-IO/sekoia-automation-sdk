import base64
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

import pytest

from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.filesystem import FileSystemConfiguration


@pytest.fixture
def configuration():
    return FileSystemConfiguration()


@pytest.fixture
def config_storage():
    old_config_storage = FileSystemConfiguration.VOLUME_PATH
    FileSystemConfiguration.VOLUME_PATH = mkdtemp()

    yield Path(FileSystemConfiguration.VOLUME_PATH)

    rmtree(FileSystemConfiguration.VOLUME_PATH)
    FileSystemConfiguration.VOLUME_PATH = old_config_storage


def test_load_config_file(configuration: Configuration, config_storage: Path):
    config_storage.joinpath("foo").write_text("bar")
    assert configuration.load("foo") == "bar"


def test_load_config_file_json(configuration: Configuration, config_storage: Path):
    config_storage.joinpath("foo").write_text('{"foo": "bar"}')
    assert configuration.load("foo", type_="json") == {"foo": "bar"}


def test_load_config_not_found_ok(configuration: Configuration, config_storage: Path):
    assert configuration.load("foo", non_exist_ok=True) is None


def test_load_config_not_found_error(
    configuration: Configuration, config_storage: Path
):
    with pytest.raises(FileNotFoundError):
        assert configuration.load("foo")


def test_load_config_env(configuration: Configuration, monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert configuration.load("foo") == "bar"


def test_load_config_env_json(configuration: Configuration, monkeypatch):
    monkeypatch.setenv("FOO", '{"foo": "bar"}')
    assert configuration.load("foo", type_="json") == {"foo": "bar"}


def test_load_config_env_json_encoded(configuration: Configuration, monkeypatch):
    monkeypatch.setenv("FOO", base64.b64encode(b'{"foo": "bar"}').decode())
    assert configuration.load("foo", type_="json") == {"foo": "bar"}
