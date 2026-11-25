import subprocess
import sys

# jinja2 is in the `cli` extra too, but flask (a core dependency) needs it
CLI_ONLY_PACKAGES = [
    "typer",
    "cookiecutter",
    "slugify",
    "yaml",
    "black",
    "rich",
]

RUNTIME_MODULES = [
    "sekoia_automation",
    "sekoia_automation.module",
    "sekoia_automation.action",
    "sekoia_automation.trigger",
    "sekoia_automation.connector",
    "sekoia_automation.aio.connector",
    "sekoia_automation.asset_connector",
    "sekoia_automation.configuration.fission",
    "sekoia_automation.checkpoint",
    "sekoia_automation.storage",
]


def _run_without_cli_packages(code: str) -> subprocess.CompletedProcess:
    # Setting a module to None in sys.modules makes importing it raise ImportError
    block = "".join(f"sys.modules[{name!r}] = None\n" for name in CLI_ONLY_PACKAGES)
    return subprocess.run(
        [sys.executable, "-c", f"import sys\n{block}{code}"],
        capture_output=True,
        text=True,
    )


def test_runtime_does_not_need_cli_extra():
    imports = "".join(f"import {module}\n" for module in RUNTIME_MODULES)
    result = _run_without_cli_packages(imports)
    assert result.returncode == 0, result.stderr


def test_cli_without_extra_shows_install_hint():
    result = _run_without_cli_packages("import sekoia_automation.cli")
    assert result.returncode == 1
    assert "sekoia-automation-sdk[cli]" in result.stderr
    assert "Traceback" not in result.stderr
