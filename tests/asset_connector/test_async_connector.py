import json
import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from sekoia_automation.asset_connector.async_connector import AsyncAssetConnector
from sekoia_automation.asset_connector.models.connector import AssetItem, AssetList
from sekoia_automation.asset_connector.models.ocsf.base import Metadata, Product
from sekoia_automation.asset_connector.models.ocsf.device import (
    Device,
    DeviceOCSFModel,
    DeviceTypeId,
    DeviceTypeStr,
    OperatingSystem,
    OSTypeId,
    OSTypeStr,
)
from sekoia_automation.asset_connector.models.ocsf.user import (
    Account,
    AccountTypeId,
    AccountTypeStr,
    Group,
    User,
    UserOCSFModel,
)
from sekoia_automation.asset_connector.models.ocsf.vulnerability import (
    CVE,
    FindingInformation,
    KillChain,
    KillChainPhase,
    KillChainPhaseID,
    VulnerabilityDetails,
    VulnerabilityOCSFModel,
)


class ContextDict(dict):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class FakeAsyncAssetConnector(AsyncAssetConnector):
    assets: AssetList | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.context = ContextDict({})

    def set_assets(self, assets: AssetList) -> None:
        self.assets = assets

    async def update_checkpoint(self):
        with self.context as cache:
            cache["most_recent_date_seen"] = self._latest_time

    async def get_assets(
        self,
    ) -> AsyncGenerator[AssetItem, None]:
        """
        Fake method to simulate asset retrieval.
        Yields:
            AssetObject: Fake asset object.
        """

        if self.assets is None:
            raise ValueError("Assets not set")

        self._latest_time = "2023-10-01T00:00:00Z"

        for item in self.assets.items:
            yield item


@pytest.fixture
def test_async_asset_connector():
    test_connector = FakeAsyncAssetConnector()

    test_connector.configuration = {
        "sekoia_base_url": "http://example.com",
        "sekoia_api_key": "fake_api_key",
        "frequency": 60,
    }

    test_connector.log = Mock()
    test_connector.log_exception = Mock()

    yield test_connector


@pytest.fixture
def asset_object_1():
    product = Product(name="Harfanglab EDR", version="24.12")
    metadata_object = Metadata(product=product, version="1.5.0")
    os_object = OperatingSystem(
        name="Windows 10", type=OSTypeStr.WINDOWS, type_id=OSTypeId.WINDOWS
    )

    device_object = Device(
        type_id=DeviceTypeId.DESKTOP,
        type=DeviceTypeStr.DESKTOP,
        uid="12345",
        os=os_object,
        hostname="example-host",
    )

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
        metadata=metadata_object,
        device=device_object,
    )


@pytest.fixture
def asset_object_2():
    product = Product(name="Harfanglab EDR", version="24.12")
    metadata_object = Metadata(product=product, version="1.5.0")
    os_object = OperatingSystem(
        name="Linux test", type=OSTypeStr.LINUX, type_id=OSTypeId.LINUX
    )

    device_object = Device(
        type_id=DeviceTypeId.DESKTOP,
        type=DeviceTypeStr.DESKTOP,
        uid="54321",
        os=os_object,
        hostname="example-host_1",
    )

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
        metadata=metadata_object,
        device=device_object,
    )


@pytest.fixture
def asset_object_3():
    product = Product(name="AWS IAM", version="1.5.0")
    metadata_object = Metadata(product=product, version="1.5.0")

    user_object = User(
        has_mfa=True,
        name="John Doe",
        uid="user-123",
        account=Account(
            name="john.doe@example.com",
            type_id=AccountTypeId.AWS_ACCOUNT,
            type=AccountTypeStr.AWS_ACCOUNT,
            uid="account-123",
        ),
        groups=[
            Group(
                name="Admins",
                desc="Administrator group",
                privileges=["read", "write", "delete"],
                uid="group-123",
            )
        ],
        full_name="Johnathan Doe",
        email_addr="john.doe@example.com",
    )

    return UserOCSFModel(
        activity_id=2,
        activity_name="Collect",
        category_name="Discovery",
        category_uid=5,
        class_name="User Inventory Info",
        class_uid=5003,
        type_name="User Inventory Info: Collect",
        type_uid=500302,
        time=1633036800,
        metadata=metadata_object,
        user=user_object,
    )


