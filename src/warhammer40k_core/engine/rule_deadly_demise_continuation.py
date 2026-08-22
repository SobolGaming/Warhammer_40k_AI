from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageApplicationPayload,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionReactionSourcePayload,
    MortalWoundApplication,
    model_owner_player_id,
)
from warhammer40k_core.engine.destruction_provenance import (
    DestructionProvenance,
    DestructionSourceKind,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    MortalWoundDestructionEvidencePayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


RULE_MODEL_DESTRUCTION_CONTEXT_KIND = "rule_model_destroyed"
RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND = "source_rule_destruction"
RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND = "deadly_demise_collateral"
RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND = "applied_mortal_wound_damage"
RULE_DEADLY_DEMISE_SECONDARY_CONTINUATION_KIND = "rule_deadly_demise_secondary_casualties"


@dataclass(frozen=True, slots=True)
class RuleDeadlyDemiseSecondaryContinuation:
    root_context: dict[str, JsonValue]
    source: DestructionReactionSource
    descriptor: dict[str, JsonValue]
    trigger_roll_payload: JsonValue
    affected_target_unit_ids: tuple[str, ...]
    pending_target_unit_ids: tuple[str, ...]
    pending_sources: tuple[DestructionReactionSource, ...]
    pending_secondary_damage_applications: tuple[DamageApplication, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_context", _payload_object(self.root_context, "root_context"))
        if type(self.source) is not DestructionReactionSource:
            raise GameLifecycleError("Rule Deadly Demise continuation source is invalid.")
        object.__setattr__(self, "descriptor", _payload_object(self.descriptor, "descriptor"))
        object.__setattr__(
            self,
            "trigger_roll_payload",
            validate_json_value(self.trigger_roll_payload),
        )
        for field_name in ("affected_target_unit_ids", "pending_target_unit_ids"):
            object.__setattr__(
                self,
                field_name,
                _identifier_tuple(field_name, getattr(self, field_name)),
            )
        if type(self.pending_sources) is not tuple or any(
            type(source) is not DestructionReactionSource for source in self.pending_sources
        ):
            raise GameLifecycleError("Rule Deadly Demise continuation sources are invalid.")
        if type(self.pending_secondary_damage_applications) is not tuple or any(
            type(damage) is not DamageApplication or not damage.destroyed
            for damage in self.pending_secondary_damage_applications
        ):
            raise GameLifecycleError("Rule Deadly Demise continuation casualties are invalid.")

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "continuation_kind": RULE_DEADLY_DEMISE_SECONDARY_CONTINUATION_KIND,
                    "root_context": self.root_context,
                    "source": self.source.to_payload(),
                    "descriptor": self.descriptor,
                    "trigger_roll": self.trigger_roll_payload,
                    "affected_target_unit_ids": list(self.affected_target_unit_ids),
                    "pending_target_unit_ids": list(self.pending_target_unit_ids),
                    "pending_sources": [source.to_payload() for source in self.pending_sources],
                    "pending_secondary_damage_applications": [
                        damage.to_payload() for damage in self.pending_secondary_damage_applications
                    ],
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, JsonValue]) -> Self:
        if payload.get("continuation_kind") != RULE_DEADLY_DEMISE_SECONDARY_CONTINUATION_KIND:
            raise GameLifecycleError("Rule Deadly Demise continuation kind is unsupported.")
        return cls(
            root_context=_payload_object(payload.get("root_context"), "root_context"),
            source=DestructionReactionSource.from_payload(
                cast(
                    DestructionReactionSourcePayload,
                    _payload_object(payload.get("source"), "source"),
                )
            ),
            descriptor=_payload_object(payload.get("descriptor"), "descriptor"),
            trigger_roll_payload=validate_json_value(payload.get("trigger_roll")),
            affected_target_unit_ids=_payload_identifier_tuple(
                payload,
                "affected_target_unit_ids",
            ),
            pending_target_unit_ids=_payload_identifier_tuple(
                payload,
                "pending_target_unit_ids",
            ),
            pending_sources=_payload_source_tuple(payload, "pending_sources"),
            pending_secondary_damage_applications=_payload_damage_tuple(
                payload,
                "pending_secondary_damage_applications",
            ),
        )


