from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_geometry import alive_geometry_models_for_placement
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_unit_scoped_generic_records,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleParameterValue,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
    parameters_from_pairs,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_ENGAGEMENT_RANGE_HORIZONTAL_INCHES = 1.0
_ENGAGEMENT_RANGE_VERTICAL_INCHES = 5.0
SUPPORTED_SELECTED_EFFECT_KINDS = frozenset(
    (
        RuleEffectKind.GRANT_WEAPON_ABILITY,
        RuleEffectKind.MODIFY_CHARACTERISTIC,
        RuleEffectKind.MODIFY_DICE_ROLL,
        RuleEffectKind.REROLL_PERMISSION,
        RuleEffectKind.SET_CONTEXTUAL_STATUS,
    )
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


def clause_is_fight_start_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target matcher requires RuleClause.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(clause.trigger.parameters)
    return (
        parameters.get("edge") == "start"
        and parameters.get("phase") == BattlePhase.FIGHT.value
        and not clause.effects
    )


def clause_is_post_shoot_hit_target_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog post-shoot matcher requires RuleClause.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(clause.trigger.parameters)
    target_parameters = parameter_payload(clause.target.parameters)
    return (
        parameters.get("timing_window") == "just_after_friendly_unit_has_shot"
        and parameters.get("target_relationship") == "hit_by_those_attacks"
        and target_parameters.get("target_relationship") == "hit_by_those_attacks"
        and not clause.effects
    )


def selected_effect_clauses_after(
    clauses: tuple[RuleClause, ...],
    selection_index: int,
    *,
    include_immediate_effects: bool = False,
) -> tuple[RuleClause, ...]:
    selected: list[RuleClause] = []
    for clause in clauses[selection_index + 1 :]:
        if clause.template_id == "phase17c:selected-target-constraint":
            break
        if not clause.effects:
            continue
        if clause.duration is None and not (
            include_immediate_effects and clause_has_immediate_selected_target_effect(clause)
        ):
            continue
        if any(effect.kind in SUPPORTED_SELECTED_EFFECT_KINDS for effect in clause.effects):
            selected.append(clause)
    return tuple(selected)


def clause_has_immediate_selected_target_effect(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target matcher requires RuleClause.")
    if clause.duration is not None or clause.target is None:
        return False
    if clause.target.kind not in {RuleTargetKind.SELECTED_UNIT, RuleTargetKind.SELECTED_TARGET}:
        return False
    return any(
        effect_is_immediate_selected_target_battle_shock(effect) for effect in clause.effects
    )


def effect_is_immediate_selected_target_battle_shock(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog selected-target matcher requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("rules_context") == "battle_shock"
        and parameters.get("status") == "force_battle_shock_test"
        and parameters.get("required") is True
        and parameters.get("target_scope") == "selected_unit"
    )


def eligible_selection_target_unit_ids(
    *,
    state: GameState,
    source_player_id: str,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    explicit_target_unit_ids: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        return ()
    source_player = _validate_identifier("source_player_id", source_player_id)
    source_unit_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    source_army = army_for_player(tuple(state.army_definitions), player_id=source_player)
    source_unit = unit_in_army_by_id(source_army, unit_instance_id=source_unit_id)
    source_placement = state.battlefield_state.unit_placement_by_id(source_unit_id)
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    explicit_ids = (
        None
        if explicit_target_unit_ids is None
        else set(validate_identifier_tuple("explicit_target_unit_ids", explicit_target_unit_ids))
    )
    target_ids: list[str] = []
    for placed_army in state.battlefield_state.placed_armies:
        if placed_army.player_id == source_player:
            continue
        for target_placement in placed_army.unit_placements:
            if explicit_ids is not None and target_placement.unit_instance_id not in explicit_ids:
                continue
            if selection_target_conditions_apply(
                state=state,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                source_unit=source_unit,
                source_placement=source_placement,
                source_model_instance_id=source_model_instance_id,
                target_placement=target_placement,
                selection_clause=selection_clause,
            ):
                target_ids.append(target_placement.unit_instance_id)
    return tuple(sorted(target_ids))


def selection_target_conditions_apply(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    source_unit: UnitInstance,
    source_placement: UnitPlacement,
    source_model_instance_id: str | None,
    target_placement: UnitPlacement,
    selection_clause: RuleClause,
) -> bool:
    if not selection_distance_conditions_apply(
        scenario=scenario,
        source_placement=source_placement,
        source_model_instance_id=source_model_instance_id,
        target_placement=target_placement,
        selection_clause=selection_clause,
    ):
        return False
    return selection_visibility_conditions_apply(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        source_unit=source_unit,
        source_model_instance_id=source_model_instance_id,
        target_placement=target_placement,
        selection_clause=selection_clause,
    )


def selection_distance_conditions_apply(
    *,
    scenario: BattlefieldScenario,
    source_placement: UnitPlacement,
    source_model_instance_id: str | None,
    target_placement: UnitPlacement,
    selection_clause: RuleClause,
) -> bool:
    distance_conditions = tuple(
        condition
        for condition in selection_clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    if not distance_conditions:
        return True
    source_models = geometry_models_for_placement(
        scenario=scenario,
        unit_placement=source_placement,
        source_model_instance_id=source_model_instance_id,
    )
    target_models = geometry_models_for_placement(
        scenario=scenario,
        unit_placement=target_placement,
        source_model_instance_id=None,
    )
    for condition in distance_conditions:
        parameters = parameter_payload(condition.parameters)
        if parameters.get("negated") is True:
            raise GameLifecycleError("Catalog selected-target negated distance is unsupported.")
        if parameters.get("predicate") != "within_engagement_range" and (
            parameters.get("range_kind") != "numeric_range"
        ):
            raise GameLifecycleError("Catalog selected-target distance predicate is unsupported.")
        if not any_models_satisfy_distance(
            source_models=source_models,
            target_models=target_models,
            parameters=parameters,
        ):
            return False
    return True


def selection_visibility_conditions_apply(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    source_unit: UnitInstance,
    source_model_instance_id: str | None,
    target_placement: UnitPlacement,
    selection_clause: RuleClause,
) -> bool:
    visibility_conditions = tuple(
        condition
        for condition in selection_clause.conditions
        if condition.kind is RuleConditionKind.VISIBILITY_PREDICATE
    )
    if not visibility_conditions:
        return True
    if state.battlefield_state is None:
        raise GameLifecycleError("Catalog selected-target visibility requires battlefield_state.")
    for condition in visibility_conditions:
        parameters = parameter_payload(condition.parameters)
        if parameters.get("predicate") != "visible_to":
            raise GameLifecycleError("Catalog selected-target visibility predicate is unsupported.")
        if parameters.get("target_reference") != "selected_unit":
            raise GameLifecycleError("Catalog selected-target visibility target is unsupported.")
        observer = parameters.get("observer")
        if observer == "this_model":
            observer_model_id = source_model_instance_id
            if observer_model_id is None:
                raise GameLifecycleError(
                    "Catalog selected-target this-model visibility requires source model."
                )
        elif observer == "this_unit":
            observer_model_id = None
        else:
            raise GameLifecycleError("Catalog selected-target visibility observer is unsupported.")
        if not unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            observing_unit=source_unit,
            target_unit_id=target_placement.unit_instance_id,
            observer_model_instance_id=observer_model_id,
            terrain_features=state.battlefield_state.terrain_features,
        ):
            return False
    return True


def any_models_satisfy_distance(
    *,
    source_models: tuple[Model, ...],
    target_models: tuple[Model, ...],
    parameters: Mapping[str, RuleParameterValue],
) -> bool:
    if parameters.get("range_kind") == "engagement_range":
        return any(
            source_model.is_within_engagement_range(
                target_model,
                horizontal_inches=_ENGAGEMENT_RANGE_HORIZONTAL_INCHES,
                vertical_inches=_ENGAGEMENT_RANGE_VERTICAL_INCHES,
            )
            for source_model in source_models
            for target_model in target_models
        )
    distance_inches = parameters.get("distance_inches")
    if not isinstance(distance_inches, (int, float)) or type(distance_inches) is bool:
        raise GameLifecycleError("Catalog selected-target numeric range is malformed.")
    maximum_distance_inches = float(distance_inches)
    return any(
        source_model.range_to(target_model) <= maximum_distance_inches
        for source_model in source_models
        for target_model in target_models
    )


def geometry_models_for_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    source_model_instance_id: str | None,
) -> tuple[Model, ...]:
    return alive_geometry_models_for_placement(
        scenario=scenario,
        unit_placement=unit_placement,
        model_instance_id=source_model_instance_id,
    )


def effect_target_unit_ids(
    *,
    state: GameState,
    source_player_id: str,
    source_unit: UnitInstance,
    selected_target_unit_instance_id: str,
    clause: RuleClause,
) -> tuple[str, ...]:
    if clause.target is None:
        return ()
    if clause.target.kind in {RuleTargetKind.THIS_MODEL, RuleTargetKind.THIS_UNIT}:
        return (source_unit.unit_instance_id,)
    if clause.target.kind in {
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.SELECTED_TARGET,
        RuleTargetKind.SELECTED_UNIT,
    }:
        return (selected_target_unit_instance_id,)
    if clause.target.kind is not RuleTargetKind.FRIENDLY_UNIT:
        return ()
    if state.battlefield_state is None:
        return ()
    from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords

    required_keywords = required_keywords_for_clause(clause)
    target_ids: list[str] = []
    for placed_army in state.battlefield_state.placed_armies:
        if placed_army.player_id != source_player_id:
            continue
        army = army_for_player(tuple(state.army_definitions), player_id=placed_army.player_id)
        for placement in placed_army.unit_placements:
            unit = unit_in_army_by_id(army, unit_instance_id=placement.unit_instance_id)
            if required_keywords and not unit_has_required_keywords(
                unit_keywords=unit.keywords,
                faction_keywords=unit.faction_keywords,
                required_keywords=required_keywords,
            ):
                continue
            target_ids.append(placement.unit_instance_id)
    return tuple(sorted(target_ids))


def required_keywords_for_clause(clause: RuleClause) -> tuple[str, ...]:
    keywords: list[str] = []
    if clause.target is not None:
        target_parameters = parameter_payload(clause.target.parameters)
        target_keyword = target_parameters.get("required_keyword")
        if type(target_keyword) is str:
            keywords.append(target_keyword)
        target_sequence = target_parameters.get("required_keyword_sequence")
        if type(target_sequence) is tuple:
            keywords.extend(target_sequence)
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        condition_parameters = parameter_payload(condition.parameters)
        keyword = condition_parameters.get("required_keyword")
        if type(keyword) is str:
            keywords.append(keyword)
    return tuple(sorted(set(keywords)))


def selected_target_status_gate_allows(
    *,
    state: GameState,
    clause: RuleClause,
    selected_target_unit_instance_id: str,
) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
            continue
        parameters = parameter_payload(condition.parameters)
        if parameters.get("relationship") != "target_unit_has_status":
            continue
        status = parameters.get("status")
        if status != "battle_shocked":
            raise GameLifecycleError("Catalog selected-target status is unsupported.")
        return selected_target_unit_instance_id in state.battle_shocked_unit_ids
    return True


def effect_with_selected_target(
    effect: RuleEffectSpec,
    *,
    selected_target_unit_instance_id: str,
) -> RuleEffectSpec:
    pairs: list[tuple[str, RuleParameterValue]] = [
        (parameter.key, parameter.value)
        for parameter in effect.parameters
        if parameter.key != "selected_target_unit_instance_id"
    ]
    pairs.append(("selected_target_unit_instance_id", selected_target_unit_instance_id))
    return replace(effect, parameters=parameters_from_pairs(tuple(pairs)))


def selection_source_model_ids(
    *,
    selection_clause: RuleClause,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[str | None, ...]:
    for condition in selection_clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("object_kind") == "model"
            and parameters.get("object_reference") == "this"
        ):
            return current_model_instance_ids
    return (None,)


def has_fight_start_selected_target_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        any(
            clause_is_fight_start_selection(clause)
            for clause in catalog_selected_target_clauses_from_record(record)
        )
        for index in ability_indexes_by_player_id.values()
        for record in records_for_timing(index, TimingTriggerKind.START_PHASE)
    )


def has_post_shoot_hit_target_effect_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        any(
            clause_is_post_shoot_hit_target_selection(clause)
            for clause in catalog_selected_target_clauses_from_record(record)
        )
        for index in ability_indexes_by_player_id.values()
        for record in records_for_timing(
            index,
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        )
    )


