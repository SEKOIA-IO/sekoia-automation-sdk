from pathlib import Path

import pytest

from sekoia_automation.config import load_config


def test_load_config_file(config_storage: Path):
    config_storage.joinpath("foo").write_text("bar")
    assert load_config("foo") == "bar"


def test_load_config_file_json(config_storage: Path):
    config_storage.joinpath("foo").write_text('{"foo": "bar"}')
    assert load_config("foo", type_="json") == {"foo": "bar"}


def test_load_config_not_found_ok(config_storage: Path):
    assert load_config("foo", non_exist_ok=True) is None


def test_load_config_not_found_error(config_storage: Path):
    with pytest.raises(FileNotFoundError):
        assert load_config("foo")


def test_load_config_env(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert load_config("foo") == "bar"


def test_load_config_env_json(monkeypatch):
    monkeypatch.setenv("FOO", '{"foo": "bar"}')
    assert load_config("foo", type_="json") == {"foo": "bar"}
