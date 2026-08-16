from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Literal, cast

import pytest
from tests.movement_submission_helpers import submit_default_movement_proposal_if_pending
from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    secondary_choice,
    unit_selection,
    with_model_offsets,
)
from tests.phase13b_shooting_declaration_helpers import (
    proposal_from_request,
    shooting_lifecycle,
)
from tests.phase17n_primary_mission_helpers import phase17n_event_setup

from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockHookBinding,
    BattleShockHookRegistry,
    BattleShockModifierContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_decisions import request_mission_action_opportunity
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseActionKind,
    MovementPhaseHandler,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex

type MovementHistoryKind = Literal["advance", "fall_back"]

_HISTORY_UNIT_ID = "army-beta:intercessor-unit-3"
_ELIGIBLE_UNIT_ID = "army-beta:intercessor-unit-4"


@pytest.mark.parametrize(
    ("history_kind", "expected_message"),
    [
        ("advance", "Primary mission boundary Advance state lacks exact authority"),
        ("fall_back", "Primary mission boundary Fall Back state lacks exact authority"),
    ],
)
def test_phase17n_restore_rejects_coordinated_movement_history_erasure(
    history_kind: MovementHistoryKind,
    expected_message: str,
) -> None:
    state, decisions = _pending_action_opportunity_after_movement(history_kind)
    forged_state = deepcopy(state)
    if history_kind == "advance":
        forged_state.advanced_unit_states = []
    else:
        forged_state.fell_back_unit_states = []

    forged_payload = _payload_with_erased_checkpoint_and_request_history(
        state=forged_state,
        decisions=decisions,
        erased_unit_id=_HISTORY_UNIT_ID,
    )

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(forged_payload)


def test_phase17n_restore_rejects_coordinated_battle_shock_history_erasure() -> None:
    state, decisions = _pending_action_opportunity_after_failed_battle_shock()
    forged_state = deepcopy(state)
    forged_state.battle_shocked_unit_ids = []
    forged_state.battle_shocked_unit_states = []

    forged_payload = _payload_with_erased_checkpoint_and_request_history(
        state=forged_state,
        decisions=decisions,
        erased_unit_id=_HISTORY_UNIT_ID,
    )

    with pytest.raises(
        GameLifecycleError,
        match="Primary mission Battle-shock causal state was erased",
    ):
        GameLifecycle.from_payload(forged_payload)


def test_phase17n_restore_rejects_coordinated_prior_shooting_history_erasure() -> None:
    state, decisions, history_unit_id = _pending_action_opportunity_after_shooting()
    forged_state = deepcopy(state)
    shooting_state = forged_state.shooting_phase_state
    assert shooting_state is not None
    forged_state.replace_shooting_phase_state(
        replace(
            shooting_state,
            shot_unit_ids=tuple(
                unit_id for unit_id in shooting_state.shot_unit_ids if unit_id != history_unit_id
            ),
        )
    )

    forged_payload = _payload_with_erased_checkpoint_and_request_history(
        state=forged_state,
        decisions=decisions,
        erased_unit_id=history_unit_id,
    )

    with pytest.raises(
        GameLifecycleError,
        match="Primary mission boundary shooting state lacks exact authority",
    ):
        GameLifecycle.from_payload(forged_payload)


