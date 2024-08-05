from pathlib import Path

from .actions_json import ActionsJSONValidator
from .changelog import ChangelogValidator
from .connectors_json import ConnectorsJSONValidator
from .deps import DependenciesValidator
from .dockerfile import DockerfileValidator
from .logo import LogoValidator
from .main import MainPYValidator
from .manifest import ManifestValidator
from .module import ModuleValidator
from .tests import TestsValidator
from .triggers_json import TriggersJSONValidator

MODULES_PATH = Path(__file__).parent.parent.parent.parent

__all__ = (
    "ActionsJSONValidator",
    "ChangelogValidator",
    "ConnectorsJSONValidator",
    "DependenciesValidator",
    "DockerfileValidator",
    "LogoValidator",
    "MainPYValidator",
    "ManifestValidator",
    "ModuleValidator",
    "TestsValidator",
    "TriggersJSONValidator",
)
