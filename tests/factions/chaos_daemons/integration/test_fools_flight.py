"""Fool's Flight through native Fall Back, Stratagem and Charge decisions."""

import pytest

from tests.daemons_native_source_helpers import BELAKOR
from tests.support.blood_legion import (
    DETACHMENTS,
    FIRST,
    SECOND,
    WRONG_KEYWORD,
    stratagem_targets,
    submit_option,
)
from tests.support.blood_legion import skulls_definitions as skulls_definitions
from tests.support.faction_batch01 import LORD, Scene, anchor, events, locate, scene, selection
from tests.support.faction_batch01 import request as require_request
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section11_fixtures import begin
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    stratagem_window_context_from_request,
)
from warhammer40k_core.geometry.pose import Pose

FOOLS_FLIGHT_ID = "000009816006"
EARLIER_RETREAT = "foe:earlier"
TRIGGER_RETREAT = "foe:trigger"
NORMAL_MOVER = "foe:normal"


def _flight_scene(
    definitions: Section02Definitions, cp: int, *, rng_seed_label: str | None = None
) -> Scene:
    from tests.support.blood_legion import BLOODTHIRSTER

    battle = scene(
        definitions,
        (
            selection(definitions, BLOODTHIRSTER, "first"),
            selection(definitions, BLOODTHIRSTER, "second"),
            selection(definitions, BELAKOR, "undivided"),
        ),
        tuple(
            selection(definitions, LORD, id_) for id_ in ("earlier", "trigger", "later", "normal")
        ),
        phase=BattlePhase.MOVEMENT,
        active="opponent",
        detachment_id_by_faction=DETACHMENTS,
        seed="fools-flight",
        rng_seed_label=rng_seed_label,
    )
    for unit_id, xy in {
        FIRST: (20, 20),
        SECOND: (15, 15),
        WRONG_KEYWORD: (31.5, 20),
        EARLIER_RETREAT: (28.2, 20),
        TRIGGER_RETREAT: (18.4, 15),
        "foe:later": (31.5, 23.6),
        NORMAL_MOVER: (20, 26),
    }.items():
        locate(battle, unit_id, (Pose.at(*xy),))
    battle.state.gain_command_points(
        player_id="owner",
        amount=cp,
        source_id="fools-flight:fixture-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    anchor(battle)
    return battle


def _flight_next(battle: Scene, req: DecisionRequest, *, stop_at_offer: bool) -> DecisionRequest:
    from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
    from warhammer40k_core.engine.triggered_movement import DECLINE_TRIGGERED_MOVEMENT_OPTION_ID

    for _ in range(12):
        if req.decision_type in {"select_movement_unit", "submit_stratagem_target_proposal"}:
            return req
        if stratagem_targets(req, FOOLS_FLIGHT_ID):
            if stop_at_offer:
                return req
            option = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        elif req.decision_type == "select_triggered_movement_unit":
            option = DECLINE_TRIGGERED_MOVEMENT_OPTION_ID
        elif req.decision_type == SEQUENCING_DECISION_TYPE:
            option = next(
                (option.option_id for option in req.options if FOOLS_FLIGHT_ID in option.option_id),
                req.options[0].option_id,
            )
        else:
            raise AssertionError(req)
        req = require_request(submit_option(battle.session, option))
    raise AssertionError(req)


def _flight_move(battle: Scene, unit: str, action: str, dx: float) -> DecisionRequest:
    assert pending(battle.session).decision_type == "select_movement_unit"
    require_request(submit_option(battle.session, unit), "select_movement_action")
    proposal = require_request(submit_option(battle.session, action), "submit_movement_proposal")
    assert not stratagem_targets(proposal, FOOLS_FLIGHT_ID)
    from tests.support.section09_fixtures import propose as propose_movement

    assert battle.state.battlefield_state is not None
    placement = battle.state.battlefield_state.unit_placement_by_id(unit)
    ends = tuple(
        Pose.at(p.pose.position.x + dx, p.pose.position.y, p.pose.position.z)
        for p in placement.model_placements
    )
    return require_request(
        propose_movement(
            battle.session, proposal, battle.units[unit], ends, result_id=f"move-{unit}"
        )
    )


@pytest.mark.integration
def test_fools_flight_native_fall_back_charge_resume_and_replay(
    skulls_definitions: Section02Definitions,
) -> None:
    from tests.support.section11_fixtures import propose, targets, witness
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    battle = _flight_scene(skulls_definitions, 4)
    begin(battle.session)
    retreat = "fall_back:ordered_retreat"
    next_move = _flight_move(battle, NORMAL_MOVER, "normal_move", 0.25)
    assert not stratagem_targets(next_move, FOOLS_FLIGHT_ID)
    _flight_next(battle, next_move, stop_at_offer=False)
    earlier = _flight_next(
        battle,
        _flight_move(battle, EARLIER_RETREAT, retreat, -2.0),
        stop_at_offer=True,
    )
    assert set(stratagem_targets(earlier, FOOLS_FLIGHT_ID)) == {FIRST}
    _flight_next(battle, earlier, stop_at_offer=False)
    assert battle.state.command_point_total("owner") == 4

    offer = _flight_next(
        battle, _flight_move(battle, TRIGGER_RETREAT, retreat, 2.25), stop_at_offer=True
    )
    assert offer.actor_id == "owner"
    assert set(stratagem_targets(offer, FOOLS_FLIGHT_ID)) == {FIRST, SECOND}
    assert stratagem_window_context_from_request(offer).trigger_payload == {
        "fall_back_completion_event_id": (
            stratagem_window_context_from_request(offer).timing_window_id or ""
        ).removeprefix("enemy-fell-back:"),
        "triggering_unit_instance_id": TRIGGER_RETREAT,
        "enemy_units_that_fell_back_this_phase": [EARLIER_RETREAT, TRIGGER_RETREAT],
    }
    assert not events(battle.session, "charge_roll_resolved")
    checkpoint = battle.session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(checkpoint).to_persistence_payload() == checkpoint
    )

    with pytest.raises(DecisionError, match="option"):
        submit_option(
            battle.session,
            stratagem_targets(offer, FOOLS_FLIGHT_ID)[FIRST].replace(FIRST, WRONG_KEYWORD),
        )
    assert pending(battle.session) == offer
    assert battle.state.command_point_total("owner") == 4

    charge = require_request(
        submit_option(battle.session, stratagem_targets(offer, FOOLS_FLIGHT_ID)[FIRST])
    )
    assert charge.decision_type == "select_charging_unit"
    assert charge.actor_id == "owner"
    assert battle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert battle.state.active_player_id == "opponent"
    assert battle.state.effective_active_player_id() == "owner"
    pending_charge = battle.session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(pending_charge).to_persistence_payload()
        == pending_charge
    )
    choice = require_request(submit_option(battle.session, FIRST))
    while choice.decision_type == "use_stratagem":
        choice = require_request(submit_option(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID))
    assert choice.decision_type == "select_charge_targets"
    allowed = set()
    for option in choice.options:
        if isinstance(option.payload, dict) and isinstance(
            ids := option.payload.get("target_ids"), list
        ):
            assert all(isinstance(id_, str) for id_ in ids)
            allowed.add(tuple(str(id_) for id_ in ids))
    assert (EARLIER_RETREAT,) in allowed
    assert all(set(group) <= {EARLIER_RETREAT, TRIGGER_RETREAT} for group in allowed)
    decline_checkpoint = battle.session.to_persistence_payload()
    declined = LocalGameSession.from_persistence_payload(decline_checkpoint)
    require_request(submit_option(declined, "decline_charge_targets"))
    assert not events(declined, "charge_move_completed")
    assert declined.lifecycle.state is not None
    assert declined.lifecycle.state.effective_active_player_id() == "opponent"
    assert declined.lifecycle.state.command_point_total("owner") == 2

    proposal = targets(battle.session, (EARLIER_RETREAT,))
    assert proposal.decision_type == "submit_movement_proposal"
    accepted = propose(battle.session, FIRST, (EARLIER_RETREAT,), witness(battle.state, FIRST, 2.7))
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    assert battle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert battle.state.effective_active_player_id() == "opponent"
    assert battle.state.charge_phase_state is None
    charge_events = events(battle.session, "charge_move_completed")
    assert len(charge_events) == 1
    assert "persisting_effect" in charge_events[0]
    assert battle.state.command_point_total("owner") == 2
    (use,) = tuple(
        u for u in battle.state.stratagem_use_records if u.stratagem_id == FOOLS_FLIGHT_ID
    )
    assert use.phase is BattlePhase.MOVEMENT
    assert use.command_point_cost == 2
    assert use.targeted_unit_instance_ids == (FIRST,)
    _flight_next(battle, require_request(accepted), stop_at_offer=False)
    later = _flight_move(battle, "foe:later", retreat, -4.0)
    assert _flight_next(battle, later, stop_at_offer=True).decision_type == (
        "submit_stratagem_target_proposal"
    )
    assert battle.state.command_point_total("owner") == 2
    _assert_fights_first_through_turn_end(battle)
    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="fools-flight")
    ).run()
    assert replay.reproduced_exactly, replay


