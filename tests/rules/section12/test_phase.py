"""12.00/02/04/05/06/07: public Fight sequencing from engaged native scenes."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import choose, pending
from tests.support.section12_fixtures import (
    LORD,
    add_native,
    begin,
    checkpoint,
    declare,
    engaged_case,
    events,
    finish_activation,
    finite_default,
    paths,
    select_fight,
    session_for,
    set_pose,
    submit_move,
)
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import ELIGIBLE_TO_FIGHT_PASS_OPTION_ID
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


def _grant(s: GameState, unit_id: str, owner: str, kind: str = "fights_first") -> None:
    s.record_persisting_effect(
        PersistingEffect(
            effect_id=f"constructed:{unit_id}:{kind}",
            source_rule_id="constructed:section12:ordering-permission",
            owner_player_id=owner,
            target_unit_instance_ids=(unit_id,),
            started_battle_round=1,
            started_phase=BattlePhase.FIGHT,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="owner"),
            effect_payload={"effect_kind": kind},
        )
    )


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_both_players_finish_all_optional_pile_ins_before_any_fight_then_consolidate(
    section12_definitions: Section02Definitions, active: str
) -> None:
    s, _u, _e = engaged_case(section12_definitions)
    s.active_player_id = active
    ally = section12_definitions.unit(LORD, identity="ally")
    foe = section12_definitions.unit(LORD, identity="foe", army_id="enemy")
    add_native(s, ally, (Pose.at(10, 20),))
    add_native(s, foe, (Pose.at(13, 20),), enemy=True)
    session = session_for(section12_definitions, s)
    moved: list[tuple[str, str]] = []
    for _ in range(4):
        r = begin(session)
        assert r.decision_type == "submit_movement_proposal"
        m = MovementProposalRequest.from_decision_request_payload(r.payload)
        assert m.proposal_kind.value == "pile_in"
        assert r.actor_id is not None
        moved.append((r.actor_id, m.unit_instance_id))
        result = submit_move(session)
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert [p for p, _ in moved] == [
        active,
        active,
        "opponent" if active == "owner" else "owner",
        "opponent" if active == "owner" else "owner",
    ]
    assert len({id_ for _, id_ in moved}) == 4
    assert not events(session, "fight_activation_selected")
    selected: list[tuple[str, str]] = []
    for _ in range(4):
        r = begin(session)
        assert r.decision_type == "select_fight_activation"
        option = next(
            o
            for o in r.options
            if isinstance(o.payload, dict) and o.payload.get("fight_type") == "normal"
        )
        assert r.actor_id is not None
        selected.append(
            (r.actor_id, cast(str, cast(dict[str, JsonValue], option.payload)["unit_instance_id"]))
        )
        choose(session, r, option.option_id)
        assert pending(session).decision_type == "submit_melee_declaration"
        result = declare(session)
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        finish_activation(session)
    assert [p for p, _ in selected] == [
        active,
        "opponent" if active == "owner" else "owner",
        active,
        "opponent" if active == "owner" else "owner",
    ]
    assert len({id_ for _, id_ in selected}) == 4
    r = begin(session)
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.proposal_kind.value == "consolidate"
    assert r.actor_id == active
    assert len(events(session, "fight_activation_selected")) == 4
    assert len(events(session, "unit_has_fought")) == 4
    assert events(session, "attack_sequence_step")
    kinds = [x["proposal_kind"] for x in events(session, "fight_movement_completed")]
    assert kinds == ["pile_in"] * 4


@pytest.mark.parametrize("grants", [(), ("owner",), ("opponent",), ("owner", "opponent")])
def test_first_band_and_remaining_band_handoff_use_current_player_and_eligibility(
    section12_definitions: Section02Definitions, grants: tuple[str, ...]
) -> None:
    s, u, e = engaged_case(section12_definitions)
    for p in grants:
        _grant(s, u.unit_instance_id if p == "owner" else e.unit_instance_id, p)
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    r = begin(session)
    first = "opponent" if grants == ("opponent",) else "owner"
    assert r.actor_id == first
    options = [cast(dict[str, JsonValue], o.payload) for o in r.options]
    assert {cast(str, o["unit_instance_id"]) for o in options} == {
        u.unit_instance_id if first == "owner" else e.unit_instance_id
    }
    assert {cast(str, o["ordering_band"]) for o in options} == {
        "fights_first" if grants else "remaining_combats"
    }
    choose(session, r, r.options[0].option_id)
    declare(session)
    finish_activation(session)
    r = begin(session)
    assert r.actor_id != first
    assert r.decision_type == "select_fight_activation"
    assert all(
        cast(str, cast(dict[str, JsonValue], o.payload)["unit_instance_id"])
        != (u.unit_instance_id if first == "owner" else e.unit_instance_id)
        for o in r.options
    )
    assert cast(str, cast(dict[str, JsonValue], r.options[0].payload)["ordering_band"]) == (
        "fights_first" if len(grants) == 2 else "remaining_combats"
    )


@pytest.mark.parametrize("gap", [5 - 0.001, 5, 5 + 0.001])
def test_pass_is_optional_only_when_every_eligible_unit_is_strictly_beyond_five(
    section12_definitions: Section02Definitions, gap: float
) -> None:
    s, u, e = engaged_case(section12_definitions)
    # Constructed Fight checkpoint after another combat removed engagement.
    set_pose(s, e, (Pose.at(10 + 1.574803149606299 + gap, 10),), enemy=True)
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert r.actor_id == "owner"
    assert (ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {o.option_id for o in r.options}) == (gap > 5)
    assert any(
        cast(dict[str, JsonValue], o.payload).get("fight_type") == "overrun" for o in r.options
    )
    if gap > 5:
        choose(session, r, ELIGIBLE_TO_FIGHT_PASS_OPTION_ID)
        r = begin(session)
        assert r.actor_id == "opponent"
        choose(session, r, ELIGIBLE_TO_FIGHT_PASS_OPTION_ID)
        r = begin(session)
        assert (
            MovementProposalRequest.from_decision_request_payload(r.payload).proposal_kind.value
            == "consolidate"
        )
        assert len(events(session, "eligible_to_fight_pass_recorded")) == 2
    else:
        r = select_fight(session, u.unit_instance_id, "overrun")
        context = MovementProposalRequest.from_decision_request_payload(r.payload).context
        assert context is not None
        assert context["fight_movement_timing"] == "overrun"


@pytest.mark.parametrize("was_engaged", [False, True])
def test_currently_engaged_normal_fight_and_newly_engaged_overrun_types(
    section12_definitions: Section02Definitions, was_engaged: bool
) -> None:
    s, u, e = engaged_case(section12_definitions)
    checkpoint(
        s,
        FightPhaseStepKind.FIGHT,
        engaged_ids=(u.unit_instance_id, e.unit_instance_id) if was_engaged else (),
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    types = {cast(str, cast(dict[str, JsonValue], o.payload)["fight_type"]) for o in r.options}
    assert types == ({"normal"} if was_engaged else {"normal", "overrun"})
    r = select_fight(session, u.unit_instance_id, "normal" if was_engaged else "overrun")
    assert r.decision_type == (
        "submit_melee_declaration" if was_engaged else "submit_movement_proposal"
    )
    if not was_engaged:
        m = MovementProposalRequest.from_decision_request_payload(r.payload)
        assert m.context is not None
        assert m.context["maximum_distance_inches"] == 3
        result = submit_move(
            session, targets=(e.unit_instance_id,), witness=paths(s, (u.unit_instance_id,), 0.25)
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        assert pending(session).decision_type == "submit_melee_declaration"
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    finish_activation(session)
    assert len(events(session, "fight_activation_selected")) == 1


@pytest.mark.parametrize("cause", ["step_start", "charge"])
def test_unengaged_eligible_unit_overruns_then_resolves_real_melee(
    section12_definitions: Section02Definitions, cause: str
) -> None:
    s, u, e = engaged_case(section12_definitions)
    set_pose(s, e, (Pose.at(14.5, 10),), enemy=True)
    if cause == "charge":
        _grant(s, u.unit_instance_id, "owner", "charge_grants_fights_first")
    checkpoint(
        s,
        FightPhaseStepKind.FIGHT,
        engaged_ids=(u.unit_instance_id, e.unit_instance_id) if cause == "step_start" else (),
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert all(
        cast(str, cast(dict[str, JsonValue], o.payload)["fight_type"]) == "overrun"
        for o in r.options
    )
    r = select_fight(session, u.unit_instance_id, "overrun")
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.context is not None
    assert m.context["fight_movement_timing"] == "overrun"
    before = s.battlefield_state
    result = submit_move(
        session, targets=(e.unit_instance_id,), witness=paths(s, (u.unit_instance_id,), -0.1)
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        witness=paths(s, (u.unit_instance_id,), 1),
        identity="legal",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert pending(session).decision_type == "submit_melee_declaration"
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    finish_activation(session)
    for _ in range(50):
        if events(session, "attack_sequence_completed"):
            break
        finite_default(session)
    else:
        pytest.fail("bounded native Overrun attacks did not finish")
    assert events(session, "attack_sequence_step")
    assert events(session, "unit_has_fought")
    assert len(events(session, "fight_movement_completed")) == 1


def test_single_pass_ends_when_opponent_has_no_eligible_units(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, e = engaged_case(section12_definitions)
    set_pose(s, e, (Pose.at(20, 10),), enemy=True)
    assert s.mission_setup is not None
    marker = replace(s.mission_setup.objective_markers[0], x_inches=13, y_inches=10)
    s.mission_setup = replace(s.mission_setup, objective_markers=(marker,))
    # The opponent was not eligible at the constructed Fight-step checkpoint.
    checkpoint(s, FightPhaseStepKind.FIGHT, engaged_ids=(u.unit_instance_id,))
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {o.option_id for o in r.options}
    choose(session, r, ELIGIBLE_TO_FIGHT_PASS_OPTION_ID)
    r = begin(session)
    assert (
        MovementProposalRequest.from_decision_request_payload(r.payload).proposal_kind.value
        == "consolidate"
    )
    assert len(events(session, "eligible_to_fight_pass_recorded")) == 1


def test_one_near_friendly_eligible_unit_prevents_passing_for_the_whole_player(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, _e = engaged_case(section12_definitions)
    far = section12_definitions.unit(LORD, identity="far")
    add_native(s, far, (Pose.at(40, 30),))
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID not in {o.option_id for o in r.options}
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["unit_instance_id"]) for o in r.options
    } == {
        u.unit_instance_id,
        far.unit_instance_id,
    }


def test_unengaged_uncharged_unit_without_start_eligibility_cannot_be_selected(
    section12_definitions: Section02Definitions,
) -> None:
    s, _u, e = engaged_case(section12_definitions)
    set_pose(s, e, (Pose.at(20, 10),), enemy=True)
    ally = section12_definitions.unit(LORD, identity="other")
    foe = section12_definitions.unit(LORD, identity="other", army_id="enemy")
    add_native(s, ally, (Pose.at(10, 20),))
    add_native(s, foe, (Pose.at(13, 20),), enemy=True)
    checkpoint(
        s, FightPhaseStepKind.FIGHT, engaged_ids=(ally.unit_instance_id, foe.unit_instance_id)
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert r.actor_id == "owner"
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["unit_instance_id"]) for o in r.options
    } == {ally.unit_instance_id}
    assert not events(session, "fight_activation_selected")


def test_pass_waits_for_enemy_overrun_to_bring_a_target_near_then_unit_fights(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, foe = engaged_case(section12_definitions, seed="section12-pass-wait")
    set_pose(s, foe, (Pose.at(17, 10),), enemy=True)
    ally = section12_definitions.unit(LORD, identity="ally")
    mid = section12_definitions.unit(LORD, identity="mid", army_id="enemy")
    add_native(s, ally, (Pose.at(14.2, 11),))
    add_native(s, mid, (Pose.at(17, 12.5),), enemy=True)
    # Constructed step-start inventory: u lost its initial target and foe became
    # engaged later. Every movement and attack after this checkpoint is genuine.
    checkpoint(
        s,
        FightPhaseStepKind.FIGHT,
        engaged_ids=(u.unit_instance_id, ally.unit_instance_id, mid.unit_instance_id),
    )
    session = session_for(section12_definitions, s)
    begin(session)
    select_fight(session, ally.unit_instance_id)
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    finish_activation(session)
    select_fight(session, mid.unit_instance_id)
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    r = finish_activation(session)
    assert r.actor_id == "owner"
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {o.option_id for o in r.options}
    choose(session, r, ELIGIBLE_TO_FIGHT_PASS_OPTION_ID)
    r = select_fight(session, foe.unit_instance_id, "overrun")
    assert r.decision_type == "submit_movement_proposal"
    result = submit_move(
        session,
        targets=(ally.unit_instance_id,),
        witness=paths(s, (foe.unit_instance_id,), -1.1, 0.1),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    r = finish_activation(session)
    from warhammer40k_core.engine.physical_engagement import (
        current_closest_physical_enemy_distance_inches,
    )

    distance = current_closest_physical_enemy_distance_inches(
        state=s, unit_instance_id=u.unit_instance_id
    )
    assert distance is not None
    assert 2 < distance < 5
    assert s.fight_phase_state is not None
    assert (
        u.unit_instance_id not in s.fight_phase_state.fight_order_state.selected_to_fight_unit_ids
    )
    assert r.actor_id == "owner"
    assert r.decision_type == "select_fight_activation"
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["unit_instance_id"]) for o in r.options
    } == {u.unit_instance_id}
    select_fight(session, u.unit_instance_id, "overrun")
    result = submit_move(
        session, targets=(foe.unit_instance_id,), witness=paths(s, (u.unit_instance_id,), 2.5)
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    finish_activation(session)
    assert len(events(session, "eligible_to_fight_pass_recorded")) == 1
    assert len(events(session, "fight_activation_selected")) == 4
    assert len(events(session, "unit_has_fought")) == 4
