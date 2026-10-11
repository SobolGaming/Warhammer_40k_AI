"""D07 analytical Ruins and canonical MONSTER, declared before public setup."""

from dataclasses import replace

from tests.d06_embark_helpers import choose, default_choice, propose
from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.model_keyword_helpers import mixed_keyword_catalog
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)

MONSTER = "army-alpha:monster"
MIXED = "army-alpha:mixed"


def upper_floor_config(*, player: str) -> GameConfig:
    monster = unit_selection(
        unit_selection_id="monster",
        datasheet_id="core-vehicle-monster",
        model_profile_id="core-vehicle-monster",
        model_count=1,
    )
    enemy = unit_selection(
        unit_selection_id="enemy",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    config = phase11c_config(player_a_units=(monster,), player_b_units=(enemy,))
    assert config.mission_setup is not None
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10,
        center_y_inches=10,
        width_inches=14,
        depth_inches=14,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        feature_id="d07:stable-ruins",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=10,
        footprint_center_y_inches=10,
        footprint_width_inches=14,
        footprint_depth_inches=14,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="d07:west-wall",
                center_x_inches=3.06,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=0.12,
                depth_inches=14,
                height_inches=3,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="d07:upper",
                center_x_inches=10,
                center_y_inches=10,
                bottom_z_inches=3,
                width_inches=14,
                depth_inches=14,
                thickness_inches=0.12,
            ),
        ),
        source_id="d07:predeclared-analytical-terrain",
    )
    other = "player-b" if player == "player-a" else "player-a"
    mission = replace(
        config.mission_setup,
        battlefield_layout_id=None,
        deployment_map_id="d07:zones",
        terrain_layout_id="d07:terrain",
        terrain_features=(feature,),
        terrain_areas=(),
        objective_terrain_areas=(),
        battlefield_regions=(),
        deployment_zones=(
            DeploymentZone.rectangle("A", player, min_x=0, min_y=0, max_x=18, max_y=44),
            DeploymentZone.rectangle("B", other, min_x=24, min_y=0, max_x=44, max_y=44),
        ),
    )
    alpha = next(row for row in config.army_muster_requests if row.army_id == "army-alpha")
    beta = next(row for row in config.army_muster_requests if row.army_id == "army-beta")
    return replace(
        config,
        game_id=f"d07:{player}",
        army_muster_requests=(
            replace(
                alpha,
                player_id=player,
                force_disposition_id=(
                    alpha.force_disposition_id
                    if player == "player-a"
                    else beta.force_disposition_id
                ),
            ),
            replace(
                beta,
                player_id=other,
                force_disposition_id=(
                    beta.force_disposition_id
                    if player == "player-a"
                    else alpha.force_disposition_id
                ),
            ),
        ),
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=()
        ),
    )


def model_ownership_config(*, player: str, attached: bool) -> GameConfig:
    """Predeclared admitted Core fixture; no official mixed roster certification."""
    config = upper_floor_config(player=player)
    catalog = mixed_keyword_catalog()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(sheet.keywords, keywords=("INFANTRY", "VEHICLE", "BATTLELINE")),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
        model_keyword_assignments=tuple(
            replace(
                row,
                keywords=("VEHICLE", "BATTLELINE")
                if row.model_profile_id == "core-keyword-specialist"
                else ("INFANTRY", "BATTLELINE"),
            )
            for row in catalog.model_keyword_assignments
        ),
    )
    mixed = unit_selection(
        unit_selection_id="mixed",
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=2,
    )
    mixed = replace(
        mixed,
        model_profile_selections=(
            *mixed.model_profile_selections,
            ModelProfileSelection(model_profile_id="core-keyword-specialist", model_count=1),
        ),
    )
    leader = unit_selection(
        unit_selection_id="leader",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    alpha = next(row for row in config.army_muster_requests if row.army_id == "army-alpha")
    beta = next(row for row in config.army_muster_requests if row.army_id == "army-beta")
    return replace(
        config,
        game_id=f"d07:ownership:{player}:{attached}",
        army_catalog=catalog,
        army_muster_requests=(
            replace(
                alpha,
                unit_selections=(mixed, leader) if attached else (mixed,),
                attachment_declarations=(
                    AttachmentDeclaration(
                        source_unit_selection_id="leader",
                        bodyguard_unit_selection_id="mixed",
                    ),
                )
                if attached
                else (),
            ),
            beta,
        ),
    )


def reach_monster_deployment(
    *, player: str, config: GameConfig | None = None
) -> tuple[LocalGameSession, DecisionRequest]:
    session = LocalGameSession()
    session.start(upper_floor_config(player=player) if config is None else config)
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "submit_deployment_placement":
            if request.actor_id == player:
                return session, request
            propose(
                session,
                request,
                deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, _p, _m: Pose.at(28, 10),
                ),
            )
        else:
            default_choice(session, request)
    raise AssertionError("D07 native MONSTER deployment not reached")


