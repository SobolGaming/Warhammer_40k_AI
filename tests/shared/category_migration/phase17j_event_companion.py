from __future__ import annotations

import hashlib
import importlib
import json
import math
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from itertools import pairwise, permutations
from pathlib import Path
from typing import Any, cast

import msgspec
import pytest

from warhammer40k_core.core.deployment_zones import (
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
)
from warhammer40k_core.core.missions import (
    BattlefieldLayoutDefinition,
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    ObjectiveMarkerDefinitionPayload,
    ObjectiveMarkerRole,
    objective_marker_role_from_token,
)
from warhammer40k_core.core.ruleset_descriptor import LineOfSightPolicy, RulesetDescriptor
from warhammer40k_core.core.terrain_areas import (
    TerrainAreaClassification,
    TerrainAreaLocalTransform,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayPoint
from warhammer40k_core.core.visibility import (
    BenefitOfCoverResult,
    CoverSourceReason,
    TerrainAreaCoverSourceRecord,
    TerrainVisibilityContext,
    VisibilityBlockerKind,
)
from warhammer40k_core.engine import mission_action_policies
from warhammer40k_core.engine.final_scoring import FinalScoringResult
from warhammer40k_core.engine.mission_setup import MissionSetup, MissionSetupError
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    validate_mission_setup_source_layout,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    ScoringWindowKind,
    ScoringWindowState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    model_within_solid_terrain,
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry import shapely_backend, terrain_area_visibility
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.polygons import polygon_overlap_area
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.visibility_footprints import visibility_polygon_within_union
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_base_size_rows,
    event_companion_patches,
    july_rules_updates_2026_07,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_primary_scoring_2026_06 as event_primary_scoring,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layout_geometry_2026_06 import (  # noqa: E501 - canonical source module path
    event_no_mans_land_shape,
    event_territory_vertices,
    terrain_area_classifications_by_suffix,
    terrain_feature_placements_from_specs,
)


def _meatgrinder_artifact_layouts() -> tuple[Any, ...]:
    layouts = tuple(
        layout
        for layout in event_layouts.battlefield_artifact().layouts
        if layout.source_page in {24, 25, 26}
    )
    assert tuple(layout.source_page for layout in layouts) == (24, 25, 26)
    return layouts


def _source_deployment_zone_layout_template_id(
    *,
    layout_id: str,
    layout_number: int,
) -> event_source.DeploymentZoneLayoutTemplateId:
    function = cast(
        Callable[..., event_source.DeploymentZoneLayoutTemplateId],
        vars(event_source)["_deployment_zone_layout_template_id"],
    )
    return function(layout_id=layout_id, layout_number=layout_number)


def _source_deployment_zone_layout_edges(
    template_id: event_source.DeploymentZoneLayoutTemplateId,
) -> tuple[str, str]:
    function = cast(
        Callable[[event_source.DeploymentZoneLayoutTemplateId], tuple[str, str]],
        vars(event_source)["_deployment_zone_layout_edges"],
    )
    return function(template_id)


def _source_deployment_zone_layout_template_id_from_number(
    template_number: int,
) -> event_source.DeploymentZoneLayoutTemplateId:
    template_ids_by_number: dict[int, event_source.DeploymentZoneLayoutTemplateId] = {
        1: event_source.DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED,
        2: event_source.DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP,
        3: event_source.DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT,
        4: event_source.DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE,
        5: event_source.DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP,
        6: event_source.DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE,
    }
    return template_ids_by_number[template_number]


def _source_deployment_zone_template_base_shape(
    template_id: event_source.DeploymentZoneLayoutTemplateId,
) -> DeploymentZoneShape:
    function = cast(
        Callable[[event_source.DeploymentZoneLayoutTemplateId], DeploymentZoneShape],
        vars(event_source)["_deployment_zone_template_base_shape"],
    )
    return function(template_id)


def _source_layout_number_from_layout_id(layout_id: str) -> int:
    function = cast(
        Callable[[str], int],
        vars(event_source)["_layout_number_from_layout_id"],
    )
    return function(layout_id)


def _source_rectangle_with_quarter_circle_cutout_vertices(
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    corner: str,
    radius: float,
) -> tuple[tuple[float, float], ...]:
    function = cast(
        Callable[..., tuple[tuple[float, float], ...]],
        vars(event_source)["_rectangle_with_quarter_circle_cutout_vertices"],
    )
    return function(
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        corner=corner,
        radius=radius,
    )


def _source_base_source_kind_and_geometry(
    base_text: str,
) -> tuple[str, event_source.GeometryResolutionStatus, object | None]:
    function = cast(
        Callable[..., tuple[str, event_source.GeometryResolutionStatus, object | None]],
        vars(event_source)["_base_source_kind_and_geometry"],
    )
    return function(base_text)


def _source_matrix_row(
    *,
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
) -> object:
    function = cast(
        Callable[..., object],
        vars(event_source)["_matrix_row"],
    )
    return function(
        player_force_disposition_id=player_force_disposition_id,
        opponent_force_disposition_id=opponent_force_disposition_id,
    )


def _layout_descriptor(
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
    layout_variant: str,
) -> event_source.WarhammerEventLayoutDescriptor:
    for descriptor in event_source.layout_descriptor_rows():
        if (
            descriptor.player_force_disposition_id == player_force_disposition_id
            and descriptor.opponent_force_disposition_id == opponent_force_disposition_id
            and descriptor.layout_variant == layout_variant
        ):
            return descriptor
    raise AssertionError("Layout descriptor was not found.")


def _shape_polygons(shape: DeploymentZoneShape) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple((point.x, point.y) for point in polygon.vertices) for polygon in shape.polygons
    )


