"""Input validators shared by config flows and service schemas."""

from __future__ import annotations

from datetime import date
import math
from typing import Any

import voluptuous as vol


def non_empty_string(value: Any) -> str:
    """Return a trimmed string and reject blank values."""
    if value is None:
        raise vol.Invalid("Value must be a non-empty string")
    text = str(value).strip()
    if not text:
        raise vol.Invalid("Value must be a non-empty string")
    return text


def _finite_number(value: Any, *, minimum: float, exclusive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid("Expected a number") from err
    if not math.isfinite(number):
        raise vol.Invalid("Number must be finite")
    if (exclusive and number <= minimum) or (not exclusive and number < minimum):
        operator = "greater than" if exclusive else "at least"
        raise vol.Invalid(f"Number must be {operator} {minimum:g}")
    return number


def positive_number(value: Any) -> float:
    """Validate a finite number greater than zero."""
    return _finite_number(value, minimum=0, exclusive=True)


def non_negative_number(value: Any) -> float:
    """Validate a finite number greater than or equal to zero."""
    return _finite_number(value, minimum=0)


def non_negative_int(value: Any) -> int:
    """Validate an integer greater than or equal to zero."""
    try:
        number = int(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid("Expected an integer") from err
    if number < 0:
        raise vol.Invalid("Integer must be at least 0")
    return number


def expiration_date(value: Any) -> str:
    """Validate and normalize a calendar date in YYYY-MM-DD format."""
    text = non_empty_string(value)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as err:
        raise vol.Invalid("Date must use YYYY-MM-DD format") from err
    if parsed.isoformat() != text:
        raise vol.Invalid("Date must use YYYY-MM-DD format")
    return text
