"""Native shooting and Fall Back through the shared source-bound Fortification clause."""

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.faction_batch01 import ELDRAD, RANGERS, anchor, locate, scene, selection
from tests.support.faction_batch01 import faction_definitions as faction_definitions
from tests.support.fortification_fixtures import GNARLMAW, SKULL_ALTAR, with_fortification
from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from tests.support.section03_fixtures import grid, native_state, placement
from tests.support.section03_session import movement_session
from tests.support.section04_fixtures import choose as choose_shooting
from tests.support.section04_fixtures import finish_attacks, shooting_payload, weapon_rows
from tests.support.section09_fixtures import (
    add_unit,
    anchor_hazard_scene,
    attach_mission,
    choose,
    events,
    finish_hazard_choices,
    propose,
    select,
)
from tests.support.section09_fixtures import section09_definitions as section09_definitions
from tests.support.section10_fixtures import (
    AVENGERS,
    LORD,
    accepted_pools,
    assert_valid,
    declaration_request,
)
from tests.support.section11_fixtures import begin
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.battle_shock_state import apply_direct_battle_shock_state
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import geometry_model_at_pose
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.movement_decision_authority import (
    validate_movement_completion_decision_authority,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    DesperateEscapeRoll,
    DesperateEscapeRollPayload,
    FallBackModeKind,
)
from warhammer40k_core.engine.phases.movement_escape_mortals import completed_escape_retry
from warhammer40k_core.engine.phases.movement_geometry import (
    _enemy_model_ids_crossed_by_witness,
)
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.physical_engagement import (
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.shooting_targets import FORTIFICATION_ENGAGEMENT_RULE_ID
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.physical_predicates import physical_footprints_overlap
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    ("source", "mixed", "crosses", "shocked", "forced", "hazard_count"),
    [
        (GNARLMAW, False, True, True, False, 1),
        (GNARLMAW, False, False, True, False, 0),
        (GNARLMAW, True, True, True, False, 2),
        (GNARLMAW, False, True, False, False, 2),
        (SKULL_ALTAR, False, True, True, False, 1),
        (None, False, True, True, False, 2),
        (GNARLMAW, False, True, True, True, 2),
    ],
)
def test_fortification_fall_back_hazards_follow_each_native_path(
    section09_definitions: Section02Definitions,
    source: str | None,
    mixed: bool,
    crosses: bool,
    shocked: bool,
    forced: bool,
    hazard_count: int,
) -> None:
    provider_sheet = "000004078"  # Known round-base fixture, not a Fortification sculpt.
    # The separate force rule is taken from Bloodletters and attached only in
    # the coexistence control to the borrowed geometry fixture.
    additional_abilities = (
        tuple(
            ability
            for ability in section09_definitions.unit("000001114").datasheet_abilities
            if ability.ability_id == "000001114:bane-of-cowards"
        )
        if forced
        else ()
    )
    assert len(additional_abilities) == int(forced)
    d = with_fortification(
        section09_definitions,
        provider_sheet=provider_sheet,
        fortification_sheet=source,
        additional_abilities=additional_abilities,
    )
    unit = d.unit("000004090")
    provider = d.unit(provider_sheet, army_id="enemy", identity="fortification")
    starts = (Pose.at(10, 10), Pose.at(13, 10))
    state = native_state(d, unit, starts, enemy=provider, enemy_poses=(Pose.at(10, 12.4),))
    if mixed:
        enemy = d.unit("000004090", army_id="enemy", identity="infantry")
        army = state.army_definitions[-1]
        assert army.player_id == "opponent"
        state.army_definitions[-1] = replace(army, units=(*army.units, enemy))
        state.starting_strength_records.append(
            StartingStrengthRecord.from_unit(player_id=army.player_id, unit=enemy)
        )
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            replace(
                state.battlefield_state,
                placed_armies=tuple(
                    replace(
                        placed,
                        unit_placements=(
                            *placed.unit_placements,
                            placement(enemy, (Pose.at(13, 7.5), Pose.at(15.5, 7.5)), enemy=True),
                        ),
                    )
                    if placed.army_id == army.army_id
                    else placed
                    for placed in state.battlefield_state.placed_armies
                ),
            )
        )
    attach_mission(state)
    add_unit(state, d.unit("000004090", identity="spare"), (Pose.at(10, 30), Pose.at(12.5, 30)))
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    session = movement_session(d, state)
    if forced:
        config = session.lifecycle.config
        index = AbilityCatalogIndex.from_records(
            catalog_ability_records_from_catalog(config.army_catalog)
        )
        handler = MovementPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
            ability_indexes_by_player_id={"owner": index, "opponent": index},
        )
        session = LocalGameSession(
            GameLifecycle(state=state, _config=config, _movement_phase_handler=handler)
        )
        record_primary_turn_start_evidence_for_fixture(
            state, decisions=session.lifecycle.decision_controller
        )

    # The retained voluntary mode is still mandatory for the already-shocked unit.
    action = select(session, unit)
    assert any(option.option_id == "fall_back:ordered_retreat" for option in action.options) is (
        not shocked
    )
    anchor_hazard_scene(session)
    request = choose(session, action, "fall_back:desperate_escape")
    end_y = 17 if crosses else 6
    status = propose(session, request, unit, (Pose.at(10, end_y), Pose.at(13, end_y)))
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    first, second = unit.own_model_ids()
    rolls = _escape_rolls(session)
    assert (
        tuple(roll.requirement.model_instance_id for roll in rolls)
        == (first, second)[:hazard_count]
    )
    if crosses:
        assert rolls[0].requirement.enemy_model_ids == provider.own_model_ids()
        assert "enemy_model_overflight" in rolls[0].requirement.reasons
    if hazard_count == 2:
        assert rolls[1].requirement.enemy_model_ids == ()
        assert ("battle_shocked" in rolls[1].requirement.reasons) is (shocked and not forced)
        if forced:
            assert rolls[1].requirement.reasons == ("forced_by_rule",)

    if forced:
        # This checkpoint supplies an already-shocked unit. The forced test and
        # both hazard rolls must resolve before the pending consequence choice.
        types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
        forced_test = types.index("forced_desperate_escape_battle_shock_resolved")
        assert all(
            index < forced_test
            for index, kind in enumerate(types)
            if kind == "desperate_escape_roll_resolved"
        )
        assert "movement_activation_completed" not in types
        assert status.decision_request is not None
        assert status.decision_request.decision_type == "select_mortal_wound_model"
        return
    finish_hazard_choices(session, status)
    (completed,) = events(session, "movement_activation_completed")
    expected_exempt = (
        [second]
        if hazard_count == 1 or forced
        else ([first, second] if hazard_count == 0 else None)
    )
    assert completed.get("fortification_desperate_escape_exempt_model_ids") == expected_exempt
    types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
    assert types.count("desperate_escape_battle_shock_resolved") == int(not shocked)
    if not shocked:
        assert (
            types.index("desperate_escape_roll_resolved")
            < types.index("fall_back_move_applied")
            < types.index("desperate_escape_battle_shock_resolved")
            < types.index("movement_activation_completed")
        )


