"""17.01 physical blocker ownership; mixed keywords are explicit Core contracts."""

# pyright: reportPrivateUsage=false

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import (
    add_unit,
    attach_mission,
    choose,
    events,
    propose,
    select,
)
from tests.support.section17_fixtures import LORD, PRINCE, SPAWN
from tests.unit_keyword_helpers import with_model_keywords
from warhammer40k_core.engine import (
    charge_move_geometry,
    scout_movement_paths,
)
from warhammer40k_core.engine import (
    triggered_movement_resolution as triggered_movement,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases import movement_geometry
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.pose import Pose


def blocker_scene(
    d: Section02Definitions,
    *,
    friendly: bool,
    keyword: str | None,
    tagged_index: int = 0,
    presence: str = "alive",
    offpath_y: float = 15,
) -> tuple[GameState, UnitInstance, UnitInstance, BattlefieldScenario]:
    mover = d.unit(PRINCE)
    blocker = d.unit(SPAWN, identity="blocker", army_id="section02" if friendly else "enemy")
    if keyword is not None:
        blocker = replace(
            blocker,
            own_models=tuple(
                with_model_keywords(m, keywords=(*m.keywords, keyword)) if i == tagged_index else m
                for i, m in enumerate(blocker.own_models)
            ),
        )
    if presence != "alive":
        blocker = replace(
            blocker,
            own_models=tuple(
                replace(m, wounds_remaining=0) if i == tagged_index else m
                for i, m in enumerate(blocker.own_models)
            ),
        )
    positions = (Pose.at(14, offpath_y), Pose.at(14, 11.5))
    if friendly:
        state = native_state(
            d,
            mover,
            (Pose.at(10, 10),),
            enemy=d.unit(LORD, identity="far", army_id="enemy"),
            enemy_poses=(Pose.at(40, 35),),
        )
        add_unit(state, blocker, positions)
    else:
        state = native_state(d, mover, (Pose.at(10, 10),), enemy=blocker, enemy_poses=positions)
    board = scenario(state)
    if presence == "retained":
        # Explicit existing presence authority, not a native Fight-on-Death workflow.
        board = replace(
            board, present_destroyed_model_ids=(blocker.own_models[tagged_index].model_instance_id,)
        )
    return state, mover, blocker, board


@pytest.mark.parametrize("friendly", [False, True])
@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("keyword", [None, "MONSTER", "VEHICLE"])
def test_off_path_sibling_keyword_cannot_forbid_ordinary_model_transit(
    section17_definitions: Section02Definitions,
    friendly: bool,
    action: str,
    keyword: str | None,
) -> None:
    d = section17_definitions
    state, mover, blocker, _ = blocker_scene(d, friendly=friendly, keyword=keyword)
    assert "MONSTER" not in blocker.own_models[1].keywords
    assert "VEHICLE" not in blocker.own_models[1].keywords
    # The tagged sibling clears the actual 2-inch enemy engagement envelope.
    from tests.support.section03_fixtures import geometry

    moving = geometry(mover, (Pose.at(14, 10),))[0]
    offpath = geometry(blocker, (Pose.at(14, 15), Pose.at(14, 11.5)), enemy=not friendly)[0]
    assert (
        moving.range_to(offpath)
        > state.runtime_ruleset_descriptor().engagement_policy.horizontal_inches
    )
    assert not unit_within_enemy_engagement_range(
        state=state, unit_instance_id=mover.unit_instance_id
    )
    attach_mission(state)
    add_unit(state, d.unit(SPAWN, identity="spare"), (Pose.at(8, 32), Pose.at(10, 32)))
    session = movement_session(d, state)
    request = choose(session, select(session, mover), action)
    end = Pose.at(18, 10)
    result = propose(session, request, mover, (end,))
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    assert state.battlefield_state is not None
    assert (
        state.battlefield_state.unit_placement_by_id(mover.unit_instance_id)
        .model_placements[0]
        .pose
        == end
    )
    assert len(events(session, "movement_activation_completed")) == 1
    assert state.movement_phase_state is not None
    assert mover.unit_instance_id in state.movement_phase_state.moved_unit_ids
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer)


@pytest.mark.parametrize("friendly", [False, True])
@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("keyword", ["MONSTER", "VEHICLE"])
def test_actual_crossed_monster_vehicle_rejects_and_allows_legal_retry(
    section17_definitions: Section02Definitions,
    friendly: bool,
    action: str,
    keyword: str,
) -> None:
    d = section17_definitions
    state, mover, blocker, _ = blocker_scene(d, friendly=friendly, keyword=keyword, tagged_index=1)
    assert keyword in blocker.own_models[1].keywords
    assert keyword not in blocker.own_models[0].keywords
    attach_mission(state)
    add_unit(state, d.unit(SPAWN, identity="spare"), (Pose.at(8, 32), Pose.at(10, 32)))
    session = movement_session(d, state)
    request = choose(session, select(session, mover), action)
    original = state.battlefield_state
    result = propose(session, request, mover, (Pose.at(18, 10),))
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert "vehicle_monster_transit_forbidden" in str(result.to_payload())
    assert state.battlefield_state == original
    assert not events(session, "movement_activation_completed")
    retry = session.lifecycle.decision_controller.queue.pending_requests[0]
    legal = propose(session, retry, mover, (Pose.at(10, 8),), result_id="s17:r003-retry")
    assert legal.status_kind is not LifecycleStatusKind.INVALID, legal
    assert len(events(session, "movement_activation_completed")) == 1


