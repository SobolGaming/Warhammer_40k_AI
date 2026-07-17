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
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.start_battle_hooks import (
    StartBattleHookBinding,
    StartBattleRequestContext,
    StartBattleResultContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
    RuleParameter,
)

CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT = "catalog_start_battle_keyword_selected"
CATALOG_START_BATTLE_KEYWORD_CHOICE_SUBMISSION_KIND = "catalog_start_battle_keyword_choice"
_HOOK_ID = "catalog-ir:start-battle-keyword-choice:start-battle"
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

    def bindings(self) -> tuple[StartBattleHookBinding, ...]:
        if not any(self._sources()):
            return ()
        return (
            StartBattleHookBinding(
                hook_id=_HOOK_ID,
                source_id=CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID,
                request_handler=self.request_handler,
                result_handler=self.result_handler,
                request_priority=_REQUEST_PRIORITY,
            ),
        )

    def validate_state(self, state: object, decisions: DecisionController) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog keyword choice validation requires GameState.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError(
                "Catalog keyword choice validation requires DecisionController."
            )
        sources = self._sources()
        candidate_effects = tuple(
            effect
            for effect in state.persisting_effects
            if _effect_is_keyword_choice_candidate(effect=effect, sources=sources)
        )
        effects_by_source_key: dict[str, list[PersistingEffect]] = {
            source.source_key: [] for source in sources
        }
        for effect in candidate_effects:
            matching_sources = tuple(
                source
                for source in sources
                if effect.source_rule_id == source.rule_ir.source_id
                and effect.target_unit_instance_ids == (source.unit.unit_instance_id,)
                and _effect_source_model_id(effect) == source.source_model_instance_id
            )
            if len(matching_sources) != 1:
                raise GameLifecycleError("Catalog keyword choice effect source drifted.")
            effects_by_source_key[matching_sources[0].source_key].append(effect)
        for source in sources:
            resolved = _validate_effect_bundle(
                source=source,
                effects=tuple(effects_by_source_key[source.source_key]),
                game_id=state.game_id,
                final_setup_step=state.setup_sequence[-1].value,
                decisions=decisions,
            )
            if state.stage is not GameLifecycleStage.SETUP and not resolved:
                raise GameLifecycleError("Catalog keyword choice effect bundle is missing.")

    def request_handler(self, context: StartBattleRequestContext) -> DecisionRequest | None:
        if type(context) is not StartBattleRequestContext:
            raise GameLifecycleError(
                "Catalog keyword choice requires a start-battle request context."
            )
        self.validate_state(context.state, context.decisions)
        for source in self._sources():
            if _source_is_resolved(
                state=context.state,
                source=source,
                decisions=context.decisions,
            ):
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

    def result_handler(self, context: StartBattleResultContext) -> bool:
        if type(context) is not StartBattleResultContext:
            raise GameLifecycleError(
                "Catalog keyword choice requires a start-battle result context."
            )
        if context.request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
            return False
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != _HOOK_ID:
            return False
        self.validate_state(context.state, context.decisions)
        result_payload = _payload_object(context.result.payload)
        source = self._source_for_payload(result_payload)
        _validate_result_source_payload(context=context, source=source, payload=result_payload)
        if _source_is_resolved(
            state=context.state,
            source=source,
            decisions=context.decisions,
        ):
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
) -> tuple[StartBattleHookBinding, ...]:
    return CatalogStartBattleKeywordChoiceRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _source_payload(
    *,
    context: StartBattleRequestContext | StartBattleResultContext,
    source: _KeywordChoiceSource,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "setup_step": (
            None
            if context.state.current_setup_step is None
            else context.state.current_setup_step.value
        ),
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
    context: StartBattleResultContext,
    source: _KeywordChoiceSource,
    payload: Mapping[str, object],
) -> None:
    expected = _source_payload(context=context, source=source)
    for key, expected_value in expected.items():
        if payload.get(key) != expected_value:
            raise GameLifecycleError(f"Catalog start-battle keyword choice {key} drifted.")
    if set(payload) != {*expected, "selected_keyword"}:
        raise GameLifecycleError("Catalog start-battle keyword choice payload is malformed.")


