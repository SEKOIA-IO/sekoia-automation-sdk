import logging
import re
from abc import abstractmethod
from datetime import datetime
from pathlib import Path
from posixpath import join as urljoin
from traceback import format_exc
from typing import Any
from uuid import uuid4

import orjson
import requests
import sentry_sdk
from pydantic import validate_arguments
from requests import RequestException, Response
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from sekoia_automation.exceptions import (
    MissingActionArgumentError,
    MissingActionArgumentFileError,
    SendEventError,
)
from sekoia_automation.module import LogLevelStr, Module, ModuleItem
from sekoia_automation.storage import UPLOAD_CHUNK_SIZE
from sekoia_automation.utils import chunks, returns


class ActionLogHandler(logging.StreamHandler):
    """Log handler using the action SDK to log messages."""

    def __init__(self, action):
        self._action = action
        super().__init__()

    def emit(self, record):
        try:
            msg = self.format(record)
            self._action.log(msg, record.levelname.lower())
        except Exception:
            pass


class Action(ModuleItem):
    ARGUMENTS_FILE_NAME = "arguments"

    def __init__(self, module: Module | None = None, data_path: Path | None = None):
        super().__init__(module, data_path)

        self._arguments: dict | None = None
        self._logs: list[dict] = []
        self._error: str | None = None
        self._results: dict | None = None
        self._outputs: dict[str, bool] = {}
        self._result_as_file = True
        self._update_secrets = False
        logging.getLogger().addHandler(ActionLogHandler(self))

        # Make sure arguments are validated/coerced by pydantic
        # if a type annotation is defined
        self.run = validate_arguments()(self.run)  # type: ignore

        # If a `results_model` is defined, also validate the return value
        if self.results_model:
            self.run = returns(self.results_model)(self.run)  # type: ignore

        sentry_sdk.set_tag("item_type", "action")

    @property
    def arguments(self) -> dict:
        if self._arguments is None:
            self._arguments = self.module.load_config(self.ARGUMENTS_FILE_NAME, "json")

        return self._arguments

    @property
    def outputs(self) -> dict[str, bool]:
        return self._outputs

    @property
    def logs(self) -> list[dict]:
        return self._logs

    @property
    def results(self) -> dict | None:
        return self._results

    @property
    def error_message(self) -> str | None:
        return self._error

    def execute(self) -> None:
        try:
            self._ensure_data_path_set()
            self.set_task_as_running()
            self._results = self.run(self.arguments)
        except Exception:
            self.error(f"An unexpected error occured: {format_exc()}")
            sentry_sdk.capture_exception()

        self.send_results()

    def log(
        self,
        message: str,
        level: LogLevelStr = "debug",
        only_sentry: bool = True,
        **kwargs,
    ) -> None:
        """Log a message with a specific level."""
        self._logs.append(
            {"date": str(datetime.utcnow()), "level": level, "message": message}
        )
        super().log(message, level, only_sentry=only_sentry, **kwargs)

    def error(self, message: str) -> None:
        """End the execution with an error."""
        self._error = message

    def set_output(self, output: str, activate: bool = True) -> None:
        """Set an output branch status.

        Calling `set_output('malicious', True)` will make sure
        the 'malicious' branch is triggered.
        """
        self._outputs[output] = activate

    @abstractmethod
    def run(self, arguments: Any) -> Any:
        """Method that each action should implement to contain its logic.

        Should return its results as a JSON serializable dict.
        """

    def json_argument(self, name: str, arguments: dict, required: bool = True) -> Any:
        """Get a JSON Argument by direct reference of by reading a file.

        If `name` is inside arguments, returns the value.
        If `name`_path is inside arguments, returns the content of the file
        """
        if arguments.get(name, None):
            self._result_as_file = False
            return arguments[name]
        elif f"{name}_path" in arguments:
            self._result_as_file = True
            filepath = self.data_path.joinpath(arguments[f"{name}_path"])
            if not filepath.is_file():
                raise MissingActionArgumentFileError(filepath)

            with filepath.open("r") as f:
                return orjson.loads(f.read().encode("utf-8"))
        else:
            if required:
                raise MissingActionArgumentError(name)

    def json_result(self, name: str, value: Any) -> dict:
        """Create a result dict with a direct value or inside a file.

        Creates a file by default.
        If the last `json_argument` was resolved using a direct value,
        it returns a direct value instead.
        """
        if self._result_as_file:
            filename = f"{name}-{uuid4()}.json"

            filepath = self.data_path / filename
            with filepath.open("wb") as f:
                data = orjson.dumps(value)
                for chunk in chunks(data, UPLOAD_CHUNK_SIZE):
                    f.write(chunk)

            return {f"{name}_path": filename}
        else:
            return {name: value}

    def format_logs(self):
        if self._logs:
            logs = ""

            for log in self._logs:
                logs += f"{log['date']}: {log['level']}: {log['message']}\n"

            return logs

        return None

    def validate_results(self):
        if self._results is not None:
            # Make sure results are valid
            if isinstance(self._results, dict):
                try:
                    orjson.dumps(self._results)
                    return
                except Exception:
                    sentry_sdk.capture_exception()

            # If we reached this point, the results are invalid
            self._error = f"Results are invalid: '{self._results}'"
            self._results = None

    def set_task_as_running(self):
        """Send a request to indicate the action started."""
        data = {"status": "running"}
        if self.module.has_secrets():
            data["need_secrets"] = True
            response = self._send_request(data, verb="PATCH")
            secrets = {
                k: v
                for k, v in response.json()["module_configuration"]["value"].items()
                if k in self.module.manifest_secrets()
            }
            self.module.set_secrets(secrets)
        else:
            self._send_request(data, verb="PATCH")

    def send_results(self):
        self.validate_results()

        data = {"status": "finished"}

        if self._results is not None:
            data["results"] = self._results

        if self._error:
            data["error"] = self._error

        logs = self.format_logs()
        if logs:
            data["logs"] = logs

        if self._outputs:
            data["outputs"] = self._outputs

        if self._update_secrets:
            data["secrets"] = self.module.secrets

        try:
            self._send_request(data, verb="PATCH")
        except SendEventError as ex:
            if ex.status_code != 409:
                raise ex


