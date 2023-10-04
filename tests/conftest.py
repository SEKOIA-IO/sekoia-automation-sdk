import asyncio
import random
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from unittest.mock import PropertyMock, patch

import pytest
import requests_mock
from faker import Faker

from sekoia_automation import config
from sekoia_automation import storage as storage_module
from sekoia_automation.module import Module
from sekoia_automation.trigger import Trigger


@pytest.fixture
def storage():
    new_storage = Path(mkdtemp())

    yield new_storage

    rmtree(new_storage.as_posix())


FAKE_URL = "http://sekoia-playbooks/endpoint"
DEFAULT_ARGUMENTS = {"key1": "value1"}
MANIFEST_WITH_SECRETS = {"configuration": {"secrets": ["a value"]}}
TRIGGER_SECRETS = {"api_key": "bar", "password": "baz"}


@pytest.fixture
def mock_volume():
    def mocked_load_config(module, file_name, type_="str", non_exist_ok=False):
        if "token" in file_name:
            return "token"
        elif "callback" in file_name:
            return FAKE_URL
        elif "sentry" in file_name:
            return "http://1234@localhost/123"
        else:
            return DEFAULT_ARGUMENTS

    original_method = Module.load_config
    Module.load_config = mocked_load_config

    yield

    Module.load_config = original_method


@pytest.fixture
def config_storage():
    old_config_storage = config.VOLUME_PATH
    config.VOLUME_PATH = mkdtemp()
    storage_module.VOLUME_PATH = config.VOLUME_PATH

    yield Path(config.VOLUME_PATH)

    rmtree(config.VOLUME_PATH)
    config.VOLUME_PATH = old_config_storage


@pytest.fixture
def tls_storage():
    old_tls_storage = config.TLS_VOLUME_PATH
    config.TLS_VOLUME_PATH = mkdtemp()
    storage_module.TLS_VOLUME_PATH = config.TLS_VOLUME_PATH

    yield Path(config.TLS_VOLUME_PATH)

    rmtree(config.TLS_VOLUME_PATH)
    config.TLS_VOLUME_PATH = old_tls_storage


@pytest.fixture
def mocked_trigger_logs():
    with patch.object(
        Trigger,
        "callback_url",
        new_callable=PropertyMock,
        return_value="http://sekoia-playbooks/callback",
    ), patch.object(Trigger, "token", return_value="secure_token"):
        with requests_mock.Mocker() as mock:
            mock.post("http://sekoia-playbooks/logs")

            yield mock


@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for pytest.mark.asyncio.

    Yields:
        loop:
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()

    yield loop

    loop.close()


@pytest.fixture(scope="session")
def faker_locale() -> list[str]:
    """
    Configure Faker to use correct locale.

    Returns:
        List[str]:
    """
    return ["en"]


@pytest.fixture(scope="session")
def faker_seed() -> int:
    """
    Configure Faker to use correct seed.

    Returns:
        int:
    """
    return random.randint(1, 10000)


@pytest.fixture(scope="session")
def session_faker(faker_locale: list[str], faker_seed: int) -> Faker:
    """
    Configure session lvl Faker to use correct seed and locale.

    Args:
        faker_locale: List[str]
        faker_seed: int

    Returns:
        Faker:
    """
    instance = Faker(locale=faker_locale)
    instance.seed_instance(seed=faker_seed)

    return instance
