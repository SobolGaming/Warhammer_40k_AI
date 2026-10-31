"""18.05 after-moving status must reach the actual shared Battle-shock state."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section04_fixtures import choose, pending, weapon_rows
from tests.support.section09_fixtures import movement_mission
from tests.support.section10_fixtures import declaration_request, shooting_session, submit
from tests.support.section18_fixtures import AVENGERS, LORD, WAVE
from warhammer40k_core.engine.battle_shock import (
    StratagemTargetPermissionStatus,
    friendly_stratagem_target_permission,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose


def test_native_emergency_survivors_become_actually_battle_shocked(
    section18_definitions: Section02Definitions,
) -> None:
    d = section18_definitions
    shooter = d.unit(LORD)
    carrier = d.unit(WAVE, identity="carrier", army_id="enemy")
    # Declared wounded native checkpoint, not a claim of playing earlier attacks.
    carrier = replace(carrier, own_models=(replace(carrier.own_models[0], wounds_remaining=1),))
    passenger = d.unit(AVENGERS, identity="cargo", army_id="enemy")
    state = native_state(
        d, shooter, (Pose.at(10, 10),), enemy=carrier, enemy_poses=(Pose.at(18, 10),)
    )
    # Current native profile: observed hit/wound/failed save reaches Emergency placement.
    state.game_id = "section18:emergency:seed-1"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.army_definitions[:] = [
        replace(a, units=(*a.units, passenger)) if a.player_id == "opponent" else a
        for a in state.army_definitions
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="opponent", unit=passenger)
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            "opponent",
            carrier.unit_instance_id,
            TransportCapacityProfile(
                WAVE, 12, ("INFANTRY",), source_id="constructed:s18:native-cargo"
            ),
            (passenger.unit_instance_id,),
        )
    )
    session = shooting_session(d, state, movement_mission())
    request = declaration_request(session, shooter, "normal")
    rows = [r for r in weapon_rows(request) if r["wargear_id"] == f"{LORD}:bolt-pistol"]
    assert len(rows) == 1
    status = submit(session, rows, [carrier.unit_instance_id], "normal")
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    for _index in range(30):
        request = pending(session)
        if request.decision_type == "submit_placement_proposal":
            break
        assert not any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ), [
            e.to_payload()
            for e in session.lifecycle.decision_controller.event_log.records
            if e.event_type == "dice_rolled"
        ]
        option = next(
            (
                o.option_id
                for o in request.options
                if o.option_id in {"decline", "keep", "keep_all_modifiers"}
            ),
            request.options[0].option_id,
        )
        choose(session, request, option)
    else:
        raise AssertionError("Native Emergency placement was not reached")
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal.context is not None
    assert proposal.context["destruction_timing"] == "destroyed_transport"
    assert not rules_unit_is_battle_shocked(
        state=state, unit_instance_id=passenger.unit_instance_id
    )
    survivor_ids = proposal.context["surviving_model_instance_ids"]
    assert isinstance(survivor_ids, list)
    from math import cos, radians, sin

    rt = carrier.own_models[0].geometry.parts[0].radius_x_inches
    poses = tuple(
        ModelPlacement(
            "enemy",
            "opponent",
            passenger.unit_instance_id,
            m.model_instance_id,
            Pose.at(
                18 + (rt + m.geometry.parts[0].radius_x_inches + 0.02) * cos(radians(70 * i)),
                10 + (rt + m.geometry.parts[0].radius_x_inches + 0.02) * sin(radians(70 * i)),
            ),
        )
        for i, m in enumerate(passenger.own_models)
        if m.model_instance_id in survivor_ids
    )
    assert poses
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s18:emergency-accepted",
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=passenger.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=UnitPlacement(
                    "enemy", "opponent", passenger.unit_instance_id, poses
                ),
                transport_unit_instance_id=carrier.unit_instance_id,
                disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert any(
        e.event_type == "unit_disembarked"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=passenger.unit_instance_id)
    from warhammer40k_core.engine.emergency_disembark_battle_shock import (
        apply_emergency_disembark_battle_shock,
    )

    accepted = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "unit_disembarked"
    )
    original_status = tuple(state.battle_shocked_unit_states)
    apply_emergency_disembark_battle_shock(
        state=state, decisions=session.lifecycle.decision_controller, event=accepted
    )
    assert tuple(state.battle_shocked_unit_states) == original_status
    assert model_objective_control_characteristic(
        passenger.own_models[0],
        battle_shocked=rules_unit_is_battle_shocked(
            state=state, unit_instance_id=passenger.unit_instance_id
        ),
    ).is_dash
    assert (
        friendly_stratagem_target_permission(
            player_id="opponent",
            target_player_id="opponent",
            target_unit_instance_id=passenger.unit_instance_id,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        ).status
        is StratagemTargetPermissionStatus.DENIED
    )
    assert state.battle_shocked_unit_states[0].source_result_id == "s18:emergency-accepted"
    # Explicit turn-cleanup boundary: the charge lock ends, direct Battle-shock
    # persists until the shared authorized clear owner. No earlier phases played.
    state.clear_turn_action_states(player_id="owner", battle_round=1)
    assert not state.disembarked_unit_states
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=passenger.unit_instance_id)
