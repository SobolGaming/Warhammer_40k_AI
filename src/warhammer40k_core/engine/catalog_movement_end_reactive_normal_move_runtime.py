from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.catalog_movement_end_reactive_normal_move_support import (
    CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
    clause_is_movement_end_reactive_normal_move,
    movement_end_reactive_normal_move_descriptor,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import unit_is_currently_engaged
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
    MovementEndSurgeHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import TriggeredMovementKind
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import RuleClause


@dataclass(frozen=True, slots=True)
class _MovementEndReactiveCandidate:
    rules_unit: RulesUnitView
    source_component_unit_instance_id: str
    record: AbilityCatalogRecord
    clause: RuleClause
    trigger_distance_inches: float


@dataclass(frozen=True, slots=True)
class CatalogMovementEndReactiveNormalMoveRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_indexes(self.ability_indexes_by_player_id),
        )
        object.__setattr__(self, "armies", _validate_armies(self.armies))

    def bindings(self) -> tuple[MovementEndSurgeHookBinding, ...]:
        if not _has_supported_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
        ):
            return ()
        return (
            MovementEndSurgeHookBinding(
                hook_id=CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
                source_id=CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
                handler=self.grants,
            ),
        )

    def grants(self, context: MovementEndSurgeContext) -> tuple[MovementEndSurgeGrant, ...]:
        if type(context) is not MovementEndSurgeContext:
            raise GameLifecycleError("Catalog movement-end reaction requires hook context.")
        if context.state.current_battle_phase is not BattlePhase.MOVEMENT:
            raise GameLifecycleError("Catalog movement-end reaction requires Movement phase.")
        if context.state.battlefield_state is None:
            raise GameLifecycleError("Catalog movement-end reaction requires battlefield_state.")
        triggering_rules_unit = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=context.triggering_unit_instance_id,
        )
        if triggering_rules_unit.owner_player_id != context.triggering_player_id:
            raise GameLifecycleError("Catalog movement-end triggering unit owner drift.")
        candidates = self._candidates(
            context=context,
            triggering_rules_unit=triggering_rules_unit,
        )
        return tuple(
            MovementEndSurgeGrant(
                hook_id=CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
                source_id=CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
                unit_instance_id=candidate.rules_unit.unit_instance_id,
                descriptor_source_rule_id=candidate.record.definition.source_id,
                movement_kind=TriggeredMovementKind.TRIGGERED,
                allow_battle_shocked=True,
                one_per_phase=False,
                independent_unit_reaction=True,
                replay_payload={
                    "consumer_id": CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
                    "catalog_record_id": candidate.record.record_id,
                    "clause_id": candidate.clause.clause_id,
                    "generic_rule_effect": cast(
                        JsonValue,
                        movement_end_reactive_normal_move_descriptor(
                            candidate.clause
                        ).effect.to_payload(),
                    ),
                    "source_component_unit_instance_id": (
                        candidate.source_component_unit_instance_id
                    ),
                    "source_rules_unit_instance_id": candidate.rules_unit.unit_instance_id,
                    "triggering_unit_instance_id": context.triggering_unit_instance_id,
                    "trigger_event_id": context.trigger_event_id,
                    "movement_phase_action": context.movement_phase_action,
                    "trigger_distance_inches": candidate.trigger_distance_inches,
                },
            )
            for candidate in candidates
        )

    def _candidates(
        self,
        *,
        context: MovementEndSurgeContext,
        triggering_rules_unit: RulesUnitView,
    ) -> tuple[_MovementEndReactiveCandidate, ...]:
        index = self.ability_indexes_by_player_id.get(context.reacting_player_id)
        if index is None:
            raise GameLifecycleError("Catalog movement-end reaction is missing ability index.")
        candidates: list[_MovementEndReactiveCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for rules_unit in rules_unit_views_from_armies(armies=self.armies):
            if rules_unit.owner_player_id != context.reacting_player_id:
                continue
            if not rules_unit.alive_models():
                continue
            if unit_is_currently_engaged(
                state=context.state,
                unit_instance_id=rules_unit.unit_instance_id,
            ):
                continue
            trigger_distance = _distance_between_rules_units_or_none(
                context=context,
                source_rules_unit=rules_unit,
                triggering_rules_unit=triggering_rules_unit,
            )
            if trigger_distance is None:
                continue
            for component in rules_unit.components:
                current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                    state=context.state,
                    unit=component.unit,
                )
                if not current_model_ids:
                    continue
                for record in index.records_for(TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE):
                    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                        continue
                    if (
                        record.definition.timing.trigger_kind
                        is not TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE
                        or record.definition.timing.phase is not BattlePhaseKind.MOVEMENT
                    ):
                        continue
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=component.unit,
                        current_model_instance_ids=current_model_ids,
                    ):
                        continue
                    for clause in catalog_rule_clauses_from_record(record):
                        if not clause_is_movement_end_reactive_normal_move(clause):
                            continue
                        semantic = movement_end_reactive_normal_move_descriptor(clause)
                        if trigger_distance > semantic.trigger_distance_inches:
                            continue
                        key = (
                            rules_unit.unit_instance_id,
                            record.definition.source_id,
                            clause.clause_id,
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        candidates.append(
                            _MovementEndReactiveCandidate(
                                rules_unit=rules_unit,
                                source_component_unit_instance_id=(component.unit.unit_instance_id),
                                record=record,
                                clause=clause,
                                trigger_distance_inches=trigger_distance,
                            )
                        )
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    candidate.rules_unit.unit_instance_id,
                    candidate.record.record_id,
                    candidate.clause.clause_id,
                ),
            )
        )


