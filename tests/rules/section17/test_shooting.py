"""17.03 and diagram A/B: native candidates, source penalties and public attack use."""

import json
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import scenario
from tests.support.section04_fixtures import finish_attacks, pending, weapon_rows
from tests.support.section10_fixtures import accepted_pools, declaration_request, submit
from tests.support.section17_fixtures import (
    DEFILER,
    LORD,
    PRINCE,
    shooting_scene,
    vehicle_diagram_scene,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.shooting_engagement import (
    CLOSE_QUARTERS_SHOOTING_SOURCE_ID,
    ENGAGED_TARGET_SOURCE_ID,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.engine.shooting_types import ShootingType


@pytest.mark.parametrize("target_sheet", [PRINCE, DEFILER, LORD])
@pytest.mark.parametrize("blast", [False, True])
@pytest.mark.parametrize("engaged", [False, True])
def test_unengaged_shooter_selects_only_engaged_monster_vehicle_without_blast(
    section17_definitions: Section02Definitions,
    target_sheet: str,
    blast: bool,
    engaged: bool,
) -> None:
    d = section17_definitions
    _session, state, attacker, target = shooting_scene(
        d, target_sheet=target_sheet, third_party=engaged
    )
    assert state.current_battle_phase is not None
    assert state.current_battle_phase.value == "shooting"
    assert state.active_player_id == "owner"
    native = d.weapon(f"{LORD}:bolt-pistol")
    # Native pistol is the positive; BLAST is an explicit Core weapon-keyword
    # combination control. Native equipped BLAST is exercised via Defiler below.
    profile = replace(native, keywords=(*native.keywords, WeaponKeyword.BLAST)) if blast else native
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_model_ids()[0],
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
    )
    expected = not engaged or (target_sheet != LORD and not blast)
    assert result.is_legal is expected, result
    assert (
        ShootingTargetCandidate.from_payload(json.loads(json.dumps(result.to_payload()))) == result
    )
    if expected:
        assert result.shooting_types == (ShootingType.NORMAL,)
        assert result.hit_roll_modifier == (-1 if engaged else 0)
        assert (ENGAGED_TARGET_SOURCE_ID in result.targeting_rule_ids) is engaged
        assert result.line_of_sight_witness is not None
        assert result.target_visible_model_ids
        assert result.target_in_range_model_ids


@pytest.mark.parametrize("mutual", [False, True])
@pytest.mark.parametrize("close_quarters", [False, True])
def test_target_penalty_exemption_requires_own_engagement_and_close_quarters_weapon(
    section17_definitions: Section02Definitions,
    mutual: bool,
    close_quarters: bool,
) -> None:
    d = section17_definitions
    _session, state, attacker, target = shooting_scene(
        d, attacker_sheet=DEFILER, target_sheet=PRINCE, mutual=mutual, third_party=True
    )
    profile = d.weapon(f"{DEFILER}:excruciator-cannon")
    if close_quarters:
        profile = replace(profile, keywords=(*profile.keywords, WeaponKeyword.CLOSE_QUARTERS))
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_model_ids()[0],
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
    )
    assert result.is_legal, result
    exempt = mutual and close_quarters
    assert result.hit_roll_modifier == (0 if exempt else -2 if mutual else -1)
    assert (ENGAGED_TARGET_SOURCE_ID in result.targeting_rule_ids) is (not exempt)
    assert (CLOSE_QUARTERS_SHOOTING_SOURCE_ID in result.targeting_rule_ids) is (
        mutual and not exempt
    )
    assert result.shooting_types == (
        (ShootingType.CLOSE_QUARTERS,) if mutual else (ShootingType.NORMAL,)
    )


