"""Gore-Hungry Onslaught through native Movement and Charge proposals."""

from dataclasses import replace
from math import inf, nextafter

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
from tests.factions.chaos_daemons.integration.test_skulls_beget_blood import (
    BLOODLETTERS,
    BLOODMASTER,
)
from tests.factions.chaos_daemons.integration.test_skulls_beget_blood import (
    attached_skulls_definitions as attached_skulls_definitions,
)
from tests.sequential_translation_helpers import leading_first_translation_paths
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
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, EffectExpiration
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_keyword_effects import movement_keywords_granted_by_effects
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.rules_unit_effects import rules_unit_effect_applications
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    stratagem_window_context_from_request,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)

GORE_SOURCE = blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_SOURCE_ID


def _onslaught_scene(
    definitions: Section02Definitions,
    phase: BattlePhase,
    *,
    cp: int = 1,
    active: str = "owner",
    round_mover: bool = False,
    advance_reroll: bool = False,
    charge_seed: str = "onslaught-ground-2",
) -> Scene:
    mover_datasheet = (
        BLOODMASTER if round_mover else (BLOODTHIRSTER if phase is BattlePhase.CHARGE else CRUSHERS)
    )
    if round_mover:
        # Use one round base to isolate terrain rules from oval/multi-model packing.
        # Model a ground Mounted unit: native Infantry would already cross a Dense wall.
        catalog = definitions.package.army_catalog
        sheets = tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    keywords=(
                        *(k for k in sheet.keywords.keywords if k != "INFANTRY"),
                        "MOUNTED",
                        *(("ADVANCE_REROLL",) if advance_reroll else ()),
                    ),
                ),
            )
            if sheet.datasheet_id == mover_datasheet
            else sheet
            for sheet in catalog.datasheets
        )
        definitions = replace(
            definitions,
            package=replace(definitions.package, army_catalog=replace(catalog, datasheets=sheets)),
        )
    battle = scene(
        definitions,
        (
            selection(definitions, mover_datasheet, "first"),
            selection(definitions, CRUSHERS, "second"),
            selection(definitions, BELAKOR, "undivided"),
        ),
        (selection(definitions, LORD, "target"),),
        phase=phase,
        active=active,
        detachment_id_by_faction=DETACHMENTS,
        seed="gore-hungry-onslaught",
        rng_seed_label=charge_seed if phase is BattlePhase.CHARGE else None,
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
        # Round-base sums can round into a tiny overlap at nominal tangency.
        enemy_x = nextafter(contact_x, inf) if round_mover else contact_x
        locate(battle, ENEMY, (Pose.at(enemy_x, 10.0),))
    else:
        locate(
            battle,
            FIRST,
            (start,) if round_mover else (start, Pose.at(11.0, 12.7), Pose.at(11.0, 15.4)),
        )
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


def _assert_onslaught(battle: Scene, phase: BattlePhase, unit_id: str = FIRST) -> None:
    (use,) = tuple(use for use in battle.state.stratagem_use_records if use.stratagem_id == GORE_ID)
    assert use.source_id == GORE_SOURCE
    assert use.targeted_unit_instance_ids == (unit_id,)
    assert use.command_point_cost == 1
    assert battle.state.command_point_total("owner") == 0
    (effect,) = tuple(e for e in battle.state.persisting_effects if e.source_rule_id == GORE_SOURCE)
    assert effect.target_unit_instance_ids == (unit_id,)
    assert effect.expiration == EffectExpiration.end_phase(
        battle_round=1, phase=phase, player_id="owner"
    )
    assert isinstance(effect.effect_payload, dict)
    assert effect.effect_payload["effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert "MOBILE" not in movement_keywords_granted_by_effects((effect,), owner_player_id="owner")
    assert effect not in battle.state.persisting_effects_for_unit(SECOND)
    assert "FLY" not in movement_keywords_granted_by_effects((effect,), owner_player_id="owner")


def _nonlevel_witness(battle: Scene, unit_id: str) -> PathWitness:
    battlefield = battle.state.battlefield_state
    assert battlefield is not None
    proposals = tuple(
        (
            model.model_instance_id,
            (
                model.pose,
                Pose.at(model.pose.position.x + 2.5, model.pose.position.y),
                Pose.at(model.pose.position.x + 3, model.pose.position.y, 0.5),
                Pose.at(model.pose.position.x + 3.5, model.pose.position.y),
                Pose.at(model.pose.position.x + 6, model.pose.position.y),
            ),
        )
        for model in battlefield.unit_placement_by_id(unit_id).model_placements
    )
    return PathWitness.for_paths(leading_first_translation_paths(proposals, dx=6.0))


def _move_nonlevel(battle: Scene, proposal: DecisionRequest) -> LifecycleStatus:
    context = MovementProposalRequest.from_decision_request_payload(proposal.payload)
    assert context.movement_phase_action is not None
    assert context.context is not None
    mode = context.context.get("movement_mode")
    assert mode is None or isinstance(mode, str)
    move = MovementProposalPayload(
        proposal.request_id,
        context.proposal_kind,
        FIRST,
        context.movement_phase_action,
        _nonlevel_witness(battle, FIRST),
        movement_mode=mode,
    )
    return battle.session.submit_parameterized_payload(
        request_id=proposal.request_id,
        payload=validate_json_value(move.to_payload()),
        result_id=f"{proposal.request_id}:nonlevel",
    )


def _assert_replay(battle: Scene, name: str) -> None:
    replay = ReplayRunner.from_payload(battle.session.replay_artifact(artifact_id=name)).run()
    assert replay.reproduced_exactly, replay


def _assert_attached_target(definitions: Section02Definitions, phase: BattlePhase) -> None:
    battle = scene(
        definitions,
        (
            selection(definitions, BLOODLETTERS, "body"),
            selection(definitions, BLOODMASTER, "leader"),
        ),
        (selection(definitions, LORD, "target"),),
        phase=phase,
        attachments=(AttachmentDeclaration("leader", "body"),),
        detachment_id_by_faction=DETACHMENTS,
        seed=f"onslaught-attached-{phase.value}",
    )
    locate(
        battle,
        "own:body",
        tuple(Pose.at(10 + 1.5 * (i // 5), 10 + 1.5 * (i % 5)) for i in range(10)),
    )
    locate(battle, "own:leader", (Pose.at(13, 13),))
    locate(battle, ENEMY, (Pose.at(20, 13),))
    battle.state.gain_command_points(
        player_id="owner",
        amount=1,
        source_id="onslaught:attached-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    anchor(battle)
    offer = begin(battle.session)
    (option,) = tuple(
        o for o in offer.options if o.option_id.startswith(f"use-stratagem:{GORE_ID}:")
    )
    formation = "attached-unit:own:body"
    assert stratagem_targets(offer, GORE_ID) == {formation: option.option_id}
    with pytest.raises(DecisionError, match="option"):
        submit_option(battle.session, option.option_id.replace(formation, "own:leader"))
    require_request(submit_option(battle.session, option.option_id))
    _assert_onslaught(battle, phase, formation)
    (application,) = tuple(
        app
        for app in rules_unit_effect_applications(battle.state, formation)
        if app.effect.source_rule_id == GORE_SOURCE
    )
    assert application.matched_target_unit_instance_ids == (formation,)
    _assert_replay(battle, f"onslaught-attached-{phase.value}")


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
    attached_skulls_definitions: Section02Definitions,
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

    proposals = []
    for use in (False, True):
        advance = _onslaught_scene(
            attached_skulls_definitions, BattlePhase.MOVEMENT, round_mover=True, advance_reroll=True
        )
        preselect = begin(advance.session)
        require_request(
            submit_option(advance.session, DECLINE_STRATAGEM_WINDOW_OPTION_ID),
            "select_movement_unit",
        )
        require_request(submit_option(advance.session, FIRST), "select_movement_action")
        reroll = require_request(
            submit_option(advance.session, "advance"), DICE_REROLL_DECISION_TYPE
        )
        assert not events(advance.session, "advance_roll_resolved")
        assert not events(advance.session, "movement_proposal_requested")
        assert "reroll:0" in {option.option_id for option in reroll.options}
        late = require_request(submit_option(advance.session, "reroll:0"), "use_stratagem")
        context = stratagem_window_context_from_request(late)
        assert (context.timing_window_id or "").startswith("movement-post-roll:")
        assert late.request_id != preselect.request_id
        assert len(events(advance.session, "advance_roll_resolved")) == 1
        assert not events(advance.session, "movement_proposal_requested")
        _assert_replay(advance, "onslaught-advance-pending")
        option = _onslaught_option(late) if use else DECLINE_STRATAGEM_WINDOW_OPTION_ID
        proposal = require_request(
            submit_option(advance.session, option), "submit_movement_proposal"
        )
        assert len(events(advance.session, "advance_roll_resolved")) == 1
        assert len(events(advance.session, "movement_proposal_requested")) == 1
        proposals.append(
            MovementProposalRequest.from_decision_request_payload(proposal.payload).context
        )
        moved = _move_nonlevel(advance, proposal)
        if use:
            assert moved.status_kind is not LifecycleStatusKind.INVALID, moved
            _assert_onslaught(advance, BattlePhase.MOVEMENT)
        else:
            assert moved.status_kind is LifecycleStatusKind.INVALID, moved
            assert "terrain" in str(moved.payload)
            assert advance.state.command_point_total("owner") == 1
            assert not advance.state.stratagem_use_records
        _assert_replay(advance, f"onslaught-advance-{use}")
    assert proposals[0] == proposals[1]
    _assert_attached_target(attached_skulls_definitions, BattlePhase.MOVEMENT)


@pytest.mark.integration
def test_gore_hungry_onslaught_charge_path_and_replay(
    skulls_definitions: Section02Definitions,
    attached_skulls_definitions: Section02Definitions,
) -> None:
    def charge_move(
        battle: Scene,
        *,
        use: bool,
        late: bool = False,
        round_mover: bool = False,
        command_reroll: bool = False,
    ) -> LifecycleStatus:
        offer = begin(battle.session)
        option = _onslaught_option(offer)
        if not use or late:
            option = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        units = require_request(submit_option(battle.session, option), "select_charging_unit")
        ground = next(
            choice
            for choice in units.options
            if isinstance(choice.payload, dict)
            and choice.payload.get("unit_instance_id") == FIRST
            and choice.payload.get("take_to_the_skies", False) is False
        )
        proposal = require_request(submit_option(battle.session, ground.option_id))
        offered_post_roll = False
        took_reroll = False
        selected_targets = False
        while proposal.decision_type in {"use_stratagem", "select_charge_targets"}:
            if proposal.decision_type == "select_charge_targets":
                assert not selected_targets
                selected_targets = True
                proposal = targets(battle.session, (ENEMY,))
                continue
            context = stratagem_window_context_from_request(proposal)
            choice = DECLINE_STRATAGEM_WINDOW_OPTION_ID
            if command_reroll and (context.timing_window_id or "").startswith("command-reroll-"):
                assert not offered_post_roll
                assert not took_reroll
                assert not events(battle.session, "charge_roll_resolved")
                (choice,) = tuple(
                    o.option_id for o in proposal.options if "command-reroll" in o.option_id
                )
                took_reroll = True
            if (context.timing_window_id or "").startswith("charge-post-roll:"):
                assert not offered_post_roll
                offered_post_roll = True
                assert len(events(battle.session, "charge_roll_resolved")) == 1
                assert not events(battle.session, "charge_move_proposal_requested")
                _assert_replay(battle, "onslaught-charge-pending")
                if command_reroll:
                    # The charging unit already received Command Re-roll this phase.
                    assert set(stratagem_targets(proposal, GORE_ID)) == {SECOND}
                if use and late:
                    choice = stratagem_targets(proposal, GORE_ID)[FIRST]
            next_request = require_request(submit_option(battle.session, choice))
            assert next_request.request_id != proposal.request_id
            proposal = next_request
        assert selected_targets, (proposal.decision_type, roll(battle.session))
        assert offered_post_roll is (not use or late)
        assert took_reroll is command_reroll
        assert len(roll(battle.session).roll_state.rerolls) == int(command_reroll)
        assert proposal.decision_type == "submit_movement_proposal", proposal
        assert len(events(battle.session, "charge_roll_resolved")) == 1
        assert roll(battle.session).movement_budget.maximum_distance_inches >= 7.0
        path = _nonlevel_witness(battle, FIRST) if round_mover else witness(battle.state, FIRST, 6)
        return propose(battle.session, FIRST, (ENEMY,), path)

    control = _onslaught_scene(
        attached_skulls_definitions,
        BattlePhase.CHARGE,
        round_mover=True,
        charge_seed="onslaught-ground-1",
    )
    blocked = charge_move(control, use=False, round_mover=True)
    assert blocked.status_kind is LifecycleStatusKind.INVALID, blocked
    assert "terrain" in str(blocked.payload)
    assert control.state.command_point_total("owner") == 1
    assert not any(use.stratagem_id == GORE_ID for use in control.state.stratagem_use_records)
    _assert_replay(control, "onslaught-charge-declined")

    late_battle = _onslaught_scene(
        attached_skulls_definitions,
        BattlePhase.CHARGE,
        round_mover=True,
        charge_seed="onslaught-ground-1",
    )
    moved_late = charge_move(late_battle, use=True, late=True, round_mover=True)
    assert moved_late.status_kind is not LifecycleStatusKind.INVALID, moved_late
    assert roll(late_battle.session) == roll(control.session)
    _assert_onslaught(late_battle, BattlePhase.CHARGE)
    _assert_replay(late_battle, "onslaught-charge-late")

    rerolled = _onslaught_scene(
        attached_skulls_definitions,
        BattlePhase.CHARGE,
        cp=2,
        round_mover=True,
        charge_seed="onslaught-ground-5",
    )
    still_blocked = charge_move(rerolled, use=False, round_mover=True, command_reroll=True)
    assert still_blocked.status_kind is LifecycleStatusKind.INVALID, still_blocked
    assert "terrain" in str(still_blocked.payload)
    assert rerolled.state.command_point_total("owner") == 1
    _assert_replay(rerolled, "onslaught-after-command-reroll")
    _assert_attached_target(attached_skulls_definitions, BattlePhase.CHARGE)

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
