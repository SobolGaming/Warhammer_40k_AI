from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
)
from warhammer40k_core.engine.catalog_geometry import alive_geometry_models_for_placement
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleParameterValue,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND = "catalog_rule_ir"

_ENGAGEMENT_RANGE_HORIZONTAL_INCHES = 1.0
_ENGAGEMENT_RANGE_VERTICAL_INCHES = 5.0
_validate_identifier = IdentifierValidator(GameLifecycleError)


def catalog_forced_desperate_escape_sources_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[dict[str, JsonValue], ...]:
    from warhammer40k_core.engine.game_state import GameState as RuntimeGameState

    if type(state) is not RuntimeGameState:
        raise GameLifecycleError("Catalog Desperate Escape requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if state.battlefield_state is None:
        return ()
    target_placement = state.battlefield_state.unit_placement_by_id(requested_unit_id)
    target_unit = _unit_by_id(armies, unit_instance_id=requested_unit_id)
    sources: list[dict[str, JsonValue]] = []
    for army in sorted(armies, key=lambda item: item.player_id):
        if army.player_id == target_placement.player_id:
            continue
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Catalog Desperate Escape missing ability index.")
        for source_unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=state,
                unit=source_unit,
            )
            if not current_model_ids:
                continue
            for record in _matching_desperate_escape_records(
                index=index,
                unit=source_unit,
                current_model_instance_ids=current_model_ids,
            ):
                force_clause = _force_desperate_escape_clause(record)
                if force_clause is None:
                    continue
                if not _falling_back_unit_allowed(clause=force_clause, unit=target_unit):
                    continue
                if not _target_within_source_engagement(
                    state=state,
                    armies=armies,
                    source_unit=source_unit,
                    target_unit_instance_id=requested_unit_id,
                ):
                    continue
                sources.append(
                    _catalog_desperate_escape_source_payload(
                        state=state,
                        record=record,
                        source_unit=source_unit,
                        fall_back_unit_instance_id=requested_unit_id,
                        battle_shocked_modifier=_battle_shocked_modifier_for_record(
                            record=record,
                            target_unit_instance_id=requested_unit_id,
                            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
                        ),
                    )
                )
    return tuple(sorted(sources, key=lambda source: str(source["effect_id"])))


def _matching_desperate_escape_records(
    *,
    index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[AbilityCatalogRecord, ...]:
    records: list[AbilityCatalogRecord] = []
    for record in _records_for_timing(
        index,
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
    ):
        if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
            continue
        if not catalog_rule_record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        ):
            continue
        if _force_desperate_escape_clause(record) is not None:
            records.append(record)
    return tuple(sorted(records, key=lambda item: item.record_id))


def _records_for_timing(
    ability_index: AbilityCatalogIndex,
    trigger_kind: TimingTriggerKind,
) -> tuple[AbilityCatalogRecord, ...]:
    records_by_id: dict[str, AbilityCatalogRecord] = {}
    for timing_kind in (trigger_kind, TimingTriggerKind.ANY_PHASE):
        for record in ability_index.records_for(timing_kind):
            records_by_id.setdefault(record.record_id, record)
    return tuple(sorted(records_by_id.values(), key=lambda record: record.record_id))


def _force_desperate_escape_clause(record: AbilityCatalogRecord) -> RuleClause | None:
    matches: list[RuleClause] = []
    for clause in catalog_rule_clauses_from_record(record):
        if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.UNIT_SELECTED:
            continue
        if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
            continue
        trigger_parameters = parameter_payload(clause.trigger.parameters)
        if (
            trigger_parameters.get("selection") != "fall_back"
            or trigger_parameters.get("selected_unit_allegiance") != "enemy"
        ):
            continue
        if any(
            effect.kind is RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS for effect in clause.effects
        ):
            matches.append(clause)
    if len(matches) > 1:
        raise GameLifecycleError("Catalog Desperate Escape record has multiple force clauses.")
    return matches[0] if matches else None


