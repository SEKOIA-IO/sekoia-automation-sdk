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

app = typer.Typer(
    help="SEKOIA.IO's automation helper to generate playbook modules",
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
    SEKOIA.IO's documentation repository.

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


if __name__ == "__main__":
    app()