def reach_monster_move(
    session: LocalGameSession, *, player: str, unit_id: str = MONSTER
) -> DecisionRequest:
    for _ in range(80):
        request = pending_request(session)
        if request.decision_type == "submit_movement_proposal" and request.actor_id == player:
            return request
        if request.decision_type == "submit_deployment_placement":
            propose(
                session,
                request,
                deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, _p, _m: Pose.at(28, 10),
                ),
            )
        elif request.decision_type == "select_movement_unit" and request.actor_id == player:
            choose(session, request, unit_id)
        elif request.decision_type == "select_movement_action" and request.actor_id == player:
            choose(session, request, "normal_move")
        else:
            default_choice(session, request)
    raise AssertionError("D07 native MONSTER movement not reached")


def body_terrain_history_config(*, player: str) -> GameConfig:
    """Declare the independently reproduced opposing body before native setup."""
    from tests.order85_overhang_helpers import evidence, footprint
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        DatasheetAbilityDescriptor,
    )
    from warhammer40k_core.core.model_geometry_catalog import (
        GeometryMeasurementKind,
        GeometryRulesFootprintPolicy,
        ModelGeometryCatalogRecord,
        ModelHeightDefinition,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_super_heavy_walker_2026_09 as walker,
    )

    body = evidence("body", GeometryMeasurementKind.FOOTPRINT, "diameter", 8.0)
    base = evidence("base", GeometryMeasurementKind.SUPPORT_BASE, "diameter", 120.0 / 25.4)
    height = evidence("height", GeometryMeasurementKind.HEIGHT, "height", 2.0)
    geometry = ModelGeometryCatalogRecord(
        model_geometry_id="d07:body-history",
        model_profile_id="core-vehicle-monster",
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_SUPPORT_BASE,
        footprint=footprint("body", body),
        support_base=footprint("base", base),
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height),
        evidence=(body, base, height),
        source_ids=("order85-fixture:solid-cylinder",),
    )
    ability = DatasheetAbilityDescriptor(
        ability_id=walker.movement_abilities()[0].ability_ids[0],
        name="Predeclared source-bound descriptor",
        source_id=walker.MOVEMENT_ABILITY_SOURCE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.CORE,
        effect_description="Existing native source descriptor",
    )
    config = model_ownership_config(player=player, attached=True)
    assert config.army_catalog is not None
    enemy = unit_selection(
        unit_selection_id="enemy",
        datasheet_id="core-vehicle-monster",
        model_profile_id="core-vehicle-monster",
        model_count=1,
    )
    return replace(
        config,
        game_id=f"d07:body-history:{player}",
        model_geometries=(geometry,),
        army_muster_requests=tuple(
            replace(army, unit_selections=(enemy,)) if army.army_id == "army-beta" else army
            for army in config.army_muster_requests
        ),
        army_catalog=replace(
            config.army_catalog,
            datasheets=tuple(
                replace(sheet, abilities=(*sheet.abilities, ability))
                if sheet.datasheet_id == "core-intercessor-like-infantry"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        ),
    )


def reach_body_terrain_move(*, player: str) -> tuple[LocalGameSession, DecisionRequest]:
    from tests.d06_embark_helpers import state_of
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session, request = reach_monster_deployment(
        player=player, config=body_terrain_history_config(player=player)
    )
    unit = rules_unit_view_by_id(state=state_of(session), unit_instance_id=MIXED)
    vehicle = next(model for model in unit.own_models if "VEHICLE" in model.keywords)
    propose(
        session,
        request,
        deployment_placement_payload_for_request(
            session.lifecycle,
            request=request,
            pose_factory=lambda index, _player, model_id: Pose.at(
                10 + (index % 2) * 1.8,
                10 + (index // 2) * 1.8,
                0 if model_id == vehicle.model_instance_id else 3,
            ),
        ),
    )
    for _ in range(80):
        request = pending_request(session)
        if request.decision_type == "submit_movement_proposal" and request.actor_id == player:
            return session, request
        if request.decision_type == "submit_deployment_placement":
            propose(
                session,
                request,
                deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=lambda _i, _p, _m: Pose.at(28, 10),
                ),
            )
        elif request.decision_type == "select_movement_unit" and request.actor_id == player:
            choose(session, request, unit.unit_instance_id)
        elif request.decision_type == "select_movement_action" and request.actor_id == player:
            option = next(
                option
                for option in request.options
                if option.option_id == "normal_move:move_keywords"
            )
            assert isinstance(option.payload, dict)
            choice = option.payload["move_keyword_choice"]
            assert isinstance(choice, dict)
            assert choice["model_instance_ids"] == sorted(
                model.model_instance_id for model in unit.alive_models()
            )
            choose(session, request, option.option_id)
        else:
            default_choice(session, request)
    raise AssertionError("D07 native body/terrain movement not reached")


def distant_history_terrain() -> TerrainFeatureDefinition:
    """Nonempty feature volumes away from the existing Charge/Fight fixture."""
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=70,
        center_y_inches=70,
        width_inches=10,
        depth_inches=10,
        display_template_id=None,
    )
    return TerrainFeatureDefinition(
        feature_id="d07:history-ruins",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=70,
        footprint_center_y_inches=70,
        footprint_width_inches=10,
        footprint_depth_inches=10,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="d07:history-wall",
                center_x_inches=70,
                center_y_inches=70,
                bottom_z_inches=0,
                width_inches=0.12,
                depth_inches=10,
                height_inches=3,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="d07:history-upper",
                center_x_inches=70,
                center_y_inches=70,
                bottom_z_inches=3,
                width_inches=10,
                depth_inches=10,
                thickness_inches=0.12,
            ),
        ),
        source_id="d07:predeclared-analytical-terrain",
    )


