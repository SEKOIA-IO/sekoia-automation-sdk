import asyncio
import os
import time
from abc import abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import cached_property

import aiohttp
import sentry_sdk
from aiolimiter import AsyncLimiter
from pydantic import BaseModel
from tenacity import Retrying, stop_after_delay, wait_exponential

from sekoia_automation.exceptions import TriggerConfigurationError
from sekoia_automation.trigger import Trigger
from sekoia_automation.utils import get_annotation_for, get_as_model

from .models.connector import AssetItem, AssetList, DefaultAssetConnectorConfiguration


class AsyncAssetConnector(Trigger):
    """
    Async base class for all asset connectors.

    Asset connectors are used to collect data from
    an asset and send it to the Sekoia.io platform.

    This async version uses AsyncGenerator for asset fetching
    and aiohttp for HTTP requests.
    """

    CONNECTOR_CONFIGURATION_FILE_NAME = "connector_configuration"
    PRODUCTION_BASE_URL = "https://api.sekoia.io"
    OCSF_SCHEMA_VERSION = 1

    configuration: DefaultAssetConnectorConfiguration  # type: ignore[assignment, override]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._latest_time = None
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter: AsyncLimiter | None = None

    @property
    def connector_name(self) -> str:
        """
        Get connector name.

        Returns:
            str:
        """
        return self.__class__.__name__

    @property  # type: ignore[override, no-redef]
    def configuration(self) -> DefaultAssetConnectorConfiguration:
        """
        Get the module configuration.
        Returns:
            DefaultAssetConnectorConfiguration: Connector configuration
        """
        if self._configuration is None:
            try:
                self.configuration = self.module.load_config(
                    self.CONNECTOR_CONFIGURATION_FILE_NAME, "json"
                )
            except FileNotFoundError:
                return super().configuration  # type: ignore[return-value]
        return self._configuration  # type: ignore[return-value]

    @configuration.setter  # type: ignore[override]
    def configuration(self, configuration: dict) -> None:
        """
        Set the module configuration.

        Args:
            configuration: dict
        """
        try:
            self._configuration = get_as_model(
                get_annotation_for(self.__class__, "configuration"), configuration
            )
        except Exception as e:
            raise TriggerConfigurationError(str(e)) from e

        if isinstance(self._configuration, BaseModel):
            sentry_sdk.set_context(
                self.CONNECTOR_CONFIGURATION_FILE_NAME, self._configuration.model_dump()
            )

    @property
    def batch_size(self) -> int:
        """
        Get the batch size from the os env.

        Returns:
            int: Batch size
        """
        if batch := os.getenv("ASSET_CONNECTOR_BATCH_SIZE"):
            return int(batch)
        return self.configuration.batch_size

    @property
    def production_base_url(self) -> str:
        """
        Get the production base URL from os env.

        Returns:
            str: Production base URL
        """
        return os.getenv(
            "ASSET_CONNECTOR_PRODUCTION_BASE_URL", self.PRODUCTION_BASE_URL
        )

    @property
    def frequency(self) -> int:
        """
        Get the frequency for the connector.

        Returns:
            str: Frequency
        """
        if frequency := os.getenv("ASSET_CONNECTOR_FREQUENCY"):
            return int(frequency)
        return self.configuration.frequency

    @staticmethod
    def _retry():
        return Retrying(
            stop=stop_after_delay(3600),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )

    @cached_property
    def _http_header(self) -> dict[str, str]:
        """
        Get the headers for the connector.

        Returns:
            dict: Headers
        """
        return {
            "Authorization": f"Bearer {self.configuration.sekoia_api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"sekoiaio-asset-connector-"
            f"{self.module.connector_configuration_uuid}",
        }

    @cached_property
    def asset_connector_endpoint(self) -> str:
        base = (self.configuration.sekoia_base_url or self.production_base_url).rstrip(
            "/"
        )
        return (
            f"{base}/api/v2/asset-management/asset-connector/"
            f"{self.module.connector_configuration_uuid}"
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        """
        Get the aiohttp session with rate limiting.

        Yields:
            aiohttp.ClientSession: The HTTP session
        """
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._http_header)

        if self._rate_limiter:
            async with self._rate_limiter:
                yield self._session
        else:
            yield self._session

    @staticmethod
    def handle_api_error(error_code: int) -> str:
        if 400 <= error_code < 500:
            return f"Client error - HTTP ({error_code})"
        if 500 <= error_code < 600:
            return f"Server error - HTTP ({error_code})"
        return f"Unexpected error ({error_code})"

    async def post_assets_to_api(
        self, assets: AssetList, asset_connector_api_url: str
    ) -> dict[str, str] | None:
        """
        Post assets to the Sekoia.io asset connector API.
        Args:
            assets (AssetList): List of assets to post.
            asset_connector_api_url (str): URL of the asset connector API.
        Returns:
            dict[str, str] | None: Response from the API or None if an error occurred.
        """
        request_body = assets.model_dump()
        asset_count = len(request_body.get("items", []))

        # Perform the API request with retry logic
        status_code: int | None = None
        response_text: str | None = None
        response_json: dict | None = None

        try:
            for attempt in self._retry():
                with attempt:
                    async with self.session() as session:
                        async with session.post(
                            asset_connector_api_url,
                            json=request_body,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as response:
                            status_code = response.status
                            response_text = await response.text()

                            if status_code == 200:
                                response_json = await response.json()
        except TimeoutError as ex:
            self.log_exception(
                ex,
                message="Timeout while pushing assets to Sekoia.io asset connector API",
            )
            return None

        # Check if response was successfully obtained
        if status_code is None:
            self.log(
                message="Failed to get response from Sekoia.io asset connector API",
                level="error",
            )
            return None

        # Handle non-200 responses
        if status_code != 200:
            await self._log_api_error(status_code, response_text, response_json)
            return None

        # Update checkpoint on success
        await self.update_checkpoint()

        self.log(
            message=f"Successfully posted {asset_count} assets "
            f"to Sekoia.io asset connector API",
            level="info",
        )
        return response_json

    async def _log_api_error(
        self, status_code: int, response_text: str | None, response_json: dict | None
    ) -> None:
        """
        Log API error details from response.

        Args:
            status_code: HTTP status code
            response_text: Raw response text
            response_json: Parsed JSON response if available
        """
        status_error = self.handle_api_error(status_code)

        # Try to extract detailed error message from response
        detail_message = ""
        if response_text:
            try:
                error_data = response_json if response_json else {}
                error_code = error_data.get("code", "")
                error_message = error_data.get("message", "")
                if error_code or error_message:
                    detail_message = f" - {error_code}: {error_message}"
                else:
                    detail_message = f" - {response_text}"
            except Exception:
                detail_message = f" - {response_text}"

        error_msg = (
            f"Error while pushing assets to Sekoia.io - "
            f"{status_error}{detail_message}"
        )
        self.log(message=error_msg, level="error")

    async def push_assets_to_sekoia(self, assets: AssetList) -> None:
        """
        Push assets to the Sekoia.io asset connector API.
        Args:
            assets (AssetList): List of assets to push.
        Returns:
            None: If the assets were successfully pushed.
        """

        if not assets:
            return

        url = self.asset_connector_endpoint

        self.log(
            message=f"Pushing assets to Sekoia.io asset connector API at {url}",
            level="info",
        )

        response = await self.post_assets_to_api(
            assets=assets,
            asset_connector_api_url=url,
        )

        if response is None:
            self.log(
                message=f"Failed to push assets to Sekoia.io "
                f"asset connector API at {url}",
                level="error",
            )
            return

    @abstractmethod
    async def update_checkpoint(self) -> None:
        """
        Update the checkpoint for the connector.
        This method should be implemented in the subclass.
        """
        raise NotImplementedError("This method should be implemented in a subclass")

    @abstractmethod
    async def get_assets(
        self,
    ) -> AsyncGenerator[AssetItem, None]:
        """
        Get assets from the connector.
        It can be a Device, User, Software or a vulnerability asset.
        Yields:
            AssetItem: Asset item ( DeviceOSCFModel, UserOCSFModel, etc. )
        """
        # Make this an async generator by using yield
        # This will never actually execute, but satisfies the type checker
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable, misc]
        raise NotImplementedError("This method should be implemented in a subclass")

    async def asset_fetch_cycle(self) -> None:
        """
        Continuously fetch assets from the connector and push them to Sekoia.io.

        This method runs in a loop until the connector is stopped. On each cycle, it:
          1. Retrieves assets from the connector.
          2. Batches the retrieved assets.
          3. Sends the batch to Sekoia.io.
          4. Waits for the next cycle according to the configured frequency.

        If no assets are fetched during a cycle, the method sleeps for a short
        interval to avoid overwhelming the API with repeated requests.

        Note:
            This implementation assumes the connector provides a checkpointing
            mechanism to prevent re-fetching the same assets.
        """

        self.log(
            message=f"Starting a new asset fetch cycle "
            f"for connector {self.connector_name}",
            level="info",
        )

        # save the starting time processing
        processing_start = time.time()

        assets = []
        total_number_of_assets = 0
        async for asset in self.get_assets():
            assets.append(asset)
            total_number_of_assets += 1

            if len(assets) >= self.batch_size:
                batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
                await self.push_assets_to_sekoia(batch)
                assets = []

        if assets:
            final_batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
            await self.push_assets_to_sekoia(final_batch)

        # save the end time processing
        processing_end = time.time()
        processing_time = processing_end - processing_start

        # Compute the remaining sleeping time.
        # If greater than 0 and no messages where fetched, pause the connector
        delta_sleep = self.frequency - processing_time
        if total_number_of_assets == 0 and delta_sleep > 0:
            self.log(message=f"Next run in the future. Waiting {delta_sleep} seconds")

            await asyncio.sleep(delta_sleep)

    async def async_run(self) -> None:
        """
        Async main loop that continuously fetches and pushes assets.
        """
        try:
            while self.running:
                try:
                    await self.asset_fetch_cycle()
                except Exception as e:
                    self.log_exception(
                        e,
                        message=f"Error while running asset connector "
                        f"{self.connector_name}",
                    )
        finally:
            # Clean up session on exit
            if self._session:
                await self._session.close()
                self._session = None

    def run(self) -> None:
        """
        Synchronous entry point that runs the async main loop.
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.async_run())
