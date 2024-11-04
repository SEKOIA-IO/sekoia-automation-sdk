import json
import re
from pathlib import Path
from shutil import copytree
from tempfile import mkdtemp
from unittest.mock import patch

import pytest
import requests_mock
import typer

from sekoia_automation.scripts.sync_library import SyncLibrary

SYMPOHNY_URL = "https://api.test.mock/v1/symphony"
API_KEY = "mock_api_key"
PAT = "mock_PAT"
USER = "mock_username"


@pytest.fixture
def module():
    with open("tests/data/sample_module/manifest.json") as f:
        module = json.load(f)
        return module


@pytest.fixture
def action():
    with open("tests/data/sample_module/action_request.json") as f:
        action = json.load(f)
        return action


@pytest.fixture
def trigger():
    with open("tests/data/sample_module/trigger_sekoiaio_alert_created.json") as f:
        trigger = json.load(f)
        return trigger


@pytest.fixture
def connector():
    with open("tests/data/sample_module/connector_test.json") as f:
        connector = json.load(f)
        return connector


@pytest.fixture
def tmp_module(tmp_path):
    copytree(Path("tests/data"), str(tmp_path), dirs_exist_ok=True)
    tmp_path.joinpath("sample_module").joinpath("trigger_test.json").unlink()
    yield tmp_path


@requests_mock.Mocker(kw="m")
def test_no_module_success(tmp_module, module, action, trigger, connector, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=200, json={}
    )
    kwargs["m"].register_uri("PATCH", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, tmp_module)
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 8
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "PATCH"
    assert history[1].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert "docker" in history[1].json()
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[2].method == "GET"
    assert history[2].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[2].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[3].method == "PATCH"
    assert history[3].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[3].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[4].method == "GET"
    assert history[4].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[4].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[5].method == "PATCH"
    assert history[5].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[5].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[6].method == "GET"
    assert history[6].url == f"{SYMPOHNY_URL}/connectors/{connector['uuid']}"
    assert history[6].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[7].method == "PATCH"
    assert history[7].url == f"{SYMPOHNY_URL}/connectors/{connector['uuid']}"
    assert history[7].headers["Authorization"] == f"Bearer {API_KEY}"


@requests_mock.Mocker(kw="m")
def test_no_module_404(tmp_module, module, action, trigger, connector, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=404, json={}
    )
    kwargs["m"].register_uri("POST", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, tmp_module)
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 8
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "POST"
    assert history[1].url == f"{SYMPOHNY_URL}/modules"
    assert "docker" in history[1].json()
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[2].method == "GET"
    assert history[2].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[2].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[3].method == "POST"
    assert history[3].url == f"{SYMPOHNY_URL}/triggers"
    assert history[3].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[4].method == "GET"
    assert history[4].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[4].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[5].method == "POST"
    assert history[5].url == f"{SYMPOHNY_URL}/actions"
    assert history[5].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[6].method == "GET"
    assert history[6].url == f"{SYMPOHNY_URL}/connectors/{connector['uuid']}"
    assert history[6].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[7].method == "POST"
    assert history[7].url == f"{SYMPOHNY_URL}/connectors"
    assert history[7].headers["Authorization"] == f"Bearer {API_KEY}"


@requests_mock.Mocker(kw="m")
def test_no_module_other_code(tmp_module, module, action, trigger, connector, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=418, json={}
    )
    kwargs["m"].register_uri("POST", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, tmp_module)
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 4
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "GET"
    assert history[1].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[2].method == "GET"
    assert history[2].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[2].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[3].method == "GET"
    assert history[3].url == f"{SYMPOHNY_URL}/connectors/{connector['uuid']}"
    assert history[3].headers["Authorization"] == f"Bearer {API_KEY}"


@requests_mock.Mocker(kw="m")
def test_with_module(tmp_module, module, action, trigger, connector, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=200, json={}
    )
    kwargs["m"].register_uri("PATCH", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, tmp_module, module="sample_module")
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 8
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "PATCH"
    assert history[1].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"
    assert "docker" in history[1].json()
    assert history[2].method == "GET"
    assert history[2].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[2].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[3].method == "PATCH"
    assert history[3].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[3].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[4].method == "GET"
    assert history[4].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[4].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[5].method == "PATCH"
    assert history[5].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[5].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[6].method == "GET"
    assert history[6].url == f"{SYMPOHNY_URL}/connectors/{connector['uuid']}"
    assert history[6].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[7].method == "PATCH"
    assert history[7].url == f"{SYMPOHNY_URL}/connectors/{connector['uuid']}"
    assert history[7].headers["Authorization"] == f"Bearer {API_KEY}"


def test_with_module_invalid_name():
    sync_lib = SyncLibrary(
        SYMPOHNY_URL,
        API_KEY,
        Path("tests/data"),
        module="invalid_module_name",
    )
    with pytest.raises(FileNotFoundError):
        sync_lib.execute()


