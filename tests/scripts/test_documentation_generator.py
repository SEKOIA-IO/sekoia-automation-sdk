import json
import re
import shutil
from pathlib import Path

import pytest
import typer
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
        "  * [Network](action_library/network/README.md)\n"
        "    * [Stale](action_library/network/stale.md)\n"
        "\n## Other\n\n* [Foo](foo.md)\n"
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
    assert "[Stale](action_library/network/stale.md)" in summary
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
    manifest = modules_path / "Test" / "manifest.json"
    manifest.write_text(manifest.read_text().replace('"d"', '"d", "deprecated": true'))
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


def test_gitbook_legacy_flat_entry_replaced(modules_path, gitbook_path):
    path = gitbook_path / SPACE / "SUMMARY.md"
    path.write_text(
        path.read_text().replace(
            "* [Library](action_library/overview.md)\n",
            "* [Library](action_library/overview.md)\n"
            "  * [Test Module](action_library/test-module.md)\n"
            "  * [Guide](action_library/guide.md)\n",
        )
    )
    generate(modules_path, gitbook_path)
    summary = path.read_text()
    assert "(action_library/test-module.md)" not in summary
    assert "(action_library/network/test-module.md)" in summary
    assert "[Guide](action_library/guide.md)" in summary


def test_gitbook_manual_redirects_kept(modules_path, gitbook_path):
    space = gitbook_path / SPACE
    (space / "action_library/manual").mkdir(parents=True)
    (space / "action_library/manual/guide.md").write_text("# Guide\n")
    (space / ".gitbook.yaml").write_text(
        "redirects:\n"
        "  action_library/guide: action_library/manual/guide.md\n"
        "  action_library/gone: action_library/network/gone.md\n"
    )
    generate(modules_path, gitbook_path)
    redirects = yaml.safe_load((space / ".gitbook.yaml").read_text())["redirects"]
    assert redirects["action_library/guide"] == "action_library/manual/guide.md"
    assert "action_library/gone" not in redirects


def test_gitbook_description_only_in_front_matter(modules_path, gitbook_path):
    generate(modules_path, gitbook_path)
    page = (gitbook_path / SPACE / "action_library/network/test-module.md").read_text()
    assert page.count('description: "d"') == 1
    assert "\n\nd\n\n" not in page and "## Configuration" in page


def test_gitbook_manual_section_kept(modules_path, gitbook_path):
    path = gitbook_path / SPACE / "SUMMARY.md"
    section = (
        "  * [Guides](action_library/guides/README.md)\n"
        "    * [Setup](action_library/guides/setup.md)\n"
    )
    path.write_text(path.read_text().replace("\n## Other", section + "\n## Other"))
    generate(modules_path, gitbook_path)
    assert section in path.read_text()
    generate(modules_path, gitbook_path, module="Test")
    assert section in path.read_text()


def stale_pages(gitbook_path: Path, count: int) -> list[Path]:
    folder = gitbook_path / SPACE / "action_library/network"
    folder.mkdir(parents=True, exist_ok=True)
    pages = [folder / f"old{i}.md" for i in range(count)]
    for page in pages:
        page.write_text("---\nuuid: x\ntype: playbook\n---\n")
    return pages


def test_gitbook_prune(modules_path, gitbook_path):
    stale = stale_pages(gitbook_path, 2)
    manual = gitbook_path / SPACE / "action_library/network/manual.md"
    manual.write_text("# Manual\n")
    readme = gitbook_path / SPACE / "action_library/network/README.md"
    readme.write_text("# Network\n")
    flat = gitbook_path / SPACE / "action_library/flat.md"
    flat.write_text("---\ntype: playbook\n---\n")
    generate(modules_path, gitbook_path)
    assert all(page.exists() for page in stale)  # no flag, no pruning
    generate(modules_path, gitbook_path, prune=True)
    assert not any(page.exists() for page in stale)
    assert manual.exists() and readme.exists() and flat.exists()
    assert (gitbook_path / SPACE / "action_library/network/test-module.md").exists()


