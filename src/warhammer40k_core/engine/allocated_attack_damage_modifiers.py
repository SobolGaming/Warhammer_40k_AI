from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

type AllocatedAttackDamageModifierHandler = Callable[["AllocatedAttackDamageModifierContext"], int]


@dataclass(frozen=True, slots=True)
class AllocatedAttackDamageModifierContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    allocated_model_instance_id: str
    weapon_profile: WeaponProfile
    current_value: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Allocated-attack Damage modifier state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        for field_name in (
            "attacking_unit_instance_id",
            "attacker_model_instance_id",
            "target_unit_instance_id",
            "allocated_model_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError(
                "Allocated-attack Damage modifier profile must be WeaponProfile."
            )
        if type(self.current_value) is not int or self.current_value <= 0:
            raise GameLifecycleError("Allocated-attack Damage current_value must be positive.")


@dataclass(frozen=True, slots=True)
class AllocatedAttackDamageModifierBinding:
    modifier_id: str
    source_id: str
    handler: AllocatedAttackDamageModifierHandler

    def __post_init__(self) -> None:
        _validate_identifier("allocated-attack Damage modifier_id", self.modifier_id)
        _validate_identifier("allocated-attack Damage source_id", self.source_id)
        if not callable(self.handler):
            raise GameLifecycleError("Allocated-attack Damage handler must be callable.")


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Allocated-attack Damage phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported allocated-attack Damage BattlePhase: {token}."
        ) from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
