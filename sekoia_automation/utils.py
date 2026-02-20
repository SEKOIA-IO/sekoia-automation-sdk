from collections.abc import Sequence
from functools import wraps
from inspect import get_annotations, getmro
from typing import get_args, get_origin

import sentry_sdk
from pydantic import BaseModel
from tenacity import RetryCallState


def get_as_model(model: type[BaseModel] | None, value: dict | BaseModel | None):
    if model is None or value is None:
        return value

    if isinstance(value, model):
        return value

    # Pydantic V2's model_validate is stricter than
    # Pydantic V1's parse_obj about type coercion.
    # To maintain backward compatibility, we need to
    # coerce basic types (like int to str) before validation.
    if isinstance(value, dict):
        value = _coerce_dict_types(model, value)

    return model.model_validate(value)


def _coerce_dict_types(model: type[BaseModel], data: dict) -> dict:
    """
    Coerce dictionary values to match model field types.
    This replicates Pydantic V1's lenient type coercion behavior.
    """
    coerced = {}
    for key, val in data.items():
        if key in model.model_fields:
            field_info = model.model_fields[key]
            annotation = field_info.annotation

            # Get the actual type
            origin = get_origin(annotation)
            if origin is not None:
                # Get and find the first non-None type for coercion
                args = get_args(annotation)
                actual_type = next((arg for arg in args if arg is not type(None)), None)
            else:
                actual_type = annotation

            # Perform basic type coercion
            if actual_type is not None and val is not None:
                if actual_type is str and not isinstance(val, str):
                    coerced[key] = str(val)
                elif actual_type is int and not isinstance(val, int):
                    try:
                        coerced[key] = int(val)
                    except (ValueError, TypeError):
                        coerced[key] = val
                elif actual_type is float and not isinstance(val, float):
                    try:
                        coerced[key] = float(val)
                    except (ValueError, TypeError):
                        coerced[key] = val
                elif actual_type is bool and not isinstance(val, bool):
                    # Be careful with bool coercion - don't convert strings/numbers
                    coerced[key] = val
                else:
                    coerced[key] = val
            else:
                coerced[key] = val
        else:
            coerced[key] = val

    return coerced


def validate_with_model(model: type[BaseModel] | None, value: dict | BaseModel | None):
    if model is None or value is None:
        return value

    return get_as_model(model, value).model_dump()


def returns(model: type[BaseModel]):
    def decorator(func):
        @wraps(func)
        def serialize_return_value(*args, **kwargs):
            raw_results = func(*args, **kwargs)

            return validate_with_model(model, raw_results)

        return serialize_return_value

    return decorator


def validate_arguments():
    """
    Decorator that validates function arguments with Pydantic V2,
    but with type coercion for backward compatibility with V1.

    This wraps Pydantic's validate_call but preprocesses
    dict arguments to coerce types before validation.
    """
    from inspect import signature

    from pydantic import validate_call

    def decorator(func):
        # Get the function signature to find BaseModel arguments
        sig = signature(func)
        basemodel_params = {}
        for param_name, param in sig.parameters.items():
            if param.annotation != param.empty:
                try:
                    if isinstance(param.annotation, type) and issubclass(
                        param.annotation, BaseModel
                    ):
                        basemodel_params[param_name] = param.annotation
                except TypeError:
                    # annotation might not be a class
                    pass

        # Apply pydantic's validate_call
        validated_func = validate_call(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Coerce dict arguments to BaseModel types before calling validated function
            coerced_kwargs = {}
            for param_name, value in kwargs.items():
                if param_name in basemodel_params and isinstance(value, dict):
                    model = basemodel_params[param_name]
                    coerced_kwargs[param_name] = _coerce_dict_types(model, value)
                else:
                    coerced_kwargs[param_name] = value

            # Also handle positional arguments
            coerced_args = []
            param_names = list(sig.parameters.keys())
            for i, arg in enumerate(args):
                if i < len(param_names):
                    param_name = param_names[i]
                    if param_name in basemodel_params and isinstance(arg, dict):
                        model = basemodel_params[param_name]
                        coerced_args.append(_coerce_dict_types(model, arg))
                    else:
                        coerced_args.append(arg)
                else:
                    coerced_args.append(arg)

            return validated_func(*coerced_args, **coerced_kwargs)

        return wrapper

    return decorator


def get_annotation_for(cls: type, attribute: str) -> type[BaseModel] | None:
    for base in getmro(cls):
        annotations = get_annotations(base)

        if attribute in annotations:
            return annotations[attribute]

    return None


def capture_retry_error(retry_state: RetryCallState):
    if retry_state.outcome:
        sentry_sdk.capture_exception(retry_state.outcome.result())


def chunks(iterable: Sequence, chunk_size: int):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i : i + chunk_size]
