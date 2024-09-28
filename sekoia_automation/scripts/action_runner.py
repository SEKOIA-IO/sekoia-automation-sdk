import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import validate

from sekoia_automation.module import Module


class ModuleItemRunner:
    def __init__(
        self,
        class_name: str,
        module_name: str,
        root_path: Path,
        data_path: Path = Path("."),
    ):
        self.__class_name = class_name
        self.__root_path = root_path.resolve()  # `automation-library` folder by default
        self.__module_path = (root_path / module_name).resolve()
        self.__data_path = data_path

        # Add the directory containing the module to sys.path
        if str(self.__module_path) not in sys.path:
            sys.path.append(str(self.__module_path))

    def load_class_from_path(self, path: Path | str, class_name: str) -> type:
        # Load the module
        module_name = (
            str(Path(path).resolve().relative_to(self.__root_path))
            .replace("/", ".")
            .rstrip(".py")
        )
        spec = importlib.util.spec_from_file_location(module_name, path)  # type: ignore
        module = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(module)  # type: ignore

        # Get the class from the module
        cls = getattr(module, class_name)
        return cls

    def find_file_with_module_item_class(self) -> Path:
        for file_path in self.__module_path.rglob("*.py"):
            with open(file_path) as f:
                try:
                    tree = ast.parse(f.read(), filename=str(file_path))
                except SyntaxError:
                    continue  # Skip files with syntax errors
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.ClassDef)
                        and node.name == self.__class_name
                    ):
                        return file_path

        raise FileNotFoundError(f"No file with class `{self.__class_name}`")

    def find_file_with_child_class(
        self, parent_class_to_find: str
    ) -> tuple[str | None, Path | None]:
        for file_path in self.__module_path.rglob("*.py"):
            with open(file_path) as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    continue  # Skip files with syntax errors
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        parent_classes = {
                            base.id for base in node.bases if hasattr(base, "id")
                        }
                        if parent_class_to_find in parent_classes:
                            return node.name, file_path

        return None, None

    def get_docker_params_from_main_py(self) -> dict:
        main_py_path = self.__module_path / "main.py"
        with open(main_py_path) as file:
            content = file.read()

        tree = ast.parse(content)

        module_item_to_docker_param = {}

        node: Any
        for node in ast.walk(tree):
            if (
                hasattr(node, "func")
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register"
            ):
                action_class = (
                    node.args[0].id if isinstance(node.args[0], ast.Name) else None
                )

                docker_param: str | None = None
                if len(node.args) > 1 and isinstance(node.args[1], ast.Str):
                    # provided as positional arg
                    docker_param = node.args[1].s

                elif len(node.keywords) > 0:
                    # provided as keyword arg
                    docker_param = node.keywords[0].value.s

                module_item_to_docker_param[action_class] = docker_param

        return module_item_to_docker_param

    def get_manifest_by_docker_param(self, prefix: str, docker_param: str) -> dict:
        manifests = self.__module_path.glob(f"{prefix}*.json")
        for manifest_path in manifests:
            with open(manifest_path) as file:
                manifest = json.load(file)

            if manifest.get("docker_parameters") == docker_param:
                return manifest

        return {}

    def get_module_configuration_schema(self) -> dict:
        manifest_path = self.__module_path / "manifest.json"
        with open(manifest_path) as file:
            manifest = json.load(file)

        return manifest.get("configuration", {})

    @staticmethod
    def get_module_item_type(cls):
        def __iter_all_parents(c):
            result = []
            parent_cls = c.__bases__

            result.extend(parent_cls)
            for parent in parent_cls:
                result.extend(__iter_all_parents(parent))

            return result

        parents_labels = {item.__name__: item for item in __iter_all_parents(cls)}
        if "Connector" in parents_labels:
            return "Connector"

        elif "Action" in parents_labels:
            return "Action"

        elif "Trigger" in parents_labels:
            return "Trigger"

        raise ValueError("Incorrect class")

    def run(self, args: dict) -> dict | None:
        cls_to_docker = self.get_docker_params_from_main_py()
        docker_param = cls_to_docker[self.__class_name]
        manifest: dict = self.get_manifest_by_docker_param(
            docker_param=docker_param, prefix=""
        )

        arguments_schema = manifest.get("arguments")
        results_schema = manifest.get(
            "results", {}
        )  # no `results` schema for connectors

        # check inputs
        validate(instance=args, schema=arguments_schema)

        # find and load Module class
        module_class_name, module_class_path = self.find_file_with_child_class(
            parent_class_to_find="Module"
        )

        if module_class_name is None or module_class_path is None:
            module = Module()

            module_conf_schema = self.get_module_configuration_schema()
            module_args = {
                k: args.get(k) for k in module_conf_schema.get("properties", [])
            }
            if len(module_args) > 0:
                validate(instance=module_args, schema=module_conf_schema)
                module.configuration = module_args

        else:
            module_cls = self.load_class_from_path(module_class_path, module_class_name)

            # Prepare module configuration
            module_annotations = module_cls.__annotations__
            module_config_cls = module_annotations["configuration"]
            conf_args = {key: args.get(key) for key in module_config_cls.__fields__}
            module_conf = module_config_cls(**conf_args)

            module = module_cls()
            module.configuration = module_conf

        file_path = self.find_file_with_module_item_class()
        module_item_cls = self.load_class_from_path(
            path=file_path, class_name=self.__class_name
        )

        module_item = module_item_cls(module=module, data_path=self.__data_path)

        module_item_type = self.get_module_item_type(module_item_cls)
        if module_item_type == "Action":
            results = module_item.run(args)

            # check result
            validate(instance=results, schema=results_schema)
            return results

        else:
            module_item_annotations = module_item_cls.__annotations__
            module_item_config_cls = module_item_annotations["configuration"]
            module_item_conf = module_item_config_cls(**args)

            module_item.configuration = module_item_conf
            module_item.run()

            return None
