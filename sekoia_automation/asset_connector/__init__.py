import os
import time
from abc import abstractmethod
from collections.abc import Generator
from functools import cached_property

import requests
import sentry_sdk
from pydantic import BaseModel
from requests import Response
from tenacity import Retrying, stop_after_delay, wait_exponential

from sekoia_automation.exceptions import TriggerConfigurationError
from sekoia_automation.trigger import Trigger
from sekoia_automation.utils import get_annotation_for, get_as_model

from .models.connector import AssetItem, AssetList, DefaultAssetConnectorConfiguration


class AssetConnector(Trigger):
    """
    Base class for all asset connectors.

    Asset connectors are used to collect data from
    an asset and send it to the Sekoia.io platform.
    """

    CONNECTOR_CONFIGURATION_FILE_NAME = "connector_configuration"
    PRODUCTION_BASE_URL = "https://api.sekoia.io"
    ASSET_BATCH_SIZE = 1000
    OCSF_SCHEMA_VERSION = 1

    configuration: DefaultAssetConnectorConfiguration  # type: ignore[override]

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
        return int(os.getenv("ASSET_CONNECTOR_BATCH_SIZE", self.ASSET_BATCH_SIZE))

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
    def _http_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self._http_header)
        return session

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

    @staticmethod
    def handle_api_error(error_code: int) -> str:
        error = {
            400: "Invalid request format",
            401: "Unauthorized access",
            404: "Connector not found",
        }
        return error.get(error_code, "An unknown error occurred")

    def post_assets_to_api(
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

        # Serialize the assets to a dictionary
        assets_object_to_dict = assets.model_dump()

        request_body = assets_object_to_dict

        try:
            for attempt in self._retry():
                with attempt:
                    res: Response = self._http_session.post(
                        asset_connector_api_url,
                        json=request_body,
                        timeout=30,
                    )
        except requests.Timeout as ex:
            self.log_exception(
                ex,
                message="Timeout while pushing assets to Sekoia.io asset connector API",
            )
            return None

        if res.status_code != 200:
            error_message = self.handle_api_error(res.status_code)
            self.log(
                message=f"Error while pushing assets to Sekoia.io: {error_message}",
                level="error",
            )
            return None

        self.log(
            message=rf"Successfully posted {len(assets_object_to_dict)} assets\ "
            f"to Sekoia.io asset connector API",
            level="info",
        )
        return res.json()

    def push_assets_to_sekoia(self, assets: AssetList) -> None:
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

        response = self.post_assets_to_api(
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
    def get_assets(
        self,
    ) -> Generator[AssetItem, None, None]:
        """
        Get assets from the connector.
        It can be a Device, User, Software or a vulnerability asset.
        Yields:
            AssetItem: Asset item ( DeviceOSCFModel, UserOCSFModel, etc. )
        """
        raise NotImplementedError("This method should be implemented in a subclass")

    def asset_fetch_cycle(self) -> None:
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
        for asset in self.get_assets():
            assets.append(asset)
            total_number_of_assets += 1

            if len(assets) >= self.batch_size:
                batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
                self.push_assets_to_sekoia(batch)
                assets = []

        if assets:
            final_batch = AssetList(version=self.OCSF_SCHEMA_VERSION, items=assets)
            self.push_assets_to_sekoia(final_batch)

        # save the end time processing
        processing_end = time.time()
        processing_time = processing_end - processing_start

        # Compute the remaining sleeping time.
        # If greater than 0 and no messages where fetched, pause the connector
        delta_sleep = self.frequency - processing_time
        if total_number_of_assets == 0 and delta_sleep > 0:
            self.log(message=f"Next run in the future. Waiting {delta_sleep} seconds")

            time.sleep(delta_sleep)

    def run(self) -> None:
        while self.running:
            try:
                self.asset_fetch_cycle()
            except Exception as e:
                self.log_exception(
                    e,
                    message=f"Error while running asset connector "
                    f"{self.connector_name}",
                )
