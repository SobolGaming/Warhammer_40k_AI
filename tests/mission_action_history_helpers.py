"""History for fixtures using the engine's lower-level Action state methods."""

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.boundary_rule_flow import (
    emit_objective_control_boundary,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_turn_end_sequencing import request_mission_turn_end_rules
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def prepare_turn_end_control_for_fixture(
    *, state: GameState, decisions: DecisionController
) -> None:
    """Complete the real phase boundary before a low-level turn scoring fixture."""
    from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
    from warhammer40k_core.engine.battle_round_flow import (
        _END_WINDOW_RESOLUTION_ORDER,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.engine.boundary_rule_flow import (
        prepare_phase_end_boundary,
        prepare_turn_end_control_boundary,
        request_end_rules,
    )
    from warhammer40k_core.engine.boundary_sequencing import boundary_context
    from warhammer40k_core.engine.fight_phase_end_sequencing import complete_fight_phase_boundary
    from warhammer40k_core.engine.timing_window_events import record_timing_window_boundary
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind
    from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry

    fight = state.fight_phase_state
    if fight is None or (fight.battle_round, fight.active_player_id) != (
        state.battle_round,
        state.active_player_id,
    ):
        seed_completed_fight_phase(state)
    registry = RuntimeModifierRegistry.empty()
    prepare_phase_end_boundary(state=state, decisions=decisions, runtime_modifier_registry=registry)
    assert (
        request_end_rules(
            state=state,
            decisions=decisions,
            registry=TurnEndHookRegistry.empty(),
            trigger_kind=TimingTriggerKind.END_PHASE,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
            army_catalog=None,
            runtime_modifier_registry=registry,
            reaction_queue=None,
        )
        is None
    )
    complete_fight_phase_boundary(state=state, decisions=decisions)
    record_timing_window_boundary(
        decisions=decisions,
        window=boundary_context(state, TimingTriggerKind.END_PHASE).timing_window,
        completed=True,
        resolution_order=_END_WINDOW_RESOLUTION_ORDER,
    )
    prepare_turn_end_control_boundary(
        state=state, decisions=decisions, runtime_modifier_registry=registry
    )


def prepare_mission_action_turn_end_for_fixture(
    *, state: GameState, decisions: DecisionController
) -> None:
    prepare_turn_end_control_for_fixture(state=state, decisions=decisions)
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
    )
    emit_objective_control_boundary(decisions=decisions, record=record)


def record_mission_action_terminal_for_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    action: MissionActionState,
    phase: BattlePhase,
) -> None:
    assert state.mission_action_state_by_id(action.action_id) == action
    assert action.status in {MissionActionStatus.COMPLETED, MissionActionStatus.INTERRUPTED}
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": action.player_id,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "mission_action_id": action.mission_action_id,
        "mission_action_state": validate_json_value(action.to_payload()),
    }
    if action.status is MissionActionStatus.COMPLETED:
        event_type = "mission_action_completed"
    else:
        event_type = "mission_action_interrupted"
        payload["interrupted_reason"] = action.interrupted_reason
    decisions.event_log.append(event_type, payload)
    if action.status is MissionActionStatus.COMPLETED and action.completion_timing == "turn_end":
        assert (
            request_mission_turn_end_rules(
                state=state,
                decisions=decisions,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
            is not None
        )


def prepare_retained_turn_end_for_fixture(
    *, state: GameState, decisions: DecisionController
) -> None:
    """Prepare retained control and turn-start evidence for isolated reserve tests."""
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    if not any(
        row.battle_round == state.battle_round and row.player_id == state.active_player_id
        for row in state.primary_objective_turn_start_states
    ):
        record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    prepare_turn_end_control_for_fixture(state=state, decisions=decisions)


def finish_primary_turn_end_for_fixture(*, state: GameState, decisions: DecisionController) -> None:
    """Score the retained boundary after isolated non-mission rules have finished."""
    from warhammer40k_core.engine.primary_scoring_boundary import (
        score_primary_objective_control_boundary,
    )

    for record in state.objective_control_records:
        if (
            record.battle_round == state.battle_round
            and record.active_player_id == state.active_player_id
            and record.phase == BattlePhase.FIGHT.value
        ):
            score_primary_objective_control_boundary(
                state=state, record=record, end_of_battle=False, event_log=decisions.event_log
            )
