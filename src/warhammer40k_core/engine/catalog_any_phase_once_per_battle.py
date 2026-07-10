from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_once_per_battle_support import (
    clause_is_any_phase_start_once_per_battle_activation,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    LifecycleStatus,
)
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_frequency import (
    optional_ability_frequency_unavailable_reason,
    optional_ability_frequency_usage_key,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR, RuleIRPayload

SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE = (
    "select_catalog_any_phase_once_per_battle_ability"
)
CATALOG_ANY_PHASE_ONCE_PER_BATTLE_SUBMISSION_KIND = "catalog_any_phase_once_per_battle_ability"
CATALOG_ANY_PHASE_ONCE_PER_BATTLE_ACTIVATED_EVENT = (
    "catalog_any_phase_once_per_battle_ability_activated"
)
CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECLINED_EVENT = (
    "catalog_any_phase_once_per_battle_ability_declined"
)


@dataclass(frozen=True, slots=True)
class _AnyPhaseSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    model_instance_id: str
    clause: RuleClause
    rule_ir: RuleIR

    @property
    def binding_id(self) -> str:
        return (
            f"catalog-ir:any-phase-once:{self.player_id}:{self.unit.unit_instance_id}:"
            f"{self.model_instance_id}:{self.clause.clause_id}"
        )

    @property
    def handler_id(self) -> str:
        return f"{self.binding_id}:handler"

    @property
    def subscription_id(self) -> str:
        return f"{self.binding_id}:subscription"

    def subscription(self) -> RuntimeContentEventSubscription:
        return RuntimeContentEventSubscription(
            subscription_id=self.subscription_id,
            source_rule_id=self.rule_ir.source_id,
            trigger_kind=TimingTriggerKind.START_PHASE,
            handler_id=self.handler_id,
            filters=MappingProxyType({"player_id": self.player_id}),
        )


@dataclass(frozen=True, slots=True)
class CatalogAnyPhaseOncePerBattleRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if set(indexes) != {army.player_id for army in armies}:
            raise GameLifecycleError("Catalog any-phase runtime indexes must match armies.")
        object.__setattr__(self, "ability_indexes_by_player_id", indexes)
        object.__setattr__(self, "armies", armies)

    def event_handler_bindings(self) -> tuple[RuntimeContentEventHandlerBinding, ...]:
        return tuple(
            RuntimeContentEventHandlerBinding(
                handler_id=source.handler_id,
                handler=self._event_handler(source),
            )
            for source in self._sources()
        )

    def event_subscriptions(self) -> tuple[RuntimeContentEventSubscription, ...]:
        return tuple(source.subscription() for source in self._sources())

    def _event_handler(
        self, source: _AnyPhaseSource
    ) -> Callable[[RuntimeContentEventContext], RuntimeContentEventResult]:
        def handler(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
            if type(context) is not RuntimeContentEventContext:
                raise GameLifecycleError("Catalog any-phase event requires context.")
            subscription = source.subscription()
            if context.event.phase is None:
                return RuntimeContentEventResult.invalid(
                    subscription,
                    reason="missing_phase",
                )
            if source.model_instance_id not in _current_source_model_ids(
                state=context.state, source=source
            ):
                return RuntimeContentEventResult.applied(
                    subscription,
                    replay_payload={"available": False, "reason": "source_model_unavailable"},
                )
            unavailable = optional_ability_frequency_unavailable_reason(
                rule_ir=source.rule_ir,
                clause=source.clause,
                event_log=context.decisions.event_log,
                player_id=source.player_id,
                source_unit_instance_id=source.unit.unit_instance_id,
                source_model_instance_id=source.model_instance_id,
            )
            if unavailable == "frequency_limit_exhausted:battle":
                return RuntimeContentEventResult.applied(
                    subscription,
                    replay_payload={"available": False, "reason": unavailable},
                )
            if unavailable is not None:
                raise GameLifecycleError(
                    f"Catalog any-phase frequency lookup failed: {unavailable}."
                )
            request = _activation_request(context=context, source=source)
            context.decisions.request_decision(request)
            return RuntimeContentEventResult.applied(
                subscription,
                replay_payload={"available": True, "request_id": request.request_id},
            )

        return handler

    def _sources(self) -> tuple[_AnyPhaseSource, ...]:
        sources: list[_AnyPhaseSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.records_for(TimingTriggerKind.START_PHASE):
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                for clause in catalog_rule_clauses_from_record(record):
                    if not clause_is_any_phase_start_once_per_battle_activation(clause):
                        continue
                    for unit in army.units:
                        model_ids = unit.own_model_ids()
                        if not catalog_rule_record_source_matches_unit(
                            record=record,
                            unit=unit,
                            current_model_instance_ids=model_ids,
                        ):
                            continue
                        sources.extend(
                            _AnyPhaseSource(
                                player_id=army.player_id,
                                record=record,
                                unit=unit,
                                model_instance_id=model_id,
                                clause=clause,
                                rule_ir=replace(
                                    rule_ir,
                                    clauses=(clause,),
                                    diagnostics=clause.diagnostics,
                                ),
                            )
                            for model_id in model_ids
                        )
        return tuple(sorted(sources, key=lambda source: source.binding_id))


def invalid_any_phase_once_per_battle_status(
    *,
    state: object,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog any-phase validation requires GameState.")
    field = _finite_result_invalid_field(request=request, result=result)
    if field is None:
        field = _request_context_invalid_field(state=state, decisions=decisions, request=request)
    if field is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog any-phase once-per-battle activation is invalid.",
        payload={
            "invalid_reason": "invalid_catalog_any_phase_once_per_battle_result",
            "field": field,
        },
    )


def apply_any_phase_once_per_battle_result(
    *,
    state: object,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.current_battle_phase is None:
        raise GameLifecycleError("Catalog any-phase activation requires battle phase state.")
    if (
        invalid_any_phase_once_per_battle_status(
            state=state, decisions=decisions, request=request, result=result
        )
        is not None
    ):
        raise GameLifecycleError("Catalog any-phase activation was not prevalidated.")
    payload = _payload_object(result.payload)
    request_payload = _payload_object(request.payload)
    activate = payload.get("activate")
    if type(activate) is not bool:
        raise GameLifecycleError("Catalog any-phase activate must be boolean.")
    rule_ir = _rule_ir_from_request(request_payload)
    if not activate:
        decisions.event_log.append(
            CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECLINED_EVENT,
            {
                **_base_payload_from_request(request_payload),
                "request_id": request.request_id,
                "result_id": result.result_id,
            },
        )
        return
    source_unit_id = _payload_string(request_payload, "source_unit_instance_id")
    source_model_id = _payload_string(request_payload, "source_model_instance_id")
    source_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=source_unit_id)
    execution = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id=_payload_string(request_payload, "player_id"),
            battle_round=state.battle_round,
            phase=battle_phase_kind_from_token(state.current_battle_phase.value),
            active_player_id=state.active_player_id,
            timing_window_id=_payload_string(request_payload, "runtime_event_id"),
            source_unit_instance_id=source_rules_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            target_unit_instance_ids=(source_rules_unit.unit_instance_id,),
            source_keywords=tuple(
                sorted((*source_rules_unit.keywords, *source_rules_unit.faction_keywords))
            ),
            trigger_payload={
                "catalog_record_id": _payload_string(request_payload, "catalog_record_id"),
                "request_id": request.request_id,
                "result_id": result.result_id,
                "submission_kind": CATALOG_ANY_PHASE_ONCE_PER_BATTLE_SUBMISSION_KIND,
                "usage_key": _payload_string(request_payload, "usage_key"),
            },
            state=state,
            event_log=decisions.event_log,
        ),
    )
    if execution.status is not RuleExecutionStatus.APPLIED:
        raise GameLifecycleError(
            "Catalog any-phase RuleIR execution failed: "
            + ("unknown" if execution.reason is None else execution.reason)
        )
    decisions.event_log.append(
        CATALOG_ANY_PHASE_ONCE_PER_BATTLE_ACTIVATED_EVENT,
        {
            **_base_payload_from_request(request_payload),
            "request_id": request.request_id,
            "result_id": result.result_id,
            "rule_execution": execution.to_payload(),
        },
    )


def _activation_request(
    *, context: RuntimeContentEventContext, source: _AnyPhaseSource
) -> DecisionRequest:
    base = _base_payload(context=context, source=source)
    decline_id = f"{source.binding_id}:decline"
    use_id = f"{source.binding_id}:use"
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
        actor_id=source.player_id,
        payload={**base, "available_option_ids": [decline_id, use_id]},
        options=(
            DecisionOption(
                option_id=decline_id,
                label=f"Do not use {source.record.definition.name}",
                payload={**base, "activate": False},
            ),
            DecisionOption(
                option_id=use_id,
                label=f"Use {source.record.definition.name}",
                payload={**base, "activate": True},
            ),
        ),
    )


