from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundary_kinds,
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
    """Score one authenticated Primary boundary through the shared policy path."""
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
    boundary_kind = (
        PrimaryScoringBoundaryKind.END_OF_BATTLE
        if end_of_battle
        else PrimaryScoringBoundaryKind.ORDINARY
    )
    required_boundary_kinds = required_primary_scoring_boundary_kinds(
        policies=policies,
        record=record,
        turn_order=state.turn_order,
    )
    boundary_matches = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.objective_control_record_id == record.record_id
        and evidence.scoring_boundary_kind is boundary_kind
    )
    if boundary_matches:
        if boundary_kind not in required_boundary_kinds:
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

    scoring_commit_checkpoint = bound_primary_scoring_commit_checkpoint(
        state=state,
        record=record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    state_evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
        scoring_commit_checkpoint=scoring_commit_checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    awards = policies.primary_awards_from_state_evidence(
        record=record,
        authoritative_state=state,
        state_evidence=state_evidence,
    )
    if boundary_kind not in required_boundary_kinds:
        if awards:
            raise GameLifecycleError("Primary scoring produced state for an inapplicable boundary.")
        return

    evidence_records_before = tuple(state.primary_scoring_state_evidence_records)
    ledgers_before = tuple(state.victory_point_ledgers)
    lifecycles_before = tuple(state.primary_scoring_boundary_lifecycles)
    event_records_before = None if event_log is None else event_log.records
    try:
        if event_log is not None:
            emit_primary_scoring_commit_checkpoint(
                event_log=event_log,
                objective_control_record_id=record.record_id,
                scoring_boundary_kind=boundary_kind.value,
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
            scoring_commit_checkpoint_id=state_evidence.scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=state_evidence.scoring_commit_checkpoint_hash,
            evidence_id=state_evidence.evidence_id,
        )
    except GameLifecycleError:
        from warhammer40k_core.engine.mission_scoring_transaction import (
            MissionScoringAggregateSnapshot,
        )

        state.restore_mission_scoring_aggregate(
            MissionScoringAggregateSnapshot(
                objective_control_records=tuple(state.objective_control_records),
                objective_control_record_authorities=tuple(
                    state.objective_control_record_authorities
                ),
                sticky_objective_control_states=tuple(state.sticky_objective_control_states),
                primary_scoring_state_evidence_records=evidence_records_before,
                secondary_scoring_state_evidence_records=tuple(
                    state.secondary_scoring_state_evidence_records
                ),
                victory_point_ledgers=ledgers_before,
                secondary_mission_card_states=tuple(state.secondary_mission_card_states),
                primary_scoring_boundary_lifecycles=lifecycles_before,
                event_records=(),
            )
        )
        if event_log is not None and event_records_before is not None:
            event_log.replace_records(event_records_before)
        raise


__all__ = ("score_primary_objective_control_boundary",)
