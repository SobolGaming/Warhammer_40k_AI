"""World Eaters source-backed consumer outcomes, beyond profile inspection."""

import math
from typing import cast

import pytest
from tests.charge_distance_helpers import move_payload, select_targets
from tests.factions.world_eaters.attack_helpers import resolve_native_attack
from tests.factions.world_eaters.gameplay_helpers import (
    ENEMY,
    SOURCE,
    complete_activation,
    events,
    gameplay_session,
    move_fight,
    reach,
    select_blessings,
)
from tests.factions.world_eaters.world_eaters_helpers import _unit_by_id
from tests.fight_completion_positive_helpers import assert_completed_melee
from tests.fight_distance_helpers import set_fight_distance_step
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import army_rule
from warhammer40k_core.engine.fight_resolution import fight_movement_maximum_distance_inches
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind


@pytest.mark.parametrize("kind", ["pile_in", "consolidate"])
def test_rage_fuelled_invigoration_moves_beyond_three_inches(kind: str) -> None:
    session = (
        gameplay_session(game_id="we-rage-pile-in", enemy_x=16.5)
        if kind == "pile_in"
        else gameplay_session(game_id="we-rage-consolidate-0", lethal=True, extra_enemy_x=14.5)
    )
    select_blessings(session, army_rule.BlessingOfKhorne.RAGE_FUELLED_INVIGORATION)
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    for _ in range(40):
        request = reach(session, "submit_movement_proposal")
        candidate = MovementProposalRequest.from_decision_request_payload(request.payload)
        state = session.lifecycle.state
        assert state is not None
        assert state.battle_round == 1
        assert state.current_battle_phase is BattlePhase.FIGHT
        if candidate.unit_instance_id == SOURCE and candidate.proposal_kind.value == kind:
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError(f"Did not reach source {kind}")
    assert request.decision_type == "submit_movement_proposal"
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert move.unit_instance_id == SOURCE
    assert move.context is not None
    assert move.context["maximum_distance_inches"] == 6.0
    if kind == "pile_in":
        move_fight(session, request, dx=6.5 - 40 / 25.4)
    else:
        # Same witnessed geometry, the matching Consolidate payload owns targets.
        from warhammer40k_core.engine.event_log import validate_json_value
        from warhammer40k_core.geometry.pathing import PathWitness
        from warhammer40k_core.geometry.pose import Pose

        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        model = state.battlefield_state.unit_placement_by_id(SOURCE).model_placements[0]
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="we-rage-consolidate",
            payload={
                "proposal_request_id": move.request_id,
                "proposal_kind": kind,
                "unit_instance_id": SOURCE,
                "movement_phase_action": move.movement_phase_action,
                "movement_mode": "consolidate",
                "consolidation_mode": "engaging",
                "consolidate_target_unit_instance_ids": ["army-beta:next-enemy"],
                "witness": validate_json_value(
                    PathWitness.for_paths(
                        (
                            (
                                model.model_instance_id,
                                (model.pose, Pose.at(10, 11.5), Pose.at(14.5 - 40 / 25.4, 10)),
                            ),
                        )
                    ).to_payload()
                ),
            },
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(SOURCE).model_placements[0]
    assert math.isclose(
        placement.pose.position.x,
        (16.5 if kind == "pile_in" else 14.5) - 40 / 25.4,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert events(session, "fight_movement_invalid") == []
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint


def test_rage_fuelled_invigoration_keeps_overrun_core_distance_and_expires() -> None:
    session = gameplay_session(game_id="we-rage-expiry")
    select_blessings(session, army_rule.BlessingOfKhorne.RAGE_FUELLED_INVIGORATION)
    reach(session, "select_fight_activation")
    state = session.lifecycle.state
    assert state is not None
    assert (
        fight_movement_maximum_distance_inches(
            state=state, unit_instance_id=SOURCE, proposal_kind=ProposalKind.PILE_IN
        )
        == 3.0
    )
    while state.battle_round == 1:
        state.advance_to_next_battle_phase()
    set_fight_distance_step(
        state,
        policy=state.runtime_ruleset_descriptor().fight_policy,
        step=FightPhaseStepKind.PILE_IN,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    assert army_rule.active_blessings_for_player(state, player_id="player-a") == ()
    assert (
        fight_movement_maximum_distance_inches(
            state=state, unit_instance_id=SOURCE, proposal_kind=ProposalKind.PILE_IN
        )
        == 3.0
    )


@pytest.mark.parametrize("choice", ["auto-wound", "roll-to-wound"])
def test_martial_excellence_warp_blades_resolve_chosen_wounds_and_damage(choice: str) -> None:
    session = gameplay_session(game_id="we-blessings-outcome-13")
    select_blessings(
        session,
        army_rule.BlessingOfKhorne.MARTIAL_EXCELLENCE,
        army_rule.BlessingOfKhorne.WARP_BLADES,
    )
    state = session.lifecycle.state
    assert state is not None
    before = _unit_by_id(state, ENEMY).own_models[0].current_wounds
    complete_activation(session, SOURCE, lethal_choice=choice)
    assert_completed_melee(session.lifecycle, unit_instance_id=SOURCE)
    assert _unit_by_id(state, ENEMY).own_models[0].current_wounds == before - 2
    steps = events(session, "attack_sequence_step")
    hits = [cast(dict[str, JsonValue], step["payload"]) for step in steps if step["step"] == "hit"]
    assert hits[0]["generated_hits"] == 2
    wounds = [
        cast(dict[str, JsonValue], step["payload"]) for step in steps if step["step"] == "wound"
    ]
    assert len(wounds) == 2
    assert len(
        [
            row
            for row in events(session, "dice_rolled")
            if cast(dict[str, JsonValue], row["spec"])["roll_type"] == "attack_sequence.wound"
        ]
    ) == (1 if choice == "auto-wound" else 2)


@pytest.mark.parametrize("infantry", [True, False])
def test_decapitating_strikes_critical_wound_consumes_only_infantry_damage_path(
    infantry: bool,
) -> None:
    session = gameplay_session(game_id="we-decapitating-consumer", infantry_target=infantry)
    select_blessings(session, army_rule.BlessingOfKhorne.DECAPITATING_STRIKES)
    state = session.lifecycle.state
    assert state is not None
    before = _unit_by_id(state, ENEMY).own_models[0].current_wounds
    remaining, status = resolve_native_attack(session)
    assert status is None
    assert remaining is None or remaining.is_complete
    assert _unit_by_id(state, ENEMY).own_models[0].current_wounds == before - 1
    damage = [
        cast(dict[str, JsonValue], row["payload"])
        for row in events(session, "attack_sequence_step")
        if row["step"] == "damage"
    ]
    assert damage
    assert (damage[0]["saving_throw"] is None) is infantry


def test_unbridled_bloodlust_charge_finishes_witnessed_move() -> None:
    session = gameplay_session(game_id="we-charge-outcome", enemy_x=14.5, phase=BattlePhase.CHARGE)
    select_blessings(session, army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST)
    request = pending_request(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="we-charge-source", option_id=SOURCE
    )
    assert status.decision_request is not None
    request = select_targets(
        session, status.decision_request, (ENEMY,), result_id="we-charge-target"
    )
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert move.proposal_kind is ProposalKind.CHARGE_MOVE
    roll = cast(dict[str, JsonValue], events(session, "charge_roll_resolved")[0]["roll_result"])
    roll_state = cast(dict[str, JsonValue], roll["roll_state"])
    assert roll["value"] == cast(int, roll_state["current_total"]) + 1
    before = session.lifecycle.state
    assert before is not None
    assert before.battlefield_state is not None
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="we-charge-witness",
        payload=move_payload(session, request, target=ENEMY, dx=4.5 - 40 / 25.4, dy=0),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    completed = events(session, "charge_move_completed")
    assert len(completed) == 1
    endpoint = cast(dict[str, JsonValue], completed[0]["endpoint_witness"])
    assert endpoint["engaged_target_unit_instance_ids"] == [ENEMY]
    assert math.isclose(
        before.battlefield_state.unit_placement_by_id(SOURCE).model_placements[0].pose.position.x,
        14.5 - 40 / 25.4,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
