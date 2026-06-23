from __future__ import annotations

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    CHAOS_DAEMONS_FACTION_ID as _CHAOS_DAEMONS_FACTION_ID,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    GREATER_DAEMON_NAMES as _GREATER_DAEMON_NAMES,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    LEGIONES_DAEMONICA as _LEGIONES_DAEMONICA,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    ShadowRegion,
    shadow_regions_for_player,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceGrant,
    ReserveArrivalDistanceHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:rule:scaffold"
WARP_RIFTS_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:daemonic-incursion:rule"
CHAOS_DAEMONS_FACTION_ID = _CHAOS_DAEMONS_FACTION_ID
LEGIONES_DAEMONICA = _LEGIONES_DAEMONICA
GREATER_DAEMON_NAMES = _GREATER_DAEMON_NAMES
DAEMONIC_INCURSION_DETACHMENT_ID = "daemonic-incursion"
WARP_RIFTS_ENEMY_DISTANCE_INCHES = 6.0
WARP_RIFTS_ANCHOR_RANGE_INCHES = 6.0
GOD_KEYWORDS = ("KHORNE", "TZEENTCH", "NURGLE", "SLAANESH")


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        reserve_arrival_distance_hook_bindings=(
            ReserveArrivalDistanceHookBinding(
                hook_id=WARP_RIFTS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=warp_rifts_distance_grants,
            ),
        ),
    )


def warp_rifts_distance_grants(
    context: ReserveArrivalDistanceContext,
) -> tuple[ReserveArrivalDistanceGrant, ...]:
    if type(context) is not ReserveArrivalDistanceContext:
        raise GameLifecycleError("Warp Rifts requires a reserve arrival distance context.")
    if context.placement_kind is not BattlefieldPlacementKind.DEEP_STRIKE:
        return ()
    if context.attempted_placement.unit_instance_id != context.reserve_state.unit_instance_id:
        return ()
    if context.attempted_placement.player_id != context.reserve_state.player_id:
        return ()
    army = _army_for_player(context.state, player_id=context.reserve_state.player_id)
    if not _army_has_daemonic_incursion_detachment(army):
        return ()
    if not _unit_has_faction_keyword(context.unit, LEGIONES_DAEMONICA):
        return ()

    within_shadow = _attempted_unit_wholly_within_shadow(context=context)
    within_anchor = _attempted_unit_wholly_within_matching_greater_daemon_anchor(
        context=context,
        army=army,
    )
    if not within_shadow and not within_anchor:
        return ()

    return (
        ReserveArrivalDistanceGrant(
            hook_id=WARP_RIFTS_HOOK_ID,
            source_id=SOURCE_RULE_ID,
            enemy_horizontal_distance_inches=WARP_RIFTS_ENEMY_DISTANCE_INCHES,
            replay_payload={
                "effect_kind": "warp_rifts",
                "detachment_id": DAEMONIC_INCURSION_DETACHMENT_ID,
                "player_id": context.reserve_state.player_id,
                "unit_instance_id": context.reserve_state.unit_instance_id,
                "placement_kind": context.placement_kind.value,
                "base_enemy_horizontal_distance_inches": (
                    context.base_enemy_horizontal_distance_inches
                ),
                "enemy_horizontal_distance_inches": WARP_RIFTS_ENEMY_DISTANCE_INCHES,
                "shadow_of_chaos": within_shadow,
                "greater_daemon_anchor": within_anchor,
                "required_faction_keyword": LEGIONES_DAEMONICA,
                "shared_god_keywords": list(_god_keywords_for_unit(context.unit)),
            },
        ),
    )


