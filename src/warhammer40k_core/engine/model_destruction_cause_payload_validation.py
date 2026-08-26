from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseAuthority,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
        MortalWoundApplication,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )


def parse_damage_application(value: JsonValue) -> DamageApplication:
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
        DamageApplicationPayload,
    )

    payload = json_object_value(value, "destruction cause damage application")
    expected_fields = {
        "target_unit_instance_id",
        "model_instance_id",
        "damage_kind",
        "requested_damage",
        "wounds_lost",
        "excess_damage_lost",
        "starting_wounds_remaining",
        "final_wounds_remaining",
        "destroyed",
    }
    if set(payload) != expected_fields:
        raise GameLifecycleError("Destruction cause damage application fields are invalid.")
    try:
        return DamageApplication.from_payload(cast(DamageApplicationPayload, payload))
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Destruction cause damage application is invalid.") from exc


def parse_mortal_wound_application(value: JsonValue) -> MortalWoundApplication:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationPayload,
    )

    payload = json_object_value(value, "mortal-wound destruction application")
    expected_fields = {
        "target_unit_instance_id",
        "mortal_wounds",
        "spill_over",
        "applications",
        "feel_no_pain_resolutions",
        "ignored_mortal_wounds",
        "remaining_mortal_wounds_lost",
    }
    if set(payload) != expected_fields:
        raise GameLifecycleError("Mortal-wound application fields are invalid.")
    try:
        application = MortalWoundApplication.from_payload(
            cast(MortalWoundApplicationPayload, payload)
        )
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Mortal-wound application is invalid.") from exc
    if application.to_payload() != payload:
        raise GameLifecycleError("Mortal-wound application is non-canonical.")
    return application


def parse_mortal_wound_destruction_evidence(
    value: JsonValue,
) -> MortalWoundDestructionEvidence:
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
        MortalWoundDestructionEvidencePayload,
    )

    payload = json_object_value(value, "mortal-wound destruction evidence")
    try:
        evidence = MortalWoundDestructionEvidence.from_payload(
            cast(MortalWoundDestructionEvidencePayload, payload)
        )
    except (KeyError, TypeError) as exc:
        raise GameLifecycleError("Mortal-wound destruction evidence is invalid.") from exc
    if evidence.to_payload() != payload:
        raise GameLifecycleError("Mortal-wound destruction evidence is non-canonical.")
    return evidence


def event_index(
    event_records: tuple[EventRecord, ...],
    requested_event: EventRecord,
) -> int:
    matches = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_id == requested_event.event_id and event == requested_event
    )
    if len(matches) != 1:
        raise GameLifecycleError("Destruction cause event is not exact canonical history.")
    return matches[0]


def json_identifier_list(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{field_name} must be a list.")
    identifiers = tuple(item for item in value if type(item) is str and item)
    if len(identifiers) != len(value):
        raise GameLifecycleError(f"{field_name} must contain identifiers.")
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"{field_name} must contain unique identifiers.")
    return identifiers


def validate_damage_application_identity(
    value: JsonValue,
    *,
    authority: ModelDestructionCauseAuthority,
    damage_kind: str | None,
) -> None:
    damage = json_object_value(value, "destruction cause damage application")
    if (
        damage.get("model_instance_id") != authority.model_instance_id
        or type(damage.get("target_unit_instance_id")) is not str
        or damage.get("destroyed") is not True
        or (damage_kind is not None and damage.get("damage_kind") != damage_kind)
    ):
        raise GameLifecycleError("Destruction cause damage application identity drift.")


def required_destroyed_event(
    authority: ModelDestructionCauseAuthority,
) -> EventRecord:
    event = authority.model_destroyed_event
    if event is None:
        raise GameLifecycleError("Finalized destruction cause lacks model_destroyed consumption.")
    return event


def require_exact_context_fields(
    context: dict[str, JsonValue],
    *,
    expected: set[str],
    cause_kind: str,
) -> None:
    if set(context) != expected:
        raise GameLifecycleError(
            f"{cause_kind} model destruction cause context fields are invalid."
        )


def context_object(
    context: dict[str, JsonValue],
    key: str,
) -> dict[str, JsonValue]:
    return json_object_value(context.get(key), f"model destruction cause {key}")


def json_object_value(value: JsonValue, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def json_identifier(
    value: dict[str, JsonValue],
    key: str,
    field_name: str,
) -> str:
    item = value.get(key)
    if type(item) is not str or not item:
        raise GameLifecycleError(f"{field_name} {key} must be an identifier.")
    return item


__all__ = (
    "context_object",
    "event_index",
    "json_identifier",
    "json_identifier_list",
    "json_object_value",
    "parse_damage_application",
    "parse_mortal_wound_application",
    "parse_mortal_wound_destruction_evidence",
    "require_exact_context_fields",
    "required_destroyed_event",
    "validate_damage_application_identity",
)
