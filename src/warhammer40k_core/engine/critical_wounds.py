from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleEffectKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class WoundRollCriticalThresholdContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile
    current_critical_threshold: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Wound critical threshold state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier("attacking_unit_instance_id", self.attacking_unit_instance_id),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier("attacker_model_instance_id", self.attacker_model_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Wound critical threshold profile must be WeaponProfile.")
        object.__setattr__(
            self,
            "current_critical_threshold",
            _validate_d6_target(self.current_critical_threshold),
        )


def generic_rule_critical_wound_threshold(
    context: WoundRollCriticalThresholdContext,
) -> int:
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        _matching_generic_attack_effects,  # pyright: ignore[reportPrivateUsage]
        _required_int_parameter,  # pyright: ignore[reportPrivateUsage]
        _required_string_parameter,  # pyright: ignore[reportPrivateUsage]
        _roll_type_matches,  # pyright: ignore[reportPrivateUsage]
    )

    if type(context) is not WoundRollCriticalThresholdContext:
        raise GameLifecycleError(
            "Generic critical wound hooks require WoundRollCriticalThresholdContext."
        )
    current = context.current_critical_threshold
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        effect_kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
        legacy_attacker_role_allowed=lambda _candidate: True,
        legacy_target_role_allowed=lambda _candidate: False,
    ):
        if _required_string_parameter(effect.parameters, key="status") != (
            "critical_wound_threshold"
        ):
            continue
        if not _roll_type_matches(effect.parameters, expected="wound"):
            continue
        current = min(
            current,
            _validate_d6_target(
                _required_int_parameter(effect.parameters, key="critical_threshold")
            ),
        )
    return current


def _battle_phase_from_token(value: object) -> BattlePhase:
    if type(value) is BattlePhase:
        return value
    if type(value) is not str:
        raise GameLifecycleError("source_phase must be a BattlePhase or phase token.")
    try:
        return BattlePhase(value)
    except ValueError as exc:
        raise GameLifecycleError("source_phase has an unsupported phase token.") from exc


def _validate_d6_target(value: object) -> int:
    if type(value) is not int or not 2 <= value <= 6:
        raise GameLifecycleError("Critical Wound threshold must be between 2 and 6.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
