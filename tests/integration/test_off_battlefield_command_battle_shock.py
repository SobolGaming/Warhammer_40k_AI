from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    secondary_choice,
    unit_by_id,
    unit_selection,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
    BattleShockTestReason,
    BattleShockTestRequest,
    collect_battle_shock_test_requests,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockRerollPermissionContext,
    HistoricalBattleShockContribution,
)
from warhammer40k_core.engine.battle_shock_model_authority import battle_shock_model_ids
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentBundle,
    RuntimeContentContribution,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.reserve_arrival_requirements import reposition_destruction_policy
from warhammer40k_core.engine.reserves import (
    ReserveOrigin,
    StrategicReserveDeclaration,
)
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked, rules_unit_view_by_id
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.transports import TransportCapacityProfile
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext


def _command_fixture(
    *,
    location: str,
    remaining: int,
    shocked: bool = False,
    attached: bool = False,
    single: bool = False,
) -> tuple[GameConfig, GameState, DecisionController, str]:
    single_profile = "core-vehicle-monster" if location == "reserves" else "core-character-leader"
    target = (
        unit_selection(
            unit_selection_id="target",
            datasheet_id=single_profile,
            model_profile_id=single_profile,
            model_count=1,
        )
        if single
        else default_unit_selection("target")
    )
    leader = unit_selection(
        unit_selection_id="leader",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    config = phase11c_config(
        game_id=f"p01-{location}-{remaining}-{shocked}-{attached}-{single}",
        player_a_units=(
            target,
            default_unit_selection("healthy"),
            unit_selection(
                unit_selection_id="transport",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
            *((leader,) if attached else ()),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader",
                bodyguard_unit_selection_id="target",
            ),
        )
        if attached
        else (),
    )
    state = GameState.from_config(config)
    decisions = DecisionController()
    for army in mustered_armies(config):
        state.record_army_definition(army)
    target_unit = unit_by_id(state, "army-alpha:target")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit.unit_instance_id)
    unit_id = rules_unit.unit_instance_id
    if location == "reserves":
        reserve_states = state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration(
                    unit_instance_id=unit_id,
                    player_id="player-a",
                    unit_points=100,
                    reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
                    declared_during_step="declare_battle_formations",
                    embarked_unit_points=0,
                    points_limit=1000,
                ),
            ),
            destruction_deadline_policy=reposition_destruction_policy(
                mission_setup=state.mission_setup,
                destruction_deadline_policy=None,
            ),
        )
        for reserve_state in reserve_states:
            decisions.event_log.append(
                "reserve_unit_declared",
                {
                    "game_id": state.game_id,
                    "player_id": "player-a",
                    "unit_instance_id": unit_id,
                    "reserve_state": reserve_state.to_payload(),
                },
            )
    elif location == "embarked":
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id="army-alpha:transport",
            embarked_unit_instance_ids=rules_unit.component_unit_instance_ids,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
        )
    else:
        raise AssertionError(location)
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id="p01-battlefield",
        armies=tuple(state.army_definitions),
    ).battlefield_state
    for component_id in rules_unit.component_unit_instance_ids:
        battlefield = battlefield.without_unit_placement(component_id)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
            )
        )
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    if single:
        model = target_unit.own_models[0]
        if model.wounds_remaining != remaining:
            apply_damage_to_model(
                state=state,
                target_unit_instance_id=unit_id,
                model_instance_id=model.model_instance_id,
                damage=model.wounds_remaining - remaining,
                damage_kind=DamageKind.NORMAL,
                remove_destroyed_model=False,
            )
    else:
        for model in rules_unit.alive_models()[: len(rules_unit.alive_models()) - remaining]:
            apply_damage_to_model(
                state=state,
                target_unit_instance_id=unit_id,
                model_instance_id=model.model_instance_id,
                damage=model.wounds_remaining,
                damage_kind=DamageKind.NORMAL,
                remove_destroyed_model=False,
            )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_unplaced_models_marked_removed(
        tuple(
            model.model_instance_id
            for component in rules_unit_view_by_id(state=state, unit_instance_id=unit_id).components
            for model in component.unit.own_models
            if not model.is_alive
        )
    )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    if shocked:
        request = BattleShockTestRequest.for_unit(
            request_id="p01-existing-shock",
            game_id=state.game_id,
            battle_round=1,
            player_id="player-a",
            unit_instance_id=unit_id,
            reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
            leadership_target=6,
            below_half_strength_context=BelowHalfStrengthContext.from_rules_unit(
                rules_unit=rules_unit,
                starting_strength=state.starting_strength_record_for_unit(unit_id),
                current_model_ids=tuple(
                    model.model_instance_id for model in rules_unit.alive_models()
                ),
            ),
        )
        state.record_battle_shock_result(
            BattleShockResult.from_roll_state(
                result_id="p01-existing-shock-result",
                request=request,
                roll_state=DiceRollManager("p01-existing-shock").roll_fixed(request.spec, [1, 1]),
            )
        )
    return config, state, decisions, unit_id


