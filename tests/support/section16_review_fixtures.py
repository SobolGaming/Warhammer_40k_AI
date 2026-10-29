"""Source-valid native held-card and mission-boundary checkpoints for review repairs."""

from collections.abc import Iterator
from dataclasses import replace
from functools import cache

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_session
from tests.support.section16_fixtures import LORD, checkpoint

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.mission_decisions import request_mission_action_start
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.triggered_movement import TriggeredMovementHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@cache
def native_mission(vital_link: bool = False) -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-priority-assets-layout-1"
        if vital_link
        else "mission-disruption-vs-reconnaissance-layout-2",
        terrain_layout_id="purge-the-foe-vs-priority-assets-layout-1"
        if vital_link
        else "disruption-vs-reconnaissance-layout-2",
        attacker_player_id="opponent" if vital_link else "owner",
        defender_player_id="owner" if vital_link else "opponent",
        attacker_force_disposition_id="purge-the-foe" if vital_link else "disruption",
        defender_force_disposition_id="priority-assets" if vital_link else "reconnaissance",
    )


@pytest.fixture(scope="session", autouse=True)
def section16_review_resources() -> Iterator[None]:
    missions = tuple(native_mission(v) for v in (False, True))
    before = tuple(m.to_payload() for m in missions)
    yield
    assert tuple(m.to_payload() for m in missions) == before


