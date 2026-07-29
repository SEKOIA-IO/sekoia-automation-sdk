import email.utils
import math
from datetime import datetime

RATE_LIMIT_DEFAULT_WAIT = 3600  # 1 hour


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
