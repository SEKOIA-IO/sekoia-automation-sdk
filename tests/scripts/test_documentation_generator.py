import json
from pathlib import Path

import pytest

from sekoia_automation.scripts.documentation.generate import (
    DocumentationGenerator,
    OutputFormat,
)

MODULE_UUID = "7cf9ccf6-e20a-4e53-bd77-3c19cdc94154"
SPACE = "docs/integration"

CONFIGURE = """# Setup

1. Click here:

    !!! warning
        Keep it **secret**.

2. Then see ![Step](docs/assets/step.png){: style="max-width:100%"}
"""


@pytest.fixture
def modules_path(tmp_path: Path) -> Path:
    module = tmp_path / "modules" / "Test"
    (module / "docs" / "assets").mkdir(parents=True)
    (module / "docs" / "assets" / "step.png").write_bytes(b"png")
    (module / "logo.svg").write_text("<svg/>")
    (module / "CONFIGURE.md").write_text(CONFIGURE)
    (module / "manifest.json").write_text(
        json.dumps(
            {
                "uuid": MODULE_UUID,
                "name": "Test Module",
                "description": "d",
                "configuration": {},
            }
        )
    )
    (module / "action_a.json").write_text(
        json.dumps(
            {
                "uuid": "a",
                "name": "Do",
                "description": "x",
                "arguments": {
                    "properties": {"arg": {"type": "string", "description": "a|b\nc"}}
                },
            }
        )
    )
    return module.parent


@pytest.fixture
def gitbook_path(tmp_path: Path) -> Path:
    path = tmp_path / "gitbook"
    (path / SPACE).mkdir(parents=True)
    (path / SPACE / "SUMMARY.md").write_text(
        "# Summary\n\n* [Home](README.md)\n"
        "* [Library](action_library/overview.md)\n"
        "  * [Stale](action_library/stale.md)\n\n## Other\n\n* [Foo](foo.md)\n"
    )
    return path


def generate(modules_path: Path, doc_path: Path, **kwargs) -> None:
    DocumentationGenerator(
        modules_path, doc_path, output_format=OutputFormat.gitbook, **kwargs
    ).generate()


def test_gitbook_page(modules_path, gitbook_path):
    generate(modules_path, gitbook_path)
    space = gitbook_path / SPACE
    page = (space / "action_library/test-module.md").read_text()
    # uuid and type are read by the redirects sync script of the docs repo
    assert page.startswith(
        f'---\nuuid: {MODULE_UUID}\nname: "Test Module"\ntype: playbook\n'
    )
    assert '<img src="../.gitbook/assets/library/test-module.svg"' in page
    assert "{ align" not in page
    assert "a\\|b<br/>c" in page
    assert "(../.gitbook/assets/library/setup/test-module/step.png)" in page
    assert "{:" not in page and "!!!" not in page
    assert '{% hint style="warning" %}\n    Keep it **secret**.' in page
    assert (space / ".gitbook/assets/library/test-module.svg").exists()
    assert (space / ".gitbook/assets/library/setup/test-module/step.png").exists()


def test_gitbook_summary(modules_path, gitbook_path):
    generate(modules_path, gitbook_path)
    path = gitbook_path / SPACE / "SUMMARY.md"
    summary = path.read_text()
    assert summary == (
        "# Summary\n\n* [Home](README.md)\n"
        "* [Library](action_library/overview.md)\n"
        "  * [Test Module](action_library/test-module.md)\n\n## Other\n\n"
        "* [Foo](foo.md)\n"
    )
    generate(modules_path, gitbook_path)
    assert path.read_text() == summary


def test_gitbook_single_module_keeps_others(modules_path, gitbook_path):
    generate(modules_path, gitbook_path, module="Test")
    summary = (gitbook_path / SPACE / "SUMMARY.md").read_text()
    assert "[Stale](action_library/stale.md)" in summary
    assert "[Test Module](action_library/test-module.md)" in summary


def test_gitbook_creates_summary_entry(modules_path, tmp_path):
    path = tmp_path / "empty"
    (path / SPACE).mkdir(parents=True)
    (path / SPACE / "SUMMARY.md").write_text("# Summary\n")
    generate(modules_path, path)
    assert (
        (path / SPACE / "SUMMARY.md")
        .read_text()
        .endswith(
            "* [Actions Library](action_library/overview.md)\n"
            "  * [Test Module](action_library/test-module.md)\n"
        )
    )


def test_mkdocs_page_unchanged(modules_path, tmp_path):
    path = tmp_path / "mkdocs"
    path.mkdir()
    (path / "mkdocs.yml").write_text("nav: []\n")
    DocumentationGenerator(modules_path, path).generate()

    page = (path / "_shared_content/automate/library/test-module.md").read_text()
    assert page.startswith(f"uuid: {MODULE_UUID}\nname: Test Module\ntype: playbook\n")
    assert (
        "![Test Module](/assets/playbooks/library/test-module.svg){ align=right" in page
    )
    assert "a|b<br/>c" in page
