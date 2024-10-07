import json
import logging
import sys
import time
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, cast

import requests
import sentry_sdk
from botocore.exceptions import ClientError
from pydantic import BaseModel
from requests import RequestException, Response

from sekoia_automation.config import load_config
from sekoia_automation.exceptions import (
    CommandNotFoundError,
    ModuleConfigurationError,
    SendEventError,
)
from sekoia_automation.storage import get_data_path
from sekoia_automation.utils import (
    get_annotation_for,
    get_as_model,
)

LogLevelStr = Literal["fatal", "critical", "error", "warning", "info", "debug"]


class Module:
    MODULE_CONFIGURATION_FILE_NAME = "module_configuration"
    COMMUNITY_UUID_FILE_NAME = "community_uuid"
    PLAYBOOK_UUID_FILE_NAME = "playbook_uuid"
    PLAYBOOK_RUN_UUID_FILE_NAME = "playbook_run_uuid"
    NODE_RUN_UUID_FILE_NAME = "node_run_uuid"
    TRIGGER_CONFIGURATION_UUID_FILE_NAME = "trigger_configuration_uuid"
    CONNECTOR_CONFIGURATION_UUID_FILE_NAME = "connector_configuration_uuid"

    SENTRY_FILE_NAME = "sentry_dsn"
    ENVIRONMENT_FILE_NAME = "environment"

    def __init__(self):
        self._command: str | None = None
        self._configuration: dict | BaseModel | None = None
        self._manifest: dict | None = None
        self._community_uuid: str | None = None
        self._items: dict[str, type[ModuleItem]] = {}
        self._playbook_uuid: str | None = None
        self._playbook_run_uuid: str | None = None
        self._node_run_uuid: str | None = None
        self._trigger_configuration_uuid: str | None = None
        self._connector_configuration_uuid: str | None = None
        self._name = None
        self.init_sentry()

    @property
    def command(self) -> str | None:
        if not self._command and len(sys.argv) >= 2:
            self._command = sys.argv[1]

        return self._command

    @property
    def manifest(self):
        if self._manifest is None:
            try:
                with open("manifest.json") as fp:
                    self._manifest = json.load(fp)
            except FileNotFoundError:
                self._manifest = {}
        return self._manifest

    @property
    def name(self):
        if not self._name:
            self._name = self.manifest.get("name", "name missing from manifest")
        return self._name

    @property
    def configuration(self) -> dict | BaseModel | None:
        if self._configuration is None:
            self.configuration = self.load_config(
                self.MODULE_CONFIGURATION_FILE_NAME, "json"
            )

        return self._configuration

    @configuration.setter
    def configuration(self, configuration: dict | BaseModel) -> None:
        """Generates the module's configuration using Pydantic's primitives

        A check for the presence of required properties has to be done:
        We look for properties that would be marked as "required" inside the
        module's manifest but wouldn't be set in the "configuration" dict
        given here as an argument.
        If this happens an exception is raised.
        Otherwise we set the "configuration" argument as the module's configuration.

        :param configuration: Configuration to be applied to this instance
        :type configuration: dict
        :raises ModuleConfigurationError: If the module requires a property that
            has not been set
        :raises ModuleConfigurationError: If the parsing of the configuration
            and the model by Pydantic fail and raise an Exception
        """
        required_properties: list[str] = self.manifest_required_properties()
        items = (
            configuration.dict().items()
            if isinstance(configuration, BaseModel)
            else configuration.items()
        )
        actual_properties = {k: v for k, v in items if k in self.manifest_properties()}
        missing_required_properties = [
            p for p in required_properties if p not in actual_properties
        ]
        if not missing_required_properties:
            try:
                self._configuration = get_as_model(
                    get_annotation_for(self.__class__, "configuration"),
                    configuration,
                )
            except Exception as e:
                raise ModuleConfigurationError(str(e))
        else:
            raise ModuleConfigurationError(
                f"Module configuration requires properties \
                    that were not found: {missing_required_properties}",
            )

        if isinstance(self._configuration, BaseModel):
            sentry_sdk.set_context("module_configuration", self._configuration.dict())
        elif self._configuration:
            sentry_sdk.set_context("module_configuration", self._configuration)

    def manifest_properties(self) -> list[str]:
        """Gets the list of expected properties from the module's manifest

        This is different from the properties that are actually set in the
        module's configuration instance since some can be optionnal

        :return: List of properties available for this module
        :rtype: list[str]
        """
        return list(self.manifest.get("configuration", {}).get("properties", {}).keys())

    def manifest_secrets(self) -> list[str]:
        """Gets the list of expected secrets from the module's manifest

        This is different from the secrets that are actually set in the
        module's configuration instance since some can be optionnal

        :return: List of secrets available for this module
        :rtype: list[str]
        """
        return list(self.manifest.get("configuration", {}).get("secrets", []))

    def manifest_required_properties(self) -> list[str]:
        """Gets the list of required properties from the module's manifest

        :return: List of required parameters for this module
        :rtype: list[str]
        """
        return list(self.manifest.get("configuration", {}).get("required", []))

    def has_secrets(self) -> bool:
        """Check with manifest if this module has secrets.

        :return: True if the module's manifest has secrets, False otherwise
        :rtype: bool
        """
        return bool(self.manifest.get("configuration", {}).get("secrets"))

    @property
    def secrets(self) -> dict[str, Any]:
        """Returns a dict of the secrets of the current module

        Both the manifest and the module configuration are required: this
        method parses the module's manifest to get a list of the secret fields,
        then it looks up their associated value in the module configuration
        Note that some secrets may not be defined in the module configuration
        and thus wouldn't be added to the return value. No check of required
        secrets is made here.

        :return: A dict mapping the secrets defined in the module conf
        to their value. If no secret is found, the dict is empty.
        :rtype: dict[str, Any]
        """
        secrets = {}
        config_dict = {}
        if isinstance(self.configuration, BaseModel):
            config_dict = self.configuration.dict()
        elif isinstance(self.configuration, dict):
            config_dict = self.configuration
        for secret_key in self.manifest_secrets():
            if secret_key in config_dict:
                secrets[secret_key] = config_dict[secret_key]
        return secrets

    def set_secrets(self, secrets):
        """
        Add the secret to the configurqtion
        """
        if isinstance(self.configuration, dict):
            self.configuration |= secrets
        else:
            for key, value in secrets.items():
                setattr(self.configuration, key, value)

    @property
    def community_uuid(self) -> str | None:
        if self._community_uuid is None:
            self._community_uuid = self.load_config(
                self.COMMUNITY_UUID_FILE_NAME, non_exist_ok=True
            )

        return self._community_uuid

    @property
    def playbook_uuid(self) -> str | None:
        if self._playbook_uuid is None:
            self._playbook_uuid = self.load_config(
                self.PLAYBOOK_UUID_FILE_NAME, non_exist_ok=True
            )

        return self._playbook_uuid

    @property
    def playbook_run_uuid(self) -> str | None:
        if self._playbook_run_uuid is None:
            self._playbook_run_uuid = self.load_config(
                self.PLAYBOOK_RUN_UUID_FILE_NAME, non_exist_ok=True
            )

        return self._playbook_run_uuid

    @property
    def node_run_uuid(self) -> str | None:
        if self._node_run_uuid is None:
            self._node_run_uuid = self.load_config(
                self.NODE_RUN_UUID_FILE_NAME, non_exist_ok=True
            )

        return self._node_run_uuid

    @property
    def trigger_configuration_uuid(self) -> str | None:
        if self._trigger_configuration_uuid is None:
            self._trigger_configuration_uuid = self.load_config(
                self.TRIGGER_CONFIGURATION_UUID_FILE_NAME, non_exist_ok=True
            )

        return self._trigger_configuration_uuid

    @property
    def connector_configuration_uuid(self) -> str | None:
        if self._connector_configuration_uuid is None:
            self._connector_configuration_uuid = self.load_config(
                self.CONNECTOR_CONFIGURATION_UUID_FILE_NAME, non_exist_ok=True
            )

        return self._connector_configuration_uuid

    def load_config(self, file_name: str, type_: str = "str", non_exist_ok=False):
        return load_config(file_name, type_, non_exist_ok=non_exist_ok)

    def register(self, item: type["ModuleItem"], name: str = ""):
        if not item.name:
            item.name = name
        self._items[name] = item

    def run(self):
        command = self.command or ""

        if command in self._items:
            to_run = self._items[command](self)
            try:
                to_run.start_monitoring()
                to_run.execute()
            finally:
                to_run.stop_monitoring()
        else:
            error = f"Could not find any Action or Trigger matching command '{command}'"
            sentry_sdk.capture_message(error, "error")
            raise CommandNotFoundError(error)

    def init_sentry(self):
        sentry_dsn = self._load_sentry_dsn()
        if sentry_dsn:
            sentry_sdk.init(sentry_dsn, environment=self._load_environment())
            sentry_sdk.set_tag("module", self.name)
            if self.community_uuid:
                sentry_sdk.set_tag("community", self.community_uuid)
            if self.playbook_uuid:
                sentry_sdk.set_tag("playbook_uuid", self.playbook_uuid)
            if self.playbook_run_uuid:
                sentry_sdk.set_tag("playbook_run_uuid", self.playbook_run_uuid)
            if self.node_run_uuid:
                sentry_sdk.set_tag("node_run_uuid", self.node_run_uuid)
            if self.trigger_configuration_uuid:
                sentry_sdk.set_tag(
                    "trigger_configuration_uuid", self.trigger_configuration_uuid
                )
            if self.connector_configuration_uuid:
                sentry_sdk.set_tag(
                    "connector_configuration_uuid", self.connector_configuration_uuid
                )

    def _load_sentry_dsn(self) -> str | None:
        try:
            return self.load_config(self.SENTRY_FILE_NAME)
        except FileNotFoundError:
            return None

    def _load_environment(self) -> str | None:
        try:
            return self.load_config(self.ENVIRONMENT_FILE_NAME)
        except FileNotFoundError:
            return None


