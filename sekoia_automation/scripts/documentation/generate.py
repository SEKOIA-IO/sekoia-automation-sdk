import copy
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from shutil import copyfile

import typer
import yaml
from jinja2 import Environment, FileSystemLoader
from rich import print
from slugify import slugify

SPACE_DIR = "docs/integration"  # GitBook space holding the library
LIBRARY_DIR = "action_library"
LIBRARY_OVERVIEW = f"{LIBRARY_DIR}/overview.md"
DEFAULT_CATEGORY = "Other"
# shortcut: hardcoded, the manifests have no deprecation flag, upgrade if they get one
DEPRECATED_MODULES = {"BinaryEdges", "Nybble", "RiskIQ"}
DEFAULT_CATEGORY = "Other"
ADMONITION = re.compile(
    r'^([ \t]*)!!! (\w+)(?: "[^"]*")?\n((?:\1    .*\n|[ \t]*\n)+)', re.M
)
HINT_STYLES = {"warning": "warning", "danger": "danger", "success": "success"}
SUMMARY_CHILD = re.compile(r"^\s+\* \[(.+)\]\((.+)\)\s*$")


class OutputFormat(StrEnum):
    mkdocs = "mkdocs"
    gitbook = "gitbook"


@dataclass
class DocumentationModule:
    name: str
    file_name: str
    categories: list[str]

    @property
    def category(self) -> str:
        # GitBook pages have a single place: the first category
        return self.categories[0] if self.categories else DEFAULT_CATEGORY

    @property
    def category_dir(self) -> str:
        return slugify(self.category, separator="_")


