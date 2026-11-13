import json
import re
from pathlib import Path
from shutil import copytree
from tempfile import mkdtemp
from unittest.mock import patch

import pytest
import requests_mock
import typer
import yaml

from sekoia_automation.scripts.sync_library import SyncLibrary, module_files

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
def fetched_connector():
    with open("tests/data/sample_module/fetched_connector_test.json") as f:
        fetched_connector = json.load(f)
        return fetched_connector


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


def test_sync_list_already_updated(requests_mock, module, connector, capsys):
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"))

    requests_mock.get(
        f"{SYMPOHNY_URL}/connectors/667f7e89-d907-4086-a578-a2324c9a277a",
        status_code=200,
        json=connector,
    )

    module_uuid = module.get("uuid")
    module_name = module.get("name")
    sync_lib.sync_list(module_name, module_uuid, [connector], "connector")

    captured = capsys.readouterr()
    assert "Already Up-To-Date" in captured.out


def test_sync_list_not_updated(
    requests_mock, module, fetched_connector, connector, capsys
):
    sync_lib = SyncLibrary(SYMPOHNY_URL, API_KEY, Path("tests/data"))

    requests_mock.get(
        f"{SYMPOHNY_URL}/connectors/667f7e89-d907-4086-a578-a2324c9a277a",
        status_code=200,
        json=fetched_connector,
    )
    requests_mock.patch(
        f"{SYMPOHNY_URL}/connectors/667f7e89-d907-4086-a578-a2324c9a277a",
        status_code=200,
        json=connector,
    )

    module_uuid = module.get("uuid")
    module_name = module.get("name")
    sync_lib.sync_list(module_name, module_uuid, [connector], "connector")

    captured = capsys.readouterr()
    assert "Updated" in captured.out
    assert requests_mock.request_history[-1].json() == connector
    assert requests_mock.request_history[-1].method == "PATCH"
    assert requests_mock.request_history[-1].json().get("type") == "asset"
    assert requests_mock.request_history[-1].json().get("slug") == "slug-connector-test"


HWL_ACTION = """
name: Get track
uuid: 4c5b9d1e-9a3c-4d0e-8f43-3c1b2a7e9f10
description: Get a track
inputs:
  slug: {type: string}
  base_url: {type: string, default: "https://api.test"}
  token: {type: string, secret: true}
  kind: {type: string, const: track}
outputs:
  result: {type: object}
pipeline: [{name: output}]
stages:
  output: {kind: output, properties: {result: "{{inputs.slug}}"}}
"""


@pytest.fixture
def hwl_module(tmp_path, module):
    """A module made of HWL actions only"""
    module_path = tmp_path / "hwl_module"
    module_path.mkdir()
    (module_path / "manifest.json").write_text(json.dumps(module))
    (module_path / "action_get_track.yml").write_text(HWL_ACTION)
    return module_path


def test_hwl_action_to_payload():
    payload = module_files.hwl_action_to_payload(
        yaml.safe_load(HWL_ACTION), "action_get_track.yml", "image:1.0"
    )

    assert payload == {
        "uuid": "4c5b9d1e-9a3c-4d0e-8f43-3c1b2a7e9f10",
        "name": "Get track",
        "description": "Get a track",
        "docker": "image:1.0",
        "docker_parameters": "action_get_track.yml",
        "arguments": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "base_url": {"type": "string", "default": "https://api.test"},
                "token": {"type": "string"},
                "kind": {"type": "string", "const": "track"},
            },
            "required": ["slug", "token"],
            "secrets": ["token"],
        },
        "results": {"type": "object", "properties": {"result": {"type": "object"}}},
    }


@pytest.mark.parametrize("missing", ["name", "uuid"])
def test_hwl_action_to_payload_missing_field(missing):
    workflow = yaml.safe_load(HWL_ACTION)
    del workflow[missing]

    with pytest.raises(typer.Exit):
        module_files.hwl_action_to_payload(workflow, "action_get_track.yml", "image")


