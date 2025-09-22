import os
from functools import lru_cache

from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.filesystem import FileSystemConfiguration
from sekoia_automation.configuration.fission import FissionConfiguration


@lru_cache
def get_configuration() -> Configuration:
    """
    Get the configuration instance to use in the module.
    """
    runtime = os.environ.get("SYMPHONY_RUNTIME")
    if runtime is not None and runtime.lower() == "fission":
        return FissionConfiguration()
    else:
        return FileSystemConfiguration()
