#!/usr/bin/env python3

"""
Load module library into database via the API
"""
import json
import re
from base64 import b64encode
from pathlib import Path
from posixpath import join as urljoin
from typing import Any

import requests
import typer
from requests.auth import HTTPBasicAuth
from rich import print


class SyncLibrary:
    DOCKER_PREFIX = "automation-module-"

    def __init__(
        self,
        playbook_url: str,
        api_key: str,
        modules_path: Path,
        registry_pat: str | None = None,
        registry_user: str | None = None,
        module: str = "",
        registry_check: bool = False,
    ):
        self.registry_pat = registry_pat
        self.registry_user = registry_user
        self.playbook_url = playbook_url
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        self.modules_path = modules_path
        self.module = module
        self.registry_check = registry_check

    def pprint(
        self, created: list, updated: list, up_to_date: list, errors: list, nb_tabs: int
    ):
        """Pretty print information on the current sync

        Args:
            created (list): Objects created through Playbook API
            updated (list): Objects updated
            up_to_date (list): Objects that were already up-to-date
            errors (list): Errors encountered during sync
            nb_tabs (int): Cue for vertical alignment
        """
        tab = "\t"
        if created:
            print(f"[green]{tab*nb_tabs}Crated: {', '.join(created)}[/green]")
        if updated:
            print(f"[green]{tab*nb_tabs}Updated: {', '.join(updated)}[/green]")
        if up_to_date:
            print(
                f"[green]{tab*nb_tabs}Already Up-To-Date: \
{', '.join(up_to_date)}[/green]"
            )
        if errors:
            err: str = "Error" if len(errors) == 1 else "Errors"
            print(f"[red]{tab*nb_tabs}{err}: {', '.join(errors)}[/red]")

    def sync_list(
        self, module_name: str, module_uuid: str, list_objects: list, name: str
    ):
        """Performs the syncing of objects linked to a module

        Args:
            module_name (str): Name of parent module
            module_uuid (str): UUID of parent module
            list_objects (list): List of objects to sync
            name (str): Type of objects to sync
        """
        created: list[str] = []
        updated: list[str] = []
        up_to_date: list[str] = []
        errors: list[str] = []

        for obj in list_objects:
            response = requests.get(
                urljoin(self.playbook_url, f"{name}s", obj["uuid"]),
                headers=self.headers,
            )
            obj_name = obj["name"]
            obj_uuid = obj["uuid"]

            if response.status_code not in (200, 404):
                errors.append(f"{{{obj_name}: {response.status_code}}}")

            elif response.status_code == 404:
                data: dict = obj.copy()
                data.update({"module_uuid": module_uuid})
                requests.post(
                    urljoin(self.playbook_url, f"{name}s"),
                    json=data,
                    headers=self.headers,
                )
                created.append(f"{obj_name}")

            else:
                content: dict = response.json()

                if "outputs" not in content:
                    content["outputs"] = {}

                if "outputs" not in obj:
                    obj["outputs"] = {}

                for k in content.keys():
                    if k in obj and content[k] == obj[k]:
                        del obj[k]

                if not obj:
                    up_to_date.append(f"{obj_name}")

                else:
                    updated.append(f"{obj_name}")
                    requests.patch(
                        urljoin(self.playbook_url, f"{name}s", obj_uuid),
                        json=obj,
                        headers=self.headers,
                    )

        print(f"\t{module_name}/{name}")
        self.pprint(
            created=created,
            updated=updated,
            up_to_date=up_to_date,
            errors=errors,
            nb_tabs=2,
        )

    def sync_module(self, module_info: dict[str, Any]):
        """Sync of a module

        Args:
            module_info (dict[str, Any]): Module data that can be found in its
                manifest.json
        """
        print(f"Module {module_info['name']}:", end=" ")
        response = requests.get(
            urljoin(f"{self.playbook_url}", "modules", module_info["uuid"]),
            headers=self.headers,
        )
        module_uuid: str = module_info["uuid"]

        if response.status_code not in (200, 404):
            print(f"[red]Error {response.status_code}[/red]")

        elif response.status_code == 404:
            requests.post(
                urljoin(self.playbook_url, "modules"),
                json=module_info,
                headers=self.headers,
            )
            print("Created")

        else:
            content: dict = response.json()
            mod_list: list = list(module_info.keys())

            for k in content.keys():
                if k not in mod_list:
                    module_info[k] = None

                if content[k] == module_info[k]:
                    del module_info[k]

            if not module_info:
                print("Already-Up-To-Date")
            else:
                requests.patch(
                    urljoin(self.playbook_url, "modules", module_uuid),
                    json=module_info,
                    headers=self.headers,
                )
                print("Updated")

    def load_actions(self, module_path: Path) -> list:
        """Load JSON files representing the actions linked to a module

        Args:
            module_path (Path): Path of the parent module

        Returns:
            list: List of actions related to the parent module
        """
        actions = []

        for filename in module_path.iterdir():
            if filename.name.endswith(".json") and filename.name.startswith("action_"):
                action_path = module_path / filename
                with action_path.open() as fd:
                    actions.append(json.load(fd))

        return actions

    def load_triggers(self, module_path: Path) -> list:
        """Load JSON files representing the triggers linked to a module

        Args:
            module_path (Path): Path of the parent module

        Returns:
            list: List of triggers related to the parent module
        """
        triggers = []

        for filename in module_path.iterdir():
            if filename.name.endswith(".json") and filename.name.startswith("trigger_"):
                trigger_path = module_path / filename
                with trigger_path.open() as fd:
                    triggers.append(json.load(fd))

        return triggers

    def set_docker(self, manifests: list, module: dict) -> list:
        """Loops over the Docker name of objets linked to a module and adds the Docker
        version if missing

        Args:
            manifests (list): List of dict representing the objects to be checked
            module (dict): Data dict of the parent module

        Returns:
            list: Modified version of the manifests received as parameter
        """
        module_docker_name = self._get_module_docker_name(module)
        for manifest in manifests:
            if "docker" not in manifest or manifest["docker"] == module_docker_name:
                manifest["docker"] = f"{module_docker_name}:{module['version']}"

        return manifests

    def get_module_logo(self, module_path: Path) -> str | None:
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

    def check_image_on_registry(
        self, docker_image: str, docker_image_version: str
    ) -> bool:
        """Checks if a Docker image exists on a registry

        If no registry is specified in the Module's manifest, we use a default value
        If the docker image name in the Module's manifest begins with a registry,
        this custom registry is used for the verification instead
        An image is considered to contain the registry path if it contains at least 2 /
        They delimit the path and the pathinfo fields
        e.g. my_registry.com/v2/my_docker_image

        Args:
            docker_image (str): Docker image name as specified in the manifest
            docker_image_version (str): Docker image version

        Returns:
            bool: True if the image exists on the registry or if we don't have access
                to a registry
                  False otherwise
        """
        assert self.registry_user and self.registry_pat
        auth = HTTPBasicAuth(self.registry_user, self.registry_pat)

        if match := re.match(r"(.*?)/(.*)/(.*)", docker_image):
            registry_path = match[1]
            registry_pathinfo = match[2]
            image_name = match[3]
        else:
            registry_path = "ghcr.io"
            registry_pathinfo = "v2/sekoialab"
            image_name = docker_image

        response = requests.get(
            f"https://{registry_path}/token",
            params={
                "service": registry_path,
                "scope": "repository:<repo>:pull",
                "client_id": "symphony-docker-image",
            },
            auth=auth,
        )
        if not response.ok:
            print(
                f"[bold red][!] Authentication against the docker registry "
                f"failed with status {response.status_code}"
            )
            raise typer.Exit(code=1)

        token = response.json()["token"]

        response = requests.get(
            f"https://{registry_path}/{registry_pathinfo}/{image_name}/manifests/\
{docker_image_version}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            },
        )

        return response.status_code == 200

    def load_module(self, module_path: Path):
        """Sync a module and its components (triggers, actions) using Playbook API

        Args:
            module_path (Path): Path to module to be synced

        Raises:
            typer.Exit: If the docker image of the module is not available
                on the registry, or we don't have access to the registry
        """
        manifest_path = module_path / "manifest.json"

        with manifest_path.open() as fd:
            module_info = json.load(fd)

        if self.registry_check and not self.check_image_on_registry(
            self._get_module_docker_name(module_info), module_info["version"]
        ):
            print(
                f"[bold red][!] Image {module_info['docker']}:{module_info['version']} "
                f"not available on registry"
            )
            raise typer.Exit(code=1)

        triggers = self.set_docker(self.load_triggers(module_path), module_info)
        actions = self.set_docker(self.load_actions(module_path), module_info)

        module_uuid: str = module_info["uuid"]
        module_name: str = module_info["name"]
        module_image: str | None = self.get_module_logo(module_path)

        if module_image:
            module_info["image"] = module_image

        self.sync_module(module_info)
        if triggers:
            self.sync_list(
                module_name=module_name,
                module_uuid=module_uuid,
                list_objects=triggers,
                name="trigger",
            )
            print()
        if actions:
            self.sync_list(
                module_name=module_name,
                module_uuid=module_uuid,
                list_objects=actions,
                name="action",
            )
            print()

    def load(self, library_path: Path):
        """Lods all modules that can be found in a given library

        Args:
            library_path (Path): Path to the library of modules
        """
        modules = [
            p
            for p in library_path.iterdir()
            if p.is_dir() and p.joinpath("manifest.json").exists()
        ]
        print(f"Loading {len(modules)} modules from library in database\n")

        for module in modules:
            self.load_module(library_path / module.name)

        print()

    def execute(self):
        """Entrypoint of the tool

        If the class was instanciated with the path to a given module, this method will
        attempt to load this module

        Otherwise, it will attempt to load all modules present in the library path
        specified
        """
        if self.registry_check and not (self.registry_pat and self.registry_user):
            print(
                "[bold red][!] Credentials must be provided to check image in registry"
            )
            raise typer.Exit(code=1)

        if not self.module:
            library_path = self.modules_path.absolute()
            print("Library path: ", library_path)
            self.load(
                library_path=library_path,
            )
        else:
            self.load_module(
                module_path=self.modules_path.joinpath(self.module).absolute(),
            )

    def _get_module_docker_name(self, manifest: dict) -> str:
        if docker := manifest.get("docker"):
            return docker
        if slug := manifest.get("slug"):
            return f"{self.DOCKER_PREFIX}{slug}"
        raise ValueError("Impossible to generate image name")
