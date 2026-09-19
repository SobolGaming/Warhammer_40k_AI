"""The effective ingress placement policy, retained for Rapid Disembark."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import msgspec

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.arrival_placement_conditions import ArrivalPlacementCondition
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, BattlefieldScenario
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_reserve_transport_2026_09 as source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.reserve_arrival_hooks import (
        ReserveArrivalDistanceGrant,
        ReserveArrivalRestriction,
    )
    from warhammer40k_core.engine.reserves import StrategicReserveRule
    from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
    from warhammer40k_core.engine.transports import DisembarkSelection, TransportOperationViolation
    from warhammer40k_core.geometry.volume import Model


class IngressSourceDistance(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    catalog_record_id: str
    clause_id: str
    source_model_instance_id: str
    minimum_distance_inches: float


class IngressPlacementRestrictions(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    placement_kind: BattlefieldPlacementKind
    edge_distance_inches: float | None
    enemy_distance_inches: float
    excludes_enemy_deployment_zone: bool
    source_distances: tuple[IngressSourceDistance, ...]
    distance_grant_source_ids: tuple[str, ...]
    placement_conditions: tuple[ArrivalPlacementCondition, ...]

    def __post_init__(self) -> None:
        if type(self.placement_kind) is not BattlefieldPlacementKind:
            raise GameLifecycleError("Ingress restriction placement kind is invalid.")
        for value in (self.enemy_distance_inches, self.edge_distance_inches):
            if value is not None and (
                type(value) not in (float, int) or not math.isfinite(value) or value <= 0
            ):
                raise GameLifecycleError("Ingress restriction distance must be positive.")
        if type(self.excludes_enemy_deployment_zone) is not bool:
            raise GameLifecycleError("Ingress deployment-zone restriction must be boolean.")
        if not self.placement_conditions:
            raise GameLifecycleError("Ingress requires explicit placement conditions.")
        for row in self.source_distances:
            if (
                type(row) is not IngressSourceDistance
                or not row.source_id
                or not row.catalog_record_id
                or not row.clause_id
                or not row.source_model_instance_id
                or not math.isfinite(row.minimum_distance_inches)
                or row.minimum_distance_inches <= 0
            ):
                raise GameLifecycleError("Ingress source-distance restriction is invalid.")

    def to_payload(self) -> JsonValue:
        return validate_json_value(msgspec.to_builtins(self))

    @classmethod
    def from_payload(cls, value: object) -> IngressPlacementRestrictions:
        try:
            return msgspec.convert(value, type=cls, strict=True)
        except (msgspec.ValidationError, TypeError) as exc:
            raise GameLifecycleError("Ingress placement restriction schema drift.") from exc


def restrictions_for_arrival(
    *,
    placement_kind: BattlefieldPlacementKind,
    battle_round: int,
    strategic_rule: StrategicReserveRule | None,
    deep_strike_enemy_distance: float | None,
    source_restrictions: tuple[ReserveArrivalRestriction, ...],
    distance_grants: tuple[ReserveArrivalDistanceGrant, ...],
) -> IngressPlacementRestrictions:
    from warhammer40k_core.engine.reserves import (
        DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES,
        StrategicReserveRule,
    )

    rule = strategic_rule if strategic_rule is not None else StrategicReserveRule()
    strategic = placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES
    distances = {
        (
            row.source_id,
            row.catalog_record_id,
            row.clause_id,
            row.source_model_instance_id,
            row.minimum_distance_inches,
        )
        for row in source_restrictions
    }
    effective = (
        deep_strike_enemy_distance
        if deep_strike_enemy_distance is not None
        else DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES
    )
    used_grants = tuple(
        grant
        for grant in distance_grants
        if grant.enemy_horizontal_distance_inches == effective
        and effective < DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES
    )
    if not strategic and effective < DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES and not used_grants:
        raise GameLifecycleError("Reduced ingress distance requires its source-linked conditions.")
    return IngressPlacementRestrictions(
        placement_kind=placement_kind,
        edge_distance_inches=rule.edge_distance_inches if strategic and battle_round != 1 else None,
        enemy_distance_inches=(
            rule.enemy_horizontal_distance_inches
            if strategic
            else deep_strike_enemy_distance
            if deep_strike_enemy_distance is not None
            else DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES
        ),
        excludes_enemy_deployment_zone=strategic and battle_round == 2,
        source_distances=tuple(IngressSourceDistance(*row) for row in sorted(distances)),
        distance_grant_source_ids=tuple(sorted({grant.source_id for grant in used_grants})),
        placement_conditions=tuple(
            condition for grant in used_grants for condition in grant.placement_conditions
        )
        if used_grants
        else (ArrivalPlacementCondition.unconditional(),),
    )


def transport_ingress_restrictions(
    *,
    event_records: tuple[EventRecord, ...],
    transport_id: str,
    battle_round: int,
    turn_player_id: str,
) -> IngressPlacementRestrictions:
    matches = [
        event.payload
        for event in event_records
        if event.event_type == "reinforcement_unit_arrived"
        and isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == transport_id
        and event.payload.get("battle_round") == battle_round
        and event.payload.get("active_player_id") == turn_player_id
    ]
    if len(matches) != 1 or "ingress_placement_restrictions" not in matches[0]:
        raise GameLifecycleError("Rapid Disembark requires authenticated Transport ingress rules.")
    return IngressPlacementRestrictions.from_payload(matches[0]["ingress_placement_restrictions"])


def validate_inherited_placement(
    *,
    restrictions: IngressPlacementRestrictions,
    scenario: BattlefieldScenario,
    models: tuple[Model, ...],
    player_id: str,
    enemy_deployment_zones: tuple[DeploymentZone, ...],
    deployment_zones: tuple[DeploymentZone, ...],
) -> tuple[str, ...]:
    """Validate every model, using the same reserve edge/zone/distance predicates."""
    from warhammer40k_core.engine.reserves import (
        BattlefieldEdge,
        ReservePlacementViolation,
        append_enemy_deployment_zone_violations,
        model_wholly_within_any_edge_band,
    )

    if not source.RESERVE_TRANSPORT_POLICY.inherits_ingress_placement:
        raise GameLifecycleError("Rapid Disembark source policy drift.")
    battlefield = scenario.battlefield_state
    geometry = {model.model_id: model for model in scenario.placed_geometry_models()}
    owners = {
        model.model_instance_id: army.player_id
        for army in scenario.armies
        for unit in army.units
        for model in unit.own_models
    }
    invalid: set[str] = set()
    if not any(
        condition.allows(models=models, scenario=scenario, deployment_zones=deployment_zones)
        for condition in restrictions.placement_conditions
    ):
        invalid.update(model.model_id for model in models)
    for model in models:
        if restrictions.edge_distance_inches is not None and not model_wholly_within_any_edge_band(
            model,
            edges=tuple(BattlefieldEdge),
            distance_inches=restrictions.edge_distance_inches,
            battlefield_width_inches=battlefield.battlefield_width_inches,
            battlefield_depth_inches=battlefield.battlefield_depth_inches,
        ):
            invalid.add(model.model_id)
        for enemy_id, enemy in geometry.items():
            if (
                owners[enemy_id] != player_id
                and model.base_distance_to(enemy) <= restrictions.enemy_distance_inches
            ):
                invalid.add(model.model_id)
        for row in restrictions.source_distances:
            source_model = geometry.get(row.source_model_instance_id)
            if (
                source_model is not None
                and model.range_to(source_model) <= row.minimum_distance_inches
            ):
                invalid.add(model.model_id)
    if restrictions.excludes_enemy_deployment_zone:
        violations: list[ReservePlacementViolation] = []
        append_enemy_deployment_zone_violations(
            violations=violations,
            models=models,
            enemy_deployment_zones=enemy_deployment_zones,
        )
        invalid.update(
            row.model_instance_id for row in violations if row.model_instance_id is not None
        )
    return tuple(sorted(invalid))


def inherited_disembark_violations(
    *,
    selection: DisembarkSelection,
    restrictions: IngressPlacementRestrictions | None,
    scenario: BattlefieldScenario,
    enemy_deployment_zones: tuple[DeploymentZone, ...] | None,
    deployment_zones: tuple[DeploymentZone, ...] | None,
    ingress_rules_unit_placement: RulesUnitPlacement | None,
) -> tuple[TransportOperationViolation, ...]:
    from warhammer40k_core.engine.transports import (
        DisembarkModeKind,
        DisembarkSelection,
        TransportMovementStatus,
        TransportOperationViolation,
        TransportOperationViolationCode,
    )

    if type(selection) is not DisembarkSelection:
        raise GameLifecycleError("Ingress inheritance requires a DisembarkSelection.")
    applies = (
        selection.disembark_mode is DisembarkModeKind.RAPID_DISEMBARK
        and selection.transport_movement_status is TransportMovementStatus.INGRESS_MOVE
    )
    if not applies:
        if restrictions is not None:
            raise GameLifecycleError("Ingress inheritance supplied for an unrelated Disembark.")
        return ()
    if restrictions is None or enemy_deployment_zones is None or deployment_zones is None:
        raise GameLifecycleError("Rapid Disembark requires the Transport ingress placement policy.")
    from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement

    placement = (
        ingress_rules_unit_placement
        if ingress_rules_unit_placement is not None
        else RulesUnitPlacement.single(selection.attempted_placement)
    )
    models = placement.geometry_models(scenario)
    invalid_ids = validate_inherited_placement(
        restrictions=restrictions,
        scenario=scenario,
        models=models,
        player_id=selection.player_id,
        enemy_deployment_zones=enemy_deployment_zones,
        deployment_zones=deployment_zones,
    )
    return tuple(
        TransportOperationViolation(
            violation_code=TransportOperationViolationCode.RAPID_DISEMBARK_INGRESS_RESTRICTION,
            message="Rapid Disembark model violates the Transport ingress placement restrictions.",
            unit_instance_id=selection.unit_instance_id,
            model_instance_id=model_id,
            source_rule_id=source.RESERVE_TRANSPORT_SOURCE_ID,
        )
        for model_id in invalid_ids
        if model_id
        in {row.model_instance_id for row in selection.attempted_placement.model_placements}
    )
