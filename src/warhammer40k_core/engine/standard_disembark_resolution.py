"""Standard Disembark owner, including inherited ingress placement validation."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.ingress_placement_restrictions import (
    IngressPlacementRestrictions,
    inherited_disembark_violations,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    DisembarkResolution,
    DisembarkSelection,
    TransportCargoState,
    resolve_disembark_internal,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

_DEFAULT_BATTLEFIELD_WIDTH_INCHES = 60.0
_DEFAULT_BATTLEFIELD_DEPTH_INCHES = 44.0


def resolve_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    battlefield_width_inches: float = _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    ingress_restrictions: IngressPlacementRestrictions | None = None,
    enemy_deployment_zones: tuple[DeploymentZone, ...] | None = None,
    deployment_zones: tuple[DeploymentZone, ...] | None = None,
    ingress_rules_unit_placement: RulesUnitPlacement | None = None,
) -> DisembarkResolution:
    if selection.disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK:
        raise GameLifecycleError("Combat Disembark requires resolve_combat_disembark.")
    if selection.disembark_mode not in {
        DisembarkModeKind.RAPID_DISEMBARK,
        DisembarkModeKind.ASSAULT_DISEMBARK,
        DisembarkModeKind.SHOCK_DISEMBARK,
        DisembarkModeKind.TACTICAL_DISEMBARK,
    }:
        raise GameLifecycleError("resolve_disembark requires a standard Disembark mode.")
    resolution = resolve_disembark_internal(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=unit,
        transport_placement=transport_placement,
        turn_player_id=selection.player_id,
        require_started_phase_embarked=True,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
    )

    violations = inherited_disembark_violations(
        selection=selection,
        restrictions=ingress_restrictions,
        scenario=scenario,
        enemy_deployment_zones=enemy_deployment_zones,
        deployment_zones=deployment_zones,
        ingress_rules_unit_placement=ingress_rules_unit_placement,
    )
    if not violations:
        return resolution
    return replace(
        resolution,
        violations=(*resolution.violations, *violations),
        updated_cargo_state=None,
        disembarked_unit_state=None,
        transition_batch=None,
    )
