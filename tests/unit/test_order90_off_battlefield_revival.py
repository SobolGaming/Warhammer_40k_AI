from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.order90_revival_helpers import offboard_scene

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.healing import resolve_healing_until_blocked
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


@pytest.mark.parametrize("reserves", [False, True])
@pytest.mark.parametrize("full_health", [False, True])
def test_offboard_revival_preserves_source_wounds_equipment_and_replay(
    reserves: bool, full_health: bool
) -> None:
    lifecycle, effect, model_id = offboard_scene(reserves=reserves, full_health=full_health)
    state = lifecycle.state
    assert state is not None
    before = model_by_id(state=state, model_instance_id=model_id)
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    assert request.decision_type == "select_healing_model"
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    session = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order90-return-choice",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    returned = model_by_id(state=state, model_instance_id=model_id)
    assert returned == replace(before, wounds_remaining=before.initial_wounds if full_health else 1)
    assert state.battlefield_state is not None
    assert model_id not in state.battlefield_state.placed_model_ids()
    assert model_id not in state.battlefield_state.removed_model_ids
    assert model_id in (
        state.unarrived_reserve_model_ids() if reserves else state.embarked_model_ids()
    )
    assert all(
        record.request.decision_type != "submit_healing_revival_placement"
        for record in session.lifecycle.decision_controller.records
    )
    LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order90")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("capacity", [5, 6])
@pytest.mark.parametrize("revive_leader", [False, True])
def test_capacity_counts_all_attached_cargo_without_new_destruction_trigger(
    capacity: int, revive_leader: bool
) -> None:
    lifecycle, effect, model_id = offboard_scene(capacity=capacity, revive_leader=revive_leader)
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    before = sum(
        e.event_type == "model_destroyed" for e in lifecycle.decision_controller.event_log.records
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order90-capacity",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert model_by_id(state=state, model_instance_id=model_id).current_wounds == (
        model_by_id(state=state, model_instance_id=model_id).initial_wounds if capacity == 6 else 0
    )
    assert (
        sum(
            e.event_type == "model_destroyed"
            for e in lifecycle.decision_controller.event_log.records
        )
        == before
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="capacity"))
        .run()
        .reproduced_exactly
    )
    LocalGameSession.from_persistence_payload(session.to_persistence_payload())


@pytest.mark.parametrize("reserves", [False, True])
def test_location_drift_is_rejected_before_recording_or_mutation(reserves: bool) -> None:
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, effect, model_id = offboard_scene(reserves=reserves)
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    for request_id, option_id in (
        ("stale", request.options[0].option_id),
        (request.request_id, "invented"),
    ):
        before = lifecycle.to_payload()
        with pytest.raises((DecisionError, GameLifecycleError)):
            session.submit_option(request_id=request_id, option_id=option_id, result_id="invalid")
        assert lifecycle.to_payload() == before
    if reserves:
        reserve = state.reserve_states[0]
        state.replace_reserve_state(replace(reserve, source_rule_ids=("drift",)))
    else:
        cargo = state.transport_cargo_states[0]
        state.replace_transport_cargo_state(
            replace(cargo, capacity_profile=replace(cargo.capacity_profile, max_model_count=9))
        )
    before = lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id=request.options[0].option_id, result_id="drift"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == before
    assert model_by_id(state=state, model_instance_id=model_id).current_wounds == 0
    with pytest.raises(GameLifecycleError, match="drift"):
        GameLifecycle.from_payload(before)


