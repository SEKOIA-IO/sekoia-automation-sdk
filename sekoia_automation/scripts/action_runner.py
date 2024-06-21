import ast
import importlib.util
import json
import sys
from pathlib import Path

from jsonschema import validate

from sekoia_automation.module import Module


class ModuleItemRunner:
    def __init__(self, class_name: str, module_path: str):
        self.__class_name = class_name
        self.__module_path = (
            module_path if isinstance(module_path, Path) else Path(module_path)
        ).resolve()

    @staticmethod
    def load_class_from_path(path: Path | str, class_name: str):
        """
        @todo having issues with relative imports in modules (e.g. metrics)
        """
        if isinstance(path, Path):
            path = str(path)

        # Add the directory containing the module to sys.path
        module_dir = "/".join(path.split("/")[:-1])
        if module_dir not in sys.path:
            sys.path.append(module_dir)

        # Load the module
        module_name = path.split("/")[-1].split(".")[0]
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get the class from the module
        cls = getattr(module, class_name)
        return cls

    def find_file_with_module_item_class(self):
        for file_path in self.__module_path.rglob("*.py"):
            with open(file_path, "r") as f:
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

        return None

    def find_file_with_child_class(
        self, parent_class_to_find: str
    ) -> (str | None, Path | None):
        for file_path in self.__module_path.rglob("*.py"):
            with open(file_path, "r") as f:
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
        from _ast import AST

        main_py_path = self.__module_path / "main.py"
        with open(main_py_path, "rt") as file:
            content = file.read()

        tree = ast.parse(content)

        module_item_to_docker_param = {}

        node: AST
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

    def get_manifest_by_docker_param(
        self, prefix: str, docker_param: str
    ) -> dict | None:
        manifests = self.__module_path.glob(f"{prefix}*.json")
        for manifest_path in manifests:
            with open(manifest_path, "rt") as file:
                manifest = json.load(file)

            if manifest.get("docker_parameters") == docker_param:
                return manifest

    def run(self, args: dict, module_conf: dict = None) -> dict:
        cls_to_docker = self.get_docker_params_from_main_py()
        docker_param = cls_to_docker[self.__class_name]
        manifest = self.get_manifest_by_docker_param(
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

        if module_class_name is None:
            module = Module()

        else:
            module_cls = self.load_class_from_path(module_class_path, module_class_name)

            # Prepare module configuration
            module_annotations = module_cls.__annotations__
            module_config_cls = module_annotations["configuration"]
            conf_args = module_conf if module_conf else {}
            module_conf = module_config_cls(**conf_args)

            module = module_cls()
            module.configuration = module_conf

        file_path = self.find_file_with_module_item_class()
        module_item_cls = self.load_class_from_path(
            path=file_path, class_name=self.__class_name
        )
        module_item = module_item_cls(
            module=module, data_path=Path(".")
        )  # @todo set custom path?

        results = module_item.run(args)

        # check result
        validate(instance=results, schema=results_schema)
        return results


if __name__ == "__main__":
    class_name = "RequestAction"
    module_name = "HTTP"
    args = {"method": "get", "url": "https://dummyjson.com/test"}

    c = ModuleItemRunner(module_path=module_name, class_name=class_name)
    print(c.run(args=args))
