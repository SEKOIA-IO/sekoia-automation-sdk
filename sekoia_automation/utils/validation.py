import copy
from decimal import Decimal
from enum import Enum
from typing import Any, get_args, get_origin

from pydantic import BaseModel


def get_type(annotation: type[Any] | None) -> type | None:
    """
    Get the actual type from an annotation
    """
    # If the annotation is None, return it as is (e.g., for unannotated fields).
    if annotation is None:
        return annotation

    # Get the origin of the annotation (e.g., List, Dict, etc.)
    origin = get_origin(annotation)

    # For simple types (like int, str), we can return the annotation itself.
    if origin is None:
        return annotation

    # For Union types (like Optional[str] which is Union[str, None]),
    # we want to extract the actual type.
    args = get_args(annotation)
    return next((arg for arg in args if arg is not type(None)), annotation)


def coerce_dict_types(model: type[BaseModel], data: dict) -> dict:
    """
    Coerce dictionary values to match model field types.
    This replicates Pydantic V1's lenient type coercion behavior.
    """
    coerced = copy.deepcopy(data)

    for key, val in data.items():
        if key in model.model_fields:
            field_info = model.model_fields[key]
            annotation = field_info.annotation

            # Get the actual type
            actual_type = get_type(annotation)

            match (actual_type, val):
                case (t, v) if t is str and not isinstance(v, str):
                    coerced[key] = validate_str(v)
                case (t, v) if t is bool and not isinstance(v, bool):
                    try:
                        coerced[key] = validate_bool(v)
                    except (ValueError, TypeError):
                        pass
                case (t, v) if t is int and not isinstance(v, int):
                    try:
                        coerced[key] = validate_int(v)
                    except (ValueError, TypeError):
                        pass
                case (t, v) if t is float and not isinstance(v, float):
                    try:
                        coerced[key] = validate_float(v)
                    except (ValueError, TypeError):
                        pass

    return coerced


def validate_str(v: Any) -> str:
    """
    Validate that a value is a string, coercing if necessary.
    This replicates Pydantic V1's lenient type coercion behavior for strings.
    """
    if isinstance(v, str):
        if isinstance(v, Enum):
            return v.value
        else:
            return v
    elif isinstance(v, (float, int, Decimal)):
        return str(v)
    elif isinstance(v, (bytes, bytearray)):
        return v.decode()

    raise TypeError(f"Value {v} is not a valid string")


def validate_int(v: Any) -> int:
    """
    Validate that a value is an integer, coercing if necessary.
    This replicates Pydantic V1's lenient type coercion behavior for integers.
    """
    if isinstance(v, int) and not (v is True or v is False):
        return v
    elif isinstance(v, float) and v.is_integer():
        return int(v)
    elif isinstance(v, (str, bytes, bytearray)) and len(v) < 4_300:
        try:
            return int(v)
        except ValueError:
            pass

    raise TypeError(f"Value {v} is not a valid integer")


def validate_float(v: Any) -> float:
    """
    Validate that a value is a float, coercing if necessary.
    This replicates Pydantic V1's lenient type coercion behavior for floats.
    """
    if isinstance(v, float):
        return v

    try:
        return float(v)
    except ValueError:
        pass

    raise TypeError(f"Value {v} is not a valid float")


def validate_bool(v: Any) -> bool:
    """
    Validate that a value is a boolean, coercing if necessary.
    This replicates Pydantic V1's lenient type coercion behavior for booleans.
    """
    if v is True or v is False:
        return v

    if isinstance(v, bytes):
        v = v.decode()

    if isinstance(v, str):
        val = v.lower()
        if val in {"true", "1", "yes", "on"}:
            return True
        elif val in {"false", "0", "no", "off"}:
            return False

    raise TypeError(f"Value {v} is not a valid boolean")
