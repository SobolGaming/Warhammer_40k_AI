from typing import cast

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import (
    choose,
    combat_session,
    combat_state,
    declare_shooting,
    finish_attacks,
    pending,
    shooting_payload,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase
from warhammer40k_core.engine.phase import LifecycleStatusKind


@pytest.mark.parametrize("weapons", [1, 2])
def test_native_shooting_selection_declaration_and_completed_participation(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup, weapons: int
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(d, combat_state(d, unit), section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    assert request.decision_type == "submit_shooting_declaration"
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    before = session.lifecycle.decision_controller.event_log.records
    assert not any(e.event_type == "attack_sequence_step" for e in before)
    rows = weapon_rows(request)[:weapons]
    declare_shooting(session, request, rows, ["enemy:target"] * weapons)
    finish_attacks(session)
    events = session.lifecycle.decision_controller.event_log.records
    completed = next(e for e in events if e.event_type == "attack_sequence_completed")
    sequence = completed_attack_sequence(
        event_records=events,
        sequence_id=cast(str, cast(dict[str, JsonValue], completed.payload)["sequence_id"]),
    )
    assert sequence.is_complete
    assert len(sequence.attack_pools) == weapons
    assert {p.weapon_instance_id for p in sequence.attack_pools} == {
        cast(str, r["weapon_instance_id"]) for r in rows
    }
    assert all(p.target_unit_instance_id == "enemy:target" for p in sequence.attack_pools)
    for pool in sequence.attack_pools:
        assert pool.weapon_profile == d.weapon(pool.wargear_id)
        assert pool.attacks == pool.weapon_profile.attack_profile.fixed_attacks
        assert model_has_attacked_this_phase(
            event_records=events,
            model_instance_id=pool.attacker_model_instance_id,
            battle_round=1,
            active_player_id="owner",
            phase="shooting",
        )
    steps = [i for i, e in enumerate(events) if e.event_type == "attack_sequence_step"]
    assert steps
    assert max(steps) < events.index(completed)
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids
    assert session.events_since(EventStreamCursor(), viewer_player_id="owner")
    assert session.events_since(EventStreamCursor(), viewer_player_id="opponent")


@pytest.mark.parametrize(("distance", "select_weapons"), [(8, False), (8, True), (40, False)])
def test_declining_legal_targets_completes_selection_without_shot(
    section04_definitions: Section02Definitions,
    section04_mission: MissionSetup,
    select_weapons: bool,
    distance: int,
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(d, combat_state(d, unit, distance=distance), section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    if distance == 8:
        rows = weapon_rows(request)[:2] if select_weapons else []
        declare_shooting(session, request, rows, [None] * len(rows))
    else:
        assert request.decision_type == "select_shooting_unit"
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    events = session.lifecycle.decision_controller.event_log.records
    assert not any(e.event_type == "attack_sequence_step" for e in events)
    assert any(
        e.event_type
        == (
            "shooting_declaration_accepted"
            if distance == 8
            else "shooting_without_attacks_completed"
        )
        for e in events
    )
    assert pending(session).decision_type == "select_shooting_unit"


def test_faq02_native_weaponless_shooter_resolves_type_without_attacks(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup
) -> None:
    d = section04_definitions
    unit = d.unit(CHAOS_SPAWN)
    session = combat_session(d, combat_state(d, unit), section04_mission)
    choose(session, pending(session), unit.unit_instance_id)
    request = pending(session)
    assert request.decision_type == "select_shooting_type"
    choose(session, request, "normal")
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "shooting_without_attacks_completed" for e in events)
    assert not any(
        e.event_type in {"shooting_declaration_accepted", "attack_sequence_step"} for e in events
    )


@pytest.mark.parametrize("alternate", [False, True])
def test_one_physical_weapon_cannot_commit_both_profiles_then_legal_retry(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup, alternate: bool
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    session = combat_session(d, combat_state(d, unit), section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    rows = [r for r in weapon_rows(request) if r["wargear_id"] == f"{LORD_EXULTANT}:plasma-pistol"]
    assert len(rows) == 2
    assert rows[0]["weapon_instance_id"] == rows[1]["weapon_instance_id"]
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="duplicate",
        payload=shooting_payload(request, rows, ["enemy:target"] * 2),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending(session) == request
    declare_shooting(session, request, [rows[int(alternate)]], ["enemy:target"])
    accepted = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "shooting_declaration_accepted"
    )
    pools = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], accepted.payload)["attack_pools"]
    )
    assert len(pools) == 1
    assert pools[0]["weapon_profile_id"] == rows[int(alternate)]["weapon_profile_id"]
    assert pools[0]["weapon_instance_id"] == rows[0]["weapon_instance_id"]
