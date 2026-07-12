from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.dice import (
    D3RollResult,
    DiceExpression,
    DiceRollSpec,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import BATTLE_SHOCK_ROLL_TYPE
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockHookBinding,
    BattleShockOutcomeContext,
    BattleShockRerollPermissionContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_ir_consumers_for_clause,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleIRError,
    parameter_payload,
)

CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE = "catalog_ir.battle_shock_failed_heal_d3"
CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT = "catalog_battle_shock_failed_heal_resolved"
CATALOG_BATTLE_SHOCK_FAILED_HEAL_NO_EFFECT_EVENT = "catalog_battle_shock_failed_heal_no_effect"


def catalog_battle_shock_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleShockHookBinding, ...]:
    bindings: list[BattleShockHookBinding] = []
    if _has_catalog_battle_shock_records(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        consumer_ids=(CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,),
    ):
        bindings.append(
            BattleShockHookBinding(
                hook_id=CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
                source_id=CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
                forced_test_handler=catalog_forced_battle_shock_unit_ids,
            )
        )
    if _has_catalog_battle_shock_records(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        consumer_ids=(CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,),
    ):
        bindings.append(
            BattleShockHookBinding(
                hook_id=CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
                source_id=CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
                outcome_handler=resolve_catalog_battle_shock_failed_heal,
            )
        )
    if _has_catalog_battle_shock_records(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        consumer_ids=(CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,),
    ):
        runtime = CatalogBattleShockRerollRuntime(
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            armies=armies,
        )
        bindings.append(
            BattleShockHookBinding(
                hook_id=CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
                source_id=CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
                reroll_permission_handler=runtime.reroll_permission,
            )
        )
    return tuple(bindings)


@dataclass(frozen=True, slots=True)
class CatalogBattleShockRerollRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_indexes(self.ability_indexes_by_player_id),
        )
        object.__setattr__(self, "armies", _validate_armies(self.armies))

    def reroll_permission(
        self,
        context: BattleShockRerollPermissionContext,
    ) -> RerollPermission | None:
        if type(context) is not BattleShockRerollPermissionContext:
            raise GameLifecycleError("Catalog Battle-shock reroll requires context.")
        player_id = context.request.player_id
        army = _army_for_player(self.armies, player_id=player_id)
        target_unit = _unit_in_army(army, unit_instance_id=context.request.unit_instance_id)
        target_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
            state=context.state,
            unit=target_unit,
        )
        if not target_model_ids:
            return None
        index = self.ability_indexes_by_player_id.get(player_id)
        if index is None:
            raise GameLifecycleError("Catalog Battle-shock reroll is missing ability index.")
        permissions: list[RerollPermission] = []
        for source_unit in army.units:
            source_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=context.state,
                unit=source_unit,
            )
            if not source_model_ids:
                continue
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                if not catalog_rule_record_source_matches_unit(
                    record=record,
                    unit=source_unit,
                    current_model_instance_ids=source_model_ids,
                ):
                    continue
                permissions.extend(
                    _battle_shock_reroll_permissions_from_record(
                        context=context,
                        record=record,
                        source_unit=source_unit,
                        source_model_ids=source_model_ids,
                        target_unit=target_unit,
                        target_model_ids=target_model_ids,
                    )
                )
        if len(permissions) > 1:
            raise GameLifecycleError("Multiple catalog Battle-shock reroll permissions matched.")
        return permissions[0] if permissions else None


def catalog_forced_battle_shock_unit_ids(
    context: BattleShockForcedTestContext,
) -> tuple[str, ...]:
    if type(context) is not BattleShockForcedTestContext:
        raise GameLifecycleError("Catalog Battle-shock forced tests require context.")
    if context.phase is not BattlePhase.COMMAND:
        return ()
    active_army = context.state.army_definition_for_player(context.active_player_id)
    if active_army is None:
        raise GameLifecycleError("Catalog Battle-shock forced tests require active army.")
    forced_ids: set[str] = set()
    for unit in active_army.units:
        for effect in context.state.persisting_effects_for_unit(unit.unit_instance_id):
            if effect.owner_player_id == context.active_player_id:
                continue
            if _persisted_forced_battle_shock_effect(effect):
                forced_ids.add(unit.unit_instance_id)
    return tuple(sorted(forced_ids))


