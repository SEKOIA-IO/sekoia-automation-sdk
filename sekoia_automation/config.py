import base64
import json
import os
from pathlib import Path

VOLUME_PATH = "/symphony"
TLS_VOLUME_PATH = "/tmp/tls"


def _json_load(value: str):
    try:
        return json.loads(value)
    except ValueError:
        return json.loads(base64.b64decode(value))


def load_config(name: str, type_: str = "str", non_exist_ok=False):
    path = Path(f"{VOLUME_PATH}/{name}")
    if path.is_file():
        with path.open("r") as fd:
            if type_ == "json":
                return json.load(fd)
            return fd.read()

    if value := os.environ.get(name.upper()):
        return _json_load(value) if type_ == "json" else value
    if non_exist_ok:
        return None
    raise FileNotFoundError(f"{path} does not exists.")
