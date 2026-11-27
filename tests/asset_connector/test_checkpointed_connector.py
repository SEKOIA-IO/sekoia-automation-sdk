from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import requests

from sekoia_automation.asset_connector import (
    AsyncCheckpointedAssetConnector,
    CheckpointedAssetConnector,
)
from sekoia_automation.asset_connector.models.ocsf.base import Metadata, Product
from sekoia_automation.asset_connector.models.ocsf.device import (
    Device,
    DeviceOCSFModel,
    DeviceTypeId,
    DeviceTypeStr,
)
from sekoia_automation.exceptions import TriggerConfigurationError

CONFIGURATION = {
    "sekoia_base_url": "http://example.com",
    "sekoia_api_key": "fake_api_key",
    "frequency": 60,
    "batch_size": 2,
}


def device(uid: str) -> DeviceOCSFModel:
    return DeviceOCSFModel(
        activity_id=2,
        activity_name="Collect",
        category_name="Discovery",
        category_uid=5,
        class_name="Asset",
        class_uid=5001,
        type_name="Software Inventory Info: Collect",
        type_uid=500102,
        time=1633036800,
        metadata=Metadata(product=Product(name="EDR", version="1"), version="1.5.0"),
        device=Device(
            type_id=DeviceTypeId.DESKTOP,
            type=DeviceTypeStr.DESKTOP,
            uid=uid,
            hostname=f"host-{uid}",
        ),
    )


class SyncConnector(CheckpointedAssetConnector):
    checkpoint_field = "updatedAt"
    checkpoint_mode = "incremental"

    def get_mapped_fields(self) -> dict[str, str]:
        return {}

    def get_assets_since(self, checkpoint):
        self.calls.append(checkpoint)
        for cursor in self.cursors:
            if checkpoint is None or cursor > checkpoint:
                yield cursor, device(str(cursor))


class AsyncConnector(AsyncCheckpointedAssetConnector):
    checkpoint_field = "updatedAt"
    checkpoint_mode = "incremental"

    def get_mapped_fields(self) -> dict[str, str]:
        return {}

    async def get_assets_since(self, checkpoint):
        self.calls.append(checkpoint)
        for cursor in self.cursors:
            if checkpoint is None or cursor > checkpoint:
                yield cursor, device(str(cursor))


def make(cls, tmp_path, cursors, mode="incremental", fail_on_batch=None):
    connector_class = type("Connector", (cls,), {"checkpoint_mode": mode})
    connector = connector_class(data_path=tmp_path)
    connector.configuration = CONFIGURATION
    connector.log = Mock()
    connector.log_exception = Mock()
    connector.cursors = cursors
    connector.calls = []
    connector.pushed = []

    connector._stop_event.wait = Mock(return_value=False)

    def status(json) -> int:
        connector.pushed.append([item["device"]["uid"] for item in json["items"]])
        return 500 if len(connector.pushed) == fail_on_batch else 200

    def post(url, json, timeout):
        response = requests.Response()
        response.status_code = status(json)
        response._content = b"{}"
        return response

    def async_post(url, json, timeout):
        response = Mock(status=status(json), headers={})
        response.text = AsyncMock(return_value="{}")
        context = MagicMock()
        context.__aenter__.return_value = response
        return context

    if issubclass(cls, AsyncCheckpointedAssetConnector):
        connector._session = Mock(post=Mock(side_effect=async_post))
    else:
        connector._http_session.post = Mock(side_effect=post)
    return connector


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("time.sleep"), patch("asyncio.sleep", new=AsyncMock()):
        yield


def stored(connector):
    with connector.asset_checkpoint.store as store:
        return dict(store)


@pytest.mark.parametrize("cls", [SyncConnector, AsyncConnector])
def test_declaration_requires_field(cls, tmp_path):
    connector_class = type("Connector", (cls,), {"checkpoint_field": ""})
    with pytest.raises(TriggerConfigurationError, match="checkpoint_field"):
        connector_class(data_path=tmp_path)


