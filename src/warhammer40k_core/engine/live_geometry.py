from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import (
    MissionDeploymentZoneSource,
    RulesetDescriptor,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES = 60.0
DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES = 44.0


@dataclass(frozen=True, slots=True)
class LiveBattlefieldGeometry:
    battlefield_width_inches: float
    battlefield_depth_inches: float
    terrain_features: tuple[TerrainFeatureDefinition, ...]


def live_battlefield_geometry_for_state(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    context: str,
) -> LiveBattlefieldGeometry:
    from warhammer40k_core.engine.game_state import GameState as RuntimeGameState

    if type(state) is not RuntimeGameState:
        raise GameLifecycleError("Live battlefield geometry requires a GameState.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Live battlefield geometry requires a RulesetDescriptor.")
    if type(context) is not str or not context.strip():
        raise GameLifecycleError("Live battlefield geometry context must be a non-empty string.")
    mission_setup = state.mission_setup
    if mission_setup is not None:
        return LiveBattlefieldGeometry(
            battlefield_width_inches=mission_setup.battlefield_width_inches,
            battlefield_depth_inches=mission_setup.battlefield_depth_inches,
            terrain_features=mission_setup.terrain_features,
        )
    if (
        ruleset_descriptor.mission_policy.deployment_zone_source
        is MissionDeploymentZoneSource.MISSION
    ):
        raise GameLifecycleError(f"{context.strip()} requires MissionSetup battlefield geometry.")
    return LiveBattlefieldGeometry(
        battlefield_width_inches=DETERMINISTIC_BRIDGE_BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=DETERMINISTIC_BRIDGE_BATTLEFIELD_DEPTH_INCHES,
        terrain_features=(),
    )