@pytest.mark.parametrize(
    ("source", "mixed", "weapon", "expected_modifier"),
    [
        (GNARLMAW, False, "avenger-shuriken-catapult", -1),
        (GNARLMAW, False, "shuriken-pistol", 0),
        (GNARLMAW, True, "avenger-shuriken-catapult", None),
        (GNARLMAW, True, "shuriken-pistol", None),
        (SKULL_ALTAR, False, "avenger-shuriken-catapult", -1),
        (None, False, "avenger-shuriken-catapult", None),
    ],
)
def test_fortification_engagement_through_normal_shooting(
    faction_definitions: Section02Definitions,
    source: str | None,
    mixed: bool,
    weapon: str,
    expected_modifier: int | None,
) -> None:
    # The descriptor is the source under test. Eldrad supplies known test
    # geometry and does not represent either sculpt or its datasheet loadout.
    d = with_fortification(faction_definitions, provider_sheet=ELDRAD, fortification_sheet=source)
    shooting_sheet = RANGERS if weapon == "shuriken-pistol" else AVENGERS
    friendly: tuple[UnitMusterSelection, ...] = (
        selection(d, shooting_sheet, "shooter"),
        selection(d, ELDRAD, "fortification"),
    )
    if mixed:
        friendly = (*friendly, selection(d, AVENGERS, "infantry"))
    battle = scene(
        d,
        friendly,
        (selection(d, LORD, "engaged"), selection(d, LORD, "unengaged")),
        phase=BattlePhase.SHOOTING,
        seed="fortification-normal-shooting",
    )
    shooter = battle.units["own:shooter"]
    locate(battle, shooter.unit_instance_id, grid(shooter, 11, 20))
    locate(battle, "own:fortification", (Pose.at(20, 22),))
    locate(battle, "foe:engaged", (Pose.at(20, 20),))
    locate(battle, "foe:unengaged", (Pose.at(20, 26),))
    if mixed:
        locate(battle, "own:infantry", grid(battle.units["own:infantry"], 20, 15.8))
    anchor(battle)

    session = battle.session
    request = begin(session)
    if request.decision_type == "start_mission_action":
        choose_shooting(session, request, "continue_to_shooting")
    request = declaration_request(session, shooter, "normal")
    row = next(r for r in weapon_rows(request) if r["wargear_id"] == f"{shooting_sheet}:{weapon}")
    if expected_modifier is None:
        before = session.lifecycle.to_payload()
        result = _submit_native_shot(session, request, (row,), "foe:engaged")
        assert result.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
        assert_valid(_submit_native_shot(session, request, (row,), "foe:unengaged"))
        return

    if weapon == "shuriken-pistol":
        rifle = next(
            candidate
            for candidate in weapon_rows(request)
            if candidate["wargear_id"] == f"{RANGERS}:long-rifle"
            and candidate["model_instance_id"] == row["model_instance_id"]
        )
        before = session.lifecycle.to_payload()
        mixed_loadout = _submit_native_shot(session, request, (row, rifle), "foe:engaged")
        assert mixed_loadout.status_kind is LifecycleStatusKind.INVALID
        assert "mixed_close_quarters_non_close_quarters_declaration" in str(mixed_loadout.payload)
        assert session.lifecycle.to_payload() == before

    assert_valid(_submit_native_shot(session, request, (row,), "foe:engaged"))
    (pool,) = accepted_pools(session)
    assert pool["hit_roll_modifier"] == expected_modifier
    assert isinstance(pool["targeting_rule_ids"], list)
    assert (FORTIFICATION_ENGAGEMENT_RULE_ID in pool["targeting_rule_ids"]) is (
        expected_modifier == -1
    )
    finish_attacks(session)
    hit_rolls = [
        cast(dict[str, JsonValue], event["payload"])
        for event in events(session, "attack_sequence_step")
        if event["step"] == "hit"
    ]
    assert hit_rolls
    assert all(roll["modifier"] == expected_modifier for roll in hit_rolls)
    assert all(roll["capped_modifier"] == expected_modifier for roll in hit_rolls)