def _terrain_display_points(
    points: tuple[TerrainDisplayPoint, ...],
) -> tuple[tuple[float, float], ...]:
    return tuple((point.x_inches, point.y_inches) for point in points)


def _event_final_scoring_windows(
    *,
    game_id: str,
    battle_round: int,
    policy_source_id: str,
) -> tuple[ScoringWindowState, ...]:
    return (
        ScoringWindowState(
            window_id=(
                f"scoring-window:{game_id}:round-{battle_round:02d}:end_of_round:battle_round_end"
            ),
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_ROUND,
            window="battle_round_end",
            source_id=f"{policy_source_id}:window:end_of_round:battle_round_end",
        ),
        ScoringWindowState(
            window_id=(
                f"scoring-window:{game_id}:round-{battle_round:02d}:"
                "end_of_game:turn_end_round_five_going_second"
            ),
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="turn_end_round_five_going_second",
            source_id=(f"{policy_source_id}:window:end_of_game:turn_end_round_five_going_second"),
        ),
        ScoringWindowState(
            window_id=(
                f"scoring-window:{game_id}:round-{battle_round:02d}:end_of_game:end_of_battle"
            ),
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="end_of_battle",
            source_id=f"{policy_source_id}:window:end_of_game:end_of_battle",
        ),
    )


__all__: list[str] = []
__all__ += ["Any", "BattlefieldLayoutDefinition", "BenefitOfCoverResult", "Callable"]
__all__ += ["CircularBase", "Counter", "CoverSourceReason", "DeploymentZonePoint"]
__all__ += ["DeploymentZonePolygon", "DeploymentZoneShape", "FinalScoringResult"]
__all__ += ["GameLifecycleError", "LineOfSightPolicy", "MissionPackDefinition"]
__all__ += ["MissionPackDefinitionPayload", "MissionPackError", "MissionSetup"]
__all__ += ["MissionSetupError", "MissionSourcePackageDefinition", "MissionSourceStatus", "Model"]
__all__ += ["ModelVolume", "ObjectiveMarkerDefinitionPayload", "ObjectiveMarkerRole", "Path"]
__all__ += ["Pose", "RulesetDescriptor", "ScoringWindowKind", "ScoringWindowState"]
__all__ += ["TerrainAreaClassification", "TerrainAreaCoverSourceRecord"]
__all__ += ["TerrainAreaLocalTransform", "TerrainDisplayPoint", "TerrainVisibilityContext"]
__all__ += ["VictoryPointAward", "VictoryPointLedger", "VictoryPointSourceKind"]
__all__ += ["VisibilityBlockerKind", "_event_final_scoring_windows", "_layout_descriptor"]
__all__ += ["_meatgrinder_artifact_layouts", "_shape_polygons"]
__all__ += ["_source_base_source_kind_and_geometry", "_source_deployment_zone_layout_edges"]
__all__ += ["_source_deployment_zone_layout_template_id"]
__all__ += ["_source_deployment_zone_layout_template_id_from_number"]
__all__ += ["_source_deployment_zone_template_base_shape", "_source_layout_number_from_layout_id"]
__all__ += ["_source_matrix_row", "_source_rectangle_with_quarter_circle_cutout_vertices"]
__all__ += ["_terrain_display_points", "cast", "deterministic_tactical_secondary_draw"]
__all__ += ["event_companion_base_size_rows", "event_companion_patches", "event_layouts"]
__all__ += ["event_no_mans_land_shape", "event_primary_scoring", "event_source"]
__all__ += ["event_territory_vertices", "hashlib", "importlib", "json"]
__all__ += ["july_rules_updates_2026_07", "math", "mission_action_policies"]
__all__ += ["mission_pack_for_id", "mission_scoring_policies_from_setup"]
__all__ += ["model_within_solid_terrain", "msgspec", "objective_marker_role_from_token"]
__all__ += ["pairwise", "permutations", "polygon_overlap_area", "pytest", "replace"]
__all__ += ["shapely_backend", "subprocess", "sys", "terrain_area_classifications_by_suffix"]
__all__ += ["terrain_area_visibility", "terrain_feature_placements_from_specs"]
__all__ += ["terrain_visibility_areas_from_placements", "validate_mission_setup_source_layout"]
__all__ += ["visibility_polygon_within_union", "warhammer_event_companion_2026_07_mission_pack"]
