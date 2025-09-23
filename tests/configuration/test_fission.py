import pytest

from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.fission import FissionConfiguration


@pytest.fixture
def app():
    from flask import Flask

    app = Flask(__name__)
    return app


def test_load_config_request_json(app, monkeypatch):
    # Set an environment variable
    monkeypatch.setenv("TOTO", "value_from_env")

    # Use a test request context with JSON data
    with app.test_request_context(
        "/", method="POST", json={"foo": "bar", "baz": '{"foo": "bar"}'}
    ):
        # Create a FissionConfiguration instance
        configuration = FissionConfiguration()

        # The value of "foo" is a simple string
        assert configuration.load("foo") == "bar"
        # The value of "baz" is a JSON string, so it should be parsed
        assert configuration.load("baz", type_="json") == {"foo": "bar"}
        # Test loading a non-existing configuration with non_exist_ok=True
        assert configuration.load("titi", non_exist_ok=True) is None
        # Test loading a non-existing configuration, should fallback to env variable
        assert configuration.load("toto") == "value_from_env"


def test_load_config_request_no_json(app):
    # Use a test request context without JSON data
    with app.test_request_context("/", method="POST"):
        # Create a FissionConfiguration instance
        configuration = FissionConfiguration()

        # Test loading a non-existing configuration, should raise KeyError
        with pytest.raises(KeyError):
            configuration.load("foo")