@pytest.mark.parametrize("target_sheet", [PRINCE, DEFILER])
def test_diagram_a_normal_shooting_penalty_reaches_real_attacks_and_both_viewers(
    section17_definitions: Section02Definitions,
    target_sheet: str,
) -> None:
    session, state, attacker, target = shooting_scene(
        section17_definitions, target_sheet=target_sheet
    )
    request = declaration_request(session, attacker, "normal")
    row = next(r for r in weapon_rows(request) if r["wargear_id"] == f"{LORD}:bolt-pistol")
    status = submit(session, [row], [target.unit_instance_id], "normal")
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    pool = accepted_pools(session)[0]
    assert pool["shooting_type"] == "normal"
    assert pool["hit_roll_modifier"] == -1
    rule_ids = pool["targeting_rule_ids"]
    assert isinstance(rule_ids, list)
    assert ENGAGED_TARGET_SOURCE_ID in rule_ids
    finish_attacks(session)
    records = session.lifecycle.decision_controller.event_log.records
    assert len([e for e in records if e.event_type == "attack_sequence_completed"]) == 1
    assert state.shooting_phase_state is not None
    assert attacker.unit_instance_id in state.shooting_phase_state.shot_unit_ids
    for viewer in state.player_ids:
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert session.view(viewer_player_id=viewer)