@pytest.mark.parametrize("cls", [SyncConnector, AsyncConnector])
def test_declaration_requires_known_mode(cls, tmp_path):
    connector_class = type("Connector", (cls,), {"checkpoint_mode": "latest"})
    with pytest.raises(TriggerConfigurationError, match="checkpoint_mode"):
        connector_class(data_path=tmp_path)


@pytest.mark.parametrize(
    "field", ["createdAt", "created_at", "creationTime", "createTime", "create_date"]
)
def test_incremental_refuses_creation_field(field, tmp_path):
    connector_class = type("Connector", (SyncConnector,), {"checkpoint_field": field})
    with pytest.raises(TriggerConfigurationError, match="sweep"):
        connector_class(data_path=tmp_path)


def test_sweep_accepts_creation_field(tmp_path):
    connector_class = type(
        "Connector",
        (SyncConnector,),
        {"checkpoint_field": "createdAt", "checkpoint_mode": "sweep"},
    )
    connector_class(data_path=tmp_path)


def test_incremental_commits_last_pushed_and_resumes(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2, 3, 4, 5])

    connector.asset_fetch_cycle()

    assert connector.pushed == [["1", "2"], ["3", "4"], ["5"]]
    assert connector.asset_checkpoint.cursor == 5

    connector.cursors = [1, 2, 3, 4, 5, 6]
    connector.asset_fetch_cycle()

    assert connector.calls == [None, 5]
    assert connector.pushed[-1] == ["6"]
    assert connector.asset_checkpoint.cursor == 6


def test_tie_group_cut_by_a_push_is_fetched_again(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2, 2, 3], fail_on_batch=2)

    connector.asset_fetch_cycle()

    # The first batch ends inside the tie group on 2: only 1 is safe.
    assert connector.asset_checkpoint.cursor == 1

    connector.asset_fetch_cycle()

    assert connector.calls == [None, 1]
    assert connector.pushed[-2:] == [["2", "2"], ["3"]]
    assert connector.asset_checkpoint.cursor == 3


def test_unsorted_assets_freeze_the_checkpoint(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2, 3, 5, 4])
    connector.get_assets_since = lambda checkpoint: (
        (c, device(str(c))) for c in connector.cursors
    )

    connector.asset_fetch_cycle()

    # [1, 2] commits 2; 4 after 5 freezes the checkpoint for the rest.
    assert connector.pushed == [["1", "2"], ["3", "5"], ["4"]]
    assert connector.asset_checkpoint.cursor == 2
    assert any(
        call.kwargs.get("level") == "error" for call in connector.log.call_args_list
    )


def test_failed_push_freezes_the_checkpoint(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2, 3, 4, 5], fail_on_batch=2)

    connector.asset_fetch_cycle()

    # [3, 4] is rejected: the later [5] must not commit past it.
    assert connector.pushed == [["1", "2"], ["3", "4"], ["5"]]
    assert connector.asset_checkpoint.cursor == 2

    connector.asset_fetch_cycle()

    assert connector.calls == [None, 2]
    assert connector.asset_checkpoint.cursor == 5


def test_changed_field_discards_the_cursor(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2])
    with connector.asset_checkpoint.store as store:
        store["field"] = "createdAt"
        store["cursor"] = 10

    connector.asset_fetch_cycle()

    assert connector.calls == [None]
    assert stored(connector) == {"field": "updatedAt", "cursor": 2}


def test_checkpoint_never_moves_backwards(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2])
    with connector.asset_checkpoint.store as store:
        store["field"] = "updatedAt"
        store["cursor"] = 10
    connector.get_assets_since = lambda checkpoint: (
        (c, device(str(c))) for c in connector.cursors
    )

    connector.asset_fetch_cycle()

    assert connector.asset_checkpoint.cursor == 10


def test_reset_fetches_everything_again(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2, 3])
    connector.asset_fetch_cycle()

    connector.reset_checkpoint()

    assert stored(connector) == {}

    connector.asset_fetch_cycle()

    assert connector.calls == [None, None]