def unit_scoped_generic_records_for_timing(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    trigger_kind: TimingTriggerKind,
) -> tuple[AbilityCatalogRecord, ...]:
    records_by_id: dict[str, AbilityCatalogRecord] = {}
    for timing_kind in (trigger_kind, TimingTriggerKind.ANY_PHASE):
        for record in catalog_rule_unit_scoped_generic_records(
            ability_index=ability_index,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
            trigger_kind=timing_kind,
        ):
            records_by_id.setdefault(record.record_id, record)
    return tuple(sorted(records_by_id.values(), key=lambda record: record.record_id))


def records_for_timing(
    ability_index: AbilityCatalogIndex,
    trigger_kind: TimingTriggerKind,
) -> tuple[AbilityCatalogRecord, ...]:
    records_by_id: dict[str, AbilityCatalogRecord] = {}
    for timing_kind in (trigger_kind, TimingTriggerKind.ANY_PHASE):
        for record in ability_index.records_for(timing_kind):
            if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                continue
            records_by_id.setdefault(record.record_id, record)
    return tuple(sorted(records_by_id.values(), key=lambda record: record.record_id))


def catalog_selected_target_clauses_from_record(
    record: AbilityCatalogRecord,
) -> tuple[RuleClause, ...]:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog selected-target requires AbilityCatalogRecord.")
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    return rule_ir_from_execution_payload(record.definition.replay_payload).clauses


