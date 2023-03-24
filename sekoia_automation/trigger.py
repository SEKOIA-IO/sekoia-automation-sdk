import logging
import signal
from abc import abstractmethod
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import cached_property
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import requests
import sentry_sdk
from pydantic import BaseModel
from requests import HTTPError
from tenacity import retry, stop_after_attempt, wait_exponential

from sekoia_automation.exceptions import (
    InvalidDirectoryError,
    ModuleConfigurationError,
    TriggerConfigurationError,
)
from sekoia_automation.module import Module, ModuleItem
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
    LIVENESS_PORT_FILE_NAME = "liveness_port"

    def __init__(self, module: Module | None = None, data_path: Path | None = None):
        super().__init__(module, data_path)
        logging.basicConfig(level=logging.INFO)
        self._configuration: dict | BaseModel | None = None
        self._error_count = 0
        self._last_events = datetime.utcnow()
        sentry_sdk.set_tag("item_type", "trigger")
        self._secrets: dict[str, Any] = {}
        self._stop_event = Event()

        # Register signal to terminate thread
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        self._liveness_server = None

    def _get_secrets_from_server(self) -> dict[str, Any]:
        """Calls the API to fetch this trigger's secrets

        If self.module has no secrets configured, we don't do anything

        :return: A dict mapping the configuration's secrets to their value
        :rtype: dict[str, Any]
        """
        secrets = {}
        if self.module.has_secrets():
            try:
                response = requests.get(
                    self.callback_url.replace("/callback", "/secrets"),
                    headers=self._headers,
                    timeout=30,
                )
                response.raise_for_status()
                secrets = response.json()["value"]
            except HTTPError as exception:
                self._log_request_error(exception)
        return secrets

    def stop(self, *args, **kwargs):  # noqa: ARG002
        """
        Engage the trigger exit
        """
        # Exit signal received, asking the processor to stop
        self._stop_event.set()

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
            self.log(str(e), "critical")
        except Exception as e:
            self.log_exception(e)
            # Increase the consecutive error count
            self._error_count += 1

            # If there was more than 5 errors without any event being sent,
            # consider the error to be critical
            level = "error"
            if self._error_count >= 5:
                level = "critical"

            # Make sure the error is recorded and available to the user
            self.log(str(e), level=level)

    def execute(self) -> None:
        self._ensure_data_path_set()
        # Always restart the trigger, except if the error seems to be unrecoverable
        self._secrets = self._get_secrets_from_server()
        while self._error_count < 5:
            self._execute_once()

    def _rm_tree(self, path: Path):
        """Delete a directory and its children.

        :param Path path: The directory to delete
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
    def _ensure_directory(self, directory: str | None, remove_directory: bool = False):
        """Make sure the directory exists."""
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
    ):
        """Send a normalized event to SEKOIA.IO so that it triggers a playbook run."""
        # Reset the consecutive error count
        self._error_count = 0
        self._last_events = datetime.utcnow()
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
    ):
        """Send an event to SEKOIA.IO so that it triggers playbook runs.

        Makes sure `results_model` is used to validate/coerce the event if present
        """
        return self.send_normalized_event(
            event_name,
            validate_with_model(self.results_model, event),
            directory,
            remove_directory,
        )

    @cached_property
    def _log_url(self):
        return self.callback_url.replace("/callback", "/logs")

    # Try to send the log record to the API
    # If it can't be done, give up after 10 attempts and capture the logging error
    @retry(
        wait=wait_exponential(max=10),
        stop=stop_after_attempt(10),
        retry_error_callback=capture_retry_error,
    )
    def log(self, message: str, level: str = "info", *args, **kwargs) -> None:
        data = {
            "logs": [
                {
                    "date": datetime.utcnow().isoformat(),
                    "level": level,
                    "message": message,
                }
            ]
        }
        response = requests.request(
            "POST", self._log_url, json=data, headers=self._headers, timeout=30
        )
        response.raise_for_status()

        super().log(message, level, *args, **kwargs)

        # A critical error should stop the process
        # and make it clear that it was its choice to terminate
        if level == "critical":
            exit(0)

    @abstractmethod
    def run(self) -> None:
        """Method that each trigger should implement to contain its logic.

        Should usually be an infinite loop, calling send_event when relevant.
        """

    def start_monitoring(self):
        port = (
            self.module.load_config(self.LIVENESS_PORT_FILE_NAME, non_exist_ok=True)
            or 8000
        )
        LivenessHandler.trigger = self
        self._liveness_server = HTTPServer(("", int(port)), LivenessHandler)
        Thread(target=self._liveness_server.serve_forever, daemon=True).start()

    def stop_monitoring(self):
        if self._liveness_server:
            self._liveness_server.shutdown()

    def is_alive(self) -> bool:
        """
        Return whether the trigger appears to be alive.

        This is based on the date of the last sent events
        compared to the `seconds_without_events` threshold.
        """
        delta = datetime.utcnow() - self._last_events
        if self.seconds_without_events <= 0 or delta < timedelta(
            seconds=self.seconds_without_events
        ):
            return True

        self.log(
            message=f"The trigger didn't send events for {delta.seconds} seconds, "
            f"it will be restarted.",
            level="error",
        )
        return False


class LivenessHandler(BaseHTTPRequestHandler):
    trigger: Trigger

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self.send(200 if self.trigger.is_alive() else 500)
            return
        self.send(404)

    def send(self, status_code: int):
        self.send_response(status_code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(f'{{"status_code": {status_code}}}'.encode())
