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
from warhammer40k_core.engine.unit_factory import UnitInstance
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


def _native_gnarlmaw_config(tmp_path: Path, *, compact_bloodcrushers: bool = False) -> GameConfig:
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
    opponent_path = ROOT / "data/army_lists/cavalcade-shadow-bloodthirster.json"
    if compact_bloodcrushers:
        opponent = json.loads(opponent_path.read_bytes())
        first_bloodcrushers = next(
            line
            for line in opponent["units"]
            if line["selection"]["unit_selection_id"] == "bloodcrushers-1"
        )
        # The pinned MFM first-unit bracket is 210 for six or 95 for three.
        # Preserve the export's separately priced enhancement.
        reduction = 210 - 95
        opponent["declared_total_points"] -= reduction
        first_bloodcrushers["declared_points"] -= reduction
        selection = first_bloodcrushers["selection"]
        selection["model_profile_selections"][1]["model_count"] = 2
        selection["wargear_selections"] = []
        opponent_path = tmp_path / "compact-bloodcrushers.json"
        opponent_path.write_text(json.dumps(opponent), encoding="utf-8")
    rosters = (load_player_army_list(roster_path), load_player_army_list(opponent_path))
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
    manifest = session.support_profile()["capability_manifest"]
    (cover_row,) = (
        row for row in manifest["rule_rows"] if row["owner_id"] == "000001470:diseased-cover"
    )
    assert cover_row["load_support"] == "generic_rule_ir"
    assert cover_row["semantic_execution"] == "engine_consumed"
    assert cover_row["metadata"]["diagnostic_reasons"] == [
        "development:gnarlmaw-diseased-cover:pre-hit-v1"
    ]
    assert not any(
        effect["rule_row_id"] == cover_row["row_id"] for effect in manifest["unsupported_effects"]
    )
    assert (
        next(
            row["status"]
            for row in manifest["mode_capabilities"]
            if row["dimension"] == "FULL_GAME_SUPPORTED"
        )
        == "unsupported"
    )
    assert manifest["certification_claims"]["phase20a_certified"] is False
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
    assert unit.keywords == (
        "CHAOS",
        "DAEMON",
        "FECULENT GNARLMAW",
        "FORTIFICATION",
        "FRAME",
        "NURGLE",
    )
    assert unit.faction_keywords == ("LEGIONES DAEMONICA",)
    (model,) = unit.own_models
    assert not model.wargear_ids
    geometries = config.model_geometries
    assert geometries is not None
    record = next(g for g in geometries if g.model_profile_id == model.model_profile_id)
    assert record.rules_footprint_policy is GeometryRulesFootprintPolicy.USE_HULL
    assert record.support_base is None
    assert all(
        e.reviewer_status is GeometryReviewStatus.PROVISIONAL_ESTIMATE for e in record.evidence
    )
    assert math.isclose(model.geometry.primary_part().radius_x_inches * 50.8, 120)
    assert math.isclose(model.geometry.primary_part().radius_y_inches * 50.8, 90)

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