@pytest.fixture
def vulnerability_asset():
    product = Product(name="Tenable", version="1.0.0")
    metadata = Metadata(product=product, version="1.5.0")

    finding_product = Product(name="Tenable Vulnerability Management", version="1.0.0")
    kill_chain_object_1 = KillChain(
        phase=KillChainPhase.DELIVERY, phase_id=KillChainPhaseID.DELIVERY
    )
    kill_chain_object_2 = KillChain(
        phase=KillChainPhase.EXPLOITATION, phase_id=KillChainPhaseID.EXPLOITATION
    )
    kill_chain = [kill_chain_object_1, kill_chain_object_2]
    finding_information = FindingInformation(
        uid="123456788",
        types=["Vulnerability", "Vulnerability_2"],
        data_sources=["DataSource1", "DataSource2"],
        title="Sample Vulnerability",
        desc="A sample vulnerability for testing purposes.",
        first_seen_time=1632036800,
        last_seen_time=1632036900,
        product=finding_product,
        kill_chain=kill_chain,
    )

    cve = CVE(uid="CVE-12345", type="")
    vulnerabilities = VulnerabilityDetails(
        cve=cve,
        title="Sample Vulnerability Title Details",
        references=["http://example.com/vuln-details", "http://example.com/more-info"],
    )

    return VulnerabilityOCSFModel(
        activity_id=2,
        activity_name="Collect",
        category_name="Findings",
        category_uid=2,
        class_name="Vulnerability Finding",
        class_uid=2002,
        type_name="Vulnerability Finding: Collect",
        type_uid=200201,
        time=1633036800,
        metadata=metadata,
        finding_info=finding_information,
        vulnerabilities=[vulnerabilities],
    )


@pytest.fixture
def asset_list(asset_object_1, asset_object_2, asset_object_3):
    return AssetList(version=1, items=[asset_object_1, asset_object_2, asset_object_3])


@pytest.mark.skipif(
    "{'ASSET_CONNECTOR_BATCH_SIZE'}.issubset(os.environ.keys()) == False"
)
def test_batch_size_env_var_exist(test_async_asset_connector):
    connector_batch_size = test_async_asset_connector.batch_size
    assert connector_batch_size == os.environ.get("ASSET_CONNECTOR_BATCH_SIZE")


def test_batch_size_env_var_not_exist(test_async_asset_connector):
    connector_batch_size = test_async_asset_connector.batch_size
    assert connector_batch_size == 100


@pytest.mark.skipif(
    "{'ASSET_CONNECTOR_PRODUCTION_BASE_URL'}.issubset(os.environ.keys()) == False"
)
def test_base_url_env_var_exist(test_async_asset_connector):
    connector_base_url = test_async_asset_connector.production_base_url
    assert connector_base_url == os.environ.get("ASSET_CONNECTOR_PRODUCTION_BASE_URL")


def test_base_url_env_var_not_exist(test_async_asset_connector):
    connector_base_url = test_async_asset_connector.production_base_url
    assert connector_base_url == "https://api.sekoia.io"


@pytest.mark.skipif(
    "{'ASSET_CONNECTOR_FREQUENCY'}.issubset(os.environ.keys()) == False"
)
def test_frequency_env_var_exist(test_async_asset_connector):
    connector_frequency = test_async_asset_connector.frequency
    assert connector_frequency == int(os.environ.get("ASSET_CONNECTOR_FREQUENCY"))


def test_frequency_env_var_not_exist(test_async_asset_connector):
    connector_frequency = test_async_asset_connector.frequency
    assert connector_frequency == 60


def test_http_header(test_async_asset_connector):
    test_async_asset_connector.module._connector_configuration_uuid = (
        "04716e25-c97f-4a22-925e-8b636ad9c8a4"
    )
    headers = test_async_asset_connector._http_header
    assert headers["Authorization"] == "Bearer fake_api_key"
    assert headers["Content-Type"] == "application/json"
    assert (
        headers["User-Agent"]
        == "sekoiaio-asset-connector-04716e25-c97f-4a22-925e-8b636ad9c8a4"
    )