@pytest.mark.parametrize("location", ["embarked", "reserves"])
@pytest.mark.parametrize(
    ("remaining", "shocked", "required"),
    [
        (5, False, False),
        (5, True, True),
        (2, False, True),
        (2, True, True),
        (0, False, False),
    ],
)
def test_command_collection_counts_living_off_battlefield_units_once(
    location: str,
    remaining: int,
    shocked: bool,
    required: bool,
) -> None:
    _, state, _, unit_id = _command_fixture(location=location, remaining=remaining, shocked=shocked)
    army = state.army_definition_for_player("player-a")
    assert army is not None
    assert state.battlefield_state is not None
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        army=army,
        battlefield_state=state.battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        state=state,
    )
    assert tuple(request.unit_instance_id for request in requests) == (
        (unit_id,) if required else ()
    )
    if required:
        assert requests[0].reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
        assert requests[0].below_half_strength_context.current_model_count == remaining


@pytest.mark.parametrize("location", ["embarked", "reserves"])
def test_off_battlefield_models_do_not_gain_non_command_battle_shock_authority(
    location: str,
) -> None:
    _, state, _, unit_id = _command_fixture(location=location, remaining=2)
    assert state.battlefield_state is not None
    with pytest.raises(GameLifecycleError, match="every alive model"):
        battle_shock_model_ids(
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
            battlefield=state.battlefield_state,
            state=state,
            allow_off_battlefield=False,
        )


@pytest.mark.parametrize(
    ("location", "remaining", "shocked", "attached", "single"),
    [
        ("embarked", 2, False, False, False),
        ("reserves", 2, False, False, False),
        ("embarked", 3, False, True, False),
        ("embarked", 1, False, True, False),
        ("embarked", 2, False, False, True),
        ("reserves", 2, False, False, True),
        ("reserves", 6, False, False, True),
    ],
)
def test_off_battlefield_command_facade_restore_replay_and_public_events(
    location: str,
    remaining: int,
    shocked: bool,
    attached: bool,
    single: bool,
) -> None:
    config, state, decisions, unit_id = _command_fixture(
        location=location,
        remaining=remaining,
        shocked=shocked,
        attached=attached,
        single=single,
    )
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    session = LocalGameSession(lifecycle=lifecycle)
    cursor = EventStreamCursor(len(decisions.event_log.records))
    status = session.advance_until_decision_or_terminal()
    for index in range(8):
        assert lifecycle.state is not None
        if lifecycle.state.current_battle_phase is not BattlePhase.COMMAND:
            break
        request = status.decision_request
        assert request is not None
        assert request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        snapshot = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
        assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=stratagem_decline_payload(),
            result_id=f"p01-decline-{index}",
        )
    else:
        pytest.fail("Command step did not complete.")
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    resolved = [
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "battle_shock_test_resolved"
    ]
    assert len(resolved) == 1
    payload = resolved[0]
    assert isinstance(payload, dict)
    result_payload = payload["battle_shock_result"]
    assert isinstance(result_payload, dict)
    result = BattleShockResult.from_payload(cast(BattleShockResultPayload, result_payload))
    assert result.request.unit_instance_id == unit_id
    assert result.request.below_half_strength_context.current_model_count == (
        1 if single else remaining
    )
    assert rules_unit_is_battle_shocked(state=lifecycle.state, unit_instance_id=unit_id) is (
        not result.passed
    )
    assert lifecycle.state.battlefield_state == state.battlefield_state
    final = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(final).to_payload() == final
    left = session.events_since(cursor, viewer_player_id="player-a")
    right = session.events_since(cursor, viewer_player_id="player-b")
    relevant = {
        "battle_shock_test_requested",
        "battle_shock_test_resolved",
        "battle_shock_step_completed",
    }
    assert [row for row in left["events"] if row["event_type"] in relevant] == [
        row for row in right["events"] if row["event_type"] in relevant
    ]
    artifact = session.replay_artifact(artifact_id="replay:p01-off-battlefield")
    assert ReplayRunner.from_payload(artifact).run().status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize("location", ["embarked", "reserves"])
