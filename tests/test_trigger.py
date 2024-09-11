import datetime
import time
from datetime import timedelta
from pathlib import Path
from typing import ClassVar
from unittest.mock import PropertyMock, mock_open, patch

# third parties
import pytest
import requests
import requests_mock
from botocore.exceptions import ClientError, ConnectionError
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
from tests.data.sample_module.sample import SampleModule


class DummyTrigger(Trigger):
    event: ClassVar[dict] = {}

    def run(self):
        self.send_event("test", self.event)


class ErrorTrigger(Trigger):
    ex = Exception()

    def run(self):
        raise self.ex


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


def test_secrets_url():
    trigger = DummyTrigger()
    with patch.object(Module, "load_config", return_value="secrets") as mock:
        assert trigger.secrets_url == "secrets"
    mock.assert_called_with(trigger.SECRETS_URL_FILE_NAME)


def test_intake_url():
    trigger = DummyTrigger()
    with patch.object(Module, "load_config", return_value="intake") as mock:
        assert trigger.intake_url == "intake"
    mock.assert_called_with(trigger.INTAKE_URL_FILE_NAME)


def test_logs_url():
    trigger = DummyTrigger()
    with patch.object(Module, "load_config", return_value="logs") as mock:
        assert trigger.logs_url == "logs"
    mock.assert_called_with(trigger.LOGS_URL_FILE_NAME)


def test_trigger_configuration():
    trigger = DummyTrigger()
    with (
        patch.object(Module, "load_config", return_value="trigger_conf") as mock,
        patch("sentry_sdk.set_context") as sentry_patch,
    ):
        assert trigger.configuration == "trigger_conf"
        sentry_patch.assert_called_with("trigger_configuration", "trigger_conf")
    mock.assert_called_with(trigger.TRIGGER_CONFIGURATION_FILE_NAME, "json")


def test_module_configuration():
    trigger = DummyTrigger()
    module_conf = {"conf_key": "conf_val"}
    with (
        patch.object(Module, "load_config", return_value=module_conf) as mock,
        patch("sentry_sdk.set_context") as sentry_patch,
    ):
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
    trigger._wait_exponent_base = 0

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

    with patch("sentry_sdk.capture_exception") as sentry_patch:
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
    with (
        requests_mock.Mocker() as rmock,
        patch.object(Path, "is_file", return_value=True),
        patch.object(Path, "open", mock),
    ):
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
    trigger.LOGS_MAX_BATCH_SIZE = 0

    assert mocked_trigger_logs.call_count == 0

    trigger.log("test message", "info")
    assert mocked_trigger_logs.call_count == 1
    log_request = mocked_trigger_logs.last_request.json()["logs"][0]
    assert log_request["date"] is not None
    assert log_request["level"] == "info"
    assert log_request["message"] == "test message"


def test_trigger_log_severity(mocked_trigger_logs):
    trigger = DummyTrigger()

    assert mocked_trigger_logs.call_count == 0

    trigger.log("test message", "info")
    assert mocked_trigger_logs.call_count == 0
    trigger.log("error message", "error")
    assert mocked_trigger_logs.call_count == 1

    log = mocked_trigger_logs.last_request.json()["logs"][0]
    assert log["date"] is not None
    assert log["level"] == "info"
    assert log["message"] == "test message"

    log = mocked_trigger_logs.last_request.json()["logs"][1]
    assert log["level"] == "error"


def test_trigger_log_batch_full(mocked_trigger_logs):
    trigger = DummyTrigger()

    for _ in range(trigger.LOGS_MAX_BATCH_SIZE):
        assert mocked_trigger_logs.call_count == 0
        trigger.log("test message", "info")

    assert mocked_trigger_logs.call_count == 1
    logs = mocked_trigger_logs.last_request.json()["logs"]
    assert len(logs) == trigger.LOGS_MAX_BATCH_SIZE