def test_sweep_starts_the_next_pass_one_frequency_after_the_previous(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2, 3], mode="sweep")

    with patch("time.time", return_value=1000.0):
        connector.asset_fetch_cycle()

    assert connector.pushed == [["1", "2"], ["3"]]
    assert stored(connector) == {
        "field": "updatedAt",
        "cursor": None,
        "pass_started_at": 1000.0,
        "pass_completed": True,
    }

    with patch("time.time", return_value=1030.0):
        connector.asset_fetch_cycle()

    connector._stop_event.wait.assert_called_once_with(30.0)
    assert connector.calls == [None, None]
    assert connector.pushed[-2:] == [["1", "2"], ["3"]]


def test_sweep_wait_ends_on_stop(tmp_path):
    connector = make(SyncConnector, tmp_path, [1], mode="sweep")
    with patch("time.time", return_value=1000.0):
        connector.asset_fetch_cycle()
    connector._stop_event.wait.return_value = True

    with patch("time.time", return_value=1030.0):
        connector.asset_fetch_cycle()

    assert connector.calls == [None]


def test_sweep_completes_when_last_batch_is_full(tmp_path):
    connector = make(SyncConnector, tmp_path, [1, 2], mode="sweep")

    connector.asset_fetch_cycle()

    assert stored(connector)["pass_completed"] is True


def test_sweep_pass_with_a_failed_push_is_not_completed(tmp_path):
    connector = make(
        SyncConnector, tmp_path, [1, 2, 3, 4, 5], mode="sweep", fail_on_batch=2
    )

    connector.asset_fetch_cycle()

    assert stored(connector)["cursor"] == 2
    assert stored(connector)["pass_completed"] is False

    connector.asset_fetch_cycle()

    assert connector.calls == [None, 2]
    assert stored(connector)["pass_completed"] is True


def test_sweep_resumes_an_interrupted_pass(tmp_path):
    connector = make(
        SyncConnector, tmp_path, [1, 2, 3, 4], mode="sweep", fail_on_batch=2
    )

    connector.asset_fetch_cycle()

    assert stored(connector)["cursor"] == 2
    assert stored(connector)["pass_completed"] is False

    connector.asset_fetch_cycle()

    assert connector.calls == [None, 2]
    assert stored(connector)["pass_completed"] is True


async def test_async_incremental_commits_and_resumes(tmp_path):
    connector = make(AsyncConnector, tmp_path, [1, 2, 2, 3], fail_on_batch=2)

    await connector.asset_fetch_cycle()

    assert connector.asset_checkpoint.cursor == 1

    await connector.asset_fetch_cycle()

    assert connector.calls == [None, 1]
    assert connector.asset_checkpoint.cursor == 3


async def test_async_failed_push_freezes_the_checkpoint(tmp_path):
    connector = make(AsyncConnector, tmp_path, [1, 2, 3, 4, 5], fail_on_batch=2)

    await connector.asset_fetch_cycle()

    assert connector.pushed == [["1", "2"], ["3", "4"], ["5"]]
    assert connector.asset_checkpoint.cursor == 2


async def test_async_sweep_completes_and_waits(tmp_path):
    connector = make(AsyncConnector, tmp_path, [1, 2, 3], mode="sweep")

    with patch("time.time", return_value=1000.0):
        await connector.asset_fetch_cycle()
    with patch("time.time", return_value=1030.0):
        await connector.asset_fetch_cycle()

    connector._stop_event.wait.assert_called_once_with(30.0)
    assert connector.calls == [None, None]
    assert stored(connector)["pass_completed"] is True


async def test_async_reset(tmp_path):
    connector = make(AsyncConnector, tmp_path, [1])
    await connector.asset_fetch_cycle()

    await connector.reset_checkpoint()

    assert stored(connector) == {}


async def test_async_unsorted_assets_freeze_the_checkpoint(tmp_path):
    connector = make(AsyncConnector, tmp_path, [1, 2, 3, 5, 4])

    async def unsorted(checkpoint):
        for cursor in connector.cursors:
            yield cursor, device(str(cursor))

    connector.get_assets_since = unsorted

    await connector.asset_fetch_cycle()

    assert connector.asset_checkpoint.cursor == 2
    assert any(
        call.kwargs.get("level") == "error" for call in connector.log.call_args_list
    )
