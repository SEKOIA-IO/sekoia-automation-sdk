import json
import re
from pathlib import Path
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


@requests_mock.Mocker(kw="m")
def test_no_module_success(module, action, trigger, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=200, json={}
    )
    kwargs["m"].register_uri("PATCH", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER)
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 6
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "PATCH"
    assert history[1].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
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


@requests_mock.Mocker(kw="m")
def test_no_module_404(module, action, trigger, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=404, json={}
    )
    kwargs["m"].register_uri("POST", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER)
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 6
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "POST"
    assert history[1].url == f"{SYMPOHNY_URL}/modules"
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


@requests_mock.Mocker(kw="m")
def test_no_module_other_code(module, action, trigger, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=418, json={}
    )
    kwargs["m"].register_uri("POST", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER)
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 3
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "GET"
    assert history[1].url == f"{SYMPOHNY_URL}/triggers/{trigger['uuid']}"
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[2].method == "GET"
    assert history[2].url == f"{SYMPOHNY_URL}/actions/{action['uuid']}"
    assert history[2].headers["Authorization"] == f"Bearer {API_KEY}"


@requests_mock.Mocker(kw="m")
def test_with_module(module, action, trigger, **kwargs):
    kwargs["m"].register_uri(
        "GET", re.compile(f"{SYMPOHNY_URL}.*"), status_code=200, json={}
    )
    kwargs["m"].register_uri("PATCH", re.compile(f"{SYMPOHNY_URL}.*"))
    sync_lib = SyncLibrary(
        SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER, module="sample_module"
    )
    sync_lib.execute()

    history = kwargs["m"].request_history
    assert len(history) == 6
    assert history[0].method == "GET"
    assert history[0].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
    assert history[0].headers["Authorization"] == f"Bearer {API_KEY}"
    assert history[1].method == "PATCH"
    assert history[1].url == f"{SYMPOHNY_URL}/modules/{module['uuid']}"
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


def test_with_module_invalid_name():
    sync_lib = SyncLibrary(
        SYMPOHNY_URL,
        API_KEY,
        Path("tests/data"),
        PAT,
        USER,
        module="invalid_module_name",
    )
    with pytest.raises(FileNotFoundError):
        sync_lib.execute()


@requests_mock.Mocker(kw="m")
def test_registry_check_default_success(module, **kwargs):
    kwargs["m"].register_uri(
        "GET",
        re.compile("https://ghcr.io/.*"),
        status_code=200,
        json={"token": API_KEY},
    )
    assert SyncLibrary(
        SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER
    ).check_image_on_registry(module["docker"], module["version"])

    history = kwargs["m"].request_history
    assert len(history) == 2
    assert history[0].method == "GET"
    assert history[0].url.startswith("https://ghcr.io/token")
    assert history[1].method == "GET"
    assert (
        history[1].url
        == f"https://ghcr.io/v2/sekoialab/{module['docker']}/\
manifests/{module['version']}"
    )
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"


@requests_mock.Mocker(kw="m")
def test_registry_check_default_fail(module, **kwargs):
    kwargs["m"].register_uri(
        "GET",
        re.compile("https://ghcr.io/token.*"),
        status_code=200,
        json={"token": API_KEY},
    )
    kwargs["m"].register_uri(
        "GET",
        re.compile("https://ghcr.io/v2/sekoialab.*"),
        status_code=404,
        json={"token": API_KEY},
    )
    assert not SyncLibrary(
        SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER
    ).check_image_on_registry(module["docker"], module["version"])

    history = kwargs["m"].request_history
    assert len(history) == 2
    assert history[0].method == "GET"
    assert history[0].url.startswith("https://ghcr.io/token")
    assert history[1].method == "GET"
    assert (
        history[1].url
        == f"https://ghcr.io/v2/sekoialab/{module['docker']}/\
manifests/{module['version']}"
    )
    assert history[1].headers["Authorization"] == f"Bearer {API_KEY}"


@requests_mock.Mocker(kw="m")
def test_registry_check_custom_success(module, **kwargs):
    custom_path = "foo.bar"
    custom_pathinfo = "v2"
    image_name = module["docker"]
    module["docker"] = f"{custom_path}/{custom_pathinfo}/{image_name}"

    kwargs["m"].register_uri(
        "GET",
        re.compile(f"https://{custom_path}.*"),
        status_code=200,
        json={"token": API_KEY},
    )
    assert SyncLibrary(
        SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER
    ).check_image_on_registry(module["docker"], module["version"])

    history = kwargs["m"].request_history
    assert len(history) == 2
    assert history[0].method == "GET"
    assert history[0].url.startswith(f"https://{custom_path}/token")
    assert history[1].method == "GET"
    assert (
        history[1].url
        == f"https://{custom_path}/{custom_pathinfo}/{image_name}/\
manifests/{module['version']}"
    )


@requests_mock.Mocker(kw="m")
def test_registry_check_auth_failure(module, **kwargs):
    custom_path = "foo.bar"
    custom_pathinfo = "v2"
    image_name = module["docker"]
    module["docker"] = f"{custom_path}/{custom_pathinfo}/{image_name}"

    kwargs["m"].register_uri("GET", f"https://{custom_path}/token", status_code=403)
    with pytest.raises(typer.Exit):
        SyncLibrary(
            SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER
        ).check_image_on_registry(module["docker"], module["version"])

    history = kwargs["m"].request_history
    assert len(history) == 1
    assert history[0].method == "GET"
    assert history[0].url.startswith(f"https://{custom_path}/token")


@requests_mock.Mocker(kw="m")
def test_registry_check_not_found(module, **kwargs):
    custom_path = "foo.bar"
    custom_pathinfo = "v2"
    image_name = module["docker"]
    module["docker"] = f"{custom_path}/{custom_pathinfo}/{image_name}"

    kwargs["m"].register_uri(
        "GET", f"https://{custom_path}/token", status_code=200, json={"token": API_KEY}
    )
    kwargs["m"].register_uri(
        "GET",
        f"https://{custom_path}/v2/sekoia-automation-module-sample/manifests/0.1",
        status_code=404,
    )
    assert (
        SyncLibrary(
            SYMPOHNY_URL, API_KEY, Path("tests/data"), PAT, USER
        ).check_image_on_registry(module["docker"], module["version"])
        is False
    )

    history = kwargs["m"].request_history
    assert len(history) == 2
    assert history[0].method == "GET"
    assert history[0].url.startswith(f"https://{custom_path}/token")


def test_check_image_no_token():
    with pytest.raises(typer.Exit):
        SyncLibrary(
            SYMPOHNY_URL, API_KEY, Path("tests/data"), None, None, registry_check=True
        ).execute()


def test_get_module_logo():
    lib = SyncLibrary(
        SYMPOHNY_URL, API_KEY, Path("tests/data"), None, None, registry_check=True
    )
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
    lib = SyncLibrary(
        SYMPOHNY_URL, API_KEY, Path("tests/data"), None, None, registry_check=True
    )
    with patch(
        "sekoia_automation.scripts.sync_library.SyncLibrary.check_image_on_registry"
    ) as mock:
        mock.return_value = False
        with pytest.raises(typer.Exit):
            lib.load_module(Path("tests/data/sample_module"))
