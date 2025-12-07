import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest
from sentry_sdk import get_isolation_scope

from sekoia_automation import SekoiaAutomationBaseModel
from sekoia_automation.exceptions import CommandNotFoundError, ModuleConfigurationError
from sekoia_automation.module import Module, ModuleItem
from sekoia_automation.trigger import Trigger
from tests.conftest import DEFAULT_ARGUMENTS


def test_load_config_file_not_exists():
    module = Module()
    with pytest.raises(Exception):
        module.load_config("foo")


def test_load_config_text(mock_volume):
    module = Module()
    assert module.load_config("token") == "token"


def test_load_config_json(mock_volume):
    module = Module()
    assert module.load_config("foo", "json") == DEFAULT_ARGUMENTS


def test_command_no_arg():
    module = Module()
    with patch("sys.argv", []):
        assert module.command is None


def test_command():
    module = Module()
    with patch("sys.argv", ["foo", "bar"]):
        assert module.command == "bar"


@pytest.fixture
def app():
    from flask import Flask

    app = Flask(__name__)
    return app


def test_command_for_fission(app, monkeypatch):
    module = Module()
    # Set SYMPHONY_RUNTIME to "Fission"
    monkeypatch.setenv("SYMPHONY_RUNTIME", "Fission")

    # Use a test request context to simulate a Flask request
    with app.test_request_context("/", headers={"command": "some_command"}):
        assert module.command == "some_command"


def test_no_command():
    module = Module()

    with pytest.raises(CommandNotFoundError):
        module.run()


class DummyTrigger(Trigger):
    def run(self):
        raise NotImplementedError


def test_register_no_command():
    module = Module()

    module.register(DummyTrigger, "some_command")

    with patch("sys.argv", ["run", "other_command"]):
        with pytest.raises(CommandNotFoundError):
            module.run()


def test_register_account_validator():
    module = Module()
    validator = Mock()
    validator.name = None
    module.register_account_validator(validator)
    assert module._items["validate_module_configuration"] == validator


@patch.object(DummyTrigger, "execute")
def test_register_execute_default(mock):
    module = Module()

    module.register(DummyTrigger)

    with patch("sys.argv", ["run"]):
        module.run()
        mock.assert_called_with()


@patch.object(DummyTrigger, "execute")
def test_register_execute_command(mock):
    module = Module()

    module.register(DummyTrigger, "some_command")

    with patch("sys.argv", ["run", "some_command"]):
        module.run()
        mock.assert_called_with()


def test_abstract_module_item():
    class TestItem(ModuleItem):
        def execute(self) -> None:
            raise NotImplementedError

    module = Module()
    module.register(TestItem)

    with patch("sys.argv", ["run"]):
        with pytest.raises(NotImplementedError):
            module.run()


def test_configuration_setter():
    module = Module()

    module.configuration = {"key1": "value1"}
    assert module.configuration == {"key1": "value1"}


def test_configuration_setter_as_model():
    class MyConfiguration(SekoiaAutomationBaseModel):
        number: int = 0

    module = Module()
    module.configuration = MyConfiguration()
    assert module.configuration.number == 0


def test_configuration_as_model():
    class MyConfiguration(SekoiaAutomationBaseModel):
        number: int = 0

    class MyModule(Module):
        configuration: MyConfiguration

    module = MyModule()

    # Default value should be used
    module.configuration = {}
    assert module.configuration.number == 0

    # Provided values should be validated / coerced
    module.configuration = {"number": "42"}
    assert module.configuration.number == 42

    # Validation errors should be raised with bad values
    with pytest.raises(ModuleConfigurationError):
        module.configuration = {"number": "NotANumber"}


def test_module_working_directory():
    module = Module()
    assert module._working_directory == Path(__file__).parent.parent

    module.set_working_directory(Path("/tmp"))
    assert module._working_directory == Path("/tmp")


def test_module_manifest_loading():
    module = Module()
    manifest_content = {
        "name": "Test Module",
        "version": "1.0.0",
        "description": "A test module",
        "properties": {"foo": {"type": "string", "description": "A foo property"}},
        "secrets": ["foo"],
    }

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        manifest_path = temp_path / "manifest.json"
        with manifest_path.open("w") as f:
            json.dump(manifest_content, f)

        module.set_working_directory(temp_path)
        assert module.manifest == manifest_content


def test_configuration_setter_add_secret_not_required():
    module = Module()
    secret_name = "foo"
    secret_val = "bar"

    with (
        patch.object(
            Module,
            "manifest_properties",
            return_value=[secret_name],
        ),
        patch.object(
            Module,
            "manifest_required_properties",
            return_value=[],
        ),
    ):
        module.configuration = {secret_name: secret_val}
        assert module.configuration == {secret_name: secret_val}


def test_configuration_setter_add_secret_required():
    module = Module()
    secret_name = "foo"
    secret_val = "bar"

    with (
        patch.object(
            Module,
            "manifest_properties",
            return_value=[secret_name],
        ),
        patch.object(
            Module,
            "manifest_required_properties",
            return_value=[secret_name],
        ),
    ):
        module.configuration = {secret_name: secret_val}
        assert module.configuration == {secret_name: secret_val}


def test_configuration_setter_missing_required_secret():
    module = Module()
    secret_name = "foo"

    with (
        patch.object(
            Module,
            "manifest_properties",
            return_value=[secret_name],
        ),
        patch.object(
            Module,
            "manifest_required_properties",
            return_value=[secret_name],
        ),
    ):
        with pytest.raises(expected_exception=ModuleConfigurationError):
            module.configuration = {"not a secret": "some value"}
            assert module.configuration == {secret_name: "some other value"}


def test_playbook_uuid():
    module = Module()
    with patch.object(
        module, "load_config", return_value="5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
    ):
        assert module.playbook_uuid == "5e57c739-391a-4eb3-b6be-7d15ca92d5ed"


def test_playbook_run_uuid():
    module = Module()
    with patch.object(
        module, "load_config", return_value="5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
    ):
        assert module.playbook_run_uuid == "5e57c739-391a-4eb3-b6be-7d15ca92d5ed"


def test_node_run_uuid():
    module = Module()
    with patch.object(
        module, "load_config", return_value="5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
    ):
        assert module.node_run_uuid == "5e57c739-391a-4eb3-b6be-7d15ca92d5ed"


def test_trigger_configuration_uuid():
    module = Module()
    with patch.object(
        module, "load_config", return_value="5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
    ):
        assert (
            module.trigger_configuration_uuid == "5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
        )


def test_connector_configuration_uuid():
    module = Module()
    with patch.object(
        module, "load_config", return_value="5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
    ):
        assert (
            module.connector_configuration_uuid
            == "5e57c739-391a-4eb3-b6be-7d15ca92d5ed"
        )


def test_init_sentry():
    module = Module()
    module._community_uuid = "community"
    module._playbook_uuid = "playbook"
    module._playbook_run_uuid = "playbook_run"
    module._node_run_uuid = "node_run"
    module._trigger_configuration_uuid = "trigger_configuration"
    module._connector_configuration_uuid = "connector_configuration"

    with patch.object(
        module, "_load_sentry_dsn", return_value="http://1234@localhost/1234"
    ):
        module.init_sentry()
        tags = get_isolation_scope()._tags
        assert tags["community"] == "community"
        assert tags["playbook_uuid"] == "playbook"
        assert tags["playbook_run_uuid"] == "playbook_run"
        assert tags["trigger_configuration_uuid"] == "trigger_configuration"
        assert tags["connector_configuration_uuid"] == "connector_configuration"