@pytest.mark.parametrize("reserves", [False, True])
def test_loaded_command_restoration_returns_offboard_without_placement(reserves: bool) -> None:
    from tests.order90_revival_helpers import with_catalog_restoration

    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    lifecycle, _, model_id = offboard_scene(reserves=reserves)
    session = LocalGameSession(with_catalog_restoration(lifecycle))
    status = session.advance_until_decision_or_terminal()
    for index in range(12):
        request = status.decision_request
        assert request is not None, status
        if request.decision_type == "select_healing_model":
            break
        # The loaded Command-start owner offers its source and target through finite choices.
        option = next(
            (
                o
                for o in request.options
                if isinstance(o.payload, dict)
                and o.payload.get("selection_kind") == "catalog_command_restoration"
            ),
            request.options[0],
        )
        status = session.submit_option(
            request_id=request.request_id, option_id=option.option_id, result_id=f"producer-{index}"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    else:
        pytest.fail("Loaded restoration did not produce its healing decision.")
    session = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="producer-revival",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    model = model_by_id(state=state, model_instance_id=model_id)
    assert model.current_wounds == model.initial_wounds
    assert state.battlefield_state is not None
    assert model_id not in state.battlefield_state.placed_model_ids()
    for viewer in state.player_ids:
        assert "revival_location" not in json.dumps(session.view(viewer_player_id=viewer))
        delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert "revival_location" not in json.dumps(delta)
        assert any(e["event_type"] == "healing_step_resolved" for e in delta["events"])
    LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="producer"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("reserves", [False, True])
def test_revived_model_participates_in_later_group_ingress_or_disembark(
    attached: bool, reserves: bool
) -> None:
    from tests.order60_emergency_disembark_helpers import emergency_disembark_contact_poses

    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldPlacementKind,
        ModelPlacement,
        UnitPlacement,
    )
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
    from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, effect, model_id = offboard_scene(
        reserves=reserves, attached=attached, battle_round=2, revive_leader=attached
    )
    state = lifecycle.state
    assert state is not None
    if not reserves:
        cargo = state.transport_cargo_states[0]
        state.replace_transport_cargo_state(
            cargo.for_movement_phase(battle_round=state.battle_round)
        )
    expected_wounds = model_by_id(state=state, model_instance_id=model_id).initial_wounds
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="arrival-revive",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_movement_unit"
    status = session.submit_option(
        request_id=request.request_id,
        option_id=effect.target_unit_instance_id,
        result_id="arrival-unit",
    )
    request = status.decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id,
        option_id="ingress" if reserves else "disembark",
        result_id="arrival-action",
    )
    request = status.decision_request
    assert request is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=effect.target_unit_instance_id)
    positions = {
        m.model_instance_id: Pose.at(20 + i * 1.5, 2) for i, m in enumerate(view.alive_models())
    }
    if not reserves:
        assert state.battlefield_state is not None
        transport = state.battlefield_state.unit_placement_by_id("army-alpha:transport")
        center = transport.model_placements[0].pose.position
        poses = emergency_disembark_contact_poses(
            view.alive_models(), center_x=center.x, center_y=center.y
        )
        positions = {
            m.model_instance_id: pose for m, pose in zip(view.alive_models(), poses, strict=True)
        }
    placement = RulesUnitPlacement(
        rules_unit_instance_id=view.unit_instance_id,
        component_unit_placements=tuple(
            UnitPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=c.unit.unit_instance_id,
                model_placements=tuple(
                    ModelPlacement(
                        army_id="army-alpha",
                        player_id="player-a",
                        unit_instance_id=c.unit.unit_instance_id,
                        model_instance_id=m.model_instance_id,
                        pose=positions[m.model_instance_id],
                    )
                    for m in c.unit.own_models
                    if m.is_alive
                ),
            )
            for c in view.components
        ),
    )
    proposal = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.STRATEGIC_RESERVES if reserves else ProposalKind.DISEMBARK,
        unit_instance_id=view.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES
        if reserves
        else BattlefieldPlacementKind.DISEMBARK,
        attempted_rules_unit_placement=placement,
        transport_unit_instance_id=None if reserves else "army-alpha:transport",
        disembark_mode=None if reserves else DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=None if reserves else TransportMovementStatus.NOT_MOVED,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="arrival-place",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.placed_model_ids()
    assert model_by_id(state=state, model_instance_id=model_id).current_wounds == expected_wounds
    LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="arrival"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("reserves", [False, True])
def test_restore_rejects_forged_source_wounds_on_nonspatial_return(reserves: bool) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, effect, _ = offboard_scene(reserves=reserves)
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="return-tamper",
    )
    payload = json.loads(json.dumps(lifecycle.to_payload()))
    event = next(
        e for e in payload["decisions"]["event_log"] if e["event_type"] == "healing_step_resolved"
    )
    event["payload"]["step"]["final_wounds_remaining"] = 1
    with pytest.raises(GameLifecycleError, match="source wounds drifted"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("revive_leader", [False, True])
@pytest.mark.parametrize("cargo_in_reserves", [False, True])
def test_return_keeps_attached_ownership_and_equipment_inside_reserve_transport(
    revive_leader: bool,
    cargo_in_reserves: bool,
) -> None:
    from warhammer40k_core.engine.ability_presence import ability_presence
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle, effect, model_id = offboard_scene(
        cargo_in_reserves=cargo_in_reserves, revive_leader=revive_leader
    )
    state = lifecycle.state
    assert state is not None
    model = model_by_id(state=state, model_instance_id=model_id)
    assert model.wargear_ids
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="carrier-reserve-return",
    )
    assert model_by_id(state=state, model_instance_id=model_id) == replace(
        model, wounds_remaining=model.initial_wounds
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=effect.target_unit_instance_id)
    presence = ability_presence(state=state, rules_unit=view)
    assert model_id in presence.off_battlefield_model_ids
    assert not presence.battlefield_model_ids
    assert model_id in state.embarked_model_ids()
    assert (model_id in state.unarrived_reserve_model_ids()) is cargo_in_reserves
    LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="carrier-reserve"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("fault", ["incomplete", "placed", "destroyed_transport"])
