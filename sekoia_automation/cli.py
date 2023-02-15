import os
from pathlib import Path

import typer

from sekoia_automation.scripts.files_generator import FilesGenerator

app = typer.Typer()


@app.command(name="generate-files")
def generate_files(
    module: Path = typer.Argument(
        Path("."), exists=True, file_okay=False, dir_okay=True, writable=True
    )
):
    # Make sure we are in a module directory by verifying that there is a manifest
    if not os.path.isfile("manifest.json"):
        typer.echo(
            "[!] No manifest.json found. "
            "Execute this command from a module's root directory."
        )
        raise typer.Exit(code=1)

    FilesGenerator(module).execute()


@app.callback()
def callback():
    """
    Force having `generate-files` as a command.
    It can be removed once another command is added.

    See https://typer.tiangolo.com/tutorial/commands/one-or-multiple/
    """
    pass


if __name__ == "__main__":
    app()
