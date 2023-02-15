import json
import logging
import sys
from abc import ABC, abstractmethod
from typing import Any

import requests
import sentry_sdk
from pydantic import BaseModel
from requests import HTTPError, Response

from sekoia_automation.config import load_config
from sekoia_automation.exceptions import (
    CommandNotFoundError,
    ModuleConfigurationError,
    SendEventError,
)
from sekoia_automation.utils import get_annotation_for, get_as_model


class Module:
    MODULE_CONFIGURATION_FILE_NAME = "module_configuration"
    COMMUNITY_UUID_FILE_NAME = "community_uuid"
    PLAYBOOK_UUID_FILE_NAME = "playbook_uuid"
    PLAYBOOK_RUN_UUID_FILE_NAME = "playbook_run_uuid"
    NODE_RUN_UUID_FILE_NAME = "node_run_uuid"
    TRIGGER_CONFIGURATION_UUID_FILE_NAME = "trigger_configuration_uuid"

    SENTRY_FILE_NAME = "sentry_dsn"
    ENVIRONMENT_FILE_NAME = "environment"

    def __init__(self):
        self._command: str | None = None
        self._configuration: dict | BaseModel | None = None
        self._manifest: dict | None = None
        self.secrets: dict | None = None
        self._community_uuid: str | None = None
        self._items: dict[str, type["ModuleItem"]] = {}
        self._playbook_uuid: str | None = None
        self._playbook_run_uuid: str | None = None
        self._node_run_uuid: str | None = None
        self._trigger_configuration_uuid: str | None = None
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
    def configuration(self, configuration: dict) -> None:
        try:
            self._configuration = get_as_model(
                get_annotation_for(self.__class__, "configuration"), configuration
            )
        except Exception as e:
            raise ModuleConfigurationError(str(e))

        if isinstance(self._configuration, BaseModel):
            sentry_sdk.set_context("module_configuration", self._configuration.dict())
        elif self._configuration:
            sentry_sdk.set_context("module_configuration", self._configuration)

    def has_secrets(self) -> bool:
        """Check with manifest if module configuration has secrets."""
        if not self.secrets:
            has_secrets = bool(self.manifest.get("configuration", {}).get("secrets"))
        else:
            has_secrets = True
        return has_secrets

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

    def load_config(self, file_name: str, type_: str = "str", non_exist_ok=False):
        return load_config(file_name, type_, non_exist_ok=non_exist_ok)

    def register(self, item: type["ModuleItem"], name: str = ""):
        if not item.name:
            item.name = name
        self._items[name] = item

    def run(self):
        command = self.command or ""

        if command in self._items:
            self._items[command](self).execute()
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

    name: str | None = None
    description: str | None = None
    results_model: type[BaseModel] | None = None

    def __init__(self, module: Module | None = None):
        self.module: Module = module or Module()

        self._token: str | None = None
        self._callback_url: str | None = None

        # Name may be set by the action/trigger class or the module during the register
        # Worse case we use the class name
        if not self.name:
            self.name = self.__class__.__name__.lower()

        self._setup_logging()

    def _setup_logging(self):
        self._logger = logging.getLogger(__name__)

        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        self._logger.addHandler(handler)

        sentry_sdk.set_tag("name", self.name)

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = self.module.load_config(self.TOKEN_FILE_NAME)

        return self._token

    def log(
        self, message: str, level: str = "debug", only_sentry: bool = False, **kwargs
    ) -> None:
        """Log a message with a specific level."""
        # Right now propagates to sentry only errors and warnings
        if not only_sentry:
            log_level = logging.getLevelName(level.upper())
            self._logger.log(log_level, message)
        if level.lower() in ["error", "warning"]:
            with sentry_sdk.push_scope() as scope:
                for key, value in kwargs.items():
                    scope.set_extra(key, value)
                sentry_sdk.capture_message(message, level)

    def log_exception(self, exception: Exception, **kwargs):
        """Log the given exception."""
        message = kwargs.get("message", "An exception occurred")
        self._logger.exception(message)
        with sentry_sdk.push_scope() as scope:
            for key, value in kwargs.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exception)

    @property
    def callback_url(self) -> str:
        if self._callback_url is None:
            self._callback_url = self.module.load_config(self.CALLBACK_URL_FILE_NAME)

        return self._callback_url

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _send_request(self, data: dict, verb: str = "POST", attempt=1) -> Response:
        try:
            response = requests.request(
                verb, self.callback_url, json=data, headers=self._headers
            )
            response.raise_for_status()
            return response
        except HTTPError as exception:
            self._log_request_error(exception)
            if attempt == 3:
                raise SendEventError("Impossible to send event to SEKOIA.IO API")
            return self._send_request(data, verb, attempt + 1)

    def _log_request_error(self, exception: HTTPError):
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