def _base_payload(
    *, context: RuntimeContentEventContext, source: _AnyPhaseSource
) -> dict[str, JsonValue]:
    if context.event.phase is None:
        raise GameLifecycleError("Catalog any-phase payload requires phase.")
    usage_key = optional_ability_frequency_usage_key(
        rule_ir=source.rule_ir,
        clause=source.clause,
        player_id=source.player_id,
        source_unit_instance_id=source.unit.unit_instance_id,
        source_model_instance_id=source.model_instance_id,
    )
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "submission_kind": CATALOG_ANY_PHASE_ONCE_PER_BATTLE_SUBMISSION_KIND,
                "consumer_id": CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.event.phase.value,
                "active_player_id": context.state.active_player_id,
                "player_id": source.player_id,
                "catalog_record_id": source.record.record_id,
                "ability_id": source.record.definition.ability_id,
                "source_rule_id": source.rule_ir.source_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "clause_id": source.clause.clause_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source.model_instance_id,
                "usage_key": usage_key,
                "runtime_event_id": context.event.event_id,
                "rule_ir": source.rule_ir.to_payload(),
            }
        ),
    )


def _finite_result_invalid_field(*, request: DecisionRequest, result: DecisionResult) -> str | None:
    if result.request_id != request.request_id:
        return "request_id"
    if result.decision_type != request.decision_type:
        return "decision_type"
    if result.actor_id != request.actor_id:
        return "actor_id"
    option = next(
        (option for option in request.options if option.option_id == result.selected_option_id),
        None,
    )
    if option is None:
        return "selected_option_id"
    if result.payload != option.payload:
        return "payload"
    return None


