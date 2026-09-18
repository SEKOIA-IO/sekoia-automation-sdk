import json
from pathlib import Path
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings

from sekoia_automation.exceptions import EnvironmentRuntimeError


class Settings(BaseSettings):
    symphony_runtime: Literal["native", "fission"] = "native"
    fission_state_file_path: Path = Path("/userfunc/state.json")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fission_enabled(self) -> bool:
        return self.symphony_runtime == "fission"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def base_directory(self) -> Path:
        """Get the base directly where manifest and other action files are stored."""

        if self.fission_enabled:
            base_directory: Path | None = None
            try:
                with self.fission_state_file_path.open() as f:
                    content = json.load(f)
                    base_path = Path(content["filepath"])
                    if base_path.exists():
                        base_directory = base_path
            except Exception:
                pass

            if base_directory is None:
                raise EnvironmentRuntimeError(
                    "Unable to identify the base directory for deployed Fission code"
                )

            return base_directory

        return Path.cwd()