def native_scene(
    d: Section02Definitions,
    *,
    active: str = "owner",
    permission: bool = False,
    vital_link: bool = False,
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    state, original = checkpoint(d, permission=permission)
    mission = native_mission(vital_link)
    state.mission_setup = mission
    state.active_player_id = active
    state.army_definitions[:] = sorted(
        [
            replace(
                a,
                force_disposition_id=mission.primary_mission_assignment_for_player(
                    a.player_id
                ).force_disposition_id,
            )
            for a in state.army_definitions
        ],
        key=lambda a: a.army_id,
    )
    unit = next(a for a in state.army_definitions if a.player_id == active).units[0]
    if permission and active != "owner":
        unit = replace(unit, datasheet_abilities=original.datasheet_abilities)
        state.army_definitions[:] = [
            replace(a, units=(unit,)) if a.player_id == active else a
            for a in state.army_definitions
        ]
    assert state.battlefield_state is not None
    central = next(m for m in mission.objective_markers if m.objective_role.value == "central")
    board = replace(
        state.battlefield_state,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
        terrain_features=mission.terrain_features,
    )
    for army in state.army_definitions:
        placed = board.unit_placement_by_id(army.units[0].unit_instance_id)
        pose = (
            Pose.at(central.x_inches, central.y_inches, central.z_inches)
            if army.player_id == active
            else Pose.at(5, 5)
        )
        board = board.with_unit_placement(
            replace(placed, model_placements=(replace(placed.model_placements[0], pose=pose),))
        )
    state.replace_battlefield_state(board)
    state.secondary_mission_choices[:] = [
        SecondaryMissionChoice(p, SecondaryMissionMode.TACTICAL, ()) for p in state.player_ids
    ]
    state.secondary_mission_card_states[:] = [
        SecondaryMissionCardState.active_tactical(
            player_id=active,
            secondary_mission_id="cleanse",
            battle_round=1,
            source_result_id="constructed:s16:held-card",
        ).with_selection(SecondaryMissionSelection())
    ]
    state.starting_strength_records.sort(key=lambda r: r.unit_instance_id)
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    session = boundary_session(d, state)
    session.lifecycle._triggered_movement_handler = TriggeredMovementHandler(  # pyright: ignore[reportPrivateUsage]
        ruleset_descriptor=state.runtime_ruleset_descriptor()
    )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return session, state, unit


def offer_native(
    session: LocalGameSession, state: GameState, action: str = "cleanse-objective"
) -> DecisionRequest:
    status = request_mission_action_start(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id=state.active_player_id or "",
        mission_action_id=action,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.decision_request is not None, status
    return status.decision_request


def start_native(
    session: LocalGameSession,
    state: GameState,
    unit: UnitInstance,
    action: str = "cleanse-objective",
) -> str:
    req = offer_native(session, state, action)
    selected = next(o for o in req.options if f":{unit.unit_instance_id}:" in o.option_id)
    status = session.submit_option(
        request_id=req.request_id, option_id=selected.option_id, result_id="s16:r2:start"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    return next(
        a.action_id
        for a in state.mission_action_states
        if a.unit_instance_id == unit.unit_instance_id
    )


def finish_mission_boundary(
    session: LocalGameSession, state: GameState, *, pause_before_score: bool = False
) -> None:
    from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
    from warhammer40k_core.engine.fight_order import FightPhaseState
    from warhammer40k_core.engine.fights_first import FightsFirstRegistry

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    # Explicit checkpoint assumes only the unrelated Fight body has finished.
    # The lifecycle performs phase-end hooks, completion, timing-window events,
    # retained turn-end control, Action completion and scoring itself.
    if state.fight_phase_state is None:
        assert state.active_player_id is not None
        state.replace_fight_phase_state(
            FightPhaseState.start(
                battle_round=state.battle_round,
                active_player_id=state.active_player_id,
                policy=state.runtime_ruleset_descriptor().fight_policy,
                engaged_at_fight_step_start_unit_ids=(),
                fights_first_registry=FightsFirstRegistry(),
            ).with_current_step(
                current_step=FightPhaseStepKind.END,
                policy=state.runtime_ruleset_descriptor().fight_policy,
            )
        )
    boundary_player = state.active_player_id
    for _ in range(15):
        if (
            state.active_player_id != boundary_player
            or state.current_battle_phase is not BattlePhase.FIGHT
        ):
            return
        req = session.lifecycle.pending_decision_request()
        if req is None:
            status = session.lifecycle.advance_until_decision_or_terminal()
            if (
                state.active_player_id != boundary_player
                or state.current_battle_phase is not BattlePhase.FIGHT
            ):
                return
            req = status.decision_request
            assert req is not None, status
        assert req.decision_type in {
            "resolve_sequencing_order",
            "score_tactical_secondary_mission",
        }, req
        if pause_before_score and req.decision_type == "score_tactical_secondary_mission":
            return
        selected = next(
            (o for o in req.options if o.option_id.startswith("next:secondary-action:")), None
        )
        if selected is None:
            selected = next(
                (o for o in req.options if o.option_id.startswith("next:secondary-scoring:")), None
            )
        if selected is None:
            selected = next(
                (o for o in req.options if o.option_id == "score:cleanse"), req.options[0]
            )
        result = session.submit_option(
            request_id=req.request_id,
            option_id=selected.option_id,
            result_id=f"s16:r2:boundary:{len(session.lifecycle.decision_controller.records)}",
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    raise AssertionError("Mission boundary did not finish within its finite choices")


def add_native_control(
    d: Section02Definitions,
    state: GameState,
    *,
    sheet: str = LORD,
    identity: str = "second",
    same_target: bool = True,
) -> UnitInstance:
    army = next(a for a in state.army_definitions if a.player_id == state.active_player_id)
    unit = d.unit(sheet, identity=identity, army_id=army.army_id)
    assert state.mission_setup is not None
    central = next(
        m for m in state.mission_setup.objective_markers if m.objective_role.value == "central"
    )
    marker = (
        central
        if same_target
        else next(
            m
            for m in state.mission_setup.objective_markers
            if m.objective_marker_id != central.objective_marker_id
            and m.objective_role.value not in {"home", "attacker_home", "defender_home"}
        )
    )
    state.army_definitions[:] = [
        replace(a, units=(*a.units, unit)) if a.army_id == army.army_id else a
        for a in state.army_definitions
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id=army.player_id, unit=unit)
    )
    state.starting_strength_records.sort(key=lambda s: s.unit_instance_id)
    assert state.battlefield_state is not None
    new_placement = UnitPlacement(
        army.army_id,
        army.player_id,
        unit.unit_instance_id,
        tuple(
            ModelPlacement(
                army.army_id,
                army.player_id,
                unit.unit_instance_id,
                m.model_instance_id,
                Pose.at(marker.x_inches + 2, marker.y_inches + 2.1 * i, marker.z_inches),
            )
            for i, m in enumerate(unit.own_models)
        ),
    )
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(a, unit_placements=(*a.unit_placements, new_placement))
                if a.army_id == army.army_id
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    return unit
