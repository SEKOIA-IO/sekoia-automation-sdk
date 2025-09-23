import json
import os
from pathlib import Path

from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.utils import json_load


class FileSystemConfiguration(Configuration):
    """
    Configuration implementation that loads configuration from the filesystem
    or environment variables.

    The configuration files are expected to be located in the /symphony
    directory.
    """

    VOLUME_PATH = "/symphony"

    def load(self, name: str, type_: str = "str", non_exist_ok=False):
        """
        Load a configuration value
        """
        # First try to load from the filesystem
        path = Path(f"{self.VOLUME_PATH}/{name}")
        if path.is_file():
            with path.open("r") as fd:
                return json.load(fd) if type_ == "json" else fd.read()
        # Then try to load from environment variables
        if value := os.environ.get(name.upper()):
            return json_load(value) if type_ == "json" else value

        # Finally, handle the non_exist_ok flag
        if non_exist_ok:
            return None

        # If the configuration is not found, raise an error
        raise FileNotFoundError(f"{path} does not exist.")

    def __hash__(self):
        return hash(self.VOLUME_PATH)
