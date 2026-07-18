from __future__ import annotations


class DiceError(ValueError):
    """Base error for invalid dice domain data."""


class DiceRollSpecError(DiceError):
    """Raised when a dice roll request violates replay-facing invariants."""