def _circular_attack_fixture_body(
    unit: UnitInstance, *, tall_front_model: bool = False, radius: float = 0.25
) -> UnitInstance:
    from warhammer40k_core.geometry.model_geometry import BaseFootprintKind, FootprintPart

    return replace(
        unit,
        own_models=tuple(
            replace(
                model,
                geometry=replace(
                    model.geometry,
                    footprint_kind=BaseFootprintKind.CIRCULAR,
                    parts=(FootprintPart("fixture", BaseFootprintKind.CIRCULAR, radius, radius),),
                    height_inches=10.0 if tall_front_model and index == 0 else 2.0,
                    body_parts=(),
                ),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _gnarlmaw_native_attack(
    tmp_path: Path,
    *,
    screen: str,
    ignores_cover: bool = False,
    ordinary_cover: bool = False,
    attacks: int | None = None,
    wounded_front: int | None = None,
    first_pool: bool = False,
    seed: str = "gnarlmaw-dice-1",
) -> tuple[LocalGameSession, UnitInstance, UnitInstance]:
    from tests.support.faction_batch01 import Scene, unit_placement
    from tests.support.private_randomness import fixture_private_rng_seed
    from tests.support.section04_fixtures import pending
    from tests.support.section10_fixtures import submit
    from warhammer40k_core.core.model_geometry_catalog import (
        GeometryRulesFootprintPolicy,
        ModelFootprintKind,
    )
    from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, WeaponKeyword
    from warhammer40k_core.engine.army_mustering import (
        ArmyMusterRequest,
        WarlordSelection,
        muster_army,
    )
    from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
    from warhammer40k_core.engine.attack_sequence_model import GatheredAttackGroupPayload
    from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
    from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, PlacedArmy
    from warhammer40k_core.engine.core_stratagem_effects import GO_TO_GROUND_EFFECT_KIND
    from warhammer40k_core.engine.damage_allocation import (
        AllocationGroupPayload,
        allocation_context_for_unit,
    )
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
    from warhammer40k_core.engine.phase import GameLifecycleStage
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
    from warhammer40k_core.engine.phases.command import CommandPhaseHandler
    from warhammer40k_core.engine.phases.fight import FightPhaseHandler
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
    from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model

    precision = screen == "precision"
    multi_model = screen in ("mixed", "all", "precision")
    config = _native_gnarlmaw_config(tmp_path, compact_bloodcrushers=multi_model)
    lash_id = "000001648:lash-of-slaanesh"
    prior_weapon_id = "000001648:pavane-of-slaanesh"
    keyword = WeaponKeyword.PRECISION if precision else WeaponKeyword.IGNORES_COVER
    if ignores_cover or precision or attacks is not None:
        config = replace(
            config,
            army_catalog=replace(
                config.army_catalog,
                wargear=tuple(
                    replace(
                        item,
                        weapon_profiles=tuple(
                            replace(
                                profile,
                                keywords=(*profile.keywords, keyword)
                                if ignores_cover or precision
                                else profile.keywords,
                                attack_profile=AttackProfile.fixed(attacks)
                                if attacks is not None
                                else profile.attack_profile,
                                damage_profile=DamageProfile.fixed(30)
                                if precision
                                else profile.damage_profile,
                            )
                            for profile in item.weapon_profiles
                        ),
                    )
                    if item.wargear_id == lash_id
                    else replace(
                        item,
                        weapon_profiles=tuple(
                            replace(
                                profile,
                                keywords=(WeaponKeyword.TORRENT,),
                                abilities=(),
                                ability_sources=(),
                                attack_profile=AttackProfile.fixed(1),
                                damage_profile=DamageProfile.fixed(1),
                            )
                            for profile in item.weapon_profiles
                        ),
                    )
                    if first_pool and item.wargear_id == prior_weapon_id
                    else item
                    for item in config.army_catalog.wargear
                ),
            ),
        )
    mission = config.mission_setup
    assert mission is not None
    mission = replace(
        mission,
        battlefield_layout_id=None,
        deployment_map_id="gnarlmaw-attack:deployment",
        terrain_layout_id="gnarlmaw-attack:terrain",
        battlefield_regions=(),
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
    )
    target_sheet = "000001115" if multi_model else "000001120"
    owner_sheets = ("000001648", GNARLMAW)
    if screen in ("unrelated", "precision"):
        owner_sheets = (*owner_sheets, "000001465")
    opponent_sheets = (
        ("000001148", target_sheet, "000001120") if precision else ("000001120", target_sheet)
    )
    selected_rosters: list[ArmyMusterRequest] = []
    for roster, sheets in zip(
        config.army_muster_requests, (owner_sheets, opponent_sheets), strict=True
    ):
        selections = tuple(
            s
            for s in roster.unit_selections
            if s.datasheet_id in sheets
            and (s.datasheet_id != "000001115" or s.unit_selection_id == "bloodcrushers-1")
        )
        ids = {s.unit_selection_id for s in selections}
        warlord = next(s for s in selections if s.datasheet_id == sheets[0])
        selected_rosters.append(
            replace(
                roster,
                unit_selections=selections,
                unit_points=tuple(p for p in roster.unit_points if p.unit_selection_id in ids),
                enhancement_assignments=(),
                enhancement_point_values=(),
                detachment_selection=replace(roster.detachment_selection, enhancement_ids=()),
                warlord_selection=WarlordSelection(
                    model_profile_id=warlord.model_profile_selections[0].model_profile_id,
                    model_index=1,
                    unit_selection_id=warlord.unit_selection_id,
                    source_id="fixture:gnarlmaw-attack-warlord",
                ),
            )
        )
    config = replace(
        config,
        army_muster_requests=tuple(selected_rosters),
        mission_setup=mission,
        private_rng_seed=fixture_private_rng_seed(seed),
    )
    if screen == "mixed":
        # Put the fixture silhouettes in the authoritative input so native
        # restore can re-muster the same models before replaying the shot.
        heights = {
            "000001115:bloodcrushers": 2.0,
            "000001115:bloodhunter": 10.0,
            "000001648:shalaxi-helbane-epic-hero": 2.0,
        }
        geometries = config.model_geometries
        assert geometries is not None
        config = replace(
            config,
            model_geometries=tuple(
                replace(
                    record,
                    model_geometry_id=f"fixture:gnarlmaw-mixed:{record.model_profile_id}",
                    rules_footprint_policy=GeometryRulesFootprintPolicy.USE_HULL,
                    footprint=replace(
                        record.footprint,
                        footprint_kind=ModelFootprintKind.CIRCULAR,
                        parts=tuple(
                            replace(
                                part,
                                footprint_kind=ModelFootprintKind.CIRCULAR,
                                radius_x_inches=0.25,
                                radius_y_inches=0.25,
                            )
                            for part in record.footprint.parts
                        ),
                    ),
                    support_base=None,
                    height=replace(record.height, height_inches=heights[record.model_profile_id]),
                )
                if record.model_profile_id in heights
                else record
                for record in geometries
            ),
        )
    state = GameState.from_config(config)
    owner, opponent = tuple(
        muster_army(
            catalog=config.army_catalog, request=roster, model_geometries=config.model_geometries
        )
        for roster in config.army_muster_requests
    )
    if multi_model and screen != "mixed":
        # Use simple fixture silhouettes for the Bloodcrushers and their observer.
        # Their native rules and allocation records still apply.
        # The screening Gnarlmaw keeps its actual catalog hull.
        owner = replace(
            owner,
            units=tuple(
                _circular_attack_fixture_body(u)
                if u.datasheet_id == "000001648"
                else _circular_attack_fixture_body(u, tall_front_model=True, radius=1.0)
                if precision and u.datasheet_id == "000001465"
                else u
                for u in owner.units
            ),
        )
        opponent = replace(
            opponent,
            units=tuple(
                _circular_attack_fixture_body(u, tall_front_model=u.datasheet_id != "000001148")
                if u.datasheet_id == target_sheet or precision
                else u
                for u in opponent.units
            ),
        )
    target = next(u for u in opponent.units if u.datasheet_id == target_sheet)
    if wounded_front is not None:
        target = replace(
            target,
            own_models=(
                replace(target.own_models[0], wounds_remaining=wounded_front),
                *target.own_models[1:],
            ),
        )
        opponent = replace(
            opponent,
            units=tuple(
                target if u.unit_instance_id == target.unit_instance_id else u
                for u in opponent.units
            ),
        )
    target_id = target.unit_instance_id
    leader_poses: dict[str, Pose] = {}
    visible_leader_ids: tuple[str, ...] = ()
    hidden_leader_ids: tuple[str, ...] = ()
    if precision:
        leaders = tuple(unit for unit in opponent.units if unit.unit_instance_id != target_id)
        leader_ids = tuple(unit.unit_instance_id for unit in leaders)
        formation = AttachedUnitFormation(
            attached_unit_instance_id=f"attached-unit:{opponent.army_id}:gnarlmaw-precision-fixture",
            bodyguard_unit_instance_id=target_id,
            leader_unit_instance_ids=leader_ids,
            component_unit_instance_ids=tuple(sorted((target_id, *leader_ids))),
            source_id="fixture:gnarlmaw-precision",
            attachment_source_ids=("fixture:gnarlmaw-precision-leaders",),
        )
        opponent = replace(opponent, attached_units=(formation,))
        target_id = formation.attached_unit_instance_id
        leader_poses = {"000001120": Pose.at(24, 20), "000001148": Pose.at(22, 31)}
    for army in (owner, opponent):
        state.record_army_definition(army)
    shooter = next(u for u in owner.units if u.datasheet_id == "000001648")
    source = next(u for u in owner.units if u.datasheet_id == GNARLMAW)
    source_pose = {
        "clear": Pose.at(15, 32),
        "unrelated": Pose.at(15, 32),
        "mixed": Pose.at(16, 20),
        "all": Pose.at(16, 20),
        "precision": Pose.at(16, 20),
    }.get(screen, Pose.at(15, 20))
    target_poses = {
        "mixed": (Pose.at(22, 20), Pose.at(22.3, 17.6), Pose.at(22.5, 15.2)),
        "all": (Pose.at(22, 20), Pose.at(26, 20), Pose.at(30, 20)),
        "precision": (Pose.at(22, 20), Pose.at(26, 20), Pose.at(30, 20)),
    }.get(screen, (Pose.at(22, 20),))
    other_placements = tuple(
        unit_placement(
            owner.army_id, owner.player_id, unit, (Pose.at(16, 25.5 if precision else 22.5),)
        )
        for unit in owner.units
        if unit.datasheet_id == "000001465"
    )
    state.record_battlefield_state(
        BattlefieldRuntimeState(
            config.game_id,
            mission.battlefield_width_inches,
            mission.battlefield_depth_inches,
            placed_armies=(
                PlacedArmy(
                    owner.army_id,
                    owner.player_id,
                    (
                        unit_placement(owner.army_id, owner.player_id, shooter, (Pose.at(10, 20),)),
                        unit_placement(owner.army_id, owner.player_id, source, (source_pose,)),
                        *other_placements,
                    ),
                ),
                PlacedArmy(
                    opponent.army_id,
                    opponent.player_id,
                    (
                        unit_placement(opponent.army_id, opponent.player_id, target, target_poses),
                        *(
                            unit_placement(
                                opponent.army_id,
                                opponent.player_id,
                                unit,
                                (leader_poses.get(unit.datasheet_id, Pose.at(49, 35)),),
                            )
                            for unit in opponent.units
                            if unit.unit_instance_id != target.unit_instance_id
                        ),
                    ),
                ),
            ),
        )
    )
    if ordinary_cover:
        state.record_persisting_effect(
            PersistingEffect(
                effect_id="fixture:gnarlmaw-independent-cover",
                source_rule_id="core-stratagem:go-to-ground",
                owner_player_id=opponent.player_id,
                target_unit_instance_ids=(target.unit_instance_id,),
                started_battle_round=1,
                started_phase=BattlePhase.SHOOTING,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload={"effect_kind": GO_TO_GROUND_EFFECT_KIND, "benefit_of_cover": True},
            )
        )

    if multi_model or screen == "unrelated":
        profile = next(
            item for item in config.army_catalog.wargear if item.wargear_id == lash_id
        ).weapon_profiles[0]
        visible = shooting_target_candidate_for_model(
            scenario=battlefield_scenario_for_state(state=state),
            ruleset_descriptor=config.ruleset_descriptor,
            attacker_unit=shooter,
            attacker_model_instance_id=shooter.own_model_ids()[0],
            weapon_profile=profile,
            target_unit_id=target_id,
        )
        assert visible.is_legal
        witness = visible.line_of_sight_witness
        assert witness is not None
        if screen == "unrelated":
            unrelated = next(unit for unit in owner.units if unit.datasheet_id == "000001465")
            assert any(
                record.blocker_id in unrelated.own_model_ids() and record.blocks_full_visibility
                for record in witness.all_blocker_records()
            )
        elif precision:
            visible_leader = next(u for u in opponent.units if u.datasheet_id == "000001120")
            visible_leader_ids = visible_leader.own_model_ids()
            hidden_leader = next(u for u in opponent.units if u.datasheet_id == "000001148")
            hidden_leader_ids = hidden_leader.own_model_ids()
            assert set(visible_leader.own_model_ids()) <= set(visible.target_visible_model_ids)
            assert set(hidden_leader.own_model_ids()).isdisjoint(visible.target_visible_model_ids)
            screened = {
                row.target_model_id
                for row in witness.model_records
                if any(
                    blocker.blocker_id in source.own_model_ids() and blocker.blocks_full_visibility
                    for blocker in row.blocker_records
                )
            }
            assert {*target.own_model_ids(), *visible_leader.own_model_ids()} <= screened
            assert set(hidden_leader.own_model_ids()).isdisjoint(screened)
        else:
            candidates = set(
                allocation_context_for_unit(
                    state=state, target_unit_instance_id=target_id
                ).candidate_model_ids()
            )
            screened = {
                record.target_model_id
                for record in witness.model_records
                if any(
                    blocker.blocker_id in source.own_model_ids() and blocker.blocks_full_visibility
                    for blocker in record.blocker_records
                )
            }
            assert candidates == set(target.own_model_ids())
            if screen == "mixed":
                assert screened < candidates
                assert screened
                assert (candidates - screened) - set(visible.target_in_range_model_ids)
            else:
                assert screened == candidates

    # Start a real shooting phase with the mustered native units.
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = owner.player_id
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    session = LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _shooting_phase_handler=handler,
            _battle_round_flow=BattleRoundFlow(
                phase_handlers={
                    BattlePhase.COMMAND: CommandPhaseHandler(
                        ruleset_descriptor=config.ruleset_descriptor,
                        army_catalog=config.army_catalog,
                    ),
                    BattlePhase.MOVEMENT: MovementPhaseHandler(
                        ruleset_descriptor=config.ruleset_descriptor,
                        army_catalog=config.army_catalog,
                    ),
                    BattlePhase.SHOOTING: handler,
                    BattlePhase.CHARGE: ChargePhaseHandler(
                        ruleset_descriptor=config.ruleset_descriptor
                    ),
                    BattlePhase.FIGHT: FightPhaseHandler(
                        ruleset_descriptor=config.ruleset_descriptor,
                        army_catalog=config.army_catalog,
                    ),
                },
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            ),
        )
    )
    anchor(Scene(session, state, {}))
    handler.begin_phase(state=state, decisions=session.lifecycle.decision_controller)
    if pending(session).decision_type == "start_mission_action":
        choose_shooting(session, pending(session), "continue_to_shooting")
    request = declaration_request(session, shooter, "normal")
    rows = weapon_rows(request)
    lash = next(row for row in rows if row["wargear_id"] == lash_id)
    used_rows = [lash]
    if first_pool:
        used_rows.insert(0, next(row for row in rows if row["wargear_id"] == prior_weapon_id))
    replay_start = (
        session.lifecycle.to_payload()
        if (screen == "singleton" and not ignores_cover and not ordinary_cover)
        or (screen == "mixed" and attacks == 1)
        else None
    )
    if replay_start is not None:
        session = LocalGameSession(GameLifecycle.from_payload(replay_start))
        replay_start = session.lifecycle.to_payload()
    assert_valid(submit(session, used_rows, [target_id] * len(used_rows), "normal"))
    if first_pool:
        group_request = pending(session)
        assert group_request.decision_type == "select_attack_weapon_group"
        prior_option = next(
            option
            for option in group_request.options
            if isinstance(option.payload, dict)
            and any(
                row["wargear_id"] == prior_weapon_id
                for row in cast(GatheredAttackGroupPayload, option.payload["gathered_group"])[
                    "contributions"
                ]
            )
        )
        choose_shooting(session, group_request, prior_option.option_id)
    if precision:
        for _ in range(20):
            request = pending(session)
            if request.decision_type == "select_precision_allocation":
                (lead,) = (
                    option for option in request.options if option.option_id != "decline_precision"
                )
                assert isinstance(lead.payload, dict)
                assert lead.payload["selected_model_ids"] == list(visible_leader_ids)
                choose_shooting(session, request, lead.option_id)
                break
            assert not events(session, "attack_sequence_completed"), (
                "Precision pool produced no eligible Wound."
            )
            choose_shooting(session, request, request.options[0].option_id)
        else:
            raise AssertionError("Native attack did not reach the Precision lead choice.")
    finish_attacks(session)
    if precision:
        final_allocation = next(
            row["payload"]
            for row in events(session, "attack_sequence_step")
            if row["step"] == "allocate"
            and isinstance(row["payload"], dict)
            and row["payload"].get("forced") is True
        )
        assert isinstance(final_allocation, dict)
        final_groups = cast(list[AllocationGroupPayload], final_allocation["allocation_groups"])
        assert final_groups[0]["model_ids"] == list(visible_leader_ids)
        assert any(group["model_ids"] == list(hidden_leader_ids) for group in final_groups[1:])
    if replay_start is not None:
        artifact = ReplayArtifact.capture(
            artifact_id="gnarlmaw-native-pre-hit",
            initial_lifecycle_payload=replay_start,
            final_lifecycle=session.lifecycle,
        )
        replay = ReplayRunner.from_payload(artifact.to_payload()).run()
        assert replay.reproduced_exactly, replay.to_payload()
    return session, source, target


def _assert_gnarlmaw_natural_two(session: LocalGameSession, *, target_number: int) -> None:
    from warhammer40k_core.engine.attack_sequence_model import HitRollPayload

    steps = events(session, "attack_sequence_step")
    rolled_twos = [
        step
        for step in steps
        if step["step"] == "hit" and cast(HitRollPayload, step["payload"])["unmodified_roll"] == 2
    ]
    assert rolled_twos
    for step in rolled_twos:
        hit = cast(HitRollPayload, step["payload"])
        assert not any(
            next_step["step"] in ("wound", "save")
            and next_step["attack_context_id"] == step["attack_context_id"]
            for next_step in steps
        )
        assert hit["target_number"] == target_number
        assert hit["capped_modifier"] == 0
        assert hit["successful"] is (target_number == 2)
        roll = hit["roll_state"]
        assert roll is not None
        assert roll["original_result"]["spec"]["roll_type"] == "attack_sequence.hit"
        assert roll["original_result"]["source"] == "rng"
        assert roll["original_result"]["values"] == [2]


def test_gnarlmaw_records_allocation_cover_after_unmodified_hit_roll(tmp_path: Path) -> None:
    from warhammer40k_core.engine.saves import SaveOptionPayload

    session, source, target = _gnarlmaw_native_attack(tmp_path, screen="singleton")
    _assert_gnarlmaw_natural_two(session, target_number=3)
    save = next(
        step["payload"]
        for step in events(session, "attack_sequence_step")
        if step["step"] == "save"
    )
    assert isinstance(save, dict)
    assert save["allocated_model_id"] == target.own_model_ids()[0]
    (armour,) = (
        option
        for option in cast(list[SaveOptionPayload], save["save_options"])
        if option["save_kind"] == "armour"
    )
    assert armour["target_number"] == 7
    assert armour["cover_applied"] is False
    cover = armour["cover_result"]
    assert cover is not None
    assert cover["source_feature_ids"] == list(source.own_model_ids())
    assert cover["cover_effect"] == "attacker_bs_modifier"


@pytest.mark.parametrize(
    ("attack_count", "first_model_wounds", "target_number"),
    [
        pytest.param(1, 1, 3, id="one-attack-forced-wounded"),
        pytest.param(2, 1, 2, id="second-attack-can-reach-next-model"),
        pytest.param(2, 3, 3, id="last-attack-can-only-exhaust-wounded"),
        pytest.param(3, 3, 2, id="attack-remains-after-exhaustion"),
    ],
)
def test_gnarlmaw_pre_hit_cover_reaches_only_allocation_within_pool(
    tmp_path: Path, attack_count: int, first_model_wounds: int, target_number: int
) -> None:
    from warhammer40k_core.engine.attack_sequence_model import HitRollPayload

    session, _, _ = _gnarlmaw_native_attack(
        tmp_path,
        screen="mixed",
        attacks=attack_count,
        wounded_front=first_model_wounds,
        seed="gnarlmaw-dice-12" if attack_count == 1 else "gnarlmaw-dice-1",
    )
    hits = [
        cast(HitRollPayload, step["payload"])
        for step in events(session, "attack_sequence_step")
        if step["step"] == "hit"
    ]
    assert len(hits) == attack_count
    assert {hit["target_number"] for hit in hits} == {target_number}
    if attack_count == 1:
        _assert_gnarlmaw_natural_two(session, target_number=3)


def test_gnarlmaw_pre_hit_cover_respects_live_allocation_from_earlier_pool(tmp_path: Path) -> None:
    from warhammer40k_core.engine.attack_sequence_model import HitRollPayload

    session, _, target = _gnarlmaw_native_attack(
        tmp_path,
        screen="mixed",
        attacks=1,
        wounded_front=3,
        first_pool=True,
        seed="gnarlmaw-dice-4",
    )
    steps = events(session, "attack_sequence_step")
    last_hit = next(step for step in reversed(steps) if step["step"] == "hit")
    assert cast(HitRollPayload, last_hit["payload"])["target_number"] == 3
    (prior_save,) = (
        step["payload"] for step in steps[: steps.index(last_hit)] if step["step"] == "save"
    )
    assert isinstance(prior_save, dict)
    assert prior_save["allocated_model_id"] == target.own_model_ids()[0]
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert target.own_model_ids()[0] in state.shooting_phase_state.allocated_model_ids_this_phase


@pytest.mark.parametrize(
    ("attack_count", "target_number"),
    [pytest.param(4, 3, id="through-bodyguards"), pytest.param(5, 2, id="nonselectable-leader")],
)
def test_gnarlmaw_pre_hit_cover_reaches_precision_follow_on_character(
    tmp_path: Path, attack_count: int, target_number: int
) -> None:
    from warhammer40k_core.engine.attack_sequence_model import HitRollPayload

    session, _, _ = _gnarlmaw_native_attack(
        tmp_path,
        screen="precision",
        attacks=attack_count,
        seed="gnarlmaw-dice-3" if attack_count == 4 else "gnarlmaw-dice-1",
    )
    hits = [
        cast(HitRollPayload, step["payload"])
        for step in events(session, "attack_sequence_step")
        if step["step"] == "hit"
    ]
    assert len(hits) == attack_count
    assert {hit["target_number"] for hit in hits} == {target_number}


@pytest.mark.parametrize(
    ("screen", "ignores_cover", "ordinary_cover", "target_number"),
    [
        pytest.param("clear", False, False, 2, id="clear"),
        pytest.param("unrelated", False, False, 2, id="unrelated-blocker"),
        pytest.param("mixed", False, False, 2, id="mixed-allocation-candidates"),
        pytest.param("all", False, False, 3, id="all-allocation-candidates"),
        pytest.param("singleton", True, False, 2, id="ignores-cover"),
        pytest.param("singleton", False, True, 3, id="ordinary-cover-does-not-stack"),
        pytest.param("clear", False, True, 3, id="ordinary-cover-alone"),
    ],
)
def test_gnarlmaw_pre_hit_cover_respects_allocation_and_modifiers(
    tmp_path: Path, screen: str, ignores_cover: bool, ordinary_cover: bool, target_number: int
) -> None:
    from warhammer40k_core.engine.attack_sequence_model import HitRollPayload

    session, _, _ = _gnarlmaw_native_attack(
        tmp_path, screen=screen, ignores_cover=ignores_cover, ordinary_cover=ordinary_cover
    )
    hits = [
        cast(HitRollPayload, step["payload"])
        for step in events(session, "attack_sequence_step")
        if step["step"] == "hit"
    ]
    assert hits
    assert {hit["target_number"] for hit in hits} == {target_number}
