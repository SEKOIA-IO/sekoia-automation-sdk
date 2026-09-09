import email.utils
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

RESET_JITTER_DEFAULT_MAX = 10800  # 3 hours


def compute_reset_jitter(seed: str, max_seconds: float) -> float:
    """
    Compute a deterministic jitter delay in ``[0, max_seconds]`` seconds.

    Args:
        seed: Stable identifier used to derive the delay (e.g. the connector
            configuration UUID).
        max_seconds: Upper bound of the jitter window. Values ``<= 0`` disable
            the jitter and this function returns ``0``.

    Returns:
        float: Delay in seconds, in the ``[0, max_seconds]`` interval.
    """
    if max_seconds <= 0 or not seed:
        return 0.0
    return random.Random(seed).uniform(0, max_seconds)


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
