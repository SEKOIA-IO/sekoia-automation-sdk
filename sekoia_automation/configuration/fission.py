import json
import os

from flask import request

from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.utils import json_load


class FissionConfiguration(Configuration):
    """
    Configuration class for Fission environment.
    """

    def __init__(self):
        self.configurations = request.get_json(silent=True, cache=True) or {}

    def load(self, name: str, type_: str = "str", non_exist_ok=False):
        """
        Load a configuration value
        """
        # First try to load from the JSON body of the request
        if name in self.configurations:
            value = self.configurations[name]
            if type_ == "json" and isinstance(value, str):
                return json.loads(value)
            return value

        # Then try to load from environment variables
        if value := os.environ.get(name.upper()):
            return json_load(value) if type_ == "json" else value

        # Finally, handle the non_exist_ok flag
        if non_exist_ok:
            return None

        # If the configuration is not found, raise an error
        raise KeyError(f"{name} does not exist.")

    def __hash__(self):
        return hash(frozenset(self.configurations.items()))
