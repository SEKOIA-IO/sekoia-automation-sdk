import os
from pathlib import Path
from typing import Optional

import typer
from cookiecutter.main import cookiecutter

from sekoia_automation.scripts.documentation.generate import (
    DocumentationGenerator,
)
from sekoia_automation.scripts.files_generator import FilesGenerator
from sekoia_automation.scripts.openapi import OpenApiToModule
from sekoia_automation.scripts.sync_library import SyncLibrary
from sekoia_automation.scripts.update_sdk_version import SDKUpdater

app = typer.Typer(
    help="Sekoia.io's automation helper to generate playbook modules",
    rich_markup_mode="markdown",
)
OptionalPath = Optional[Path]
OptionalStr = Optional[str]


@app.command(name="generate-files-from-code")
def generate_files(
    module: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Path to the module to work on",
    )
):
    """
    Generate modules files from the actions and triggers python code.

    It will create:

        * The main python entrypoint

        * The actions manifests

        * The triggers manifests

        * Update the module manifest to add the configurations schema
    """
    FilesGenerator(module).execute()


@app.command(name="new-module")
def new_module(
    output_dir: Path = typer.Argument(
        ..., help="Path where the module must be created"
    ),
    module_name: str = typer.Option(..., help="Name of the module", prompt=True),
    description: str = typer.Option("", help="Description of the module", prompt=True),
    overwrite_if_exists: bool = typer.Option(
        False, help="Overwrite the output directory if it exists"
    ),
):
    """
    Generate a new empty playbook module.

    The script will ask for:

        * The name of the module

        * Its description



    It will generate all the required files to have a working module:

        * The manifest

        * A docker file

        * The main entrypoint

        * A `pyproject.toml` file

        * A tests directory with some mocks

        * A base package for the module
    """
    current_dir = Path(os.path.dirname(__file__)).resolve()
    template = current_dir / "scripts" / "new_module" / "template"
    cookiecutter(
        template.as_posix(),
        overwrite_if_exists=overwrite_if_exists,
        output_dir=output_dir.as_posix(),
        no_input=True,
        extra_context={
            "module_name": module_name,
            "module_description": description,
            "module_dir": module_name,
        },
    )


@app.command(name="generate-documentation")
def generate_documentation(
    modules_path: Path = typer.Argument(..., help="Path to the playbook modules"),
    documentation_path: Path = typer.Argument(
        ..., help="Path to the documentation repository"
    ),
    module: OptionalStr = typer.Option(None, help="Module to deploy"),
):
    """
    Generate modules documentation.

    This script generates modules documentation and add it to
    Sekoia.io's documentation repository.

    If a module is provided only the documentation for this module will be generated
    """
    DocumentationGenerator(
        modules_path=modules_path,
        documentation_path=documentation_path,
        module=module,
    ).generate()


@app.command(name="openapi-to-module")
def openapi_to_module(
    modules_path: Path = typer.Argument(..., help="Path to the playbook modules"),
    swagger: str = typer.Argument(..., help="Path or URL to the swagger file"),
    tags: bool = typer.Option(False, help="Use Swagger Tags to get unique names"),
):
    """
    This script generates a new module from an OpenAPI specification

    It will generate the module with the required code from a swagger file.
    """
    OpenApiToModule(
        modules_path=modules_path, swagger_file=swagger, use_tags=tags
    ).run()


@app.command(name="synchronize-library")
def sync_library(
    playbook_url=typer.Argument(
        ..., envvar="PLAYBOOK_URL", help="URL of the Playbook API"
    ),
    api_key=typer.Argument(
        ..., envvar="PLAYBOOK_API_KEY", help="Secret key to connect to the Playbook API"
    ),
    modules_path: Path = typer.Option(".", help="Path to the playbook modules"),
    module: str = typer.Option("", help="Module to deploy. Default to all modules"),
    check_image_on_registry: bool = typer.Option(
        False, help="Whether to check registry for existing image"
    ),
    registry: OptionalStr = typer.Option(
        None, envvar="REGISTRY", help="Docker registry"
    ),
    namespace: OptionalStr = typer.Option(
        None, envvar="NAMESPACE", help="Docker namespace use by the images"
    ),
    registry_pat: OptionalStr = typer.Option(
        None, envvar="REGISTRY_PAT", help="Docker registry personal access token"
    ),
):
    """
    Synchronize the module library to Sekoia.io
    """
    SyncLibrary(
        playbook_url=playbook_url,
        api_key=api_key,
        modules_path=modules_path,
        module=module,
        registry_check=check_image_on_registry,
        registry=registry,
        namespace=namespace,
        registry_pat=registry_pat,
    ).execute()


@app.command(name="update-sdk-version")
def update_sekoia_library(
    modules_path: Path = typer.Option(".", help="Path to the playbook modules"),
):
    SDKUpdater(modules_path=modules_path).update_sdk_version()


if __name__ == "__main__":
    app()
