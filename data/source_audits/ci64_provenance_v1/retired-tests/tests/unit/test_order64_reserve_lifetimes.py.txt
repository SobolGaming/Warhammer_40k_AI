"""Core reserve deadlines and ingress locks use authenticated shared authority."""

from __future__ import annotations

from dataclasses import replace

import pytest
from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
from tests.order63_reserve_transport_helpers import reserve_transport_session, submit_ingress

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import (
    MissionPolicyDescriptor,
    ReserveDestructionTimingKind,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reserves import ReserveDestructionTimingPolicy


def test_core_defaults_block_first_round_and_destroy_at_round_three() -> None:
    mission = MissionPolicyDescriptor.core_rules_default()
    assert mission.reserves_arrival_blocked_battle_rounds == (1,)
    assert mission.reserve_destruction_timing is ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N
    assert mission.reserve_destruction_battle_round == 3
    policy = ReserveDestructionTimingPolicy.core_rules_default()
    assert policy.applies_at(battle_round=3, end_of_battle=False)
    assert not policy.applies_at(battle_round=2, end_of_battle=False)


@pytest.mark.parametrize("deep_strike", [False, True])
def test_ingress_locks_the_transport_until_charge_but_does_not_lock_its_cargo(
    deep_strike: bool,
) -> None:
    from warhammer40k_core.engine.ingress_lifetimes import ingress_movement_locked

    session = reserve_transport_session(deep_strike=deep_strike)
    submit_ingress(session, deep_strike=deep_strike)
    state = session.lifecycle.state
    assert state is not None
    assert ingress_movement_locked(state, TRANSPORT_ID)
    assert not ingress_movement_locked(state, PASSENGER_ID)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert ingress_movement_locked(state, TRANSPORT_ID)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert not ingress_movement_locked(state, TRANSPORT_ID)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    assert not ingress_movement_locked(state, TRANSPORT_ID)


@pytest.mark.parametrize("arrival_phase", list(BattlePhase))
@pytest.mark.parametrize("arrival_player", ["player-a", "player-b"])
def test_next_charge_boundary_uses_actual_turn_and_phase(
    arrival_phase: BattlePhase, arrival_player: str
) -> None:
    from msgspec.structs import replace as replace_record

    from warhammer40k_core.engine.ingress_lifetimes import ingress_movement_locked

    session = reserve_transport_session()
    submit_ingress(session)
    state = session.lifecycle.state
    assert state is not None
    original = state.phase_movement_history[0]
    state.phase_movement_history[0] = replace_record(
        original, phase=arrival_phase, turn_player_id=arrival_player
    )
    state.active_player_id = arrival_player
    state.battle_phase_index = state.battle_phase_sequence.index(arrival_phase)
    assert ingress_movement_locked(state, TRANSPORT_ID)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    assert ingress_movement_locked(state, TRANSPORT_ID) is (
        arrival_phase in {BattlePhase.CHARGE, BattlePhase.FIGHT}
    )
    # When ingress happened after Charge began, the lock survives to the next turn.
    state.active_player_id = "player-b" if arrival_player == "player-a" else "player-a"
    if state.turn_order.index(state.active_player_id) < state.turn_order.index(arrival_player):
        state.battle_round += 1
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    assert ingress_movement_locked(state, TRANSPORT_ID) is (
        arrival_phase in {BattlePhase.CHARGE, BattlePhase.FIGHT}
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert not ingress_movement_locked(state, TRANSPORT_ID)


def test_ingress_movement_lock_cannot_be_bypassed_by_battlefield_mutation() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.geometry.pose import Pose

    session = reserve_transport_session()
    submit_ingress(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(TRANSPORT_ID)
    moved = replace(
        placement,
        model_placements=tuple(
            replace(row, pose=Pose.at(row.pose.position.x + 1, row.pose.position.y))
            for row in placement.model_placements
        ),
    )
    with pytest.raises(GameLifecycleError, match="ingress_movement_locked"):
        state.replace_battlefield_state(state.battlefield_state.with_unit_placement(moved))


@pytest.mark.parametrize("end_of_battle", [False, True])
def test_boundary_destroys_unarrived_transport_and_cargo_without_destroyed_model_triggers(
    end_of_battle: bool,
) -> None:
    from warhammer40k_core.engine.reserve_lifetime_boundary import resolve_boundary
    from warhammer40k_core.engine.reserves import ReserveStatus

    session = reserve_transport_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.battle_round = 5 if end_of_battle else 3
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    # Cleanup is automatic engine mutation, not a player choice.
    event_count = len(session.lifecycle.decision_controller.event_log.records)
    resolve_boundary(state, end_of_battle=end_of_battle)
    reserve = state.reserve_state_for_unit(TRANSPORT_ID)
    assert reserve is not None
    assert reserve.status is ReserveStatus.DESTROYED
    assert reserve.destroyed_at_end_of_battle is end_of_battle
    assert state.battlefield_state.removed_model_ids
    assert {row.destroyed_unit_instance_id for row in state.primary_unit_destruction_states} == {
        TRANSPORT_ID,
        PASSENGER_ID,
    }
    assert state.transport_cargo_states == []
    assert len(session.lifecycle.decision_controller.event_log.records) == event_count
    assert all(
        model.model_instance_id in state.battlefield_state.removed_model_ids
        for unit in state.army_definitions[0].units
        if unit.unit_instance_id in {TRANSPORT_ID, PASSENGER_ID}
        for model in unit.own_models
    )


def test_core_deadline_exemption_does_not_become_a_final_cleanup_exemption() -> None:
    from tests.phase10p_reserves_helpers import battle_state_with_reserve

    from warhammer40k_core.engine.reserve_destruction import (
        final_turn_cleanup_policy,
        resolve_unarrived_reserve_destruction,
    )
    from warhammer40k_core.engine.reserves import ReserveStatus

    state, scenario, reserve, unit = battle_state_with_reserve()
    for end, round_number, policy in (
        (False, 3, ReserveDestructionTimingPolicy.core_rules_default()),
        (True, 5, final_turn_cleanup_policy()),
    ):
        result = resolve_unarrived_reserve_destruction(
            reserve_states=(reserve,),
            armies=tuple(state.army_definitions),
            battlefield_state=scenario.battlefield_state,
            policy=policy,
            battle_round=round_number,
            end_of_battle=end,
            exempt_unit_instance_ids=frozenset({unit.unit_instance_id}),
        )
        assert bool(result.destroyed_model_instance_ids) is end
        assert (result.updated_reserve_states[0].status is ReserveStatus.DESTROYED) is end


def test_a_during_battle_reserve_origin_does_not_invent_repositioning_history() -> None:
    from warhammer40k_core.engine.reserve_lifetime_boundary import reserve_round_deadline_exempt_ids
    from warhammer40k_core.engine.reserves import ReserveOrigin

    session = reserve_transport_session()
    state = session.lifecycle.state
    assert state is not None
    reserve = state.reserve_states[0]
    state.reserve_states[0] = replace(reserve, reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY)
    assert reserve_round_deadline_exempt_ids(state) == frozenset()
    state.reserve_states[0] = reserve
    submit_ingress(session)
    assert reserve_round_deadline_exempt_ids(state) == frozenset({TRANSPORT_ID})


@pytest.mark.parametrize("deep_strike", [False, True])
def test_cargo_of_an_ingressed_transport_survives_round_three(deep_strike: bool) -> None:
    from warhammer40k_core.engine.reserve_lifetime_boundary import resolve_boundary
    from warhammer40k_core.engine.reserves import ReserveStatus

    session = reserve_transport_session(deep_strike=deep_strike)
    submit_ingress(session, deep_strike=deep_strike)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    state.battle_round = 3
    resolve_boundary(state, end_of_battle=False)
    assert state.reserve_states[0].status is ReserveStatus.ARRIVED
    assert state.transport_cargo_states[0].embarked_unit_instance_ids == (PASSENGER_ID,)
    assert state.battlefield_state == before
    assert state.primary_unit_destruction_states == []


@pytest.mark.parametrize("tamper", ["remove", "false", "not_bool"])
def test_restore_rejects_forged_ingress_classification(tamper: str) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = reserve_transport_session()
    submit_ingress(session)
    payload = session.lifecycle.to_payload()
    rows = payload["state"]["phase_movement_history"]
    if tamper == "remove":
        del rows[0]["is_ingress"]
    else:
        rows[0]["is_ingress"] = False if tamper == "false" else 1
    with pytest.raises(GameLifecycleError, match=r"movement|history"):
        GameLifecycle.from_payload(payload)


def test_mission_deadline_override_requires_and_preserves_its_source() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    override = replace(
        MissionPolicyDescriptor.core_rules_default(), reserve_destruction_battle_round=4
    )
    with pytest.raises(GameLifecycleError, match="explicit source_id"):
        ReserveDestructionTimingPolicy.from_mission_policy(override)
    policy = ReserveDestructionTimingPolicy.from_mission_policy(
        override, source_id="mission:round-four"
    )
    assert not policy.applies_at(battle_round=3, end_of_battle=False)
    assert policy.applies_at(battle_round=4, end_of_battle=False)
    assert ReserveDestructionTimingPolicy.from_payload(policy.to_payload()) == policy
    assert policy.source_id == "mission:round-four"


@pytest.mark.parametrize("surge", [False, True])
def test_reactive_movement_selection_excludes_ingressed_units_until_charge(surge: bool) -> None:
    from tests.surge_helpers import surge_descriptor

    from warhammer40k_core.engine.triggered_movement import (
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        TriggeredMovementEligibleUnit,
        TriggeredMovementKind,
    )
    from warhammer40k_core.engine.triggered_movement_selection import (
        triggered_movement_unit_selection_request,
    )

    session = reserve_transport_session()
    submit_ingress(session)
    state = session.lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    descriptor = replace(
        surge_descriptor(lifecycle=session.lifecycle),
        movement_kind=TriggeredMovementKind.SURGE if surge else TriggeredMovementKind.TRIGGERED,
    )
    request = triggered_movement_unit_selection_request(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(TRANSPORT_ID, "test:hook", descriptor.source_rule_id),
        ),
    )
    assert [option.option_id for option in request.options] == [
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID
    ]


def test_final_turn_marker_is_required_and_only_valid_on_destroyed_reserves() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.reserves import ReserveState

    session = reserve_transport_session()
    state = session.lifecycle.state
    assert state is not None
    reserve = state.reserve_states[0]
    with pytest.raises(GameLifecycleError, match="final-turn"):
        replace(reserve, destroyed_at_end_of_battle=True)
    destroyed = reserve.mark_destroyed(battle_round=5, end_of_battle=True)
    assert ReserveState.from_payload(destroyed.to_payload()) == destroyed


@pytest.mark.parametrize(("complete", "round_number"), [(False, 5), (True, 3), (True, 5)])
def test_final_cleanup_restore_binds_the_actual_battle_boundary(
    complete: bool,
    round_number: int,
) -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
    from warhammer40k_core.engine.reserve_lifetime_boundary import validate_final_turn_destruction

    session = reserve_transport_session()
    state = session.lifecycle.state
    assert state is not None
    state.reserve_states[0] = state.reserve_states[0].mark_destroyed(
        battle_round=round_number,
        end_of_battle=True,
    )
    state.battle_round = round_number
    if complete:
        state.stage = GameLifecycleStage.COMPLETE
    if complete and round_number == 5:
        validate_final_turn_destruction(state)
    else:
        with pytest.raises(GameLifecycleError, match="Final-turn reserve destruction"):
            validate_final_turn_destruction(state)


def test_setup_without_an_ingress_completion_does_not_invent_an_ingress_lock() -> None:
    from msgspec.structs import replace as replace_record

    from warhammer40k_core.engine.ingress_lifetimes import ingress_movement_locked

    session = reserve_transport_session()
    submit_ingress(session)
    state = session.lifecycle.state
    assert state is not None
    # Disembark/return-on-death are set-ups, but not Ingress moves.
    row = state.phase_movement_history[0]
    state.phase_movement_history[0] = replace_record(row, is_ingress=False)
    assert not ingress_movement_locked(state, TRANSPORT_ID)


def _pass_reserve_deadline_decision(session: LocalGameSession) -> None:
    """Keep reserves offboard using only choices from the public session."""
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

    request = pending_request(session)
    result_id = f"issue534:{request.request_id}"
    if request.decision_type == "submit_stratagem_target_proposal":
        outcome = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=stratagem_decline_payload(),
        )
    else:
        if request.decision_type in {"select_movement_unit", "resolve_sequencing_order"}:
            option_id = request.options[0].option_id
        else:
            option_id = {
                "select_movement_action": "remain_stationary",
                "select_shooting_unit": "complete_shooting_phase",
                "select_charging_unit": "complete_charge_phase",
                "use_stratagem": "decline_stratagem_window",
            }[request.decision_type]
        outcome = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option_id
        )
    assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome


