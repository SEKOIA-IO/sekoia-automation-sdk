import json
from base64 import b64encode
from pathlib import Path


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
