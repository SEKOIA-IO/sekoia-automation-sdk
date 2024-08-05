import json
from collections import defaultdict
from functools import partial
from pathlib import Path

from sekoia_automation.scripts.compliance.validators import ModuleValidator
from sekoia_automation.scripts.compliance.validators.models import CheckError


class CheckCompliance:
    def __init__(self, path: Path) -> None:
        if path.name == "automation-library":
            # launched from a folder with all modules
            self.modules_path = path
            print(f"Looking for modules in {path}...")
            self.all_modules = self.find_modules(self.modules_path)
            self.modules = self.all_modules

        elif path.parent.name == "automation-library":
            # launched from individual module
            print(f"Checking module in {path}")
            self.modules_path = path.parent
            self.all_modules = self.find_modules(self.modules_path)
            self.modules = [path]

        else:
            raise ValueError(
                "Please run script for a module folder or `automation-library` folder"
            )

    def run(self, fix: bool = False) -> None:
        all_validators = []
        selected_validators = []

        errors_to_fix = []
        has_any_errors = False

        print(f"🔎 {len(self.modules)} module(s) found")

        for module in self.all_modules:
            r = self.check_module(module)
            all_validators.append(r)

            # We have to check all the modules, but show results only for the selected ones
            if module in self.modules:
                selected_validators.append(r)

        self.check_uuids_and_slugs(all_validators)
        self.check_docker_params(all_validators)

        for r in selected_validators:
            if r.result.errors:
                for item in r.result.errors:
                    has_any_errors = True
                    if item.fix is not None:
                        errors_to_fix.append(item)

        for res in sorted(selected_validators, key=lambda x: x.path):
            if len(res.result.errors) > 0:
                fmt = self.format_errors(res, ignored_paths=set())
                if fmt:
                    print(fmt)

        if not fix:
            if len(errors_to_fix) > 0:
                print()
                print("🛠 Available automatic fixes (run with `fix` command):")
                for error in errors_to_fix:
                    print(
                        f"FIX {error.filepath.relative_to(self.modules_path)}:{error.fix_label}"
                    )

        else:
            if len(errors_to_fix) == 0:
                print("There is nothing we can fix automatically")
                print()
                print("Fixing...")
                for error in errors_to_fix:
                    print(
                        f"FIX {error.filepath.relative_to(self.modules_path)}:{error.fix_label}"
                    )
                    error.fix()

        if has_any_errors:
            print("❌  Found errors")
            exit(1)

        else:
            print("✅  No errors found!")

    def check_module(self, module_path: str | Path):
        if isinstance(module_path, str):
            module_path = Path(module_path)

        m = ModuleValidator(path=module_path)
        m.validate()

        return m

    def format_errors(self, mod_val: ModuleValidator, ignored_paths: set[Path]) -> str:
        errors = mod_val.result.errors
        module_name = mod_val.path.name
        return "\n".join(
            f"{module_name}:{error.filepath.name}:{error.error}"
            for error in errors
            if error.filepath not in ignored_paths
        )

    def find_modules(self, root_path: Path) -> list[Path]:
        result = []

        for path in root_path.iterdir():
            if (
                path.is_dir()
                and not path.name.startswith("_")
                and not path.name.startswith(".")
                and path.name not in ("docs",)
            ):
                result.append(path)

        return result

    def fix_set_uuid(self, file_path: Path, uuid: str) -> None:
        with open(file_path) as file:
            manifest = json.load(file)

        manifest["uuid"] = uuid

        with open(file_path, "w") as file:
            json.dump(manifest, file, indent=2)

    def check_uniqueness(self, items, error_msg: str):
        for k, v in items.items():
            if len(v) > 1:
                for file_name, val in v:
                    path = val.result.options["path"] / file_name

                    # We don't add fix call (e.g. generating new UUID) here, because it would create
                    # a lot of error-prone corner cases
                    val.result.errors.append(
                        CheckError(
                            filepath=path,
                            error=error_msg,
                        )
                    )

    def check_docker_params(self, validators: list[ModuleValidator]):
        for validator in validators:
            actions_docker_params = defaultdict(list)
            triggers_docker_params = defaultdict(list)
            connectors_docker_params = defaultdict(list)

            module_path = validator.result.options["path"]
            docker_parameters = validator.result.options.get("docker_parameters", {})

            suffix_to_docker = defaultdict(dict)
            for filename, docker in docker_parameters.items():
                if filename.startswith("action_"):
                    actions_docker_params[docker].append((filename, validator))
                    suffix_to_docker[filename.lstrip("action_")]["action"] = docker

                elif filename.startswith("trigger_"):
                    triggers_docker_params[docker].append((filename, validator))
                    suffix_to_docker[filename.lstrip("trigger_")]["trigger"] = docker

                elif filename.startswith("connector_"):
                    connectors_docker_params[docker].append((filename, validator))
                    suffix_to_docker[filename.lstrip("connector_")][
                        "connector"
                    ] = docker

            for suffix, data in suffix_to_docker.items():
                # ignore cases where we have only either `trigger_` or `connector_` files
                if "connector" not in data or "trigger" not in data:
                    continue

                if data["connector"] != data["trigger"]:
                    filename_to_fix = f"connector_{suffix}"
                    filepath = module_path / filename_to_fix
                    validator.result.errors.append(
                        CheckError(
                            filepath=filepath,
                            error=f"`docker_parameters` is not consistent with trigger_{suffix}",
                        )
                    )
                    # We don't want to check these further
                    del triggers_docker_params[data["trigger"]]
                    del connectors_docker_params[data["connector"]]

            self.check_uniqueness(
                actions_docker_params, error_msg="`docker_parameters` is not unique"
            )
            self.check_uniqueness(
                triggers_docker_params, error_msg="`docker_parameters` is not unique"
            )
            self.check_uniqueness(
                connectors_docker_params, error_msg="`docker_parameters` is not unique"
            )

    def check_uuids_and_slugs(self, validators: list[ModuleValidator]):
        manifest_uuids = defaultdict(list)
        manifest_slugs = defaultdict(list)
        actions_uuids = defaultdict(list)
        triggers_uuids = defaultdict(list)
        connectors_uuids = defaultdict(list)

        for validator in validators:
            module_path = validator.result.options["path"]

            module_slug = validator.result.options.get("module_slug")
            if module_slug:
                manifest_slugs[module_slug].append(("manifest.json", validator))

            uuids = validator.result.options.get("uuid_to_check", {})

            suffix_to_uuid = defaultdict(dict)
            for filename, uuid in uuids.items():
                if filename == "manifest.json":
                    manifest_uuids[uuid].append((filename, validator))

                elif filename.startswith("action_"):
                    actions_uuids[uuid].append((filename, validator))

                elif filename.startswith("trigger_"):
                    triggers_uuids[uuid].append((filename, validator))
                    suffix_to_uuid[filename.lstrip("trigger_")]["trigger"] = uuid

                elif filename.startswith("connector_"):
                    connectors_uuids[uuid].append((filename, validator))
                    suffix_to_uuid[filename.lstrip("connector_")]["connector"] = uuid

            for suffix, data in suffix_to_uuid.items():
                # ignore cases where we have only either `trigger_` or `connector_` files
                if "connector" not in data or "trigger" not in data:
                    continue

                if data["connector"] != data["trigger"]:
                    filename_to_fix = f"connector_{suffix}"
                    filepath = module_path / filename_to_fix
                    validator.result.errors.append(
                        CheckError(
                            filepath=filepath,
                            error=f"UUID is not consistent with trigger_{suffix}",
                            fix_label=f"Set the same UUID for trigger_{suffix} and connector_{suffix}",
                            fix=partial(
                                self.fix_set_uuid,
                                file_path=filepath,
                                uuid=data["trigger"],
                            ),
                        )
                    )
                    # We don't want to check these further
                    del triggers_uuids[data["trigger"]]
                    del connectors_uuids[data["connector"]]

        # check UUIDs from each group separately
        self.check_uniqueness(manifest_slugs, error_msg="slug is not unique")
        self.check_uniqueness(manifest_uuids, error_msg="UUID is not unique")
        self.check_uniqueness(actions_uuids, error_msg="UUID is not unique")
        self.check_uniqueness(connectors_uuids, error_msg="UUID is not unique")
        self.check_uniqueness(triggers_uuids, error_msg="UUID is not unique")
