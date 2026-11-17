import signal
import traceback
from collections.abc import Generator
from typing import ClassVar
from unittest.mock import Mock

import pytest
import requests
import requests_mock
from pydantic import ValidationError

from sekoia_automation.asset_connector import AssetConnector, AssetConnectorAction
from sekoia_automation.asset_connector.models.connector import AssetItem
from sekoia_automation.exceptions import TriggerConfigurationError
from sekoia_automation.storage import PersistentJSON
from tests.asset_connector.test_connector import (  # noqa: F401
    asset_list,
    asset_object_1,
    asset_object_2,
    asset_object_3,
)

UUID = "04716e25-c97f-4a22-925e-8b636ad9c8a4"
PUSH_URL = f"http://example.com/api/v2/asset-management/asset-connector/{UUID}"
LOGS_URL = f"http://example.com/api/v1/symphony/connector-configurations/{UUID}/logs"
ARGUMENTS = {
    "sekoia_base_url": "http://example.com",
    "sekoia_api_key": "api-key",
    "batch_size": 1,
    "asset_connector_uuid": UUID,
    "connector_configuration_token": "configuration-token",
}


class FakeAssetConnector(AssetConnector):
    items: ClassVar[list[AssetItem]] = []
    stop_after: int | None = None
    error: Exception | None = None

    def update_checkpoint(self) -> None:
        with PersistentJSON("context.json", self.data_path) as cache:
            cache["pushes"] = cache.get("pushes", 0) + 1

    def reset_checkpoint(self) -> None:
        pass

    def get_mapped_fields(self) -> dict[str, str]:
        return {}

    def get_assets(self) -> Generator[AssetItem, None, None]:
        for index, item in enumerate(self.items):
            if index == self.stop_after:
                self.stop()
            if self.error:
                raise self.error
            yield item


class FakeAssetConnectorAction(AssetConnectorAction):
    connector_class = FakeAssetConnector


@pytest.fixture
def fake_connector(asset_list):  # noqa: F811
    FakeAssetConnector.items = asset_list.items
    yield FakeAssetConnector
    FakeAssetConnector.items = []
    FakeAssetConnector.stop_after = None
    FakeAssetConnector.error = None


@pytest.fixture
def action(tmp_path, fake_connector):
    return FakeAssetConnectorAction(data_path=tmp_path)


@pytest.fixture
def api():
    with requests_mock.Mocker() as mock:
        mock.post(PUSH_URL, json={})
        mock.post(LOGS_URL)
        yield mock


def requests_to(api, url):
    return [request for request in api.request_history if request.url == url]


def test_run_pushes_assets_to_the_connector_configuration(action, api, tmp_path):
    results = action.run(ARGUMENTS)

    assert results == {
        "fetched": 3,
        "pushed_batches": 3,
        "failed_batches": 0,
        "has_more": False,
    }
    pushes = requests_to(api, PUSH_URL)
    assert len(pushes) == 3
    assert pushes[0].headers["Authorization"] == "Bearer api-key"
    assert pushes[0].headers["User-Agent"] == f"sekoiaio-asset-connector-{UUID}"
    with PersistentJSON("context.json", tmp_path) as cache:
        assert cache["pushes"] == 3


def test_run_sends_the_logs_to_the_connector_configuration(action, api):
    action.run(ARGUMENTS)

    logs = requests_to(api, LOGS_URL)
    assert logs
    assert logs[-1].headers["Authorization"] == "Bearer configuration-token"
    messages = [log["message"] for request in logs for log in request.json()["logs"]]
    assert any("Starting a new asset fetch cycle" in message for message in messages)


def test_run_returns_has_more_when_stopped(action, api, fake_connector):
    fake_connector.stop_after = 1

    results = action.run(ARGUMENTS)

    assert results["has_more"] is True
    assert results["pushed_batches"] == 1
    assert len(requests_to(api, PUSH_URL)) == 1


