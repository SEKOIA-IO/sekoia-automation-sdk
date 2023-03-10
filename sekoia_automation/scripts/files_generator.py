import json
import sys
from functools import cached_property
from importlib import import_module
from inspect import getmembers, isabstract, isclass, signature
from pathlib import Path
from pkgutil import walk_packages
from uuid import UUID, uuid5

import typer
from pydantic import BaseModel
from rich import print

from sekoia_automation.action import Action
from sekoia_automation.module import Module
from sekoia_automation.trigger import Trigger
from sekoia_automation.utils import get_annotation_for


class FilesGenerator:
    @property
    def manifest_path(self) -> Path:
        return self.base_path.joinpath("manifest.json")

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def inspect_module(
        self,
        name: str,
        modules: set[type[Module]],
        actions: set[type[Action]],
        triggers: set[type[Trigger]],
    ):
        module = import_module(name)

        for _, obj in getmembers(module, isclass):
            if not isabstract(obj):
                if issubclass(obj, Action):
                    actions.add(obj)
                elif issubclass(obj, Trigger):
                    triggers.add(obj)
                elif issubclass(obj, Module) and obj != Module:
                    modules.add(obj)

    def execute(self):
        # Make sure we are in a module directory by verifying that there is a manifest
        if not self.manifest_path.is_file():
            print(
                "[bold red][!] No manifest.json found. "
                "Execute this command from a module's root directory.[/bold red]"
            )
            raise typer.Exit(code=1)
        _old_path = sys.path
        sys.path = [self.base_path.as_posix(), *sys.path]

        modules = set()
        actions = set()
        triggers = set()

        for _, name, ispkg in walk_packages([self.base_path.as_posix()]):
            if not ispkg:
                self.inspect_module(name, modules, actions, triggers)

        if len(modules) != 1:
            print("[bold red][!] Found 0 or more than 1 module, aborting[/bold red]")
            raise typer.Exit(code=1)
        module = next(iter(modules))

        self.generate_main(module, actions, triggers)
        self.generate_action_manifests(actions)
        self.generate_trigger_manifests(triggers)
        self.update_module_manifest(module)

        sys.path = _old_path

    @cached_property
    def module_uuid(self):
        with self.manifest_path.open() as f:
            return UUID(json.load(f)["uuid"])

    def generate_main(
        self,
        module: type[Module],
        actions: set[type[Action]],
        triggers: set[type[Trigger]],
    ):
        main = self.base_path / "main.py"

        with main.open("w") as out:
            out.write(f"from {module.__module__} import {module.__name__}\n\n")

            for trigger in triggers:
                out.write(f"from {trigger.__module__} import {trigger.__name__}\n")

            for action in actions:
                out.write(f"from {action.__module__} import {action.__name__}\n")

            out.write('\n\nif __name__ == "__main__":\n')
            out.write(f"    module = {module.__name__}()\n")

            for trigger in triggers:
                out.write(
                    f'    module.register({trigger.__name__}, "{trigger.__name__}")\n'
                )

            for action in actions:
                out.write(
                    f'    module.register({action.__name__}, "{action.__name__}")\n'
                )

            out.write("    module.run()\n")

        print(f"[green][+][/green] Generated {main}")

    def generate_action_manifests(self, actions: set[type[Action]]):
        for action in actions:
            name = action.name or action.__name__
            filepath = self.base_path / f"action_{name.lower().replace(' ', '_')}.json"

            manifest: dict[str, str | dict | None] = {
                "name": name,
                "description": action.description,
                "uuid": str(uuid5(self.module_uuid, name)),
                "docker_parameters": action.__name__,
                "arguments": {},
                "results": {},
            }

            if action.results_model:
                manifest["results"] = action.results_model.schema()

            args = list(signature(action.run).parameters.values())
            if args[1].annotation and issubclass(args[1].annotation, BaseModel):
                manifest["arguments"] = args[1].annotation.schema()

            with filepath.open("w") as out:
                out.write(json.dumps(manifest, indent=2))

            print(f"[green][+][/green] Generated {filepath}")

    def generate_trigger_manifests(self, triggers: set[type[Trigger]]):
        for trigger in triggers:
            name = trigger.name or trigger.__name__
            filepath = self.base_path / f"trigger_{name.lower().replace(' ', '_')}.json"

            manifest: dict[str, str | dict | None] = {
                "name": name,
                "description": trigger.description,
                "uuid": str(uuid5(self.module_uuid, name)),
                "docker_parameters": trigger.__name__,
                "arguments": {},
                "results": {},
            }

            if trigger.results_model:
                manifest["results"] = trigger.results_model.schema()

            if configuration_model := get_annotation_for(trigger, "configuration"):
                manifest["arguments"] = configuration_model.schema()

            with filepath.open("w") as out:
                out.write(json.dumps(manifest, indent=2))

            print(f"[green][+][/green] Generated {filepath}")

    def update_module_manifest(self, module: type[Module]):
        configuration_model = get_annotation_for(module, "configuration")

        if configuration_model is None:
            return

        with self.manifest_path.open() as f:
            manifest = json.load(f)

        manifest["configuration"] = configuration_model.schema()

        with self.manifest_path.open("w") as out:
            out.write(json.dumps(manifest, indent=2))

        print(f"[green][+][/green] Updated {self.manifest_path}")
