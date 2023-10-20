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
from sekoia_automation.connector import Connector
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
        connectors: set[type[Connector]],
    ):
        module = import_module(name)

        for _, obj in getmembers(module, isclass):
            if not isabstract(obj):
                if issubclass(obj, Action):
                    actions.add(obj)
                elif issubclass(obj, Connector):
                    connectors.add(obj)
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
        connectors = set()

        for _, name, ispkg in walk_packages([self.base_path.as_posix()]):
            if not ispkg and not (name == "tests" or name.startswith("tests.")):
                self.inspect_module(name, modules, actions, triggers, connectors)

        if len(modules) != 1:
            print("[bold red][!] Found 0 or more than 1 module, aborting[/bold red]")
            raise typer.Exit(code=1)
        module = next(iter(modules))

        self.generate_main(module, actions, triggers)
        self.generate_action_manifests(actions)
        self.generate_trigger_manifests(triggers)
        self.generate_connector_manifests(connectors)
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

    def generate_connector_manifests(self, connectors: set[type[Connector]]):
        for connector in connectors:
            name = connector.name or connector.__name__
            filepath = (
                self.base_path / f"connector_{name.lower().replace(' ', '_')}.json"
            )

            manifest: dict[str, str | dict | None] = {
                "name": name,
                "description": connector.description,
                "uuid": str(uuid5(self.module_uuid, name)),
                "docker_parameters": connector.__name__,
                "arguments": {},
                "results": {},
            }

            if connector.results_model:
                manifest["results"] = connector.results_model.schema()

            if configuration_model := get_annotation_for(connector, "configuration"):
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
        self.add_secrets_to_configuration(
            manifest["configuration"], configuration_model.__fields__.values()
        )

        with self.manifest_path.open("w") as out:
            out.write(json.dumps(manifest, indent=2))

        print(f"[green][+][/green] Updated {self.manifest_path}")

    @staticmethod
    def add_secrets_to_configuration(config, config_fields):
        """Add module conf's secrets to the manifest, if any

        If the module has secrets, they are handled by Pandytic as if
        the parameter's name is "secret". We parse the model's fieds
        to find if such secrets exist and if so, we remove the
        "secret" field from the generated JSON and add fields with the
        right names instead

        Parameters
        ----------
        config : dict[str, Any]
            Config generated by Pydantic from the Model
        config_fields :
            Raw list of fields in the module's Model
        """
        for field in config_fields:
            if field.field_info.extra.get("secret", False):
                name = field.name

                # By default Pydantic adds the extra field "secret"
                # to the generated manifest
                # This is not the behavior that we want
                config["properties"][name].pop("secret")

                if "secrets" in config:
                    config["secrets"].append(name)
                else:
                    config["secrets"] = [name]
