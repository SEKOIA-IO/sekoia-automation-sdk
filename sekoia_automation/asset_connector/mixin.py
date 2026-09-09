import hashlib
import json
import os
import time
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
from .utils import (
    RATE_LIMIT_DEFAULT_WAIT,
    RESET_JITTER_DEFAULT_MAX,
    TASK_POLL_INTERVAL_DEFAULT,
    TASK_POLL_TIMEOUT_DEFAULT,
    compute_reset_jitter,
    get_env_float,
)


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
        self._skip_task_wait = False
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

    @property
    def task_poll_interval(self) -> float:
        """
        Delay (in seconds) between two checks of an asset push task status.
        Overridable via the ASSET_CONNECTOR_TASK_POLL_INTERVAL env variable.

        Returns:
            float: Delay in seconds
        """
        return get_env_float(
            "ASSET_CONNECTOR_TASK_POLL_INTERVAL", TASK_POLL_INTERVAL_DEFAULT
        )

    @property
    def task_poll_timeout(self) -> float:
        """
        How long (in seconds) to wait for an asset push task to complete before
        giving up. Overridable via the ASSET_CONNECTOR_TASK_POLL_TIMEOUT env
        variable.

        Returns:
            float: Timeout in seconds
        """
        return get_env_float(
            "ASSET_CONNECTOR_TASK_POLL_TIMEOUT", TASK_POLL_TIMEOUT_DEFAULT
        )

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

    @cached_property
    def task_endpoint(self) -> str:
        base = (self.configuration.sekoia_base_url or self.production_base_url).rstrip(
            "/"
        )
        return f"{base}/api/v1/tasks"

    @staticmethod
    def handle_api_error(error_code: int) -> str:
        if 400 <= error_code < 500:
            return f"Client error - HTTP ({error_code})"
        if 500 <= error_code < 600:
            return f"Server error - HTTP ({error_code})"
        return f"Unexpected error ({error_code})"

    def _disable_task_wait(self) -> None:
        """
        Stop waiting for push tasks until the end of the current fetch cycle.

        A cycle can push thousands of batches. Paying the full timeout on each
        of them once the platform stopped answering would stall the connector
        for days, so the verification is dropped for the rest of the cycle.
        """
        self._skip_task_wait = True

    def _log_task_outcome(self, task_id: str, task: dict, status: str | None) -> None:
        """
        Report the terminal status of an asset push task.

        Args:
            task_id (str): UUID of the task.
            task (dict): Task as returned by the Task API.
            status (str | None): Terminal status of the task.
        """
        if status == "FINISHED":
            self.log(
                message=f"Asset push task {task_id} finished successfully",
                level="info",
            )
            return

        self.log(
            message=(
                f"Asset push task {task_id} ended with the status {status} "
                f"- {task.get('error') or 'no error reported'}"
            ),
            level="error",
        )

    @abstractmethod
    def get_mapped_fields(self) -> dict[str, str]:
        """
        Return the field mappings declared by this connector as a dict.

        Every connector must implement this method. Return an empty dict if
        no field mappings are needed (schema-change detection will be skipped).

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

    @property
    def reset_jitter_max_seconds(self) -> float:
        """
        Maximum jitter (in seconds) applied before the first fetch after a
        checkpoint reset.

        Returns:
            float: Maximum jitter in seconds.
        """
        raw = os.getenv("ASSET_CONNECTOR_RESET_JITTER_MAX")
        if raw is not None:
            try:
                return max(float(raw), 0.0)
            except ValueError:
                self.log(
                    message=(
                        "Invalid ASSET_CONNECTOR_RESET_JITTER_MAX value; "
                        "falling back to the default jitter window"
                    )
                )
        return float(RESET_JITTER_DEFAULT_MAX)

    def _schedule_reset_jitter(self) -> None:
        """
        Schedule a deterministic delay before the next fetch cycle.
        """
        max_seconds = self.reset_jitter_max_seconds

        if max_seconds <= 0:
            return

        seed = self.module.connector_configuration_uuid or self.connector_name
        delay = compute_reset_jitter(seed, max_seconds)
        resume_at = time.time() + delay

        with self.schema_store as store:
            store["reset_resume_at"] = resume_at

        self.log(
            message=(
                f"Checkpoint reset — delaying next fetch by {delay:.0f}s "
            ),
            level="info",
        )

    def _pending_reset_jitter_seconds(self) -> float:
        """
        Return the remaining wait (seconds) before the next fetch may start.
        """
        with self.schema_store as store:
            resume_at = store.get("reset_resume_at")
        if not resume_at:
            return 0.0
        remaining = float(resume_at) - time.time()
        return max(remaining, 0.0)

    def _clear_reset_jitter(self) -> None:
        """Clear any persisted reset-jitter resume timestamp."""
        with self.schema_store as store:
            if "reset_resume_at" in store:
                del store["reset_resume_at"]
