import json
from pathlib import Path

import pytest
import yaml

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
                "categories": ["Network", "Endpoint"],
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
    (path / SPACE / ".gitbook.yaml").write_text(
        "root: ./\nredirects:\n  other: foo.md\n"
        "  action_library/stale: action_library/other/stale.md\n"
    )
    (path / SPACE / "SUMMARY.md").write_text(
        "# Summary\n\n* [Home](README.md)\n"
        "* [Library](action_library/overview.md)\n"
        "  * [Other](action_library/other/README.md)\n"
        "    * [Stale](action_library/other/stale.md)\n\n## Other\n\n* [Foo](foo.md)\n"
    )
    return path


def generate(modules_path: Path, doc_path: Path, **kwargs) -> None:
    DocumentationGenerator(
        modules_path, doc_path, output_format=OutputFormat.gitbook, **kwargs
    ).generate()


def test_gitbook_page(modules_path, gitbook_path):
    generate(modules_path, gitbook_path)
    space = gitbook_path / SPACE
    page = (space / "action_library/network/test-module.md").read_text()
    # uuid and type are read by the redirects sync script of the docs repo
    assert page.startswith(
        f'---\nuuid: {MODULE_UUID}\nname: "Test Module"\ntype: playbook\n'
    )
    assert '<img src="../../.gitbook/assets/library/test-module.svg"' in page
    assert "{ align" not in page
    assert "a\\|b<br/>c" in page
    assert "(../../.gitbook/assets/library/setup/test-module/step.png)" in page
    assert "{:" not in page and "!!!" not in page
    assert '{% hint style="warning" %}\n    Keep it **secret**.' in page
    assert (space / "action_library/network/README.md").read_text() == "# Network\n"
    assert (space / ".gitbook/assets/library/test-module.svg").exists()
    assert (space / ".gitbook/assets/library/setup/test-module/step.png").exists()


def test_gitbook_summary(modules_path, gitbook_path):
    generate(modules_path, gitbook_path)
    path = gitbook_path / SPACE / "SUMMARY.md"
    summary = path.read_text()
    assert summary == (
        "# Summary\n\n* [Home](README.md)\n"
        "* [Library](action_library/overview.md)\n"
        "  * [Network](action_library/network/README.md)\n"
        "    * [Test Module](action_library/network/test-module.md)\n\n## Other\n\n"
        "* [Foo](foo.md)\n"
    )
    generate(modules_path, gitbook_path)
    assert path.read_text() == summary


def test_gitbook_single_module_keeps_others(modules_path, gitbook_path):
    generate(modules_path, gitbook_path, module="Test")
    summary = (gitbook_path / SPACE / "SUMMARY.md").read_text()
    assert "[Stale](action_library/other/stale.md)" in summary
    assert "[Test Module](action_library/network/test-module.md)" in summary


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
            "  * [Network](action_library/network/README.md)\n"
            "    * [Test Module](action_library/network/test-module.md)\n"
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


def test_gitbook_redirects(modules_path, gitbook_path):
    path = gitbook_path / SPACE / ".gitbook.yaml"
    generate(modules_path, gitbook_path)
    conf = yaml.safe_load(path.read_text())
    assert conf == {
        "root": "./",
        "redirects": {
            "other": "foo.md",
            "action_library/test-module": "action_library/network/test-module.md",
        },
    }
    generate(modules_path, gitbook_path)
    assert yaml.safe_load(path.read_text()) == conf


def test_deprecated_module_ignored(modules_path, gitbook_path):
    (modules_path / "Test").rename(modules_path / "Nybble")
    generate(modules_path, gitbook_path)
    assert not (gitbook_path / SPACE / "action_library/network").exists()


def test_gitbook_empty_redirects(modules_path, gitbook_path):
    path = gitbook_path / SPACE / ".gitbook.yaml"
    path.write_text("root: ./\nredirects:\n")
    generate(modules_path, gitbook_path)
    assert "action_library/test-module" in yaml.safe_load(path.read_text())["redirects"]


def test_gitbook_keeps_manual_children(modules_path, gitbook_path):
    path = gitbook_path / SPACE / "SUMMARY.md"
    path.write_text(
        path.read_text().replace(
            "* [Library](action_library/overview.md)\n",
            "* [Library](action_library/overview.md)\n"
            "  * [Guide](action_library/guide.md)\n",
        )
    )
    generate(modules_path, gitbook_path)
    generate(modules_path, gitbook_path, module="Test")
    assert "  * [Guide](action_library/guide.md)\n" in path.read_text()


def test_gitbook_module_changes_category(modules_path, gitbook_path):
    generate(modules_path, gitbook_path)
    manifest = modules_path / "Test" / "manifest.json"
    manifest.write_text(manifest.read_text().replace("Network", "Cloud"))
    generate(modules_path, gitbook_path, module="Test")
    library = gitbook_path / SPACE / "action_library"
    summary = (gitbook_path / SPACE / "SUMMARY.md").read_text()
    assert summary.count("[Test Module]") == 1
    assert "(action_library/cloud/test-module.md)" in summary
    assert not (library / "network/test-module.md").exists()
    conf = yaml.safe_load((gitbook_path / SPACE / ".gitbook.yaml").read_text())
    assert conf["redirects"]["action_library/test-module"].endswith(
        "cloud/test-module.md"
    )


def test_gitbook_title_is_escaped(modules_path, gitbook_path):
    manifest = modules_path / "Test" / "manifest.json"
    manifest.write_text(
        manifest.read_text().replace("Test Module", "Test [x](http://e)")
    )
    generate(modules_path, gitbook_path)
    summary = (gitbook_path / SPACE / "SUMMARY.md").read_text()
    assert r"* [Test \[x\](http://e)](action_library/network/" in summary


def test_gitbook_admonition_title_and_end_of_file(modules_path, tmp_path):
    (modules_path / "Test" / "CONFIGURE.md").write_text(
        '!!! warning "Required"\n    Keep it secret.\n    Really.'
    )
    generator = DocumentationGenerator(
        modules_path, tmp_path, output_format=OutputFormat.gitbook
    )
    setup = generator._copy_configure_md(modules_path / "Test", None)
    assert setup == (
        '{% hint style="warning" %}\n**Required**\n\nKeep it secret.\nReally.\n'
        "{% endhint %}\n\n"
    )