def catalog_movement_end_reactive_normal_move_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[MovementEndSurgeHookBinding, ...]:
    return CatalogMovementEndReactiveNormalMoveRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _has_supported_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> bool:
    for army in armies:
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            continue
        for unit in army.units:
            current_model_ids = tuple(
                sorted(model.model_instance_id for model in unit.own_models if model.is_alive)
            )
            if not current_model_ids:
                continue
            for record in index.records_for(TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE):
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                if (
                    record.definition.timing.trigger_kind
                    is not TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE
                    or record.definition.timing.phase is not BattlePhaseKind.MOVEMENT
                ):
                    continue
                if not catalog_rule_record_source_matches_unit(
                    record=record,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                ):
                    continue
                if any(
                    clause_is_movement_end_reactive_normal_move(clause)
                    for clause in catalog_rule_clauses_from_record(record)
                ):
                    return True
    return False


def _distance_between_rules_units_or_none(
    *,
    context: MovementEndSurgeContext,
    source_rules_unit: RulesUnitView,
    triggering_rules_unit: RulesUnitView,
) -> float | None:
    source_models = _geometry_models_for_rules_unit(
        context=context,
        rules_unit=source_rules_unit,
    )
    triggering_models = _geometry_models_for_rules_unit(
        context=context,
        rules_unit=triggering_rules_unit,
    )
    if not source_models:
        return None
    if not triggering_models:
        raise GameLifecycleError(
            "Catalog movement-end triggering unit requires placed alive models."
        )
    return min(
        DistanceMeasurementContext.from_models(
            source_model,
            triggering_model,
        ).closest_distance_inches()
        for source_model in source_models
        for triggering_model in triggering_models
    )


def _geometry_models_for_rules_unit(
    *,
    context: MovementEndSurgeContext,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    battlefield_state = context.state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Catalog movement-end geometry lookup requires battlefield_state.")
    models: list[GeometryModel] = []
    for model in rules_unit.alive_models():
        placement = battlefield_state.model_placement_or_none(model.model_instance_id)
        if placement is None:
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def _validate_ability_indexes(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog movement-end reaction indexes must be a mapping.")
    validated: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or not player_id.strip() or player_id != player_id.strip():
            raise GameLifecycleError("Catalog movement-end reaction player id is invalid.")
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog movement-end reaction index is invalid.")
        validated[player_id] = index
    return MappingProxyType(validated)


def _validate_armies(value: tuple[ArmyDefinition, ...]) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog movement-end reaction armies must be a tuple.")
    for army in value:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog movement-end reaction army is invalid.")
    player_ids = tuple(army.player_id for army in value)
    if len(set(player_ids)) != len(player_ids):
        raise GameLifecycleError("Catalog movement-end reaction armies duplicate player ids.")
    return tuple(sorted(value, key=lambda army: army.player_id))
