from unittest.mock import call, patch

import pytest
import requests
import requests_mock

from sekoia_automation.module import AccountValidator
from tests.conftest import MockAccountValidator


def test_execute_success():
    validator = MockAccountValidator()

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ) as mock_load_config,
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.post("http://example.com/callback", status_code=200)

        validator.execute()

        assert mock_load_config.call_args_list == [
            call(validator.VALIDATION_CALLBACK_URL_FILE_NAME),
            call(validator.TOKEN_FILE_NAME),
        ]
        assert mock_request.called
        assert mock_request.last_request.json() == {"validation_status": True}


def test_execute_failure():
    class FailingAccountValidator(AccountValidator):
        def validator(self) -> bool:
            return False

    validator = FailingAccountValidator()

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ) as mock_load_config,
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.post("http://example.com/callback", status_code=200)

        validator.execute()

        assert mock_load_config.call_args_list == [
            call(validator.VALIDATION_CALLBACK_URL_FILE_NAME),
            call(validator.TOKEN_FILE_NAME),
        ]
        assert mock_request.called
        assert mock_request.last_request.json() == {"validation_status": False}


def test_execute_request_failure():
    validator = MockAccountValidator()

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ) as mock_load_config,
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.post("http://example.com/callback", status_code=500)

        with pytest.raises(requests.exceptions.HTTPError):
            validator.execute()

        assert mock_load_config.call_args_list == [
            call(validator.VALIDATION_CALLBACK_URL_FILE_NAME),
            call(validator.TOKEN_FILE_NAME),
        ]
        assert mock_request.called
        assert mock_request.last_request.json() == {"validation_status": True}
