from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilityCatalogRecord
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
    catalog_rule_unit_scoped_generic_records,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_duration_execution import expiration_for_duration
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleIR,
    RuleIRError,
    parameter_payload,
)

CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND = "catalog_shadow_form_selection"
CATALOG_SHADOW_FORM_SELECTED_EVENT = "catalog_shadow_form_selected"
CATALOG_SHADOW_FORM_SUBMISSION_KIND = "catalog_shadow_form_selection"


@dataclass(frozen=True, slots=True)
class CatalogShadowFormRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def battle_round_start_bindings(self) -> tuple[BattleRoundStartHookBinding, ...]:
        if not _has_shadow_form_choice_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            BattleRoundStartHookBinding(
                hook_id=CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
                source_id=CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
                request_handler=self.battle_round_start_request,
                result_handler=self.apply_battle_round_start_result,
            ),
        )

    def battle_round_start_request(
        self,
        context: BattleRoundStartRequestContext,
    ) -> DecisionRequest | None:
        for request in _shadow_form_selection_requests(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        ):
            return request
        return None

    def apply_battle_round_start_result(self, context: BattleRoundStartResultContext) -> bool:
        return apply_catalog_shadow_form_selection_result(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )


def catalog_shadow_form_battle_round_start_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleRoundStartHookBinding, ...]:
    return CatalogShadowFormRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).battle_round_start_bindings()


def apply_catalog_shadow_form_selection_result(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: BattleRoundStartResultContext,
) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Catalog Shadow Form requires a result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Catalog Shadow Form selection requires an actor.")
    if result.actor_id != context.request.actor_id:
        raise GameLifecycleError("Catalog Shadow Form actor drift.")
    try:
        expected_option = context.request.option_by_id(result.selected_option_id)
    except DecisionError as exc:
        raise GameLifecycleError("Catalog Shadow Form selected option is not available.") from exc
    if result.payload != expected_option.payload:
        raise GameLifecycleError("Catalog Shadow Form selected option payload drift.")

    player_id = result.actor_id
    source_unit_id = _payload_string(request_payload, key="source_unit_instance_id")
    army, source_unit = _army_and_unit_for_unit_id(armies=armies, unit_instance_id=source_unit_id)
    if army.player_id != player_id:
        raise GameLifecycleError("Catalog Shadow Form source unit owner drift.")
    if _shadow_form_selection_exists(
        state=context.state,
        source_unit_instance_id=source_unit_id,
        battle_round=context.state.battle_round,
    ):
        raise GameLifecycleError("Catalog Shadow Form selection is already recorded this round.")

    index = _ability_index_for_player(
        ability_indexes_by_player_id,
        player_id=player_id,
    )
    current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
        state=context.state,
        unit=source_unit,
    )
    if not current_model_ids:
        raise GameLifecycleError("Catalog Shadow Form source unit is not currently placed.")
    shadow_form_record, shadow_form_rule_ir = _shadow_form_record_for_request(
        index=index,
        unit=source_unit,
        current_model_instance_ids=current_model_ids,
        request_payload=request_payload,
    )
    selected_payload = _payload_object(result.payload)
    selected_source_id = _payload_string(
        selected_payload,
        key="selected_shadow_form_source_id",
    )
    selected_rule_ir_hash = _payload_string(
        selected_payload,
        key="selected_shadow_form_rule_ir_hash",
    )
    selected_record, selected_rule_ir = _selectable_shadow_form_record_by_source_id(
        index=index,
        unit=source_unit,
        current_model_instance_ids=current_model_ids,
        source_id=selected_source_id,
    )
    if selected_rule_ir.ir_hash() != selected_rule_ir_hash:
        raise GameLifecycleError("Catalog Shadow Form selected RuleIR hash drift.")

    selection_effect = _record_shadow_form_selection_effect(
        context=context,
        player_id=player_id,
        source_unit_instance_id=source_unit_id,
        shadow_form_record=shadow_form_record,
        shadow_form_rule_ir=shadow_form_rule_ir,
        selected_record=selected_record,
        selected_rule_ir=selected_rule_ir,
        selected_option_id=result.selected_option_id,
    )
    context.state.record_persisting_effect(selection_effect)
    rule_context = RuleExecutionContext(
        game_id=context.state.game_id,
        player_id=player_id,
        battle_round=context.state.battle_round,
        phase=BattlePhaseKind.COMMAND,
        active_player_id=context.state.active_player_id,
        timing_window_id="catalog-shadow-form-selection",
        source_unit_instance_id=source_unit_id,
        source_keywords=(*source_unit.keywords, *source_unit.faction_keywords),
        trigger_payload={
            "source": CATALOG_SHADOW_FORM_SUBMISSION_KIND,
            "request_id": context.request.request_id,
            "result_id": result.result_id,
            "selected_shadow_form_source_id": selected_rule_ir.source_id,
        },
        state=context.state,
        event_log=context.decisions.event_log,
        record_persisting_effects=False,
    )
    execution_result = execute_rule_ir(rule_ir=selected_rule_ir, context=rule_context)
    if execution_result.status is not RuleExecutionStatus.APPLIED:
        reason = execution_result.reason
        if reason is None:
            raise GameLifecycleError("Catalog Shadow Form selected RuleIR failed without reason.")
        raise GameLifecycleError(f"Catalog Shadow Form selected RuleIR failed: {reason}.")
    created_effects = _persist_shadow_form_execution_effects(
        context=context,
        player_id=player_id,
        selection_effect_id=selection_effect.effect_id,
        rule_ir=selected_rule_ir,
        rule_context=rule_context,
        effect_payloads=execution_result.effect_payloads,
    )
    context.decisions.event_log.append(
        CATALOG_SHADOW_FORM_SELECTED_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "source_unit_instance_id": source_unit_id,
            "hook_id": CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
            "request_id": context.request.request_id,
            "result_id": result.result_id,
            "source_rule_id": shadow_form_rule_ir.source_id,
            "selected_shadow_form_source_id": selected_rule_ir.source_id,
            "selected_shadow_form_rule_ir_hash": selected_rule_ir.ir_hash(),
            "selection_effect": validate_json_value(selection_effect.to_payload()),
            "rule_execution": validate_json_value(execution_result.to_payload()),
            "created_persisting_effect_ids": [effect.effect_id for effect in created_effects],
        },
    )
    return True


