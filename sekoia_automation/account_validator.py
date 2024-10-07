from abc import abstractmethod

import requests

from sekoia_automation.module import ModuleItem


class AccountValidator(ModuleItem):
    VALIDATION_CALLBACK_URL_FILE_NAME = "validation_callback_url"

    @abstractmethod
    def validate(self) -> bool:
        """To define in subclasses. Validates the configuration of the module.

        Returns:
            bool: True if the module is valid, False otherwise
        """

    def execute(self):
        """Validates the account (module_configuration) of the module
        and sends the result to Symphony."""
        # Call the actual validation procedure
        status = self.validate()

        # Return result of validation to Symphony
        data = {"validation_status": status}
        self._send_request(data)