def runtime_clause_id_from_record(record: AbilityCatalogRecord) -> str | None:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog selected-target requires AbilityCatalogRecord.")
    from warhammer40k_core.engine.rule_execution import runtime_clause_id_from_execution_payload

    return runtime_clause_id_from_execution_payload(record.definition.replay_payload)


def army_for_player(
    armies: tuple[ArmyDefinition, ...],
    *,
    player_id: str,
) -> ArmyDefinition:
    requested_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_id:
            return army
    raise GameLifecycleError("Catalog selected-target army is missing.")


def unit_in_army_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_id:
            return unit
    raise GameLifecycleError("Catalog selected-target unit is missing.")


def validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog selected-target armies must be a tuple.")
    armies = cast(tuple[object, ...], value)
    validated: list[ArmyDefinition] = []
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog selected-target armies must contain definitions.")
        validated.append(army)
    return tuple(sorted(validated, key=lambda item: item.player_id))


def validate_ability_indexes(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog selected-target ability indexes must be a mapping.")
    validated: dict[str, AbilityCatalogIndex] = {}
    value_mapping = cast(Mapping[object, object], value)
    for raw_player_id, raw_index in value_mapping.items():
        player_id = _validate_identifier("player_id", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "Catalog selected-target ability indexes must contain indexes."
            )
        validated[player_id] = raw_index
    return MappingProxyType(validated)


def validate_unit(value: object) -> UnitInstance:
    if type(value) is not UnitInstance:
        raise GameLifecycleError("Catalog selected-target requires UnitInstance.")
    return value


def payload_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog selected-target payload must be an object.")
    return cast(dict[str, object], value)


def payload_string(payload: Mapping[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be a string.")
    return _validate_identifier(key, value)


def payload_int(payload: Mapping[str, object], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be an int.")
    return value


def payload_string_tuple(payload: Mapping[str, object], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be a list.")
    values: list[str] = []
    for item in cast(list[object], value):
        if type(item) is not str:
            raise GameLifecycleError(f"Catalog selected-target payload {key} must be strings.")
        values.append(_validate_identifier(key, item))
    return tuple(sorted(values))


def payload_effect_records(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    value = payload.get("generic_rule_effect_records")
    if not isinstance(value, list):
        raise GameLifecycleError("Catalog selected-target effect records must be a list.")
    records: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise GameLifecycleError("Catalog selected-target effect record must be an object.")
        records.append(cast(dict[str, object], item))
    return tuple(records)


def selected_payload(payload: Mapping[str, object]) -> dict[str, object]:
    selected = payload.get("selected_catalog_target_effect")
    if not isinstance(selected, dict):
        raise GameLifecycleError("Catalog selected-target selected payload must be an object.")
    return cast(dict[str, object], selected)


def validate_effect_record_tuple(value: object) -> tuple[dict[str, JsonValue], ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog selected-target effect records must be a tuple.")
    records: list[dict[str, JsonValue]] = []
    for item in cast(tuple[object, ...], value):
        if not isinstance(item, dict):
            raise GameLifecycleError("Catalog selected-target effect record must be an object.")
        record = cast(dict[str, object], item)
        records.append(cast(dict[str, JsonValue], validate_json_value(record)))
    return tuple(records)


def validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        sorted(_validate_identifier(field_name, item) for item in cast(tuple[object, ...], values))
    )


def unit_statuses(state: GameState, unit_instance_id: str) -> list[str]:
    if unit_instance_id in state.battle_shocked_unit_ids:
        return ["battle_shocked"]
    return []


def active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Catalog selected-target requires active_player_id.")
    return _validate_identifier("active_player_id", state.active_player_id)


def battle_phase_kind(phase: BattlePhase) -> BattlePhaseKind:
    if phase is BattlePhase.FIGHT:
        return BattlePhaseKind.FIGHT
    if phase is BattlePhase.SHOOTING:
        return BattlePhaseKind.SHOOTING
    raise GameLifecycleError("Catalog selected-target phase is unsupported.")


def timing_window_id(phase: BattlePhase) -> str:
    if phase is BattlePhase.FIGHT:
        return "fight_phase_start"
    if phase is BattlePhase.SHOOTING:
        return "attack_sequence_completed"
    raise GameLifecycleError("Catalog selected-target phase is unsupported.")