def _shadow_form_selection_requests(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: BattleRoundStartRequestContext,
) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    for army in sorted(armies, key=lambda item: item.player_id):
        index = _ability_index_for_player(
            ability_indexes_by_player_id,
            player_id=army.player_id,
        )
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=context.state,
                unit=unit,
            )
            if not current_model_ids:
                continue
            if _shadow_form_selection_exists(
                state=context.state,
                source_unit_instance_id=unit.unit_instance_id,
                battle_round=context.state.battle_round,
            ):
                continue
            for record in catalog_rule_unit_scoped_generic_records(
                ability_index=index,
                unit=unit,
                current_model_instance_ids=current_model_ids,
                trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
            ):
                request = _shadow_form_selection_request_for_record(
                    context=context,
                    army=army,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                    ability_index=index,
                    record=record,
                )
                if request is not None:
                    requests.append(request)
    return tuple(sorted(requests, key=lambda request: request.request_id))


def _shadow_form_selection_request_for_record(
    *,
    context: BattleRoundStartRequestContext,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    ability_index: AbilityCatalogIndex,
    record: AbilityCatalogRecord,
) -> DecisionRequest | None:
    rule_ir = _rule_ir_from_record(record)
    selectable_source_ids = _shadow_form_selectable_source_ids(record)
    if not selectable_source_ids:
        return None
    options = _shadow_form_selection_options(
        state_battle_round=context.state.battle_round,
        source_unit=unit,
        current_model_instance_ids=current_model_instance_ids,
        ability_index=ability_index,
        selectable_source_ids=selectable_source_ids,
    )
    if not options:
        return None
    common_payload = _shadow_form_common_payload(
        context=context,
        army=army,
        unit=unit,
        record=record,
        rule_ir=rule_ir,
        available_source_ids=tuple(
            _payload_string(_payload_object(option.payload), key="selected_shadow_form_source_id")
            for option in options
        ),
    )
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=options,
    )


def _shadow_form_common_payload(
    *,
    context: BattleRoundStartRequestContext,
    army: ArmyDefinition,
    unit: UnitInstance,
    record: AbilityCatalogRecord,
    rule_ir: RuleIR,
    available_source_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "submission_kind": CATALOG_SHADOW_FORM_SUBMISSION_KIND,
        "hook_id": CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "player_id": army.player_id,
        "active_player_id": context.state.active_player_id,
        "source_unit_instance_id": unit.unit_instance_id,
        "catalog_record_id": record.record_id,
        "source_ability_id": record.definition.ability_id,
        "source_rule_id": rule_ir.source_id,
        "source_rule_ir_hash": rule_ir.ir_hash(),
        "available_shadow_form_source_ids": list(available_source_ids),
    }


