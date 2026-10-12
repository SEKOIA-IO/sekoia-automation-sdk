import json
from pathlib import Path

import pytest

from sekoia_automation.exceptions import AutomationSDKError, EnvironmentRuntimeError
from sekoia_automation.settings import Settings

DEFAULT_STATE_FILE_PATH = Path("/userfunc/state.json")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Make sure the ambient environment does not leak into the tests."""
    monkeypatch.delenv("SYMPHONY_RUNTIME", raising=False)
    monkeypatch.delenv("FISSION_STATE_FILE_PATH", raising=False)


@pytest.fixture
def code_directory(tmp_path: Path) -> Path:
    """Directory standing for the deployed Fission code."""
    directory = tmp_path / "deployed-code"
    directory.mkdir()
    return directory


@pytest.fixture
def state_file(tmp_path: Path, code_directory: Path) -> Path:
    """Valid Fission state file pointing to ``code_directory``."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"filepath": str(code_directory)}))
    return path


@pytest.fixture
def fission_settings(monkeypatch, state_file: Path) -> Settings:
    monkeypatch.setenv("SYMPHONY_RUNTIME", "fission")
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(state_file))
    return Settings()


# ---------------------------------------------------------------------------
# Defaults & native runtime
# ---------------------------------------------------------------------------


def test_default_settings():
    settings = Settings()

    assert settings.symphony_runtime == "native"
    assert settings.fission_state_file_path == DEFAULT_STATE_FILE_PATH
    assert settings.fission_enabled is False


def test_default_base_directory_is_cwd(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

    assert Settings().base_directory == tmp_path


def test_native_runtime_from_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "native")
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.fission_enabled is False
    assert settings.base_directory == tmp_path


def test_state_file_ignored_in_native_runtime(
    monkeypatch, tmp_path: Path, state_file: Path
):
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(state_file))
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.fission_state_file_path == state_file
    assert settings.base_directory == tmp_path


def test_missing_state_file_is_harmless_in_native_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(tmp_path / "missing.json"))
    monkeypatch.chdir(tmp_path)

    assert Settings().base_directory == tmp_path


# ---------------------------------------------------------------------------
# Environment handling
# ---------------------------------------------------------------------------


def test_fission_runtime_from_environment(monkeypatch):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "fission")

    settings = Settings()

    assert settings.symphony_runtime == "fission"
    assert settings.fission_enabled is True
    assert settings.fission_state_file_path == DEFAULT_STATE_FILE_PATH


def test_environment_variable_names_are_case_insensitive(monkeypatch):
    monkeypatch.setenv("symphony_runtime", "fission")

    assert Settings().fission_enabled is True


def test_custom_state_file_path_from_environment(monkeypatch, tmp_path: Path):
    custom = tmp_path / "custom-state.json"
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(custom))

    settings = Settings()

    assert isinstance(settings.fission_state_file_path, Path)
    assert settings.fission_state_file_path == custom


def test_explicit_arguments_override_environment(monkeypatch, state_file: Path):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "native")
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", "/from/environment.json")

    settings = Settings(symphony_runtime="fission", fission_state_file_path=state_file)

    assert settings.fission_enabled is True
    assert settings.fission_state_file_path == state_file


# ---------------------------------------------------------------------------
# Fission runtime: base directory resolution
# ---------------------------------------------------------------------------


def test_fission_base_directory_read_from_state_file(
    fission_settings: Settings, code_directory: Path
):
    assert fission_settings.base_directory == code_directory


def test_fission_base_directory_is_independent_from_cwd(
    monkeypatch, tmp_path: Path, fission_settings: Settings, code_directory: Path
):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert fission_settings.base_directory == code_directory


def test_fission_base_directory_is_not_cached(
    tmp_path: Path, fission_settings: Settings, state_file: Path, code_directory: Path
):
    assert fission_settings.base_directory == code_directory

    other = tmp_path / "other-code"
    other.mkdir()
    state_file.write_text(json.dumps({"filepath": str(other)}))

    assert fission_settings.base_directory == other


def test_fission_state_file_may_contain_extra_keys(
    fission_settings: Settings, state_file: Path, code_directory: Path
):
    state_file.write_text(
        json.dumps(
            {
                "filepath": str(code_directory),
                "functionName": "my-function",
                "url": "http://example.org",
            }
        )
    )

    assert fission_settings.base_directory == code_directory


def test_fission_missing_state_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "fission")
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(tmp_path / "missing.json"))

    with pytest.raises(EnvironmentRuntimeError):
        Settings().base_directory


def test_fission_state_file_is_a_directory(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "fission")
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(tmp_path))

    with pytest.raises(EnvironmentRuntimeError):
        Settings().base_directory


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json at all",
        "{",
        "[]",
        json.dumps("a string"),
        json.dumps({"path": "/somewhere"}),
        json.dumps({"filepath": None}),
        json.dumps({"filepath": 42}),
    ],
    ids=[
        "empty",
        "not-json",
        "truncated-json",
        "list",
        "string",
        "missing-filepath-key",
        "null-filepath",
        "non-string-filepath",
    ],
)
def test_fission_invalid_state_file_content(
    fission_settings: Settings, state_file: Path, content: str
):
    state_file.write_text(content)

    with pytest.raises(EnvironmentRuntimeError):
        fission_settings.base_directory


def test_fission_filepath_does_not_exist(
    tmp_path: Path, fission_settings: Settings, state_file: Path
):
    state_file.write_text(json.dumps({"filepath": str(tmp_path / "does-not-exist")}))

    with pytest.raises(EnvironmentRuntimeError):
        fission_settings.base_directory


def test_fission_filepath_may_be_a_file(
    tmp_path: Path, fission_settings: Settings, state_file: Path
):
    """Only existence is checked, the target does not have to be a directory."""
    target = tmp_path / "some-file"
    target.touch()
    state_file.write_text(json.dumps({"filepath": str(target)}))

    assert fission_settings.base_directory == target


def test_fission_error_message_and_hierarchy(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "fission")
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(tmp_path / "missing.json"))

    with pytest.raises(
        EnvironmentRuntimeError,
        match="Unable to identify the base directory for deployed Fission code",
    ) as excinfo:
        Settings().base_directory

    assert isinstance(excinfo.value, AutomationSDKError)
    assert str(excinfo.value).startswith("EnvironmentRuntimeError: ")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_computed_fields_are_serialized_in_native_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

    dumped = Settings().model_dump()

    assert dumped["symphony_runtime"] == "native"
    assert dumped["fission_state_file_path"] == DEFAULT_STATE_FILE_PATH
    assert dumped["fission_enabled"] is False
    assert dumped["base_directory"] == tmp_path


def test_computed_fields_are_serialized_in_fission_runtime(
    fission_settings: Settings, state_file: Path, code_directory: Path
):
    dumped = fission_settings.model_dump()

    assert dumped["symphony_runtime"] == "fission"
    assert dumped["fission_state_file_path"] == state_file
    assert dumped["fission_enabled"] is True
    assert dumped["base_directory"] == code_directory


def test_model_dump_fails_when_fission_base_directory_cannot_be_resolved(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setenv("SYMPHONY_RUNTIME", "fission")
    monkeypatch.setenv("FISSION_STATE_FILE_PATH", str(tmp_path / "missing.json"))

    with pytest.raises(EnvironmentRuntimeError):
        Settings().model_dump()
