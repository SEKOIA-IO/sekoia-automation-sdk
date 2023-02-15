import json
from pathlib import Path

VOLUME_PATH = "/symphony"


def load_config(file_name: str, type_: str = "str", non_exist_ok=False):
    path = Path(f"{VOLUME_PATH}/{file_name}")
    if not path.is_file():
        if non_exist_ok:
            return None

        raise FileNotFoundError(f"{path} does not exists.")

    with path.open("r") as fd:
        if type_ == "json":
            return json.load(fd)
        return fd.read()
