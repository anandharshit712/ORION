"""
Reusable validation helpers for ORION.

Provides common validation patterns used across modules.
"""

from typing import Any, Optional


def validate_range(
    value: float,
    min_val: float,
    max_val: float,
    name: str = "value",
) -> float:
    """
    Validate that a value falls within [min_val, max_val].

    Args:
        value: Value to check.
        min_val: Minimum allowed value (inclusive).
        max_val: Maximum allowed value (inclusive).
        name: Name for error messages.

    Returns:
        The validated value.

    Raises:
        ValueError: If value is out of range.
    """
    if not (min_val <= value <= max_val):
        raise ValueError(
            f"{name} must be in [{min_val}, {max_val}], got {value}"
        )
    return value


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value to [min_val, max_val].

    Args:
        value: Value to clamp.
        min_val: Minimum.
        max_val: Maximum.

    Returns:
        Clamped value.
    """
    return max(min_val, min(value, max_val))


def validate_positive(value: float, name: str = "value") -> float:
    """
    Validate that a value is strictly positive.

    Args:
        value: Value to check.
        name: Name for error messages.

    Returns:
        The validated value.

    Raises:
        ValueError: If value <= 0.
    """
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def validate_non_negative(value: float, name: str = "value") -> float:
    """
    Validate that a value is >= 0.

    Args:
        value: Value to check.
        name: Name for error messages.

    Returns:
        The validated value.

    Raises:
        ValueError: If value < 0.
    """
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def validate_type(value: Any, expected_type: type, name: str = "value") -> Any:
    """
    Validate that a value is of the expected type.

    Args:
        value: Value to check.
        expected_type: Expected type.
        name: Name for error messages.

    Returns:
        The validated value.

    Raises:
        TypeError: If value is not of expected type.
    """
    if not isinstance(value, expected_type):
        raise TypeError(
            f"{name} must be {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def validate_not_empty(value: str, name: str = "value") -> str:
    """
    Validate that a string is non-empty after stripping whitespace.

    Args:
        value: String to check.
        name: Name for error messages.

    Returns:
        The validated value.

    Raises:
        ValueError: If string is empty.
    """
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value