@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("keyword", ["MONSTER", "VEHICLE"])
def test_actual_enemy_monster_vehicle_engagement_envelope_still_blocks_transit(
    section17_definitions: Section02Definitions,
    action: str,
    keyword: str,
) -> None:
    d = section17_definitions
    state, mover, _, _ = blocker_scene(d, friendly=False, keyword=keyword, offpath_y=14)
    attach_mission(state)
    add_unit(state, d.unit(SPAWN, identity="spare"), (Pose.at(8, 32), Pose.at(10, 32)))
    session = movement_session(d, state)
    request = choose(session, select(session, mover), action)
    original = state.battlefield_state
    result = propose(session, request, mover, (Pose.at(18, 10),))
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert "enemy_engagement_range_transit_forbidden" in str(result.to_payload())
    assert state.battlefield_state == original
    assert not events(session, "movement_activation_completed")
    retry = session.lifecycle.decision_controller.queue.pending_requests[0]
    legal = propose(session, retry, mover, (Pose.at(10, 8),), result_id="s17:r003-engagement-retry")
    assert legal.status_kind is not LifecycleStatusKind.INVALID, legal
    assert len(events(session, "movement_activation_completed")) == 1


@pytest.mark.parametrize(
    "consumer",
    [
        "normal_friendly",
        "normal_enemy",
        "triggered_friendly",
        "triggered_enemy",
        "scout_friendly",
        "scout_enemy",
        "charge_friendly",
    ],
)
@pytest.mark.parametrize("keyword", ["MONSTER", "VEHICLE"])
@pytest.mark.parametrize("presence", ["alive", "absent", "retained"])
def test_all_collectors_use_actual_present_model_keywords(
    section17_definitions: Section02Definitions,
    consumer: str,
    keyword: str,
    presence: str,
) -> None:
    friendly = consumer.endswith("friendly")
    _, mover, blocker, board = blocker_scene(
        section17_definitions,
        friendly=friendly,
        keyword=keyword,
        presence=presence,
    )
    if friendly:
        friendly_collector = {
            "normal_friendly": movement_geometry._friendly_vehicle_monster_model_ids,
            "triggered_friendly": triggered_movement._friendly_vehicle_monster_model_ids,
            "scout_friendly": scout_movement_paths._friendly_vehicle_monster_model_ids,
            "charge_friendly": charge_move_geometry._friendly_vehicle_monster_model_ids,
        }[consumer]
        ids = friendly_collector(
            scenario=board,
            player_id="owner",
            moving_model_instance_id=mover.own_models[0].model_instance_id,
        )
    else:
        # Charge has no enemy collector. Other consumers have the same contract.
        enemy_collector = {
            "normal_enemy": movement_geometry._enemy_vehicle_monster_model_ids_for_player,
            "triggered_enemy": triggered_movement._enemy_vehicle_monster_model_ids_for_player,
            "scout_enemy": scout_movement_paths._enemy_vehicle_monster_model_ids_for_player,
        }[consumer]
        ids = enemy_collector(
            scenario=board,
            player_id="owner",
        )
    expected = () if presence == "absent" else (blocker.own_models[0].model_instance_id,)
    assert ids == expected
    assert blocker.own_models[1].model_instance_id not in ids
    assert mover.own_models[0].model_instance_id not in ids


def test_all_seven_collectors_delegate_physical_classification_to_one_owner() -> None:
    root = Path(__file__).resolve().parents[3] / "src/warhammer40k_core/engine"
    count = 0
    for relative in (
        "phases/movement_geometry.py",
        "triggered_movement_resolution.py",
        "scout_movement_paths.py",
        "charge_move_geometry.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf8"))
        for fn in tree.body:
            if isinstance(fn, ast.FunctionDef) and fn.name in (
                "_friendly_vehicle_monster_model_ids",
                "_enemy_vehicle_monster_model_ids_for_player",
            ):
                calls = [
                    n.func.id
                    for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                ]
                assert "vehicle_monster_model_ids_for_player" in calls
                assert not any(
                    isinstance(n, ast.Attribute) and n.attr == "keywords" for n in ast.walk(fn)
                )
                count += 1
    assert count == 7