def resolve_catalog_battle_shock_failed_heal(context: BattleShockOutcomeContext) -> None:
    if type(context) is not BattleShockOutcomeContext:
        raise GameLifecycleError("Catalog Battle-shock heal requires outcome context.")
    if context.phase is not BattlePhase.COMMAND:
        return
    result = context.result
    if result.passed:
        return
    target_unit_id = result.request.unit_instance_id
    for effect in context.state.persisting_effects_for_unit(target_unit_id):
        if effect.owner_player_id == result.request.player_id:
            continue
        if not _persisted_failed_battle_shock_heal_effect(effect):
            continue
        _resolve_failed_battle_shock_heal_effect(context=context, effect=effect)


def _resolve_failed_battle_shock_heal_effect(
    *,
    context: BattleShockOutcomeContext,
    effect: PersistingEffect,
) -> None:
    source_unit_id = _generic_effect_source_unit_id(effect)
    source_unit = _unit_by_id(tuple(context.state.army_definitions), source_unit_id)
    current_model_ids = _placed_model_ids_for_unit(
        context=context,
        unit_instance_id=source_unit.unit_instance_id,
    )
    if not current_model_ids:
        context.decisions.event_log.append(
            CATALOG_BATTLE_SHOCK_FAILED_HEAL_NO_EFFECT_EVENT,
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.phase.value,
                "hook_id": CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
                "battle_shock_result_id": context.result.result_id,
                "persisting_effect_id": effect.effect_id,
                "source_unit_instance_id": source_unit.unit_instance_id,
                "no_effect_reason": "source_unit_not_placed",
            },
        )
        return
    d3_result = _roll_d3(
        context=context,
        reason="Catalog Battle-shock failed heal",
        actor_id=source_unit.unit_instance_id,
    )
    healing_effect = HealingEffect(
        effect_id=f"{effect.effect_id}:battle-shock-failed-heal:{context.result.result_id}",
        target_unit_instance_id=source_unit.unit_instance_id,
        amount=d3_result.value,
        opposing_player_id=context.result.request.player_id,
        selection_actor_player_id=effect.owner_player_id,
        source_rule_id=effect.source_rule_id,
        source_context=validate_json_value(
            {
                "source_kind": "generic_rule_ir_battle_shock_failed_heal",
                "hook_id": CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
                "battle_shock_result_id": context.result.result_id,
                "persisting_effect": validate_json_value(effect.to_payload()),
                "d3_result": validate_json_value(d3_result.to_payload()),
            }
        ),
        phase_start_model_ids=current_model_ids,
    )
    resolved, pending = resolve_healing_until_blocked(
        state=context.state,
        decisions=context.decisions,
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        effect=healing_effect,
    )
    if pending is not None:
        raise GameLifecycleError(
            "Catalog Battle-shock failed heal unexpectedly requested a choice."
        )
    context.decisions.event_log.append(
        CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "hook_id": CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
            "battle_shock_result_id": context.result.result_id,
            "player_id": effect.owner_player_id,
            "source_unit_instance_id": source_unit.unit_instance_id,
            "target_unit_instance_id": context.result.request.unit_instance_id,
            "persisting_effect_id": effect.effect_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "healing_effect": validate_json_value(resolved.to_payload()),
        },
    )


def _persisted_forced_battle_shock_effect(effect: PersistingEffect) -> bool:
    rule_effect = _generic_rule_effect_or_none(effect)
    if rule_effect is None or rule_effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(rule_effect.parameters)
    return (
        parameters.get("status") == "battle_shock_forced_below_starting_strength"
        and parameters.get("rules_context") == "battle_shock"
        and parameters.get("force_battle_shock_below_starting_strength") is True
    )


