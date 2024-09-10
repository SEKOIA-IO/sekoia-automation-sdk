import json
import signal
from abc import abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import requests
import sentry_sdk
from botocore.exceptions import ClientError, ConnectionError, HTTPClientError
from pydantic import BaseModel
from requests import HTTPError
from tenacity import retry, stop_after_attempt, wait_exponential

from sekoia_automation.exceptions import (
    InvalidDirectoryError,
    ModuleConfigurationError,
    SendEventError,
    TriggerConfigurationError,
)
from sekoia_automation.metrics import PrometheusExporterThread, make_exporter
from sekoia_automation.module import LogLevelStr, Module, ModuleItem
from sekoia_automation.timer import RepeatedTimer
from sekoia_automation.utils import (
    capture_retry_error,
    get_annotation_for,
    get_as_model,
    validate_with_model,
)


class Trigger(ModuleItem):
    configuration_model: BaseModel | None = None

    TRIGGER_CONFIGURATION_FILE_NAME = "trigger_configuration"

    # Number of seconds without sent events after which
    # the trigger is considered in error.
    # 0 means that the trigger is never considered in error
    seconds_without_events = 0
    # Limit in seconds since the last heartbeat to consider the trigger in error.
    # 0 means that the trigger is never considered in error
    last_heartbeat_threshold = 0
    LIVENESS_PORT_FILE_NAME = "liveness_port"
    METRICS_PORT_FILE_NAME = "metrics_port"

    LOGS_MAX_BATCH_SIZE = 50
    LOGS_MAX_DELTA = 5  # seconds

    # Time to wait for stop event to be received
    _STOP_EVENT_WAIT = 120

    def __init__(self, module: Module | None = None, data_path: Path | None = None):
        super().__init__(module, data_path)
        self._configuration: dict | BaseModel | None = None
        self._error_count = 0
        self._last_events_time = datetime.utcnow()
        self._last_heartbeat = datetime.utcnow()
        self._startup_time = datetime.utcnow()
        sentry_sdk.set_tag("item_type", "trigger")
        self._secrets: dict[str, Any] = {}
        self._stop_event = Event()
        self._critical_log_sent = False
        self._logs: list[dict] = []

        self._logs_timer = RepeatedTimer(self.LOGS_MAX_DELTA, self._send_logs_to_api)

        # Register signal to terminate thread
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        self._liveness_server = None
        self._exporter = None

    @retry(
        reraise=True,
        wait=wait_exponential(max=10),
        stop=stop_after_attempt(10),
        retry_error_callback=capture_retry_error,
    )
    def _get_secrets_from_server(self) -> dict[str, Any]:
        """
        Calls the API to fetch this trigger's secrets.

        If `self.module` has no secrets configured, we don't do anything.

        Returns:
            dict[str, Any]:
        """
        secrets = {}
        if self.module.has_secrets():
            try:
                response = requests.get(
                    self.secrets_url,
                    headers=self._headers,
                    timeout=30,
                )
                response.raise_for_status()
                secrets = response.json()["value"]
            except HTTPError as exception:
                self._log_request_error(exception)
        return secrets

    def stop(self, *args, **kwargs) -> None:  # noqa: ARG002
        """
        Engage the trigger exit
        """
        self._stop_event.set()
        self._logs_timer.stop()

    @property
    def running(self) -> bool:
        """
        Return if the trigger is still active or not
        """
        return not self._stop_event.is_set()

    @property
    def configuration(self) -> dict | BaseModel | None:
        if self._configuration is None:
            self.configuration = self.module.load_config(
                self.TRIGGER_CONFIGURATION_FILE_NAME, "json"
            )

        return self._configuration

    @configuration.setter
    def configuration(self, configuration: dict) -> None:
        """
        Set the trigger configuration.

        Args:
            configuration: dict
        """
        try:
            self._configuration = get_as_model(
                get_annotation_for(self.__class__, "configuration"), configuration
            )
        except Exception as e:
            raise TriggerConfigurationError(str(e))

        if isinstance(self._configuration, BaseModel):
            sentry_sdk.set_context("trigger_configuration", self._configuration.dict())
        elif self._configuration:
            sentry_sdk.set_context("trigger_configuration", self._configuration)

    def _execute_once(self) -> None:
        try:
            self.run()
        # Configuration errors are considered to be critical
        except (TriggerConfigurationError, ModuleConfigurationError) as e:
            self.log_exception(e)
            self.log("Configuration error", "critical")
        except (ConnectionError, HTTPClientError) as ex:
            # Error while communicating with the S3 storage
            # Don't increment the error count because this is an internal issue
            self.log_exception(ex)
        except ClientError as ex:
            self._handle_s3_exception(ex)
        except SendEventError as ex:
            self._handle_send_event_exception(ex)
        except Exception as ex:
            self._handle_trigger_exception(ex)
        if self._critical_log_sent:
            # Prevent the trigger from running
            # and creating other errors until it is stopped
            self._stop_event.wait(self._STOP_EVENT_WAIT)

    def execute(self) -> None:
        self._ensure_data_path_set()
        # Always restart the trigger, except if the error seems to be unrecoverable
        self._secrets = self._get_secrets_from_server()
        self.module.set_secrets(self._secrets)
        self._logs_timer.start()
        try:
            while not self._stop_event.is_set():
                try:
                    self._execute_once()
                except Exception:  # pragma: no cover
                    # Exception are handled in `_execute_once` but in case
                    # an error occurred while handling an error we catch everything
                    # i.e. An error occurred while sending logs to Sekoia.io
                    pass
        finally:
            # Send remaining logs if any
            self._send_logs_to_api()

    def heartbeat(self):
        """
        Mark the trigger as alive.
        """
        self._last_heartbeat = datetime.utcnow()

    def _rm_tree(self, path: Path) -> None:
        """
        Delete a directory and its children.

        Args:
            path: Path: The directory to delete
        """
        # iter over children
        for child in path.iterdir():
            # if file, remove it
            if child.is_file():
                child.unlink()
            else:
                # explore the directory to remove children
                self._rm_tree(child)

        # remove the directory (only ones that still exists)
        if path.exists():
            path.rmdir()

    @contextmanager
    def _ensure_directory(
        self, directory: str | None = None, remove_directory: bool = False
    ) -> Generator[str | None, None, None]:
        """
        Make sure the directory exists.

        Args:
            directory: str | None
            remove_directory: bool

        Raises:
            InvalidDirectoryError: If the directory doesn't exist

        Returns:
            Generator[str | None, None, None]:
        """
        if directory:
            # This will work for both relative and absolute path
            directory_path = self.data_path.joinpath(directory)
            if not directory_path.is_dir():
                raise InvalidDirectoryError()

            # Make sure we send a relative directory
            try:
                yield directory_path.relative_to(self.data_path).as_posix()
            finally:
                # Remove directory if needed
                if remove_directory:
                    self._rm_tree(directory_path)
        else:
            yield None

    def send_normalized_event(
        self,
        event_name: str,
        event: dict,
        directory: str | None = None,
        remove_directory: bool = False,
    ) -> None:
        """
        Send a normalized event to Sekoia.io so that it triggers a playbook run.

        Args:
            event_name: str
            event: dict
            directory: str | None
            remove_directory: bool
        """
        # Reset the consecutive error count
        self._error_count = 0
        self._last_events_time = datetime.utcnow()
        data = {"name": event_name, "event": event}

        with self._ensure_directory(directory, remove_directory) as directory_location:
            if directory_location:
                data["directory"] = directory_location

            self._send_request(data)

    def send_event(
        self,
        event_name: str,
        event: dict,
        directory: str | None = None,
        remove_directory: bool = False,
    ) -> None:
        """
        Send an event to Sekoia.io so that it triggers playbook runs.

        Makes sure `results_model` is used to validate/coerce the event if present

        Args:
            event_name: str
            event: dict
            directory: str | None
            remove_directory: bool
        """
        return self.send_normalized_event(
            event_name,
            validate_with_model(self.results_model, event),
            directory,
            remove_directory,
        )

    def log_exception(self, exception: Exception, **kwargs):
        super().log_exception(exception, **kwargs)
        # Send error to the API
        message = kwargs.get("message", "An exception occurred")
        self.log(f"{message}\n{exception}", level="error", propagate=False)

    def log(self, message: str, level: LogLevelStr = "info", *args, **kwargs) -> None:
        if level == "critical" and self._critical_log_sent:
            #  Prevent sending multiple critical errors
            level = "error"

        if kwargs.pop("propagate", True):
            super().log(message, level, *args, **kwargs)

        self._logs.append(
            {
                "date": datetime.utcnow().isoformat(),
                "level": level,
                "message": message,
            }
        )
        if (
            level in ["error", "critical"]  # Don't wait for error or critical logs
            or len(self._logs) >= self.LOGS_MAX_BATCH_SIZE  # batch is full
        ):
            self._send_logs_to_api()

        if level == "critical":
            self._critical_log_sent = True

    @retry(
        reraise=True,
        wait=wait_exponential(max=10),
        stop=stop_after_attempt(10),
        retry_error_callback=capture_retry_error,
    )
    def _send_logs_to_api(self):
        if not self._logs:
            return
        # Clear self._logs, so we won't lose logs that are added while sending
        logs = self._logs
        self._logs = []
        try:
            data = {"logs": logs}
            response = requests.request(
                "POST", self.logs_url, json=data, headers=self._headers, timeout=30
            )
            response.raise_for_status()
        except Exception:
            # If the request failed, we add the logs back to the list
            self._logs.extend(logs)
            raise

    @abstractmethod
    def run(self) -> None:
        """
        Method that each trigger should implement to contain its logic.

        Should usually be an infinite loop, calling send_event when relevant.
        """

    def start_monitoring(self):
        # start the liveness server
        port = (
            self.module.load_config(self.LIVENESS_PORT_FILE_NAME, non_exist_ok=True)
            or 8000
        )
        LivenessHandler.trigger = self
        self._liveness_server = HTTPServer(("", int(port)), LivenessHandler)
        Thread(target=self._liveness_server.serve_forever, daemon=True).start()

        # start the metrics exporter
        metrics_port = (
            self.module.load_config(self.METRICS_PORT_FILE_NAME, non_exist_ok=True)
            or 8020
        )
        self._exporter = make_exporter(PrometheusExporterThread, int(metrics_port))
        self._exporter.start()

    def stop_monitoring(self):
        if self._liveness_server:
            self._liveness_server.shutdown()
            self._liveness_server = None

        # Stop the exporter
        if self._exporter:
            self._exporter.stop()
            self._exporter = None

    def is_alive(self) -> bool:
        """
        Return whether the trigger appears to be alive.

        This is based on the date of the last sent events
        compared to the `seconds_without_events` threshold
        or to the last heartbeat the trigger produced
        """
        if not self._events_alive():
            return False
        if not self._heartbeat_alive():
            return False
        return True

    def _events_alive(self) -> bool:
        delta = datetime.utcnow() - self._last_events_time
        if self.seconds_without_events <= 0 or delta < timedelta(
            seconds=self.seconds_without_events
        ):
            return True

        delta_seconds = delta.total_seconds()
        self.log(
            message=f"The trigger didn't send events for {delta_seconds} seconds, "
            "it will be restarted.",
            level="error",
        )
        return False

    def _heartbeat_alive(self) -> bool:
        heartbeat_delta = datetime.utcnow() - self._last_heartbeat
        if self.last_heartbeat_threshold <= 0 or heartbeat_delta < timedelta(
            seconds=self.last_heartbeat_threshold
        ):
            return True

        delta_seconds = heartbeat_delta.total_seconds()
        self.log(
            message=f"The trigger didn't produce heartbeat for {delta_seconds} seconds,"
            " it will be restarted.",
            level="error",
        )
        return False

    def liveness_context(self) -> dict:
        """Context returned when the health endpoint is requested."""
        return {
            "last_events_time": self._last_events_time.isoformat(),
            "last_heartbeat": self._last_heartbeat.isoformat(),
            "seconds_without_events_threshold": self.seconds_without_events,
            "last_heartbeat_threshold": self.last_heartbeat_threshold,
            "error_count": self._error_count,
        }

    def _handle_trigger_exception(self, e: Exception):
        self.log_exception(e)
        # Increase the consecutive error count
        self._error_count += 1

        # If there was more than 5 errors without any event being sent,
        # log a critical error.
        if self._is_error_critical():
            self.log(
                f"{self._error_count} successive uncatched errors", level="critical"
            )

    def _is_error_critical(self) -> bool:
        """
        Whether the next error should be considered as critical.

        A log can be critical if we got at least 5 consecutive errors
        and no critical logs have been already sent.
        Then a graceful period applies. This period depends on the time
        the trigger has been running.

        A trigger running for:
            * 1 hour  would exit after 12 minutes
            * 12 hours would exit after 3 hours
            * 1 day would exit after 5 hours
            * 2 days would exit after 10 hours
            * >=5 days would exit after 24 hours
        """
        if self._error_count < 5 or self._critical_log_sent:
            return False

        delta_since_last_event = (
            datetime.utcnow() - self._last_events_time
        ).total_seconds()
        delta_since_startup = min(
            datetime.utcnow() - self._startup_time, timedelta(days=5)
        ).total_seconds()
        if delta_since_startup < 1800:
            # Graceful 30 minutes period at startup
            return False
        return delta_since_startup / 5 <= delta_since_last_event

    def _handle_s3_exception(self, ex: ClientError):
        """
        Handle errors coming from the S3 storage
        """
        error_code = ex.response.get("Error", {}).get("Code", 500)
        try:
            status_code = int(error_code)
        except ValueError:
            if error_code in [
                "InternalError",
                "ServiceUnavailable",
                "SlowDown",
                "503 SlowDown",
                "InsufficientCapacity",
            ]:
                status_code = 500
            else:
                status_code = 400
        if status_code < 500:
            # Let the exception follow the "normal flow"
            return self._handle_trigger_exception(ex)

        # We don't increment the error count because this is an internal issue
        self.log_exception(ex)

    def _handle_send_event_exception(self, ex: SendEventError):
        if ex.status_code >= 500:
            # We don't increment the error count because this is an internal issue
            self.log_exception(ex)
            return
        return self._handle_trigger_exception(ex)


class LivenessHandler(BaseHTTPRequestHandler):
    trigger: Trigger

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self.send(
                200 if self.trigger.is_alive() else 500, self.trigger.liveness_context()
            )
            return
        self.send(404, {"status_code": 404, "reason": "Endpoint doesn't exist"})

    def send(self, status_code: int, content: dict):
        self.send_response(status_code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(content).encode())