def _source_is_resolved(
    *,
    state: object,
    source: _KeywordChoiceSource,
    decisions: DecisionController,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog keyword choice resolution requires GameState.")
    matching = tuple(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == source.rule_ir.source_id
        and effect.target_unit_instance_ids == (source.unit.unit_instance_id,)
        and _effect_source_model_id(effect) == source.source_model_instance_id
    )
    return _validate_effect_bundle(
        source=source,
        effects=matching,
        game_id=state.game_id,
        final_setup_step=state.setup_sequence[-1].value,
        decisions=decisions,
    )


def _validate_effect_bundle(
    *,
    source: _KeywordChoiceSource,
    effects: tuple[PersistingEffect, ...],
    game_id: str,
    final_setup_step: str,
    decisions: DecisionController,
) -> bool:
    if not effects:
        return False
    if len(effects) != len(source.clause.effects):
        raise GameLifecycleError("Catalog keyword choice effect bundle is not atomic.")
    trigger_payloads: list[dict[str, JsonValue]] = []
    effect_payloads_by_id: dict[str, dict[str, JsonValue]] = {}
    for effect in effects:
        if (
            effect.source_rule_id != source.rule_ir.source_id
            or effect.owner_player_id != source.player_id
            or effect.target_unit_instance_ids != (source.unit.unit_instance_id,)
            or effect.started_battle_round != 1
            or effect.started_phase is not None
            or effect.expiration != EffectExpiration.end_of_battle()
        ):
            raise GameLifecycleError("Catalog keyword choice effect envelope drifted.")
        payload = _payload_object(effect.effect_payload)
        context_payload = _payload_object(payload.get("context"))
        trigger_payload = _payload_object(context_payload.get("trigger_payload"))
        trigger_payloads.append(trigger_payload)
        effect_payloads_by_id[effect.effect_id] = payload
    if len(effect_payloads_by_id) != len(effects):
        raise GameLifecycleError("Catalog keyword choice effect IDs are duplicated.")
    first_trigger = trigger_payloads[0]
    if any(trigger != first_trigger for trigger in trigger_payloads[1:]):
        raise GameLifecycleError("Catalog keyword choice effect bundle selection drifted.")
    if set(first_trigger) != {"event", "request_id", "result_id", "selected_keyword"}:
        raise GameLifecycleError("Catalog keyword choice trigger payload is malformed.")
    if first_trigger.get("event") != CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT:
        raise GameLifecycleError("Catalog keyword choice trigger event drifted.")
    request_id = _payload_string(first_trigger, "request_id")
    result_id = _payload_string(first_trigger, "result_id")
    selected_keyword = _payload_string(first_trigger, "selected_keyword")
    if selected_keyword not in source.descriptor.keyword_options:
        raise GameLifecycleError("Catalog keyword choice selected keyword is unsupported.")
    _validate_choice_decision_record(
        source=source,
        selected_keyword=selected_keyword,
        request_id=request_id,
        result_id=result_id,
        game_id=game_id,
        final_setup_step=final_setup_step,
        decisions=decisions,
    )
    expected_context = {
        "game_id": game_id,
        "player_id": source.player_id,
        "battle_round": 1,
        "phase": None,
        "active_player_id": None,
        "timing_window_id": "start_battle",
        "source_unit_instance_id": source.unit.unit_instance_id,
        "source_model_instance_id": source.source_model_instance_id,
        "target_unit_instance_ids": [source.unit.unit_instance_id],
        "target_player_id": None,
        "source_keywords": sorted((*source.unit.keywords, *source.unit.faction_keywords)),
        "trigger_payload": first_trigger,
        "record_persisting_effects": False,
    }
    for index, source_effect in enumerate(source.clause.effects):
        expected_id = f"{result_id}:catalog-start-battle-keyword:{index:03d}"
        installed_payload = effect_payloads_by_id.get(expected_id)
        if installed_payload is None:
            raise GameLifecycleError("Catalog keyword choice effect identity drifted.")
        expected_effect = replace(
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
        expected_payload = {
            "effect_kind": "generic_rule_execution",
            "rule_id": source.rule_ir.rule_id,
            "source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "clause_id": source.clause.clause_id,
            "source_span": source.clause.source_span.to_payload(),
            "target": None if source.clause.target is None else source.clause.target.to_payload(),
            "target_unit_instance_ids": [source.unit.unit_instance_id],
            "duration": (
                None if source.clause.duration is None else source.clause.duration.to_payload()
            ),
            "effect": expected_effect.to_payload(),
            "context": expected_context,
        }
        if installed_payload != expected_payload:
            raise GameLifecycleError("Catalog keyword choice effect payload drifted.")
    return True


def _validate_choice_decision_record(
    *,
    source: _KeywordChoiceSource,
    selected_keyword: str,
    request_id: str,
    result_id: str,
    game_id: str,
    final_setup_step: str,
    decisions: DecisionController,
) -> None:
    records = tuple(
        record
        for record in decisions.records
        if record.request.request_id == request_id and record.result.result_id == result_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Catalog keyword choice decision provenance drifted.")
    record = records[0]
    request_payload = _payload_object(record.request.payload)
    result_payload = _payload_object(record.result.payload)
    expected_common = {
        "game_id": game_id,
        "setup_step": final_setup_step,
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
    expected_result = {**expected_common, "selected_keyword": selected_keyword}
    expected_option_id = f"{source.clause.clause_id}:keyword:{selected_keyword.casefold()}"
    if (
        record.request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE
        or record.request.actor_id != source.player_id
        or request_payload != expected_common
        or record.result.selected_option_id != expected_option_id
        or result_payload != expected_result
    ):
        raise GameLifecycleError("Catalog keyword choice decision record drifted.")


def _effect_is_keyword_choice_candidate(
    *,
    effect: PersistingEffect,
    sources: tuple[_KeywordChoiceSource, ...],
) -> bool:
    source_rule_ids = {source.rule_ir.source_id for source in sources}
    source_unit_ids = {source.unit.unit_instance_id for source in sources}
    if effect.source_rule_id not in source_rule_ids or not set(
        effect.target_unit_instance_ids
    ).intersection(source_unit_ids):
        return False
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return False
    if payload.get("clause_id") in {source.clause.clause_id for source in sources}:
        return True
    context = payload.get("context")
    if not isinstance(context, dict):
        return False
    trigger = context.get("trigger_payload")
    return isinstance(trigger, dict) and trigger.get("event") == (
        CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT
    )


def _persisting_effects_for_result(
    *,
    context: StartBattleResultContext,
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
