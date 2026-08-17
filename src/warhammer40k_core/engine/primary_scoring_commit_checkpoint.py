from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import EventLog, EventRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control import ObjectiveControlRecord

PRIMARY_SCORING_COMMIT_BOUNDARY_KIND = "primary_scoring_commit"
PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT = "primary_scoring_commit_checkpoint_recorded"
_SCORING_COMMIT_EVENT_KEYS = (
    "objective_control_record_id",
    "scoring_boundary_kind",
    "checkpoint",
)
_validate_identifier = IdentifierValidator(GameLifecycleError)


def bound_primary_scoring_commit_checkpoint(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    scoring_commit_checkpoint: PrimaryMissionBoundaryCheckpoint | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> PrimaryMissionBoundaryCheckpoint:
    """Capture or verify the post-window scoring-commit checkpoint for one OC record."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        capture_primary_mission_boundary_checkpoint,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Primary scoring-commit checkpoint requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring-commit checkpoint requires an ObjectiveControlRecord."
        )
    registry = (
        RuntimeModifierRegistry.empty()
        if runtime_modifier_registry is None
        else runtime_modifier_registry
    )
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Primary scoring-commit checkpoint requires RuntimeModifierRegistry."
        )
    captured = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind=PRIMARY_SCORING_COMMIT_BOUNDARY_KIND,
        player_id=record.active_player_id,
        runtime_modifier_registry=registry,
    )
    if scoring_commit_checkpoint is None:
        return captured
    if type(scoring_commit_checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError("Primary scoring-commit checkpoint must be typed.")
    if scoring_commit_checkpoint != captured:
        raise GameLifecycleError(
            "Primary scoring-commit checkpoint drifted from current authoritative state."
        )
    return captured


def emit_primary_scoring_commit_checkpoint(
    *,
    event_log: EventLog,
    objective_control_record_id: str,
    scoring_boundary_kind: str,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    from warhammer40k_core.engine.event_log import EventLog

    if type(event_log) is not EventLog:
        raise GameLifecycleError("Primary scoring-commit event requires EventLog.")
    record_id = _validate_identifier(
        "Primary scoring-commit objective_control_record_id",
        objective_control_record_id,
    )
    kind = _validate_identifier(
        "Primary scoring-commit scoring_boundary_kind",
        scoring_boundary_kind,
    )
    if type(checkpoint) is not PrimaryMissionBoundaryCheckpoint:
        raise GameLifecycleError("Primary scoring-commit event requires a typed checkpoint.")
    if checkpoint.boundary_kind != PRIMARY_SCORING_COMMIT_BOUNDARY_KIND:
        raise GameLifecycleError("Primary scoring-commit event kind drifted.")
    matches = tuple(
        _scoring_commit_binding(event)
        for event in event_log.records
        if event.event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
        and _scoring_commit_binding(event)[0] == record_id
        and _scoring_commit_binding(event)[1] == kind
    )
    if len(matches) > 1:
        raise GameLifecycleError("Primary scoring-commit checkpoint event is duplicated.")
    if matches:
        if matches[0][2] != checkpoint:
            raise GameLifecycleError("Primary scoring-commit checkpoint event drifted.")
        return
    event_log.append(
        PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
        {
            "objective_control_record_id": record_id,
            "scoring_boundary_kind": kind,
            "checkpoint": checkpoint.to_payload(),
        },
    )


def primary_scoring_commit_checkpoint_from_events(
    *,
    event_records: tuple[EventRecord, ...],
    objective_control_record_id: str,
    scoring_boundary_kind: str,
) -> tuple[int, PrimaryMissionBoundaryCheckpoint]:
    record_id = _validate_identifier(
        "Primary scoring-commit objective_control_record_id",
        objective_control_record_id,
    )
    kind = _validate_identifier(
        "Primary scoring-commit scoring_boundary_kind",
        scoring_boundary_kind,
    )
    matches: list[tuple[int, PrimaryMissionBoundaryCheckpoint]] = []
    for index, event in enumerate(event_records):
        if event.event_type != PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT:
            continue
        bound_record_id, bound_kind, checkpoint = _scoring_commit_binding(event)
        if bound_record_id == record_id and bound_kind == kind:
            matches.append((index, checkpoint))
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary scoring position evidence requires exactly one scoring-commit checkpoint."
        )
    return matches[0]


def _scoring_commit_binding(
    event: EventRecord,
) -> tuple[str, str, PrimaryMissionBoundaryCheckpoint]:
    from warhammer40k_core.engine.event_log import EventRecord

    if type(event) is not EventRecord:
        raise GameLifecycleError("Primary scoring-commit event must be typed.")
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary scoring-commit event payload must be an object.")
    raw = cast(dict[str, object], event.payload)
    missing = [key for key in _SCORING_COMMIT_EVENT_KEYS if key not in raw]
    if missing:
        raise GameLifecycleError(
            f"Primary scoring-commit event payload is missing required field: {missing[0]}."
        )
    unexpected = tuple(sorted(set(raw).difference(_SCORING_COMMIT_EVENT_KEYS)))
    if unexpected:
        raise GameLifecycleError(
            f"Primary scoring-commit event payload contains unexpected field: {unexpected[0]}."
        )
    record_id = _validate_identifier(
        "Primary scoring-commit objective_control_record_id",
        raw["objective_control_record_id"],
    )
    kind = _validate_identifier(
        "Primary scoring-commit scoring_boundary_kind",
        raw["scoring_boundary_kind"],
    )
    return (
        record_id,
        kind,
        PrimaryMissionBoundaryCheckpoint.from_payload(raw["checkpoint"]),
    )


__all__ = (
    "PRIMARY_SCORING_COMMIT_BOUNDARY_KIND",
    "PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT",
    "bound_primary_scoring_commit_checkpoint",
    "emit_primary_scoring_commit_checkpoint",
    "primary_scoring_commit_checkpoint_from_events",
)
