from unittest.mock import patch

import requests_mock

from sekoia_automation.account_validator import AccountValidator
from sekoia_automation.module import Module


class MockAccountValidator(AccountValidator):
    mock_return_value = True

    def validate(self):
        if not self.mock_return_value:
            self.error("Validation failed")
        return self.mock_return_value


def test_execute_success():
    validator = MockAccountValidator()
    validator.mock_return_value = True

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ),
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch("http://example.com/callback", status_code=200)

        validator.execute()

        # Check the callback has been called
        assert mock_request.call_count == 2
        assert mock_request.request_history[0].json() == {"status": "running"}
        assert mock_request.last_request.json() == {
            "results": {"success": True},
            "status": "finished",
        }


def test_execute_failure():
    validator = MockAccountValidator()
    validator.mock_return_value = False

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ),
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch("http://example.com/callback", status_code=200)

        validator.execute()

        # Check the callback has been called
        assert mock_request.call_count == 2
        assert mock_request.request_history[0].json() == {"status": "running"}
        assert mock_request.last_request.json() == {
            "error": "Validation failed",
            "results": {"success": False},
            "status": "finished",
        }


def test_execute_with_secrets():
    module = Module()
    module._manifest = {
        "configuration": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "properties": {
                "api_key": {"description": "SEKOIA.IO API key", "type": "string"},
                "base_url": {
                    "description": "SEKOIA.IO base URL (ex. https://api.sekoia.io)",
                    "type": "string",
                },
            },
            "required": ["api_key"],
            "secrets": ["api_key"],
            "title": "SEKOIA.IO Configuration",
            "type": "object",
        }
    }
    module._configuration = {"base_url": "https://api.sekoia.io"}
    validator = MockAccountValidator(module=module)
    validator.mock_return_value = True

    with (
        patch.object(
            validator.module, "load_config", return_value="http://example.com/callback"
        ),
        requests_mock.Mocker() as mock_request,
    ):
        mock_request.patch(
            "http://example.com/callback",
            status_code=200,
            json={"module_configuration": {"value": {"api_key": "foo"}}},
        )

        validator.execute()

        # Check the configuration has been updated with the secrets
        assert module.configuration == {
            "api_key": "foo",
            "base_url": "https://api.sekoia.io",
        }
        # Check the callback has been called
        assert mock_request.call_count == 2
        assert mock_request.request_history[0].json() == {"status": "running"}
        assert mock_request.last_request.json() == {
            "results": {"success": True},
            "status": "finished",
        }
