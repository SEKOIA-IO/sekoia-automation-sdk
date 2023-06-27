import json
import subprocess
from pathlib import Path

from rich import print
from rich.progress import Progress


class SDKUpdater:
    def __init__(self, modules_path: Path):
        self._modules_path = modules_path

    def update_sdk_version(self):
        with Progress(transient=True) as progress:
            modules = self.get_modules()
            task = progress.add_task("Updating modules", total=len(modules))
            for module in modules:
                progress.update(task, description=f"Updating module {module.name}")
                self.update_module(module)
                progress.advance(task)

    def update_module(self, module: Path):
        if err := self._update_requirements(module):
            print(
                f"  [bold red][!] {module.name}: Error while updating the project SDK."
                f"Error : {err}"
            )
            return
        self._bump_module_version(module)

    def get_modules(self) -> list[Path]:
        return [
            module
            for module in self._modules_path.absolute().iterdir()
            if module.is_dir() and module.joinpath("manifest.json").exists()
        ]

    def _bump_module_version(self, module: Path):
        manifest_file = module.joinpath("manifest.json")
        with manifest_file.open("r") as fp:
            data = json.load(fp)

        major, minor, *_ = data["version"].split(".")
        data["version"] = major + "." + str(int(minor) + 1)

        with manifest_file.open("w") as fp:
            json.dump(data, fp, indent=4)

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
