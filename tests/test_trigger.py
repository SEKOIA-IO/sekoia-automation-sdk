from pathlib import Path
from unittest.mock import PropertyMock, mock_open, patch

# third parties
import pytest
import requests_mock
from pydantic import BaseModel
from tenacity import wait_none

from sekoia_automation.exceptions import (
    InvalidDirectoryError,
    SendEventError,
    TriggerConfigurationError,
)

# internal
from sekoia_automation.module import Module
from sekoia_automation.trigger import Trigger
from tests.conftest import TRIGGER_SECRETS


class DummyTrigger(Trigger):
    event: dict = {}

    def run(self):
        self.send_event("test", self.event)


def test_token():
    trigger = DummyTrigger()
    with patch.object(Module, "load_config", return_value="token") as mock:
        assert trigger.token == "token"
    mock.assert_called_with(trigger.TOKEN_FILE_NAME)


def test_callback_url():
    trigger = DummyTrigger()
    with patch.object(Module, "load_config", return_value="callback") as mock:
        assert trigger.callback_url == "callback"
    mock.assert_called_with(trigger.CALLBACK_URL_FILE_NAME)


def test_trigger_configuration():
    trigger = DummyTrigger()
    with patch.object(
        Module, "load_config", return_value="trigger_conf"
    ) as mock, patch("sentry_sdk.set_context") as sentry_patch:
        assert trigger.configuration == "trigger_conf"
        sentry_patch.assert_called_with("trigger_configuration", "trigger_conf")
    mock.assert_called_with(trigger.TRIGGER_CONFIGURATION_FILE_NAME, "json")


def test_module_configuration():
    trigger = DummyTrigger()
    module_conf = {"conf_key": "conf_val"}
    with patch.object(Module, "load_config", return_value=module_conf) as mock, patch(
        "sentry_sdk.set_context"
    ) as sentry_patch:
        assert trigger.module.configuration == module_conf
        sentry_patch.assert_called_with("module_configuration", module_conf)
    mock.assert_called_with(Module.MODULE_CONFIGURATION_FILE_NAME, "json")


def test_module_community_uuid():
    trigger = DummyTrigger()
    with patch.object(Module, "load_config", return_value="some_uuid") as mock:
        assert trigger.module.community_uuid == "some_uuid"
    mock.assert_called_with(Module.COMMUNITY_UUID_FILE_NAME, non_exist_ok=True)


def test_send_event(mocked_trigger_logs):
    trigger = DummyTrigger()

    mocked_trigger_logs.post("http://sekoia-playbooks/callback")
    trigger.send_event("my_event", {"foo": "bar"})


def test_send_event_4xx_error(mocked_trigger_logs):
    trigger = DummyTrigger()

    mocked_trigger_logs.post(
        "http://sekoia-playbooks/callback",
        status_code=401,
        json={"error": "Unauthorized"},
    )
    with pytest.raises(SendEventError):
        trigger.send_event("my_event", {"foo": "bar"})


def test_send_event_too_many_failures(mocked_trigger_logs):
    trigger = DummyTrigger()

    mocked_trigger_logs.post(
        "http://sekoia-playbooks/callback",
        status_code=500,
        json={"error": "Unauthorized"},
    )
    with pytest.raises(SendEventError):
        trigger.send_event("my_event", {"foo": "bar"})


def test_trigger_execute(mocked_trigger_logs):
    class TestTrigger(Trigger):
        def run(self):
            raise NotImplementedError

    trigger = TestTrigger()

    with patch("sentry_sdk.capture_message") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()

    with patch.object(Trigger, "send_event") as mock:
        DummyTrigger()._execute_once()
        mock.assert_called_with("test", {})


def test_trigger_configuration_setter():
    trigger = DummyTrigger()

    trigger.configuration = {"key1": "value1"}
    assert trigger.configuration == {"key1": "value1"}


def test_trigger_stop():
    trigger = DummyTrigger()
    assert trigger.running is True

    trigger.stop()
    assert trigger.running is False


def send_event_with_mock(
    name, event, directory, remove_directory=False, data_path=None
):
    trigger = DummyTrigger(data_path=data_path)

    mock = mock_open(read_data="token")
    mock_2 = mock_open(read_data="http://sekoia-playbooksapi/endpoint")
    mock.side_effect = [
        mock.return_value,
        mock_2.return_value,
    ]  # First call token and second url
    with requests_mock.Mocker() as rmock, patch.object(
        Path, "is_file", return_value=True
    ), patch.object(Path, "open", mock):
        rmock.post("http://sekoia-playbooksapi/endpoint")
        trigger.send_event(name, event, directory, remove_directory)

    return rmock


def test_trigger_directory_does_not_exist():
    with pytest.raises(InvalidDirectoryError):
        send_event_with_mock("test", {}, "directory")


