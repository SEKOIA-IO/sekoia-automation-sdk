import hashlib
import json
import os
from abc import abstractmethod
from functools import cached_property

import sentry_sdk
from pydantic import BaseModel
from tenacity import Retrying, stop_after_delay, wait_exponential

from sekoia_automation.exceptions import TriggerConfigurationError
from sekoia_automation.storage import PersistentJSON
from sekoia_automation.trigger import Trigger
from sekoia_automation.utils import get_annotation_for, get_as_model

from .models.connector import DefaultAssetConnectorConfiguration
from .utils import RATE_LIMIT_DEFAULT_WAIT


class AssetConnectorMixin(Trigger):
    """
    Mixin providing shared configuration, HTTP helpers, and schema-fingerprint
    logic for both AssetConnector and AsyncAssetConnector.
    """

    ASSET_SCHEMA_FIELDS_FILE = "asset_schema_fields.json"
    CONNECTOR_CONFIGURATION_FILE_NAME = "connector_configuration"
    PRODUCTION_BASE_URL = "https://api.sekoia.io"
    OCSF_SCHEMA_VERSION = 1

    configuration: DefaultAssetConnectorConfiguration  # type: ignore[override]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._latest_time = None
        self.schema_store = PersistentJSON(
            self.ASSET_SCHEMA_FIELDS_FILE, self.data_path
        )

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

    @property
    def rate_limit_wait(self) -> float:
        """
        Default wait (in seconds) after a 429, used when the response carries no
        usable Retry-After header. Overridable via the
        ASSET_CONNECTOR_RATE_LIMIT_WAIT env variable.

        Returns:
            float: Wait time in seconds
        """
        if wait := os.getenv("ASSET_CONNECTOR_RATE_LIMIT_WAIT"):
            try:
                return float(wait)
            except ValueError:
                self.log(
                    message=(
                        "Invalid ASSET_CONNECTOR_RATE_LIMIT_WAIT value; "
                        "falling back to the default wait"
                    )
                )
        return RATE_LIMIT_DEFAULT_WAIT

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

    @staticmethod
    def handle_api_error(error_code: int) -> str:
        if 400 <= error_code < 500:
            return f"Client error - HTTP ({error_code})"
        if 500 <= error_code < 600:
            return f"Server error - HTTP ({error_code})"
        return f"Unexpected error ({error_code})"

    @abstractmethod
    def get_mapped_fields(self) -> dict[str, str]:
        """
        Return the field mappings declared by this connector as a dict.

        Default empty mapping for backward compatibility: connectors that want
        automatic checkpoint reset on schema change should override this.

        Returns:
            dict[str, str]: Mapping of source API field → OCSF field path.
        """
        raise NotImplementedError(
            "get_mapped_fields must be implemented to support schema-change refetching"
        )

    def _compute_schema_fingerprint(self) -> str:
        """Compute a SHA-256 fingerprint of the connector's declared field mappings.

        The fingerprint changes whenever :meth:`get_mapped_fields` returns a
        different dict, enabling automatic checkpoint detection.

        Returns:
            str: SHA-256 hex digest of the sorted field mapping dict.
        """
        fields = sorted(self.get_mapped_fields().items())
        return hashlib.sha256(json.dumps(fields).encode()).hexdigest()
