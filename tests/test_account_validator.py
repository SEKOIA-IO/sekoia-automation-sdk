from unittest.mock import call, patch

import pytest
import requests
import requests_mock

from tests.conftest import MockAccountValidator


def test_execute_success():
    validator = MockAccountValidator()

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ) as mock_load_config,
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch("http://example.com/callback", status_code=200)

        validator.execute()

        assert mock_load_config.call_args_list == [
            call(validator.CALLBACK_URL_FILE_NAME),
            call(validator.TOKEN_FILE_NAME),
        ]
        assert mock_request.called
        assert mock_request.last_request.json() == {
            "validation_status": True,
            "need_secrets": False,
        }


def test_execute_failure():
    validator = MockAccountValidator(mock_return_value=False)

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ) as mock_load_config,
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch("http://example.com/callback", status_code=200)

        validator.execute()

        assert mock_load_config.call_args_list == [
            call(validator.CALLBACK_URL_FILE_NAME),
            call(validator.TOKEN_FILE_NAME),
        ]
        assert mock_request.called
        assert mock_request.last_request.json() == {
            "validation_status": False,
            "need_secrets": False,
        }


def test_execute_request_failure():
    validator = MockAccountValidator()

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ) as mock_load_config,
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch("http://example.com/callback", status_code=500)

        with pytest.raises(requests.exceptions.HTTPError):
            validator.execute()

        assert mock_load_config.call_args_list == [
            call(validator.CALLBACK_URL_FILE_NAME),
            call(validator.TOKEN_FILE_NAME),
        ]
        assert mock_request.called
        assert mock_request.last_request.json() == {
            "validation_status": True,
            "need_secrets": False,
        }


def test_retrieve_secrets():
    validator = MockAccountValidator()

    with (
        patch.object(validator.module, "has_secrets", return_value=True),
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ),
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch(
            "http://example.com/callback",
            json={"module_configuration": {"value": {"secret_key": "secret_value"}}},
        )

        validator.execute()
