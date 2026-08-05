from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    current_source_model_ids,
    source_applies_to_rules_unit,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID,
    CATALOG_IR_FIGHT_SELECTED_CRITICAL_WOUND_CONSUMER_ID,
    clause_is_fight_end_failed_activation_model_destruction,
    clause_is_fight_selected_critical_wound_threshold,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.damage_allocation import model_owner_player_id
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpirationKind,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.fight_phase_end_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    FightPhaseEndHookBinding,
    FightPhaseEndRequestContext,
    FightPhaseEndResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_model_destruction import (
    destroy_model_with_rule_reactions,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_SUBMISSION_KIND = "select_failed_fight_activation_model_destruction"
_MODEL_DESTROYED_EVENT = "model_destroyed"
_RESOLVED_EVENT = "catalog_failed_fight_activation_model_destroyed"


@dataclass(frozen=True, slots=True)
class _FightEndCandidate:
    owner_player_id: str
    rules_unit_instance_id: str
    record: AbilityCatalogRecord
    rule_ir: RuleIR
    activation_clause: RuleClause
    destruction_clause: RuleClause
    persisting_effects: tuple[PersistingEffect, ...]


@dataclass(frozen=True, slots=True)
class CatalogSelectedToFightRiskRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if set(indexes) != {army.player_id for army in armies}:
            raise GameLifecycleError("Selected-to-fight risk indexes must match armies.")
        object.__setattr__(self, "ability_indexes_by_player_id", indexes)
        object.__setattr__(self, "armies", armies)

    def fight_unit_selected_grant_bindings(
        self,
    ) -> tuple[FightUnitSelectedGrantBinding, ...]:
        return tuple(
            FightUnitSelectedGrantBinding(
                hook_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._grant_handler(source),
            )
            for source in self._activation_sources()
        )

    def fight_phase_end_hook_bindings(self) -> tuple[FightPhaseEndHookBinding, ...]:
        if not any(self._records_with_risk()):
            return ()
        return (
            FightPhaseEndHookBinding(
                hook_id=CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID,
                source_id=CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID,
                request_handler=self.next_fight_phase_end_request,
                result_handler=self.apply_fight_phase_end_result,
            ),
        )

    def next_fight_phase_end_request(
        self,
        context: FightPhaseEndRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not FightPhaseEndRequestContext:
            raise GameLifecycleError("Selected-to-fight risk requires Fight-end request context.")
        candidates = self._failed_candidates(
            state=context.state,
            records=context.decisions.event_log.records,
        )
        if not candidates:
            return None
        candidate = candidates[0]
        alive_model_ids = tuple(
            sorted(
                model.model_instance_id
                for model in rules_unit_view_by_id(
                    state=context.state,
                    unit_instance_id=candidate.rules_unit_instance_id,
                ).alive_models()
            )
        )
        if not alive_model_ids:
            return None
        active_player_id = _active_player_id(context.state)
        base_payload = {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "player_id": candidate.owner_player_id,
            "submission_kind": _SUBMISSION_KIND,
            "hook_id": CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID,
            "source_rule_id": candidate.rule_ir.source_id,
            "rule_ir_hash": candidate.rule_ir.ir_hash(),
            "activation_clause_id": candidate.activation_clause.clause_id,
            "destruction_clause_id": candidate.destruction_clause.clause_id,
            "persisting_effect_ids": [effect.effect_id for effect in candidate.persisting_effects],
            "rules_unit_instance_id": candidate.rules_unit_instance_id,
        }
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
            actor_id=candidate.owner_player_id,
            payload=validate_json_value(
                {
                    **base_payload,
                    "eligible_model_instance_ids": list(alive_model_ids),
                }
            ),
            options=tuple(
                DecisionOption(
                    option_id=f"destroy-model:{model_id}",
                    label=f"Destroy model {model_id}",
                    payload=validate_json_value(
                        {
                            **base_payload,
                            "selected_model_instance_id": model_id,
                        }
                    ),
                )
                for model_id in alive_model_ids
            ),
        )

    def apply_fight_phase_end_result(
        self,
        context: FightPhaseEndResultContext,
    ) -> bool | LifecycleStatus:
        if type(context) is not FightPhaseEndResultContext:
            raise GameLifecycleError("Selected-to-fight risk requires Fight-end result context.")
        request_payload = _object_payload(context.request.payload, "request")
        if request_payload.get("hook_id") != (
            CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID
        ):
            return False
        result_payload = _object_payload(context.result.payload, "result")
        effect_ids = _payload_string_tuple(result_payload, "persisting_effect_ids")
        candidate = next(
            (
                item
                for item in self._failed_candidates(
                    state=context.state,
                    records=context.decisions.event_log.records,
                )
                if tuple(effect.effect_id for effect in item.persisting_effects) == effect_ids
            ),
            None,
        )
        if candidate is None:
            return _invalid_result(context, "selected_to_fight_risk_source_drift")
        if _payload_string(result_payload, "source_rule_id") != candidate.rule_ir.source_id:
            return _invalid_result(context, "selected_to_fight_risk_rule_drift")
        if _payload_string(result_payload, "rule_ir_hash") != candidate.rule_ir.ir_hash():
            return _invalid_result(context, "selected_to_fight_risk_ir_hash_drift")
        rules_unit_id = _payload_string(result_payload, "rules_unit_instance_id")
        if rules_unit_id != candidate.rules_unit_instance_id:
            return _invalid_result(context, "selected_to_fight_risk_unit_drift")
        model_id = _payload_string(result_payload, "selected_model_instance_id")
        eligible_model_ids = _payload_string_tuple(
            request_payload,
            "eligible_model_instance_ids",
        )
        if model_id not in eligible_model_ids:
            return _invalid_result(context, "selected_to_fight_risk_model_snapshot_drift")
        current_model_ids = {
            model.model_instance_id
            for model in rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=rules_unit_id,
            ).alive_models()
        }
        if model_id not in current_model_ids:
            return _invalid_result(context, "selected_to_fight_risk_model_state_drift")

        destruction = destroy_model_with_rule_reactions(
            state=context.state,
            decisions=context.decisions,
            model_instance_id=model_id,
            rules_unit_instance_id=rules_unit_id,
            destroying_player_id=candidate.owner_player_id,
            source_rule_id=candidate.rule_ir.source_id,
            source_effect_ids=effect_ids,
            source_phase=BattlePhase.FIGHT,
            source_step="fight_phase_end",
            source_result_id=context.result.result_id,
            completion_event_type=_RESOLVED_EVENT,
            completion_event_payload=validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": _active_player_id(context.state),
                    "phase": BattlePhase.FIGHT.value,
                    "player_id": candidate.owner_player_id,
                    "source_rule_id": candidate.rule_ir.source_id,
                    "rule_ir_hash": candidate.rule_ir.ir_hash(),
                    "activation_clause_id": candidate.activation_clause.clause_id,
                    "destruction_clause_id": candidate.destruction_clause.clause_id,
                    "persisting_effect_ids": list(effect_ids),
                    "rules_unit_instance_id": rules_unit_id,
                    "destroyed_model_instance_id": model_id,
                    "request_id": context.request.request_id,
                    "result_id": context.result.result_id,
                }
            ),
        )
        return True if destruction.status is None else destruction.status

    def _grant_handler(
        self,
        source: CatalogDatasheetClauseSource,
    ) -> Callable[[FightUnitSelectedContext], FightUnitSelectedGrant | None]:
        effect = source.clause.effects[0]

        def handler(context: FightUnitSelectedContext) -> FightUnitSelectedGrant | None:
            if context.player_id != source.player_id or not source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.unit_instance_id,
                state=context.state,
            ):
                return None
            source_model_ids = current_source_model_ids(state=context.state, source=source)
            if not source_model_ids:
                raise GameLifecycleError("Selected-to-fight risk source has no alive model.")
            execution_context = RuleExecutionContext(
                game_id=context.state.game_id,
                player_id=source.player_id,
                battle_round=context.state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                active_player_id=context.state.active_player_id,
                timing_window_id="selected_to_fight",
                source_unit_instance_id=context.unit_instance_id,
                source_model_instance_id=source_model_ids[0],
                target_unit_instance_ids=(context.unit_instance_id,),
                source_keywords=tuple(
                    sorted((*source.unit.keywords, *source.unit.faction_keywords))
                ),
                trigger_payload={
                    "catalog_record_id": source.record.record_id,
                    "consumer_id": CATALOG_IR_FIGHT_SELECTED_CRITICAL_WOUND_CONSUMER_ID,
                    "activation_request_id": context.request_id,
                    "activation_result_id": context.result_id,
                },
                state=context.state,
                event_log=None,
                record_persisting_effects=False,
            )
            return FightUnitSelectedGrant(
                hook_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                label=source.record.definition.name,
                replay_payload={
                    "catalog_record_id": source.record.record_id,
                    "clause_id": source.clause.clause_id,
                    "rule_ir_hash": source.rule_ir.ir_hash(),
                },
                unit_effect_payload=generic_rule_effect_payload(
                    rule_ir=source.rule_ir,
                    clause=source.clause,
                    effect=effect,
                    context=execution_context,
                    target_unit_instance_ids=(context.unit_instance_id,),
                ),
                unit_effect_expiration="end_phase",
                decline_allowed=True,
            )

        return handler

    def _activation_sources(self) -> tuple[CatalogDatasheetClauseSource, ...]:
        sources: list[CatalogDatasheetClauseSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                clauses = tuple(
                    clause
                    for clause in catalog_rule_clauses_from_record(record)
                    if clause_is_fight_selected_critical_wound_threshold(clause)
                )
                if not clauses:
                    continue
                for unit in army.units:
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=unit.own_model_ids(),
                    ):
                        continue
                    sources.extend(
                        CatalogDatasheetClauseSource(
                            player_id=army.player_id,
                            record=record,
                            unit=unit,
                            clause=clause,
                            rule_ir=rule_ir,
                        )
                        for clause in clauses
                    )
        return tuple(sorted(sources, key=lambda source: source.binding_id))

    def _records_with_risk(
        self,
    ) -> tuple[tuple[str, AbilityCatalogRecord, RuleIR, RuleClause, RuleClause], ...]:
        records_by_source: dict[
            tuple[str, str, str],
            tuple[str, AbilityCatalogRecord, RuleIR, RuleClause, RuleClause],
        ] = {}
        for player_id, index in self.ability_indexes_by_player_id.items():
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                activation_clauses = tuple(
                    clause
                    for clause in rule_ir.clauses
                    if clause_is_fight_selected_critical_wound_threshold(clause)
                )
                destruction_clauses = tuple(
                    clause
                    for clause in rule_ir.clauses
                    if clause_is_fight_end_failed_activation_model_destruction(clause)
                )
                if not activation_clauses and not destruction_clauses:
                    continue
                if len(activation_clauses) != 1 or len(destruction_clauses) != 1:
                    raise GameLifecycleError(
                        "Selected-to-fight risk requires one activation and consequence clause."
                    )
                key = (player_id, rule_ir.source_id, rule_ir.ir_hash())
                existing = records_by_source.get(key)
                candidate = (
                    player_id,
                    record,
                    rule_ir,
                    activation_clauses[0],
                    destruction_clauses[0],
                )
                if existing is None or record.record_id < existing[1].record_id:
                    records_by_source[key] = candidate
        return tuple(
            sorted(records_by_source.values(), key=lambda item: (item[0], item[1].record_id))
        )

    def _failed_candidates(
        self,
        *,
        state: GameState,
        records: tuple[EventRecord, ...],
    ) -> tuple[_FightEndCandidate, ...]:
        candidates_by_key: dict[
            tuple[str, str, str, str],
            tuple[
                str,
                str,
                AbilityCatalogRecord,
                RuleIR,
                RuleClause,
                RuleClause,
                list[PersistingEffect],
            ],
        ] = {}
        record_rows = self._records_with_risk()
        for effect in state.persisting_effects:
            for owner_id, record, rule_ir, activation_clause, destruction_clause in record_rows:
                if not _effect_matches_activation(
                    state=state,
                    effect=effect,
                    owner_player_id=owner_id,
                    rule_ir=rule_ir,
                    activation_clause=activation_clause,
                ):
                    continue
                for unit_id in effect.target_unit_instance_ids:
                    key = (owner_id, rule_ir.source_id, rule_ir.ir_hash(), unit_id)
                    existing = candidates_by_key.get(key)
                    if existing is None:
                        candidates_by_key[key] = (
                            owner_id,
                            unit_id,
                            record,
                            rule_ir,
                            activation_clause,
                            destruction_clause,
                            [effect],
                        )
                        continue
                    existing[6].append(effect)
        candidates: list[_FightEndCandidate] = []
        for (
            owner_id,
            unit_id,
            record,
            rule_ir,
            activation_clause,
            destruction_clause,
            effects,
        ) in candidates_by_key.values():
            effect_tuple = tuple(sorted(effects, key=lambda item: item.effect_id))
            if _enemy_model_was_destroyed_by_unit_attacks(
                state=state,
                records=records,
                owner_player_id=owner_id,
                rules_unit_instance_id=unit_id,
                persisting_effects=effect_tuple,
            ):
                continue
            candidates.append(
                _FightEndCandidate(
                    owner_player_id=owner_id,
                    rules_unit_instance_id=unit_id,
                    record=record,
                    rule_ir=rule_ir,
                    activation_clause=activation_clause,
                    destruction_clause=destruction_clause,
                    persisting_effects=effect_tuple,
                )
            )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.owner_player_id,
                    item.rules_unit_instance_id,
                    tuple(effect.effect_id for effect in item.persisting_effects),
                ),
            )
        )


