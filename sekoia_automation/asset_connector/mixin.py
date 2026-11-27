import hashlib
import json
import math
import os
import time
from abc import abstractmethod
from functools import cached_property

import sentry_sdk
from pydantic import BaseModel, ValidationError
from tenacity import Retrying, stop_after_delay, stop_any, wait_exponential

from sekoia_automation.configuration.exception import MissingConfigurationError
from sekoia_automation.exceptions import TriggerConfigurationError
from sekoia_automation.storage import PersistentJSON
from sekoia_automation.trigger import Trigger
from sekoia_automation.utils import get_annotation_for, get_as_model

from .models.connector import DefaultAssetConnectorConfiguration
from .utils import (
    RATE_LIMIT_DEFAULT_WAIT,
    RESET_JITTER_DEFAULT_MAX,
    RESET_JITTER_HEARTBEAT_INTERVAL,
    TASK_POLL_INTERVAL_DEFAULT,
    TASK_POLL_TIMEOUT_DEFAULT,
    compute_reset_jitter,
    get_env_float,
)


class AssetConnectorBase(Trigger):
    """
    Base class providing shared configuration, HTTP helpers, and
    schema-fingerprint logic for both AssetConnector and AsyncAssetConnector.
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
        self._batch_rejected = False
        self.cycle_stats = {"fetched": 0, "pushed_batches": 0, "failed_batches": 0}
        # (env variable, raw value) pairs already reported as invalid
        self._warned_invalid_env: set[tuple[str, str]] = set()
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
            except MissingConfigurationError:
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
        except ValidationError as e:
            # The input holds the Sekoia.io API key: keep it out of the error
            raise TriggerConfigurationError(
                str(e.errors(include_url=False, include_input=False))
            ) from None
        except Exception as e:
            raise TriggerConfigurationError(str(e)) from e

        if isinstance(self._configuration, BaseModel):
            sentry_sdk.set_context(
                self.CONNECTOR_CONFIGURATION_FILE_NAME,
                self._configuration.model_dump(exclude={"sekoia_api_key"}),
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

    def _warn_invalid_env_once(self, name: str, raw: str, fallback: str) -> None:
        """
        Log that an env variable holds an invalid value, once per value.

        The properties reading these variables are evaluated on every batch or
        cycle; values are not cached so that platform configuration changes
        still apply, hence this deduplication of the warning.
        """
        if (name, raw) in self._warned_invalid_env:
            return
        self._warned_invalid_env.add((name, raw))
        self.log(message=f"Invalid {name} value; falling back to {fallback}")

    @property
    def batch_push_interval(self) -> float:
        """
        Delay (in seconds) to wait between two consecutive batch pushes within
        a single fetch cycle. Spacing pushes out avoids tripping the platform
        rate limiter (HTTP 429) when a cycle produces many batches.

        Read from the connector configuration (so it can be changed from the
        platform), with an optional ``ASSET_CONNECTOR_BATCH_PUSH_INTERVAL`` env
        override.

        Returns:
            float: Delay in seconds (never negative).
        """
        if raw := os.getenv("ASSET_CONNECTOR_BATCH_PUSH_INTERVAL"):
            try:
                interval = float(raw)
            except ValueError:
                interval = math.nan
            if math.isfinite(interval):
                return max(interval, 0.0)
            self._warn_invalid_env_once(
                "ASSET_CONNECTOR_BATCH_PUSH_INTERVAL", raw, "the configured value"
            )
        interval = self.configuration.batch_push_interval
        return max(interval, 0.0) if math.isfinite(interval) else 0.0

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

    def _retry(self):
        return Retrying(
            stop=stop_any(stop_after_delay(3600), lambda _: not self.running),
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

    def _compute_schema_fingerprint(self, fields: dict[str, str] | None = None) -> str:
        """Compute a SHA-256 fingerprint of the connector's declared field mappings.

        The fingerprint changes whenever :meth:`get_mapped_fields` returns a
        different dict, enabling automatic checkpoint detection.

        Args:
            fields: Field mappings to fingerprint. Defaults to the mappings
                returned by :meth:`get_mapped_fields`.

        Returns:
            str: SHA-256 hex digest of the sorted field mapping dict.
        """
        if fields is None:
            fields = self.get_mapped_fields()
        return hashlib.sha256(json.dumps(sorted(fields.items())).encode()).hexdigest()

    def _read_schema_store(self) -> dict:
        """
        Read the schema store without writing it back.

        ``with self.schema_store`` rewrites the file every time it exits, even
        when nothing changed. Reads go through this helper so that only real
        changes are persisted.
        """
        self.schema_store.load()
        return self.schema_store._data

    def _detect_schema_change(self) -> tuple[dict[str, str], bool] | None:
        """Compare the current field-mapping fingerprint against the stored one.

        Returns:
            ``None`` when there is nothing to do: no declared mapping, or a
            mapping identical to the stored one. Otherwise the current field
            mappings to persist with :meth:`_save_schema`, and whether the
            checkpoint must be reset first. On the very first run (no
            fingerprint stored yet) no reset is needed.
        """
        current_fields = self.get_mapped_fields()
        # No declared mapping (default for connectors that don't override
        # get_mapped_fields): schema-change detection is inert, skip entirely.
        if not current_fields:
            return None

        store = self._read_schema_store()
        stored_fingerprint = store.get("fingerprint")
        stored_fields: dict[str, str] = store.get("fields", {})

        if stored_fingerprint == self._compute_schema_fingerprint(current_fields):
            return None

        if stored_fingerprint is None:
            return current_fields, False

        diff = {
            "added": {
                k: v for k, v in current_fields.items() if k not in stored_fields
            },
            "removed": {
                k: v for k, v in stored_fields.items() if k not in current_fields
            },
            "changed": {
                k: {"from": stored_fields[k], "to": v}
                for k, v in current_fields.items()
                if k in stored_fields and stored_fields[k] != v
            },
        }
        self.log(
            message=(
                "Field mapping change detected — "
                f"{diff}. Resetting checkpoint to re-fetch all assets."
            ),
            level="info",
        )
        return current_fields, True

    def _save_schema(self, fields: dict[str, str]) -> None:
        """Persist the field mappings and their fingerprint."""
        with self.schema_store as store:
            store["fingerprint"] = self._compute_schema_fingerprint(fields)
            store["fields"] = fields

    @property
    def reset_jitter_max_seconds(self) -> float:
        """
        Maximum jitter (in seconds) applied before the first fetch after a
        checkpoint reset. Overridable via the ASSET_CONNECTOR_RESET_JITTER_MAX
        env variable; ``0`` disables the jitter.

        Returns:
            float: Maximum jitter in seconds.
        """
        if raw := os.getenv("ASSET_CONNECTOR_RESET_JITTER_MAX"):
            try:
                max_seconds = float(raw)
            except ValueError:
                max_seconds = math.nan
            # inf would wait forever and nan would silently disable the jitter
            if math.isfinite(max_seconds):
                return max(max_seconds, 0.0)
            self._warn_invalid_env_once(
                "ASSET_CONNECTOR_RESET_JITTER_MAX", raw, "the default jitter window"
            )
        return float(RESET_JITTER_DEFAULT_MAX)

    def _schedule_reset_jitter(self) -> None:
        """
        Schedule a delay before the next fetch cycle.

        The delay is derived from the connector configuration UUID, so each
        configuration of a connector restarts at its own moment.
        """
        max_seconds = self.reset_jitter_max_seconds

        if max_seconds <= 0:
            return

        delay = compute_reset_jitter(
            self.module.connector_configuration_uuid, max_seconds
        )

        with self.schema_store as store:
            store["reset_resume_at"] = time.time() + delay

        self.log(
            message=f"Checkpoint reset — delaying next fetch by {delay:.0f}s",
            level="info",
        )

    def _pending_reset_jitter_seconds(self) -> float:
        """
        Return the remaining wait (seconds) before the next fetch may start.
        """
        resume_at = self._read_schema_store().get("reset_resume_at")
        if not resume_at:
            return 0.0
        remaining = float(resume_at) - time.time()
        # Bound by the current max: the window may have shrunk or the clock gone back
        return min(max(remaining, 0.0), self.reset_jitter_max_seconds)

    def _wait_reset_jitter(self, pending: float) -> bool:
        """
        Wait out the reset jitter, marking the connector as alive meanwhile.

        The wait can last hours: without heartbeats, the liveness probe would
        restart the connector, which would resume the same wait and crash-loop
        until the jitter window elapses.

        Args:
            pending: Seconds to wait.

        Returns:
            bool: ``True`` once the wait is over, ``False`` if the connector
            was stopped meanwhile.
        """
        remaining = pending
        while remaining > 0:
            self.heartbeat()
            timeout = min(remaining, RESET_JITTER_HEARTBEAT_INTERVAL)
            if self._stop_event.wait(timeout) or not self.running:
                return False
            remaining -= timeout
        return True

    def _clear_reset_jitter(self) -> None:
        """Clear the persisted reset-jitter resume timestamp, if any."""
        if "reset_resume_at" not in self._read_schema_store():
            return
        with self.schema_store as store:
            del store["reset_resume_at"]
