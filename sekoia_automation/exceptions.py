class AutomationSDKError(Exception):
    def __str__(self) -> str:
        result = self.__class__.__name__

        if self.args:
            result += f": {self.args[0]}"

        return result


class SendEventError(AutomationSDKError):
    pass


class CommandNotFoundError(AutomationSDKError):
    pass


class InvalidDirectoryError(AutomationSDKError):
    pass


class MissingActionArgumentError(AutomationSDKError):
    def __init__(self, argument):
        self.argument = argument


class MissingActionArgumentFileError(AutomationSDKError):
    def __init__(self, filepath):
        self.filepath = filepath


class ModuleConfigurationError(AutomationSDKError):
    pass


class TriggerConfigurationError(AutomationSDKError):
    pass
