from sekoia_automation.configuration.base import Configuration
from sekoia_automation.configuration.filesystem import FileSystemConfiguration
from sekoia_automation.configuration.fission import FissionConfiguration


def get_configuration(fission_mode: bool = False) -> Configuration:
    """
    Get the configuration instance to use in the module.
    """
    if fission_mode is True:
        return FissionConfiguration()
    else:
        return FileSystemConfiguration()