def _persisted_failed_battle_shock_heal_effect(effect: PersistingEffect) -> bool:
    rule_effect = _generic_rule_effect_or_none(effect)
    if rule_effect is None or rule_effect.kind is not RuleEffectKind.RESTORE_LOST_WOUNDS:
        return False
    parameters = parameter_payload(rule_effect.parameters)
    return (
        parameters.get("amount") == "D3"
        and parameters.get("trigger") == "target_failed_battle_shock"
        and parameters.get("source_reference") == "aura_source"
    )


def _battle_shock_reroll_permissions_from_record(
    *,
    context: BattleShockRerollPermissionContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_ids: tuple[str, ...],
    target_unit: UnitInstance,
    target_model_ids: tuple[str, ...],
) -> tuple[RerollPermission, ...]:
    permissions: list[RerollPermission] = []
    for clause in catalog_rule_clauses_from_record(record):
        if CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID not in catalog_rule_ir_consumers_for_clause(
            clause
        ):
            continue
        if not _battle_shock_reroll_clause_matches_source(clause, source_unit=source_unit):
            continue
        if not _battle_shock_reroll_clause_matches_target(clause, target_unit=target_unit):
            continue
        if not _units_within_distance(
            context=context,
            first_unit=source_unit,
            first_model_ids=source_model_ids,
            second_unit=target_unit,
            second_model_ids=target_model_ids,
            distance_inches=_battle_shock_reroll_distance_inches(clause),
        ):
            continue
        for effect_index, effect in enumerate(clause.effects, start=1):
            if not _effect_is_battle_shock_reroll(effect):
                continue
            permissions.append(
                RerollPermission(
                    source_id=(f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}"),
                    timing_window="battle_shock_test",
                    owning_player_id=context.request.player_id,
                    eligible_roll_type=BATTLE_SHOCK_ROLL_TYPE,
                    component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
                )
            )
    return tuple(permissions)


def _effect_is_battle_shock_reroll(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog Battle-shock reroll effect is invalid.")
    if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("roll_type") in {"battle_shock", "battle_shock_roll", "battle_shock_test"}
        and parameters.get("timing_window") == "battle_shock_test"
    )


def _battle_shock_reroll_clause_matches_target(
    clause: RuleClause,
    *,
    target_unit: UnitInstance,
) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog Battle-shock reroll clause is invalid.")
    if type(target_unit) is not UnitInstance:
        raise GameLifecycleError("Catalog Battle-shock reroll target unit is invalid.")
    for required_keyword in _required_keywords_for_clause(clause):
        if not _unit_has_required_keyword(target_unit, required_keyword=required_keyword):
            return False
    return True


def _battle_shock_reroll_clause_matches_source(
    clause: RuleClause,
    *,
    source_unit: UnitInstance,
) -> bool:
    object_kind = _source_distance_object_kind(clause)
    if object_kind == "fortification":
        return _unit_has_required_keyword(source_unit, required_keyword="FORTIFICATION")
    raise GameLifecycleError("Catalog Battle-shock reroll source object kind is malformed.")


def _source_distance_object_kind(clause: RuleClause) -> str:
    object_kinds: set[str] = set()
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        object_kind = parameters.get("object_kind")
        if type(object_kind) is str and parameters.get("object_reference") == "this":
            object_kinds.add(object_kind)
    if len(object_kinds) != 1:
        raise GameLifecycleError(
            "Catalog Battle-shock reroll requires exactly one source object kind."
        )
    return next(iter(object_kinds))