def test_handle_api_error(test_async_asset_connector):
    error_code = 400
    error_message = test_async_asset_connector.handle_api_error(error_code)
    assert error_message == "Client error - HTTP (400)"

    error_code = 401
    error_message = test_async_asset_connector.handle_api_error(error_code)
    assert error_message == "Client error - HTTP (401)"

    error_code = 404
    error_message = test_async_asset_connector.handle_api_error(error_code)
    assert error_message == "Client error - HTTP (404)"

    error_code = 500
    error_message = test_async_asset_connector.handle_api_error(error_code)
    assert error_message == "Server error - HTTP (500)"


@pytest.mark.asyncio
async def test_session_creation(test_async_asset_connector):
    """Test that session is created properly"""
    assert test_async_asset_connector._session is None

    async with test_async_asset_connector.session() as session:
        assert isinstance(session, aiohttp.ClientSession)
        assert test_async_asset_connector._session is not None

    # Session should still exist after context manager
    assert test_async_asset_connector._session is not None

    # Clean up
    await test_async_asset_connector._session.close()


@pytest.mark.asyncio
async def test_session_with_rate_limiter(test_async_asset_connector):
    """Test that session respects rate limiter"""
    from aiolimiter import AsyncLimiter

    test_async_asset_connector._rate_limiter = AsyncLimiter(max_rate=10, time_period=1)

    async with test_async_asset_connector.session() as session:
        assert isinstance(session, aiohttp.ClientSession)

    # Clean up
    if test_async_asset_connector._session:
        await test_async_asset_connector._session.close()


@pytest.mark.asyncio
async def test_post_assets_to_api_success(test_async_asset_connector, asset_list):
    """Test successful asset posting"""
    # Mock the retry mechanism and session directly
    test_async_asset_connector.update_checkpoint = AsyncMock()

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value='{"result": "success"}')
    mock_response.json = AsyncMock(return_value={"result": "success"})

    # Patch at aiohttp ClientSession level
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response
        mock_post.return_value.__aexit__.return_value = None

        response = await test_async_asset_connector.post_assets_to_api(
            asset_list, "http://example.com/api"
        )

    assert response == {"result": "success"}
    test_async_asset_connector.update_checkpoint.assert_called_once()


@pytest.mark.asyncio
async def test_post_assets_to_api_failure(test_async_asset_connector, asset_list):
    """Test failed asset posting with 400 error"""
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text = AsyncMock(return_value='{"error": "bad request"}')
    mock_response.json = AsyncMock(return_value={"error": "bad request"})

    # Patch at aiohttp ClientSession level
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_response
        mock_post.return_value.__aexit__.return_value = None

        response = await test_async_asset_connector.post_assets_to_api(
            asset_list, "http://example.com/api"
        )

    assert response is None


@pytest.mark.asyncio
async def test_post_assets_to_api_timeout(test_async_asset_connector, asset_list):
    """Test timeout handling"""
    # Patch the tenacity retry to not retry and the post to raise TimeoutError
    with patch.object(test_async_asset_connector, "_retry") as mock_retry:
        # Create a simple context manager that doesn't retry
        class FakeAttempt:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        mock_retry.return_value = [FakeAttempt()]

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.side_effect = TimeoutError()
            mock_post.return_value.__aexit__.return_value = None

            response = await test_async_asset_connector.post_assets_to_api(
                asset_list, "http://example.com/api"
            )

    assert response is None
    test_async_asset_connector.log_exception.assert_called_once()


@pytest.mark.asyncio
async def test_push_assets_to_sekoia(test_async_asset_connector, asset_list):
    """Test pushing assets to Sekoia API"""
    test_async_asset_connector.post_assets_to_api = AsyncMock(
        return_value={"result": "success"}
    )
    test_async_asset_connector.module._connector_configuration_uuid = (
        "04716e25-c97f-4a22-925e-8b636ad9c8a4"
    )

    await test_async_asset_connector.push_assets_to_sekoia(asset_list)

    test_async_asset_connector.post_assets_to_api.assert_called_once()
    call_args = test_async_asset_connector.post_assets_to_api.call_args
    pos_args, kw_args = call_args
    assert kw_args["assets"] == asset_list
    assert (
        kw_args["asset_connector_api_url"]
        == "http://example.com/api/v2/asset-management/asset-connector/04716e25-c97f-4a22-925e-8b636ad9c8a4"
    )


