from abc import abstractmethod
from pathlib import Path

from sekoia_automation.module import Module, ModuleItem


class AccountValidator(ModuleItem):
    def __init__(self, module: Module | None = None, data_path: Path | None = None):
        super().__init__(module, data_path)
        self._error: str | None = None

    @abstractmethod
    def validate(self) -> bool:
        """To define in subclasses. Validates the configuration of the module.

        Returns:
            bool: True if the module is valid, False otherwise
        """

    def error(self, message: str) -> None:
        """Allow to set an error message explaining why the validation failed."""
        self._error = message

    def execute(self):
        """Validates the account (module_configuration) of the module
        and sends the result to Symphony."""
        self.set_task_as_running()
        # Call the actual validation procedure
        success = self.validate()
        self.send_results(success)

    def set_task_as_running(self):
        """Send a request to indicate the action started."""
        data = {"status": "running"}
        response = self._send_request(data, verb="PATCH")
        if self.module.has_secrets():
            secrets = {
                k: v
                for k, v in response.json()["module_configuration"]["value"].items()
                if k in self.module.manifest_secrets()
            }
            self.module.set_secrets(secrets)

    def send_results(self, success: bool):
        data = {"status": "finished", "results": {"success": success}}
        if self._error:
            data["error"] = self._error
        self._send_request(data, verb="PATCH")
