# natives
from unittest.mock import patch

# third parties
import pytest
from pydantic import BaseModel

# internal
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
    class MyConfiguration(BaseModel):
        number: int = 0

    module = Module()
    module.configuration = MyConfiguration()
    assert module.configuration.number == 0


def test_configuration_as_model():
    class MyConfiguration(BaseModel):
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


def test_configuration_setter_add_secret_not_required():
    module = Module()
    secret_name = "foo"
    secret_val = "bar"

    with patch.object(
        Module,
        "manifest_properties",
        return_value=[secret_name],
    ), patch.object(
        Module,
        "manifest_required_properties",
        return_value=[],
    ):
        module.configuration = {secret_name: secret_val}
        assert module.configuration == {secret_name: secret_val}


def test_configuration_setter_add_secret_required():
    module = Module()
    secret_name = "foo"
    secret_val = "bar"

    with patch.object(
        Module,
        "manifest_properties",
        return_value=[secret_name],
    ), patch.object(
        Module,
        "manifest_required_properties",
        return_value=[secret_name],
    ):
        module.configuration = {secret_name: secret_val}
        assert module.configuration == {secret_name: secret_val}


def test_configuration_setter_missing_required_secret():
    module = Module()
    secret_name = "foo"

    with patch.object(
        Module,
        "manifest_properties",
        return_value=[secret_name],
    ), patch.object(
        Module,
        "manifest_required_properties",
        return_value=[secret_name],
    ):
        with pytest.raises(expected_exception=ModuleConfigurationError):
            module.configuration = {"not a secret": "some value"}
            assert module.configuration == {secret_name: "some other value"}
