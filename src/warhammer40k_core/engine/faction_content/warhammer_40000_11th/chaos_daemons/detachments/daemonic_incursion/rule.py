from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    CHAOS_DAEMONS_FACTION_ID as _CHAOS_DAEMONS_FACTION_ID,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    GREATER_DAEMON_SHADOW_AURA_KEYWORDS_BY_SOURCE_ID,
    ShadowRegion,
    shadow_regions_for_player,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.army_rule import (
    LEGIONES_DAEMONICA as _LEGIONES_DAEMONICA,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceGrant,
)
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as daemonic_incursion_ir,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:rule:warp_rifts"
WARP_RIFTS_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:daemonic-incursion:rule"
DENIZENS_OF_THE_WARP_SOURCE_RULE_ID = daemonic_incursion_ir.DENIZENS_OF_THE_WARP_SOURCE_RULE_ID
CHAOS_DAEMONS_FACTION_ID = _CHAOS_DAEMONS_FACTION_ID
LEGIONES_DAEMONICA = _LEGIONES_DAEMONICA
DAEMONIC_INCURSION_DETACHMENT_ID = "daemonic-incursion"
WARP_RIFTS_ENEMY_DISTANCE_INCHES = 6.0
WARP_RIFTS_ANCHOR_RANGE_INCHES = 6.0
DENIZENS_OF_THE_WARP_ENEMY_DISTANCE_INCHES = (
    daemonic_incursion_ir.DENIZENS_OF_THE_WARP_ENEMY_DISTANCE_INCHES
)
GOD_KEYWORDS = ("KHORNE", "TZEENTCH", "NURGLE", "SLAANESH")


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
    )


def warp_rifts_distance_grants(
    context: ReserveArrivalDistanceContext,
    *,
    source: GenericRuleAbilitySource | None = None,
) -> tuple[ReserveArrivalDistanceGrant, ...]:
    if type(context) is not ReserveArrivalDistanceContext:
        raise GameLifecycleError("Warp Rifts requires a reserve arrival distance context.")
    if source is not None:
        _validate_generic_rule_source(source)
    if context.placement_kind is not BattlefieldPlacementKind.DEEP_STRIKE:
        return ()
    if (
        context.attempted_rules_unit_placement.rules_unit_instance_id
        != context.reserve_state.unit_instance_id
    ):
        return ()
    if context.attempted_rules_unit_placement.player_id != context.reserve_state.player_id:
        return ()
    army = _army_for_player(context.state, player_id=context.reserve_state.player_id)
    if not _army_has_daemonic_incursion_detachment(army):
        return ()
    if not _rules_unit_has_faction_keyword(context.rules_unit, LEGIONES_DAEMONICA):
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
            replay_payload=_warp_rifts_replay_payload(
                context=context,
                source=source,
                within_shadow=within_shadow,
                within_anchor=within_anchor,
            ),
        ),
    )


def denizens_of_the_warp_distance_grants(
    context: ReserveArrivalDistanceContext,
    *,
    source: GenericRuleAbilitySource,
) -> tuple[ReserveArrivalDistanceGrant, ...]:
    if type(context) is not ReserveArrivalDistanceContext:
        raise GameLifecycleError("Denizens of the Warp requires a reserve arrival context.")
    _validate_generic_rule_source(source)
    if context.placement_kind is not BattlefieldPlacementKind.DEEP_STRIKE:
        return ()
    if (
        context.attempted_rules_unit_placement.rules_unit_instance_id
        != context.reserve_state.unit_instance_id
    ):
        return ()
    if context.attempted_rules_unit_placement.player_id != context.reserve_state.player_id:
        return ()
    if not _rules_unit_has_faction_keyword(context.rules_unit, LEGIONES_DAEMONICA):
        return ()

    from warhammer40k_core.engine.generic_rule_ability_effects import (
        generic_rule_ability_effects_for_unit,
        generic_rule_ability_source_context_payload,
    )

    matching_effects = generic_rule_ability_effects_for_unit(
        state=context.state,
        source=source,
        unit_instance_id=context.reserve_state.unit_instance_id,
        ability=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,
    )
    if not matching_effects:
        return ()
    return (
        ReserveArrivalDistanceGrant(
            hook_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_HOOK_ID,
            source_id=DENIZENS_OF_THE_WARP_SOURCE_RULE_ID,
            enemy_horizontal_distance_inches=DENIZENS_OF_THE_WARP_ENEMY_DISTANCE_INCHES,
            replay_payload=generic_rule_ability_source_context_payload(
                source=source,
                matching_effects=matching_effects,
                source_rule_id=DENIZENS_OF_THE_WARP_SOURCE_RULE_ID,
                extra_context={
                    "effect_kind": "denizens_of_the_warp",
                    "player_id": context.reserve_state.player_id,
                    "unit_instance_id": context.reserve_state.unit_instance_id,
                    "placement_kind": context.placement_kind.value,
                    "base_enemy_horizontal_distance_inches": (
                        context.base_enemy_horizontal_distance_inches
                    ),
                    "enemy_horizontal_distance_inches": DENIZENS_OF_THE_WARP_ENEMY_DISTANCE_INCHES,
                    "required_faction_keyword": LEGIONES_DAEMONICA,
                },
            ),
        ),
    )