def _assert_fights_first_through_turn_end(battle: Scene) -> None:
    from tests.psychic_modifier_helpers import submit_fixture_request
    from warhammer40k_core.engine.effects import EffectExpiration

    (bonus,) = tuple(
        effect
        for effect in battle.state.persisting_effects_for_unit(FIRST)
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == "charge_grants_fights_first"
    )
    assert bonus.expiration == EffectExpiration.end_turn(battle_round=1, player_id="opponent")
    skipped_actions = {
        "start_mission_action": "continue_to_shooting",
        "select_shooting_unit": "complete_shooting_phase",
        "select_charging_unit": "complete_charge_phase",
        "use_stratagem": DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    }
    first_fight = None
    for _ in range(96):
        if (battle.state.battle_round, battle.state.active_player_id) != (1, "opponent"):
            break
        req = pending(battle.session)
        if req.decision_type == "select_fight_activation" and first_fight is None:
            assert battle.state.current_battle_phase is BattlePhase.FIGHT
            assert req.actor_id == "owner"
            assert isinstance(req.payload, dict)
            assert req.payload["ordering_band"] == "fights_first"
            assert bonus in battle.state.persisting_effects_for_unit(FIRST)
            first_fight = next(
                choice
                for choice in req.options
                if isinstance(choice.payload, dict)
                and choice.payload.get("unit_instance_id") == FIRST
            )
            submit_option(battle.session, first_fight.option_id)
        elif req.decision_type in skipped_actions:
            submit_option(battle.session, skipped_actions[req.decision_type])
        else:
            submit_fixture_request(battle.session, req)
    else:
        raise AssertionError("Opponent Fight and turn end did not complete.")
    assert first_fight is not None
    assert battle.state.battle_round == 2
    assert battle.state.active_player_id == "owner"
    assert bonus not in battle.state.persisting_effects_for_unit(FIRST)


