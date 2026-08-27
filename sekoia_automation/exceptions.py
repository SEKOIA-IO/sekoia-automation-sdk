class AutomationSDKError(Exception):
    def __str__(self) -> str:
        result = self.__class__.__name__

        if self.args:
            result += f": {self.args[0]}"

        return result


class SendEventError(AutomationSDKError):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


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


class AssetConnectorRateLimitError(AutomationSDKError):
    """Raised when the asset-connector push endpoint returns HTTP 429."""

    def __init__(self, retry_after: float):
        super().__init__("Asset connector push rate limit exceeded (HTTP 429)")
        self.retry_after = retry_after