@pytest.mark.asyncio
async def test_push_assets_to_sekoia_empty_list(test_async_asset_connector):
    """Test pushing empty asset list"""
    empty_list = AssetList(version=1, items=[])
    test_async_asset_connector.post_assets_to_api = AsyncMock()
    test_async_asset_connector.module._connector_configuration_uuid = (
        "04716e25-c97f-4a22-925e-8b636ad9c8a4"
    )

    await test_async_asset_connector.push_assets_to_sekoia(empty_list)

    # Empty list is still posted to API
    test_async_asset_connector.post_assets_to_api.assert_called_once()


@pytest.mark.asyncio
async def test_asset_fetch_cycle(
    test_async_asset_connector,
    asset_object_1,
    asset_object_2,
    asset_object_3,
    asset_list,
):
    """Test the asset fetch cycle"""
    test_async_asset_connector.set_assets(
        AssetList(version=1, items=[asset_object_1, asset_object_2, asset_object_3])
    )
    test_async_asset_connector.push_assets_to_sekoia = AsyncMock()

    await test_async_asset_connector.asset_fetch_cycle()

    test_async_asset_connector.push_assets_to_sekoia.assert_called_once()
    assert test_async_asset_connector.push_assets_to_sekoia.call_count == 1
    assert (
        test_async_asset_connector.push_assets_to_sekoia.call_args[0][0] == asset_list
    )


@pytest.mark.asyncio
async def test_asset_fetch_cycle_batching(
    test_async_asset_connector, asset_object_1, asset_object_2, asset_object_3
):
    """Test that batching works correctly"""
    # Create enough assets to trigger multiple batches
    assets = [asset_object_1, asset_object_2, asset_object_3] * 50  # 150 assets
    test_async_asset_connector.set_assets(AssetList(version=1, items=assets))
    test_async_asset_connector.push_assets_to_sekoia = AsyncMock()
    test_async_asset_connector.configuration.batch_size = 100

    await test_async_asset_connector.asset_fetch_cycle()

    # Should be called twice: once for 100 assets, once for remaining 50
    assert test_async_asset_connector.push_assets_to_sekoia.call_count == 2


@pytest.mark.asyncio
async def test_update_checkpoint(
    test_async_asset_connector, asset_object_1, asset_object_2, asset_object_3
):
    """Test checkpoint update"""
    test_async_asset_connector.set_assets(
        AssetList(version=1, items=[asset_object_1, asset_object_2, asset_object_3])
    )

    # Call get_assets to set _latest_time, then call update_checkpoint directly
    assets = []
    async for asset in test_async_asset_connector.get_assets():
        assets.append(asset)

    await test_async_asset_connector.update_checkpoint()

    # Verify checkpoint was updated
    assert (
        test_async_asset_connector.context["most_recent_date_seen"]
        == "2023-10-01T00:00:00Z"
    )


def test_jsonify_device_asset(asset_object_1):
    """Test device asset serialization"""
    json_data = asset_object_1.model_dump()
    serialized_json = json.dumps(json_data)

    assert serialized_json
    assert json_data["activity_name"] == "Collect"
    assert json_data["device"]["hostname"] == "example-host"
    assert json_data["device"]["type_id"] == 2
    assert json_data["device"]["type"] == "Desktop"
    assert json_data["device"]["os"]["type"] == "windows"
    assert json_data["device"]["os"]["type_id"] == 100
    assert json_data["metadata"]["product"]["name"] == "Harfanglab EDR"


def test_jsonify_vulnerability_asset(vulnerability_asset):
    """Test vulnerability asset serialization"""
    json_data = vulnerability_asset.model_dump()
    serialized_json = json.dumps(json_data)

    assert serialized_json
    assert (
        json_data["vulnerabilities"][0]["title"] == "Sample Vulnerability Title Details"
    )
    assert json_data["vulnerabilities"][0]["cve"]["uid"] == "CVE-12345"
    assert json_data["finding_info"]["kill_chain"][0]["phase"] == "Delivery"
    assert json_data["finding_info"]["kill_chain"][1]["phase"] == "Exploitation"


@pytest.mark.asyncio
async def test_get_assets_async_generator(test_async_asset_connector, asset_list):
    """Test that get_assets returns an AsyncGenerator"""
    test_async_asset_connector.set_assets(asset_list)

    assets = []
    async for asset in test_async_asset_connector.get_assets():
        assets.append(asset)

    assert len(assets) == 3
    assert assets[0] == asset_list.items[0]
    assert assets[1] == asset_list.items[1]
    assert assets[2] == asset_list.items[2]