def _effect_matches_activation(
    *,
    state: GameState,
    effect: PersistingEffect,
    owner_player_id: str,
    rule_ir: RuleIR,
    activation_clause: RuleClause,
) -> bool:
    if (
        effect.source_rule_id != rule_ir.source_id
        or effect.owner_player_id != owner_player_id
        or effect.started_battle_round != state.battle_round
        or effect.started_phase is not BattlePhaseKind.FIGHT
        or effect.expiration.expiration_kind is not EffectExpirationKind.END_PHASE
        or effect.expiration.battle_round != state.battle_round
        or effect.expiration.phase is not BattlePhaseKind.FIGHT
        or effect.expiration.player_id != _active_player_id(state)
    ):
        return False
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("effect_kind") == GENERIC_RULE_EFFECT_KIND
        and payload.get("source_id") == rule_ir.source_id
        and payload.get("rule_ir_hash") == rule_ir.ir_hash()
        and payload.get("clause_id") == activation_clause.clause_id
        and payload.get("effect") == activation_clause.effects[0].to_payload()
    )


def _enemy_model_was_destroyed_by_unit_attacks(
    *,
    state: GameState,
    records: tuple[EventRecord, ...],
    owner_player_id: str,
    rules_unit_instance_id: str,
    persisting_effects: tuple[PersistingEffect, ...],
) -> bool:
    attack_lineage = _liability_attack_lineage(
        state=state,
        rules_unit_instance_id=rules_unit_instance_id,
        persisting_effects=persisting_effects,
    )
    for event in records:
        if event.event_type != _MODEL_DESTROYED_EVENT:
            continue
        payload = _object_payload(event.payload, "model_destroyed event")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("battle_round") != state.battle_round
            or payload.get("phase") != BattlePhase.FIGHT.value
            or payload.get("active_player_id") != _active_player_id(state)
            or payload.get("destroying_player_id") != owner_player_id
        ):
            continue
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
        if attribution.destruction_provenance.destruction_source_kind is not (
            DestructionSourceKind.ATTACK
        ):
            continue
        attacking_unit_id = attribution.attacking_unit_instance_id
        attacking_model_id = attribution.attacking_model_instance_id
        target_unit_id = payload.get("target_unit_instance_id")
        destroyed_model_id = payload.get("model_instance_id")
        if type(attacking_unit_id) is not str or type(attacking_model_id) is not str:
            continue
        allowed_model_ids = attack_lineage.get(attacking_unit_id)
        if allowed_model_ids is None or attacking_model_id not in allowed_model_ids:
            continue
        if type(target_unit_id) is not str:
            raise GameLifecycleError("Attack model_destroyed event target unit is invalid.")
        if type(destroyed_model_id) is not str:
            raise GameLifecycleError("Attack model_destroyed event model is invalid.")
        if (
            model_owner_player_id(
                state=state,
                model_instance_id=destroyed_model_id,
            )
            != owner_player_id
        ):
            return True
    return False


