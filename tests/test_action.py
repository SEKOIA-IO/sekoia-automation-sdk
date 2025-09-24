# natives
import json
import logging
from unittest.mock import Mock, PropertyMock, patch

import pytest
import requests_mock
from pydantic.v1 import BaseModel, ValidationError

# third parties
from requests import Timeout
from tenacity import wait_none

# internal
from sekoia_automation.action import Action, GenericAPIAction
from sekoia_automation.exceptions import MissingActionArgumentError, SendEventError
from sekoia_automation.module import Module
from tests.conftest import DEFAULT_ARGUMENTS, FAKE_URL, MANIFEST_WITH_SECRETS


class DummyAction(Action):
    def run(self, arguments):
        return {}


def test_action_logs(capsys):
    action = DummyAction()

    action.log("message1")
    action.log("message2", level="info")
    action.log("message3", level="warning")
    action.log("message4", level="error")
    logging.warning("message5")

    # Make sure nothing was printed on stdout
    assert capsys.readouterr().out == ""

    assert action.logs[0]["level"] == "debug"
    assert action.logs[1]["level"] == "info"
    assert action.logs[2]["level"] == "warning"
    assert action.logs[3]["level"] == "error"
    assert action.logs[0]["message"] == "message1"
    assert action.logs[1]["message"] == "message2"
    assert action.logs[2]["message"] == "message3"
    assert action.logs[3]["message"] == "message4"


def test_action_outputs():
    action = DummyAction()

    action.set_output("output1")
    action.set_output("output2", True)
    action.set_output("output3", False)

    assert action.outputs == {"output1": True, "output2": True, "output3": False}


def test_action_error():
    action = DummyAction()

    action.error("error message")

    assert action.error_message == "error message"
    assert action.results is None


def test_action_results_with_secrets_update(mock_volume):
    data = {"key1": "value1", "key2": "value2"}
    secret = {"a_key": "a_secret"}

    class SimpleAction(Action):
        def run(self, arguments):
            self._update_secrets = True
            return data

    action = SimpleAction()
    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL, json={"module_configuration": {"value": secret}})

        with (
            patch.object(Module, "manifest_secrets", return_value=["a_key"]),
            patch.object(Module, "manifest_required_properties", return_value=[]),
            patch.object(Module, "has_secrets", return_value=True),
        ):
            action.execute()

        assert action.results == data
        assert rmock.call_count == 2
        assert rmock.request_history[0].json() == {
            "status": "running",
            "need_secrets": True,
        }
        assert rmock.last_request.json() == {
            "results": data,
            "status": "finished",
            "secrets": {"a_key": "a_secret"},
        }


def test_action_execute_with_get_secrets(mock_volume):
    class TestAction(Action):
        def run(self, arguments):
            assert arguments == DEFAULT_ARGUMENTS
            return {}

    action = TestAction()
    action.module._manifest = MANIFEST_WITH_SECRETS

    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL, json={"module_configuration": {"value": {"foo": "bar"}}})

        action.execute()

        assert rmock.call_count == 2
        assert rmock.request_history[0].json() == {
            "status": "running",
            "need_secrets": True,
        }
        assert rmock.last_request.json() == {"results": {}, "status": "finished"}


def test_exception_handler(mock_volume):
    class TestAction(Action):
        def run(self, arguments):
            raise NotImplementedError

    with (
        requests_mock.Mocker() as rmock,
        patch("sentry_sdk.capture_exception") as sentry_patch,
    ):
        rmock.patch(FAKE_URL)

        action = TestAction()
        action.execute()

        assert rmock.call_count == 2
        assert rmock.request_history[0].json() == {"status": "running"}
        assert "NotImplementedError" in rmock.last_request.json()["error"]
        sentry_patch.assert_called()


