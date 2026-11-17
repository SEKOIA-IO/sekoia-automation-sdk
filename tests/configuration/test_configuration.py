import os
from unittest.mock import patch

import pytest

from sekoia_automation.configuration import get_configuration
from sekoia_automation.configuration.filesystem import FileSystemConfiguration
from sekoia_automation.configuration.fission import FissionConfiguration


@pytest.fixture
def app():
    from flask import Flask

    app = Flask(__name__)
    return app


def test_get_configuration_filesystem(monkeypatch):
    # Ensure SYMPHONY_RUNTIME is not set
    monkeypatch.delenv("SYMPHONY_RUNTIME", raising=False)

    # Get the configuration
    config = get_configuration()

    # Assert it's a FileSystemConfiguration
    assert isinstance(config, FileSystemConfiguration)


def test_get_configuration_fission(app, monkeypatch):
    with (
        patch.dict(os.environ, {"SYMPHONY_RUNTIME": "fission"}),
        app.test_request_context("/", method="POST"),
    ):
        # Use a test request context to simulate a Flask request
        # Get the configuration
        config = get_configuration(fission_mode=True)

        # Assert it's a FissionConfiguration
        assert isinstance(config, FissionConfiguration)