@requests_mock.Mocker(kw="m")
def test_registry_check_default_success(module, **kwargs):
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), registry_pat=PAT)
    kwargs["m"].register_uri(
        "GET",
        re.compile("https://ghcr.io/.*"),
        status_code=200,
        json={"token": API_KEY},
    )
    assert lib.check_image_on_registry(
        lib._get_module_docker_name(module), module["version"]
    )

    history = kwargs["m"].request_history
    assert len(history) == 1
    assert history[0].method == "GET"
    assert (
        history[0].url
        == f"https://ghcr.io/v2/sekoia-io/{lib.DOCKER_PREFIX}-{module['slug']}/\
manifests/{module['version']}"
    )


@requests_mock.Mocker(kw="m")
def test_registry_check_default_fail(module, **kwargs):
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT)
    kwargs["m"].register_uri(
        "GET",
        re.compile("https://ghcr.io/v2/sekoia-io.*"),
        status_code=404,
    )
    assert not lib.check_image_on_registry(
        lib._get_module_docker_name(module), module["version"]
    )

    history = kwargs["m"].request_history
    assert len(history) == 1
    assert history[0].method == "GET"
    assert (
        history[0].url
        == f"https://ghcr.io/v2/sekoia-io/{lib.DOCKER_PREFIX}-{module['slug']}/\
manifests/{module['version']}"
    )


@requests_mock.Mocker(kw="m")
def test_registry_check_custom_success(module, **kwargs):
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT)
    custom_path = "foo.bar"
    custom_pathinfo = "sekoia-io"
    image_name = lib._get_module_docker_name(module)
    module["docker"] = f"{custom_path}/{custom_pathinfo}/{image_name}"

    kwargs["m"].register_uri(
        "GET",
        re.compile(f"https://{custom_path}.*"),
        status_code=200,
        json={"token": API_KEY},
    )
    assert lib.check_image_on_registry(module["docker"], module["version"])

    history = kwargs["m"].request_history
    assert len(history) == 1
    assert history[0].method == "GET"
    assert (
        history[0].url
        == f"https://{custom_path}/v2/{custom_pathinfo}/{image_name}/\
manifests/{module['version']}"
    )


@requests_mock.Mocker(kw="m")
def test_registry_check_not_found(module, **kwargs):
    custom_path = "foo.bar"
    custom_pathinfo = "sekoia-io"
    lib = SyncLibrary(
        SYMPOHNY_URL,
        API_KEY,
        Path("tests/data"),
        registry=custom_path,
        namespace=custom_pathinfo,
    )
    module["docker"] = lib._get_module_docker_name(module)

    kwargs["m"].register_uri(
        "GET",
        f"https://{custom_path}/v2/sekoia-io/automation-module-sample/manifests/0.1",
        status_code=404,
    )
    assert lib.check_image_on_registry(module["docker"], module["version"]) is False

    history = kwargs["m"].request_history
    assert len(history) == 1


def test_get_module_logo():
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), registry_check=True)
    path = Path(mkdtemp())
    assert lib.get_module_logo(path) is None

    svg = path.joinpath("logo.svg")
    svg.touch()
    assert "svg+xml;base64" in lib.get_module_logo(path)
    svg.unlink()

    png = path.joinpath("logo.png")
    png.touch()
    assert "png;base64" in lib.get_module_logo(path)
    png.unlink()


def test_load_module_docker_image_not_found():
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), registry_check=True)
    with patch(
        "sekoia_automation.scripts.sync_library.SyncLibrary.check_image_on_registry"
    ) as mock:
        mock.return_value = False
        with pytest.raises(typer.Exit):
            lib.load_module(Path("tests/data/sample_module"))


def test_get_module_docker_name():
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"))

    manifest = {"docker": "foo", "slug": "bar"}
    assert (
        lib._get_module_docker_name(manifest)
        == "ghcr.io/sekoia-io/automation-module-bar"
    )

    manifest.pop("slug")
    with pytest.raises(ValueError):
        lib._get_module_docker_name(manifest)


def test_sync_module_create_error(requests_mock):
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"))

    requests_mock.get(
        f"{SYMPOHNY_URL}/modules/eaa1d29c-4c34-42c6-8275-2da1c8cca129",
        status_code=404,
    )
    requests_mock.post(
        f"{SYMPOHNY_URL}/modules",
        status_code=500,
        json={"error": "Internal Server Error"},
    )
    with pytest.raises(typer.Exit):
        lib.sync_module(
            {"name": "My Module", "uuid": "eaa1d29c-4c34-42c6-8275-2da1c8cca129"}
        )


def test_sync_module_update_error(requests_mock):
    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"))

    requests_mock.get(
        f"{SYMPOHNY_URL}/modules/eaa1d29c-4c34-42c6-8275-2da1c8cca129",
        status_code=200,
        json={
            "name": "My Module",
            "uuid": "eaa1d29c-4c34-42c6-8275-2da1c8cca129",
            "version": "0.1",
        },
    )
    requests_mock.patch(
        f"{SYMPOHNY_URL}/modules/eaa1d29c-4c34-42c6-8275-2da1c8cca129",
        status_code=500,
        json={"error": "Internal Server Error"},
    )
    with pytest.raises(typer.Exit):
        lib.sync_module(
            {
                "name": "My Module",
                "uuid": "eaa1d29c-4c34-42c6-8275-2da1c8cca129",
                "version": "0.2",
            }
        )