class ModuleItem(ABC):
    TOKEN_FILE_NAME = "token"
    CALLBACK_URL_FILE_NAME = "url_callback"
    SECRETS_URL_FILE_NAME = "url_secrets"
    LOGS_URL_FILE_NAME = "url_logs"
    INTAKE_URL_FILE_NAME = "intake_url"

    name: str | None = None
    description: str | None = None
    results_model: type[BaseModel] | None = None

    _wait_exponent_base: int = 2

    def __init__(self, module: Module | None = None, data_path: Path | None = None):
        self.module: Module = module or Module()

        self._token: str | None = None

        # Name may be set by the action/trigger class or the module during the register
        # Worse case we use the class name
        if not self.name:
            self.name = self.__class__.__name__.lower()
        self._data_path = data_path

        self._setup_logging()

    def _setup_logging(self):
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.INFO,
        )
        self._logger = logging.getLogger(self.name)
        sentry_sdk.set_tag("name", self.name)

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = self.module.load_config(self.TOKEN_FILE_NAME)

        return self._token

    @property
    def data_path(self) -> Path:
        self._ensure_data_path_set()
        return cast(Path, self._data_path)

    def _ensure_data_path_set(self):
        if not self._data_path:
            try:
                self._data_path = get_data_path()
            except Exception as e:
                if (
                    isinstance(e, ClientError)
                    and e.response.get("Error", {}).get("Code") == "403"
                ):
                    self.log("Access denied to the object storage", level="critical")
                    raise
                self.log_exception(e)
                self.log("Impossible access the object storage", level="critical")
                raise

    def log(
        self,
        message: str,
        level: LogLevelStr = "debug",
        only_sentry: bool = False,
        **kwargs,
    ) -> None:
        """Log a message with a specific level."""
        # Right now propagates to sentry only errors and warnings
        if not only_sentry:
            log_level = logging.getLevelName(level.upper())
            self._logger.log(log_level, message)
        if level.lower() in ["error", "warning", "critical"]:
            with sentry_sdk.push_scope() as scope:
                for key, value in kwargs.items():
                    scope.set_extra(key, value)
                sentry_sdk.capture_message(message, level)  # type: ignore

    def log_exception(self, exception: Exception, **kwargs):
        """Log the given exception."""
        message = kwargs.get("message", "An exception occurred")
        self._logger.exception(message)
        with sentry_sdk.push_scope() as scope:
            for key, value in kwargs.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exception)

    @cached_property
    def callback_url(self) -> str:
        return self.module.load_config(self.CALLBACK_URL_FILE_NAME)

    @cached_property
    def logs_url(self) -> str:
        try:
            return self.module.load_config(self.LOGS_URL_FILE_NAME)
        except FileNotFoundError:
            return self.callback_url.replace("/callback", "/logs")

    @cached_property
    def secrets_url(self) -> str:
        try:
            return self.module.load_config(self.SECRETS_URL_FILE_NAME)
        except FileNotFoundError:
            return self.callback_url.replace("/callback", "/secrets")

    @cached_property
    def intake_url(self) -> str:
        return self.module.load_config(self.INTAKE_URL_FILE_NAME)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _send_request(self, data: dict, verb: str = "POST", attempt=1) -> Response:
        try:
            response = requests.request(
                verb, self.callback_url, json=data, headers=self._headers, timeout=30
            )
            response.raise_for_status()
            return response
        except (RequestException, OSError) as exception:
            if isinstance(exception, RequestException):
                self._log_request_error(exception)
            if attempt == 10:
                status_code = (
                    exception.response.status_code
                    if isinstance(exception, RequestException)
                    and isinstance(exception.response, Response)
                    else 500
                )
                raise SendEventError(
                    "Impossible to send event to Sekoia.io API", status_code=status_code
                )
            if (
                isinstance(exception, RequestException)
                and isinstance(exception.response, Response)
                and 400 <= exception.response.status_code < 500
            ):
                raise SendEventError(
                    "Impossible to send event to Sekoia.io API",
                    status_code=exception.response.status_code,
                )
            time.sleep(self._wait_exponent_base**attempt)
            return self._send_request(data, verb, attempt + 1)

    def _log_request_error(self, exception: RequestException):
        context: dict[str, Any] = {}
        if exception.response:
            response: Response = exception.response
            context["status_status"] = response.status_code
            try:
                context["response_content"] = response.json()
            except ValueError:
                context["response_content"] = response.content
        self.log_exception(exception, **context)

    @abstractmethod
    def execute(self) -> None:
        """To define in subclasses. Main method being called to run the ModuleItem."""

    def start_monitoring(self) -> None:
        """
        Allow the Trigger or Action to start some background monitoring tasks
        """

    def stop_monitoring(self):
        """
        Stops the background monitoring operations
        """
