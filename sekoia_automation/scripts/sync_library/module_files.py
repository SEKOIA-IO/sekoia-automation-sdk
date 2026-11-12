import json
from base64 import b64encode
from pathlib import Path

import typer
import yaml
from rich import print


def load_json_objects(module_path: Path, prefix: str) -> list:
    """Load the JSON files of a module whose name starts with a given prefix

    Args:
        module_path (Path): Path of the parent module
        prefix (str): Prefix of the files to load (action_, trigger_, connector_)

    Returns:
        list: List of objects related to the parent module
    """
    objects = []

    for filename in module_path.iterdir():
        if filename.name.endswith(".json") and filename.name.startswith(prefix):
            with filename.open() as fd:
                objects.append(json.load(fd))

    return objects


def load_actions(module_path: Path) -> list:
    """Load JSON files representing the actions linked to a module

    Args:
        module_path (Path): Path of the parent module

    Returns:
        list: List of actions related to the parent module
    """
    return load_json_objects(module_path, "action_")


def load_triggers(module_path: Path) -> list:
    """Load JSON files representing the triggers linked to a module

    Args:
        module_path (Path): Path of the parent module

    Returns:
        list: List of triggers related to the parent module
    """
    return load_json_objects(module_path, "trigger_")


def load_connectors(module_path: Path) -> list:
    """Load JSON files representing the connectors linked to a module

    Args:
        module_path (Path): Path of the parent module

    Returns:
        list: List of connectors related to the parent module
    """
    return load_json_objects(module_path, "connector_")


def hwl_action_to_payload(workflow: dict, filename: str, docker_image: str) -> dict:
    """Build the action object expected by the Playbook API from an HWL workflow

    The inputs and outputs of the workflow become the arguments and the results
    of the action, and its file name the Docker parameters

    Args:
        workflow (dict): Content of the HWL action file
        filename (str): Name of the HWL action file
        docker_image (str): The docker image running the HWL actions of the module

    Returns:
        dict: The action object

    Raises:
        typer.Exit: If the workflow has no name or no uuid, or an invalid input
    """
    for field in ("name", "uuid"):
        if not isinstance(workflow, dict) or not workflow.get(field):
            print(f"[bold red][!] HWL action {filename} has no {field}")
            raise typer.Exit(code=1)

    raw_inputs = workflow.get("inputs") or {}
    for name, schema in raw_inputs.items():
        if not isinstance(schema, dict):
            print(f"[bold red][!] HWL action {filename}: input {name} is invalid")
            raise typer.Exit(code=1)
    # Secret inputs are listed in the arguments instead of being flagged
    inputs = {
        name: {k: v for k, v in schema.items() if k != "secret"}
        for name, schema in raw_inputs.items()
    }
    secrets = [name for name, schema in raw_inputs.items() if schema.get("secret")]
    # Inputs having a default value or a constant do not need to be provided
    required = [k for k, v in inputs.items() if "default" not in v and "const" not in v]
    arguments: dict = {"type": "object", "properties": inputs}
    if required:
        arguments["required"] = required
    if secrets:
        arguments["secrets"] = secrets

    action = {
        "uuid": str(workflow["uuid"]),
        "name": workflow["name"],
        "docker": docker_image,
        "docker_parameters": filename,
        "arguments": arguments,
        "results": {"type": "object", "properties": workflow.get("outputs") or {}},
    }
    if workflow.get("description"):
        action["description"] = workflow["description"]

    return action


def load_hwl_actions(module_path: Path, docker_image: str) -> list:
    """Load YAML files representing the HWL actions linked to a module

    Args:
        module_path (Path): Path of the parent module
        docker_image (str): The docker image running the HWL actions of the module

    Returns:
        list: List of HWL actions related to the parent module
    """
    actions = []

    for filename in sorted(module_path.glob("action_*.yml")):
        try:
            with filename.open() as fd:
                workflow = yaml.safe_load(fd)
        except yaml.YAMLError as e:
            print(f"[bold red][!] HWL action {filename.name} is not valid YAML: {e}")
            raise typer.Exit(code=1)
        actions.append(hwl_action_to_payload(workflow, filename.name, docker_image))

    return actions


def set_docker(manifests: list, module_docker_image: str) -> list:
    """Loops over the Docker name of objets linked to a module and adds the Docker
    version if missing

    Args:
        manifests (list): List of dict representing the objects to be checked
        module_docker_image (str): The docker image as defined in the module

    Returns:
        list: Modified version of the manifests received as parameter
    """

    for manifest in manifests:
        if "docker" not in manifest or manifest["docker"] != module_docker_image:
            manifest["docker"] = module_docker_image

    return manifests


def get_module_logo(module_path: Path) -> str | None:
    """Checks if a logo exists for a given module and returns its path

    Args:
        module_path (Path): Path to the module to be checked

    Returns:
        str | None: Path to the logo if it exists; None otherwise
    """
    svglogo_path = module_path / "logo.svg"
    pnglogo_path = module_path / "logo.png"

    if svglogo_path.is_file():
        prefix = "data:image/svg+xml;base64,"
        path_to_use = svglogo_path
    elif pnglogo_path.is_file():
        prefix = "data:image/png;base64,"
        path_to_use = pnglogo_path
    else:
        return None

    with path_to_use.open("rb") as f:
        return f"{prefix}{b64encode(f.read()).decode('utf-8')}"


def get_module_changelog(module_path: Path) -> str | None:
    """Checks if a changelog exists for a given module and returns its path

    Args:
        module_path (Path): Path to the module to be checked

    Returns:
        str | None: Path to the logo if it exists; None otherwise
    """
    changelog_path = module_path / "CHANGELOG.md"

    if not changelog_path.is_file():
        return None

    with changelog_path.open() as f:
        return f.read()