def test_trigger_log_time_elapsed(mocked_trigger_logs):
    DummyTrigger.LOGS_MAX_DELTA = 0.01
    trigger = DummyTrigger()
    trigger._logs_timer.start()

    trigger.log("test message", "info")
    try:
        assert mocked_trigger_logs.call_count == 0
        time.sleep(trigger.LOGS_MAX_DELTA * 1.5)
        assert mocked_trigger_logs.call_count == 1

        logs = mocked_trigger_logs.last_request.json()["logs"]
        assert len(logs) == 1
    finally:
        trigger.stop()


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
    trigger._send_logs_to_api.retry.wait = wait_none()
    trigger.log("test message", "error")

    assert mocked_trigger_logs.call_count == 2


@patch.object(Trigger, "_get_secrets_from_server")
def test_configuration_errors_are_critical(_, mocked_trigger_logs):
    class TestTrigger(Trigger):
        raised = False

        def run(self):
            if self.raised:
                raise SystemExit
            else:
                self.raised = True
                raise TriggerConfigurationError

    trigger = TestTrigger()
    trigger._STOP_EVENT_WAIT = 0.001
    with (
        pytest.raises(SystemExit),
        patch.object(Module, "load_config", return_value={}),
    ):
        trigger.execute()

    # configuration errors are directly considered to be critical
    assert mocked_trigger_logs.call_count == 2
    assert mocked_trigger_logs.request_history[0].json()["logs"][0]["level"] == "error"
    assert (
        mocked_trigger_logs.request_history[1].json()["logs"][0]["level"] == "critical"
    )
    trigger.stop()


@patch.object(Trigger, "_get_secrets_from_server")
def test_too_many_errors_critical_log(_, mocked_trigger_logs):
    class TestTrigger(Trigger):
        raised = False

        def run(self):
            if self.raised:
                raise SystemExit
            else:
                self.raised = True
                raise ValueError

    trigger = TestTrigger()
    trigger._error_count = 4
    trigger._startup_time = datetime.datetime.utcnow() - timedelta(hours=1)
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=5)
    trigger._STOP_EVENT_WAIT = 0.001
    with (
        pytest.raises(SystemExit),
        patch.object(Module, "load_config", return_value={}),
    ):
        trigger.execute()

    # 5th error triggers a critical log
    assert mocked_trigger_logs.call_count == 2
    assert mocked_trigger_logs.request_history[0].json()["logs"][0]["level"] == "error"
    assert (
        mocked_trigger_logs.request_history[1].json()["logs"][0]["level"] == "critical"
    )
    trigger.stop()


def test_trigger_log_critical_only_once(mocked_trigger_logs):
    trigger = DummyTrigger()
    # Make sure we are retrying log registrations
    assert mocked_trigger_logs.call_count == 0
    trigger.log("test message", "critical")
    trigger.log("test message", "critical")
    assert mocked_trigger_logs.call_count == 2
    assert (
        mocked_trigger_logs.request_history[0].json()["logs"][0]["level"] == "critical"
    )
    assert mocked_trigger_logs.request_history[1].json()["logs"][0]["level"] == "error"


@patch.object(Module, "has_secrets", return_value=True)
@patch.object(
    Trigger,
    "secrets_url",
    new_callable=PropertyMock,
    return_value="http://sekoia-playbooks/secrets",
)
@patch.object(Trigger, "token", return_value="secure_token")
def test_get_secrets(_, __, ___):
    trigger = ErrorTrigger(SampleModule())
    trigger.ex = SystemExit

    with (
        requests_mock.Mocker() as rmock,
        patch.object(
            Module,
            "load_config",
            return_value={
                "module_field": "foo",
                "api_key": "encrypted",
                "password": "secret",
            },
        ),
    ):
        rmock.get("http://sekoia-playbooks/secrets", json={"value": TRIGGER_SECRETS})

        with pytest.raises(SystemExit):
            trigger.execute()

        assert rmock.call_count == 1
        assert trigger._secrets == TRIGGER_SECRETS
        trigger.stop()


@pytest.fixture()
def monitored_trigger():
    trigger = DummyTrigger()
    trigger.start_monitoring()
    try:
        yield trigger
    finally:
        trigger.stop_monitoring()


def test_trigger_liveness(monitored_trigger):
    res = requests.get("http://127.0.0.1:8000/health")
    assert res.status_code == 200