def test_trigger_directory(storage, mocked_trigger_logs):
    trigger = DummyTrigger(data_path=storage)

    mocked_trigger_logs.post("http://sekoia-playbooks/callback")

    # Create a directory with some content
    dirpath = storage / "test_dir"
    dirpath.mkdir(parents=True)
    (dirpath / "test.txt").touch()

    # Send an event with an absolute path
    trigger.send_event("test", {}, dirpath)
    assert mocked_trigger_logs.last_request.json()["directory"] == "test_dir"

    # Send an event with a relative path
    trigger.send_event("test", {}, "test_dir")
    assert mocked_trigger_logs.last_request.json()["directory"] == "test_dir"

    # Make sure the directory still exists
    assert dirpath.exists()

    # Send an event with remove_directory set to True
    trigger.send_event("test", {}, "test_dir", remove_directory=True)
    assert mocked_trigger_logs.last_request.json()["directory"] == "test_dir"

    # Make sure the directory was deleted
    assert not dirpath.exists()


def test_trigger_event_normalization(mocked_trigger_logs):
    class TestResults(BaseModel):
        field: str = "value"
        number: int = 0

    class TestTrigger(DummyTrigger):
        results_model = TestResults

    trigger = TestTrigger()

    with patch.object(trigger, "send_normalized_event") as send_normalized_event:
        # An empty event should use the default value
        trigger._execute_once()
        send_normalized_event.assert_called_with(
            "test", {"field": "value", "number": 0}, None, False
        )

        # The event value should be validated / coerced
        trigger.event = {"field": 42}
        trigger._execute_once()
        send_normalized_event.assert_called_with(
            "test", {"field": "42", "number": 0}, None, False
        )

        # Validation Errors should be raised when the event is wrong
        trigger.event = {"number": "NotANumber"}
        trigger._execute_once()

        log_request = mocked_trigger_logs.last_request.json()["logs"][0]
        assert log_request["level"] == "error"
        assert "not a valid integer" in log_request["message"]


def test_trigger_configuration_as_model():
    class TestConfiguration(BaseModel):
        number: int = 0

    class TestTrigger(DummyTrigger):
        configuration: TestConfiguration

    trigger = TestTrigger()

    # An empty configuration should use default values
    trigger.configuration = {}
    assert trigger.configuration.number == 0

    # The specified value should be validated / coerced
    trigger.configuration = {"number": "4"}
    assert trigger.configuration.number == 4

    # Validation errors should be raised if there is an issue with the configuration
    with pytest.raises(TriggerConfigurationError):
        trigger.configuration = {"number": "NotANumber"}


def test_trigger_log(mocked_trigger_logs):
    trigger = DummyTrigger()

    assert mocked_trigger_logs.call_count == 0

    trigger.log("test message", "info")
    assert mocked_trigger_logs.call_count == 1
    log_request = mocked_trigger_logs.last_request.json()["logs"][0]
    assert log_request["date"] is not None
    assert log_request["level"] == "info"
    assert log_request["message"] == "test message"


def test_trigger_log_critical(mocked_trigger_logs):
    trigger = DummyTrigger()

    assert mocked_trigger_logs.call_count == 0

    # A critical error should exit the process
    with pytest.raises(SystemExit):
        trigger.log("test message", "critical")

    # But still be recoreded
    assert mocked_trigger_logs.call_count == 1


def test_trigger_log_retry(mocked_trigger_logs):
    trigger = DummyTrigger()

    # Simulate an error followed by a success
    mocked_trigger_logs.register_uri(
        "POST",
        "http://sekoia-playbooks/logs",
        [{"status_code": 503}, {"status_code": 200}],
    )

    # Make sure we are retrying log registrations
    assert mocked_trigger_logs.call_count == 0
    trigger.log.retry.wait = wait_none()
    trigger.log("test message", "error")

    assert mocked_trigger_logs.call_count == 2


@patch.object(Trigger, "_get_secrets_from_server")
def test_execute_logs_errors(_, mocked_trigger_logs):
    class TestTrigger(Trigger):
        def run(self):
            raise NotImplementedError

    trigger = TestTrigger()
    with pytest.raises(SystemExit):
        trigger.execute()

    # 5 errors should have been logger, the last one being considered critical
    assert mocked_trigger_logs.call_count == 5


@patch.object(Trigger, "_get_secrets_from_server")
def test_configuration_errors_are_critical(_, mocked_trigger_logs):
    class TestTrigger(Trigger):
        def run(self):
            raise TriggerConfigurationError

    trigger = TestTrigger()

    with pytest.raises(SystemExit):
        trigger.execute()

    # configuration errors are directly considered to be critical
    assert mocked_trigger_logs.call_count == 1


@patch.object(Module, "has_secrets", return_value=True)
@patch.object(
    Trigger,
    "callback_url",
    new_callable=PropertyMock,
    return_value="http://sekoia-playbooks/callback",
)
@patch.object(Trigger, "token", return_value="secure_token")
def test_get_secrets(_, __, ___):
    class TestGetSecretsTrigger(Trigger):
        def run(self):
            self._error_count = 5

    trigger = TestGetSecretsTrigger()

    with requests_mock.Mocker() as rmock:
        rmock.get("http://sekoia-playbooks/secrets", json={"value": TRIGGER_SECRETS})

        trigger.execute()

        assert rmock.call_count == 1
        assert trigger._secrets == TRIGGER_SECRETS