def _submit_native_shot(
    session: LocalGameSession,
    request: DecisionRequest,
    weapons: tuple[dict[str, JsonValue], ...],
    target: str,
) -> LifecycleStatus:
    payload = shooting_payload(request, list(weapons), (target,) * len(weapons))
    assert isinstance(payload, dict)
    declarations = cast(list[dict[str, JsonValue]], payload["declarations"])
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, JsonValue], request.payload["proposal_request"])
    candidates = cast(list[dict[str, JsonValue]], proposal["target_candidates"])
    for declaration, weapon in zip(declarations, weapons, strict=True):
        candidate = next(
            row
            for row in candidates
            if row["target_unit_instance_id"] == target
            and row["weapon_instance_id"] == weapon["weapon_instance_id"]
            and row["weapon_profile_id"] == weapon["weapon_profile_id"]
        )
        declaration["selected_weapon_ability_ids"] = [
            cast(list[dict[str, JsonValue]], choice["options"])[0]["option_id"]
            for choice in cast(
                list[dict[str, JsonValue]], candidate["required_weapon_ability_selections"]
            )
        ]
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"fortification:shoot:{target}:{len(weapons)}",
        payload=payload,
    )


def test_fortification_native_shallow_crossing_is_independent_of_waypoint(
    section09_definitions: Section02Definitions,
) -> None:
    d = with_fortification(section09_definitions, provider_sheet=LORD, fortification_sheet=GNARLMAW)
    unit = d.unit("000004090")
    provider = d.unit(LORD, army_id="enemy", identity="fortification")
    first, second = unit.own_model_ids()
    first_base = geometry_model_at_pose(model=unit.own_models[0], pose=Pose.at(10, 10)).base
    obstacle_base = geometry_model_at_pose(model=provider.own_models[0], pose=Pose.at(10, 10)).base
    assert isinstance(first_base, CircularBase)
    assert isinstance(obstacle_base, CircularBase)
    reach = first_base.radius + obstacle_base.radius
    for split in (False, True):
        for overlap in (0.008, 0.0, -0.008):
            starts = (Pose.at(10, 10), Pose.at(7, 10))
            state = native_state(
                d,
                unit,
                starts,
                enemy=provider,
                enemy_poses=(Pose.at(10 + reach - overlap, 11.25),),
            )
            attach_mission(state)
            add_unit(
                state, d.unit("000004090", identity="spare"), (Pose.at(10, 30), Pose.at(12.5, 30))
            )
            state.battle_shocked_unit_ids.append(unit.unit_instance_id)
            session = movement_session(d, state)
            action = select(session, unit)
            anchor_hazard_scene(session)
            request = choose(session, action, "fall_back:desperate_escape")
            first_path: tuple[Pose, ...] = (starts[0], Pose.at(10, 17))
            if split:
                first_path = (first_path[0], Pose.at(10, 11.25), first_path[1])
            status = _submit_fall_back(
                session,
                request,
                unit.unit_instance_id,
                ((first, first_path), (second, (starts[1], Pose.at(7, 17)))),
                result_id="shallow-crossing",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            assert tuple(roll.requirement.model_instance_id for roll in _escape_rolls(session)) == (
                (first,) if overlap > 0 else ()
            )


def test_fortification_crossing_uses_planar_body_projection_and_strict_clearance() -> None:
    mover = Model("mover", Pose.at(10, 10), CircularBase(1), ModelVolume(1))
    enemy = Model("enemy", Pose.at(12, 11.25), CircularBase(1), ModelVolume(1))
    for z in (0.0, 5.0):
        for split in (False, True):
            start, end = Pose.at(10, 10, z), Pose.at(10, 17, z)
            poses = (start, Pose.at(10, 11.25, z), end) if split else (start, end)
            witness = PathWitness.for_paths(((mover.model_id, poses),))
            for obstacle_x, expected in (
                (11.992, (enemy.model_id,)),
                (11.999999998, (enemy.model_id,)),
                (11.999999999, ()),
                (12.0, ()),
                (12.008, ()),
            ):
                support = replace(enemy, pose=Pose.at(obstacle_x, 11.25))
                assert (
                    _enemy_model_ids_crossed_by_witness(
                        moving_model=mover,
                        witness=witness,
                        enemy_models=(support,),
                        check_continuous_motion=True,
                    )
                    == expected
                )
            # The same explicit overhang geometry as section 17's body fixture.
            body = ModelBodyPart("overhang", CircularBase(0.5), 3, 0, 1, 1, "constructed:s17:body")
            support = replace(enemy, pose=Pose.at(8.492, 11.25), base=CircularBase(0.25))
            assert _enemy_model_ids_crossed_by_witness(
                moving_model=mover,
                witness=witness,
                enemy_models=(support, replace(support, model_id="body", body_parts=(body,))),
                check_continuous_motion=True,
            ) == ("body",)


def _escape_rolls(session: LocalGameSession) -> tuple[DesperateEscapeRoll, ...]:
    return tuple(
        DesperateEscapeRoll.from_payload(
            cast(DesperateEscapeRollPayload, event["desperate_escape_roll"])
        )
        for event in events(session, "desperate_escape_roll_resolved")
    )


def _submit_fall_back(
    session: LocalGameSession,
    request: DecisionRequest,
    unit_id: str,
    paths: tuple[tuple[str, tuple[Pose, ...]], ...],
    *,
    result_id: str,
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=cast(
            JsonValue,
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.FALL_BACK,
                unit_instance_id=unit_id,
                movement_phase_action="fall_back",
                movement_mode="fall_back",
                fall_back_mode="desperate_escape",
                witness=PathWitness.for_paths(paths),
            ).to_payload(),
        ),
    )