def _liability_attack_lineage(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    persisting_effects: tuple[PersistingEffect, ...],
) -> dict[str, frozenset[str]]:
    current_component_ids = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    ).component_unit_instance_ids
    lineage = {
        rules_unit_instance_id: _model_ids_for_units(
            state=state,
            unit_instance_ids=current_component_ids,
        )
    }
    for effect in persisting_effects:
        for origin_id in _effect_original_target_ids(effect):
            starting_record = next(
                (
                    record
                    for record in state.starting_attached_unit_records
                    if record.attached_unit_instance_id == origin_id
                ),
                None,
            )
            origin_component_ids = (
                starting_record.component_unit_instance_ids
                if starting_record is not None
                else rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=origin_id,
                ).component_unit_instance_ids
            )
            lineage[origin_id] = _model_ids_for_units(
                state=state,
                unit_instance_ids=origin_component_ids,
            )
    return lineage


def _model_ids_for_units(
    *,
    state: GameState,
    unit_instance_ids: tuple[str, ...],
) -> frozenset[str]:
    requested_ids = set(unit_instance_ids)
    return frozenset(
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id in requested_ids
        for model in unit.own_models
    )


def _effect_original_target_ids(effect: PersistingEffect) -> tuple[str, ...]:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Selected-to-fight risk effect payload must be an object.")
    target_ids = payload.get("target_unit_instance_ids")
    if not isinstance(target_ids, list) or not all(
        type(unit_id) is str and unit_id for unit_id in target_ids
    ):
        raise GameLifecycleError("Selected-to-fight risk original targets are invalid.")
    return tuple(cast(list[str], target_ids))