def phase_body_terrain_history_session() -> LocalGameSession:
    """Admit a D07-only analytical phase fixture; protected helpers stay byte-exact."""
    from typing import cast

    from tests.charge_distance_helpers import add_modifier
    from tests.phase15c_fight_order_helpers import fight_config, unit_placement_at
    from tests.setup_completion_helpers import (
        ensure_army_mustered_events_for_fixture,
        record_completed_command_occurrences_for_fixture,
        record_current_battlefield_placements_for_fixture,
    )
    from warhammer40k_core.engine.army_mustering import muster_army
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import (
        GameState,
        SecondaryMissionChoice,
        SecondaryMissionMode,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
    from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario

    features = (distant_history_terrain(),)
    config = fight_config(
        game_id="order85-preflight",
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy", "second"),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        enemy_unit_specs={"enemy": ("core-vehicle-monster", "core-vehicle-monster", 1)},
    )
    assert config.mission_setup is not None
    config = replace(
        config,
        model_geometries=body_terrain_history_config(player="player-a").model_geometries,
        mission_setup=replace(config.mission_setup, terrain_features=features),
    )
    config = replace(
        config,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            config.mission_setup, rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids
        ),
    )
    assert config.army_catalog is not None
    armies = tuple(
        muster_army(
            catalog=config.army_catalog, request=request, model_geometries=config.model_geometries
        )
        for request in config.army_muster_requests
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order85-battlefield",
        armies=armies,
        battlefield_width_inches=100,
        battlefield_depth_inches=100,
        terrain_features=features,
    )
    battlefield = scenario.battlefield_state
    poses = {
        "army-alpha:source": Pose.at(10, 8),
        "army-beta:enemy": Pose.at(10, 14),
        "army-beta:second": Pose.at(14, 8),
    }
    for army in armies:
        for unit in army.units:
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(
                    unit,
                    army_id=army.army_id,
                    player_id=army.player_id,
                    poses=(poses[unit.unit_instance_id],),
                )
            )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.battle_round = 1
    state.active_player_id = "player-a"
    decisions = DecisionController()
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(state, decisions=decisions, config=config)
    add_modifier(state, effect_id="order85-fixture-budget", kind="modify_dice_roll", delta=10)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    return LocalGameSession(lifecycle)