def test_all(mock_volume):
    class PrintAction(Action):
        def run(self, arguments):
            self.log("message", "info", status=401)
            self.set_output("malicious")

            return {"key1": "value1"}

    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL)

        action = PrintAction()
        action.execute()

        assert rmock.call_count == 2
        assert rmock.request_history[0].json() == {"status": "running"}

        results = rmock.last_request.json()
        assert "info: message" in results["logs"]
        assert '- Context: {"status": 401}' in results["logs"]
        assert results["outputs"] == {"malicious": True}
        assert results["results"] == {"key1": "value1"}


def test_validate_results_none():
    action = DummyAction()
    action.validate_results()

    assert action.results is None
    assert action.error_message is None


def test_validate_list_results(mock_volume):
    class ListAction(Action):
        def run(self, arguments):
            return [{"key1": "value1"}, {"key2": "value2"}]

    action = ListAction()

    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL)

        action.execute()

        assert rmock.last_request.json()["results"] == [
            {"key1": "value1"},
            {"key2": "value2"},
        ]


def test_action_results_invalid(mock_volume):
    class TestAction(Action):
        def run(self, arguments):
            assert arguments == DEFAULT_ARGUMENTS
            return "wrong"

    action = TestAction()

    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL)

        action.execute()

        assert rmock.call_count == 2
        assert rmock.request_history[0].json() == {"status": "running"}
        assert rmock.last_request.json() == {
            "error": "Results are invalid: 'wrong'",
            "status": "finished",
        }


def test_action_json_argument(storage):
    action = DummyAction(data_path=storage)

    # Pass the value directly as argument
    assert action.json_argument("test", {"test": "value"}) == "value"

    # Pass the value as a file
    with storage.joinpath("test.txt").open("w") as out:
        out.write('"value"')

    assert action.json_argument("test", {"test_path": "test.txt"}) == "value"


def test_action_json_argument_missing():
    action = DummyAction()

    # If the argument is not present, it should raise an exception
    with pytest.raises(MissingActionArgumentError):
        action.json_argument("test", {})

    # Except if required is set to False
    assert action.json_argument("test", {}, required=False) is None


def test_action_json_result(storage):
    action = DummyAction(data_path=storage)

    # By default, it should return the result inside a file
    result = action.json_result("test", {"key": "value"})
    assert "test_path" in result
    filepath = storage.joinpath(result["test_path"])
    assert filepath.is_file()
    with filepath.open("r") as f:
        assert json.load(f) == {"key": "value"}


def test_action_json_result_same_as_argument():
    action = DummyAction()

    # When fetching a JSON Argument, the result should use the same mode
    action.json_argument("test", {"test": "value"})

    assert action.json_result("test", {"key": "value"}) == {"test": {"key": "value"}}


