#!/usr/bin/env python3
import json
import os
import re
import shutil
from functools import cached_property
from pathlib import Path
from uuid import uuid4

import requests
import typer
from black import Mode, WriteBack, format_file_in_place
from requests import Response
from rich import print


class OpenApiToModule:
    class_template = """
class {name}(GenericAPIAction):
    verb = "{verb}"
    endpoint = base_url + "{endpoint}"
    query_parameters = {query_parameters}
"""

    @cached_property
    def swagger(self) -> dict:
        """
        Read a swagger from a specified url or from a file.
        """
        if self.swagger_file.startswith("http") and self.swagger_file.endswith(".json"):
            response: Response = requests.get(
                self.swagger_file, headers={"Accept": "application/json"}, timeout=30
            )
            response.raise_for_status()
            return response.json()

        with open(self.swagger_file) as fd:
            return json.load(fd)

    @property
    def module_name(self) -> str:
        return self.swagger["info"]["title"]

    @property
    def python_module_name(self) -> str:
        return (
            self.module_name.replace(".", "_")
            .replace(" ", "_")
            .replace("-", "_")
            .lower()
        )

    @property
    def module_path(self) -> Path:
        return self.modules_path / self.module_name

    def __init__(self, modules_path: Path, swagger_file: str, use_tags: bool):
        self.swagger_file = swagger_file
        self.use_tags = use_tags
        self.modules_path = modules_path
        self.actions: list[str] = []
        self.classes: list[str] = []

    def add_results_to_action(self, action: dict, action_method: dict):
        for response in action_method["responses"].values():
            if "schema" in response and "$ref" in response["schema"]:
                action["results"] = self.swagger["definitions"].get(
                    response["schema"]["$ref"].split("/definitions/")[1]
                )
                return

    @staticmethod
    def get_properties(endpoint_params: dict, action_method: dict) -> tuple[dict, list]:
        """
        Get properties available for the given endpoint.

        It returns a tuple containing the properties definition
        and a list of required properties.
        """
        required: list = []
        properties: dict = {}

        # Endpoint parameters
        for param in endpoint_params:
            param_name = param["name"]
            required.append(param_name)
            prop = {"in": param["in"]}
            if _type := param.get("type"):
                prop["type"] = _type
            properties.update({param_name: prop})

        # Parameters from methods
        parameters = action_method.get("parameters", [])

        for param in parameters:
            param_in = param["in"]
            param_name = param["name"]
            param_required = param.get("required", False)
            if param_required:
                required.append(param_name)

            if param_in in ["body", "formData"] or "schema" in param.keys():
                param = param["schema"]
                for v in param.get("properties", {}).values():
                    v.update({"in": param_in})

                properties.update(param.get("properties", {}))
                required += param.get("required", [])
                continue
            prop = {"in": param_in}
            if _type := param.get("type"):
                prop["type"] = _type

            properties.update({param_name: prop})

        return properties, required

    @staticmethod
    def get_action_name(
        action_method: dict, docker_parameters: str, use_tags: bool
    ) -> str:
        name: str = ""

        if action_method.get("summary"):
            if use_tags and action_method.get("tags"):
                name = "-".join(action_method["tags"])
                name += "_"

            name += action_method["summary"]
        else:
            name = docker_parameters

        return re.sub("[^A-Za-z1-9]", "_", name).lower()

    def generate_actions(self, endpoint: str, methods: dict):
        list_methods: list = list(methods.keys())

        endpoint_params: dict = methods.get("parameters", {})
        for method in list_methods:
            if method not in ["get", "post", "delete", "patch", "put"]:
                continue

            action_method: dict = methods[method]

            docker_parameters: str = f"{method}-{endpoint.lstrip('/')}"
            name: str = self.get_action_name(
                action_method, docker_parameters, self.use_tags
            )
            action_path: str = os.path.join(self.module_path, f"action_{name}.json")
            if action_path in self.actions:
                print("[orange3] Action name '{name}' already used[/orange3]")
                continue

            action: dict = {
                "uuid": str(uuid4()),
                "name": name,
                "docker_parameters": docker_parameters,
            }
            desc: str = str(action_method.get("description"))

            if desc:
                action["description"] = desc

            properties, required = self.get_properties(
                endpoint_params=endpoint_params, action_method=action_method
            )

            arguments: dict = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "title": name,
                "properties": properties,
            }

            if required:
                arguments["required"] = required

            action["arguments"] = arguments
            self.add_results_to_action(action=action, action_method=action_method)

            with open(action_path, "w") as fd:
                fd.write(json.dumps(action, indent=4))

            self.actions.append(action_path)

    def generate_module(self) -> str:
        info = self.swagger["info"]
        docker: str = (
            f"sekoia-playbook-module-{info.get('title').replace(' ', '-').lower()}"
        )
        self.module_path.mkdir(exist_ok=True)
        with (self.module_path / "manifest.json").open("w") as fd:
            manifest: dict = {
                "uuid": str(uuid4()),
                "name": info["title"],
                "docker": docker,
            }
            if description := info.get("description"):
                manifest["description"] = description

            fd.write(json.dumps(manifest, indent=4))

        return docker

    def generate_classes(self):
        content = (
            'from sekoia_automation.action import GenericAPIAction\n\n\nbase_url = ""\n'
        )

        for file in self.actions:
            with open(file) as fd:
                action_json: dict = json.load(fd)

            docker_parameters = action_json["docker_parameters"]
            query_parameters: list = [
                x
                for x, v in action_json["arguments"]["properties"].items()
                if v.get("in") == "query"
            ]

            name = re.sub("[^A-Za-z1-9]", "-", action_json["name"])
            for article in ["a", "an", "the"]:
                name = name.replace("-" + article + "-", "-")
            name = "".join(list(map(str.capitalize, name.split("-"))))

            verb, endpoint = docker_parameters.split("-", 1)

            content += self.class_template.format(
                name=name,
                verb=verb,
                endpoint=endpoint,
                query_parameters=query_parameters,
            )

            self.classes.append((name, docker_parameters))

        module_dir = self.module_path / self.python_module_name
        os.makedirs(module_dir, exist_ok=True)
        with (module_dir / "__init__.py").open("w") as f:
            f.write(content)

        # Format code with black
        format_file_in_place(
            src=(module_dir / "__init__.py"),
            fast=False,
            mode=Mode(),
            write_back=WriteBack.YES,
        )

    def generate_main(self):
        with (self.module_path / "main.py").open("w") as f:
            f.write("from sekoia_automation.module import Module\n")
            f.write(f"from {self.python_module_name} import (\n")
            for class_name, _ in self.classes:
                f.write(f"    {class_name},\n")
            f.write(")\n\n")
            f.write('if __name__ == "__main__":\n')
            f.write("    module = Module()\n")
            for class_name, action_id in self.classes:
                f.write(f'    module.register({class_name}, "{action_id}")\n')
            f.write("    module.run()\n")

        # Format code with black
        format_file_in_place(
            src=(self.module_path / "main.py"),
            fast=False,
            mode=Mode(),
            write_back=WriteBack.YES,
        )

    def run(self):
        if "info" not in self.swagger or "title" not in self.swagger["info"]:
            print("[bold red][!] Swagger file doesn't have a title[/bold red]")
            raise typer.Exit(code=1)

        if self.module_path.exists():
            print("[orange3][!]Module already exists, overriding it[/orange3]")
            shutil.rmtree(self.module_path)

        print("Generating module ...")
        self.generate_module()
        print(f"Module generated at {self.module_path}")

        print("Generating actions ...")
        for endpoint, methods in self.swagger.get("paths").items():
            self.generate_actions(
                endpoint=endpoint,
                methods=methods,
            )
        print(f"{len(self.actions)} actions have been generated")

        print("Generating classes ...")
        self.generate_classes()
        print(f"{len(self.classes)} classes have been generated")

        print("Generating main.py ...")
        self.generate_main()
        print("main.py generated")