def _pending_action_opportunity_after_movement(
    history_kind: MovementHistoryKind,
) -> tuple[GameState, DecisionController]:
    state, config = _phase17n_two_unit_state(game_id=f"phase17n-boundary-{history_kind}-history")
    target = _central_objective(state)
    player_b_army = state.army_definition_for_player("player-b")
    assert player_b_army is not None
    history_unit, eligible_unit = player_b_army.units
    assert history_unit.unit_instance_id == _HISTORY_UNIT_ID
    assert eligible_unit.unit_instance_id == _ELIGIBLE_UNIT_ID
    assert state.battlefield_state is not None

    history_placement = state.battlefield_state.unit_placement_by_id(_HISTORY_UNIT_ID)
    eligible_placement = state.battlefield_state.unit_placement_by_id(_ELIGIBLE_UNIT_ID)
    if history_kind == "advance":
        history_offsets = (
            (-2.6, -1.3),
            (-1.3, -1.3),
            (0.0, -1.3),
            (-2.6, 0.0),
            (-1.3, 0.0),
        )
    else:
        history_offsets = (
            (-2.6, -6.0),
            (-1.3, -6.0),
            (0.0, -6.0),
            (-2.6, -4.7),
            (-1.3, -4.7),
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(history_placement, target, offsets=history_offsets)
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            eligible_placement,
            target,
            offsets=(
                (1.3, 0.0),
                (2.6, 0.0),
                (1.3, 1.3),
                (2.6, 1.3),
                (1.3, 2.6),
            ),
        )
    )
    if history_kind == "fall_back":
        player_a_army = state.army_definition_for_player("player-a")
        assert player_a_army is not None
        enemy = player_a_army.units[0]
        enemy_placement = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                enemy_placement,
                target,
                offsets=(
                    (-2.6, -7.3),
                    (-1.3, -7.3),
                    (0.0, -7.3),
                    (-2.6, -8.6),
                    (-1.3, -8.6),
                ),
            )
        )

    decisions = DecisionController()
    handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        stratagem_index=StratagemCatalogIndex.from_records(()),
    )
    lifecycle = GameLifecycle(
        decision_controller=decisions,
        state=state,
        _config=config,
        _movement_phase_handler=handler,
    )
    unit_status = handler.begin_phase(state=state, decisions=decisions)
    unit_request = _request(unit_status.decision_request)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"phase17n-{history_kind}-unit",
            request=unit_request,
            selected_option_id=_HISTORY_UNIT_ID,
        )
    )
    action_request = _request(action_status.decision_request)
    action_option_id = (
        MovementPhaseActionKind.ADVANCE.value
        if history_kind == "advance"
        else next(
            option.option_id
            for option in action_request.options
            if option.option_id.startswith("fall_back:ordered_retreat")
        )
    )
    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"phase17n-{history_kind}-action",
            request=action_request,
            selected_option_id=action_option_id,
        )
    )
    completed_status = submit_default_movement_proposal_if_pending(
        lifecycle,
        proposal_status,
        result_id=f"phase17n-{history_kind}-proposal",
        dx=0.0,
        dy=0.0 if history_kind == "advance" else 6.0,
    )
    assert completed_status.status_kind.value != "invalid"
    assert any(
        event.event_type == "movement_activation_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("movement_phase_action") == history_kind
        for event in decisions.event_log.records
    )
    if history_kind == "advance":
        assert (
            state.advanced_unit_state_for_unit(
                player_id="player-b",
                battle_round=1,
                unit_instance_id=_HISTORY_UNIT_ID,
            )
            is not None
        )
    else:
        assert (
            state.fell_back_unit_state_for_unit(
                player_id="player-b",
                battle_round=1,
                unit_instance_id=_HISTORY_UNIT_ID,
            )
            is not None
        )

    decisions = _without_pending_request_suffix(decisions)
    _enter_shooting(state)
    status = request_mission_action_opportunity(
        state=state,
        decisions=decisions,
        player_id="player-b",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = _request(status.decision_request if status is not None else None)
    assert any(_ELIGIBLE_UNIT_ID in option.option_id for option in request.options)
    assert all(_HISTORY_UNIT_ID not in option.option_id for option in request.options)
    return state, decisions


def _pending_action_opportunity_after_failed_battle_shock() -> tuple[
    GameState,
    DecisionController,
]:
    state, _config = _phase17n_two_unit_state(
        game_id="phase17n-boundary-battle-shock-history",
        single_model_history_unit=True,
    )
    _place_action_units_at_central_objective(state)
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=(
                        replace(
                            unit.own_models[0],
                            wounds_remaining=unit.own_models[0].wounds_remaining - 1,
                        ),
                    ),
                )
                if unit.unit_instance_id == _HISTORY_UNIT_ID
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    decisions = DecisionController()
    hooks = BattleShockHookRegistry.from_bindings(
        (
            BattleShockHookBinding(
                hook_id="phase17n-test-forced-battle-shock",
                source_id="phase17n-test:forced-battle-shock",
                forced_test_handler=_force_history_unit_battle_shock_test,
                modifier_handler=_force_history_unit_battle_shock_failure,
            ),
        )
    )
    status = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        battle_shock_hooks=hooks,
    ).begin_phase(state=state, decisions=decisions)
    assert status.status_kind.value == "advanced"
    assert _HISTORY_UNIT_ID in state.battle_shocked_unit_ids
    resolved = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "battle_shock_test_resolved"
    )
    assert isinstance(resolved.payload, dict)
    result_payload = resolved.payload["battle_shock_result"]
    assert isinstance(result_payload, dict)
    assert result_payload["passed"] is False

    state.replace_command_step_state(None)
    _enter_shooting(state)
    opportunity = request_mission_action_opportunity(
        state=state,
        decisions=decisions,
        player_id="player-b",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = _request(opportunity.decision_request if opportunity is not None else None)
    assert any(_ELIGIBLE_UNIT_ID in option.option_id for option in request.options)
    assert all(_HISTORY_UNIT_ID not in option.option_id for option in request.options)
    return state, decisions


def _pending_action_opportunity_after_shooting() -> tuple[
    GameState,
    DecisionController,
    str,
]:
    lifecycle, units = shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        game_id="phase17n-boundary-shot-history",
    )
    state = cast(GameState, lifecycle.state)
    decisions = lifecycle.decision_controller
    history_unit_id = units["intercessor-1"].unit_instance_id
    eligible_unit_id = units["intercessor-2"].unit_instance_id
    selection_status = lifecycle.advance_until_decision_or_terminal()
    selection_request = _request(selection_status.decision_request)
    type_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17n-shot-unit",
            request=selection_request,
            selected_option_id=history_unit_id,
        )
    )
    type_request = _request(type_status.decision_request)
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    declaration_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17n-shot-type",
            request=type_request,
            selected_option_id=type_request.options[0].option_id,
        )
    )
    declaration_request = _request(declaration_status.decision_request)
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    proposal = proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )
    completed_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17n-shot-declaration",
            request_id=declaration_request.request_id,
            decision_type=declaration_request.decision_type,
            actor_id=declaration_request.actor_id,
            selected_option_id="submit_parameterized_payload",
            payload=validate_json_value(proposal.to_payload()),
        )
    )
    assert completed_status.status_kind.value != "invalid"
    assert state.shooting_phase_state is not None
    assert history_unit_id in state.shooting_phase_state.shot_unit_ids
    assert any(
        event.event_type == "shooting_declaration_accepted" for event in decisions.event_log.records
    )

    decisions = _without_pending_request_suffix(decisions)
    setup = phase17n_event_setup(
        layout_id="priority-assets-vs-priority-assets-layout-1",
        attacker_force_disposition_id="priority-assets",
        defender_force_disposition_id="priority-assets",
    )
    state.mission_setup = setup
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.army_definitions = [
        replace(army, force_disposition_id="priority-assets") for army in state.army_definitions
    ]
    target = _central_objective(state)
    for unit_id, offsets in (
        (
            history_unit_id,
            ((-2.6, -1.3), (-1.3, -1.3), (0.0, -1.3), (-2.6, 0.0), (-1.3, 0.0)),
        ),
        (
            eligible_unit_id,
            ((1.3, 0.0), (2.6, 0.0), (1.3, 1.3), (2.6, 1.3), (1.3, 2.6)),
        ),
    ):
        placement = state.battlefield_state.unit_placement_by_id(unit_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(placement, target, offsets=offsets)
        )
    opportunity = request_mission_action_opportunity(
        state=state,
        decisions=decisions,
        player_id="player-a",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = _request(opportunity.decision_request if opportunity is not None else None)
    assert any(eligible_unit_id in option.option_id for option in request.options)
    assert all(history_unit_id not in option.option_id for option in request.options)
    return state, decisions, history_unit_id


def _phase17n_two_unit_state(
    *,
    game_id: str,
    single_model_history_unit: bool = False,
) -> tuple[GameState, GameConfig]:
    base = phase11c_config()
    player_a_request, player_b_request = base.army_muster_requests
    config = replace(
        base,
        game_id=game_id,
        army_muster_requests=(
            player_a_request,
            replace(
                player_b_request,
                unit_selections=(
                    (
                        unit_selection(
                            unit_selection_id="intercessor-unit-3",
                            datasheet_id="core-character-leader",
                            model_profile_id="core-character-leader",
                            model_count=1,
                        )
                        if single_model_history_unit
                        else default_unit_selection("intercessor-unit-3")
                    ),
                    default_unit_selection("intercessor-unit-4"),
                ),
            ),
        ),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17n-unit-history-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    complete_setup_through_gate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    setup = phase17n_event_setup(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
    )
    state.mission_setup = setup
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                setup.primary_mission_assignment_for_player(army.player_id).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.battle_round = 1
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.replace_command_step_state(None)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    return state, config


def _place_action_units_at_central_objective(state: GameState) -> None:
    assert state.battlefield_state is not None
    target = _central_objective(state)
    history_placement = state.battlefield_state.unit_placement_by_id(_HISTORY_UNIT_ID)
    eligible_placement = state.battlefield_state.unit_placement_by_id(_ELIGIBLE_UNIT_ID)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            history_placement,
            target,
            offsets=(
                (-2.6, -1.3),
                (-1.3, -1.3),
                (0.0, -1.3),
                (-2.6, 0.0),
                (-1.3, 0.0),
            )[: len(history_placement.model_placements)],
        )
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            eligible_placement,
            target,
            offsets=(
                (1.3, 0.0),
                (2.6, 0.0),
                (1.3, 1.3),
                (2.6, 1.3),
                (1.3, 2.6),
            ),
        )
    )


