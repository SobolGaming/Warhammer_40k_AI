"""10.04/05/06: physical native weapons reach real declaration and attack consumers."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import add_enemy, finish_attacks, pending, weapon_rows
from tests.support.section10_fixtures import (
    AVENGERS,
    DEFILER,
    LORD,
    SPINNER,
    WRAITHLORD,
    accepted_pools,
    assert_valid,
    case,
    declaration_request,
    shooting_mission,
    submit,
)
from tests.support.section10_fixtures import shooting_session as combat_session
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@pytest.mark.parametrize(
    ("sheet", "kind", "advance", "engaged"),
    [
        (LORD, "normal", False, False),
        (AVENGERS, "assault", True, False),
        (LORD, "close_quarters", False, True),
        (SPINNER, "indirect", False, False),
    ],
)
def test_each_type_resolves_native_attacks_before_next_selection_and_blocks_action(
    section10_definitions: Section02Definitions, sheet: str, kind: str, advance: bool, engaged: bool
) -> None:
    session, state, unit = case(section10_definitions, sheet, advance=advance, engaged=engaged)
    request = declaration_request(session, unit, kind)
    rows = weapon_rows(request)
    row = (
        next(r for r in rows if r["wargear_id"] == f"{sheet}:doomweaver")
        if kind == "indirect"
        else rows[0]
    )
    assert_valid(submit(session, [row], ["enemy:target"], kind))
    assert state.shooting_phase_state is not None
    completed = any(
        e.event_type == "attack_sequence_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    assert (unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids) is completed
    if not completed:
        assert pending(session).decision_type != "select_shooting_unit"
    finish_attacks(session)
    # A native Night Spinner may offer its optional post-shoot effect.
    if pending(session).decision_type == "select_catalog_post_shoot_hit_target_effect":
        from tests.support.section04_fixtures import choose

        choose(session, pending(session), pending(session).options[0].option_id)
    assert pending(session).decision_type == "select_shooting_unit"
    assert unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids
    events = session.lifecycle.decision_controller.event_log.records
    assert len([e for e in events if e.event_type == "attack_sequence_completed"]) == 1
    assert unit.unit_instance_id in state.shooting_phase_state.shot_unit_ids
    assert accepted_pools(session)[0]["shooting_type"] == kind
    assert session.events_since(EventStreamCursor(), viewer_player_id="owner")
    assert session.events_since(EventStreamCursor(), viewer_player_id="opponent")
    reason = mission_action_unit_ineligibility_reason(
        state=state,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    # Advance/engagement are independently sufficient restrictions; the explicit
    # activity owner below checks the shooting restriction even for these cases.
    from warhammer40k_core.engine.activity_restrictions import has_activity_restriction
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    assert reason is not None
    assert has_activity_restriction(
        state=state,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        activity="completed_shooting",
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert not has_activity_restriction(
        state=state,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        activity="completed_shooting",
    )


def test_assault_only_native_assault_weapons_are_admitted_then_legal_retry(
    section10_definitions: Section02Definitions,
) -> None:
    session, _state, unit = case(section10_definitions, SPINNER, advance=True)
    declaration_request(session, unit, "assault")
    rows = weapon_rows(pending(session))
    assert all(r["wargear_id"] == f"{SPINNER}:twin-shuriken-catapult" for r in rows)
    # Malformed profile identity cannot use the indirect weapon as Assault.
    wrong = dict(rows[0])
    wrong["weapon_profile_id"] = f"{SPINNER}:doomweaver:standard"
    wrong["wargear_id"] = f"{SPINNER}:doomweaver"
    before = session.lifecycle.to_payload()
    result = submit(session, [wrong], ["enemy:target"], "assault")
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert_valid(submit(session, [rows[0]], ["enemy:target"], "assault", result_id="legal"))
    assert accepted_pools(session)[0]["wargear_id"] == rows[0]["wargear_id"]


@pytest.mark.parametrize(
    ("sheet", "suffix", "target", "valid", "modifier"),
    [
        (LORD, "bolt-pistol", "engaged", True, 0),
        (LORD, "bolt-pistol", "outside", False, 0),
        (DEFILER, "excruciator-cannon", "engaged", True, -1),
        (DEFILER, "excruciator-cannon", "outside", True, -1),
        (DEFILER, "hades-battle-cannon", "engaged", False, 0),
        (DEFILER, "hades-battle-cannon", "outside", True, -1),
        (WRAITHLORD, "shuriken-catapult", "engaged", True, -1),
        (WRAITHLORD, "shuriken-catapult", "outside", True, -1),
    ],
)
def test_close_quarters_model_weapon_target_and_hit_penalty_policy(
    section10_definitions: Section02Definitions,
    sheet: str,
    suffix: str,
    target: str,
    valid: bool,
    modifier: int,
) -> None:
    # Insert an unengaged target before the phase builds its public candidates.
    from tests.support.section04_fixtures import combat_state

    d = section10_definitions
    unit = d.unit(sheet)
    state = combat_state(d, unit, distance=5 if sheet == DEFILER else 2.5)
    add_enemy(d, state, identity="outside", x=10, y=22)
    session = combat_session(d, state, shooting_mission())
    request = declaration_request(session, unit, "close_quarters")
    rows = weapon_rows(request)
    row = next(r for r in rows if r["wargear_id"] == f"{sheet}:{suffix}")
    target_id = "enemy:target" if target == "engaged" else "enemy:outside"
    before = session.lifecycle.to_payload()
    result = submit(session, [row], [target_id], "close_quarters")
    assert (result.status_kind is not LifecycleStatusKind.INVALID) is valid
    if not valid:
        assert session.lifecycle.to_payload() == before
        legal = next(
            r
            for r in rows
            if r["wargear_id"]
            == f"{sheet}:" + ("bolt-pistol" if sheet == LORD else "excruciator-cannon")
        )
        assert_valid(
            submit(session, [legal], ["enemy:target"], "close_quarters", result_id="legal")
        )
    else:
        pool = accepted_pools(session)[0]
        assert pool["hit_roll_modifier"] == modifier
        assert pool["target_unit_instance_id"] == target_id
        # This declaration boundary proves native geometry and penalty provenance;
        # full natural attack continuation is exercised once per type above.


@pytest.mark.parametrize("bad_kind", ["assault", "close_quarters", "indirect"])
def test_declaration_cannot_change_the_selected_type(
    section10_definitions: Section02Definitions, bad_kind: str
) -> None:
    session, _state, unit = case(section10_definitions)
    declaration_request(session, unit, "normal")
    rows = weapon_rows(pending(session))[:1]
    before = session.lifecycle.to_payload()
    result = submit(session, rows, ["enemy:target"], bad_kind)
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert_valid(submit(session, rows, ["enemy:target"], "normal", result_id="legal-type"))
