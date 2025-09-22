from functools import lru_cache

from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.filesystem import FileSystemConfiguration


@lru_cache
def get_configuration() -> Configuration:
    """
    Get the configuration instance to use in the module.
    """
    return FileSystemConfiguration()
