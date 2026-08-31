from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_model import AttackResolutionContextPayload
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
        DestructionReactionSource,
        FeelNoPainResolution,
    )

_validate_identifier = IdentifierValidator(GameLifecycleError)


def deadly_demise_source_context_payload(
    *,
    sequence_id: str,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    wound_roll_payload: JsonValue,
    source_damage_completion: JsonValue = None,
) -> JsonValue:
    payload = cast(
        dict[str, JsonValue],
        {
            "source_kind": DEADLY_DEMISE_SOURCE_KIND,
            "sequence_id": _validate_identifier("sequence_id", sequence_id),
            "attack_context": attack_context,
            "damage_application": damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "source": source.to_payload(),
            "descriptor": validate_json_value(descriptor),
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "trigger_roll": validate_json_value(trigger_roll_payload),
            "affected_target_unit_ids": list(affected_target_unit_ids),
            "pending_target_unit_ids": list(pending_target_unit_ids),
            "pending_sources": [pending_source.to_payload() for pending_source in pending_sources],
            "mortal_wound_roll": validate_json_value(wound_roll_payload),
        },
    )
    if source_damage_completion is not None:
        payload["source_damage_completion"] = validate_json_value(source_damage_completion)
    return validate_json_value(payload)


def deadly_demise_secondary_continuation_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    resolved_secondary_damage_application: DamageApplication,
    resolved_secondary_model_destroyed_event_id: str,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    pending_secondary_damage_applications: tuple[DamageApplication, ...],
    source_damage_completion: JsonValue = None,
) -> JsonValue:
    payload = cast(
        dict[str, JsonValue],
        {
            "source_kind": DEADLY_DEMISE_SOURCE_KIND,
            "continuation_kind": "secondary_destroyed_model_reaction",
            "attack_context": attack_context,
            "damage_application": source_damage.to_payload(),
            "resolved_secondary_damage_application": (
                resolved_secondary_damage_application.to_payload()
            ),
            "resolved_secondary_model_destroyed_event_id": _validate_identifier(
                "resolved_secondary_model_destroyed_event_id",
                resolved_secondary_model_destroyed_event_id,
            ),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "source": source.to_payload(),
            "descriptor": validate_json_value(descriptor),
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "trigger_roll": validate_json_value(trigger_roll_payload),
            "affected_target_unit_ids": list(affected_target_unit_ids),
            "pending_target_unit_ids": list(pending_target_unit_ids),
            "pending_sources": [pending_source.to_payload() for pending_source in pending_sources],
            "pending_secondary_damage_applications": [
                application.to_payload() for application in pending_secondary_damage_applications
            ],
        },
    )
    if source_damage_completion is not None:
        payload["source_damage_completion"] = validate_json_value(source_damage_completion)
    return validate_json_value(payload)


def deadly_demise_secondary_pending_completion_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    resolved_secondary_damage_application: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    pending_secondary_damage_applications: tuple[DamageApplication, ...],
    source_damage_completion: JsonValue = None,
) -> JsonValue:
    payload = _payload_object(
        deadly_demise_secondary_continuation_payload(
            attack_context=attack_context,
            source_damage=source_damage,
            resolved_secondary_damage_application=resolved_secondary_damage_application,
            resolved_secondary_model_destroyed_event_id="pending-model-destruction-event",
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            descriptor=descriptor,
            destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            trigger_roll_payload=trigger_roll_payload,
            affected_target_unit_ids=affected_target_unit_ids,
            pending_target_unit_ids=pending_target_unit_ids,
            pending_sources=pending_sources,
            pending_secondary_damage_applications=pending_secondary_damage_applications,
            source_damage_completion=source_damage_completion,
        )
    )
    payload["continuation_kind"] = "secondary_destroyed_model_mandatory_reaction"
    payload.pop("resolved_secondary_model_destroyed_event_id")
    return validate_json_value(payload)


def deadly_demise_secondary_continuation_after_mandatory_reaction(
    *,
    pending_completion: JsonValue,
    resolved_secondary_model_destroyed_event_id: str,
) -> JsonValue:
    payload = dict(_payload_object(pending_completion))
    expected_fields = {
        "source_kind",
        "continuation_kind",
        "attack_context",
        "damage_application",
        "resolved_secondary_damage_application",
        "saving_throw",
        "feel_no_pain",
        "source",
        "descriptor",
        "destroyed_model_controller_player_id",
        "trigger_roll",
        "affected_target_unit_ids",
        "pending_target_unit_ids",
        "pending_sources",
        "pending_secondary_damage_applications",
    }
    if "source_damage_completion" in payload:
        expected_fields.add("source_damage_completion")
    if (
        set(payload) != expected_fields
        or payload.get("source_kind") != DEADLY_DEMISE_SOURCE_KIND
        or payload.get("continuation_kind") != "secondary_destroyed_model_mandatory_reaction"
    ):
        raise GameLifecycleError("Deadly Demise pending completion context drift.")
    payload["continuation_kind"] = "secondary_destroyed_model_reaction"
    payload["resolved_secondary_model_destroyed_event_id"] = _validate_identifier(
        "resolved_secondary_model_destroyed_event_id",
        resolved_secondary_model_destroyed_event_id,
    )
    return validate_json_value(payload)


def is_deadly_demise_continuation(payload: JsonValue) -> bool:
    if payload is None:
        return False
    if not isinstance(payload, dict):
        raise GameLifecycleError("Destruction reaction continuation must be an object.")
    return (
        payload.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND
        and payload.get("continuation_kind") == "secondary_destroyed_model_reaction"
    )


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Deadly Demise continuation must be an object.")
    return payload


__all__ = (
    "deadly_demise_secondary_continuation_after_mandatory_reaction",
    "deadly_demise_secondary_continuation_payload",
    "deadly_demise_secondary_pending_completion_payload",
    "deadly_demise_source_context_payload",
    "is_deadly_demise_continuation",
)