def _shadow_form_selection_options(
    *,
    state_battle_round: int,
    source_unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    ability_index: AbilityCatalogIndex,
    selectable_source_ids: tuple[str, ...],
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    seen: set[str] = set()
    for source_id in selectable_source_ids:
        record, rule_ir = _selectable_shadow_form_record_by_source_id(
            index=ability_index,
            unit=source_unit,
            current_model_instance_ids=current_model_instance_ids,
            source_id=source_id,
        )
        if rule_ir.source_id in seen:
            continue
        seen.add(rule_ir.source_id)
        option_payload = validate_json_value(
            {
                "submission_kind": CATALOG_SHADOW_FORM_SUBMISSION_KIND,
                "hook_id": CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
                "battle_round": state_battle_round,
                "source_unit_instance_id": source_unit.unit_instance_id,
                "selected_shadow_form_source_id": rule_ir.source_id,
                "selected_shadow_form_rule_ir_hash": rule_ir.ir_hash(),
                "selected_catalog_record_id": record.record_id,
                "selected_ability_id": record.definition.ability_id,
            }
        )
        options.append(
            DecisionOption(
                option_id=f"catalog-shadow-form:{_hash_for_option(rule_ir.source_id)}",
                label=record.definition.name,
                payload=option_payload,
            )
        )
    return tuple(sorted(options, key=lambda option: option.option_id))


def _shadow_form_record_for_request(
    *,
    index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    request_payload: dict[str, JsonValue],
) -> tuple[AbilityCatalogRecord, RuleIR]:
    requested_record_id = _payload_string(request_payload, key="catalog_record_id")
    requested_source_id = _payload_string(request_payload, key="source_rule_id")
    requested_hash = _payload_string(request_payload, key="source_rule_ir_hash")
    for record in index.records_for(TimingTriggerKind.START_BATTLE_ROUND):
        if record.record_id != requested_record_id:
            continue
        if not catalog_rule_record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        ):
            break
        rule_ir = _rule_ir_from_record(record)
        if rule_ir.source_id != requested_source_id or rule_ir.ir_hash() != requested_hash:
            raise GameLifecycleError("Catalog Shadow Form request source RuleIR drift.")
        if not _shadow_form_selectable_source_ids(record):
            raise GameLifecycleError("Catalog Shadow Form request record lost selectable effects.")
        return record, rule_ir
    raise GameLifecycleError("Catalog Shadow Form source record is no longer available.")


def _selectable_shadow_form_record_by_source_id(
    *,
    index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    source_id: str,
) -> tuple[AbilityCatalogRecord, RuleIR]:
    requested_source_id = _validate_identifier("selected_shadow_form_source_id", source_id)
    matches: list[tuple[AbilityCatalogRecord, RuleIR]] = []
    for record in index.all_records():
        if not catalog_rule_record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        ):
            continue
        rule_ir = _rule_ir_from_record(record)
        if rule_ir.source_id == requested_source_id:
            matches.append((record, rule_ir))
    deduped_by_hash = {rule_ir.ir_hash(): (record, rule_ir) for record, rule_ir in matches}
    if len(deduped_by_hash) != 1:
        raise GameLifecycleError("Catalog Shadow Form selectable record lookup was ambiguous.")
    return next(iter(deduped_by_hash.values()))


def _shadow_form_selectable_source_ids(record: AbilityCatalogRecord) -> tuple[str, ...]:
    selectable: list[str] = []
    for clause in catalog_rule_clauses_from_record(record):
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
                continue
            parameters = parameter_payload(effect.parameters)
            if (
                parameters.get("status") != "catalog_shadow_form_selection"
                or parameters.get("rules_context") != "shadow_form"
            ):
                continue
            source_ids = parameters.get("selectable_source_ids")
            if type(source_ids) is not tuple:
                raise GameLifecycleError("Catalog Shadow Form selectable_source_ids is invalid.")
            selectable.extend(
                _validate_identifier("selectable_source_id", item) for item in source_ids
            )
    return tuple(sorted(set(selectable)))