def test_trigger_liveness_error(monitored_trigger, mocked_trigger_logs):
    monitored_trigger.seconds_without_events = 1
    monitored_trigger._last_events_time = (
        datetime.datetime.utcnow() - datetime.timedelta(seconds=60)
    )
    mocked_trigger_logs.register_uri(
        "GET", "http://127.0.0.1:8000/health", real_http=True
    )
    res = requests.get("http://127.0.0.1:8000/health")
    assert res.status_code == 500
    data = res.json()
    assert data["seconds_without_events_threshold"] == 1
    assert data["last_events_time"] is not None
    assert data["error_count"] is not None


def test_trigger_liveness_heartbeat_error(monitored_trigger, mocked_trigger_logs):
    monitored_trigger.last_heartbeat_threshold = 1
    monitored_trigger._last_heartbeat = datetime.datetime.utcnow() - datetime.timedelta(
        seconds=60
    )
    mocked_trigger_logs.register_uri(
        "GET", "http://127.0.0.1:8000/health", real_http=True
    )
    res = requests.get("http://127.0.0.1:8000/health")
    assert res.status_code == 500
    data = res.json()
    assert data["last_heartbeat_threshold"] == 1
    assert data["last_heartbeat"] is not None
    assert data["error_count"] is not None


def test_trigger_liveness_not_found(monitored_trigger):
    res = requests.get("http://127.0.0.1:8000/wrong")
    assert res.status_code == 404


def test_trigger_s3_connection_error(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = ConnectionError(error="Err")

    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
    assert trigger._error_count == 0


def test_trigger_s3_server_error_int(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = ClientError({"Error": {"Code": 500}}, "foo")
    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
    assert trigger._error_count == 0


def test_trigger_s3_server_error_str(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = ClientError({"Error": {"Code": "ServiceUnavailable"}}, "foo")
    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
    assert trigger._error_count == 0


def test_trigger_s3_client_error_int(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = ClientError({"Error": {"Code": 400}}, "foo")
    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
        assert mocked_trigger_logs.call_count == 1
    assert trigger._error_count == 1


def test_trigger_s3_client_error_str(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = ClientError({"Error": {"Code": "NoSuchBucket"}}, "foo")
    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
    assert trigger._error_count == 1


def test_trigger_send_server_error(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = SendEventError("Server error", 500)
    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
    assert trigger._error_count == 0


def test_trigger_send_client_error(mocked_trigger_logs):
    trigger = ErrorTrigger()
    trigger.ex = SendEventError("Client error", 400)
    with patch("sentry_sdk.capture_exception") as sentry_patch:
        trigger._execute_once()
        sentry_patch.assert_called()
        assert mocked_trigger_logs.called is True
    assert trigger._error_count == 1


def test_is_error_critical_errors():
    trigger = DummyTrigger()
    assert trigger._is_error_critical() is False
    trigger._error_count = 5
    assert trigger._is_error_critical() is False
    trigger._startup_time = datetime.datetime.utcnow() - timedelta(hours=1)
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=9)
    assert trigger._is_error_critical() is True


def test_is_error_critical_time_since_last_event():
    trigger = DummyTrigger()
    trigger._error_count = 5

    # Trigger that has been running for a long time
    trigger._startup_time = datetime.datetime(year=2021, month=1, day=1)
    assert trigger._is_error_critical() is False
    # Time without events is capped to 24 hours
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=23)
    assert trigger._is_error_critical() is False
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=24)
    assert trigger._is_error_critical() is True

    # Trigger that just started and already has 5 errors without sending any event
    trigger = DummyTrigger()
    trigger._error_count = 5
    assert trigger._is_error_critical() is False
    trigger._startup_time = datetime.datetime.utcnow() - timedelta(hours=1)
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=5)
    assert trigger._is_error_critical() is True

    # Trigger that has been running for 1 day should exit after 5 hours of errors
    trigger._last_events_time = datetime.datetime.utcnow()
    trigger._startup_time = datetime.datetime.utcnow() - timedelta(days=1)
    assert trigger._is_error_critical() is False
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=1)
    assert trigger._is_error_critical() is False
    trigger._last_events_time = datetime.datetime.utcnow() - timedelta(hours=5)
    assert trigger._is_error_critical() is True
