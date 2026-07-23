from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type PostRollWeaponProfileModifierHandler = Callable[
    ["PostRollWeaponProfileModifierContext"],
    WeaponProfile,
]

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class ResolvedAttackRollValues:
    unmodified_roll: int | None
    final_roll: int | None
    successful: bool
    critical: bool
    skipped: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unmodified_roll",
            _validate_optional_d6_value("unmodified_roll", self.unmodified_roll),
        )
        object.__setattr__(
            self,
            "final_roll",
            _validate_optional_int("final_roll", self.final_roll),
        )
        for field_name in ("successful", "critical", "skipped"):
            if type(getattr(self, field_name)) is not bool:
                raise GameLifecycleError(f"Resolved attack roll {field_name} must be a bool.")
        if self.skipped:
            if self.unmodified_roll is not None or self.final_roll is not None:
                raise GameLifecycleError("Skipped attack roll cannot include rolled values.")
        elif self.unmodified_roll is None or self.final_roll is None:
            raise GameLifecycleError("Resolved attack roll requires rolled values.")
        if self.critical and not self.successful:
            raise GameLifecycleError("Critical attack roll must be successful.")


@dataclass(frozen=True, slots=True)
class PostRollWeaponProfileModifierContext:
    state: GameState
    source_phase: BattlePhase
    attack_context_id: str
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    hit_roll: ResolvedAttackRollValues
    wound_roll: ResolvedAttackRollValues
    weapon_profile: WeaponProfile

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Post-roll weapon profile modifier state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        for field_name in (
            "attack_context_id",
            "attacking_unit_instance_id",
            "attacker_model_instance_id",
            "target_unit_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if type(self.hit_roll) is not ResolvedAttackRollValues:
            raise GameLifecycleError("Post-roll profile modifier requires Hit roll values.")
        if type(self.wound_roll) is not ResolvedAttackRollValues:
            raise GameLifecycleError("Post-roll profile modifier requires Wound roll values.")
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError(
                "Post-roll weapon profile modifier profile must be WeaponProfile."
            )


@dataclass(frozen=True, slots=True)
class PostRollWeaponProfileModifierBinding:
    modifier_id: str
    source_id: str
    handler: PostRollWeaponProfileModifierHandler

    def __post_init__(self) -> None:
        _validate_identifier("post-roll weapon profile modifier modifier_id", self.modifier_id)
        _validate_identifier("post-roll weapon profile modifier source_id", self.source_id)
        if not callable(self.handler):
            raise GameLifecycleError("post-roll weapon profile modifier handler must be callable.")


def modified_post_roll_weapon_profile(
    *,
    bindings: tuple[PostRollWeaponProfileModifierBinding, ...],
    context: PostRollWeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not PostRollWeaponProfileModifierContext:
        raise GameLifecycleError("Post-roll weapon profile modifiers require a context.")
    current = context.weapon_profile
    for binding in bindings:
        if type(binding) is not PostRollWeaponProfileModifierBinding:
            raise GameLifecycleError("Post-roll weapon profile modifier binding is invalid.")
        current = binding.handler(replace(context, weapon_profile=current))
        if type(current) is not WeaponProfile:
            raise GameLifecycleError(
                f"{binding.modifier_id} returned weapon profile must be a WeaponProfile."
            )
    return current


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Post-roll modifier BattlePhase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported post-roll modifier BattlePhase: {token}.") from exc


def _validate_optional_d6_value(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    integer = _validate_int(field_name, value)
    if not 1 <= integer <= 6:
        raise GameLifecycleError(f"{field_name} must be between 1 and 6.")
    return integer


def _validate_optional_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_int(field_name, value)


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    return value
