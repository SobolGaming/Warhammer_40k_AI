from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundary_kinds,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_scoring_transaction_integrity import (
    validate_primary_boundary_transaction_semantics,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def score_primary_objective_control_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> None:
    """Score one authenticated Primary boundary through the shared policy path."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary boundary scoring requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Primary boundary scoring requires an ObjectiveControlRecord.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary boundary end_of_battle must be a bool.")
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Mission scoring requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(mission_setup)
    boundary_kind = (
        PrimaryScoringBoundaryKind.END_OF_BATTLE
        if end_of_battle
        else PrimaryScoringBoundaryKind.ORDINARY
    )
    state_evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
    )
    awards = policies.primary_awards_from_state_evidence(
        record=record,
        authoritative_state=state,
        state_evidence=state_evidence,
    )
    boundary_matches = tuple(
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.objective_control_record_id == record.record_id
        and evidence.scoring_boundary_kind is boundary_kind
    )
    required_boundary_kinds = required_primary_scoring_boundary_kinds(
        policies=policies,
        record=record,
        turn_order=state.turn_order,
    )
    if boundary_kind not in required_boundary_kinds:
        if boundary_matches or awards:
            raise GameLifecycleError("Primary scoring produced state for an inapplicable boundary.")
        return
    if boundary_matches:
        if boundary_matches != (state_evidence,):
            raise GameLifecycleError(
                "Primary scoring boundary already has different state evidence."
            )
        validate_primary_boundary_transaction_semantics(
            state=state,
            evidence=state_evidence,
        )
        return

    evidence_records_before = tuple(state.primary_scoring_state_evidence_records)
    ledgers_before = tuple(state.victory_point_ledgers)
    try:
        record_primary_scoring_state_evidence(state=state, evidence=state_evidence)
        for award in awards:
            state.award_victory_points(award)
        validate_primary_boundary_transaction_semantics(
            state=state,
            evidence=state_evidence,
        )
    except GameLifecycleError:
        state.restore_primary_scoring_boundary_snapshot(
            evidence_records=evidence_records_before,
            victory_point_ledgers=ledgers_before,
        )
        raise


__all__ = ("score_primary_objective_control_boundary",)