def _attempted_unit_wholly_within_shadow(
    *,
    context: ReserveArrivalDistanceContext,
) -> bool:
    state = context.state
    if state.mission_setup is None:
        raise GameLifecycleError("Warp Rifts Shadow check requires MissionSetup.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Warp Rifts Shadow check requires battlefield_state.")
    models = _attempted_geometry_models(context)
    if not models:
        return False
    regions = shadow_regions_for_player(
        state=state,
        player_id=context.reserve_state.player_id,
    )
    shadow_surface = None
    if ShadowRegion.OWN_DEPLOYMENT_ZONE in regions:
        for zone in state.mission_setup.deployment_zones:
            if zone.player_id == context.reserve_state.player_id:
                zone_surface = shapely_backend.footprint_for_deployment_zone(zone)
                shadow_surface = (
                    zone_surface if shadow_surface is None else shadow_surface.union(zone_surface)
                )
    if ShadowRegion.OPPONENT_DEPLOYMENT_ZONE in regions:
        for zone in state.mission_setup.deployment_zones:
            if zone.player_id != context.reserve_state.player_id:
                zone_surface = shapely_backend.footprint_for_deployment_zone(zone)
                shadow_surface = (
                    zone_surface if shadow_surface is None else shadow_surface.union(zone_surface)
                )
    if ShadowRegion.NO_MANS_LAND in regions:
        no_mans_land_surface = shapely_backend.footprint_for_no_mans_land(
            battlefield_bounds=(
                0.0,
                0.0,
                state.battlefield_state.battlefield_width_inches,
                state.battlefield_state.battlefield_depth_inches,
            ),
            deployment_zones=state.mission_setup.deployment_zones,
        )
        shadow_surface = (
            no_mans_land_surface
            if shadow_surface is None
            else shadow_surface.union(no_mans_land_surface)
        )
    if shadow_surface is None:
        return False
    return all(
        shadow_surface.covers(shapely_backend.footprint_for_base(model.base, model.pose))
        for model in models
    )


def _attempted_unit_wholly_within_matching_greater_daemon_anchor(
    *,
    context: ReserveArrivalDistanceContext,
    army: ArmyDefinition,
) -> bool:
    target_god_keywords = _god_keywords_for_unit(context.unit)
    if not target_god_keywords:
        return False
    target_models = _attempted_geometry_models(context)
    if not target_models:
        return False
    anchor_models: list[GeometryModel] = []
    for source_unit in army.units:
        if source_unit.unit_instance_id == context.unit.unit_instance_id:
            continue
        if not _unit_is_named_greater_daemon(source_unit):
            continue
        if not (target_god_keywords & _god_keywords_for_unit(source_unit)):
            continue
        source_placement = _placed_unit_for_army(
            scenario=context.scenario,
            player_id=army.player_id,
            unit_instance_id=source_unit.unit_instance_id,
        )
        if source_placement is None:
            continue
        anchor_models.extend(_geometry_models_for_placement(context.scenario, source_placement))
    if not anchor_models:
        return False
    return all(
        any(
            shapely_backend.base_footprint_distance(
                target_model.base,
                target_model.pose,
                anchor_model.base,
                anchor_model.pose,
            )
            <= WARP_RIFTS_ANCHOR_RANGE_INCHES
            for anchor_model in anchor_models
        )
        for target_model in target_models
    )


def _attempted_geometry_models(
    context: ReserveArrivalDistanceContext,
) -> tuple[GeometryModel, ...]:
    return _geometry_models_for_placement(context.scenario, context.attempted_placement)


def _geometry_models_for_placement(
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[GeometryModel, ...]:
    models: list[GeometryModel] = []
    for model_placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(model_placement)
        if not model.is_alive:
            continue
        models.append(
            geometry_model_for_placement(
                model=model,
                placement=model_placement,
            )
        )
    return tuple(models)


def _placed_unit_for_army(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    unit_instance_id: str,
) -> UnitPlacement | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for placement in placed_army.unit_placements:
            if placement.unit_instance_id == requested_unit_id:
                return placement
    return None


def _army_for_player(state: object, *, player_id: str) -> ArmyDefinition:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Warp Rifts requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Warp Rifts could not find the player's army.")


def _army_has_daemonic_incursion_detachment(army: ArmyDefinition) -> bool:
    return (
        army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and DAEMONIC_INCURSION_DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _unit_is_named_greater_daemon(unit: UnitInstance) -> bool:
    return _canonical_keyword(unit.name) in GREATER_DAEMON_NAMES


def _god_keywords_for_unit(unit: UnitInstance) -> frozenset[str]:
    return frozenset(
        god_keyword for god_keyword in GOD_KEYWORDS if _unit_has_keyword(unit, god_keyword)
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Warp Rifts {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Warp Rifts {field_name} must not be empty.")
    return stripped