@pytest.mark.integration
def test_fools_flight_unavailable_at_one_cp(skulls_definitions: Section02Definitions) -> None:
    battle = _flight_scene(skulls_definitions, 1)
    begin(battle.session)
    response = _flight_move(battle, TRIGGER_RETREAT, "fall_back:ordered_retreat", 2.25)
    assert not stratagem_targets(response, FOOLS_FLIGHT_ID)
    assert _flight_next(battle, response, stop_at_offer=True).actor_id == "opponent"
    assert not battle.state.stratagem_use_records
    assert battle.state.command_point_total("owner") == 1


@pytest.mark.integration
def test_fools_flight_short_roll_resumes_opponent_movement(
    skulls_definitions: Section02Definitions,
) -> None:
    battle = _flight_scene(skulls_definitions, 2, rng_seed_label="fools-flight-short-1")
    begin(battle.session)
    offer = _flight_next(
        battle,
        _flight_move(battle, TRIGGER_RETREAT, "fall_back:ordered_retreat", 5.1),
        stop_at_offer=True,
    )
    assert SECOND in stratagem_targets(offer, FOOLS_FLIGHT_ID)
    previous_placement = battle.state.battlefield_state
    charge = require_request(
        submit_option(battle.session, stratagem_targets(offer, FOOLS_FLIGHT_ID)[SECOND])
    )
    assert charge.decision_type == "select_charging_unit"
    resumed = require_request(submit_option(battle.session, SECOND))
    (failed,) = events(battle.session, "charge_no_move_possible")
    roll_result = failed["roll_result"]
    assert isinstance(roll_result, dict)
    assert not roll_result["reachable_target_distances_inches"]
    assert not events(battle.session, "charge_move_completed")
    assert battle.state.battlefield_state == previous_placement
    assert battle.state.charge_phase_state is None
    assert battle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert battle.state.effective_active_player_id() == "opponent"
    assert battle.state.command_point_total("owner") == 0
    resumed = _flight_next(battle, resumed, stop_at_offer=True)
    assert resumed.actor_id == "opponent"
    assert resumed.decision_type == "select_movement_unit"
    assert NORMAL_MOVER in {option.option_id for option in resumed.options}
    _flight_move(battle, NORMAL_MOVER, "normal_move", 0.25)
    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="fools-flight-short")
    ).run()
    assert replay.reproduced_exactly, replay
