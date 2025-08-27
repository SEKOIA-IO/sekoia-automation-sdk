import copy
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile

import typer
import yaml
from jinja2 import Environment, FileSystemLoader
from rich import print
from slugify import slugify


@dataclass
class DocumentationModule:
    name: str
    file_name: str
    categories: list[str]


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
        self, modules_path: Path, documentation_path: Path, module: str | None = None
    ):
        self.modules_path = modules_path
        self.documentation_path = documentation_path
        self.module = module

    def generate_module_doc(self, module_path: Path) -> DocumentationModule | None:
        """
        Generate documentation for the given module
        """
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
            logo_filename=module_logo_filename,
            setup=setup,
        )

        module_doc_filename = f'{slugify(module_manifest["name"])}.md'

        module_doc_path = (
            self.documentation_path
            / "_shared_content/automate/library/"
            / module_doc_filename
        )

        # write the module documentation file
        with module_doc_path.open("wb") as fd:
            fd.write(output.encode("utf-8"))

        return DocumentationModule(
            name=module_manifest["name"],
            file_name=module_doc_filename,
            categories=module_manifest.get("categories", []),
        )

    def _copy_logo(self, module_path: Path, module_manifest: dict) -> str | None:
        for ext in ["png", "svg"]:
            module_logo_path = module_path / f"logo.{ext}"
            if module_logo_path.exists():
                module_logo_filename = f'{slugify(module_manifest["name"])}.{ext}'
                copyfile(
                    module_logo_path,
                    (
                        self.documentation_path
                        / "docs/assets/playbooks/library"
                        / module_logo_filename
                    ),
                )
                return module_logo_filename
        return None

    def _copy_assets(self, module_path: Path, module_manifest: dict) -> str | None:
        """
        Copy the assets from the module directory to the documentation directory.
        Return the new location of the assets
        """
        assets_dir = "docs/assets"
        assets_path = module_path / assets_dir

        if assets_path.exists():
            new_location = (
                f"assets/playbooks/library/setup/{slugify(module_manifest['name'])}"
            )
            new_location_path = self.documentation_path / "docs" / new_location
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
            content = content.replace(assets_dir, f"/{assets_location}")

        return content

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

        self._update_documentation_menu(generated_modules)

    def _validate_dirs(self):
        if not self.modules_path.is_dir():
            print("[bold red][!] Module path doesn't exist.[/bold red]")
            raise typer.Exit(code=1)
        if (
            not self.documentation_path.is_dir()
            or not (self.documentation_path / "mkdocs.yml").exists()
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
