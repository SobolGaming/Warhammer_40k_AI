"""12.02/06/07 additional native movement continuation consumers."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section12_fixtures import (
    LORD,
    add_native,
    begin,
    checkpoint,
    declare,
    engaged_case,
    events,
    finish_activation,
    move_payload,
    paths,
    select_fight,
    session_for,
    set_pose,
    submit_move,
)
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import unit_is_currently_engaged
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("charged", [True, False])
def test_initial_pile_in_admits_unengaged_charger_and_moves_to_nearby_target(
    section12_definitions: Section02Definitions,
    charged: bool,
) -> None:
    s, u, e = engaged_case(section12_definitions)
    # Constructed later phase checkpoint: native units START engaged, then the
    # target is displaced; the charge permission is explicitly granted, not replayed.
    set_pose(s, e, (Pose.at(14.5, 10),), enemy=True)
    assert not unit_is_currently_engaged(state=s, unit_instance_id=u.unit_instance_id)
    ally = section12_definitions.unit(LORD, identity="z-sentinel")
    foe = section12_definitions.unit(LORD, army_id="enemy", identity="z-sentinel")
    add_native(s, ally, (Pose.at(10, 30),))
    add_native(s, foe, (Pose.at(13, 30),), enemy=True)
    if charged:
        s.record_persisting_effect(
            PersistingEffect(
                effect_id="constructed:s12:charged",
                source_rule_id="constructed:s12:charged",
                owner_player_id="owner",
                target_unit_instance_ids=(u.unit_instance_id,),
                started_battle_round=1,
                started_phase=BattlePhase.FIGHT,
                expiration=EffectExpiration.end_turn(battle_round=1, player_id="owner"),
                effect_payload={"effect_kind": "charge_grants_fights_first"},
            )
        )
    checkpoint(s, FightPhaseStepKind.PILE_IN)
    session = session_for(section12_definitions, s)
    r = begin(session)
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.proposal_kind.value == "pile_in"
    assert m.unit_instance_id == (u.unit_instance_id if charged else ally.unit_instance_id)
    assert m.context is not None
    assert m.context.get("fight_movement_timing") != "overrun"
    if charged:
        result = submit_move(
            session, targets=(e.unit_instance_id,), witness=paths(s, (u.unit_instance_id,), 1)
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        assert unit_is_currently_engaged(state=s, unit_instance_id=u.unit_instance_id)
        completed = events(session, "fight_movement_completed")
        assert len(completed) == 1
        assert completed[0]["unit_instance_id"] == u.unit_instance_id
        assert not events(session, "fight_activation_selected")
        assert (
            MovementProposalRequest.from_decision_request_payload(
                pending(session).payload
            ).unit_instance_id
            == ally.unit_instance_id
        )
    else:
        assert not events(session, "fight_movement_completed")
        assert not unit_is_currently_engaged(state=s, unit_instance_id=u.unit_instance_id)


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_consolidation_orders_all_active_units_before_opponent_once_each(
    section12_definitions: Section02Definitions,
    active: str,
) -> None:
    s, u, e = engaged_case(section12_definitions)
    s.active_player_id = active
    ally = section12_definitions.unit(LORD, identity="ally")
    foe = section12_definitions.unit(LORD, army_id="enemy", identity="foe")
    add_native(s, ally, (Pose.at(10, 20),))
    add_native(s, foe, (Pose.at(13, 20),), enemy=True)
    checkpoint(s, FightPhaseStepKind.CONSOLIDATE)
    session = session_for(section12_definitions, s)
    initial = s.battlefield_state
    chosen: list[tuple[str, str]] = []
    for i in range(4):
        r = begin(session)
        m = MovementProposalRequest.from_decision_request_payload(r.payload)
        assert m.proposal_kind.value == "consolidate"
        assert r.actor_id is not None
        chosen.append((r.actor_id, m.unit_instance_id))
        if i < 3:
            result = submit_move(session)
            assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        else:
            # Complete the actual final request with the same controller and
            # native handler, stopping at Fight END instead of processing missions.
            selection = replace(
                DecisionResult.for_request(
                    result_id="s12:last-consolidation",
                    request=r,
                    selected_option_id=r.options[0].option_id,
                ),
                payload=move_payload(r),
            )
            controller = session.lifecycle.decision_controller
            controller.submit_result(selection)
            handler = session.lifecycle._fight_phase_handler  # pyright: ignore[reportPrivateUsage]
            status = handler.apply_decision(state=s, result=selection, decisions=controller)
            assert status is None or status.status_kind is not LifecycleStatusKind.INVALID, status
            for _ in range(3):
                assert s.fight_phase_state is not None
                if s.fight_phase_state.current_step is FightPhaseStepKind.END:
                    break
                status = handler.begin_phase(state=s, decisions=controller)
                assert status.decision_request is None
            else:
                pytest.fail("bounded consolidation did not reach Fight END")
    other = "opponent" if active == "owner" else "owner"
    assert [p for p, _ in chosen] == [active, active, other, other]
    assert {i for _, i in chosen} == {
        u.unit_instance_id,
        ally.unit_instance_id,
        e.unit_instance_id,
        foe.unit_instance_id,
    }
    completed = events(session, "fight_movement_completed")
    assert [cast(str, x["unit_instance_id"]) for x in completed] == [i for _, i in chosen]
    assert [x["proposal_kind"] for x in completed] == ["consolidate"] * 4
    assert s.battlefield_state == initial
    assert not events(session, "fight_activation_selected")
    assert not events(session, "attack_sequence_step")


def test_overrun_pile_in_can_be_declined_then_native_attacks_complete(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, _ = engaged_case(section12_definitions)
    # Constructed newly-engaged Fight checkpoint, not a replayed earlier combat.
    checkpoint(s, FightPhaseStepKind.FIGHT, engaged_ids=())
    session = session_for(section12_definitions, s)
    r = select_fight(session, u.unit_instance_id, "overrun")
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.context is not None
    assert m.context["fight_movement_timing"] == "overrun"
    before = s.battlefield_state
    status = submit_move(session)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert s.battlefield_state == before
    assert pending(session).decision_type == "submit_melee_declaration"
    completed = events(session, "fight_movement_completed")
    assert len(completed) == 1
    assert completed[0]["unit_instance_id"] == u.unit_instance_id
    assert completed[0]["proposal_kind"] == "pile_in"
    status = declare(session)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    r = finish_activation(session)
    assert r.actor_id == "opponent"
    assert events(session, "attack_sequence_step")
    assert [
        cast(dict[str, JsonValue], x["activation_selection"])["unit_instance_id"]
        for x in events(session, "unit_has_fought")
    ] == [u.unit_instance_id]
