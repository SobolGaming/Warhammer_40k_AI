"""Native three-weapon sequence, target priority, and replacement through the facade."""

from typing import cast

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section04_fixtures import (
    add_enemy,
    choose,
    combat_session,
    combat_state,
    declare_shooting,
    finish_attacks,
    pending,
    shooting_request,
    weapon_rows,
)
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.attack_sequence_selection import unresolved_target_unit_ids
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.wargear_selections import WargearSelection
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("split", [False, True])
def test_native_resolution_finishes_current_target_before_switching(
    section04_definitions: Section02Definitions, section04_mission: MissionSetup, split: bool
) -> None:
    d = section04_definitions
    unit = d.unit(
        LORD_EXULTANT,
        wargear=(
            WargearSelection(
                f"{LORD_EXULTANT}:phoenix-power-spear-screamer-pistol:option-2",
                f"{LORD_EXULTANT}:lord-exultant",
                (f"{LORD_EXULTANT}:screamer-pistol",),
            ),
        ),
    )
    state = combat_state(d, unit)
    add_enemy(d, state)
    session = combat_session(d, state, section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    rows: list[dict[str, JsonValue]] = []
    for row in weapon_rows(request):
        if not any(r["weapon_instance_id"] == row["weapon_instance_id"] for r in rows):
            rows.append(row)
    assert len(rows) == 3
    targets = ["enemy:target", "enemy:target", "enemy:other" if split else "enemy:target"]
    declare_shooting(session, request, rows, targets)
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.attack_sequence is not None
    sequence = state.shooting_phase_state.attack_sequence
    assert unresolved_target_unit_ids(sequence) == tuple(sorted(set(targets)))
    assert (len(unresolved_target_unit_ids(sequence)) == 1) is (not split)
    assert not any(
        e.event_type == "attack_sequence_step"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    request = pending(session)
    if split:
        assert request.decision_type == "select_resolve_target_unit"
        assert request.actor_id == "owner"
        assert {o.option_id for o in request.options} == {
            "resolve-target:enemy:target",
            "resolve-target:enemy:other",
        }
        choose(session, request, "resolve-target:enemy:target")
    request = pending(session)
    assert request.decision_type == "select_attack_weapon_group"
    assert len(request.options) == (2 if split else 3)
    finish_attacks(session)
    events = session.lifecycle.decision_controller.event_log.records
    completed = next(e for e in events if e.event_type == "attack_sequence_completed")
    sequence = completed_attack_sequence(
        event_records=events,
        sequence_id=cast(str, cast(dict[str, JsonValue], completed.payload)["sequence_id"]),
    )
    assert sequence.is_complete
    assert set(sequence.used_pool_indices) == {0, 1, 2}
    assert [p.target_unit_instance_id for p in sequence.attack_pools] == targets
    hit_indices = [
        cast(int, cast(dict[str, JsonValue], e.payload)["pool_index"])
        for e in events
        if e.event_type == "attack_sequence_step"
        and cast(dict[str, JsonValue], e.payload)["step"] == "hit"
    ]
    assert set(hit_indices) == {0, 1, 2}
    assert all(hit_indices.count(i) == p.attacks for i, p in enumerate(sequence.attack_pools))
    if split:
        assert max(i for i, p in enumerate(hit_indices) if p in {0, 1}) < hit_indices.index(2)
    assert unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids


@pytest.mark.parametrize("replace_target", [False, True])
def test_ineligible_native_target_offers_optional_replacement(
    section04_definitions: Section02Definitions,
    section04_mission: MissionSetup,
    replace_target: bool,
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit)
    add_enemy(d, state)
    session = combat_session(d, state, section04_mission)
    request = shooting_request(session, unit.unit_instance_id)
    declare_shooting(session, request, weapon_rows(request)[:2], ["enemy:target", "enemy:other"])
    request = pending(session)
    assert request.decision_type == "select_resolve_target_unit"
    # Explicit post-declaration geometry contract. This tests replacement, not
    # the separate rule which grants or executes an out-of-phase move.
    target = next(
        u for a in state.army_definitions for u in a.units if u.unit_instance_id == "enemy:target"
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            placement(target, (Pose.at(40, 35),), enemy=True)
        )
    )
    choose(session, request, "resolve-target:enemy:target")
    request = pending(session)
    assert request.decision_type == "select_target_replacement"
    assert request.actor_id == "owner"
    assert "target:enemy:other" in {o.option_id for o in request.options}
    option = (
        "target:enemy:other"
        if replace_target
        else next(o.option_id for o in request.options if not o.option_id.startswith("target:"))
    )
    choose(session, request, option)
    events = session.lifecycle.decision_controller.event_log.records
    event = next(e for e in events if e.event_type == "target_replacement_resolved")
    payload = cast(dict[str, JsonValue], event.payload)
    assert payload["replacement_target_ids"] == (["enemy:other"] if replace_target else None)
    finish_attacks(session)
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids
