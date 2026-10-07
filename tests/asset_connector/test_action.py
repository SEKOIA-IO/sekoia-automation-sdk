from collections.abc import Generator
from typing import ClassVar

import pytest
import requests_mock

from sekoia_automation.asset_connector import AssetConnector, AssetConnectorAction
from sekoia_automation.asset_connector.models.connector import AssetItem
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

    assert results["has_more"] is False
    # The rate-limited batch is fetched and pushed again by the next cycle
    assert len(requests_to(api, PUSH_URL)) == 4


def test_run_returns_has_more_when_the_rate_limit_exceeds_the_time_budget(action, api):
    action.MAX_DURATION = 60
    api.post(PUSH_URL, status_code=429, headers={"Retry-After": "120"})

    results = action.run(ARGUMENTS)

    assert results["has_more"] is True
    assert len(requests_to(api, PUSH_URL)) == 1


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