def _falling_back_unit_allowed(*, clause: RuleClause, unit: UnitInstance) -> bool:
    from warhammer40k_core.engine.rule_target_resolution import canonical_keyword

    unit_keywords = {
        canonical_keyword(keyword) for keyword in (*unit.keywords, *unit.faction_keywords)
    }
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        excluded_any = parameters.get("excluded_keyword_any")
        if excluded_any is None:
            continue
        if type(excluded_any) is not tuple:
            raise GameLifecycleError(
                "Catalog Desperate Escape excluded keywords must be structured."
            )
        excluded_keywords = _canonical_keyword_set(excluded_any)
        if unit_keywords & excluded_keywords:
            return False
    return True


def _canonical_keyword_set(values: tuple[RuleParameterValue, ...]) -> frozenset[str]:
    keywords: set[str] = set()
    from warhammer40k_core.engine.rule_target_resolution import canonical_keyword

    for value in values:
        if type(value) is not str:
            raise GameLifecycleError("Catalog Desperate Escape keyword value is invalid.")
        keywords.add(canonical_keyword(value))
    return frozenset(keywords)


def _target_within_source_engagement(
    *,
    state: GameState,
    armies: tuple[ArmyDefinition, ...],
    source_unit: UnitInstance,
    target_unit_instance_id: str,
) -> bool:
    if state.battlefield_state is None:
        return False
    scenario = BattlefieldScenario(
        armies=armies,
        battlefield_state=state.battlefield_state,
    )
    source_placement = state.battlefield_state.unit_placement_by_id(source_unit.unit_instance_id)
    target_placement = state.battlefield_state.unit_placement_by_id(target_unit_instance_id)
    source_models = alive_geometry_models_for_placement(
        scenario=scenario,
        unit_placement=source_placement,
    )
    target_models = alive_geometry_models_for_placement(
        scenario=scenario,
        unit_placement=target_placement,
    )
    return any(
        source_model.is_within_engagement_range(
            target_model,
            horizontal_inches=_ENGAGEMENT_RANGE_HORIZONTAL_INCHES,
            vertical_inches=_ENGAGEMENT_RANGE_VERTICAL_INCHES,
        )
        for source_model in source_models
        for target_model in target_models
    )


def _battle_shocked_modifier_for_record(
    *,
    record: AbilityCatalogRecord,
    target_unit_instance_id: str,
    battle_shocked_unit_ids: tuple[str, ...],
) -> int:
    if target_unit_instance_id not in battle_shocked_unit_ids:
        return 0
    modifier = 0
    for clause in catalog_rule_clauses_from_record(record):
        if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL:
            continue
        trigger_parameters = parameter_payload(clause.trigger.parameters)
        if trigger_parameters.get("roll_type") != "desperate_escape":
            continue
        if not _clause_requires_battle_shocked_target(clause):
            continue
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
                continue
            effect_parameters = parameter_payload(effect.parameters)
            if effect_parameters.get("roll_type") != "desperate_escape":
                continue
            delta = effect_parameters.get("delta")
            if type(delta) is not int:
                raise GameLifecycleError("Catalog Desperate Escape modifier delta is invalid.")
            modifier += delta
    return modifier


def _clause_requires_battle_shocked_target(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("relationship") == "target_unit_has_status"
            and parameters.get("status") == "battle_shocked"
        ):
            return True
    return False


def _catalog_desperate_escape_source_payload(
    *,
    state: GameState,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    fall_back_unit_instance_id: str,
    battle_shocked_modifier: int,
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
    payload = {
        "effect_id": f"{record.record_id}:force-desperate-escape:{fall_back_unit_instance_id}",
        "source_kind": CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND,
        "source_rule_id": record.definition.source_id,
        "catalog_record_id": record.record_id,
        "ability_id": record.definition.ability_id,
        "ability_name": record.definition.name,
        "rule_ir_hash": rule_ir.ir_hash(),
        "forcing_unit_instance_id": source_unit.unit_instance_id,
        "fall_back_unit_instance_id": fall_back_unit_instance_id,
        "required_fall_back_mode": "desperate_escape",
        "desperate_escape_roll_modifier": battle_shocked_modifier,
        "battle_round": state.battle_round,
        "phase": None if state.current_battle_phase is None else state.current_battle_phase.value,
    }
    return cast(dict[str, JsonValue], validate_json_value(payload))


def _unit_by_id(
    armies: tuple[ArmyDefinition, ...],
    *,
    unit_instance_id: str,
) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Catalog Desperate Escape target unit is unknown.")
