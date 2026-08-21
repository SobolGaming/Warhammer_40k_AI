from __future__ import annotations

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_decisions import apply_mission_decision
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.secondary_mission_choices import SECONDARY_CHOICE_DECISION_TYPES
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.secondary_when_drawn import (
    RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE,
)

SECONDARY_MISSION_SETUP_DECISION_TYPES = frozenset(
    {
        RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE,
        *SECONDARY_CHOICE_DECISION_TYPES,
    }
)
_SECONDARY_SETUP_DRAIN_LIMIT = 64


def drain_pending_secondary_mission_setup(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id_prefix: str,
) -> LifecycleStatus:
    current = status
    for step_index in range(1, _SECONDARY_SETUP_DRAIN_LIMIT + 1):
        request = current.decision_request
        if request is None or request.decision_type not in SECONDARY_MISSION_SETUP_DECISION_TYPES:
            return current
        if not request.options:
            raise AssertionError("Secondary mission setup request has no options.")
        current = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"{result_id_prefix}-{step_index:02d}",
                request=request,
                selected_option_id=request.options[0].option_id,
            )
        )
    raise AssertionError("Secondary mission setup did not drain.")


def drain_pending_secondary_mission_setup_for_command_handler(
    *,
    handler: CommandPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    result_id_prefix: str,
) -> LifecycleStatus:
    status = handler.begin_phase(state=state, decisions=decisions)
    for step_index in range(1, _SECONDARY_SETUP_DRAIN_LIMIT + 1):
        request = status.decision_request
        if request is None or request.decision_type not in SECONDARY_MISSION_SETUP_DECISION_TYPES:
            return status
        if not request.options:
            raise AssertionError("Secondary mission setup request has no options.")
        result = DecisionResult.for_request(
            result_id=f"{result_id_prefix}-{step_index:02d}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        decisions.submit_result(result)
        apply_mission_decision(
            state=state,
            request=request,
            result=result,
            decisions=decisions,
            runtime_modifier_registry=handler.runtime_modifier_registry,
        )
        status = handler.begin_phase(state=state, decisions=decisions)
    raise AssertionError("Secondary mission setup did not drain.")


def resolved_secondary_mission_selection_for_card(
    state: GameState,
    card: SecondaryMissionCardState,
) -> SecondaryMissionSelection:
    selection = SecondaryMissionSelection().with_when_drawn_resolved()
    if card.secondary_mission_id == "a-tempting-target":
        return selection.with_tempting_objective(_first_tempting_objective_id(state))
    if card.secondary_mission_id == "beacon":
        return selection.with_beacon_unit(
            _first_friendly_placed_unit_id(state, player_id=card.player_id)
        )
    if card.secondary_mission_id == "burden-of-trust":
        if state.mission_setup is None:
            raise AssertionError("Burden of Trust selection requires MissionSetup.")
        return selection.with_guards(
            guarded_objective_unit_ids=(),
            resolved_guard_objective_ids=tuple(
                marker.objective_marker_id for marker in state.mission_setup.objective_markers
            ),
            battle_round=state.battle_round,
        )
    return selection


def seed_resolved_secondary_mission_selections(state: GameState, *, player_id: str) -> None:
    for card in tuple(state.secondary_mission_card_states):
        if (
            card.player_id != player_id
            or card.mode is not SecondaryMissionCardMode.TACTICAL
            or card.status is not SecondaryMissionCardStatus.ACTIVE
        ):
            continue
        state.replace_secondary_mission_card_state(
            card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
        )


def _first_tempting_objective_id(state: GameState) -> str:
    if state.mission_setup is None:
        raise AssertionError("Tempting Target selection requires MissionSetup.")
    for marker in state.mission_setup.objective_markers:
        if marker.objective_role in {
            ObjectiveMarkerRole.CENTRAL,
            ObjectiveMarkerRole.EXPANSION,
        }:
            return marker.objective_marker_id
    raise AssertionError("Tempting Target fixture has no No Man's Land objective.")


def _first_friendly_placed_unit_id(state: GameState, *, player_id: str) -> str:
    if state.battlefield_state is None:
        raise AssertionError("Beacon selection requires battlefield state.")
    for army in state.army_definitions:
        if army.player_id != player_id:
            continue
        for unit in army.units:
            if state.battlefield_state.is_unit_placed(unit.unit_instance_id):
                return unit.unit_instance_id
    raise AssertionError("Beacon fixture has no friendly unit on the battlefield.")
