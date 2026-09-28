"""Explicit unit/model ownership for characteristic provider evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class UnitCharacteristicModifierContext:
    state: GameState
    unit_instance_id: str
    characteristic: Characteristic
    base_value: int
    current_value: int
    model_instance_id: str | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Unit characteristic modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        if self.model_instance_id is not None:
            object.__setattr__(
                self,
                "model_instance_id",
                _validate_identifier("model_instance_id", self.model_instance_id),
            )
            from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

            rules_unit_view_by_id(
                state=self.state, unit_instance_id=self.unit_instance_id
            ).model_by_id(self.model_instance_id)
        object.__setattr__(
            self,
            "characteristic",
            characteristic_from_runtime_token(self.characteristic),
        )
        object.__setattr__(
            self,
            "base_value",
            _validate_non_negative_int("base_value", self.base_value),
        )
        object.__setattr__(
            self,
            "current_value",
            _validate_non_negative_int("current_value", self.current_value),
        )


def characteristic_from_runtime_token(token: object) -> Characteristic:
    if type(token) is Characteristic:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Runtime modifier characteristic must be a Characteristic.")
    try:
        return Characteristic(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported runtime modifier characteristic: {token}.") from exc


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative integer.")
    return value
