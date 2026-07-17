from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookBinding,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_start_battle_keyword_choice_support import (
    CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID,
    CatalogStartBattleKeywordChoiceDescriptor,
    start_battle_keyword_choice_descriptor_for_clause,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
    RuleParameter,
)

CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT = "catalog_start_battle_keyword_selected"
CATALOG_START_BATTLE_KEYWORD_CHOICE_SUBMISSION_KIND = "catalog_start_battle_keyword_choice"
_HOOK_ID = "catalog-ir:start-battle-keyword-choice:setup"
_REQUEST_PRIORITY = 100


@dataclass(frozen=True, slots=True)
class _KeywordChoiceSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    source_model_instance_id: str
    clause: RuleClause
    rule_ir: RuleIR
    descriptor: CatalogStartBattleKeywordChoiceDescriptor

    @property
    def source_key(self) -> str:
        return f"{self.rule_ir.source_id}:{self.clause.clause_id}:{self.source_model_instance_id}"


@dataclass(frozen=True, slots=True)
class CatalogStartBattleKeywordChoiceRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.ability_indexes_by_player_id), Mapping):
            raise GameLifecycleError("Catalog keyword choice indexes must be a mapping.")
        indexes: dict[str, AbilityCatalogIndex] = {}
        for player_id, index in self.ability_indexes_by_player_id.items():
            if type(player_id) is not str or not player_id:
                raise GameLifecycleError("Catalog keyword choice player IDs must be strings.")
            if type(index) is not AbilityCatalogIndex:
                raise GameLifecycleError(
                    "Catalog keyword choice indexes must contain AbilityCatalogIndex values."
                )
            indexes[player_id] = index
        if type(self.armies) is not tuple or not all(
            type(army) is ArmyDefinition for army in self.armies
        ):
            raise GameLifecycleError(
                "Catalog keyword choice armies must contain ArmyDefinition values."
            )
        if set(indexes) != {army.player_id for army in self.armies}:
            raise GameLifecycleError("Catalog keyword choice indexes must match armies.")
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            MappingProxyType(dict(sorted(indexes.items()))),
        )
        object.__setattr__(
            self,
            "armies",
            tuple(sorted(self.armies, key=lambda army: (army.player_id, army.army_id))),
        )

    def bindings(self) -> tuple[BattleFormationHookBinding, ...]:
        if not any(self._sources()):
            return ()
        return (
            BattleFormationHookBinding(
                hook_id=_HOOK_ID,
                source_id=CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID,
                request_handler=self.request_handler,
                result_handler=self.result_handler,
                request_priority=_REQUEST_PRIORITY,
            ),
        )

    def request_handler(self, context: BattleFormationRequestContext) -> DecisionRequest | None:
        if type(context) is not BattleFormationRequestContext:
            raise GameLifecycleError(
                "Catalog keyword choice requires a battle-formation request context."
            )
        for source in self._sources():
            if _source_is_resolved(state=context.state, source=source):
                continue
            common_payload = _source_payload(context=context, source=source)
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
                actor_id=source.player_id,
                payload=common_payload,
                options=tuple(
                    DecisionOption(
                        option_id=f"{source.clause.clause_id}:keyword:{keyword.casefold()}",
                        label=keyword.title(),
                        payload={**common_payload, "selected_keyword": keyword},
                    )
                    for keyword in source.descriptor.keyword_options
                ),
            )
        return None

    def result_handler(self, context: BattleFormationResultContext) -> bool:
        if type(context) is not BattleFormationResultContext:
            raise GameLifecycleError(
                "Catalog keyword choice requires a battle-formation result context."
            )
        if context.request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
            return False
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != _HOOK_ID:
            return False
        result_payload = _payload_object(context.result.payload)
        source = self._source_for_payload(result_payload)
        _validate_result_source_payload(context=context, source=source, payload=result_payload)
        if _source_is_resolved(state=context.state, source=source):
            raise GameLifecycleError("Catalog start-battle keyword choice is already resolved.")
        selected_keyword = _payload_string(result_payload, "selected_keyword")
        if selected_keyword not in source.descriptor.keyword_options:
            raise GameLifecycleError("Catalog start-battle keyword choice is unsupported.")
        effects = _persisting_effects_for_result(
            context=context,
            source=source,
            selected_keyword=selected_keyword,
        )
        for effect in effects:
            context.state.record_persisting_effect(effect)
        context.decisions.event_log.append(
            CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT,
            {
                **_source_payload(context=context, source=source),
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "selected_option_id": context.result.selected_option_id,
                "selected_keyword": selected_keyword,
                "persisting_effects": [effect.to_payload() for effect in effects],
            },
        )
        return True

    def _sources(self) -> tuple[_KeywordChoiceSource, ...]:
        sources: list[_KeywordChoiceSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for unit in sorted(army.units, key=lambda candidate: candidate.unit_instance_id):
                current_model_ids = tuple(
                    model.model_instance_id for model in unit.own_models if model.is_alive
                )
                if not current_model_ids:
                    continue
                for record in index.all_records():
                    if (
                        record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID
                        or not catalog_rule_record_source_matches_unit(
                            record=record,
                            unit=unit,
                            current_model_instance_ids=current_model_ids,
                        )
                    ):
                        continue
                    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                    for clause in catalog_rule_clauses_from_record(record):
                        descriptor = start_battle_keyword_choice_descriptor_for_clause(clause)
                        if descriptor is None:
                            continue
                        for model_id in current_model_ids:
                            sources.append(
                                _KeywordChoiceSource(
                                    player_id=army.player_id,
                                    record=record,
                                    unit=unit,
                                    source_model_instance_id=model_id,
                                    clause=clause,
                                    rule_ir=rule_ir,
                                    descriptor=descriptor,
                                )
                            )
        return tuple(sorted(sources, key=lambda source: source.source_key))

    def _source_for_payload(self, payload: Mapping[str, object]) -> _KeywordChoiceSource:
        source_key = _payload_string(payload, "source_key")
        matches = tuple(source for source in self._sources() if source.source_key == source_key)
        if len(matches) != 1:
            raise GameLifecycleError("Catalog start-battle keyword choice source drifted.")
        return matches[0]


def catalog_start_battle_keyword_choice_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleFormationHookBinding, ...]:
    return CatalogStartBattleKeywordChoiceRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _source_payload(
    *,
    context: BattleFormationRequestContext | BattleFormationResultContext,
    source: _KeywordChoiceSource,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        "submission_kind": CATALOG_START_BATTLE_KEYWORD_CHOICE_SUBMISSION_KIND,
        "hook_id": _HOOK_ID,
        "consumer_id": CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID,
        "player_id": source.player_id,
        "catalog_record_id": source.record.record_id,
        "source_key": source.source_key,
        "source_rule_id": source.rule_ir.source_id,
        "source_rule_ir_hash": source.rule_ir.ir_hash(),
        "source_clause_id": source.clause.clause_id,
        "source_unit_instance_id": source.unit.unit_instance_id,
        "source_model_instance_id": source.source_model_instance_id,
    }


