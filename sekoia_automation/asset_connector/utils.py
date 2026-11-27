import email.utils
import json
import math
import os
import random
from datetime import datetime

RATE_LIMIT_DEFAULT_WAIT = 3600  # 1 hour

# Statuses a task can hold while the platform has not finished ingesting the
# pushed assets yet. Anything else is terminal.
TASK_PENDING_STATUSES = frozenset({"PENDING", "RUNNING"})
TASK_POLL_INTERVAL_DEFAULT = 5.0  # seconds between two task status checks
TASK_POLL_TIMEOUT_DEFAULT = 300.0  # give up waiting after 5 minutes

# Push statuses refusing the batch itself: pushing it again cannot succeed.
# A 413 is not one of them: without the refused item, it may be a partial write.
REJECTED_BATCH_STATUSES = frozenset({400, 422})

# Code of the 429 the push API returns once a configuration reached a limit
LIMIT_REACHED_CODE = "ASSET_CONNECTOR_LIMIT_REACHED"

RESET_JITTER_DEFAULT_MAX = 10800  # 3 hours
# The jitter wait is split in slices of this duration (in seconds) to send a
# heartbeat between each of them.
RESET_JITTER_HEARTBEAT_INTERVAL = 60.0


def compute_reset_jitter(seed: str | None, max_seconds: float) -> float:
    """
    Compute a jitter delay in ``[0, max_seconds]`` seconds.

    The delay is deterministic for a given seed, so a connector that restarts
    keeps the same slot in the window. Without a seed there is nothing stable
    to derive it from: the delay is then random, so that the configurations of
    a connector still do not restart all at once.

    Args:
        seed: Stable identifier used to derive the delay (e.g. the connector
            configuration UUID), if any.
        max_seconds: Upper bound of the jitter window. Values ``<= 0`` disable
            the jitter and this function returns ``0``.

    Returns:
        float: Delay in seconds, in the ``[0, max_seconds]`` interval.
    """
    if max_seconds <= 0:
        return 0.0
    rng = random.Random(seed) if seed else random.Random()
    return rng.uniform(0, max_seconds)


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


def parse_error_detail(body: str | None) -> dict | None:
    """
    Read the ``detail`` of an error returned by the push API, shaped as
    ``{"detail": {"message": ..., "code": ..., ...}}``.

    Args:
        body: Raw response body.
    Returns:
        dict | None: The detail, or None when the body is not JSON or has none.
    """
    try:
        detail = json.loads(body or "").get("detail")
    except (ValueError, AttributeError):
        return None
    return detail if isinstance(detail, dict) else None


def push_429_message(body: str | None, retry_after: float) -> str:
    """
    Describe a push refused with an HTTP 429: a reached limit, naming each
    limit, or a rate limit.

    Args:
        body: Raw response body.
        retry_after: Wait in seconds before the next fetch.
    Returns:
        str: The message to log.
    """
    wait = f"Waiting {retry_after} seconds before refetching."
    detail = parse_error_detail(body) or {}
    if detail.get("code") == LIMIT_REACHED_CODE:
        reached = detail.get("limits")
        limits = ", ".join(
            f"{limit.get('figure')} per {limit.get('scope')}"
            for limit in (reached if isinstance(reached, list) else [])
            if isinstance(limit, dict)
        )
        return f"Asset connector limit reached ({limits}). {wait}"
    reason = ", ".join(
        str(part)
        for part in ("HTTP 429", detail.get("code"), detail.get("limit"))
        if part
    )
    return f"Asset connector push rate limited ({reason}). {wait}"


def push_error_message(status_error: str, body: str | None) -> str:
    """
    Describe a push the API refused: its code, message and other details, or
    its raw body when it holds no ``detail``.

    Args:
        status_error: Description of the HTTP status.
        body: Raw response body.
    Returns:
        str: The message to log.
    """
    message = f"Error while pushing assets to Sekoia.io - {status_error}"
    detail = parse_error_detail(body)
    if detail is None:
        return f"{message} - {body}" if body else message

    others = ", ".join(
        f"{key}={value}"
        for key, value in detail.items()
        if key not in ("code", "message")
    )
    message = f"{message} - {detail.get('code')}: {detail.get('message')}"
    return f"{message} ({others})" if others else message