def test_generic_api_action(storage):
    def init_action(verb: str = "get"):
        action = GenericAPIAction(data_path=storage)
        action.verb = verb
        action.endpoint = "resource/{uuid}/count"
        action.query_parameters = ["param"]
        action.module.configuration = {"base_url": "http://base_url/"}
        action._wait_param = lambda: wait_none()
        return action

    # success
    action = init_action()
    expected_response = {"count": 10}
    arguments = {"uuid": "fake_uuid"}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/fake_uuid/count", json=expected_response)

        results: dict = action.run(arguments)

        assert results == expected_response
        assert mock.call_count == 1
        history = mock.request_history
        assert history[0].method == "GET"
        assert history[0].url == "http://base_url/resource/fake_uuid/count"

    # success
    action = init_action()
    arguments = {"uuid": "fake_uuid", "param": "number"}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/fake_uuid/count", json=expected_response)

        results: dict = action.run(arguments)

        assert results == expected_response
        assert mock.call_count == 1
        history = mock.request_history
        assert history[0].method == "GET"
        assert history[0].url == "http://base_url/resource/fake_uuid/count?param=number"

    # success with no content
    action = init_action()
    arguments = {"uuid": "fake_uuid", "param": "number"}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/fake_uuid/count", status_code=204)

        results: dict = action.run(arguments)

        assert results is None
        assert mock.call_count == 1
        history = mock.request_history
        assert history[0].method == "GET"
        assert history[0].url == "http://base_url/resource/fake_uuid/count?param=number"

    # error on action.run
    action = init_action()
    with requests_mock.Mocker() as mock:
        pytest.raises(KeyError, action.run, {})

        assert mock.call_count == 0

    # timeout on request then success
    action = init_action()
    arguments = {"uuid": "fake_uuid", "param": "number"}
    with patch("requests.request") as mock:
        mock.side_effect = [Timeout, Mock(json=Mock(return_value=expected_response))]
        results: dict = action.run(arguments)

        assert results == expected_response
        assert mock.call_count == 2
        mock.assert_called_with(
            "get",
            "http://base_url/resource/fake_uuid/count",
            json=arguments,
            headers={"Accept": "application/json"},
            timeout=5,
            params={"param": "number"},
        )

    # error http code
    action = init_action()
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/fake_uuid/count", status_code=500, json={})
        results: dict = action.run({"uuid": "fake_uuid", "param": "number"})

        assert results is None
        assert mock.call_count == 10

    action = init_action()
    with requests_mock.Mocker() as mock:
        mock.get(
            "http://base_url/resource/fake_uuid/count",
            status_code=400,
            json={"message": "Oops"},
        )
        results: dict = action.run({"uuid": "fake_uuid", "param": "number"})

        assert results is None
        assert mock.call_count == 1
        assert action._error == "Oops"

    action = init_action(verb="delete")
    with requests_mock.Mocker() as mock:
        mock.delete(
            "http://base_url/resource/fake_uuid/count",
            [{"status_code": 503}, {"status_code": 404}],
        )
        results: dict = action.run({"uuid": "fake_uuid", "param": "number"})

        assert results is None
        assert mock.call_count == 2

    # timeout
    action = init_action()
    arguments = {"uuid": "fake_uuid", "param": "number"}
    with patch("requests.request") as mock:
        mock.side_effect = Timeout
        results: dict = action.run(arguments)

        assert results is None
        assert mock.call_count == 10

    # Makes sure `*_path` have been recursively replaced
    action = init_action()
    filepath = storage / "foo.txt"
    with filepath.open("w") as fp:
        fp.write('{"foo": "bar"}')
    arguments = {"uuid": "fake_uuid", "other": {"sub_path": "foo.txt"}}
    expected = {"other": {"sub": {"foo": "bar"}}}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/fake_uuid/count", json=expected_response)

        results: dict = action.run(arguments)

        assert results == expected_response
        assert mock.call_count == 1
        history = mock.request_history
        assert history[0].method == "GET"
        assert history[0].url == "http://base_url/resource/fake_uuid/count"
        assert history[0].json() == expected

    # path argument should allow non-string parameters
    action = init_action()
    arguments = {"uuid": 10}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/10/count", json=expected_response)

        results: dict = action.run(arguments)

        assert results == expected_response
        assert mock.call_count == 1
        history = mock.request_history
        assert history[0].method == "GET"
        assert history[0].url == "http://base_url/resource/10/count"

    # Basic auth
    action = init_action()
    action.authentication = "baSic"
    action.module.configuration["username"] = "user"
    action.module.configuration["password"] = "pass"
    arguments = {"uuid": 10}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/10/count", json=expected_response)
        action.run(arguments)
        assert mock.request_history[0].headers["Authorization"] == "Basic dXNlcjpwYXNz"

    # API Key
    action = init_action()
    action.authentication = "aPiKey"
    action.auth_header = "X-API-Key"
    action.module.configuration["api_key"] = "api_key"
    arguments = {"uuid": 10}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/10/count", json=expected_response)
        action.run(arguments)
        assert mock.request_history[0].headers["X-API-Key"] == "api_key"

    # Bearer Token
    action = init_action()
    action.authentication = "Bearer"
    action.module.configuration["api_key"] = "api_key"
    arguments = {"uuid": 10}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/10/count", json=expected_response)
        action.run(arguments)
        assert mock.request_history[0].headers["Authorization"] == "Bearer api_key"

    # Query Param API Key
    action = init_action()
    action.authentication = "apiKey"
    action.auth_query_param = "key"
    action.module.configuration["api_key"] = "api_key"
    arguments = {"uuid": 10}
    with requests_mock.Mocker() as mock:
        mock.get("http://base_url/resource/10/count", json=expected_response)
        action.run(arguments)
        assert mock.request_history[0].qs == {"key": ["api_key"]}