def _validate_result_source_payload(
    *,
    context: BattleFormationResultContext,
    source: _KeywordChoiceSource,
    payload: Mapping[str, object],
) -> None:
    expected = _source_payload(context=context, source=source)
    for key, expected_value in expected.items():
        if payload.get(key) != expected_value:
            raise GameLifecycleError(f"Catalog start-battle keyword choice {key} drifted.")
    if set(payload) != {*expected, "selected_keyword"}:
        raise GameLifecycleError("Catalog start-battle keyword choice payload is malformed.")


def _source_is_resolved(*, state: object, source: _KeywordChoiceSource) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog keyword choice resolution requires GameState.")
    matching = tuple(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == source.rule_ir.source_id
        and source.unit.unit_instance_id in effect.target_unit_instance_ids
        and _effect_source_model_id(effect) == source.source_model_instance_id
    )
    if len(matching) not in {0, len(source.clause.effects)}:
        raise GameLifecycleError("Catalog keyword choice effects are partially installed.")
    return bool(matching)


def _persisting_effects_for_result(
    *,
    context: BattleFormationResultContext,
    source: _KeywordChoiceSource,
    selected_keyword: str,
) -> tuple[PersistingEffect, ...]:
    execution_context = RuleExecutionContext(
        game_id=context.state.game_id,
        player_id=source.player_id,
        battle_round=max(1, context.state.battle_round),
        phase=None,
        active_player_id=context.state.active_player_id,
        timing_window_id="start_battle",
        source_unit_instance_id=source.unit.unit_instance_id,
        source_model_instance_id=source.source_model_instance_id,
        target_unit_instance_ids=(source.unit.unit_instance_id,),
        source_keywords=tuple(sorted((*source.unit.keywords, *source.unit.faction_keywords))),
        trigger_payload={
            "event": CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
            "selected_keyword": selected_keyword,
        },
        state=context.state,
        event_log=context.decisions.event_log,
        record_persisting_effects=False,
    )
    effects: list[PersistingEffect] = []
    for index, source_effect in enumerate(source.clause.effects):
        effect = replace(
            source_effect,
            parameters=tuple(
                RuleParameter(
                    key=parameter.key,
                    value=(
                        selected_keyword
                        if parameter.key == "target_required_keyword"
                        else parameter.value
                    ),
                )
                for parameter in source_effect.parameters
            ),
        )
        effect_payload = generic_rule_effect_payload(
            rule_ir=source.rule_ir,
            clause=source.clause,
            effect=effect,
            context=execution_context,
            target_unit_instance_ids=(source.unit.unit_instance_id,),
        )
        effects.append(
            generic_rule_persisting_effect(
                effect_id=(f"{context.result.result_id}:catalog-start-battle-keyword:{index:03d}"),
                source_rule_id=source.rule_ir.source_id,
                owner_player_id=source.player_id,
                target_unit_instance_ids=(source.unit.unit_instance_id,),
                started_battle_round=max(1, context.state.battle_round),
                started_phase=None,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=effect_payload,
            )
        )
    return tuple(effects)


def _effect_source_model_id(effect: PersistingEffect) -> str | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    context = payload.get("context")
    if not isinstance(context, dict):
        return None
    value = context.get("source_model_instance_id")
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError("Catalog keyword choice source model payload is malformed.")
    return value


def _payload_object(value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog keyword choice payload must be an object.")
    return payload


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog keyword choice {key} must be a string.")
    return value


__all__ = (
    "CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID",
    "CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT",
    "CatalogStartBattleKeywordChoiceRuntime",
    "catalog_start_battle_keyword_choice_bindings",
)
