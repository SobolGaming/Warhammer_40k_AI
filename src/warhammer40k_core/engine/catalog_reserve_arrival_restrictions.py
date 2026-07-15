from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.catalog_reserve_arrival_restriction_classification import (
    CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,
    clause_is_reserve_arrival_restriction,
    reserve_arrival_restriction_distance_inches,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalRestriction,
    ReserveArrivalRestrictionContext,
    ReserveArrivalRestrictionHookBinding,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance


@dataclass(frozen=True, slots=True)
class CatalogReserveArrivalRestrictionRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_indexes(self.ability_indexes_by_player_id)
        if type(self.armies) is not tuple:
            raise GameLifecycleError("Catalog reserve restrictions require army tuple.")
        for army in self.armies:
            if type(army) is not ArmyDefinition:
                raise GameLifecycleError("Catalog reserve restriction army is invalid.")
            if army.player_id not in indexes:
                raise GameLifecycleError("Catalog reserve restriction ability index is missing.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(indexes))
        object.__setattr__(
            self,
            "armies",
            tuple(sorted(self.armies, key=lambda army: army.player_id)),
        )

    def bindings(self) -> tuple[ReserveArrivalRestrictionHookBinding, ...]:
        if not _has_reserve_arrival_restriction_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            ReserveArrivalRestrictionHookBinding(
                hook_id=CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,
                source_id=CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,
                handler=self.restrictions_for,
            ),
        )

    def restrictions_for(
        self,
        context: ReserveArrivalRestrictionContext,
    ) -> tuple[ReserveArrivalRestriction, ...]:
        if type(context) is not ReserveArrivalRestrictionContext:
            raise GameLifecycleError("Catalog reserve restrictions require context.")
        restrictions: list[ReserveArrivalRestriction] = []
        for army in self.armies:
            if army.player_id == context.reserve_state.player_id:
                continue
            index = self.ability_indexes_by_player_id[army.player_id]
            for unit in sorted(army.units, key=lambda value: value.unit_instance_id):
                current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                    state=context.state,
                    unit=unit,
                )
                if not current_model_ids:
                    continue
                for record in index.all_records():
                    if not _record_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                    ):
                        continue
                    restrictions.extend(
                        _restrictions_for_record(
                            context=context,
                            unit=unit,
                            current_model_instance_ids=current_model_ids,
                            record=record,
                        )
                    )
        return tuple(restrictions)


def _has_reserve_arrival_restriction_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        any(
            clause_is_reserve_arrival_restriction(clause)
            for clause in catalog_rule_clauses_from_record(record)
        )
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
    )


def _validate_ability_indexes(value: object) -> dict[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog reserve restrictions require ability indexes.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or not player_id.strip():
            raise GameLifecycleError("Catalog reserve restriction player_id is invalid.")
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog reserve restriction ability index is invalid.")
        indexes[player_id] = index
    return indexes


def _record_matches_unit(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> bool:
    return (
        record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        and catalog_rule_record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        )
    )


def _restrictions_for_record(
    *,
    context: ReserveArrivalRestrictionContext,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
) -> tuple[ReserveArrivalRestriction, ...]:
    source_models = {model.model_instance_id: model for model in unit.own_models}
    arriving_models = {
        model.model_instance_id: model for model in context.rules_unit.alive_models()
    }
    restrictions: list[ReserveArrivalRestriction] = []
    battlefield_state = context.state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Catalog reserve restrictions require battlefield state.")
    for clause in catalog_rule_clauses_from_record(record):
        if not clause_is_reserve_arrival_restriction(clause):
            continue
        distance = reserve_arrival_restriction_distance_inches(clause)
        for source_model_id in current_model_instance_ids:
            source_model = _required_model(source_models, source_model_id)
            source_geometry = geometry_model_for_placement(
                model=source_model,
                placement=battlefield_state.model_placement_by_id(source_model_id),
            )
            for arriving_placement in context.attempted_rules_unit_placement.model_placements:
                arriving_model = _required_model(
                    arriving_models,
                    arriving_placement.model_instance_id,
                )
                arriving_geometry = geometry_model_for_placement(
                    model=arriving_model,
                    placement=arriving_placement,
                )
                if arriving_geometry.range_to(source_geometry) > distance:
                    continue
                restrictions.append(
                    ReserveArrivalRestriction(
                        hook_id=CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,
                        source_id=CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID,
                        catalog_record_id=record.record_id,
                        clause_id=clause.clause_id,
                        arriving_model_instance_id=arriving_model.model_instance_id,
                        source_model_instance_id=source_model.model_instance_id,
                        minimum_distance_inches=distance,
                        replay_payload={
                            "ability_id": record.definition.ability_id,
                            "catalog_record_id": record.record_id,
                            "catalog_source_rule_id": record.definition.source_id,
                            "clause_id": clause.clause_id,
                            "source_unit_instance_id": unit.unit_instance_id,
                        },
                    )
                )
    return tuple(restrictions)


def _required_model(
    models_by_id: Mapping[str, ModelInstance],
    model_instance_id: str,
) -> ModelInstance:
    model = models_by_id.get(model_instance_id)
    if model is None:
        raise GameLifecycleError("Catalog reserve restriction model evidence drifted.")
    return model
