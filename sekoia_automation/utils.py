from collections.abc import Sequence
from functools import wraps
from inspect import get_annotations, getmro

import sentry_sdk
from pydantic import BaseModel
from tenacity import RetryCallState


def get_as_model(model: type[BaseModel] | None, value: dict | BaseModel | None):
    if model is None or value is None:
        return value

    if isinstance(value, model):
        return value

    return model.parse_obj(value)


def validate_with_model(model: type[BaseModel] | None, value: dict | BaseModel | None):
    if model is None or value is None:
        return value

    return get_as_model(model, value).dict()


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


def capture_retry_error(retry_state: RetryCallState):
    if retry_state.outcome:
        sentry_sdk.capture_exception(retry_state.outcome.result())


def chunks(iterable: Sequence, chunk_size: int):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i : i + chunk_size]
