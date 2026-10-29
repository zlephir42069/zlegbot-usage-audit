"""Duration and timestamp parsing."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_DURATION = re.compile(r"^(\d+)([smhdw])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(value: str) -> timedelta:
    """Parse `30s`, `15m`, `12h`, `7d`, or `1w` into a timedelta."""
    text = value.strip().lower()
    match = _DURATION.fullmatch(text)
    if not match:
        raise ValueError(
            f"invalid duration {value!r} (use a number plus s, m, h, d, or w, such as 30m)"
        )
    amount = int(match.group(1))
    return timedelta(seconds=amount * _UNITS[match.group(2)])


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp. A trailing Z is UTC.

    A value with no offset is read as UTC. The report states that rule.
    """
    text = value.strip()
    if not text:
        raise ValueError("timestamp is empty")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_since(value: str, anchor: datetime) -> tuple[datetime, str]:
    """Resolve ``--since`` against the latest timestamp in the file.

    A duration is subtracted from ``anchor``. An absolute timestamp is used
    as given. The clock is not consulted, so the window stays a function of
    the log plus the flag.
    """
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    else:
        anchor = anchor.astimezone(timezone.utc)
    text = value.strip()
    try:
        duration = parse_duration(text)
    except ValueError:
        duration = None
    if duration is not None:
        bound = anchor - duration
        note = (
            f"duration {text} before the latest parsed timestamp {format_timestamp(anchor)}"
        )
        return bound, note
    try:
        bound = parse_timestamp(text)
    except ValueError as exc:
        raise ValueError(
            f"invalid --since {value!r} (use a duration like 7d or an ISO timestamp)"
        ) from exc
    return bound, "absolute timestamp"


def parse_until(value: str) -> datetime:
    """Resolve ``--until`` as an inclusive ISO-8601 timestamp."""
    try:
        return parse_timestamp(value)
    except ValueError as exc:
        raise ValueError(f"invalid --until {value!r} (use an ISO timestamp)") from exc


def format_timestamp(value: datetime) -> str:
    """Format a UTC timestamp with a Z suffix."""
    utc = value.astimezone(timezone.utc)
    text = utc.isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text