@pytest.mark.parametrize(
    ("new_crossing_fails", "rng_label", "initial_enemy_y"),
    [
        (False, "fortification-crossing-retry-30", 11.55),
        (True, "fortification-crossing-retry-4", 11.55),
        (False, "fortification-crossing-retry-0", 12.25),
    ],
    ids=("pass", "fail", "disengaged-after-casualty"),
)
def test_fortification_survivor_retry_rolls_each_new_crossing_only_once(
    faction_definitions: Section02Definitions,
    new_crossing_fails: bool,
    rng_label: str,
    initial_enemy_y: float,
) -> None:
    d = with_fortification(faction_definitions, provider_sheet=LORD, fortification_sheet=GNARLMAW)
    battle = scene(
        d,
        (selection(d, AVENGERS, "retreat"), selection(d, AVENGERS, "spare")),
        (selection(d, LORD, "fortification"),),
        seed="fortification-crossing-retry",
        rng_seed_label=rng_label,
    )
    unit = battle.units["own:retreat"]
    first, second, middle, fourth, last = unit.own_model_ids()
    fortification = battle.units["foe:fortification"]
    starts = tuple(Pose.at(x, 10) for x in (6, 8, 10.6, 13.2, 15.2))
    locate(battle, unit.unit_instance_id, starts)
    locate(battle, fortification.unit_instance_id, (Pose.at(10.6, initial_enemy_y),))
    apply_direct_battle_shock_state(
        state=battle.state,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        source_result_id="fixture-starting-battle-shock",
        battle_round=battle.state.battle_round,
    )
    anchor(battle)

    session = battle.session
    action = select(session, unit)
    anchor_hazard_scene(session)
    grant = choose(session, action, "fall_back:desperate_escape")
    assert grant.decision_type == "select_movement_action_grant"
    request = choose(session, grant, "decline_movement_action_grant")
    initial_paths = tuple(
        (
            model_id,
            (start, Pose.at(9.48, 12), end) if model_id == second else (start, end),
        )
        for model_id, start, end in zip(
            (first, second, middle, fourth, last),
            starts,
            tuple(Pose.at(start.position.x, 16) for start in starts),
            strict=True,
        )
    )
    after_initial = _submit_fall_back(
        session, request, unit.unit_instance_id, initial_paths, result_id="initial-path"
    )
    initial_rolls = _escape_rolls(session)
    assert tuple(roll.requirement.model_instance_id for roll in initial_rolls) == (second, middle)
    assert tuple(roll.is_failed for roll in initial_rolls) == (False, True), initial_rolls
    assert after_initial.decision_request is not None, after_initial
    mortal = after_initial.decision_request
    assert mortal.decision_type == "select_mortal_wound_model", mortal
    after_casualty = session.submit_option(
        request_id=mortal.request_id, result_id="crossing-casualty", option_id=middle
    )
    assert after_casualty.status_kind is LifecycleStatusKind.INVALID, after_casualty
    assert isinstance(after_casualty.payload, dict)
    assert after_casualty.payload["violation_code"] == "unit_coherency_broken"

    retry = session.lifecycle.pending_decision_request()
    assert retry is not None
    assert retry.decision_type == request.decision_type
    if initial_enemy_y == 12.25:
        assert (
            scenario_physically_engaged_enemy_rules_unit_ids(
                scenario=battlefield_scenario_for_state(state=battle.state),
                ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
                unit_instance_id=unit.unit_instance_id,
            )
            == ()
        )
        checkpoint = session.lifecycle.to_payload()
        restored_state = GameState.from_payload(checkpoint["state"])
        restored_decisions = DecisionController.from_payload(checkpoint["decisions"])
        (restored_request,) = restored_decisions.queue.pending_requests
        assert restored_request == retry
        restored_retry = completed_escape_retry(
            state=restored_state,
            decisions=restored_decisions,
            proposal=MovementProposalRequest.from_decision_request_payload(
                restored_request.payload
            ),
            fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        )
        assert restored_retry is not None
        assert restored_retry.start_engaged_enemy_unit_ids == (fortification.unit_instance_id,)
    invalid_paths = tuple(
        (model_id, (poses[0], Pose.at(11.72, 12), poses[-1]))
        if model_id == fourth and rng_label == "fortification-crossing-retry-4"
        else (model_id, poses)
        for model_id, poses in initial_paths
        if model_id != middle
    )
    before_mismatch = session.lifecycle.to_payload()
    mismatch = _submit_fall_back(
        session, retry, "unrelated-unit", invalid_paths, result_id="mismatched-retry"
    )
    assert mismatch.status_kind is LifecycleStatusKind.INVALID, mismatch
    assert session.lifecycle.to_payload() == before_mismatch
    active_state = session.lifecycle.state
    assert active_state is not None
    before_rejection = active_state.to_payload()
    records = session.lifecycle.decision_controller.event_log.records
    rejected = _submit_fall_back(
        session, retry, unit.unit_instance_id, invalid_paths, result_id="invalid-retry"
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID, rejected
    assert isinstance(rejected.payload, dict)
    assert rejected.payload["violation_code"] == "unit_coherency_broken"
    after_rejection = active_state.to_payload()
    assert after_rejection == {
        **before_rejection,
        "decision_request_count": before_rejection["decision_request_count"] + 1,
    }
    assert session.lifecycle.decision_controller.event_log.records[: len(records)] == records
    assert not {
        "dice_rolled",
        "desperate_escape_roll_requested",
        "desperate_escape_roll_resolved",
        "desperate_escape_hazard_mortals_resolved",
        "fall_back_move_applied",
    }.intersection(
        record.event_type
        for record in session.lifecycle.decision_controller.event_log.records[len(records) :]
    )
    assert _escape_rolls(session) == initial_rolls

    retry = session.lifecycle.pending_decision_request()
    assert retry is not None
    corrected = (
        (first, (starts[0], Pose.at(7.5, 16))),
        (second, (starts[1], Pose.at(9.48, 12), Pose.at(9.5, 16))),
        (fourth, (starts[3], Pose.at(11.72, 12), Pose.at(12, 16))),
        (last, (starts[4], Pose.at(14.5, 16))),
    )
    status = _submit_fall_back(
        session, retry, unit.unit_instance_id, corrected, result_id="valid-retry"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    rolls = _escape_rolls(session)
    assert rolls[:2] == initial_rolls
    assert len(rolls) == 3
    assert rolls[-1].requirement.model_instance_id == fourth
    assert rolls[-1].requirement.enemy_model_ids == fortification.own_model_ids()
    assert rolls[-1].is_failed is new_crossing_fails, rolls[-1]
    if new_crossing_fails:
        assert status.decision_request is not None, status
        assert status.decision_request.decision_type == "select_mortal_wound_model"
        status = session.submit_option(
            request_id=status.decision_request.request_id,
            result_id="new-crossing-casualty",
            option_id=last,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    (completed,) = events(session, "movement_activation_completed")
    assert completed.get("fortification_desperate_escape_exempt_model_ids") == [first, last]
    assert completed.get("start_engaged_enemy_unit_instance_ids") == [
        fortification.unit_instance_id
    ]
    assert len(events(session, "desperate_escape_hazard_mortals_resolved")) == (
        2 if new_crossing_fails else 1
    )
    decisions = session.lifecycle.decision_controller
    mutation_index = next(
        i
        for i, record in enumerate(decisions.event_log.records)
        if record.event_type == "movement_activation_completed"
    )
    authority = validate_movement_completion_decision_authority(
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        mutation_index=mutation_index,
        payload=completed,
    )
    assert authority is not None
    assert authority.witness == PathWitness.for_paths(
        tuple(path for path in corrected if not (new_crossing_fails and path[0] == last))
    )


@pytest.fixture(scope="session")
def fortification_pivot_definitions(
    selected_army_source_index: Path | None,
) -> Section02Definitions:
    return Section02Definitions(
        _ability_support_catalog_package(
            datasheet_ids=(INFRACTORS, LORD, "000001115", "000004090"),
            source_index_dir=selected_army_source_index,
        ),
        0,
    )


@pytest.mark.parametrize("overlap", [0.008, 0.0, -0.008], ids=("crossing", "tangent", "clear"))
def test_fortification_native_bloodcrusher_pivot_is_independent_of_waypoint(
    fortification_pivot_definitions: Section02Definitions, overlap: float
) -> None:
    d = with_fortification(
        fortification_pivot_definitions, provider_sheet=LORD, fortification_sheet=GNARLMAW
    )
    unit = d.unit("000001115")
    first, second, third = unit.own_model_ids()
    provider = d.unit(LORD, army_id="enemy", identity="fortification")
    starts = (Pose.at(10, 10), Pose.at(13.65, 10), Pose.at(17.3, 10))
    moving_base = geometry_model_at_pose(model=unit.own_models[0], pose=starts[0]).base
    obstacle_base = geometry_model_at_pose(model=provider.own_models[0], pose=starts[0]).base
    assert isinstance(moving_base, OvalBase)
    assert math.isclose(moving_base.length, 90 / 25.4)
    assert math.isclose(moving_base.width, 52.5 / 25.4)
    assert isinstance(obstacle_base, CircularBase)
    obstacle = Pose.at(10, 10 + moving_base.max_radius() + obstacle_base.radius - overlap)
    for split in (True, False):
        state = native_state(d, unit, starts, enemy=provider, enemy_poses=(obstacle,))
        attach_mission(state)
        add_unit(state, d.unit("000004090", identity="spare"), (Pose.at(10, 30), Pose.at(12.5, 30)))
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
        session = movement_session(d, state)
        action = select(session, unit)
        anchor_hazard_scene(session)
        request = choose(session, action, "fall_back:desperate_escape")
        pivot = (starts[0], Pose.at(10, 10, facing_degrees=90)) if split else (starts[0],)
        status = _submit_fall_back(
            session,
            request,
            unit.unit_instance_id,
            (
                (
                    first,
                    (
                        *pivot,
                        Pose.at(10, 10, facing_degrees=180),
                        Pose.at(10, 6, facing_degrees=180),
                    ),
                ),
                (second, (starts[1], Pose.at(13.65, 6))),
                (third, (starts[2], Pose.at(17.3, 6))),
            ),
            result_id="bloodcrusher-pivot",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, (split, status)
        rolls = _escape_rolls(session)
        assert tuple(roll.requirement.model_instance_id for roll in rolls) == (
            (first,) if overlap > 0 else ()
        ), (split, rolls)
        if rolls:
            assert rolls[0].requirement.enemy_model_ids == provider.own_model_ids()


def test_fortification_crossing_respects_physical_overlap_tolerance() -> None:
    start, end = Pose.at(10, 10), Pose.at(10, 17)
    for penetration, expected in ((0.5e-9, False), (2e-9, True)):
        obstacle = Pose.at(12 - penetration, 11.25)
        for first in (CircularBase(1), OvalBase(2, 2)):
            for second in (CircularBase(1), OvalBase(2, 2)):
                assert (
                    physical_footprints_overlap(first, Pose.at(10, 11.25), second, obstacle)
                    is expected
                )
                _assert_crossing(first, second, obstacle, (start, end), expected)

    # A physical margin at a flat face can persist along an entire segment.
    slab = RectangularBase(16, 4)
    for penetration, expected in ((1e-9, False), (2e-9, True)):
        obstacle = Pose.at(10, 13 - penetration)
        _assert_crossing(
            OvalBase(4, 2), slab, obstacle, (Pose.at(6, 10), Pose.at(14, 10)), expected
        )


def test_fortification_crossing_interpolates_rotation_and_translation_together() -> None:
    moving, enemy = OvalBase(4, 2), CircularBase(0.75)
    start, end = Pose.at(9, 10), Pose.at(11, 10, facing_degrees=180)
    for obstacle_y, expected in ((12.742, True), (12.75, False)):
        obstacle = Pose.at(10, obstacle_y)
        _assert_crossing(moving, enemy, obstacle, (start, end), expected)
        _assert_crossing(
            moving, enemy, obstacle, (start, Pose.at(9.5, 10, facing_degrees=45), end), expected
        )
    # Across the zero-degree seam the short turn keeps the narrow side toward
    # the obstacle. Sweeping the long way would reach it.
    start, end = Pose.at(9, 10, facing_degrees=350), Pose.at(11, 10, facing_degrees=10)
    obstacle = Pose.at(10, 12.5)
    _assert_crossing(moving, enemy, obstacle, (start, end), False)
    _assert_crossing(moving, enemy, obstacle, (start, Pose.at(10, 10), end), False)

    # Neither endpoint nor the initial temporal midpoint reaches this obstacle.
    start, end = Pose.at(10, 10), Pose.at(10, 10, facing_degrees=150)
    obstacle = Pose.at(10, 12.738)
    angle = math.radians(75)
    assert math.hypot(2 * math.sin(angle), math.cos(angle)) + enemy.radius < 2.738
    _assert_crossing(moving, enemy, obstacle, (start, end), True)
    _assert_crossing(
        moving, enemy, obstacle, (start, Pose.at(10, 10, facing_degrees=30), end), True
    )
    _assert_crossing(RectangularBase(4, 2), enemy, obstacle, (start, end), True)


def _assert_crossing(
    first: BaseShape,
    second: BaseShape,
    obstacle: Pose,
    poses: tuple[Pose, ...],
    expected: bool,
) -> None:
    mover = Model("mover", poses[0], first, ModelVolume(1))
    enemy = Model("obstacle", obstacle, second, ModelVolume(1))
    assert _enemy_model_ids_crossed_by_witness(
        moving_model=mover,
        witness=PathWitness.for_paths(((mover.model_id, poses),)),
        enemy_models=(enemy,),
        check_continuous_motion=True,
    ) == ((enemy.model_id,) if expected else ())


def _native_gnarlmaw_config(tmp_path: Path) -> GameConfig:
    from tests.support.monster_mash_v995 import ROOT, monster_mash_vs_cavalcade_config
    from warhammer40k_core.engine.player_army_list import (
        army_muster_request_from_player_army_list,
        load_player_army_list,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        chaos_daemons_gnarlmaw_2026_11 as gnarlmaw,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import mfm_2026_10

    baseline = monster_mash_vs_cavalcade_config()
    package = gnarlmaw.catalog_package()
    roster_path = tmp_path / "gnarlmaw-development.json"
    original = json.loads((ROOT / "data/army_lists/monster-mash.json").read_bytes())
    original["declared_total_points"] = 1985
    original["provenance"]["source_format"] = "native_development_fixture"
    for line in original["units"]:
        if line["selection"]["unit_selection_id"] == "bloodletters":
            line["selection"] = {
                "unit_selection_id": "gnarlmaw",
                "datasheet_id": gnarlmaw.DATASHEET_ID,
                "model_profile_selections": [
                    {"model_profile_id": gnarlmaw.PROFILE_ID, "model_count": 1}
                ],
                "wargear_selections": [],
                "mustering_option_selections": [],
            }
            line["declared_points"] = 100
            break
    else:
        pytest.fail("Expected the export to contain a Bloodletters line for replacement.")
    roster_path.write_text(json.dumps(original), encoding="utf-8")
    rosters = (
        load_player_army_list(roster_path),
        load_player_army_list(ROOT / "data/army_lists/cavalcade-shadow-bloodthirster.json"),
    )
    return replace(
        baseline,
        army_catalog=package.army_catalog,
        model_geometries=package.model_geometries,
        army_muster_requests=tuple(
            army_muster_request_from_player_army_list(
                catalog=package.army_catalog,
                army_list=roster,
                points_source_package=mfm_2026_10.source_package(),
                army_id=old.army_id,
                player_id=old.player_id,
            )
            for old, roster in zip(baseline.army_muster_requests, rosters, strict=True)
        ),
    )


def test_gnarlmaw_deploys_from_native_development_roster(tmp_path: Path) -> None:
    from tests.support.monster_mash_v995 import (
        _submit_option,  # pyright: ignore[reportPrivateUsage]
    )
    from tests.support.section04_fixtures import pending
    from warhammer40k_core.adapters.access_control import ViewerContext
    from warhammer40k_core.core.model_geometry_catalog import (
        GeometryReviewStatus,
        GeometryRulesFootprintPolicy,
    )
    from warhammer40k_core.engine.battlefield_state import ModelPlacement
    from warhammer40k_core.engine.deployment import (
        DeploymentPlacementProposal,
        DeploymentPlacementRequest,
    )
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import SetupStep
    from warhammer40k_core.engine.replay import ReplayRunner

    config = _native_gnarlmaw_config(tmp_path)
    session = LocalGameSession()
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    for kind, choice in (
        ("select_secondary_missions", "fixed:assassination:bring_it_down"),
        ("select_secondary_missions", "fixed:assassination:bring_it_down"),
        ("select_reserve_declaration", "complete_reserve_declarations"),
        ("select_reserve_declaration", "complete_reserve_declarations"),
        ("select_deployment_unit", "deploy:cavalcade-b:belakor"),
    ):
        status = _submit_option(session, status, kind, choice)

    def submit_placement(pose: Pose, result_id: str) -> LifecycleStatus:
        request = pending(session)
        assert request.actor_id is not None
        viewer = ViewerContext.for_player(request.actor_id)
        issued = session.view_for_context(viewer=viewer)["pending_decision"]
        assert issued is not None
        placement = DeploymentPlacementRequest.from_decision_request_payload(issued["payload"])
        (model_id,) = placement.model_instance_ids
        army_id = "cavalcade-b" if request.actor_id == "player-b" else "monster-mash-a"
        proposal = DeploymentPlacementProposal(
            proposal_request_id=placement.request_id,
            proposal_kind=placement.proposal_kind,
            game_id=placement.game_id,
            ruleset_descriptor_hash=placement.ruleset_descriptor_hash,
            setup_step=SetupStep.DEPLOY_ARMIES,
            player_id=placement.player_id,
            unit_instance_id=placement.unit_instance_id,
            placement_kind=placement.placement_kind,
            model_placements=(
                ModelPlacement(
                    army_id, placement.player_id, placement.unit_instance_id, model_id, pose
                ),
            ),
            context=placement.context,
        )
        return session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=issued["request_id"],
            payload=validate_json_value(proposal.to_payload()),
            result_id=result_id,
        )

    status = submit_placement(Pose.at(41, 57), "place-defender")
    status = _submit_option(
        session, status, "select_deployment_unit", "deploy:monster-mash-a:gnarlmaw"
    )
    state = session.lifecycle.state
    assert state is not None
    army = next(a for a in state.army_definitions if a.player_id == "player-a")
    assert army.roster_legality_report.is_legal
    unit = next(u for u in army.units if u.datasheet_id == GNARLMAW)
    (model,) = unit.own_models
    assert not model.wargear_ids
    record = next(
        g for g in config.model_geometries if g.model_profile_id == model.model_profile_id
    )
    assert record.rules_footprint_policy is GeometryRulesFootprintPolicy.USE_HULL
    assert record.support_base is None
    assert all(
        e.reviewer_status is GeometryReviewStatus.PROVISIONAL_ESTIMATE for e in record.evidence
    )
    assert model.geometry.primary_part().radius_x_inches * 50.8 == pytest.approx(120)
    assert model.geometry.primary_part().radius_y_inches * 50.8 == pytest.approx(90)

    before = session.lifecycle.to_payload()
    for pose, code in (
        (Pose.at(41, 57), "model_overlap"),
        (Pose.at(20, 3), "infiltrators_enemy_zone_distance"),
    ):
        rejected = submit_placement(pose, f"invalid-{code}")
        assert rejected.status_kind is LifecycleStatusKind.INVALID
        assert code in str(rejected.to_payload())
        assert session.lifecycle.to_payload() == before

    accepted = submit_placement(Pose.at(17, 3), "place-gnarlmaw")
    assert accepted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, accepted
    assert state.battlefield_state is not None
    placed = state.battlefield_state.model_placement_by_id(model.model_instance_id)
    assert placed.pose == Pose.at(17, 3)
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    analysis = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="native-gnarlmaw-deployment")
    ).run()
    assert analysis.reproduced_exactly, analysis.to_payload()


def test_gnarlmaw_diseased_cover_uses_native_hull_occlusion(tmp_path: Path) -> None:
    from tests.support.faction_batch01 import unit_placement
    from warhammer40k_core.core.ruleset_descriptor import CoverEffect
    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.engine.army_mustering import muster_army
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldRuntimeState,
        BattlefieldScenario,
        PlacedArmy,
    )
    from warhammer40k_core.engine.battlefield_visibility_context import (
        battlefield_visibility_context,
    )
    from warhammer40k_core.engine.shooting_model_blockers import shooting_dynamic_model_blockers
    from warhammer40k_core.engine.shooting_types import ShootingType
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

    config = _native_gnarlmaw_config(tmp_path)
    mission = config.mission_setup
    assert mission is not None
    mission = replace(
        mission,
        battlefield_layout_id=None,
        deployment_map_id="gnarlmaw-cover:deployment",
        terrain_layout_id="gnarlmaw-cover:terrain",
        battlefield_regions=(),
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
    )
    descriptor = config.ruleset_descriptor
    armies = tuple(
        muster_army(
            catalog=config.army_catalog,
            request=request,
            model_geometries=config.model_geometries,
        )
        for request in config.army_muster_requests
    )
    owner, opponent = armies
    shooter = next(u for u in owner.units if u.datasheet_id == "000001125")
    target = next(u for u in opponent.units if u.datasheet_id == "000001148")
    source = next(u for u in owner.units if u.datasheet_id == GNARLMAW)
    unrelated = next(u for u in owner.units if u.datasheet_id == "000001465")
    attacking_model = shooter.own_models[0]
    (target_model,) = target.own_models
    item, profile = next(
        (item, profile)
        for item in config.army_catalog.wargear
        if item.wargear_id in attacking_model.wargear_ids
        for profile in item.weapon_profiles
        if profile.range_profile.kind is RangeProfileKind.DISTANCE
    )
    pool = RangedAttackPool(
        weapon_instance_id="native-cover:weapon",
        attacker_model_instance_id=attacking_model.model_instance_id,
        wargear_id=item.wargear_id,
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=(target_model.model_instance_id,),
        target_in_range_model_ids=(target_model.model_instance_id,),
    )
    for source_y, unrelated_y, expected_blocker in (
        (20, 37, source),
        (34, 37, None),
        (34, 22.5, unrelated),
    ):
        state = GameState.from_config(replace(config, mission_setup=mission))
        for army in armies:
            state.record_army_definition(army)
        battlefield = BattlefieldRuntimeState(
            config.game_id,
            mission.battlefield_width_inches,
            mission.battlefield_depth_inches,
            placed_armies=(
                PlacedArmy(
                    owner.army_id,
                    owner.player_id,
                    (
                        unit_placement(
                            owner.army_id,
                            owner.player_id,
                            shooter,
                            (Pose.at(10, 20), Pose.at(8.5, 20), Pose.at(11.5, 20)),
                        ),
                        unit_placement(
                            owner.army_id, owner.player_id, source, (Pose.at(17, source_y),)
                        ),
                        unit_placement(
                            owner.army_id, owner.player_id, unrelated, (Pose.at(16, unrelated_y),)
                        ),
                    ),
                ),
                PlacedArmy(
                    opponent.army_id,
                    opponent.player_id,
                    (
                        unit_placement(
                            opponent.army_id, opponent.player_id, target, (Pose.at(22, 20),)
                        ),
                    ),
                ),
            ),
        )
        state.record_battlefield_state(battlefield)
        scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield)
        physical = {model.model_id: model for model in scenario.placed_geometry_models()}
        context = battlefield_visibility_context(
            scenario=scenario,
            ruleset_descriptor=descriptor,
            los_cache_key="gnarlmaw-cover-probe",
            observer_model=physical[attacking_model.model_instance_id],
            target_models=(physical[target_model.model_instance_id],),
            target_model_keywords=((target_model.model_instance_id, target_model.keywords),),
            dynamic_model_blockers=shooting_dynamic_model_blockers(
                scenario=scenario,
                observing_unit_id=shooter.unit_instance_id,
                target_unit_id=target.unit_instance_id,
            ),
        )
        witness = context.resolve_line_of_sight()
        assert witness.unit_visible
        assert witness.unit_fully_visible is (expected_blocker is None)
        if expected_blocker is not None:
            assert any(
                b.blocker_id in expected_blocker.own_model_ids() and b.blocks_full_visibility
                for b in witness.all_blocker_records()
            )
        cover = cover_for_allocated_model(
            state=state,
            ruleset_descriptor=descriptor,
            pool=pool,
            allocated_model_id=target_model.model_instance_id,
        )
        assert cover is not None
        assert cover.has_benefit is (expected_blocker is source)
        if expected_blocker is source:
            assert cover.source_feature_ids == source.own_model_ids()
            assert cover.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER
