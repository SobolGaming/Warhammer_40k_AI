"""Authenticate Fight feasibility permissions from historical movement ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.charge_endpoint_history import charge_component_at_physical_boundary
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import EventRecord, JsonValue
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        PhysicalModelAuthority,
    )
    from warhammer40k_core.engine.unit_factory import UnitInstance
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery


def validate_fight_contact_permissions(
    *,
    state: GameState,
    unit: UnitInstance,
    physical: tuple[PhysicalModelAuthority, ...],
    query: MovementReachabilityQuery,
    mode: MovementMode,
) -> None:
    if mode not in {MovementMode.PILE_IN, MovementMode.CONSOLIDATE}:
        raise GameLifecycleError("Fight contact movement mode drifted.")
    unit = charge_component_at_physical_boundary(unit=unit, physical=physical)
    legality = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.PILE_IN
        if mode is MovementMode.PILE_IN
        else ModelDisplacementKind.CONSOLIDATE,
    )
    context = query.path_context
    present = {
        p.model_instance_id for p in physical if p.presence in {"battlefield", "retained_destroyed"}
    }
    aircraft = tuple(
        sorted(
            m.model_instance_id
            for army in state.army_definitions
            for unit in army.units
            if "AIRCRAFT" in unit.keywords
            for m in unit.own_models
            if m.model_instance_id in present
            and m.model_instance_id != context.moving_model.model_id
        )
    )
    expected_path = legality.to_path_validation_context(
        moving_model=context.moving_model,
        witness=context.witness,
        battlefield_width_inches=context.battlefield_width_inches,
        battlefield_depth_inches=context.battlefield_depth_inches,
        friendly_models=context.friendly_models,
        enemy_models=context.enemy_models,
        terrain=(),
        aircraft_model_ids=aircraft,
        movement_distance_budget_inches=context.movement_distance_budget_inches,
    )
    expected_terrain = legality.to_terrain_path_legality_context(
        moving_model=context.moving_model,
        witness=context.witness,
        terrain=query.terrain_context.terrain,
        terrain_features=query.terrain_context.terrain_features,
    )
    if context != expected_path or query.terrain_context != expected_terrain:
        raise GameLifecycleError("Deemed contact Fight movement capabilities drifted.")


def validate_triggered_contact_permissions(
    *,
    state: GameState,
    unit: UnitInstance,
    physical: tuple[PhysicalModelAuthority, ...],
    query: MovementReachabilityQuery,
    payload: dict[str, JsonValue],
    events: tuple[EventRecord, ...],
) -> bool:
    """Rebuild source-aware reactive permissions, including the Surge override."""
    from dataclasses import replace
    from typing import cast

    from warhammer40k_core.engine.aircraft import AircraftMovementPolicy
    from warhammer40k_core.engine.battlefield_state import model_displacement_kind_from_token
    from warhammer40k_core.engine.fight_model_authority_history import (
        historical_rules_unit_model_ids,
    )
    from warhammer40k_core.engine.move_ability_choices import (
        chosen_move_keywords,
        movement_ability_keywords,
    )
    from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView
    from warhammer40k_core.engine.take_to_the_skies import flight_selection
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementKind,
        triggered_movement_kind_from_token,
    )

    is_surge = (
        triggered_movement_kind_from_token(payload["triggered_movement_kind"])
        is TriggeredMovementKind.SURGE
    )
    units = {
        u.unit_instance_id: charge_component_at_physical_boundary(unit=u, physical=physical)
        for army in state.army_definitions
        for u in army.units
    }
    identities = {
        m.model_instance_id: (army.player_id, units[u.unit_instance_id])
        for army in state.army_definitions
        for u in army.units
        for m in u.own_models
    }
    source_ids = historical_rules_unit_model_ids(
        state=state, event_records=events, unit_instance_id=cast(str, payload["unit_instance_id"])
    )
    component_ids = {identities[mid][1].unit_instance_id for mid in source_ids}
    unit = units[unit.unit_instance_id]
    context = query.path_context
    owner = identities[context.moving_model.model_id][0]
    ruleset = state.runtime_ruleset_descriptor()
    keywords = tuple(
        sorted(
            {
                *AircraftMovementPolicy.from_unit(
                    unit=unit, ruleset_descriptor=ruleset
                ).effective_keywords,
                *chosen_move_keywords(payload),
                *(
                    kw
                    for uid in sorted(component_ids)
                    for kw in movement_ability_keywords(
                        RulesUnitView(
                            unit_instance_id=uid,
                            owner_player_id=owner,
                            components=(RulesUnitComponent(units[uid], "unit"),),
                        )
                    )
                ),
            }
        )
    )
    legality = MovementLegalityContext.from_keywords(
        keywords=keywords,
        ruleset_descriptor=ruleset,
        movement_mode=MovementMode(cast(str, payload["movement_mode"])),
        take_to_the_skies=flight_selection(payload),
        unit=unit,
        model_instance_id=context.moving_model.model_id,
        movement_phase_action=None,
        displacement_kind=model_displacement_kind_from_token(payload["displacement_kind"]),
    )
    if is_surge:
        legality = replace(
            legality,
            engagement_policy=replace(
                legality.engagement_policy,
                may_transit_enemy_engagement=True,
                may_end_in_enemy_engagement=True,
            ),
        )
    present = {
        p.model_instance_id for p in physical if p.presence in {"battlefield", "retained_destroyed"}
    }
    retained = {p.model_instance_id for p in physical if p.presence == "retained_destroyed"}

    def matching(friendly: bool, keywords: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                mid
                for mid in present
                if mid != context.moving_model.model_id
                and (identities[mid][0] == owner) == friendly
                and set(keywords) & set(identities[mid][1].keywords)
            )
        )

    def blockers(friendly: bool, keywords: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *matching(friendly, keywords),
                    *(mid for mid in retained if (identities[mid][0] == owner) == friendly),
                }
            )
        )

    expected = legality.to_path_validation_context(
        moving_model=context.moving_model,
        witness=context.witness,
        battlefield_width_inches=context.battlefield_width_inches,
        battlefield_depth_inches=context.battlefield_depth_inches,
        friendly_models=context.friendly_models,
        enemy_models=context.enemy_models,
        terrain=(),
        friendly_vehicle_monster_model_ids=matching(True, ("VEHICLE", "MONSTER")),
        enemy_vehicle_monster_model_ids=matching(False, ("VEHICLE", "MONSTER")),
        friendly_model_transit_blocker_ids=blockers(
            True, legality.capabilities.friendly_model_transit_blocker_keywords
        ),
        enemy_model_transit_blocker_ids=blockers(
            False, legality.capabilities.enemy_model_transit_blocker_keywords
        ),
        aircraft_model_ids=tuple(
            sorted(
                mid
                for mid in (*matching(True, ("AIRCRAFT",)), *matching(False, ("AIRCRAFT",)))
                if mid not in retained
            )
        ),
        movement_distance_budget_inches=context.movement_distance_budget_inches,
    )
    terrain = legality.to_terrain_path_legality_context(
        moving_model=context.moving_model,
        witness=context.witness,
        terrain=query.terrain_context.terrain,
        terrain_features=query.terrain_context.terrain_features,
    )
    if expected != context or terrain != query.terrain_context:
        raise GameLifecycleError("Deemed contact reactive movement capabilities drifted.")
    return is_surge
