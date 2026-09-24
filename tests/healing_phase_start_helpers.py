"""Explicit real timing boundaries for focused healing fixtures."""

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
from warhammer40k_core.engine.timing_window_events import record_timing_window_boundary


def record_healing_phase_start(*, state: GameState, decisions: DecisionController) -> None:
    record_timing_window_boundary(
        decisions=decisions,
        window=phase_start_context(state).timing_window,
        completed=False,
    )


def wound_model_for_healing_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    target_unit_id: str,
    model_id: str,
) -> None:
    """Record one real pre-phase mortal wound, including its allocation decision."""
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        continue_mortal_wound_application,
    )
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import resolve_mortal_wound_decision
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    phase = state.current_battle_phase
    assert phase is not None
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    identity = f"fixture-wound:{model_id}"
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=f"{identity}:request",
        progress=MortalWoundApplicationProgress.start(
            application_id=identity,
            source_rule_id=identity,
            source_context={"source_kind": "fixture"},
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id="player-b",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=phase,
                source_step="fixture",
            ),
            target_unit_instance_id=target_unit_id,
            defender_player_id=target.owner_player_id,
            mortal_wounds=1,
            spill_over=True,
        ),
    )
    if routed.request is not None:
        request = decisions.request_decision(routed.request)
        result = DecisionResult.for_request(
            request=request,
            result_id=f"{identity}:result",
            selected_option_id=model_id,
        )
        decisions.submit_result(result)
        routed = resolve_mortal_wound_decision(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            next_request_id=f"{identity}:next",
        )
    assert routed.request is None
    assert routed.application is not None
    assert tuple(d.model_instance_id for d in routed.application.applications) == (model_id,)