@pytest.mark.parametrize("option_id", ["decline", "reroll:0,1"])
def test_off_battlefield_reroll_restores_and_rejects_stale_presence_before_queue_pop(
    location: str,
    option_id: str,
) -> None:
    config, state, decisions, _unit_id = _command_fixture(location=location, remaining=2)

    def permission(context: BattleShockRerollPermissionContext) -> RerollPermission:
        return RerollPermission(
            source_id="p01:test:reroll",
            timing_window="battle_shock_test",
            owning_player_id=context.request.player_id,
            eligible_roll_type=context.request.spec.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )

    armies = tuple(state.army_definitions)
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(armies=armies, catalog=config.army_catalog),
        armies=armies,
        catalog=config.army_catalog,
        contributions=(
            RuntimeContentContribution(
                contribution_id="p01:test:reroll-contribution",
                battle_shock_hook_bindings=(
                    BattleShockHookBinding(
                        hook_id="p01:test:reroll",
                        source_id="p01:test:reroll",
                        reroll_permission_handler=permission,
                        historical_contribution_handler=lambda context: (
                            HistoricalBattleShockContribution(
                                reroll_permission=RerollPermission(
                                    source_id="p01:test:reroll",
                                    timing_window="battle_shock_test",
                                    owning_player_id=context.request.player_id,
                                    eligible_roll_type=context.request.spec.roll_type,
                                    component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
                                ),
                            )
                        ),
                    ),
                ),
            ),
        ),
    )
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        },
        runtime_content_bundle=bundle,
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=stratagem_decline_payload(),
            result_id="p01-reroll-decline-stratagem",
        )
        request = status.decision_request
        assert request is not None
    assert request.decision_type == DICE_REROLL_DECISION_TYPE
    snapshot = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    restored = GameLifecycle.from_payload(snapshot, runtime_content_bundle=bundle)
    assert restored.to_payload() == snapshot
    with pytest.raises(GameLifecycleError, match="pending request"):
        session.submit_option(request_id="stale", option_id=option_id, result_id="p01-stale")
    with pytest.raises(DecisionError):
        session.submit_option(
            request_id=request.request_id, option_id="malformed", result_id="p01-bad"
        )
    assert lifecycle.to_payload() == snapshot
    result = DecisionResult.for_request(
        result_id="p01-reroll-result",
        request=request,
        selected_option_id=option_id,
    )
    wrong_actor = restored.submit_decision(replace(result, actor_id="player-b"))
    assert wrong_actor.status_kind is LifecycleStatusKind.INVALID
    assert restored.to_payload() == snapshot
    assert restored.state is not None
    if location == "embarked":
        restored.state.transport_cargo_states.clear()
    else:
        restored.state.reserve_states.clear()
    drifted = restored.to_payload()
    rejected = restored.submit_decision(result)
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert restored.to_payload() == drifted
    continued = session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=result.result_id,
    )
    assert continued.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    completed = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert (
        GameLifecycle.from_payload(completed, runtime_content_bundle=bundle).to_payload()
        == completed
    )
    replayed = GameLifecycle.from_payload(snapshot, runtime_content_bundle=bundle)
    assert replayed.submit_decision(result) == continued
    assert replayed.to_payload() == completed
    assert (
        sum(
            event.event_type == "battle_shock_test_requested"
            for event in lifecycle.decision_controller.event_log.records
        )
        == 1
    )


@pytest.mark.parametrize("location", ["embarked", "reserves"])
def test_mixed_battlefield_and_off_battlefield_candidates_share_finite_sequencing(
    location: str,
) -> None:
    config, state, decisions, unit_id = _command_fixture(location=location, remaining=2)
    healthy = unit_by_id(state, "army-alpha:healthy")
    for model in healthy.own_models[:3]:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=healthy.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )
    session = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            }
        )
    )
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=stratagem_decline_payload(),
            result_id="p01-sequencing-decline-stratagem",
        )
        request = status.decision_request
        assert request is not None
    assert request.decision_type == "resolve_sequencing_order"
    assert {option.option_id for option in request.options} == {
        f"next:command-battle-shock-test:{unit_id}",
        f"next:command-battle-shock-test:{healthy.unit_instance_id}",
    }
    owner = session.view(viewer_player_id="player-a")["pending_decision"]
    opponent = session.view(viewer_player_id="player-b")["pending_decision"]
    assert owner is not None
    assert opponent is not None
    assert owner["options"] == opponent["options"]
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    with pytest.raises(DecisionError):
        session.submit_option(
            request_id=request.request_id, option_id="invented", result_id="p01-invalid-order"
        )
    assert session.lifecycle.to_payload() == snapshot
    session.submit_option(
        request_id=request.request_id,
        option_id=f"next:command-battle-shock-test:{unit_id}",
        result_id="p01-selected-off-battlefield-first",
    )
    requested = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "battle_shock_test_requested"
    ]
    request_ids: list[str] = []
    for payload in requested:
        assert isinstance(payload, dict)
        test_request = payload["battle_shock_test_request"]
        assert isinstance(test_request, dict)
        target_id = test_request["unit_instance_id"]
        assert isinstance(target_id, str)
        request_ids.append(target_id)
    assert request_ids == [unit_id, healthy.unit_instance_id]
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="replay:p01-mixed"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
