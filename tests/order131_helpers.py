"""Explicit configured catalog exercises one retained consumer, without roster certification."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import secondary_choice
from tests.phase13b_shooting_declaration_helpers import _display_geometry
from tests.phase15a_charge_config_helpers import _config, _unit_selection
from tests.psychic_modifier_helpers import pending_request
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

MOVER = "army-beta:mover"


def objective_session(
    *, objective_x: float = 25.0, objective_y: float = 20.0, wall: bool = False
) -> LocalGameSession:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = replace(
        base.datasheet_by_id("core-intercessor-like-infantry"),
        name="Ironkin Steeljacks",
        keywords=DatasheetKeywordSet(
            keywords=("INFANTRY",), faction_keywords=("LEAGUES OF VOTANN",)
        ),
    )
    catalog = replace(
        base,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in base.datasheets
        ),
        factions=(
            *base.factions,
            FactionDefinition(
                faction_id="leagues-of-votann",
                name="Configured Votann acceptance",
                faction_keywords=("LEAGUES OF VOTANN",),
                source_ids=("order131:configured-catalog",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="hearthfyre-arsenal",
                canonical_detachment_id="hearthfyre-arsenal",
                name="Hearthfyre Arsenal",
                faction_id="leagues-of-votann",
                detachment_point_cost=1,
                unit_datasheet_ids=tuple(row.datasheet_id for row in base.datasheets),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("order131:configured-catalog",),
            ),
        ),
    )
    config = _config(
        game_id="order131-objective", alpha_unit_ids=("mover",), enemy_unit_ids=("mover",)
    )
    mission = config.mission_setup
    assert mission is not None
    features: tuple[TerrainFeatureDefinition, ...] = ()
    if wall:
        display = _display_geometry(
            center_x_inches=15, center_y_inches=23, width_inches=1, depth_inches=40
        )
        features = (
            TerrainFeatureDefinition(
                feature_id="order131-wall",
                feature_kind=TerrainFeatureKind.HILLS,
                footprint_center_x_inches=15,
                footprint_center_y_inches=23,
                footprint_width_inches=1,
                footprint_depth_inches=40,
                rules_footprint_polygon=display.footprint_polygon,
                display_geometry=display,
                walls=(TerrainWallDefinition("wall", 15, 23, 0, 1, 40, 10),),
                source_id="order131:configured-geometry",
            ),
        )
    config = replace(
        config,
        army_catalog=catalog,
        mission_setup=replace(
            mission,
            terrain_features=features,
            objective_markers=tuple(
                replace(row, x_inches=objective_x, y_inches=objective_y)
                for row in mission.objective_markers
            ),
        ),
        army_muster_requests=tuple(
            ArmyMusterRequest(
                army_id=army,
                player_id=player,
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="leagues-of-votann", detachment_ids=("hearthfyre-arsenal",)
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(_unit_selection("mover", catalog=catalog),),
            )
            for army, player in (("army-alpha", "player-a"), ("army-beta", "player-b"))
        ),
    )
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=catalog, request=request))
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order131-configured-field",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=100,
        battlefield_depth_inches=100,
        terrain_features=features,
    )
    battlefield = scenario.battlefield_state
    for army, y in (("army-alpha", 70), ("army-beta", 20)):
        placement = battlefield.unit_placement_by_id(f"{army}:mover")
        battlefield = battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(row, pose=Pose.at(10, y + index * 1.5))
                    for index, row in enumerate(placement.model_placements)
                ),
            )
        )
    state.record_battlefield_state(battlefield)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player, mode=SecondaryMissionMode.FIXED)
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.gain_command_points(
        player_id="player-b",
        amount=1,
        source_id="order131:fixture-command-phase",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
        cap_exempt=True,
    )
    decisions = DecisionController()
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    return LocalGameSession(
        GameLifecycle.from_payload(
            cast(
                GameLifecyclePayload,
                {
                    "config": config.to_payload(),
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": {"frames": []},
                    "parameterized_movement_proposals": True,
                },
            )
        )
    )


def request_objective_move(session: LocalGameSession) -> None:
    """Reach the native end-of-opponent-Movement window through finite facade commands."""
    for index in range(16):
        request = pending_request(session)
        if request.decision_type == "select_triggered_movement":
            return
        choice = next(
            (option for option in request.options if "COGITATED" in option.label.upper()), None
        )
        if choice is None:
            choice = next(
                (
                    option
                    for option in request.options
                    if option.option_id == "finish_movement_phase"
                ),
                None,
            )
        if choice is None:
            choice = next(
                (option for option in request.options if "decline" in option.option_id), None
            )
        if choice is None and request.decision_type == "select_movement_unit":
            choice = request.options[0]
        if choice is None and request.decision_type == "select_movement_action":
            choice = next(
                (option for option in request.options if option.option_id == "remain_stationary"),
                None,
            )
        assert choice is not None, request
        session.submit_option(
            request_id=request.request_id,
            result_id=f"order131-select-{index}",
            option_id=choice.option_id,
        )
    raise AssertionError("Objective move was not offered.")
