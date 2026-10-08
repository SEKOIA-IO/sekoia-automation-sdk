from collections.abc import Sequence
from functools import wraps
from inspect import get_annotations, getmro
from typing import Any, Generic, TypeVar, get_args, get_origin

import sentry_sdk
from pydantic import BaseModel
from tenacity import RetryCallState


def get_as_model(model: type[BaseModel] | None, value: dict | BaseModel | None):
    if model is None or value is None:
        return value

    if isinstance(value, model):
        return value

    return model.model_validate(value)


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


def get_annotation_for(cls: type, attribute: str) -> type[BaseModel] | None:
    for base in getmro(cls):
        annotations = get_annotations(base)

        if attribute in annotations:
            return annotations[attribute]

    return None


def _get_type_var_values(cls: type) -> dict[Any, Any]:
    """Maps the type variables of the generic bases of `cls` to their value

    Values that are not bound by `cls` or its bases are type variables of `cls`.
    """
    mapping: dict[Any, Any] = {}
    for base in cls.__dict__.get("__orig_bases__", cls.__bases__):
        origin = get_origin(base) or base
        if not isinstance(origin, type) or origin is Generic:
            continue

        parameters = getattr(origin, "__parameters__", ())
        arguments = dict(zip(parameters, get_args(base), strict=False))
        inherited = _get_type_var_values(origin) | {p: p for p in parameters}
        for type_var, value in inherited.items():
            # A value bound by a base wins over a type variable left unbound by another
            if isinstance(mapping.get(type_var, type_var), TypeVar):
                mapping[type_var] = arguments.get(value, value)

    return mapping


def get_type_argument(cls: type, generic: type, index: int = 0) -> Any:
    """Returns the type argument given to `cls` for a parameter of `generic`

    E.g. for `class MyModule(Module[MyConfiguration])`, the type argument of
    `MyModule` for the first parameter of `Module` is `MyConfiguration`.
    If the parameter is not bound, its default value is returned, if any.
    """
    type_var = getattr(generic, "__parameters__", ())[index]
    value = _get_type_var_values(cls).get(type_var, type_var)
    while isinstance(value, TypeVar):
        if not getattr(value, "has_default", lambda: False)():
            return None
        value = value.__default__  # type: ignore[attr-defined]

    return value


def get_configuration_model(
    cls: type, generic: type, index: int = 0
) -> type[BaseModel] | None:
    """Returns the Pydantic model of the configuration of `cls`, if any

    The model is the type argument given to `cls` for the parameter of `generic`
    at `index`. For backward compatibility, a `configuration: MyModel` annotation
    takes precedence.
    """
    for model in (
        get_annotation_for(cls, "configuration"),
        get_type_argument(cls, generic, index),
    ):
        if isinstance(model, type) and issubclass(model, BaseModel):
            return model

    return None


def capture_retry_error(retry_state: RetryCallState):
    if retry_state.outcome:
        sentry_sdk.capture_exception(retry_state.outcome.result())


def chunks(iterable: Sequence, chunk_size: int):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i : i + chunk_size]
