"""Exact decimal sums. Missing values stay missing."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+)(?:\.\d+)?$")


class UnitsError(ValueError):
    """A present units field is not a finite number."""


def parse_units(value) -> Decimal | None:
    """Return a Decimal, or None when the field is absent or blank.

    Booleans, NaN, and infinities raise ``UnitsError``. They are not coerced
    to zero.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise UnitsError("not a number")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise UnitsError("not a finite number")
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnitsError("not a finite number")
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise UnitsError("not a number") from exc
        if not parsed.is_finite():
            raise UnitsError("not a finite number")
        return parsed
    raise UnitsError("not a number")


def format_units(value: Decimal) -> str:
    """Render a Decimal without scientific notation or binary float noise."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0", "+0"}:
        return "0"
    return text


def add_units(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal(0))


def is_plain_number(value: str) -> bool:
    return _PLAIN_NUMBER.fullmatch(value.strip()) is not None