class DocumentationGenerator:
    @property
    def modules_paths(self):
        """
        Returns the paths of the modules that needs to be processed
        """
        if self.module:
            return [self.modules_path / self.module]
        return sorted(
            path
            for path in self.modules_path.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )

    def __init__(
        self,
        modules_path: Path,
        documentation_path: Path,
        module: str | None = None,
        output_format: OutputFormat = OutputFormat.mkdocs,
    ):
        self.modules_path = modules_path
        self.documentation_path = documentation_path
        self.module = module
        self.gitbook = output_format == OutputFormat.gitbook
        # pages dir, assets dir (both relative to documentation_path),
        # and the assets url as seen from a page
        if self.gitbook:
            self.pages_dir = f"{SPACE_DIR}/{LIBRARY_DIR}"
            self.assets_dir = f"{SPACE_DIR}/.gitbook/assets/library"
            self.assets_url = "../../.gitbook/assets/library"
        else:
            self.pages_dir = "_shared_content/automate/library"
            self.assets_dir = "docs/assets/playbooks/library"
            self.assets_url = "/assets/playbooks/library"

    def generate_module_doc(self, module_path: Path) -> DocumentationModule | None:
        """
        Generate documentation for the given module
        """
        if module_path.name in DEPRECATED_MODULES:
            print(f"[white][!] {module_path.name}: Deprecated, ignored[/white]")
            return None

        if not (module_path / "manifest.json").exists():
            print(f"[orange3][!] {module_path.name}: No manifest found[/orange3]")
            return None

        with (module_path / "manifest.json").open("rb") as fd:
            module_manifest = json.load(fd)

        # Load connectors uuids
        connector_uuids = set()
        for connector_file in sorted(module_path.glob("connector_*.json")):
            with connector_file.open("rb") as fd:
                connector_uuids.add(json.load(fd)["uuid"])

        # Load actions
        module_actions = []
        for action_file in sorted(module_path.glob("action_*.json")):
            with action_file.open("rb") as fd:
                module_actions.append(json.load(fd))

        # Load triggers
        module_triggers = []
        for trigger_file in sorted(module_path.glob("trigger_*.json")):
            with trigger_file.open("rb") as fd:
                loaded = json.load(fd)
                if loaded["uuid"] in connector_uuids:
                    print(
                        f"[white][!] {module_path.name}: Trigger {loaded['name']}"
                        " ignored because it is a connector[/white]"
                    )
                else:
                    module_triggers.append(loaded)

        if not module_actions and not module_triggers:
            print(
                f"[orange3][!] {module_path.name}: No actions/triggers found[/orange3]"
            )
            return None

        # Copy the logo
        module_logo_filename = self._copy_logo(module_path, module_manifest)

        # Copy the assets
        assets_location = self._copy_assets(module_path, module_manifest)

        # Copy content of CONFIGURE.md
        setup = self._copy_configure_md(module_path, assets_location)

        current_dir = Path(os.path.dirname(__file__)).resolve()
        file_loader = FileSystemLoader(current_dir / "templates")
        env = Environment(loader=file_loader)

        template = env.get_template("module.md")
        output = template.render(
            manifest=module_manifest,
            actions=module_actions,
            triggers=module_triggers,
            logo_url=module_logo_filename
            and f"{self.assets_url}/{module_logo_filename}",
            setup=setup,
            gitbook=self.gitbook,
        )

        doc = DocumentationModule(
            name=module_manifest["name"],
            file_name=f"{slugify(module_manifest['name'])}.md",
            categories=module_manifest.get("categories", []),
        )
        pages_dir = self.documentation_path / self.pages_dir
        if self.gitbook:
            pages_dir /= doc.category_dir
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / doc.file_name).write_bytes(output.encode("utf-8"))

        category_page = pages_dir / "README.md"
        if self.gitbook and not category_page.exists():  # keep manual edits
            category_page.write_text(f"# {doc.category}\n")

        return doc

    def _copy_logo(self, module_path: Path, module_manifest: dict) -> str | None:
        for ext in ["png", "svg"]:
            module_logo_path = module_path / f"logo.{ext}"
            if module_logo_path.exists():
                module_logo_filename = f"{slugify(module_manifest['name'])}.{ext}"
                logo_dir = self.documentation_path / self.assets_dir
                logo_dir.mkdir(parents=True, exist_ok=True)
                copyfile(module_logo_path, logo_dir / module_logo_filename)
                return module_logo_filename
        return None

    def _copy_assets(self, module_path: Path, module_manifest: dict) -> str | None:
        """
        Copy the assets from the module directory to the documentation directory.
        Return the new url of the assets, as seen from a page
        """
        assets_dir = "docs/assets"
        assets_path = module_path / assets_dir

        if assets_path.exists():
            setup_dir = f"setup/{slugify(module_manifest['name'])}"
            new_location = f"{self.assets_url}/{setup_dir}"
            new_location_path = self.documentation_path / self.assets_dir / setup_dir
            new_location_path.mkdir(parents=True, exist_ok=True)

            for item in assets_path.iterdir():
                copyfile(item, new_location_path / item.name)

            return new_location

        return None

    def _copy_configure_md(
        self, module_path: Path, assets_location: str | None
    ) -> str | None:
        """
        Copy and return the CONFIGURE.md content

        Read the content of CONFIGURE.md in the automation module directory.
        """
        # Is the SETUP.md exists
        if not (module_path / "CONFIGURE.md").exists():
            return None

        # Read it content
        with (module_path / "CONFIGURE.md").open("r") as fd:
            content = fd.read()

        if assets_location:
            assets_dir = "docs/assets"
            content = content.replace(assets_dir, assets_location)

        if self.gitbook:
            # mkdocs-only syntax: attribute lists and admonitions
            content = re.sub(r"\{:[^}]*\}", "", content)
            content = ADMONITION.sub(self._admonition_to_hint, content)

        return content

    @staticmethod
    def _admonition_to_hint(match: re.Match) -> str:
        indent, kind, body = match.groups()
        style = HINT_STYLES.get(kind, "info")
        lines = (line[len(indent) + 4 :] for line in body.rstrip().splitlines())
        inner = "\n".join(f"{indent}{line}" for line in lines)
        return (
            f'{indent}{{% hint style="{style}" %}}\n{inner}\n'
            f"{indent}{{% endhint %}}\n\n"
        )

    def _update_submenu(
        self, menu: list[dict], target: str, value: list, append_only: bool = False
    ):
        root_target, *target_lst = target.split("/")
        for item in menu:
            if root_target in item:
                if target_lst == []:
                    if append_only:
                        item.setdefault(root_target, [])
                        # Sort by the name of the key in the dict
                        for category_dict in value:
                            category = next(iter(category_dict))
                            for root_categories_dict in item[root_target]:
                                root_category = next(iter(root_categories_dict))
                                if root_category == category:
                                    root_categories_dict[root_category] = sorted(
                                        root_categories_dict[root_category]
                                        + category_dict[category],
                                        key=lambda x: next(iter(x)),
                                    )
                                    break
                            else:
                                item[root_target].append(category_dict)

                        item[root_target] = sorted(
                            item[root_target], key=lambda x: next(iter(x))
                        )
                    else:
                        item[root_target] = value

                self._update_submenu(
                    item[root_target], "/".join(target_lst), value, append_only
                )

    def generate(self) -> None:
        self._validate_dirs()

        print("Generating documentation for modules:")
        generated_modules: list[DocumentationModule] = []
        for module_path in self.modules_paths:
            doc = self.generate_module_doc(module_path=module_path)
            if doc:
                generated_modules.append(doc)
                print(f"[green][+][/green] {module_path.name}: Success")

        if self.gitbook:
            self._update_summary(generated_modules)
            self._update_redirects(generated_modules)
        else:
            self._update_documentation_menu(generated_modules)

    def _validate_dirs(self):
        if not self.modules_path.is_dir():
            print("[bold red][!] Module path doesn't exist.[/bold red]")
            raise typer.Exit(code=1)
        marker_files = (f"{SPACE_DIR}/SUMMARY.md",) if self.gitbook else ("mkdocs.yml",)
        if not self.documentation_path.is_dir() or not any(
            (self.documentation_path / name).exists() for name in marker_files
        ):
            print("[bold red][!] Documentation path is not valid.[/bold red]")
            raise typer.Exit(code=1)
        if self.module and not (self.modules_path / self.module).is_dir():
            print("[bold red][!] Module doesn't exist.[/bold red]")
            raise typer.Exit(code=1)

    def _update_documentation_menu(self, modules: list[DocumentationModule]):
        print("Updating documentation menus:")
        with (self.documentation_path / "mkdocs.yml").open("r+") as fd:
            mkdocs_conf = yaml.safe_load(fd)

            root_menu_items = {
                "Sekoia.io TIP/Features/"
                "Automate/Actions Library": "tip/features/automate/library",
                "Integrations/List of Playbooks Actions": "integration/action_library",
            }
            append_only = True if self.module else False
            for root, directory in root_menu_items.items():
                categories_mapping = defaultdict(list)
                for module in modules:
                    for category in module.categories:
                        categories_mapping[category].append(
                            {module.name: f"{directory}/{module.file_name}"}
                        )

                sub_content: list[dict[str, str | list]] = []
                for category, pages in sorted(
                    categories_mapping.items(), key=lambda item: item[0]
                ):
                    sub_content.append(
                        {category: sorted(pages, key=lambda x: next(iter(x)))}
                    )
                if not append_only:
                    sub_content = [
                        {"Overview": f"{directory}/overview.md"},
                        *sub_content,
                    ]

                self._update_submenu(
                    mkdocs_conf["nav"],
                    root,
                    copy.deepcopy(sub_content),
                    append_only=append_only,
                )
                print(f"[green][+][/green] {root} updated")

            fd.seek(0)
            fd.write(yaml.dump(mkdocs_conf))
            fd.truncate()

    def _update_summary(self, modules: list[DocumentationModule]):
        """
        Replace the children of the library entry in SUMMARY.md, leaving the rest
        of the file (edited by hand or by GitBook) untouched.
        shortcut: modules are listed under their first category, deeper nested
        lines are dropped, upgrade if needed.
        """
        print("Updating SUMMARY.md:")
        path = self.documentation_path / SPACE_DIR / "SUMMARY.md"
        lines = path.read_text().splitlines() if path.exists() else ["# Summary", ""]
        # anchor on the link, GitBook may rewrite the title
        entry = next(
            (
                i
                for i, line in enumerate(lines)
                if line.startswith("* [") and line.endswith(f"]({LIBRARY_OVERVIEW})")
            ),
            None,
        )
        if entry is None:
            lines.append(f"* [Actions Library]({LIBRARY_OVERVIEW})")
            entry = len(lines) - 1
        start = entry + 1
        end = start
        while end < len(lines) and lines[end].startswith(" "):
            end += 1

        categories: dict[str, str] = {}  # category page -> title
        pages: dict[str, str] = {}  # module page -> title
        if self.module:  # single module: keep the others
            for line in lines[start:end]:
                if match := SUMMARY_CHILD.match(line):
                    title, link = match[1], match[2]
                    (categories if link.endswith("/README.md") else pages)[link] = title
        for module in modules:
            folder = f"{LIBRARY_DIR}/{module.category_dir}"
            categories[f"{folder}/README.md"] = module.category
            pages[f"{folder}/{module.file_name}"] = module.name

        block = []
        for link, title in sorted(categories.items(), key=lambda e: e[1]):
            block.append(f"  * [{title}]({link})")
            folder = link.removesuffix("README.md")
            block += [
                f"    * [{name}]({page})"
                for page, name in sorted(pages.items(), key=lambda e: e[1])
                if page.startswith(folder)
            ]
        lines[start:end] = block
        path.write_text("\n".join(lines) + "\n")
        print("[green][+][/green] SUMMARY.md updated")

    def _update_redirects(self, modules: list[DocumentationModule]):
        """
        Redirect the former flat url of each page to its category page, in the
        redirects of the space .gitbook.yaml. Other keys and redirects are kept.
        shortcut: the file is re-dumped, so its comments are lost.
        """
        path = self.documentation_path / SPACE_DIR / ".gitbook.yaml"
        conf = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
        redirects = conf.setdefault("redirects", {})

        def flat_source(target: str) -> str | None:
            parts = Path(target).parts
            if len(parts) == 3 and parts[0] == LIBRARY_DIR:
                return f"{LIBRARY_DIR}/{Path(parts[2]).stem}"
            return None

        if not self.module:  # full run: drop the redirects of removed modules
            for source, target in list(redirects.items()):
                if source == flat_source(target):
                    del redirects[source]
        for module in modules:
            target = f"{LIBRARY_DIR}/{module.category_dir}/{module.file_name}"
            redirects[flat_source(target)] = target

        path.write_text(yaml.dump(conf, sort_keys=False))
        print("[green][+][/green] .gitbook.yaml redirects updated")
