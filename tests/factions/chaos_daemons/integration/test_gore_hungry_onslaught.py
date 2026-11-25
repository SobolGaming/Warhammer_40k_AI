"""Gore-Hungry Onslaught through native Movement and Charge proposals."""

import pytest

from tests.daemons_native_source_helpers import BELAKOR
from tests.factions.chaos_daemons.integration.test_blood_begets_skulls import (
    BLOODTHIRSTER,
    DETACHMENTS,
    ENEMY,
    FIRST,
    GORE_ID,
    SECOND,
    WRONG_KEYWORD,
    stratagem_targets,
    submit_option,
)
from tests.factions.chaos_daemons.integration.test_blood_begets_skulls import (
    skulls_definitions as skulls_definitions,
)
from tests.support.faction_batch01 import (
    CRUSHERS,
    LORD,
    Scene,
    anchor,
    events,
    locate,
    scene,
    selection,
    submit_translation,
)
from tests.support.faction_batch01 import request as require_request
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section11_fixtures import begin, propose, roll, targets, witness
from tests.support.terrain_batch03 import barrier
from warhammer40k_core.engine.battlefield_state import geometry_model_at_pose
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, EffectExpiration
from warhammer40k_core.engine.movement_keyword_effects import movement_keywords_granted_by_effects
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    stratagem_window_context_from_request,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)

GORE_SOURCE = blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_SOURCE_ID