def _record_shadow_form_selection_effect(
    *,
    context: BattleRoundStartResultContext,
    player_id: str,
    source_unit_instance_id: str,
    shadow_form_record: AbilityCatalogRecord,
    shadow_form_rule_ir: RuleIR,
    selected_record: AbilityCatalogRecord,
    selected_rule_ir: RuleIR,
    selected_option_id: str,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=f"catalog-shadow-form-selection:{context.result.result_id}",
        source_rule_id=shadow_form_rule_ir.source_id,
        owner_player_id=player_id,
        target_unit_instance_ids=(source_unit_instance_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=EffectExpiration.end_battle_round(battle_round=context.state.battle_round),
        effect_payload=validate_json_value(
            {
                "effect_kind": CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND,
                "hook_id": CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
                "source_rule_id": shadow_form_rule_ir.source_id,
                "source_rule_ir_hash": shadow_form_rule_ir.ir_hash(),
                "source_catalog_record_id": shadow_form_record.record_id,
                "selected_shadow_form_source_id": selected_rule_ir.source_id,
                "selected_shadow_form_rule_ir_hash": selected_rule_ir.ir_hash(),
                "selected_catalog_record_id": selected_record.record_id,
                "selected_option_id": selected_option_id,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
            }
        ),
    )


def _persist_shadow_form_execution_effects(
    *,
    context: BattleRoundStartResultContext,
    player_id: str,
    selection_effect_id: str,
    rule_ir: RuleIR,
    rule_context: RuleExecutionContext,
    effect_payloads: tuple[dict[str, JsonValue], ...],
) -> tuple[PersistingEffect, ...]:
    clauses_by_id = {clause.clause_id: clause for clause in rule_ir.clauses}
    created: list[PersistingEffect] = []
    for index, effect_payload in enumerate(effect_payloads):
        target_unit_ids = _payload_identifier_tuple(effect_payload, key="target_unit_instance_ids")
        if not target_unit_ids:
            continue
        clause_id = _payload_string(effect_payload, key="clause_id")
        clause = clauses_by_id.get(clause_id)
        if clause is None:
            raise GameLifecycleError("Catalog Shadow Form execution payload clause is unknown.")
        expiration = _expiration_for_clause(clause=clause, rule_context=rule_context)
        if expiration is None:
            continue
        effect = PersistingEffect(
            effect_id=f"{selection_effect_id}:effect:{index:03d}",
            source_rule_id=rule_ir.source_id,
            owner_player_id=player_id,
            target_unit_instance_ids=target_unit_ids,
            started_battle_round=context.state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=expiration,
            effect_payload=validate_json_value(effect_payload),
        )
        context.state.record_persisting_effect(effect)
        created.append(effect)
    return tuple(created)


def _expiration_for_clause(
    *,
    clause: RuleClause,
    rule_context: RuleExecutionContext,
) -> EffectExpiration | None:
    if clause.duration is None:
        return None
    return expiration_for_duration(duration=clause.duration, context=rule_context)


def _rule_ir_from_record(record: AbilityCatalogRecord) -> RuleIR:
    try:
        return rule_ir_from_execution_payload(record.definition.replay_payload)
    except RuleIRError as exc:
        raise GameLifecycleError("Catalog Shadow Form record RuleIR is invalid.") from exc


def _shadow_form_selection_exists(
    *,
    state: object,
    source_unit_instance_id: str,
    battle_round: int,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog Shadow Form selection lookup requires GameState.")
    for effect in state.persisting_effects_for_unit(source_unit_instance_id):
        if effect.started_battle_round != battle_round:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND:
            return True
    return False


def _has_shadow_form_choice_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _shadow_form_selectable_source_ids(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.records_for(TimingTriggerKind.START_BATTLE_ROUND)
    )


def _army_and_unit_for_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> tuple[ArmyDefinition, UnitInstance]:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return army, unit
    raise GameLifecycleError("Catalog Shadow Form source unit is unknown.")


def _ability_index_for_player(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    *,
    player_id: str,
) -> AbilityCatalogIndex:
    requested_player_id = _validate_identifier("player_id", player_id)
    index = ability_indexes_by_player_id.get(requested_player_id)
    if index is None:
        raise GameLifecycleError("Catalog Shadow Form runtime missing player ability index.")
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Catalog Shadow Form runtime has invalid player ability index.")
    return index


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog Shadow Form payload must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog Shadow Form payload requires string {key}.")
    return _validate_identifier(key, value)


def _payload_identifier_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise GameLifecycleError(f"Catalog Shadow Form payload requires list {key}.")
    return tuple(_validate_identifier(key, value) for value in values)


def _hash_for_option(source_id: str) -> str:
    canonical = json.dumps(source_id, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()[:16]


_validate_identifier = IdentifierValidator(GameLifecycleError)
