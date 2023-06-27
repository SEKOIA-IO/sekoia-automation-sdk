import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

from rich import print


class SDKUpdater:
    def __init__(self, modules_path: Path):
        self._modules_path = modules_path

    def update_sdk_version(self):
        for module in self.get_modules():
            self.update_module(module)

    def update_module(self, module: Path):
        print(f"Updating {module.name}")
        if err := self._update_requirements(module):
            print(
                f"  [bold red][!] Error while updating the project SDK."
                f"Error : {err}"
            )
            return
        print("  [green] Requirements updated")
        version = self._bump_module_version(module)
        print(f"  [green] Version in manifest bumped to {version}")

    def get_modules(self) -> Iterator[Path]:
        for module in self._modules_path.absolute().iterdir():
            if module.is_dir() and module.joinpath("manifest.json").exists():
                yield module

    def _bump_module_version(self, module: Path) -> str:
        manifest_file = module.joinpath("manifest.json")
        with manifest_file.open("r") as fp:
            data = json.load(fp)

        major, minor, *_ = data["version"].split(".")
        data["version"] = major + "." + str(int(minor) + 1)

        with manifest_file.open("w") as fp:
            json.dump(data, fp)
        return data["version"]

    def _update_requirements(self, module: Path) -> str | None:
        r = subprocess.run(
            args=f"cd {module.absolute()} && poetry add sekoia-automation-sdk@latest",
            shell=True,
            capture_output=True,
        )
        if r.returncode != 0:
            error = r.stderr.decode() if r.stderr else "Unknown error"
            print(
                f"  [bold red][!] Error while updating the project SDK."
                f"Error : {error}"
            )
            return error
        return None