def _required_keywords_for_clause(clause: RuleClause) -> tuple[str, ...]:
    keywords: set[str] = set()
    if clause.target is not None:
        target_parameters = parameter_payload(clause.target.parameters)
        required_keyword = target_parameters.get("required_keyword")
        if type(required_keyword) is str:
            keywords.add(required_keyword)
        required_sequence = target_parameters.get("required_keyword_sequence")
        if type(required_sequence) is tuple:
            for value in required_sequence:
                if type(value) is not str:
                    raise GameLifecycleError(
                        "Catalog Battle-shock reroll target keyword sequence is malformed."
                    )
                keywords.add(value)
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        required_keyword = parameters.get("required_keyword")
        if type(required_keyword) is str:
            keywords.add(required_keyword)
        required_sequence = parameters.get("required_keyword_sequence")
        if type(required_sequence) is tuple:
            for value in required_sequence:
                if type(value) is not str:
                    raise GameLifecycleError(
                        "Catalog Battle-shock reroll condition keyword sequence is malformed."
                    )
                keywords.add(value)
    return tuple(sorted(keywords))


def _unit_has_required_keyword(unit: UnitInstance, *, required_keyword: str) -> bool:
    required = _canonical_keyword(required_keyword)
    keywords = {_canonical_keyword(keyword) for keyword in (*unit.keywords, *unit.faction_keywords)}
    if required in keywords:
        return True
    return _keyword_sequence_is_covered(tuple(required.split()), frozenset(keywords))


def _keyword_sequence_is_covered(
    required_words: tuple[str, ...],
    keywords: frozenset[str],
) -> bool:
    if not required_words:
        return True
    for keyword in keywords:
        keyword_words = tuple(keyword.split())
        if (
            keyword_words
            and required_words[: len(keyword_words)] == keyword_words
            and (_keyword_sequence_is_covered(required_words[len(keyword_words) :], keywords))
        ):
            return True
    return False


def _battle_shock_reroll_distance_inches(clause: RuleClause) -> float:
    matches: list[float] = []
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("range_kind") == "numeric_range"
            and parameters.get("predicate") == "within"
            and parameters.get("object_kind") == "fortification"
            and parameters.get("object_reference") == "this"
            and parameters.get("negated") is False
        ):
            distance = parameters.get("distance_inches")
            if not isinstance(distance, int | float) or type(distance) is bool or distance <= 0:
                raise GameLifecycleError(
                    "Catalog Battle-shock reroll distance predicate is malformed."
                )
            matches.append(float(distance))
    if len(matches) != 1:
        raise GameLifecycleError(
            "Catalog Battle-shock reroll requires exactly one source distance predicate."
        )
    return matches[0]


def _units_within_distance(
    *,
    context: BattleShockRerollPermissionContext,
    first_unit: UnitInstance,
    first_model_ids: tuple[str, ...],
    second_unit: UnitInstance,
    second_model_ids: tuple[str, ...],
    distance_inches: float,
) -> bool:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Catalog Battle-shock reroll requires battlefield state.")
    scenario = BattlefieldScenario(
        armies=tuple(context.state.army_definitions),
        battlefield_state=battlefield,
    )
    first_models = _geometry_models_for_unit_ids(
        scenario=scenario,
        unit=first_unit,
        model_ids=first_model_ids,
    )
    second_models = _geometry_models_for_unit_ids(
        scenario=scenario,
        unit=second_unit,
        model_ids=second_model_ids,
    )
    return any(
        first_model.base_distance_to(second_model) <= distance_inches
        for first_model in first_models
        for second_model in second_models
    )


def _geometry_models_for_unit_ids(
    *,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    model_ids: tuple[str, ...],
) -> tuple[GeometryModel, ...]:
    requested_ids = frozenset(_validate_identifier_tuple("model_ids", model_ids))
    try:
        unit_placement = scenario.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Catalog Battle-shock reroll unit placement is missing.") from exc
    models: list[GeometryModel] = []
    for placement in unit_placement.model_placements:
        if placement.model_instance_id not in requested_ids:
            continue
        model = scenario.model_instance_for_placement(placement)
        if not model.is_alive:
            raise GameLifecycleError("Catalog Battle-shock reroll model evidence drifted.")
        models.append(geometry_model_for_placement(model=model, placement=placement))
    if len(models) != len(requested_ids):
        raise GameLifecycleError("Catalog Battle-shock reroll placement evidence drifted.")
    return tuple(models)


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str or not keyword.strip():
        raise GameLifecycleError("Catalog Battle-shock reroll keyword must be a string.")
    return keyword.strip().upper().replace("_", " ").replace("-", " ")