def _onslaught_scene(
    definitions: Section02Definitions, phase: BattlePhase, *, cp: int = 1, active: str = "owner"
) -> Scene:
    battle = scene(
        definitions,
        (
            selection(
                definitions, BLOODTHIRSTER if phase is BattlePhase.CHARGE else CRUSHERS, "first"
            ),
            selection(definitions, CRUSHERS, "second"),
            selection(definitions, BELAKOR, "undivided"),
        ),
        (selection(definitions, LORD, "target"),),
        phase=phase,
        active=active,
        detachment_id_by_faction=DETACHMENTS,
        seed="gore-hungry-onslaught",
        rng_seed_label="onslaught-ground-2" if phase is BattlePhase.CHARGE else None,
        terrain_features=(barrier(7.0),),
    )
    start = Pose.at(11.0, 10.0)
    if phase is BattlePhase.CHARGE:
        (mover_model,) = battle.units[FIRST].own_models
        (enemy_model,) = battle.units[ENEMY].own_models
        mover = geometry_model_at_pose(model=mover_model, pose=start)
        enemy = geometry_model_at_pose(model=enemy_model, pose=start)
        contact_x = (
            start.position.x
            + 6.0
            + mover.base.radius_at_angle(0.0, start.facing)
            + enemy.base.radius_at_angle(180.0, start.facing)
        )
        locate(battle, FIRST, (start,))
        locate(battle, ENEMY, (Pose.at(contact_x, 10.0),))
    else:
        locate(battle, FIRST, (start, Pose.at(11.0, 12.7), Pose.at(11.0, 15.4)))
        enemy_pose = Pose.at(5.5, 10.0) if phase is BattlePhase.SHOOTING else Pose.at(30.0, 20.0)
        locate(battle, ENEMY, (enemy_pose,))
    locate(battle, SECOND, tuple(Pose.at(11.0, y) for y in (20.0, 22.7, 25.4)))
    locate(battle, WRONG_KEYWORD, (Pose.at(45.0, 35.0),))
    if cp:
        battle.state.gain_command_points(
            player_id="owner",
            amount=cp,
            source_id="gore-hungry-onslaught:fixture-cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    anchor(battle)
    return battle


def _onslaught_option(request: DecisionRequest) -> str:
    assert request.decision_type == "use_stratagem"
    assert request.actor_id == "owner"
    candidates = stratagem_targets(request, GORE_ID)
    assert set(candidates) == {FIRST, SECOND}
    return candidates[FIRST]


def _assert_onslaught(battle: Scene, phase: BattlePhase) -> None:
    (use,) = tuple(use for use in battle.state.stratagem_use_records if use.stratagem_id == GORE_ID)
    assert use.source_id == GORE_SOURCE
    assert use.targeted_unit_instance_ids == (FIRST,)
    assert use.command_point_cost == 1
    assert battle.state.command_point_total("owner") == 0
    (effect,) = tuple(e for e in battle.state.persisting_effects if e.source_rule_id == GORE_SOURCE)
    assert effect.target_unit_instance_ids == (FIRST,)
    assert effect.expiration == EffectExpiration.end_phase(
        battle_round=1, phase=phase, player_id="owner"
    )
    assert isinstance(effect.effect_payload, dict)
    assert effect.effect_payload["effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert "MOBILE" not in movement_keywords_granted_by_effects((effect,), owner_player_id="owner")
    assert effect not in battle.state.persisting_effects_for_unit(SECOND)


def _advance_through_wall(battle: Scene, unit_id: str, inches: float) -> LifecycleStatus:
    require_request(submit_option(battle.session, unit_id), "select_movement_action")
    proposal = require_request(
        submit_option(battle.session, "normal_move"), "submit_movement_proposal"
    )
    return submit_translation(battle, proposal, unit_id, inches)


@pytest.mark.integration
def test_gore_hungry_onslaught_movement_path_and_replay(
    skulls_definitions: Section02Definitions,
) -> None:
    battle = _onslaught_scene(skulls_definitions, BattlePhase.MOVEMENT)
    offer = begin(battle.session)
    choice = _onslaught_option(offer)
    with pytest.raises(DecisionError, match="option"):
        submit_option(battle.session, choice.replace(FIRST, WRONG_KEYWORD))
    assert pending(battle.session) == offer

    control = _onslaught_scene(skulls_definitions, BattlePhase.MOVEMENT)
    _onslaught_option(begin(control.session))
    require_request(
        submit_option(control.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID), "select_movement_unit"
    )
    blocked = _advance_through_wall(control, FIRST, 6.0)
    assert blocked.status_kind is LifecycleStatusKind.INVALID, blocked
    assert "terrain" in str(blocked.payload)
    assert control.state.command_point_total("owner") == 1

    require_request(submit_option(battle.session, choice), "select_movement_unit")
    _assert_onslaught(battle, BattlePhase.MOVEMENT)
    require_request(submit_option(battle.session, FIRST), "select_movement_action")
    proposal = require_request(
        submit_option(battle.session, "normal_move"), "submit_movement_proposal"
    )
    endpoint_in_wall = submit_translation(battle, proposal, FIRST, 3.0)
    assert endpoint_in_wall.status_kind is LifecycleStatusKind.INVALID, endpoint_in_wall
    assert "endpoint" in str(endpoint_in_wall.payload)
    proposal = pending(battle.session)
    require_request(submit_translation(battle, proposal, FIRST, 6.0), "select_movement_unit")
    assert events(battle.session, "movement_activation_completed")[-1]["unit_instance_id"] == FIRST
    require_request(submit_option(battle.session, SECOND), "select_movement_action")
    require_request(submit_option(battle.session, "remain_stationary"), "select_movement_unit")
    require_request(submit_option(battle.session, WRONG_KEYWORD), "select_movement_action")
    require_request(submit_option(battle.session, "remain_stationary"))
    req = pending(battle.session)
    if req.decision_type == "start_mission_action":
        require_request(submit_option(battle.session, "continue_to_shooting"))
    assert battle.state.current_battle_phase is BattlePhase.SHOOTING
    assert not any(e.source_rule_id == GORE_SOURCE for e in battle.state.persisting_effects)
    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="onslaught-move")
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.integration
def test_gore_hungry_onslaught_later_movement_window(
    skulls_definitions: Section02Definitions,
) -> None:
    battle = _onslaught_scene(skulls_definitions, BattlePhase.MOVEMENT)
    first = begin(battle.session)
    _onslaught_option(first)
    require_request(
        submit_option(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID), "select_movement_unit"
    )
    require_request(submit_option(battle.session, WRONG_KEYWORD), "select_movement_action")
    later = require_request(submit_option(battle.session, "remain_stationary"), "use_stratagem")
    assert stratagem_window_context_from_request(first) != stratagem_window_context_from_request(
        later
    )
    require_request(submit_option(battle.session, _onslaught_option(later)), "select_movement_unit")
    _assert_onslaught(battle, BattlePhase.MOVEMENT)


@pytest.mark.integration
def test_gore_hungry_onslaught_charge_path_and_replay(
    skulls_definitions: Section02Definitions,
) -> None:
    def charge_move(battle: Scene, *, use: bool) -> LifecycleStatus:
        offer = begin(battle.session)
        option = _onslaught_option(offer)
        if not use:
            option = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        units = require_request(submit_option(battle.session, option), "select_charging_unit")
        ground = next(
            choice
            for choice in units.options
            if isinstance(choice.payload, dict)
            and choice.payload.get("unit_instance_id") == FIRST
            and choice.payload.get("take_to_the_skies") is False
        )
        req = require_request(submit_option(battle.session, ground.option_id))
        while req.decision_type == "use_stratagem":
            continued = require_request(
                submit_option(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID)
            )
            assert continued.request_id != req.request_id
            req = continued
        assert req.decision_type == "select_charge_targets", req
        proposal = targets(battle.session, (ENEMY,))
        if proposal.decision_type == "use_stratagem":
            proposal = require_request(
                submit_option(battle.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID)
            )
        assert proposal.decision_type == "submit_movement_proposal", proposal
        assert roll(battle.session).movement_budget.maximum_distance_inches == 9.0
        return propose(battle.session, FIRST, (ENEMY,), witness(battle.state, FIRST, 6.0))

    control = _onslaught_scene(skulls_definitions, BattlePhase.CHARGE)
    blocked = charge_move(control, use=False)
    assert blocked.status_kind is LifecycleStatusKind.INVALID, blocked
    assert "terrain" in str(blocked.payload)

    battle = _onslaught_scene(skulls_definitions, BattlePhase.CHARGE)
    moved = charge_move(battle, use=True)
    assert moved.status_kind is not LifecycleStatusKind.INVALID, moved
    assert battle.state.battlefield_state is not None
    (model,) = battle.state.battlefield_state.unit_placement_by_id(FIRST).model_placements
    assert model.pose.position.x == 17.0
    _assert_onslaught(battle, BattlePhase.CHARGE)
    require_request(submit_option(battle.session, "complete_charge_phase"))
    assert battle.state.current_battle_phase is BattlePhase.FIGHT
    assert not any(e.source_rule_id == GORE_SOURCE for e in battle.state.persisting_effects)
    replay = ReplayRunner.from_payload(
        battle.session.replay_artifact(artifact_id="onslaught-charge")
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.integration
@pytest.mark.parametrize(
    ("phase", "cp", "active"),
    [
        (BattlePhase.MOVEMENT, 0, "owner"),
        (BattlePhase.MOVEMENT, 1, "opponent"),
        (BattlePhase.CHARGE, 1, "opponent"),
        (BattlePhase.SHOOTING, 1, "owner"),
    ],
)
def test_gore_hungry_onslaught_ineligible_window(
    skulls_definitions: Section02Definitions, phase: BattlePhase, cp: int, active: str
) -> None:
    control = _onslaught_scene(skulls_definitions, phase, cp=cp, active=active)
    request = begin(control.session)
    assert control.state.current_battle_phase is phase
    assert not stratagem_targets(request, GORE_ID)
    assert not control.state.stratagem_use_records