class GenericAPIAction(Action):
    # Endpoint Specific Information, should be defined in subclasses
    verb: str
    endpoint: str
    query_parameters: list[str]
    timeout: int = 5

    def get_headers(self):
        headers = {"Accept": "application/json"}
        api_key = self.module.configuration.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def get_url(self, arguments):
        # Specific Informations, should be defined in the Module Configuration
        url = self.module.configuration["base_url"]

        match = re.findall("{(.*?)}", self.endpoint)
        for replacement in match:
            self.endpoint = self.endpoint.replace(
                f"{{{replacement}}}", str(arguments.pop(replacement)), 1
            )

        path = urljoin(url, self.endpoint.lstrip("/"))

        if self.query_parameters:
            query_arguments: list = []

            for k in self.query_parameters:
                if k in arguments:
                    value = arguments.pop(k)
                    if isinstance(value, bool):
                        value = int(value)
                    query_arguments.append(f"{k}={value}")

            path += f"?{'&'.join(query_arguments)}"
        return path

    def log_request_error(self, url: str, arguments: dict, response: Response):
        try:
            content = response.json()
        except ValueError:
            content = response.content
        message = f"HTTP Request failed: {url} with {response.status_code}"
        self.log(
            message,
            level="error",
            url=url,
            arguments=arguments,
            response=content,
            status=response.status_code,
        )
        self.error(message)

    def log_retry_error(self, url: str, arguments: dict):
        message = f"HTTP Request failed after all retries: {url}"
        self.log(
            message,
            level="error",
            url=url,
            arguments=arguments,
        )
        self.error(message)

    def get_body(self, arguments: dict):
        """Get the body to use for the request.

        Data will be loaded from disk for arguments ending by `_path`.
        The key in the body will be cleaned of the suffix.

        i.e. `bundle_path` will become `bundle`
        """
        res = {}
        for key, value in arguments.items():
            if isinstance(value, dict):
                # Recursively set the values
                res[key] = self.get_body(value)
            else:
                try:
                    new_key = key.replace("_path", "")
                    res[new_key] = self.json_argument(new_key, arguments)
                except MissingActionArgumentFileError:
                    # we assume `*_path` is what the API expects so we give it as it is
                    res[key] = value
        return res

    def run(self, arguments) -> dict | None:
        headers = self.get_headers()
        url = self.get_url(arguments)
        body = self.get_body(arguments)

        try:
            for attempt in Retrying(
                stop=stop_after_attempt(10),
                wait=self._wait_param(),
                retry=retry_if_exception_type((RequestException, OSError)),
            ):
                with attempt:
                    response: Response = requests.request(
                        self.verb, url, json=body, headers=headers, timeout=self.timeout
                    )
                    if not response.ok:
                        if (
                            self.verb.lower() == "delete"
                            and response.status_code == 404
                            and attempt.retry_state.attempt_number > 1
                        ):
                            return None
                        if 400 <= response.status_code < 500:
                            self.log_request_error(url, arguments, response)
                            return None
                        response.raise_for_status()
        except RetryError:
            self.log_retry_error(url, arguments)
            return None

        return response.json() if response.status_code != 204 else None

    def _wait_param(self) -> wait_base:
        return wait_exponential(multiplier=2, min=2, max=300)