def _request_context_invalid_field(
    *, state: object, decisions: DecisionController, request: DecisionRequest
) -> str | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog any-phase validation requires GameState.")
    payload = _payload_object(request.payload)
    expected = (
        ("game_id", state.game_id),
        ("battle_round", state.battle_round),
        ("phase", None if state.current_battle_phase is None else state.current_battle_phase.value),
        ("active_player_id", state.active_player_id),
        ("player_id", request.actor_id),
    )
    for field, value in expected:
        if payload.get(field) != value:
            return field
    rule_ir = _rule_ir_from_request(payload)
    if payload.get("rule_ir_hash") != rule_ir.ir_hash():
        return "rule_ir_hash"
    source_unit_id = _payload_string(payload, "source_unit_instance_id")
    model_id = _payload_string(payload, "source_model_instance_id")
    source_unit = next(
        (
            unit
            for army in state.army_definitions
            if army.player_id == request.actor_id
            for unit in army.units
            if unit.unit_instance_id == source_unit_id
        ),
        None,
    )
    if source_unit is None or model_id not in _current_model_ids(state=state, unit=source_unit):
        return "source_model_instance_id"
    unavailable = optional_ability_frequency_unavailable_reason(
        rule_ir=rule_ir,
        clause=rule_ir.clauses[0],
        event_log=decisions.event_log,
        player_id=_payload_string(payload, "player_id"),
        source_unit_instance_id=source_unit_id,
        source_model_instance_id=model_id,
    )
    return None if unavailable is None else "frequency_limit"


def _rule_ir_from_request(payload: dict[str, JsonValue]) -> RuleIR:
    raw = payload.get("rule_ir")
    if not isinstance(raw, dict):
        raise GameLifecycleError("Catalog any-phase request requires RuleIR payload.")
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, raw))
    if len(rule_ir.clauses) != 1 or not clause_is_any_phase_start_once_per_battle_activation(
        rule_ir.clauses[0]
    ):
        raise GameLifecycleError("Catalog any-phase request RuleIR shape drifted.")
    return rule_ir


def _current_source_model_ids(*, state: object, source: _AnyPhaseSource) -> tuple[str, ...]:
    return _current_model_ids(state=state, unit=source.unit)


def _current_model_ids(*, state: object, unit: UnitInstance) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog any-phase source query requires GameState.")
    return catalog_rule_current_placed_alive_model_instance_ids_for_unit(state=state, unit=unit)


def _base_payload_from_request(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: value for key, value in payload.items() if key != "available_option_ids"}


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog any-phase payload must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog any-phase payload {key} must be non-empty string.")
    return value


def _validate_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog any-phase indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog any-phase index entry is invalid.")
        indexes[player_id] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog any-phase runtime requires ArmyDefinition tuple.")
    armies = cast(tuple[object, ...], value)
    if not all(type(army) is ArmyDefinition for army in armies):
        raise GameLifecycleError("Catalog any-phase runtime requires ArmyDefinition tuple.")
    return cast(tuple[ArmyDefinition, ...], armies)
