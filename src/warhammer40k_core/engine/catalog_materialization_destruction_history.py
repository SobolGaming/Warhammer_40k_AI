from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
    MortalWoundDestructionEvidence,
    MortalWoundDestructionEvidencePayload,
    MortalWoundDestructionFinalizationKind,
    mortal_wound_destruction_finalization_kind_from_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_materialization_destruction_history(events: tuple[EventRecord, ...]) -> None:
    """Bind completion summaries to the casualties that actually produced them."""
    by_id = {event.event_id: (index, event) for index, event in enumerate(events)}
    if len(by_id) != len(events):
        raise GameLifecycleError("Catalog materialization event identities are duplicated.")
    completions: dict[str, dict[str, JsonValue]] = {}
    for index, event in enumerate(events):
        if event.event_type != MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT:
            continue
        payload = _object(event.payload)
        context = _object(payload.get("source_context"))
        kind = mortal_wound_destruction_finalization_kind_from_event(event)
        evidence = MortalWoundDestructionEvidence.from_payload(
            cast(
                MortalWoundDestructionEvidencePayload, _object(payload.get("destruction_evidence"))
            )
        )
        application_id = _identifier(payload.get("application_id"))
        if application_id in completions:
            raise GameLifecycleError("Catalog materialization destruction evidence drift.")
        model_ids = _identifiers(payload.get("destroyed_model_instance_ids"))
        event_ids = _identifiers(payload.get("model_destroyed_event_ids"))
        if len(model_ids) != len(event_ids):
            raise GameLifecycleError("Catalog materialization destruction evidence drift.")
        for model_id, event_id in zip(model_ids, event_ids, strict=True):
            if event_id not in by_id:
                raise GameLifecycleError("Catalog materialization destruction evidence drift.")
            source_index, source = by_id[event_id]
            casualty = _object(source.payload)
            producer_matches = (
                casualty.get("mortal_wound_application_id") == application_id
                and casualty.get("source_rule_id") == payload.get("source_rule_id")
                and casualty.get("source_context") == context
                if kind is MortalWoundDestructionFinalizationKind.APPLICATION_PACKET
                else context.get("model_destroyed_event_id") == event_id and len(event_ids) == 1
            )
            if (
                source_index >= index
                or source.event_type != "model_destroyed"
                or casualty.get("model_instance_id") != model_id
                or not producer_matches
                or casualty.get("sequence_id") != context.get("sequence_id")
                or ModelDestructionAttribution.from_model_destroyed_payload(casualty)
                != evidence.destruction_attribution
            ):
                raise GameLifecycleError("Catalog materialization destruction evidence drift.")
        completions[application_id] = payload
    for event in events:
        if event.event_type != "hazardous_mortal_wounds_applied":
            continue
        payload = _object(event.payload)
        application = payload.get("mortal_wound_application")
        if not isinstance(application, dict):
            raise GameLifecycleError("Catalog materialization Hazardous evidence is malformed.")
        applications = application.get("applications")
        if not isinstance(applications, list):
            raise GameLifecycleError("Catalog materialization Hazardous evidence is malformed.")
        for damage in applications:
            if not isinstance(damage, dict):
                raise GameLifecycleError("Catalog materialization Hazardous evidence is malformed.")
            if damage.get("destroyed") is True and type(damage.get("model_instance_id")) is not str:
                raise GameLifecycleError(
                    "Catalog materialization model_instance_id must be a string."
                )
        sequence_id = _identifier(payload.get("sequence_id"))
        completion = completions.get(f"{sequence_id}:hazardous:mortal-wounds")
        if completion is None or completion.get("application") != application:
            raise GameLifecycleError("Catalog materialization destruction evidence drift.")
        context = _object(completion.get("source_context"))
        if any(
            payload.get(field) != context.get(field)
            for field in (
                "sequence_id",
                "attacking_unit_instance_id",
                "source_phase",
                "hazardous_weapon_instance_ids",
                "hazardous_weapon_profile_ids",
                "failed_hazardous_weapon_instance_ids",
                "hazardous_roll_state",
                "mortal_wounds_per_failed_roll",
                "mortal_wounds",
            )
        ):
            raise GameLifecycleError("Catalog materialization destruction evidence drift.")


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog materialization mortal-wound evidence is malformed.")
    return value


def _identifier(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError("Catalog materialization destruction evidence drift.")
    return value


def _identifiers(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError("Catalog materialization destruction evidence drift.")
    identifiers = tuple(_identifier(item) for item in value)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError("Catalog materialization destruction evidence drift.")
    return identifiers