def test_action_with_arguments_model():
    class TestActionArguments(BaseModel):
        field: str = "value"
        number: int = 0

    class TestAction(Action):
        def run(self, arguments: TestActionArguments):
            return arguments

    action = TestAction()

    # Call the action with an empty dict, the default value should be used
    arguments = action.run({})
    assert arguments.field == "value"

    # Call the action with a value, it should be used and coerced
    arguments = action.run({"field": 3})
    assert arguments.field == "3"

    # Call the action with a bad value, it should raise a validation error
    with pytest.raises(ValidationError):
        action.run({"number": "NotANumber"})


def test_action_with_results_model():
    class TestActionResults(BaseModel):
        field: str = "value"
        number: int = 0

    class TestAction(Action):
        results_model = TestActionResults

        def run(self, arguments: dict):
            return arguments

    action = TestAction()

    # Return and empty dict, the default value should be used
    results = action.run({})
    assert results["field"] == "value"

    # Return a value, it should be validated/coerced
    results = action.run({"field": 3})
    assert results["field"] == "3"

    # Return a bad value, it should raise a validation error
    with pytest.raises(ValidationError):
        action.run({"number": "NotANumber"})


def test_action_send_result_client_error(mock_volume):
    class DummyAction(Action):
        def run(self, arguments):
            pass

    action = DummyAction()
    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL, status_code=400)
        with pytest.raises(SendEventError):
            action.send_results()


def test_action_send_result_conflict(mock_volume):
    """
    Conflict error should be ignored
    """

    class DummyAction(Action):
        def run(self, arguments):
            pass

    action = DummyAction()
    with requests_mock.Mocker() as rmock:
        rmock.patch(FAKE_URL, status_code=409)
        try:
            action.send_results()
        except Exception as ex:
            assert False, f"'send_results' raised an exception {ex}"


@patch.object(Module, "has_secrets", return_value=True)
@patch.object(Action, "token", return_value="", new_callable=PropertyMock)
@requests_mock.Mocker(kw="m")
def test_add_secrets_dict(_, __, **kwargs):
    callback_url = "https://mock.callback"
    secret_key = "foo"
    secrets = {secret_key: "bar"}
    kwargs["m"].register_uri(
        "PATCH",
        callback_url,
        status_code=200,
        json={"module_configuration": {"value": secrets}},
    )
    action = DummyAction()

    class DummyModule(Module):
        def __init__(self):
            super().__init__()
            self._configuration = {}

    action.module = DummyModule()

    with (
        patch.object(
            Action, "callback_url", return_value=callback_url, new_callable=PropertyMock
        ),
        patch.object(Module, "manifest_secrets", return_value=secret_key),
    ):
        action.set_task_as_running()
    assert action.module.configuration == secrets


@patch.object(Module, "has_secrets", return_value=True)
@patch.object(Action, "token", return_value="", new_callable=PropertyMock)
@requests_mock.Mocker(kw="m")
def test_add_secrets_object(_, __, **kwargs):
    callback_url = "https://mock.callback"
    secret_key = "foo"
    secrets = {secret_key: "bar"}
    kwargs["m"].register_uri(
        "PATCH",
        callback_url,
        status_code=200,
        json={"module_configuration": {"value": secrets}},
    )
    action = DummyAction()

    class DummyConf:
        pass

    class DummyModule(Module):
        def __init__(self):
            super().__init__()
            self._configuration = DummyConf()

    action.module = DummyModule()

    with (
        patch.object(
            Action, "callback_url", return_value=callback_url, new_callable=PropertyMock
        ),
        patch.object(Module, "manifest_secrets", return_value=secret_key),
    ):
        action.set_task_as_running()
    assert getattr(action.module.configuration, secret_key) == secrets[secret_key]
