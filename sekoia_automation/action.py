import json
import logging
import re
from abc import abstractmethod
from datetime import UTC, datetime
from numbers import Real
from pathlib import Path
from posixpath import join as urljoin
from traceback import format_exc
from typing import Any
from uuid import uuid4

import orjson
import requests
import sentry_sdk
from aiohttp import BasicAuth
from pydantic import validate_call
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
from sekoia_automation.typing import SupportedAuthentications
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

        # Make sure arguments are validated/coerced by Pydantic
        # if a type annotation is defined
        self.run = validate_call(self.run)  # type: ignore

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
            self.error(f"An unexpected error occurred: {format_exc()}")
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
            {
                "date": str(datetime.now(UTC).replace(tzinfo=None)),
                "level": level,
                "message": message,
                **kwargs,
            }
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
        if arguments.get(name, None) is not None:
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
                log = log.copy()
                formatted = (
                    f"{log.pop('date')}: {log.pop('level')}: {log.pop('message')}"
                )
                if log:
                    formatted += f" - Context: {json.dumps(log)}"
                logs += f"{formatted}\n"

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

            # Add a check for list
            if isinstance(self._results, list):
                for result in self._results:
                    if isinstance(result, dict):
                        try:
                            orjson.dumps(result)
                        except Exception:
                            sentry_sdk.capture_exception()
                return

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
    base_url = ""
    verb: str
    endpoint: str
    query_parameters: list[str]
    timeout: int = 5
    strip_empty_string_fields: tuple[str, ...] = ()
    retry_without_fields_on_failure: tuple[str, ...] = ()
    skip_request_if_body_empty: bool = False

    authentication: SupportedAuthentications = None
    auth_header: str | None = None
    auth_query_param: str | None = None

    @staticmethod
    def _normalize_timeout_value(value: Any) -> float | tuple[float, float] | None:
        if isinstance(value, Real):
            return float(value)

        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(v, Real) for v in value)
        ):
            return (float(value[0]), float(value[1]))

        return None

    def get_timeout(self) -> float | tuple[float, float]:
        configured_connect_timeout = self._module_configuration_value(
            "http_connect_timeout"
        )
        configured_read_timeout = self._module_configuration_value("http_read_timeout")
        if (
            configured_connect_timeout is not None
            and configured_read_timeout is not None
        ):
            configured_pair = self._normalize_timeout_value(
                (configured_connect_timeout, configured_read_timeout)
            )
            if configured_pair is not None:
                return configured_pair

            self.log(
                (
                    "Invalid HTTP timeout pair in module configuration, "
                    "falling back to action timeout"
                ),
                level="warning",
                connect_timeout=configured_connect_timeout,
                read_timeout=configured_read_timeout,
            )

        configured_timeout = self._module_configuration_value("http_timeout")
        if configured_timeout is not None:
            normalized_timeout = self._normalize_timeout_value(configured_timeout)
            if normalized_timeout is not None:
                return normalized_timeout

            self.log(
                (
                    "Invalid HTTP timeout in module configuration, "
                    "falling back to action timeout"
                ),
                level="warning",
                http_timeout=configured_timeout,
            )

        normalized_action_timeout = self._normalize_timeout_value(self.timeout)
        if normalized_action_timeout is not None:
            return normalized_action_timeout

        self.log(
            "Invalid action timeout, falling back to default timeout",
            level="warning",
            action_timeout=self.timeout,
        )
        return 5.0

    def __set_authentication_header(self, headers: dict):
        """
        Set the authentication header based on the authentication method.
        """
        # If no authentication method is set
        if not self.authentication:
            # If an API key is set in the configuration, use it as a
            # Bearer token (backward compatibility)
            if self.module.configuration and (
                api_key := self._module_configuration_value("api_key")
            ):
                headers["Authorization"] = f"Bearer {api_key}"

            # Do nothing more
            return

        match self.authentication.lower():
            case "basic":
                headers[self.auth_header or "Authorization"] = BasicAuth(
                    login=self._module_configuration_value("username"),
                    password=self._module_configuration_value("password"),
                ).encode()
            case "apikey":
                # API keys can be passed as headers or query parameters
                if self.auth_header:
                    headers[self.auth_header] = self._module_configuration_value(
                        "api_key"
                    )
            case "bearer":
                headers[self.auth_header or "Authorization"] = (
                    f"Bearer {self._module_configuration_value('api_key')}"
                )

    def get_headers(self):
        headers = {"Accept": "application/json"}
        self.__set_authentication_header(headers)
        return headers

    def get_url(self, arguments) -> str:
        # Specific Information, should be defined in the Module Configuration
        if base_url := self._module_configuration_value("base_url"):
            url = base_url
        else:
            url = self.base_url

        match = re.findall("{(.*?)}", self.endpoint)
        for replacement in match:
            self.endpoint = self.endpoint.replace(
                f"{{{replacement}}}", str(arguments.pop(replacement)), 1
            )
        return urljoin(url, self.endpoint.lstrip("/"))

    def get_query_parameters(self, arguments: dict) -> dict | None:
        query_parameters = {}
        if self.authentication == "apiKey" and self.auth_query_param:
            query_parameters[self.auth_query_param] = self._module_configuration_value(
                "api_key"
            )
        if self.query_parameters:
            query_parameters |= {
                k: arguments.pop(k) for k in self.query_parameters if k in arguments
            }
        return query_parameters if query_parameters else None

    def log_request_error(
        self,
        url: str,
        arguments: dict,
        response: Response,
    ):
        attempts = getattr(self, "_last_http_attempts", 1)
        attempts = max(attempts, 1)

        retries = attempts - 1
        details = (
            f"(status code: {response.status_code}, "
            f"attempts: {attempts}, retries: {retries})"
        )
        message = f"HTTP Request failed: {url} {details}"
        try:
            content = response.json()
            if isinstance(content, dict) and "message" in content:
                message = f"{content['message']} {details}"
        except ValueError:
            content = response.text
        self.log(
            message,
            level="error",
            url=url,
            arguments=arguments,
            response=content,
            retries=retries,
            attempts=attempts,
            status=response.status_code,
        )
        self.error(message)

    def log_retry_error(
        self,
        url: str,
        arguments: dict,
        retry_error: RetryError | None = None,
    ):
        attempts = getattr(self, "_last_http_attempts", 1)
        status_code = getattr(self, "_last_http_status_code", None)
        attempts = max(attempts, 1)

        retries = attempts - 1
        attempts_details = f"after {attempts} attempts ({retries} retries)"

        code = status_code if status_code is not None else "unknown"
        message = (
            f"HTTP Request failed {attempts_details}: {url} (last status code: {code})"
        )

        # Extract the underlying exception from RetryError if available
        underlying_exception: BaseException | None = None
        if retry_error and retry_error.last_attempt:
            underlying_exception = retry_error.last_attempt.exception()

        self.log(
            message,
            level="error",
            url=url,
            arguments=arguments,
            retries=retries,
            attempts=attempts,
            status=status_code,
            underlying_error=str(underlying_exception)
            if underlying_exception
            else None,
            exception_type=(
                type(underlying_exception).__name__ if underlying_exception else None
            ),
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

    def _normalize_request_body(
        self, body: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        if not self.strip_empty_string_fields:
            return body, []

        normalized = dict(body)
        removed_fields: list[str] = []
        for field in self.strip_empty_string_fields:
            if normalized.get(field) == "":
                normalized.pop(field)
                removed_fields.append(field)

        return normalized, removed_fields

    @staticmethod
    def _drop_fields(body: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
        if not fields:
            return body

        reduced = dict(body)
        for field in fields:
            reduced.pop(field, None)
        return reduced

    def _execute_http_request(
        self,
        *,
        url: str,
        headers: dict[str, Any],
        params: dict[str, Any] | None,
        body: dict[str, Any],
        arguments: dict[str, Any],
        timeout: float | tuple[float, float],
    ) -> dict | None:
        self._last_http_attempts = 1
        self._last_http_status_code = None

        try:
            for attempt in Retrying(
                stop=stop_after_attempt(10),
                wait=self._wait_param(),
                retry=retry_if_exception_type((RequestException, OSError)),
            ):
                with attempt:
                    response: Response = requests.request(
                        self.verb,
                        url,
                        json=body,
                        headers=headers,
                        timeout=timeout,
                        params=params,
                    )
                    if not response.ok:
                        if (
                            self.verb.lower() == "delete"
                            and response.status_code == 404
                            and attempt.retry_state.attempt_number > 1
                        ):
                            return None
                        if 400 <= response.status_code < 500:
                            self._last_http_attempts = (
                                attempt.retry_state.attempt_number
                            )
                            self.log_request_error(url, arguments, response)
                            return None
                        response.raise_for_status()
        except RetryError as ex:
            attempts = 1
            status_code = None
            if ex.last_attempt is not None:
                attempts = ex.last_attempt.attempt_number
                if last_exception := ex.last_attempt.exception():
                    failed_response = getattr(last_exception, "response", None)
                    if failed_response is not None:
                        status_code = failed_response.status_code

            self._last_http_attempts = attempts
            self._last_http_status_code = status_code
            self.log_retry_error(url, arguments, ex)
            return None

        return response.json() if response.status_code != 204 else None

    def run(self, arguments) -> dict | None:
        headers = self.get_headers()
        url = self.get_url(arguments)
        params = self.get_query_parameters(arguments)
        body = self.get_body(arguments)
        timeout = self.get_timeout()

        if isinstance(body, dict):
            body, removed_fields = self._normalize_request_body(body)
            if removed_fields:
                self.log(
                    "Removed empty string fields from request body",
                    level="warning",
                    removed_fields=removed_fields,
                )

            if self.skip_request_if_body_empty and not body:
                self.log(
                    (
                        "Skipping HTTP request because request body is empty "
                        "after normalization"
                    ),
                    level="warning",
                )
                self._error = None
                return {}

        result = self._execute_http_request(
            url=url,
            headers=headers,
            params=params,
            body=body,
            arguments=arguments,
            timeout=timeout,
        )
        if result is not None:
            return result

        if isinstance(body, dict) and self.retry_without_fields_on_failure:
            reduced_body = self._drop_fields(body, self.retry_without_fields_on_failure)
            if reduced_body != body:
                if self.skip_request_if_body_empty and not reduced_body:
                    self.log(
                        (
                            "Skipping fallback HTTP request because reduced "
                            "request body is empty"
                        ),
                        level="warning",
                        removed_fields=list(self.retry_without_fields_on_failure),
                    )
                    self._error = None
                    return {}

                self.log(
                    "Retrying HTTP request with reduced request body",
                    level="warning",
                    removed_fields=list(self.retry_without_fields_on_failure),
                )
                self._error = None
                fallback_result = self._execute_http_request(
                    url=url,
                    headers=headers,
                    params=params,
                    body=reduced_body,
                    arguments=arguments,
                    timeout=timeout,
                )
                if fallback_result is not None:
                    self._error = None
                    self.log(
                        "HTTP request succeeded with reduced request body",
                        level="warning",
                    )
                    return fallback_result

        return None

    def _wait_param(self) -> wait_base:
        return wait_exponential(multiplier=2, min=2, max=300)

    def _module_configuration_value(self, key: str) -> Any:
        if isinstance(self.module.configuration, dict):
            return self.module.configuration.get(key)
        return getattr(self.module.configuration, key, None)