def _force_history_unit_battle_shock_test(
    context: BattleShockForcedTestContext,
) -> tuple[str, ...]:
    assert context.active_player_id == "player-b"
    return (_HISTORY_UNIT_ID,)


def _force_history_unit_battle_shock_failure(
    context: BattleShockModifierContext,
) -> tuple[RollModifier, ...]:
    assert context.request.unit_instance_id == _HISTORY_UNIT_ID
    return (
        RollModifier(
            modifier_id="phase17n-test:battle-shock-minus-five",
            source_id="phase17n-test:forced-battle-shock",
            operand=-5,
        ),
    )


def _payload_with_erased_checkpoint_and_request_history(
    *,
    state: GameState,
    decisions: DecisionController,
    erased_unit_id: str,
) -> GameLifecyclePayload:
    original_request = decisions.queue.pending_requests[0]
    assert original_request.actor_id is not None
    rebuilt_state = deepcopy(state)
    rebuilt_state.decision_request_count -= 1
    rebuilt = DecisionController()
    status = request_mission_action_opportunity(
        state=rebuilt_state,
        decisions=rebuilt,
        player_id=original_request.actor_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    rebuilt_request = _request(status.decision_request if status is not None else None)
    assert any(erased_unit_id in option.option_id for option in rebuilt_request.options)
    assert rebuilt_request.request_id == original_request.request_id
    forged_request = rebuilt_request
    rebuilt_checkpoint = next(
        event
        for event in rebuilt.event_log.records
        if event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    )

    controller_payload = deepcopy(decisions.to_payload())
    controller_payload["queue"]["pending_requests"] = [forged_request.to_payload()]
    for event in controller_payload["event_log"]:
        if event["event_type"] == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT:
            event["payload"] = rebuilt_checkpoint.payload
        elif (
            event["event_type"] == "decision_requested"
            and isinstance(event["payload"], dict)
            and event["payload"].get("request_id") == original_request.request_id
        ):
            event["payload"] = validate_json_value(forged_request.to_payload())
    forged_decisions = DecisionController.from_payload(controller_payload)
    return GameLifecycle(
        decision_controller=forged_decisions,
        state=state,
    ).to_payload()


def _without_pending_request_suffix(decisions: DecisionController) -> DecisionController:
    payload = deepcopy(decisions.to_payload())
    pending = payload["queue"]["pending_requests"]
    assert len(pending) == 1
    request_id = pending[0]["request_id"]
    final_event = payload["event_log"][-1]
    assert final_event["event_type"] == "decision_requested"
    assert isinstance(final_event["payload"], dict)
    assert final_event["payload"].get("request_id") == request_id
    payload["queue"]["pending_requests"] = []
    payload["event_log"].pop()
    return DecisionController.from_payload(payload)


def _enter_shooting(state: GameState) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(
        ShootingPhaseState(battle_round=state.battle_round, active_player_id="player-b")
    )


def _central_objective(state: GameState) -> ObjectiveMarkerDefinition:
    assert state.mission_setup is not None
    return next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )


def _request(request: DecisionRequest | None) -> DecisionRequest:
    assert request is not None
    return request


__all__ = ()