def catalog_selected_to_fight_risk_end_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[FightPhaseEndHookBinding, ...]:
    return CatalogSelectedToFightRiskRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).fight_phase_end_hook_bindings()


def _invalid_result(context: FightPhaseEndResultContext, reason: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=context.state.stage,
        message="Selected-to-fight risk decision context drifted.",
        payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "invalid_reason": reason,
            }
        ),
    )


def _object_payload(payload: JsonValue, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"Selected-to-fight risk {field_name} payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Selected-to-fight risk {key} must be a string.")
    return value


def _payload_string_tuple(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list) or not all(type(value) is str and value for value in values):
        raise GameLifecycleError(f"Selected-to-fight risk {key} must be a string list.")
    return tuple(cast(list[str], values))


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Selected-to-fight risk requires active player.")
    return state.active_player_id


def _validate_ability_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Selected-to-fight risk indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or not player_id.strip() or player_id != player_id.strip():
            raise GameLifecycleError("Selected-to-fight risk player ID is invalid.")
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Selected-to-fight risk ability index is invalid.")
        indexes[player_id] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Selected-to-fight risk armies must be a tuple.")
    armies = cast(tuple[object, ...], value)
    if not all(type(army) is ArmyDefinition for army in armies):
        raise GameLifecycleError("Selected-to-fight risk armies contain invalid values.")
    typed = cast(tuple[ArmyDefinition, ...], armies)
    if len({army.player_id for army in typed}) != len(typed):
        raise GameLifecycleError("Selected-to-fight risk armies duplicate players.")
    return tuple(sorted(typed, key=lambda army: army.player_id))
