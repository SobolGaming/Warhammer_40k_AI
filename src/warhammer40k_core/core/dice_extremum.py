"""Physical component identities for Core highest/lowest die references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.core.dice_errors import DiceRollSpecError


class DiceExtremum(StrEnum):
    HIGHEST = "highest"
    LOWEST = "lowest"


@dataclass(frozen=True, slots=True)
class DiceExtremumSelection:
    roll_state: DiceRollState
    extremum: DiceExtremum
    component_index: int

    def __post_init__(self) -> None:
        indices = extremum_indices(self.roll_state, self.extremum)
        if type(self.component_index) is not int or self.component_index not in indices:
            raise DiceRollSpecError("Selected die is not a matching highest/lowest component.")

    @property
    def component_id(self) -> str:
        return f"{self.roll_state.original_result.roll_id}:component-{self.component_index}"

    @property
    def value(self) -> int:
        return self.roll_state.current_values[self.component_index]


def extremum_indices(state: DiceRollState, extremum: DiceExtremum) -> tuple[int, ...]:
    if type(state) is not DiceRollState or type(extremum) is not DiceExtremum:
        raise DiceRollSpecError("Highest/lowest selection requires typed dice state and kind.")
    value = (max if extremum is DiceExtremum.HIGHEST else min)(state.current_values)
    return tuple(
        index for index, candidate in enumerate(state.current_values) if candidate == value
    )
