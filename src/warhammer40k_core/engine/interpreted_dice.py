"""Validate rule-interpreted faces against authenticated physical roll state."""

from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_interpreted_d6(*, state: DiceRollState, value: int) -> None:
    if type(state) is not DiceRollState:
        raise GameLifecycleError("Interpreted D6 requires a DiceRollState.")
    expression = state.original_result.spec.expression
    if expression.quantity != 1 or expression.sides != 6 or expression.modifier != 0:
        raise GameLifecycleError("Interpreted D6 requires one physical D6 without an offset.")
    if type(value) is not int or value != state.current_total:
        raise GameLifecycleError("Interpreted D6 value does not match its dice state.")


@dataclass(frozen=True, slots=True)
class CriticalRollThreshold:
    value: int = 6
    inclusive: bool = False

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 2 <= self.value <= 6:
            raise GameLifecycleError("Critical threshold must be between 2 and 6.")
        if type(self.inclusive) is not bool:
            raise GameLifecycleError("Critical threshold inclusive must be boolean.")
        if not self.inclusive and self.value != 6:
            raise GameLifecycleError("Default critical result must be exactly six.")

    def matches(self, value: int) -> bool:
        return value >= self.value if self.inclusive else value == self.value
