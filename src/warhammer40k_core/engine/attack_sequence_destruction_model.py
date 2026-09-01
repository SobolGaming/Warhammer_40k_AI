from __future__ import annotations

from dataclasses import dataclass
from typing import Self, cast

from warhammer40k_core.engine.attack_sequence_model import (
    AttackResolutionContextPayload,
    PendingAttackDestructionPayload,
)
from warhammer40k_core.engine.attack_sequence_validation import (
    _validate_destruction_reaction_source_tuple,
    _validate_identifier,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DestructionReactionSource,
    FeelNoPainResolution,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


@dataclass(frozen=True, slots=True)
class PendingAttackDestruction:
    """One logically dead model retained until its attacking unit finishes its attacks."""

    attack_context: AttackResolutionContextPayload
    attack_pool: RangedAttackPool
    damage_application: DamageApplication
    saving_throw_payload: JsonValue
    feel_no_pain: FeelNoPainResolution
    destroyed_model_controller_player_id: str
    destruction_sources: tuple[DestructionReactionSource, ...]
    damage_event_id: str
    destroyed_model_placement: JsonValue

    def __post_init__(self) -> None:
        attack_context = validate_json_value(self.attack_context)
        if not isinstance(attack_context, dict):
            raise GameLifecycleError("Pending attack destruction context must be an object.")
        object.__setattr__(
            self,
            "attack_context",
            cast(AttackResolutionContextPayload, attack_context),
        )
        if type(self.attack_pool) is not RangedAttackPool:
            raise GameLifecycleError("Pending attack destruction requires an attack pool.")
        if type(self.damage_application) is not DamageApplication:
            raise GameLifecycleError("Pending attack destruction requires damage application.")
        if not self.damage_application.destroyed:
            raise GameLifecycleError("Pending attack destruction requires destroyed damage.")
        if (
            self.attack_context["sequence_id"] == ""
            or self.attack_context["attack_context_id"] == ""
            or self.attack_context["weapon_instance_id"] != self.attack_pool.weapon_instance_id
            or self.attack_context["weapon_profile_id"] != self.attack_pool.weapon_profile_id
            or self.attack_context["target_unit_instance_id"]
            != self.damage_application.target_unit_instance_id
        ):
            raise GameLifecycleError("Pending attack destruction context drift.")
        object.__setattr__(
            self,
            "saving_throw_payload",
            validate_json_value(self.saving_throw_payload),
        )
        if type(self.feel_no_pain) is not FeelNoPainResolution:
            raise GameLifecycleError("Pending attack destruction requires Feel No Pain result.")
        object.__setattr__(
            self,
            "destroyed_model_controller_player_id",
            _validate_identifier(
                "Pending attack destruction controller",
                self.destroyed_model_controller_player_id,
            ),
        )
        object.__setattr__(
            self,
            "destruction_sources",
            _validate_destruction_reaction_source_tuple(
                "Pending attack destruction sources",
                self.destruction_sources,
            ),
        )
        object.__setattr__(
            self,
            "damage_event_id",
            _validate_identifier(
                "Pending attack destruction damage_event_id",
                self.damage_event_id,
            ),
        )
        destroyed_model_placement = validate_json_value(self.destroyed_model_placement)
        if not isinstance(destroyed_model_placement, dict):
            raise GameLifecycleError(
                "Pending attack destruction requires pre-removal placement evidence."
            )
        object.__setattr__(self, "destroyed_model_placement", destroyed_model_placement)

    def to_payload(self) -> PendingAttackDestructionPayload:
        return {
            "attack_context": self.attack_context,
            "attack_pool": self.attack_pool.to_payload(),
            "damage_application": self.damage_application.to_payload(),
            "saving_throw": self.saving_throw_payload,
            "feel_no_pain": self.feel_no_pain.to_payload(),
            "destroyed_model_controller_player_id": self.destroyed_model_controller_player_id,
            "destruction_sources": [source.to_payload() for source in self.destruction_sources],
            "damage_event_id": self.damage_event_id,
            "destroyed_model_placement": self.destroyed_model_placement,
        }

    @classmethod
    def from_payload(cls, payload: PendingAttackDestructionPayload) -> Self:
        return cls(
            attack_context=payload["attack_context"],
            attack_pool=RangedAttackPool.from_payload(payload["attack_pool"]),
            damage_application=DamageApplication.from_payload(payload["damage_application"]),
            saving_throw_payload=payload["saving_throw"],
            feel_no_pain=FeelNoPainResolution.from_payload(payload["feel_no_pain"]),
            destroyed_model_controller_player_id=payload["destroyed_model_controller_player_id"],
            destruction_sources=tuple(
                DestructionReactionSource.from_payload(source)
                for source in payload["destruction_sources"]
            ),
            damage_event_id=payload["damage_event_id"],
            destroyed_model_placement=payload["destroyed_model_placement"],
        )


__all__ = ("PendingAttackDestruction",)
