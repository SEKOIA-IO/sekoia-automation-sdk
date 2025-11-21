import base64
import json


def json_load(value: str):
    try:
        return json.loads(value)
    except ValueError:
        return json.loads(base64.b64decode(value))
