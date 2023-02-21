import json
import os
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import Result
from typer.testing import CliRunner
from yaml import Loader

from sekoia_automation.cli import app

runner = CliRunner()


@pytest.fixture
def swagger_path():
    return Path(os.path.dirname(__file__)).resolve().joinpath("data", "swagger.json")


def test_new_module(tmp_path):
    module = "My Module"
    description = "My Description"
    res: Result = runner.invoke(
        app, ["new-module", str(tmp_path)], input=f"{module}\n{description}\n"
    )
    assert res.exit_code == 0

    module_path = tmp_path.joinpath(module)
    assert module_path.is_dir()

    manifest = json.loads(module_path.joinpath("manifest.json").read_text())
    assert manifest["name"] == module
    assert manifest["description"] == description

    assert module_path.joinpath("main.py").is_file()
    assert module_path.joinpath("tests").is_dir()
    assert module_path.joinpath("my_module_modules").is_dir()


def test_generate_documentation_invalid_modules_path(tmp_path):
    res: Result = runner.invoke(app, ["generate-documentation", "foo", "bar"])
    assert res.exit_code == 1


def test_generate_documentation_invalid_documentation_path(tmp_path):
    current_dir = Path(os.path.dirname(__file__)).resolve()
    modules_path = current_dir.joinpath("data")
    res: Result = runner.invoke(
        app, ["generate-documentation", str(modules_path), "bar"]
    )
    assert res.exit_code == 1


def test_generate_documentation_invalid_module_path(tmp_path):
    current_dir = Path(os.path.dirname(__file__)).resolve()
    modules_path = current_dir.joinpath("data")
    documentation_path = tmp_path.joinpath("documentation")
    shutil.copytree(current_dir.joinpath("data", "documentation"), documentation_path)
    res: Result = runner.invoke(
        app,
        [
            "generate-documentation",
            str(modules_path),
            str(documentation_path),
            "--module",
            "foo",
        ],
    )
    assert res.exit_code == 1


def test_generate_documentation(tmp_path):
    current_dir = Path(os.path.dirname(__file__)).resolve()
    modules_path = current_dir.joinpath("data")
    documentation_path = tmp_path.joinpath("documentation")
    shutil.copytree(current_dir.joinpath("data", "documentation"), documentation_path)
    res: Result = runner.invoke(
        app, ["generate-documentation", str(modules_path), str(documentation_path)]
    )
    assert res.exit_code == 0

    assert documentation_path.joinpath(
        "docs/assets/playbooks/library/test-module.svg"
    ).exists()
    assert documentation_path.joinpath(
        "_shared_content/automate/library/test-module.md"
    ).exists()

    with documentation_path.joinpath("mkdocs.yml").open("r") as fp:
        manifest = yaml.load(fp, Loader=Loader)

    assert (
        manifest["nav"][0]["SEKOIA.IO XDR"][0]["Features"][0]["Automate"][0][
            "Actions Library"
        ][0]["Test Module"]
        == "xdr/features/automate/library/test-module.md"
    )
    assert (
        manifest["nav"][1]["SEKOIA.IO TIP"][0]["Features"][0]["Automate"][0][
            "Actions Library"
        ][0]["Test Module"]
        == "tip/features/automate/library/test-module.md"
    )


def test_openapi_to_module_no_title(tmp_path, swagger_path, requests_mock):
    with swagger_path.open() as fp:
        swagger = json.load(fp)
        swagger.pop("info")
    requests_mock.get("https://myswagger.com/swagger.json", json=swagger)
    res: Result = runner.invoke(
        app,
        ["openapi-to-module", str(tmp_path), "https://myswagger.com/swagger.json"],
    )
    assert res.exit_code == 1


def test_openapi_to_module(tmp_path, swagger_path):
    res: Result = runner.invoke(
        app,
        ["openapi-to-module", str(tmp_path), str(swagger_path)],
    )
    assert res.exit_code == 0
    module = tmp_path.joinpath("Dashboard API")
    assert module.is_dir()
    assert module.joinpath("manifest.json").exists()
    assert module.joinpath("main.py").exists()
    assert len(list(module.glob("action_*"))) > 0
    assert module.joinpath("dashboard_api", "__init__.py").exists()


def test_openapi_url_to_module(tmp_path, requests_mock, swagger_path):
    requests_mock.get(
        "https://myswagger.com/swagger.json", json=json.load(swagger_path.open())
    )

    module = tmp_path.joinpath("Dashboard API")
    module.mkdir()
    module.joinpath("should_be_removed").write_text("foo")

    res: Result = runner.invoke(
        app,
        [
            "openapi-to-module",
            str(tmp_path),
            "https://myswagger.com/swagger.json",
            "--tags",
        ],
    )
    assert res.exit_code == 0
    assert module.is_dir()
    assert not module.joinpath("should_be_removed").exists()
    assert module.joinpath("manifest.json").exists()
    assert module.joinpath("main.py").exists()
    assert len(list(module.glob("action_*"))) > 0
    assert module.joinpath("dashboard_api", "__init__.py").exists()