def test_load_hwl_module(hwl_module, module, requests_mock):
    version = module["version"]
    requests_mock.get(f"{SYMPOHNY_URL}/modules/{module['uuid']}", status_code=404)
    requests_mock.post(f"{SYMPOHNY_URL}/modules")
    action_uuid = "4c5b9d1e-9a3c-4d0e-8f43-3c1b2a7e9f10"
    requests_mock.get(f"{SYMPOHNY_URL}/actions/{action_uuid}", status_code=404)
    post_action = requests_mock.post(f"{SYMPOHNY_URL}/actions")

    lib = SyncLibrary(SYMPOHNY_URL, API_KEY, hwl_module.parent)
    lib.load_module(hwl_module)

    docker_name = lib._get_module_docker_name(module)
    action = post_action.last_request.json()
    assert action["docker"] == f"{docker_name}-hwl:{version}"
    assert action["docker_parameters"] == "action_get_track.yml"
    assert action["module_uuid"] == module["uuid"]


def test_registry_check_hwl_only_module(hwl_module, module, requests_mock):
    """Only the HWL image is checked, the module image is not built"""
    lib = SyncLibrary(
        SYMPOHNY_URL, API_KEY, hwl_module.parent, registry_check=True, registry_pat=PAT
    )
    docker_name = lib._get_module_docker_name(module)
    hwl_check = requests_mock.get(
        f"https://ghcr.io/v2/sekoia-io/{docker_name.split('/')[-1]}-hwl"
        f"/manifests/{module['version']}",
        status_code=404,
    )

    with pytest.raises(typer.Exit):
        lib.load_module(hwl_module)

    assert hwl_check.call_count == 1


def test_registry_check_mixed_module(tmp_module, module, requests_mock):
    """Both images are checked when the module has both kinds of actions"""
    module_path = tmp_module / "sample_module"
    (module_path / "action_get_track.yml").write_text(HWL_ACTION)
    lib = SyncLibrary(
        SYMPOHNY_URL, API_KEY, tmp_module, registry_check=True, registry_pat=PAT
    )

    with patch.object(
        SyncLibrary, "check_image_on_registry", return_value=False
    ) as check:
        with pytest.raises(typer.Exit):
            lib.load_module(module_path)
        # The module image is checked first, and is the one failing
        assert check.call_count == 1

    with patch.object(SyncLibrary, "check_image_on_registry") as check:
        check.side_effect = [True, False]
        with pytest.raises(typer.Exit):
            lib.load_module(module_path)
        assert [c.args[0] for c in check.call_args_list] == [
            lib._get_module_docker_name(module),
            lib._get_module_docker_name(module, hwl=True),
        ]


def test_load_hwl_actions_invalid(tmp_path):
    (tmp_path / "action_bad.yml").write_text("name: [unclosed")
    with pytest.raises(typer.Exit):
        module_files.load_hwl_actions(tmp_path, "image")

    workflow = yaml.safe_load(HWL_ACTION)
    workflow["inputs"]["slug"] = None
    with pytest.raises(typer.Exit):
        module_files.hwl_action_to_payload(workflow, "action_bad.yml", "image")


def test_hwl_action_to_payload_skips_module_properties():
    payload = module_files.hwl_action_to_payload(
        yaml.safe_load(HWL_ACTION),
        "action_get_track.yml",
        "image:1.0",
        module_properties={"token", "base_url"},
    )

    arguments = payload["arguments"]
    assert set(arguments["properties"]) == {"slug", "kind"}
    assert arguments["required"] == ["slug"]
    assert "secrets" not in arguments


def test_load_hwl_module_skips_manifest_properties(hwl_module, module, requests_mock):
    manifest = {**module, "configuration": {"properties": {"token": {}}}}
    (hwl_module / "manifest.json").write_text(json.dumps(manifest))
    requests_mock.get(f"{SYMPOHNY_URL}/modules/{module['uuid']}", status_code=404)
    requests_mock.post(f"{SYMPOHNY_URL}/modules")
    action_uuid = "4c5b9d1e-9a3c-4d0e-8f43-3c1b2a7e9f10"
    requests_mock.get(f"{SYMPOHNY_URL}/actions/{action_uuid}", status_code=404)
    post_action = requests_mock.post(f"{SYMPOHNY_URL}/actions")

    SyncLibrary(SYMPOHNY_URL, API_KEY, hwl_module.parent).load_module(hwl_module)

    arguments = post_action.last_request.json()["arguments"]
    assert "token" not in arguments["properties"]
    assert "secrets" not in arguments