def test_run_waits_for_the_rate_limit_within_the_time_budget(action, api):
    api.post(
        PUSH_URL,
        [
            {"status_code": 429, "headers": {"Retry-After": "0"}},
            {"status_code": 200, "json": {}},
        ],
    )

    results = action.run(ARGUMENTS)

    # The counters of the last cycle: the rate-limited batch is fetched and
    # pushed again by the next cycle
    assert results == {
        "fetched": 3,
        "pushed_batches": 3,
        "failed_batches": 0,
        "has_more": False,
    }
    assert len(requests_to(api, PUSH_URL)) == 4


def test_run_returns_has_more_when_the_rate_limit_exceeds_the_time_budget(action, api):
    action.MAX_DURATION = 60
    api.post(PUSH_URL, status_code=429, headers={"Retry-After": "120"})

    results = action.run(ARGUMENTS)

    assert results == {
        "fetched": 1,
        "pushed_batches": 0,
        "failed_batches": 0,
        "has_more": True,
    }
    assert len(requests_to(api, PUSH_URL)) == 1


def test_run_returns_has_more_when_the_time_limit_stops_a_retried_push(action, api):
    action.MAX_DURATION = 0.5
    api.post(PUSH_URL, exc=requests.ConnectionError("platform is down"))

    results = action.run(ARGUMENTS)

    assert results == {
        "fetched": 1,
        "pushed_batches": 0,
        "failed_batches": 0,
        "has_more": True,
    }


def test_run_fails_with_its_counters_on_a_failed_push(action, api, tmp_path):
    api.post(PUSH_URL, [{"status_code": 200, "json": {}}, {"status_code": 500}])

    results = action.run(ARGUMENTS)

    assert results == {
        "fetched": 2,
        "pushed_batches": 1,
        "failed_batches": 1,
        "has_more": False,
    }
    assert action.error_message
    assert len(requests_to(api, PUSH_URL)) == 2
    with PersistentJSON("context.json", tmp_path) as cache:
        assert cache["pushes"] == 1


def test_run_logs_errors_to_the_connector_configuration(action, api, fake_connector):
    fake_connector.error = RuntimeError("LDAP is down")

    with pytest.raises(RuntimeError):
        action.run(ARGUMENTS)

    messages = [
        log["message"]
        for request in requests_to(api, LOGS_URL)
        for log in request.json()["logs"]
    ]
    assert any("LDAP is down" in message for message in messages)


def test_run_raises_its_error_when_the_logs_api_is_down(
    monkeypatch, action, api, fake_connector
):
    fake_connector.error = RuntimeError("LDAP is down")
    monkeypatch.setattr(
        FakeAssetConnector,
        "_send_logs_to_api",
        Mock(side_effect=requests.ConnectionError("logs API is down")),
    )

    with pytest.raises(RuntimeError, match="LDAP is down"):
        action.run(ARGUMENTS)


def test_run_requires_the_connector_configuration(action, api):
    arguments = dict(ARGUMENTS)
    del arguments["connector_configuration_token"]

    with pytest.raises(ValidationError) as error:
        action.run(arguments)

    assert "api-key" not in str(error.value)
    assert not api.request_history


def test_run_keeps_the_api_key_out_of_configuration_errors(action, api):
    arguments = dict(ARGUMENTS)
    del arguments["sekoia_base_url"]

    with pytest.raises(TriggerConfigurationError) as error:
        action.run(arguments)

    assert "api-key" not in "".join(traceback.format_exception(error.value))
    assert not api.request_history


def test_run_restores_the_signal_handlers(action, api):
    def handler(*_):
        pass

    previous = signal.signal(signal.SIGTERM, handler)
    try:
        action.run(ARGUMENTS)

        assert signal.getsignal(signal.SIGTERM) is handler
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_run_restores_the_signal_handlers_when_the_configuration_is_invalid(
    action, api
):
    def handler(*_):
        pass

    arguments = dict(ARGUMENTS)
    del arguments["sekoia_api_key"]

    previous = signal.signal(signal.SIGTERM, handler)
    try:
        with pytest.raises(TriggerConfigurationError):
            action.run(arguments)

        assert signal.getsignal(signal.SIGTERM) is handler
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_run_skips_the_handlers_not_installed_from_python(monkeypatch, action, api):
    previous = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    monkeypatch.setattr(signal, "getsignal", lambda _: None)
    try:
        results = action.run(ARGUMENTS)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    assert results["pushed_batches"] == 3
