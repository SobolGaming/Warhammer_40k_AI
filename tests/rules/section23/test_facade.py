"""Native public combat controls plus supported Core Aircraft restore/replay boundary."""

import json

import pytest

from tests.aircraft_helpers import aircraft_session
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import (
    combat_session,
    declare_shooting,
    finish_attacks,
    shooting_request,
    weapon_rows,
)
from tests.support.section05_fixtures import replace_unit
from tests.support.section09_fixtures import movement_mission
from tests.support.section11_fixtures import begin as begin_charge
from tests.support.section11_fixtures import session_for as charge_session
from tests.support.section11_fixtures import state_case
from tests.support.section12_fixtures import (
    checkpoint,
    declare,
    engaged_case,
    select_fight,
)
from tests.support.section12_fixtures import session_for as fight_session
from tests.support.section20_fixtures import (
    ingress_request,
    reserve_scene,
    submit_ingress,
)
from tests.support.section23_fixtures import scene
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import PLUNGING_FIRE_RULE_ID
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("aircraft_attacker", [False, True])
def test_public_native_shooting_accepts_aircraft_without_plunging_effect(
    section23_definitions: Section02Definitions, aircraft_attacker: bool
) -> None:
    d = section23_definitions
    state, own, target = scene(d, aircraft_attacker=aircraft_attacker)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    session = combat_session(d, state, movement_mission())
    request = shooting_request(session, own.unit_instance_id)
    before = state.to_payload()
    records = session.lifecycle.decision_controller.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="s23:malformed", payload={}
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == records
    rows = weapon_rows(request)[:1]
    assert rows
    declare_shooting(session, request, rows, [target.unit_instance_id])
    finish_attacks(session)
    events = session.lifecycle.decision_controller.event_log.records
    completed = next(e for e in events if e.event_type == "attack_sequence_completed")
    assert isinstance(completed.payload, dict)
    identity = completed.payload["sequence_id"]
    assert isinstance(identity, str)
    sequence = completed_attack_sequence(event_records=events, sequence_id=identity)
    assert sequence.is_complete
    assert sequence.attack_pools
    assert all(PLUNGING_FIRE_RULE_ID not in p.targeting_rule_ids for p in sequence.attack_pools)
    for viewer in state.player_ids:
        view = session.view(viewer_player_id=viewer)
        assert json.loads(json.dumps(view)) == view
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)["events"]


def test_public_charge_excludes_aircraft_and_rejects_invented_selection_atomically(
    section23_definitions: Section02Definitions,
) -> None:
    state, own, _ = state_case(section23_definitions)
    own = with_unit_keywords(own, keywords=(*own.keywords, "AIRCRAFT", "FLY"))
    replace_unit(state, own)
    session = charge_session(section23_definitions, state)
    request = begin_charge(session)
    assert own.unit_instance_id not in {o.option_id for o in request.options}
    assert "section02:spare" in {o.option_id for o in request.options}
    before = state.to_payload()
    records = session.lifecycle.decision_controller.to_payload()
    with pytest.raises(GameLifecycleError, match="parameterized request"):
        session.submit_parameterized_payload(
            request_id=request.request_id, result_id="s23:wrong-kind", payload={}
        )
    assert state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == records
    assert not any(
        e.event_type == "charge_roll_started"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s23:valid-spare",
        option_id="section02:spare",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert any(
        e.event_type == "charge_roll_started"
        for e in session.lifecycle.decision_controller.event_log.records
    )


@pytest.mark.parametrize("flying", [False, True])
def test_public_fight_weapon_choices_keep_aircraft_target_fly_requirement(
    section23_definitions: Section02Definitions, flying: bool
) -> None:
    state, own, target = engaged_case(section23_definitions)
    target = with_unit_keywords(target, keywords=(*target.keywords, "AIRCRAFT", "FLY"))
    replace_unit(state, target)
    if flying:
        own = with_unit_keywords(own, keywords=(*own.keywords, "FLY"))
        replace_unit(state, own)
    checkpoint(state, FightPhaseStepKind.FIGHT)
    session = fight_session(section23_definitions, state)
    request = select_fight(session, own.unit_instance_id)
    if flying:
        assert request.decision_type == "submit_melee_declaration"
        rows = weapon_rows(request)
        assert rows
        for row in rows:
            targets = row["engaged_target_unit_instance_ids"]
            assert isinstance(targets, list)
            assert target.unit_instance_id in targets
        status = declare(session)
        assert status.status_kind is not LifecycleStatusKind.INVALID
        finish_attacks(session)
        assert any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        )
    else:
        # With no legal targets, the public owner consumes the empty selection
        # immediately. It emits no melee attack sequence or declaration request.
        assert request.decision_type == "select_fight_activation"
        assert all(
            not isinstance(o.payload, dict)
            or o.payload.get("unit_instance_id") != own.unit_instance_id
            for o in request.options
        )
        assert not any(
            e.event_type
            in {"melee_declaration_accepted", "attack_sequence_step", "attack_sequence_completed"}
            for e in session.lifecycle.decision_controller.event_log.records
        )
    for viewer in state.player_ids:
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)["events"]


def test_supported_core_aircraft_departure_restores_and_replays_exactly() -> None:
    # Canonical supported Core checkpoint. This does not admit a native Aircraft
    # provider or turn the separate native scenes into legal roster fixtures.
    session = aircraft_session(fleet_size=2)
    initial = session.lifecycle.to_payload()
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    assert len(state.reserve_states) == 2
    assert all(r.is_unarrived for r in state.reserve_states)
    final = session.lifecycle.to_payload()
    clone = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert clone.lifecycle.to_payload() == final
    for viewer in state.player_ids:
        assert clone.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert clone.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="s23:aircraft-return",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay


def test_public_native_aircraft_ingress_preserves_keyword_and_actual_placement(
    section23_definitions: Section02Definitions,
) -> None:
    from tests.support.section23_fixtures import LORD

    s = reserve_scene(section23_definitions, sheet=LORD)
    unit = with_unit_keywords(s.unit, keywords=(*s.unit.keywords, "AIRCRAFT", "FLY"))
    replace_unit(s.state, unit)
    session = s.session()
    request = ingress_request(session, unit)
    before = s.state.to_payload()
    records = session.lifecycle.decision_controller.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s23:bad-ingress",
        payload={},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == records
    status = submit_ingress(session, request, unit, (Pose.at(2, 15),), result_id="s23:arrive")
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert s.state.battlefield_state is not None
    placed = s.state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    assert placed.model_placements[0].pose == Pose.at(2, 15)
    assert s.state.phase_movement_history[-1].is_ingress
    assert (
        "AIRCRAFT"
        in rules_unit_view_by_id(state=s.state, unit_instance_id=unit.unit_instance_id).keywords
    )
    for viewer in s.state.player_ids:
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)["events"]