def build_rule_deadly_demise_secondary_root_context(
    *,
    state: GameState,
    parent_root_context: dict[str, JsonValue],
    source: DestructionReactionSource,
    damage: DamageApplication,
    completion_continuation: JsonValue,
) -> dict[str, JsonValue]:
    model_id = damage.model_instance_id
    physical_unit_id = state.unit_instance_id_for_model(model_id)
    rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=physical_unit_id,
    ).unit_instance_id
    sources = state.destruction_reaction_sources_for_model(model_instance_id=model_id)
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "context_kind": RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
                "completion_kind": RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND,
                "completion_continuation": completion_continuation,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": _payload_string(parent_root_context, "phase"),
                "source_step": "deadly_demise_collateral",
                "source_rule_id": source.source_rule_id,
                "source_effect_ids": [],
                "source_result_id": (
                    f"{_payload_string(parent_root_context, 'source_result_id')}:"
                    f"deadly-demise:{source.source_id}:{model_id}"
                ),
                "rules_unit_instance_id": rules_unit_id,
                "target_unit_instance_id": physical_unit_id,
                "model_instance_id": model_id,
                "destroying_player_id": _payload_string(
                    parent_root_context,
                    "destroyed_model_controller_player_id",
                ),
                "source_rules_unit_instance_id": _payload_string(
                    parent_root_context,
                    "rules_unit_instance_id",
                ),
                "source_model_instance_id": _payload_string(
                    parent_root_context,
                    "model_instance_id",
                ),
                "destroyed_model_controller_player_id": model_owner_player_id(
                    state=state,
                    model_instance_id=model_id,
                ),
                "destroyed_model_placement": _model_placement_payload(
                    state=state,
                    model_instance_id=model_id,
                ),
                "destruction_source_kind": DestructionSourceKind.DEADLY_DEMISE.value,
                "damage_application": damage.to_payload(),
                "post_removal_mandatory_sources": [
                    item.to_payload()
                    for item in sources
                    if not item.optional
                    and item.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE
                ],
            }
        ),
    )


def destroyed_damage_applications(
    application: MortalWoundApplication,
) -> tuple[DamageApplication, ...]:
    if type(application) is not MortalWoundApplication:
        raise GameLifecycleError("Rule Deadly Demise requires a mortal-wound application.")
    return tuple(damage for damage in application.applications if damage.destroyed)


def damage_application_from_rule_context(
    context: dict[str, JsonValue],
) -> DamageApplication | None:
    completion_kind = _payload_string(context, "completion_kind")
    raw_damage = context.get("damage_application")
    if completion_kind == RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND:
        if raw_damage is not None:
            raise GameLifecycleError("Source rule destruction cannot carry collateral damage.")
        return None
    if completion_kind not in {
        RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND,
    }:
        raise GameLifecycleError("Rule destruction completion kind is unsupported.")
    damage = DamageApplication.from_payload(
        cast(DamageApplicationPayload, _payload_object(raw_damage, "damage_application"))
    )
    if not damage.destroyed or damage.model_instance_id != _payload_string(
        context,
        "model_instance_id",
    ):
        raise GameLifecycleError("Applied rule destruction damage context drift.")
    return damage


def destruction_provenance_from_rule_context(
    context: dict[str, JsonValue],
) -> DestructionProvenance:
    completion_kind = _payload_string(context, "completion_kind")
    if completion_kind == RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND:
        return DestructionProvenance.for_non_attack(DestructionSourceKind.ABILITY)
    if completion_kind == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND:
        raw_evidence = _payload_object(
            context.get("mortal_wound_destruction_evidence"),
            "mortal_wound_destruction_evidence",
        )
        evidence = MortalWoundDestructionEvidence.from_payload(
            cast(MortalWoundDestructionEvidencePayload, raw_evidence)
        )
        return evidence.destruction_attribution.destruction_provenance
    if completion_kind != RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND:
        raise GameLifecycleError("Rule destruction completion kind is unsupported.")
    if context.get("destruction_source_kind") != DestructionSourceKind.DEADLY_DEMISE.value:
        raise GameLifecycleError("Collateral rule destruction provenance drift.")
    return DestructionProvenance.for_non_attack(DestructionSourceKind.DEADLY_DEMISE)


def _model_placement_payload(*, state: GameState, model_instance_id: str) -> JsonValue:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rule Deadly Demise requires battlefield state.")
    placement = battlefield.model_placement_or_none(model_instance_id)
    if placement is None:
        raise GameLifecycleError("Rule Deadly Demise casualty must remain placed.")
    return validate_json_value(placement.to_payload())


def _payload_object(value: object, field_name: str) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"Rule Deadly Demise continuation {field_name} must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(key, payload.get(key))


def _identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Rule Deadly Demise continuation {field_name} must be a tuple.")
    values = cast(tuple[object, ...], value)
    identifiers = tuple(_validate_identifier(field_name, item) for item in values)
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"Rule Deadly Demise continuation {field_name} has duplicates.")
    return identifiers


def _payload_identifier_tuple(
    payload: dict[str, JsonValue],
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Rule Deadly Demise continuation {key} must be a list.")
    return _identifier_tuple(key, tuple(value))


def _payload_source_tuple(
    payload: dict[str, JsonValue],
    key: str,
) -> tuple[DestructionReactionSource, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise GameLifecycleError(f"Rule Deadly Demise continuation {key} must be a source list.")
    return tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, item))
        for item in value
    )


def _payload_damage_tuple(
    payload: dict[str, JsonValue],
    key: str,
) -> tuple[DamageApplication, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise GameLifecycleError(f"Rule Deadly Demise continuation {key} must be a damage list.")
    return tuple(
        DamageApplication.from_payload(cast(DamageApplicationPayload, item)) for item in value
    )


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Rule Deadly Demise continuation requires active player.")
    return state.active_player_id


_validate_identifier = IdentifierValidator(GameLifecycleError)
