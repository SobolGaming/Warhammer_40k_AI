from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundaries,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    resolve_primary_scoring_boundary_lifecycle,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    bound_primary_scoring_commit_checkpoint,
    emit_primary_scoring_commit_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_scoring_transaction_integrity import (
    validate_primary_boundary_transaction_semantics,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def score_primary_objective_control_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
    event_log: EventLog | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    """Complete each required player commit for an atomic engine scoring operation."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary boundary scoring requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Primary boundary scoring requires an ObjectiveControlRecord.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary boundary end_of_battle must be a bool.")
    if event_log is not None and type(event_log) is not EventLog:
        raise GameLifecycleError("Primary boundary scoring event_log must be EventLog.")
    if state.mission_setup is None:
        raise GameLifecycleError("Mission scoring requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    kind = (
        PrimaryScoringBoundaryKind.END_OF_BATTLE
        if end_of_battle
        else PrimaryScoringBoundaryKind.ORDINARY
    )
    from warhammer40k_core.engine.mission_scoring_transaction import (
        capture_mission_scoring_aggregate,
        restore_mission_scoring_aggregate,
    )

    snapshot = capture_mission_scoring_aggregate(state=state, event_log=event_log)
    try:
        for boundary_kind, player_id in required_primary_scoring_boundaries(
            policies=policies, record=record, turn_order=state.turn_order
        ):
            if boundary_kind is kind:
                score_primary_player_boundary(
                    state=state,
                    record=record,
                    scoring_player_id=player_id,
                    end_of_battle=end_of_battle,
                    event_log=event_log,
                    runtime_modifier_registry=runtime_modifier_registry,
                )
    except GameLifecycleError:
        restore_mission_scoring_aggregate(state=state, event_log=event_log, snapshot=snapshot)
        raise


def score_primary_player_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    scoring_player_id: str,
    end_of_battle: bool,
    event_log: EventLog | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    """Commit the selected player's mission with its own authenticated checkpoint."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary boundary scoring requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Primary boundary scoring requires an ObjectiveControlRecord.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary boundary end_of_battle must be a bool.")
    if event_log is not None and type(event_log) is not EventLog:
        raise GameLifecycleError("Primary boundary scoring event_log must be EventLog.")
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Mission scoring requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(mission_setup)
    if scoring_player_id not in state.player_ids:
        raise GameLifecycleError("Primary scoring player is not part of this game.")
    boundary_kind = (
        PrimaryScoringBoundaryKind.END_OF_BATTLE
        if end_of_battle
        else PrimaryScoringBoundaryKind.ORDINARY
    )
    required_boundaries = required_primary_scoring_boundaries(
        policies=policies,
        record=record,
        turn_order=state.turn_order,
    )
    boundary_matches = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.objective_control_record_id == record.record_id
        and evidence.scoring_boundary_kind is boundary_kind
        and evidence.scoring_player_id == scoring_player_id
    )
    if boundary_matches:
        if (boundary_kind, scoring_player_id) not in required_boundaries:
            raise GameLifecycleError("Primary scoring produced state for an inapplicable boundary.")
        if len(boundary_matches) != 1:
            raise GameLifecycleError(
                "Primary scoring boundary already has different state evidence."
            )
        validate_primary_boundary_transaction_semantics(
            state=state,
            evidence=boundary_matches[0],
        )
        return

    if (boundary_kind, scoring_player_id) not in required_boundaries:
        raise GameLifecycleError("Primary scoring player has no rule at this boundary.")

    scoring_commit_checkpoint = bound_primary_scoring_commit_checkpoint(
        state=state,
        scoring_player_id=scoring_player_id,
        record=record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    state_evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
        scoring_player_id=scoring_player_id,
        scoring_commit_checkpoint=scoring_commit_checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    awards = policies.primary_awards_from_state_evidence(
        record=record,
        authoritative_state=state,
        state_evidence=state_evidence,
    )
    from warhammer40k_core.engine.mission_scoring_transaction import (
        capture_mission_scoring_aggregate,
        restore_mission_scoring_aggregate,
    )

    snapshot = capture_mission_scoring_aggregate(state=state, event_log=event_log)
    try:
        if event_log is not None:
            emit_primary_scoring_commit_checkpoint(
                event_log=event_log,
                objective_control_record_id=record.record_id,
                scoring_boundary_kind=boundary_kind.value,
                scoring_player_id=scoring_player_id,
                checkpoint=scoring_commit_checkpoint,
            )
        record_primary_scoring_state_evidence(
            state=state,
            evidence=state_evidence,
            scoring_commit_checkpoint=scoring_commit_checkpoint,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        for award in awards:
            state.award_victory_points(award)
        validate_primary_boundary_transaction_semantics(
            state=state,
            evidence=state_evidence,
        )
        resolve_primary_scoring_boundary_lifecycle(
            state=state,
            record=record,
            scoring_boundary_kind=boundary_kind,
            scoring_player_id=scoring_player_id,
            scoring_commit_checkpoint_id=state_evidence.scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=state_evidence.scoring_commit_checkpoint_hash,
            evidence_id=state_evidence.evidence_id,
        )
    except GameLifecycleError:
        restore_mission_scoring_aggregate(state=state, event_log=event_log, snapshot=snapshot)
        raise


__all__ = ("score_primary_objective_control_boundary", "score_primary_player_boundary")
