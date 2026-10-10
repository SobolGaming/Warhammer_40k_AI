"""Authenticate existing scoring checkpoints for exact physical-history anchors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.objective_control_record_authority import (
    objective_control_record_hash,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import PrimaryScoringBoundaryStatus
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_BOUNDARY_KIND,
    primary_scoring_commit_checkpoint_from_events,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringBoundaryKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def authenticated_scoring_commit_checkpoint(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    anchor_index: int,
) -> PrimaryMissionBoundaryCheckpoint:
    event = event_records[anchor_index]
    if event.event_id != f"event-{anchor_index + 1:06d}":
        raise GameLifecycleError("Primary scoring-commit physical anchor event order drifted.")
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Primary scoring-commit physical anchor payload is invalid.")
    raw_record_id = event.payload.get("objective_control_record_id")
    raw_boundary_kind = event.payload.get("scoring_boundary_kind")
    scoring_player_id = event.payload.get("scoring_player_id")
    if type(scoring_player_id) is not str or scoring_player_id not in state.player_ids:
        raise GameLifecycleError("Primary scoring-commit physical anchor player drifted.")
    if type(raw_record_id) is not str or not raw_record_id:
        raise GameLifecycleError(
            "Primary scoring-commit physical anchor record identity is invalid."
        )
    if raw_boundary_kind not in {
        PrimaryScoringBoundaryKind.ORDINARY.value,
        PrimaryScoringBoundaryKind.END_OF_BATTLE.value,
    }:
        raise GameLifecycleError("Primary scoring-commit physical anchor boundary kind is invalid.")
    boundary_kind = PrimaryScoringBoundaryKind(raw_boundary_kind)
    bound_index, checkpoint = primary_scoring_commit_checkpoint_from_events(
        event_records=event_records,
        objective_control_record_id=raw_record_id,
        scoring_boundary_kind=boundary_kind.value,
        scoring_player_id=scoring_player_id,
    )
    if bound_index != anchor_index:
        raise GameLifecycleError("Primary scoring-commit physical anchor occurrence drifted.")
    records = tuple(
        record for record in state.objective_control_records if record.record_id == raw_record_id
    )
    if len(records) != 1:
        raise GameLifecycleError(
            "Primary scoring-commit physical anchor Objective Control record drifted."
        )
    record = records[0]
    evidences = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.objective_control_record_id == raw_record_id
        and evidence.scoring_boundary_kind is boundary_kind
        and evidence.scoring_player_id == scoring_player_id
    )
    lifecycles = tuple(
        lifecycle
        for lifecycle in state.primary_scoring_boundary_lifecycles
        if lifecycle.objective_control_record_id == raw_record_id
        and lifecycle.scoring_boundary_kind is boundary_kind
        and lifecycle.scoring_player_id == scoring_player_id
    )
    if len(evidences) != 1 or len(lifecycles) != 1:
        raise GameLifecycleError(
            "Primary scoring-commit physical anchor retained authority drifted."
        )
    evidence = evidences[0]
    lifecycle = lifecycles[0]
    if (
        lifecycle.status is not PrimaryScoringBoundaryStatus.RESOLVED
        or lifecycle.scoring_commit_checkpoint_id != checkpoint.checkpoint_id
        or lifecycle.scoring_commit_checkpoint_hash != checkpoint.checkpoint_hash
        or evidence.scoring_commit_checkpoint_id != checkpoint.checkpoint_id
        or evidence.scoring_commit_checkpoint_hash != checkpoint.checkpoint_hash
        or evidence.objective_control_record_hash != objective_control_record_hash(record)
    ):
        raise GameLifecycleError("Primary scoring-commit physical anchor hash binding drifted.")
    if (
        checkpoint.boundary_kind != PRIMARY_SCORING_COMMIT_BOUNDARY_KIND
        or checkpoint.game_id != record.game_id
        or checkpoint.player_id != record.active_player_id
        or checkpoint.active_player_id != record.active_player_id
        or checkpoint.battle_round != record.battle_round
        or checkpoint.phase != record.phase
        or checkpoint.battlefield_id != record.battlefield_id
        or evidence.game_id != record.game_id
        or evidence.active_player_id != record.active_player_id
        or evidence.battle_round != record.battle_round
        or evidence.phase != record.phase
        or evidence.battlefield_id != record.battlefield_id
    ):
        raise GameLifecycleError("Primary scoring-commit physical anchor context drifted.")
    return checkpoint