def _warp_rifts_replay_payload(
    *,
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource | None,
    within_shadow: bool,
    within_anchor: bool,
) -> JsonValue:
    payload: dict[str, object] = {
        "effect_kind": "warp_rifts",
        "source_rule_id": SOURCE_RULE_ID,
        "detachment_id": DAEMONIC_INCURSION_DETACHMENT_ID,
        "player_id": context.reserve_state.player_id,
        "unit_instance_id": context.reserve_state.unit_instance_id,
        "placement_kind": context.placement_kind.value,
        "base_enemy_horizontal_distance_inches": context.base_enemy_horizontal_distance_inches,
        "enemy_horizontal_distance_inches": WARP_RIFTS_ENEMY_DISTANCE_INCHES,
        "shadow_of_chaos": within_shadow,
        "greater_daemon_anchor": within_anchor,
        "required_faction_keyword": LEGIONES_DAEMONICA,
        "shared_god_keywords": list(_god_keywords_for_rules_unit(context.rules_unit)),
    }
    if source is not None:
        payload.update(
            {
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_source_id": source.rule_ir.source_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
            }
        )
    return validate_json_value(payload)


def _validate_generic_rule_source(source: object) -> None:
    from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource

    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError(
            "Daemonic Incursion generic RuleIR source requires ability source."
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
    target_god_keywords = _god_keywords_for_rules_unit(context.rules_unit)
    if not target_god_keywords:
        return False
    target_models = _attempted_geometry_models(context)
    if not target_models:
        return False
    anchor_models: list[GeometryModel] = []
    for source_unit in army.units:
        if source_unit.unit_instance_id in context.rules_unit.component_unit_instance_ids:
            continue
        anchor_god_keywords = _greater_daemon_anchor_keywords(source_unit)
        if not (target_god_keywords & anchor_god_keywords):
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
    return tuple(
        model
        for component_placement in (
            context.attempted_rules_unit_placement.component_unit_placements
        )
        for model in _geometry_models_for_placement(
            context.scenario,
            component_placement,
        )
    )


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


def _greater_daemon_anchor_keywords(unit: UnitInstance) -> frozenset[str]:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Warp Rifts Greater Daemon anchor lookup requires UnitInstance.")
    keywords: set[str] = set()
    for ability in unit.datasheet_abilities:
        for source_id, keyword in GREATER_DAEMON_SHADOW_AURA_KEYWORDS_BY_SOURCE_ID:
            if ability.source_id == source_id:
                keywords.add(keyword)
    return frozenset(keywords)


def _god_keywords_for_unit(unit: UnitInstance) -> frozenset[str]:
    return frozenset(
        god_keyword for god_keyword in GOD_KEYWORDS if _unit_has_keyword(unit, god_keyword)
    )


def _god_keywords_for_rules_unit(view: RulesUnitView) -> frozenset[str]:
    if type(view) is not RulesUnitView:
        raise GameLifecycleError("Warp Rifts god-keyword lookup requires RulesUnitView.")
    return frozenset(
        keyword
        for component in view.components
        for keyword in _god_keywords_for_unit(component.unit)
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


def _rules_unit_has_faction_keyword(view: RulesUnitView, keyword: str) -> bool:
    if type(view) is not RulesUnitView:
        raise GameLifecycleError("Warp Rifts faction-keyword lookup requires RulesUnitView.")
    return all(_unit_has_faction_keyword(component.unit, keyword) for component in view.components)


_validate_identifier = IdentifierValidator(GameLifecycleError)
