import email.utils
import json
import math
import os
from datetime import datetime

RATE_LIMIT_DEFAULT_WAIT = 3600  # 1 hour

# Statuses a task can hold while the platform has not finished ingesting the
# pushed assets yet. Anything else is terminal.
TASK_PENDING_STATUSES = frozenset({"PENDING", "RUNNING"})
TASK_POLL_INTERVAL_DEFAULT = 5.0  # seconds between two task status checks
TASK_POLL_TIMEOUT_DEFAULT = 300.0  # give up waiting after 5 minutes


def parse_retry_after(header_value: str | None, default: float) -> float:
    """
    Parse the Retry-After header (RFC 7231): either delta-seconds or an
    HTTP-date. Falls back to ``default`` when missing or unparseable.

    Args:
        header_value: Raw Retry-After header value.
        default: Fallback wait in seconds.
    Returns:
        float: Wait time in seconds.
    """
    if not header_value:
        return default

    try:
        seconds: float = float(header_value)
    except ValueError:
        try:
            dt = email.utils.parsedate_to_datetime(header_value)
        except (TypeError, ValueError):
            return default
        if dt is None:
            return default
        seconds = (dt - datetime.now(tz=dt.tzinfo)).total_seconds()

    # Reject non-finite values (inf/nan) coming from an untrusted server,
    # and clamp to [0, RATE_LIMIT_DEFAULT_WAIT] so a bogus header can never
    # force a negative sleep or an arbitrarily long pause.
    if seconds is None or not math.isfinite(seconds):
        return default
    return min(max(seconds, 0.0), RATE_LIMIT_DEFAULT_WAIT)


def pop_refused_item(response_text: str | None, items: list[dict]) -> str | None:
    """
    Remove from a push the item an HTTP 413 refused, when the response names one.

    Only ``request_index``, the item's position in the request, is trusted.
    ``item_index`` counts the items left after the API dropped those with an
    unusable hostname, and ``item_bytes`` is measured after the API cut long
    strings: neither locates the item in the request.

    Args:
        response_text: Body of the 413 response.
        items: The items of the push, as sent. Updated in place.
    Returns:
        str | None: Message describing the removed item, or None when the response
        names no item (for instance when Kafka refused a whole message).
    """
    try:
        detail = json.loads(response_text or "")["detail"]
        index = detail["request_index"]
    except (ValueError, KeyError, TypeError):
        return None

    if type(index) is not int or not 0 <= index < len(items):
        return None

    item = items.pop(index)
    uids = {k: v["uid"] for k, v in item.items() if isinstance(v, dict) and "uid" in v}
    return (
        f"Asset item refused by Sekoia.io (HTTP 413, {detail.get('item_bytes')} bytes, "
        f"limit {detail.get('limit_bytes')}), dropped from the push: {uids}"
    )


def get_env_float(name: str, default: float) -> float:
    """
    Read a float from the environment, falling back to ``default`` when the
    variable is unset or does not hold a valid number.

    Args:
        name: Environment variable name.
        default: Fallback value.
    Returns:
        float: The parsed value or the default.
    """
    value = os.getenv(name)
    if not value:
        return default

    try:
        return float(value)
    except ValueError:
        return default