@pytest.mark.parametrize("attacker_sheet", [LORD, PRINCE, DEFILER])
def test_diagram_b_engagement_does_not_grant_infantry_normal_shooting(
    section17_definitions: Section02Definitions,
    attacker_sheet: str,
) -> None:
    d = section17_definitions
    session, _state, attacker, target = shooting_scene(
        d, attacker_sheet=attacker_sheet, target_sheet=DEFILER, mutual=True, third_party=False
    )
    from tests.support.section04_fixtures import choose

    choose(session, pending(session), attacker.unit_instance_id)
    assert {o.option_id for o in pending(session).options} == {"close_quarters"}
    choose(session, pending(session), "close_quarters")
    suffix = (
        "bolt-pistol"
        if attacker_sheet == LORD
        else "infernal-cannon"
        if attacker_sheet == PRINCE
        else "excruciator-cannon"
    )
    row = next(
        r for r in weapon_rows(pending(session)) if r["wargear_id"] == f"{attacker_sheet}:{suffix}"
    )
    before = session.lifecycle.to_payload()
    invalid = submit(session, [row], [target.unit_instance_id], "normal")
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    status = submit(
        session, [row], [target.unit_instance_id], "close_quarters", result_id="s17:close"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    pool = accepted_pools(session)[0]
    assert pool["shooting_type"] == "close_quarters"
    assert pool["hit_roll_modifier"] == (0 if attacker_sheet == LORD else -2)
    rule_ids = pool["targeting_rule_ids"]
    assert isinstance(rule_ids, list)
    assert (ENGAGED_TARGET_SOURCE_ID in rule_ids) is (attacker_sheet != LORD)


def test_equipped_native_blast_rejects_engaged_target_before_queue_pop_and_retries(
    section17_definitions: Section02Definitions,
) -> None:
    session, _state, attacker, target = shooting_scene(
        section17_definitions, attacker_sheet=DEFILER, target_sheet=PRINCE
    )
    request = declaration_request(session, attacker, "normal")
    rows = weapon_rows(request)
    blast = next(r for r in rows if r["wargear_id"] == f"{DEFILER}:hades-battle-cannon")
    plain = next(r for r in rows if r["wargear_id"] == f"{DEFILER}:excruciator-cannon")
    before = session.lifecycle.to_payload()
    invalid = submit(session, [blast], [target.unit_instance_id], "normal")
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    accepted = submit(
        session, [plain], [target.unit_instance_id], "normal", result_id="s17:plain-retry"
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    assert accepted_pools(session)[0]["hit_roll_modifier"] == -1


def test_stale_engaged_target_keyword_loss_rejects_original_option_atomically(
    section17_definitions: Section02Definitions,
) -> None:
    d = section17_definitions
    session, state, attacker, target = shooting_scene(d, target_sheet=PRINCE)
    request = declaration_request(session, attacker, "normal")
    row = weapon_rows(request)[0]
    from tests.support.section05_fixtures import replace_unit
    from tests.unit_keyword_helpers import with_unit_keywords

    # Explicit source-policy loss checkpoint, not a native keyword-loss provider.
    changed = with_unit_keywords(
        target, keywords=tuple(k for k in target.keywords if k != "MONSTER")
    )
    replace_unit(state, changed)
    before = session.lifecycle.to_payload()
    result = submit(session, [row], [target.unit_instance_id], "normal")
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending(session).request_id == request.request_id


@pytest.mark.parametrize("target", ["enemy:target", "enemy:a"])
@pytest.mark.parametrize("blast", [False, True])
def test_diagram_vehicle_can_shoot_a_or_b_with_target_specific_blast_restriction(
    section17_definitions: Section02Definitions,
    target: str,
    blast: bool,
) -> None:
    session, _state, vehicle = vehicle_diagram_scene(section17_definitions)
    request = declaration_request(session, vehicle, "close_quarters")
    rows = weapon_rows(request)
    suffix = "hades-battle-cannon" if blast else "excruciator-cannon"
    row = next(r for r in rows if r["wargear_id"] == f"{DEFILER}:{suffix}")
    before = session.lifecycle.to_payload()
    result = submit(session, [row], [target], "close_quarters")
    forbidden = blast and target == "enemy:target"
    assert (result.status_kind is LifecycleStatusKind.INVALID) is forbidden
    if forbidden:
        assert session.lifecycle.to_payload() == before
        result = submit(session, [row], ["enemy:a"], "close_quarters", result_id="s17:blast-other")
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    pool = accepted_pools(session)[0]
    assert pool["hit_roll_modifier"] == -1
    rule_ids = pool["targeting_rule_ids"]
    assert isinstance(rule_ids, list)
    assert CLOSE_QUARTERS_SHOOTING_SOURCE_ID in rule_ids
    assert ENGAGED_TARGET_SOURCE_ID not in rule_ids


@pytest.mark.parametrize("target", ["enemy:target", "enemy:a"])
def test_diagram_vehicle_close_quarters_exemption_only_for_engaged_infantry(
    section17_definitions: Section02Definitions,
    target: str,
) -> None:
    d = section17_definitions
    _session, state, vehicle = vehicle_diagram_scene(d)
    native = d.weapon(f"{DEFILER}:excruciator-cannon")
    # Declared Core weapon-keyword premise, not native Defiler equipment.
    profile = replace(native, keywords=(*native.keywords, WeaponKeyword.CLOSE_QUARTERS))
    candidate = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=vehicle,
        attacker_model_instance_id=vehicle.own_model_ids()[0],
        weapon_profile=profile,
        target_unit_id=target,
    )
    assert candidate.is_legal
    assert candidate.hit_roll_modifier == (0 if target == "enemy:target" else -1)


def test_faq51_destroyed_model_does_not_supply_target_unit_monster_keyword(
    section17_definitions: Section02Definitions,
) -> None:
    from tests.support.section03_fixtures import native_state
    from tests.support.section17_fixtures import SPAWN
    from tests.unit_keyword_helpers import with_model_keywords
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    d = section17_definitions
    target = d.unit(SPAWN, identity="target", army_id="enemy")
    first, second = target.own_models
    # Heterogeneous keyword contract: no native MONSTER Spawn provider claimed.
    first = with_model_keywords(first, keywords=(*first.keywords, "MONSTER"))
    target = replace(target, own_models=(first, second))
    attacker = d.unit(LORD)
    state = native_state(
        d, attacker, enemy=target, enemy_poses=(Pose.at(22, 10), Pose.at(22, 12.5))
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=target.unit_instance_id)
    assert "MONSTER" in view.keywords
    from tests.support.section05_fixtures import replace_unit

    replace_unit(state, replace(target, own_models=(replace(first, wounds_remaining=0), second)))
    living = rules_unit_view_by_id(state=state, unit_instance_id=target.unit_instance_id)
    assert "MONSTER" not in living.keywords
    assert living.alive_models() == (second,)