def _generic_rule_effect_or_none(effect: PersistingEffect) -> RuleEffectSpec | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    effect_payload = payload.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Catalog Battle-shock generic effect payload is missing effect.")
    try:
        return RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, effect_payload))
    except RuleIRError as exc:
        raise GameLifecycleError("Catalog Battle-shock generic effect payload is invalid.") from exc


def _generic_effect_source_unit_id(effect: PersistingEffect) -> str:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog Battle-shock heal requires generic effect payload.")
    context_payload = payload.get("context")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Catalog Battle-shock heal requires generic context payload.")
    source_unit_id = context_payload.get("source_unit_instance_id")
    if type(source_unit_id) is not str:
        raise GameLifecycleError("Catalog Battle-shock heal requires source unit context.")
    return source_unit_id


def _roll_d3(
    *,
    context: BattleShockOutcomeContext,
    reason: str,
    actor_id: str,
) -> D3RollResult:
    roll_state = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=reason,
            roll_type=CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE,
            actor_id=actor_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _placed_model_ids_for_unit(
    *,
    context: BattleShockOutcomeContext,
    unit_instance_id: str,
) -> tuple[str, ...]:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Catalog Battle-shock heal requires battlefield state.")
    try:
        placement = battlefield.unit_placement_by_id(unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Catalog Battle-shock heal source unit is not placed.") from exc
    return tuple(placement.model_instance_id for placement in placement.model_placements)


def _unit_by_id(armies: tuple[ArmyDefinition, ...], unit_instance_id: str) -> UnitInstance:
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise GameLifecycleError("Catalog Battle-shock heal source unit is unknown.")


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Catalog Battle-shock runtime player army is unknown.")


def _unit_in_army(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Catalog Battle-shock runtime unit is unknown.")


def _has_catalog_battle_shock_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    consumer_ids: tuple[str, ...],
) -> bool:
    relevant_consumer_ids = set(_validate_identifier_tuple("consumer_ids", consumer_ids))
    for index in ability_indexes_by_player_id.values():
        for record in index.all_records():
            if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                continue
            for clause in catalog_rule_clauses_from_record(record):
                if set(catalog_rule_ir_consumers_for_clause(clause)) & relevant_consumer_ids:
                    return True
    return False


def _validate_ability_indexes(
    indexes: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("Catalog Battle-shock ability indexes must be a mapping.")
    validated: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], indexes).items():
        if type(player_id) is not str or not player_id.strip():
            raise GameLifecycleError("Catalog Battle-shock ability index player ID is invalid.")
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog Battle-shock ability index value is invalid.")
        validated[player_id] = index
    return MappingProxyType(validated)


def _validate_armies(armies: tuple[ArmyDefinition, ...]) -> tuple[ArmyDefinition, ...]:
    if type(armies) is not tuple:
        raise GameLifecycleError("Catalog Battle-shock runtime armies must be a tuple.")
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog Battle-shock runtime armies are invalid.")
    return armies


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Catalog Battle-shock {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in cast(tuple[object, ...], value):
        identifier = _validate_identifier(f"{field_name} value", item)
        if identifier in seen:
            raise GameLifecycleError(
                f"Catalog Battle-shock {field_name} must not contain duplicates."
            )
        identifiers.append(identifier)
        seen.add(identifier)
    return tuple(identifiers)


_validate_identifier = IdentifierValidator(GameLifecycleError)