def test_inconsistent_offboard_authority_fails_before_return(fault: str) -> None:
    from warhammer40k_core.engine.healing import healing_army_definitions_with_model_wounds
    from warhammer40k_core.engine.healing_off_battlefield import revival_location
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario

    lifecycle, effect, _ = offboard_scene()
    state = lifecycle.state
    assert state is not None
    if fault == "incomplete":
        state.transport_cargo_states[0] = replace(
            state.transport_cargo_states[0], embarked_unit_instance_ids=("army-alpha:passengers",)
        )
    elif fault == "placed":
        state.battlefield_state = create_deterministic_battlefield_scenario(
            battlefield_id="conflict", armies=tuple(state.army_definitions)
        ).battlefield_state
    else:
        transport = next(
            u
            for u in state.army_definitions[0].units
            if u.unit_instance_id == "army-alpha:transport"
        )
        state.army_definitions[:] = healing_army_definitions_with_model_wounds(
            armies=tuple(state.army_definitions),
            model_instance_id=transport.own_models[0].model_instance_id,
            wounds_remaining=0,
        )
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match=r"incomplete|placed models|destroyed Transport"):
        revival_location(state=state, unit_instance_id=effect.target_unit_instance_id)
    assert state.to_payload() == before


@pytest.mark.parametrize("reserves", [False, True])
@pytest.mark.parametrize(
    "fault", ["round", "player", "phase", "owner", "capacity_or_source", "origin"]
)
def test_completed_return_authenticates_independent_location_history(
    reserves: bool, fault: str
) -> None:
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, effect, _ = offboard_scene(reserves=reserves)
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="history-return",
    )
    payload = json.loads(json.dumps(lifecycle.to_payload()))
    if fault == "origin":
        del payload["off_battlefield_revival_history_origin"]
    else:

        def tamper(value: JsonValue) -> None:
            if isinstance(value, list):
                for item in value:
                    tamper(item)
            elif isinstance(value, dict):
                location = value.get("revival_location")
                if isinstance(location, dict):
                    if fault == "round":
                        location["battle_round"] = 99
                    elif fault == "player":
                        location["turn_owner_player_id"] = "player-b"
                    elif fault == "phase":
                        location["phase"] = "fight"
                    elif fault == "owner":
                        raw = location["reserve_state" if reserves else "cargo_state"]
                        assert isinstance(raw, dict)
                        raw["unit_instance_id" if reserves else "transport_unit_instance_id"] = (
                            "missing-owner"
                        )
                    elif reserves:
                        raw = location["reserve_state"]
                        assert isinstance(raw, dict)
                        raw["source_rule_ids"] = ["forged-source"]
                    else:
                        location["occupied_model_count"] = 0
                for key, item in value.items():
                    if key != "off_battlefield_revival_history_origin":
                        tamper(item)

        tamper(payload)
    with pytest.raises(GameLifecycleError, match=r"drift|historical|pre-return|owner"):
        GameLifecycle.from_payload(payload)


def test_reserve_declaration_cannot_substitute_another_cargo_rules_unit() -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, _, _ = offboard_scene(cargo_in_reserves=True, revive_leader=True)
    payload = json.loads(json.dumps(lifecycle.to_payload()))
    declaration = next(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "reserve_unit_declared"
    )
    declaration["payload"]["reserve_state"]["embarked_unit_instance_ids"] = ["army-alpha:transport"]
    with pytest.raises(GameLifecycleError, match="declaration evidence drift"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("cargo_in_reserves", [False, True])
def test_restore_rejects_missing_living_attached_cargo_component(cargo_in_reserves: bool) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, _, _ = offboard_scene(cargo_in_reserves=cargo_in_reserves)
    payload = json.loads(json.dumps(lifecycle.to_payload()))
    payload["state"]["transport_cargo_states"][0]["embarked_unit_instance_ids"] = [
        "army-alpha:passengers"
    ]
    if cargo_in_reserves:
        payload["state"]["reserve_states"][0]["embarked_unit_instance_ids"] = [
            "army-alpha:passengers"
        ]
    with pytest.raises(GameLifecycleError, match="incomplete living attached cargo"):
        GameLifecycle.from_payload(payload)