def test_gitbook_prune_cap(modules_path, gitbook_path):
    stale = stale_pages(gitbook_path, 6)
    with pytest.raises(typer.Exit):
        generate(modules_path, gitbook_path, prune=True)
    assert all(page.exists() for page in stale)


def test_prune_needs_full_gitbook_run(modules_path, gitbook_path):
    with pytest.raises(typer.Exit):
        generate(modules_path, gitbook_path, module="Test", prune=True)
    with pytest.raises(typer.Exit):
        DocumentationGenerator(modules_path, gitbook_path, prune=True).generate()


def test_gitbook_prune_drops_links_of_emptied_category(modules_path, gitbook_path):
    space = gitbook_path / SPACE
    folder = space / "action_library/other"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# Other\n")
    (folder / "old.md").write_text("---\ntype: playbook\n---\n")
    summary = space / "SUMMARY.md"
    summary.write_text(
        summary.read_text().replace(
            "\n## Other",
            "  * [Other](action_library/other/README.md)\n"
            "    * [Old](action_library/other/old.md)\n\n## Other",
        )
    )
    generate(modules_path, gitbook_path, prune=True)
    text = summary.read_text()
    assert "(action_library/other/old.md)" not in text
    assert "[Other](action_library/other/README.md)" in text


def test_gitbook_manual_page_named_like_a_module_kept(modules_path, gitbook_path):
    space = gitbook_path / SPACE
    (space / "action_library/guides").mkdir(parents=True)
    (space / "action_library/guides/test-module.md").write_text("# Guide\n")
    summary = space / "SUMMARY.md"
    entry = (
        "  * [Guides](action_library/guides/README.md)\n"
        "    * [Test](action_library/guides/test-module.md)\n"
    )
    summary.write_text(summary.read_text().replace("\n## Other", entry + "\n## Other"))
    generate(modules_path, gitbook_path)
    assert entry in summary.read_text()


def test_gitbook_single_module_keeps_category_order(modules_path, gitbook_path):
    for name, category in (("Mail", "Email"), ("Zed", "Zeta")):
        folder = modules_path / name
        shutil.copytree(modules_path / "Test", folder)
        manifest = folder / "manifest.json"
        manifest.write_text(
            manifest.read_text()
            .replace("Test Module", f"{name} Module")
            .replace('"Network"', f'"{category}"')
            .replace("7cf9ccf6-e20a-4e53-bd77-3c19cdc94154", name)
        )
    generate(modules_path, gitbook_path)
    path = gitbook_path / SPACE / "SUMMARY.md"

    def titles() -> list[str]:
        return re.findall(r"^  \* \[(.+?)\]\(.*README", path.read_text(), re.M)

    assert titles() == ["Email", "Network", "Zeta"]
    generate(modules_path, gitbook_path, module="Test")
    assert titles() == ["Email", "Network", "Zeta"]


def test_gitbook_prune_keeps_page_with_playbook_in_body(modules_path, gitbook_path):
    guide = gitbook_path / SPACE / "action_library/network/guide.md"
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text("# Guide\n\n```yaml\ntype: playbook\n```\n")
    generate(modules_path, gitbook_path, prune=True)
    assert guide.exists()


def moved_module(modules_path: Path, gitbook_path: Path) -> Path:
    generate(modules_path, gitbook_path)
    manifest = modules_path / "Test" / "manifest.json"
    manifest.write_text(manifest.read_text().replace("Network", "Cloud"))
    return gitbook_path / SPACE / "action_library/network/test-module.md"


def test_gitbook_prune_deletes_moved_page(modules_path, gitbook_path):
    old = moved_module(modules_path, gitbook_path)
    generate(modules_path, gitbook_path, prune=True)
    assert not old.exists()
    assert (old.parents[1] / "cloud/test-module.md").exists()


def test_gitbook_prune_cap_keeps_moved_page(modules_path, gitbook_path):
    old = moved_module(modules_path, gitbook_path)
    stale_pages(gitbook_path, 5)  # with the moved page, over the cap
    with pytest.raises(typer.Exit):
        generate(modules_path, gitbook_path, prune=True)
    assert old.exists()
