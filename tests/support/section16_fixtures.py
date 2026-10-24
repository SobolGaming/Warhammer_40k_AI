"""Native Action checkpoints; constructed supplements never claim provider admission."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.action_battle_shock_helpers import action_permission_catalog
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section07_fixtures import boundary_session
from tests.support.section09_fixtures import add_unit, attach_mission, movement_mission
from tests.unit_keyword_helpers import with_unit_keywords
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.mission_decisions import request_mission_action_start
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.triggered_movement import TriggeredMovementHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

LORD = "000004078"
INFRACTORS = "000004080"
SPAWN = "000004090"
IDS = (LORD, INFRACTORS, SPAWN)


@pytest.fixture(scope="session")
def section16_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    seconds = perf_counter() - start

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    mission = movement_mission()
    mission_before = mission.to_payload()
    print(f"Section16 preparation: {seconds:.6f}s; three native definitions, one indexed build")
    yield Section02Definitions(package, seconds)
    assert digest() == before
    assert mission.to_payload() == mission_before


def checkpoint(
    definitions: Section02Definitions,
    *,
    supplement: str | None = None,
    engaged: bool = False,
    permission: bool = False,
    sheet: str = LORD,
) -> tuple[GameState, UnitInstance]:
    unit = definitions.unit(sheet)
    if supplement is not None:
        unit = with_unit_keywords(unit, keywords=tuple(sorted({*unit.keywords, supplement})))
    if permission:
        # Explicit conditional FAQ premise, carried by typed source-linked RuleIR.
        # No assertion that the native Lord or any faction grants this permission.
        augmented = action_permission_catalog(definitions.package.army_catalog)
        unit = replace(unit, datasheet_abilities=augmented.datasheet_by_id(sheet).abilities)
    enemy = definitions.unit(LORD, identity="enemy", army_id="enemy")
    state = native_state(
        definitions,
        unit,
        tuple(Pose.at(10, 10 + 1.2 * i) for i in range(len(unit.own_models))),
        enemy=enemy,
        enemy_poses=(Pose.at(12 if engaged else 30, 10),),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    return state, unit


def action(unit: UnitInstance, *, identity: str = "s16:action") -> MissionActionState:
    """Explicit zero-VP Core Action contract, not a new mission or faction action."""
    return MissionActionState.start(
        action_id=identity,
        mission_action_id="constructed:s16:core-action",
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        target_id="constructed:s16:location",
        condition_target_id=None,
        mission_id="constructed:s16:mission",
        battle_round=1,
        phase="shooting",
        start_timing="shooting_phase",
        completion_timing="turn_end",
        eligible_unit_instance_ids=(unit.unit_instance_id,),
        interruption_conditions=("unit_moved", "unit_left_battlefield", "unit_destroyed"),
        scoring_source_id="constructed:s16:zero-VP-effect",
        victory_points=0,
    )


def facade_checkpoint(
    definitions: Section02Definitions,
    *,
    permission: bool = False,
    supplement: str | None = None,
    supporting: bool = False,
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    state, unit = checkpoint(definitions, permission=permission, supplement=supplement)
    attach_mission(state)
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    # Explicit marker kernel using the retained Companion coordinates. Terrain
    # Objectives remain the primary complete-game/training mode. This one-point
    # placement cannot satisfy range with different physical points on each axis.
    marker = next(
        m
        for m in state.mission_setup.objective_markers
        if m.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placed = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            replace(
                placed,
                model_placements=(
                    replace(
                        placed.model_placements[0],
                        pose=Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
                    ),
                ),
            )
        )
    )
    if supporting:
        add_unit(
            state,
            definitions.unit(LORD, identity="support"),
            (Pose.at(marker.x_inches + 2, marker.y_inches, marker.z_inches),),
        )
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(player, SecondaryMissionMode.FIXED, ("cleanse", "assassination"))
        )
        for mid in ("cleanse", "assassination"):
            state.record_secondary_mission_card_state(
                SecondaryMissionCardState.active_fixed(player_id=player, secondary_mission_id=mid)
            )
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    state.starting_strength_records.sort(key=lambda r: r.unit_instance_id)
    session = boundary_session(definitions, state)
    # The minimal boundary fixture prepares only ordinary phase handlers. Give
    # its existing generic triggered-movement handler the required descriptor.
    session.lifecycle._triggered_movement_handler = TriggeredMovementHandler(  # pyright: ignore[reportPrivateUsage]
        ruleset_descriptor=state.runtime_ruleset_descriptor()
    )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return session, state, unit


def offer(session: LocalGameSession, state: GameState) -> DecisionRequest:
    status = request_mission_action_start(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id="owner",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.decision_request is not None, status
    return status.decision_request


def accept(session: LocalGameSession, state: GameState, unit: UnitInstance) -> MissionActionState:
    request = offer(session, state)
    selected = next(o for o in request.options if f":{unit.unit_instance_id}:" in o.option_id)
    status = session.submit_option(
        request_id=request.request_id, option_id=selected.option_id, result_id="s16:accept"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    return next(
        a for a in state.mission_action_states if a.unit_instance_id == unit.unit_instance_id
    )
