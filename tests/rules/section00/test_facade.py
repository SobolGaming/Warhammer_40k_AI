"""00.1/00.2 and FAQ18 through actual witnessed carrier moves and submissions."""

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from tests.support.section00_fixtures import conversion_scene, grant, restore_kernel
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import begin, events, propose
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverridePayload,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    "mode", [DisembarkModeKind.ASSAULT_DISEMBARK, DisembarkModeKind.SHOCK_DISEMBARK]
)
def test_actual_normal_or_advance_converts_disembark_and_preserves_physical_state_restore_replay(
    section00_definitions: Section02Definitions,
    mode: DisembarkModeKind,
) -> None:
    scene = conversion_scene(section00_definitions)
    grant(scene, mode)
    session = scene.session
    request = begin(session)
    initial = deepcopy(session.lifecycle.to_payload())
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s00:carrier",
        option_id=scene.transport.unit_instance_id,
    )
    assert status.decision_request is not None
    action = "normal_move" if mode is DisembarkModeKind.ASSAULT_DISEMBARK else "advance"
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="s00:carrier-action",
        option_id=action,
    )
    # Resolve only generated finite movement choices, including optional Advance rerolls.
    for index in range(6):
        assert status.decision_request is not None, status.to_payload()
        request = status.decision_request
        if request.decision_type == "submit_movement_proposal":
            break
        assert request.decision_type in {"select_advance_reroll", "select_dice_reroll"}, (
            request.to_payload()
        )
        option = next(o.option_id for o in request.options if o.option_id in {"keep", "decline"})
        status = session.submit_option(
            request_id=request.request_id, result_id=f"s00:roll:{index}", option_id=option
        )
    else:
        raise AssertionError("Carrier movement proposal not reached")
    status = propose(
        session, request, scene.transport, (Pose.at(20, 20.1),), result_id="s00:carrier-path"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "select_movement_unit", request.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s00:passenger",
        option_id=scene.passenger.unit_instance_id,
    )
    assert status.decision_request is not None
    assert f"disembark:{mode.value}" in {o.option_id for o in status.decision_request.options}
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="s00:convert",
        option_id=f"disembark:{mode.value}",
    )
    assert status.decision_request is not None
    request = status.decision_request
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert context.context is not None
    expected_status = (
        TransportMovementStatus.NORMAL_MOVE
        if mode is DisembarkModeKind.ASSAULT_DISEMBARK
        else TransportMovementStatus.ADVANCE
    )
    assert context.context["disembark_mode"] == mode.value
    assert context.context["transport_movement_status"] == expected_status.value
    raw = context.context["restriction_overrides"]
    assert isinstance(raw, list)
    overrides = tuple(
        TransportRestrictionOverride.from_payload(cast(TransportRestrictionOverridePayload, item))
        for item in raw
    )
    assert tuple(o.source_rule_id for o in overrides) == (
        f"constructed:s00:permission:{mode.value}",
    )
    payload = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=scene.passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=scene.selection(mode, expected_status).attempted_placement,
        transport_unit_instance_id=scene.transport.unit_instance_id,
        disembark_mode=mode,
        transport_movement_status=expected_status,
        restriction_overrides=overrides,
        start_engaged_enemy_unit_instance_ids=()
        if mode is DisembarkModeKind.SHOCK_DISEMBARK
        else None,
    )
    # Supported proposal boundary: malformed, stale, wrong mode and stripped source
    # are rejected before queue-pop, authoritative mutation or history append.
    invalid_payloads: list[JsonValue] = [
        {"proposal_request_id": request.request_id},
        validate_json_value(replace(payload, proposal_request_id="s00:stale").to_payload()),
        validate_json_value(
            replace(
                payload,
                disembark_mode=DisembarkModeKind.RAPID_DISEMBARK
                if mode is DisembarkModeKind.ASSAULT_DISEMBARK
                else DisembarkModeKind.ASSAULT_DISEMBARK,
            ).to_payload()
        ),
        validate_json_value(replace(payload, restriction_overrides=()).to_payload()),
    ]
    for index, invalid_payload in enumerate(invalid_payloads):
        before = session.lifecycle.to_payload()
        rejected = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=f"s00:invalid:{index}", payload=invalid_payload
        )
        assert rejected.status_kind is LifecycleStatusKind.INVALID, rejected.to_payload()
        assert session.lifecycle.to_payload() == before
        assert session.lifecycle.pending_decision_request() == request
    pending = restore_kernel(session, json.loads(json.dumps(session.lifecycle.to_payload())))
    for viewer in scene.state.player_ids:
        assert pending.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    # Identical continuation of an independent restored graph.
    for active in (session, pending):
        accepted = active.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="s00:placed",
            payload=validate_json_value(payload.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert pending.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert pending.lifecycle.state is not scene.state
    assert not scene.cargo.embarked_unit_instance_ids
    assert scene.state.battlefield_state is not None
    assert (
        scene.state.battlefield_state.unit_placement_by_id(scene.passenger.unit_instance_id)
        == payload.attempted_placement
    )
    outcome = scene.state.disembarked_unit_state_for_unit(
        player_id="owner", battle_round=1, unit_instance_id=scene.passenger.unit_instance_id
    )
    assert outcome is not None
    assert outcome.disembark_mode is mode
    assert outcome.can_declare_charge is (mode is DisembarkModeKind.ASSAULT_DISEMBARK)
    assert not outcome.can_move_further
    assert not outcome.can_choose_remain_stationary
    assert outcome.permission_source_rule_id == f"constructed:s00:permission:{mode.value}"
    assert outcome.battle_shocked_until is None
    assert not rules_unit_is_battle_shocked(
        state=scene.state, unit_instance_id=scene.passenger.unit_instance_id
    )
    # Colocated FAQ18: converted moves count as having disembarked this turn/phase.
    assert scene.cargo.unit_disembarked_this_phase(scene.passenger.unit_instance_id)
    history = [
        row
        for row in scene.state.phase_movement_history
        if row.unit_instance_id == scene.passenger.unit_instance_id
    ]
    assert history[-1].setup_kind is BattlefieldPlacementKind.DISEMBARK
    assert history[-1].model_instance_ids == scene.passenger.own_model_ids()
    assert len(events(session, "unit_disembarked")) == 1
    assert events(session, "unit_disembarked")[0]["disembarked_unit_state"] == outcome.to_payload()
    assert scene.state.fight_phase_state is None
    assert not any(
        event.event_type.startswith("forced_fight_activation_queue_")
        for event in session.lifecycle.decision_controller.event_log.records
    )
    next_request = session.lifecycle.pending_decision_request()
    assert next_request is not None
    assert next_request.decision_type == "select_movement_unit"
    restored = restore_kernel(session, json.loads(json.dumps(session.lifecycle.to_payload())))
    for viewer in scene.state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    records = tuple(
        DecisionRecord.from_payload(value)
        for value in json.loads(
            json.dumps(
                [record.to_payload() for record in session.lifecycle.decision_controller.records]
            )
        )
    )
    assert [record.to_payload() for record in records] == [
        record.to_payload() for record in session.lifecycle.decision_controller.records
    ]
    replay = restore_kernel(session, initial)
    for record in records:
        replayed = submit_replay_record(session=replay, record=record)
        assert replayed.status_kind is not LifecycleStatusKind.INVALID, replayed.to_payload()
    assert replay.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(session.lifecycle.to_payload())