def _play_to_reserve_deadline_round(session: LocalGameSession, round_number: int) -> None:
    from tests.psychic_modifier_helpers import pending_request

    for _ in range(150):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if (
            state.battle_round == round_number
            and state.active_player_id == "player-a"
            and request.decision_type == "select_movement_unit"
        ):
            return
        _pass_reserve_deadline_decision(session)
    raise AssertionError("Public play did not reach the requested round's movement.")


@pytest.mark.parametrize("loaded", [False, True])
@pytest.mark.parametrize("deep_strike", [False, True])
def test_reserve_deadline_logical_death_preserves_public_play_and_persistence(
    loaded: bool, deep_strike: bool
) -> None:
    import json

    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayRunner
    from warhammer40k_core.engine.reserves import ReserveStatus

    session = reserve_transport_session(loaded=loaded, deep_strike=deep_strike)
    _play_to_reserve_deadline_round(session, 3)
    before = session.lifecycle.to_payload()
    before_fork = session.fork()
    session = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    _play_to_reserve_deadline_round(session, 4)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    reserve = state.reserve_state_for_unit(TRANSPORT_ID)
    assert reserve is not None
    assert reserve.status is ReserveStatus.DESTROYED
    assert reserve.destroyed_battle_round == 3
    assert not reserve.destroyed_at_end_of_battle
    destroyed_units = {TRANSPORT_ID, PASSENGER_ID} if loaded else {TRANSPORT_ID}
    destroyed_models = {
        model.model_instance_id
        for unit_id in destroyed_units
        for model in unit_by_id(state=state, unit_instance_id=unit_id).own_models
    }
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                assert model.is_alive is (model.model_instance_id not in destroyed_models)
    assert destroyed_models == set(state.battlefield_state.removed_model_ids)
    assert state.transport_cargo_states == []
    assert {row.destroyed_unit_instance_id for row in state.primary_unit_destruction_states} == (
        destroyed_units
    )
    assert not any(
        event.event_type in {"model_destroyed", "unit_destroyed", "destruction_reaction_triggered"}
        for event in session.lifecycle.decision_controller.event_log.records
    )
    request = pending_request(session)
    options = {option.option_id for option in request.options}
    assert "army-alpha:remaining-unit" in options
    assert options.isdisjoint(destroyed_units)
    final = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(final).to_payload() == final
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    for candidate in (restored, fork):
        assert candidate.lifecycle.to_payload() == final
        for viewer in ("player-a", "player-b"):
            assert candidate.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
            assert candidate.events_since(
                EventStreamCursor(), viewer_player_id=viewer
            ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        _pass_reserve_deadline_decision(candidate)
        _pass_reserve_deadline_decision(candidate)
    assert restored.lifecycle.to_payload() == fork.lifecycle.to_payload()
    assert session.lifecycle.to_payload() == final
    assert before_fork.lifecycle.to_payload() == before
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="issue534")).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("cargo", [False, True])
@pytest.mark.parametrize("end_of_battle", [False, True])
def test_reserve_deadline_destroys_attached_components_with_prior_casualty(
    cargo: bool, end_of_battle: bool
) -> None:
    from tests.order90_revival_helpers import offboard_scene
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.reserve_lifetime_boundary import resolve_boundary
    from warhammer40k_core.engine.reserves import ReserveStatus
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle, _effect, casualty_id = offboard_scene(
        reserves=not cargo, attached=True, cargo_in_reserves=cargo, battle_round=2
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    attached = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    assert len(attached.component_unit_instance_ids) == 2
    assert not model_by_id(state=state, model_instance_id=casualty_id).is_alive
    assert casualty_id in state.battlefield_state.removed_model_ids
    reserve = state.reserve_states[0]
    affected = {model.model_instance_id for model in attached.own_models}
    if cargo:
        affected.update(
            model.model_instance_id
            for model in rules_unit_view_by_id(
                state=state, unit_instance_id=TRANSPORT_ID
            ).own_models
        )
    state.battle_round = 5 if end_of_battle else 3
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    events = lifecycle.decision_controller.event_log.to_payload()
    reactions = lifecycle.reaction_queue.to_payload()
    resolve_boundary(state, end_of_battle=end_of_battle)
    updated = state.reserve_state_for_unit(reserve.unit_instance_id)
    assert updated is not None
    assert updated.status is ReserveStatus.DESTROYED
    assert updated.destroyed_at_end_of_battle is end_of_battle
    assert state.transport_cargo_states == []
    assert affected <= set(state.battlefield_state.removed_model_ids)
    assert all(
        not model_by_id(state=state, model_instance_id=model_id).is_alive for model_id in affected
    )
    assert lifecycle.decision_controller.event_log.to_payload() == events
    assert lifecycle.reaction_queue.to_payload() == reactions
    after = state.to_payload()
    resolve_boundary(state, end_of_battle=end_of_battle)
    assert state.to_payload() == after


def test_attached_reserve_deadline_public_continuation_restores_and_replays() -> None:
    from tests.order90_revival_helpers import offboard_scene

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayRunner
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle, _effect, _casualty_id = offboard_scene(reserves=True, attached=True, battle_round=2)
    session = LocalGameSession(lifecycle)
    _play_to_reserve_deadline_round(session, 3)
    before = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(before).to_payload() == before
    _play_to_reserve_deadline_round(session, 4)
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    assert len(view.component_unit_instance_ids) == 2
    assert not view.alive_models()
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    _pass_reserve_deadline_decision(restored)
    _pass_reserve_deadline_decision(restored)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="issue534-attached")
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("cargo", [False, True])
@pytest.mark.parametrize("after_destruction", [False, True])
def test_reserve_deadline_secondary_boundary_preserves_attached_casualty_presence(
    cargo: bool, after_destruction: bool
) -> None:
    from tests.order90_revival_helpers import offboard_scene
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    from warhammer40k_core.engine.primary_destruction_evidence import (
        PrimaryUnattributedDestructionCause,
    )
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        capture_primary_mission_boundary_checkpoint,
        primary_unit_destruction_states_from_checkpoint,
    )
    from warhammer40k_core.engine.reserve_lifetime_boundary import resolve_boundary
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.secondary_scoring_state_evidence_authority import (
        _validate_same_boundary_reserve_destructions,  # pyright: ignore[reportPrivateUsage]
    )

    lifecycle, _effect, casualty_id = offboard_scene(
        reserves=not cargo, attached=True, cargo_in_reserves=cargo, battle_round=2
    )
    state = lifecycle.state
    assert state is not None
    state.battle_round = 3
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    record = state.determine_current_phase_end_objective_control()
    if after_destruction:
        resolve_boundary(state, end_of_battle=False)
    checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="objective_control",
        player_id="player-a",
        runtime_modifier_registry=RuntimeModifierRegistry(),
    )
    casualty = next(row for row in checkpoint.model_states if row.model_instance_id == casualty_id)
    assert casualty.presence == "destroyed"
    if not after_destruction:
        resolve_boundary(state, end_of_battle=False)
    _validate_same_boundary_reserve_destructions(
        state=state,
        record=record,
        checkpoint=checkpoint,
        checkpoint_destruction_ids=tuple(
            row.destruction_id
            for row in primary_unit_destruction_states_from_checkpoint(checkpoint)
        ),
        destructions=tuple(
            row
            for row in state.primary_unit_destruction_states
            if row.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
        ),
    )
