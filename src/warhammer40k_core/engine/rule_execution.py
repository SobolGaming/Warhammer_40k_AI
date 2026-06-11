from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointLedger,
    CommandPointSourceKind,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecord,
    EventRecordPayload,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransactionPayload,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleParameterValue,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

GENERIC_RULE_IR_ABILITY_HANDLER_ID = "generic:rule-ir"
GENERIC_RULE_IR_STRATAGEM_HANDLER_ID = "generic:rule-ir"
RULE_IR_AURA_TEMPLATE_ID = "phase17c:aura"

STATE_INPUT_GAME_STATE = "game_state"
STATE_INPUT_BATTLEFIELD_STATE = "battlefield_state"
STATE_INPUT_SOURCE_UNIT = "source_unit"
STATE_INPUT_EVENT_LOG = "event_log"
TARGET_BINDING_UNIT_IDS = "target_unit_instance_ids"
UNIT_EFFECT_TARGET_KINDS = (
    RuleTargetKind.ENEMY_UNIT,
    RuleTargetKind.FRIENDLY_UNIT,
    RuleTargetKind.SELECTED_TARGET,
    RuleTargetKind.SELECTED_UNIT,
    RuleTargetKind.THIS_UNIT,
)
TARGET_SCOPED_EFFECT_KINDS = (
    RuleEffectKind.GRANT_ABILITY,
    RuleEffectKind.GRANT_WEAPON_ABILITY,
    RuleEffectKind.MODIFY_CHARACTERISTIC,
    RuleEffectKind.MODIFY_DICE_ROLL,
    RuleEffectKind.MODIFY_MOVE_DISTANCE,
    RuleEffectKind.PLACEMENT_PERMISSION,
    RuleEffectKind.PLACEMENT_RESTRICTION,
    RuleEffectKind.REROLL_PERMISSION,
)
AURA_ALLEGIANCE_ANY = "any"
AURA_ALLEGIANCE_ENEMY = "enemy"
AURA_ALLEGIANCE_FRIENDLY = "friendly"


class RuleExecutionStatus(StrEnum):
    APPLIED = "applied"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class RuleExecutionContextPayload(TypedDict):
    game_id: str
    player_id: str
    battle_round: int
    phase: str | None
    active_player_id: str | None
    timing_window_id: str | None
    source_unit_instance_id: str | None
    source_model_instance_id: str | None
    target_unit_instance_ids: list[str]
    target_player_id: str | None
    source_keywords: list[str]
    trigger_payload: JsonValue


class RuleRuntimeBindingPayload(TypedDict):
    binding_id: str
    template_id: str | None
    effect_kinds: list[str]
    trigger_kind: str | None
    required_state_inputs: list[str]
    required_target_bindings: list[str]


class RuleExecutionResultPayload(TypedDict):
    rule_id: str
    source_id: str
    rule_ir_hash: str
    status: str
    reason: str | None
    applied_clause_ids: list[str]
    effect_payloads: list[dict[str, JsonValue]]
    target_bindings: list[dict[str, JsonValue]]
    aura_evaluations: list[dict[str, JsonValue]]
    victory_point_transactions: list[VictoryPointTransactionPayload]
    command_point_transactions: list[dict[str, JsonValue]]
    created_persisting_effects: list[dict[str, JsonValue]]
    event_records: list[EventRecordPayload]
    replay_payload: JsonValue


@dataclass(frozen=True, slots=True)
class RuleExecutionContext:
    game_id: str
    player_id: str
    battle_round: int
    phase: BattlePhaseKind | None
    active_player_id: str | None
    timing_window_id: str | None = None
    source_unit_instance_id: str | None = None
    source_model_instance_id: str | None = None
    target_unit_instance_ids: tuple[str, ...] = ()
    target_player_id: str | None = None
    source_keywords: tuple[str, ...] = ()
    trigger_payload: JsonValue = None
    state: GameState | None = None
    event_log: EventLog | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", _validate_optional_phase("phase", self.phase))
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier("timing_window_id", self.timing_window_id),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_optional_identifier("source_unit_instance_id", self.source_unit_instance_id),
        )
        object.__setattr__(
            self,
            "source_model_instance_id",
            _validate_optional_identifier(
                "source_model_instance_id", self.source_model_instance_id
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple(
                "target_unit_instance_ids",
                self.target_unit_instance_ids,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "target_player_id",
            _validate_optional_identifier("target_player_id", self.target_player_id),
        )
        object.__setattr__(
            self,
            "source_keywords",
            _validate_identifier_tuple(
                "source_keywords",
                self.source_keywords,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(self, "trigger_payload", validate_json_value(self.trigger_payload))
        if self.state is not None and type(self.state) is not GameState:
            raise GameLifecycleError("RuleExecutionContext state must be a GameState.")
        if self.event_log is not None and type(self.event_log) is not EventLog:
            raise GameLifecycleError("RuleExecutionContext event_log must be an EventLog.")

    def to_payload(self) -> RuleExecutionContextPayload:
        return {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": None if self.phase is None else self.phase.value,
            "active_player_id": self.active_player_id,
            "timing_window_id": self.timing_window_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "source_model_instance_id": self.source_model_instance_id,
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
            "target_player_id": self.target_player_id,
            "source_keywords": list(self.source_keywords),
            "trigger_payload": self.trigger_payload,
        }


RuleTemplateHandler = Callable[
    [RuleIR, RuleClause, RuleEffectSpec | None, RuleExecutionContext],
    "RuleExecutionResult",
]
RuleExecutionHandler = RuleTemplateHandler


@dataclass(frozen=True, slots=True)
class RuleRuntimeBinding:
    binding_id: str
    template_id: str | None
    effect_kinds: tuple[RuleEffectKind, ...]
    handler: RuleTemplateHandler
    trigger_kind: RuleTriggerKind | None = None
    required_state_inputs: tuple[str, ...] = ()
    required_target_bindings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "binding_id",
            _validate_identifier("RuleRuntimeBinding binding_id", self.binding_id),
        )
        object.__setattr__(
            self,
            "template_id",
            _validate_optional_identifier("RuleRuntimeBinding template_id", self.template_id),
        )
        object.__setattr__(
            self,
            "effect_kinds",
            _validate_effect_kind_tuple("RuleRuntimeBinding effect_kinds", self.effect_kinds),
        )
        if self.trigger_kind is not None and type(self.trigger_kind) is not RuleTriggerKind:
            raise GameLifecycleError("RuleRuntimeBinding trigger_kind must be RuleTriggerKind.")
        object.__setattr__(
            self,
            "required_state_inputs",
            _validate_identifier_tuple(
                "RuleRuntimeBinding required_state_inputs",
                self.required_state_inputs,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "required_target_bindings",
            _validate_identifier_tuple(
                "RuleRuntimeBinding required_target_bindings",
                self.required_target_bindings,
                min_length=0,
                sort_values=True,
            ),
        )
        if not callable(self.handler):
            raise GameLifecycleError("RuleRuntimeBinding handler must be callable.")
        if self.template_id is None and not self.effect_kinds and not self.required_target_bindings:
            raise GameLifecycleError("RuleRuntimeBinding requires a template, effect, or target.")

    def matches_clause(self, clause: RuleClause) -> bool:
        if type(clause) is not RuleClause:
            raise GameLifecycleError("RuleRuntimeBinding clause match requires a RuleClause.")
        if self.template_id is not None and clause.template_id != self.template_id:
            return False
        if self.trigger_kind is not None:
            return clause.trigger is not None and clause.trigger.kind is self.trigger_kind
        return True

    def matches_effect(self, clause: RuleClause, effect: RuleEffectSpec) -> bool:
        if type(effect) is not RuleEffectSpec:
            raise GameLifecycleError("RuleRuntimeBinding effect match requires RuleEffectSpec.")
        return self.matches_clause(clause) and effect.kind in self.effect_kinds

    def to_payload(self) -> RuleRuntimeBindingPayload:
        return {
            "binding_id": self.binding_id,
            "template_id": self.template_id,
            "effect_kinds": [kind.value for kind in self.effect_kinds],
            "trigger_kind": None if self.trigger_kind is None else self.trigger_kind.value,
            "required_state_inputs": list(self.required_state_inputs),
            "required_target_bindings": list(self.required_target_bindings),
        }


@dataclass(frozen=True, slots=True)
class RuleExecutionResult:
    rule_id: str
    source_id: str
    rule_ir_hash: str
    status: RuleExecutionStatus
    reason: str | None = None
    applied_clause_ids: tuple[str, ...] = ()
    effect_payloads: tuple[dict[str, JsonValue], ...] = ()
    target_bindings: tuple[dict[str, JsonValue], ...] = ()
    aura_evaluations: tuple[dict[str, JsonValue], ...] = ()
    victory_point_transactions: tuple[VictoryPointTransactionPayload, ...] = ()
    command_point_transactions: tuple[dict[str, JsonValue], ...] = ()
    created_persisting_effects: tuple[PersistingEffect, ...] = ()
    event_records: tuple[EventRecord, ...] = ()
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _validate_identifier("rule_id", self.rule_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "rule_ir_hash",
            _validate_identifier("rule_ir_hash", self.rule_ir_hash),
        )
        object.__setattr__(self, "status", rule_execution_status_from_token(self.status))
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("RuleExecutionResult reason", self.reason),
        )
        object.__setattr__(
            self,
            "applied_clause_ids",
            _validate_identifier_tuple(
                "RuleExecutionResult applied_clause_ids",
                self.applied_clause_ids,
                min_length=0,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "effect_payloads",
            _validate_json_object_tuple(
                "RuleExecutionResult effect_payloads",
                self.effect_payloads,
            ),
        )
        object.__setattr__(
            self,
            "target_bindings",
            _validate_json_object_tuple(
                "RuleExecutionResult target_bindings",
                self.target_bindings,
            ),
        )
        object.__setattr__(
            self,
            "aura_evaluations",
            _validate_json_object_tuple(
                "RuleExecutionResult aura_evaluations",
                self.aura_evaluations,
            ),
        )
        object.__setattr__(
            self,
            "command_point_transactions",
            _validate_json_object_tuple(
                "RuleExecutionResult command_point_transactions",
                self.command_point_transactions,
            ),
        )
        for transaction in self.victory_point_transactions:
            validate_json_value(transaction)
        for effect in self.created_persisting_effects:
            if type(effect) is not PersistingEffect:
                raise GameLifecycleError(
                    "RuleExecutionResult created_persisting_effects must contain effects."
                )
        for event in self.event_records:
            if type(event) is not EventRecord:
                raise GameLifecycleError("RuleExecutionResult event_records must contain events.")
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        if self.status is RuleExecutionStatus.APPLIED and self.reason is not None:
            raise GameLifecycleError("Applied RuleExecutionResult must not include reason.")
        if self.status is not RuleExecutionStatus.APPLIED and self.reason is None:
            raise GameLifecycleError("Non-applied RuleExecutionResult requires reason.")

    @classmethod
    def applied(
        cls,
        rule_ir: RuleIR,
        *,
        applied_clause_ids: tuple[str, ...] = (),
        effect_payloads: tuple[dict[str, JsonValue], ...] = (),
        target_bindings: tuple[dict[str, JsonValue], ...] = (),
        aura_evaluations: tuple[dict[str, JsonValue], ...] = (),
        victory_point_transactions: tuple[VictoryPointTransactionPayload, ...] = (),
        command_point_transactions: tuple[dict[str, JsonValue], ...] = (),
        created_persisting_effects: tuple[PersistingEffect, ...] = (),
        event_records: tuple[EventRecord, ...] = (),
        replay_payload: JsonValue = None,
    ) -> Self:
        _validate_rule_ir(rule_ir)
        return cls(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            applied_clause_ids=applied_clause_ids,
            effect_payloads=effect_payloads,
            target_bindings=target_bindings,
            aura_evaluations=aura_evaluations,
            victory_point_transactions=victory_point_transactions,
            command_point_transactions=command_point_transactions,
            created_persisting_effects=created_persisting_effects,
            event_records=event_records,
            replay_payload=replay_payload,
        )

    @classmethod
    def invalid(cls, rule_ir: RuleIR, *, reason: str, replay_payload: JsonValue = None) -> Self:
        _validate_rule_ir(rule_ir)
        return cls(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.INVALID,
            reason=reason,
            replay_payload=replay_payload,
        )

    @classmethod
    def unsupported(
        cls,
        rule_ir: RuleIR,
        *,
        reason: str,
        replay_payload: JsonValue = None,
    ) -> Self:
        _validate_rule_ir(rule_ir)
        return cls(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.UNSUPPORTED,
            reason=reason,
            replay_payload=replay_payload,
        )

    def to_payload(self) -> RuleExecutionResultPayload:
        return {
            "rule_id": self.rule_id,
            "source_id": self.source_id,
            "rule_ir_hash": self.rule_ir_hash,
            "status": self.status.value,
            "reason": self.reason,
            "applied_clause_ids": list(self.applied_clause_ids),
            "effect_payloads": list(self.effect_payloads),
            "target_bindings": list(self.target_bindings),
            "aura_evaluations": list(self.aura_evaluations),
            "victory_point_transactions": list(self.victory_point_transactions),
            "command_point_transactions": list(self.command_point_transactions),
            "created_persisting_effects": [
                _json_object(effect.to_payload()) for effect in self.created_persisting_effects
            ],
            "event_records": [event.to_payload() for event in self.event_records],
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class RuleExecutionRegistry:
    _bindings: Mapping[str, RuleRuntimeBinding]

    @classmethod
    def from_bindings(cls, bindings: tuple[RuleRuntimeBinding, ...]) -> Self:
        if type(bindings) is not tuple:
            raise GameLifecycleError("RuleExecutionRegistry bindings must be a tuple.")
        validated: dict[str, RuleRuntimeBinding] = {}
        for binding in bindings:
            if type(binding) is not RuleRuntimeBinding:
                raise GameLifecycleError(
                    "RuleExecutionRegistry bindings must contain RuleRuntimeBinding values."
                )
            if binding.binding_id in validated:
                raise GameLifecycleError("RuleExecutionRegistry binding IDs must be unique.")
            validated[binding.binding_id] = binding
        return cls(_bindings=MappingProxyType(validated))

    @classmethod
    def empty(cls) -> Self:
        return cls.from_bindings(())

    def with_binding(self, binding: RuleRuntimeBinding) -> Self:
        if type(binding) is not RuleRuntimeBinding:
            raise GameLifecycleError("RuleExecutionRegistry binding must be RuleRuntimeBinding.")
        return self.from_bindings((*tuple(self._bindings.values()), binding))

    def binding_for_clause(self, clause: RuleClause) -> RuleRuntimeBinding | None:
        if _is_aura_clause(clause):
            for binding in self._bindings.values():
                if binding.template_id == RULE_IR_AURA_TEMPLATE_ID and binding.matches_clause(
                    clause
                ):
                    return binding
            return None
        if not clause.effects and clause.target is not None:
            for binding in self._bindings.values():
                if binding.effect_kinds:
                    continue
                if binding.template_id is not None and binding.template_id != clause.template_id:
                    continue
                if binding.matches_clause(clause):
                    return binding
            return None
        return None

    def binding_for_effect(
        self,
        *,
        clause: RuleClause,
        effect: RuleEffectSpec,
    ) -> RuleRuntimeBinding | None:
        for binding in self._bindings.values():
            if binding.matches_effect(clause, effect):
                return binding
        return None

    def execute(
        self,
        *,
        rule_ir: RuleIR,
        context: RuleExecutionContext,
    ) -> RuleExecutionResult:
        return execute_rule_ir(rule_ir=rule_ir, context=context, registry=self)

    def to_payload(self) -> list[RuleRuntimeBindingPayload]:
        return [binding.to_payload() for binding in self._bindings.values()]


def default_rule_execution_registry() -> RuleExecutionRegistry:
    return (
        RuleExecutionRegistry.empty()
        .with_binding(
            RuleRuntimeBinding(
                binding_id="phase17d:generic-modifier",
                template_id=None,
                effect_kinds=(
                    RuleEffectKind.MODIFY_DICE_ROLL,
                    RuleEffectKind.MODIFY_CHARACTERISTIC,
                    RuleEffectKind.MODIFY_MOVE_DISTANCE,
                    RuleEffectKind.GRANT_ABILITY,
                    RuleEffectKind.GRANT_WEAPON_ABILITY,
                    RuleEffectKind.PLACEMENT_PERMISSION,
                    RuleEffectKind.PLACEMENT_RESTRICTION,
                ),
                handler=_generic_effect_handler,
            )
        )
        .with_binding(
            RuleRuntimeBinding(
                binding_id="phase17d:generic-reroll-permission",
                template_id=None,
                effect_kinds=(RuleEffectKind.REROLL_PERMISSION,),
                handler=_generic_effect_handler,
            )
        )
        .with_binding(
            RuleRuntimeBinding(
                binding_id="phase17d:generic-victory-points",
                template_id=None,
                effect_kinds=(RuleEffectKind.ADD_VICTORY_POINTS,),
                required_state_inputs=(STATE_INPUT_GAME_STATE,),
                handler=_victory_point_handler,
            )
        )
        .with_binding(
            RuleRuntimeBinding(
                binding_id="phase17d:generic-command-points",
                template_id=None,
                effect_kinds=(RuleEffectKind.MODIFY_COMMAND_POINTS,),
                required_state_inputs=(STATE_INPUT_GAME_STATE,),
                handler=_command_point_handler,
            )
        )
        .with_binding(
            RuleRuntimeBinding(
                binding_id="phase17d:generic-stratagem-target-binding",
                template_id=None,
                effect_kinds=(),
                required_target_bindings=(TARGET_BINDING_UNIT_IDS,),
                handler=_target_binding_handler,
            )
        )
        .with_binding(
            RuleRuntimeBinding(
                binding_id="phase17d:generic-aura",
                template_id=RULE_IR_AURA_TEMPLATE_ID,
                effect_kinds=(),
                required_state_inputs=(
                    STATE_INPUT_GAME_STATE,
                    STATE_INPUT_BATTLEFIELD_STATE,
                    STATE_INPUT_SOURCE_UNIT,
                ),
                handler=_aura_handler,
            )
        )
    )


def execute_rule_ir(
    *,
    rule_ir: RuleIR,
    context: RuleExecutionContext,
    registry: RuleExecutionRegistry | None = None,
) -> RuleExecutionResult:
    resolved_rule_ir = _validate_rule_ir(rule_ir)
    if type(context) is not RuleExecutionContext:
        raise GameLifecycleError("Rule execution requires RuleExecutionContext.")
    resolved_registry = default_rule_execution_registry() if registry is None else registry
    if type(resolved_registry) is not RuleExecutionRegistry:
        raise GameLifecycleError("Rule execution requires RuleExecutionRegistry.")
    if not resolved_rule_ir.is_supported:
        return RuleExecutionResult.unsupported(
            resolved_rule_ir,
            reason="unsupported_rule_ir",
            replay_payload=validate_json_value(
                {"diagnostics": _diagnostic_payloads(resolved_rule_ir)}
            ),
        )
    preflight = _preflight_rule_ir(
        rule_ir=resolved_rule_ir,
        context=context,
        registry=resolved_registry,
    )
    if preflight is not None:
        return preflight
    return _execute_preflighted_rule_ir(
        rule_ir=resolved_rule_ir,
        context=context,
        registry=resolved_registry,
    )


def rule_ir_from_execution_payload(payload: JsonValue) -> RuleIR:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Generic rule execution payload must be a JSON object.")
    rule_ir_payload = payload.get("rule_ir")
    if not isinstance(rule_ir_payload, dict):
        raise GameLifecycleError("Generic rule execution payload requires rule_ir.")
    return RuleIR.from_payload(cast(RuleIRPayload, rule_ir_payload))


def rule_execution_status_from_token(token: object) -> RuleExecutionStatus:
    if type(token) is RuleExecutionStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("RuleExecutionStatus token must be a string.")
    try:
        return RuleExecutionStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported RuleExecutionStatus token: {token}.") from exc


def _preflight_rule_ir(
    *,
    rule_ir: RuleIR,
    context: RuleExecutionContext,
    registry: RuleExecutionRegistry,
) -> RuleExecutionResult | None:
    simulated_command_ledgers: dict[str, CommandPointLedger] = {}
    for clause in rule_ir.clauses:
        if _is_aura_clause(clause):
            binding = registry.binding_for_clause(clause)
            if binding is None:
                return RuleExecutionResult.unsupported(rule_ir, reason="missing_aura_handler")
            unavailable = _binding_unavailable_reason(binding=binding, context=context)
            if unavailable is not None:
                return RuleExecutionResult.invalid(rule_ir, reason=unavailable)
            unavailable = _clause_semantic_unavailable_reason(
                rule_ir=rule_ir,
                clause=clause,
                context=context,
                simulated_command_ledgers=simulated_command_ledgers,
            )
            if unavailable is not None:
                return RuleExecutionResult.invalid(rule_ir, reason=unavailable)
            continue
        if clause.effects:
            for effect in clause.effects:
                binding = registry.binding_for_effect(clause=clause, effect=effect)
                if binding is None:
                    return RuleExecutionResult.unsupported(
                        rule_ir,
                        reason=f"missing_effect_handler:{effect.kind.value}",
                    )
                unavailable = _binding_unavailable_reason(binding=binding, context=context)
                if unavailable is not None:
                    return RuleExecutionResult.invalid(rule_ir, reason=unavailable)
            unavailable = _clause_semantic_unavailable_reason(
                rule_ir=rule_ir,
                clause=clause,
                context=context,
                simulated_command_ledgers=simulated_command_ledgers,
            )
            if unavailable is not None:
                return RuleExecutionResult.invalid(rule_ir, reason=unavailable)
            continue
        if clause.target is not None:
            binding = registry.binding_for_clause(clause)
            if binding is None:
                return RuleExecutionResult.unsupported(rule_ir, reason="missing_target_handler")
            unavailable = _binding_unavailable_reason(binding=binding, context=context)
            if unavailable is not None:
                return RuleExecutionResult.invalid(rule_ir, reason=unavailable)
    return None


def _execute_preflighted_rule_ir(
    *,
    rule_ir: RuleIR,
    context: RuleExecutionContext,
    registry: RuleExecutionRegistry,
) -> RuleExecutionResult:
    results: list[RuleExecutionResult] = []
    for clause in rule_ir.clauses:
        if _is_aura_clause(clause):
            binding = _require_binding(registry.binding_for_clause(clause))
            result = binding.handler(rule_ir, clause, None, context)
            if result.status is not RuleExecutionStatus.APPLIED:
                return result
            results.append(result)
            continue
        if clause.effects:
            for effect in clause.effects:
                binding = _require_binding(
                    registry.binding_for_effect(clause=clause, effect=effect)
                )
                result = binding.handler(rule_ir, clause, effect, context)
                if result.status is not RuleExecutionStatus.APPLIED:
                    return result
                results.append(result)
            continue
        if clause.target is not None:
            binding = _require_binding(registry.binding_for_clause(clause))
            result = binding.handler(rule_ir, clause, None, context)
            if result.status is not RuleExecutionStatus.APPLIED:
                return result
            results.append(result)
            continue
        results.append(
            RuleExecutionResult.applied(
                rule_ir,
                applied_clause_ids=(clause.clause_id,),
                replay_payload={"clause_id": clause.clause_id, "execution": "no_effect"},
            )
        )
    return _merge_applied_results(rule_ir=rule_ir, results=tuple(results))


def _generic_effect_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    resolved_effect = _require_effect(effect)
    effect_payload = _effect_payload(
        rule_ir=rule_ir,
        clause=clause,
        effect=resolved_effect,
        context=context,
    )
    created_effect = _persisting_effect_or_none(
        rule_ir=rule_ir,
        clause=clause,
        effect_payload=effect_payload,
        context=context,
    )
    event = _emit_event(
        context=context,
        event_type="rule_execution_effect_applied",
        payload=effect_payload,
        fallback_id=_fallback_event_id(rule_ir, clause, resolved_effect, "effect"),
    )
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        effect_payloads=(effect_payload,),
        created_persisting_effects=() if created_effect is None else (created_effect,),
        event_records=(event,),
    )


def _victory_point_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    resolved_effect = _require_effect(effect)
    state = _require_state(context)
    amount = _positive_int_parameter(resolved_effect, "delta")
    if context.phase is None:
        return RuleExecutionResult.invalid(rule_ir, reason="missing_phase")
    award = VictoryPointAward(
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=context.phase.value,
        amount=amount,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        source_id=rule_ir.source_id,
        scoring_timing="generic_rule_execution",
        metadata=validate_json_value(
            {
                "rule_id": rule_ir.rule_id,
                "clause_id": clause.clause_id,
                "effect": resolved_effect.to_payload(),
            }
        ),
    )
    transaction = state.award_victory_points(award)
    payload = transaction.to_payload()
    event = _emit_event(
        context=context,
        event_type="rule_execution_victory_points_awarded",
        payload=payload,
        fallback_id=_fallback_event_id(rule_ir, clause, resolved_effect, "vp"),
    )
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        effect_payloads=(
            _effect_payload(
                rule_ir=rule_ir,
                clause=clause,
                effect=resolved_effect,
                context=context,
            ),
        ),
        victory_point_transactions=(payload,),
        event_records=(event,),
    )


def _command_point_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    resolved_effect = _require_effect(effect)
    state = _require_state(context)
    delta = _int_parameter(resolved_effect, "delta")
    if delta == 0:
        return RuleExecutionResult.invalid(rule_ir, reason="zero_command_point_delta")
    if delta > 0:
        gain_result = state.gain_command_points(
            player_id=context.player_id,
            amount=delta,
            source_id=rule_ir.source_id,
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=False,
        )
        if gain_result.status is not CommandPointGainStatus.APPLIED:
            return RuleExecutionResult.invalid(rule_ir, reason="command_point_gain_capped")
        payload = _json_object(gain_result.to_payload())
    else:
        spend_result = state.spend_command_points(
            player_id=context.player_id,
            amount=abs(delta),
            source_id=rule_ir.source_id,
        )
        if spend_result.status is not CommandPointSpendStatus.APPLIED:
            return RuleExecutionResult.invalid(rule_ir, reason="insufficient_command_points")
        payload = _json_object(spend_result.to_payload())
    event = _emit_event(
        context=context,
        event_type="rule_execution_command_points_modified",
        payload=payload,
        fallback_id=_fallback_event_id(rule_ir, clause, resolved_effect, "cp"),
    )
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        effect_payloads=(
            _effect_payload(
                rule_ir=rule_ir,
                clause=clause,
                effect=resolved_effect,
                context=context,
            ),
        ),
        command_point_transactions=(payload,),
        event_records=(event,),
    )


def _target_binding_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    if effect is not None:
        raise GameLifecycleError("Target binding handler does not accept an effect.")
    target_kind = "unbound" if clause.target is None else clause.target.kind.value
    payload: dict[str, JsonValue] = {
        "rule_id": rule_ir.rule_id,
        "source_id": rule_ir.source_id,
        "clause_id": clause.clause_id,
        "target_kind": target_kind,
        "target_unit_instance_ids": list(context.target_unit_instance_ids),
        "target_player_id": context.target_player_id,
    }
    event = _emit_event(
        context=context,
        event_type="rule_execution_target_bound",
        payload=payload,
        fallback_id=_fallback_event_id(rule_ir, clause, None, "target"),
    )
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        target_bindings=(payload,),
        event_records=(event,),
    )


def _aura_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    if effect is not None:
        raise GameLifecycleError("Aura handler does not accept a single effect.")
    affected_unit_ids = _aura_affected_unit_ids(clause=clause, context=context)
    aura_payload = _json_object(
        {
            "rule_id": rule_ir.rule_id,
            "source_id": rule_ir.source_id,
            "clause_id": clause.clause_id,
            "source_unit_instance_id": context.source_unit_instance_id,
            "affected_unit_instance_ids": list(affected_unit_ids),
            "conditions": [condition.to_payload() for condition in clause.conditions],
        }
    )
    effect_payloads = tuple(
        _effect_payload(
            rule_ir=rule_ir,
            clause=clause,
            effect=effect_spec,
            context=context,
            target_unit_instance_ids=affected_unit_ids,
        )
        for effect_spec in clause.effects
    )
    event = _emit_event(
        context=context,
        event_type="rule_execution_aura_evaluated",
        payload=aura_payload,
        fallback_id=_fallback_event_id(rule_ir, clause, None, "aura"),
    )
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        effect_payloads=effect_payloads,
        aura_evaluations=(aura_payload,),
        event_records=(event,),
    )


def _effect_payload(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec,
    context: RuleExecutionContext,
    target_unit_instance_ids: tuple[str, ...] | None = None,
) -> dict[str, JsonValue]:
    target_ids = _target_unit_instance_ids_for_clause(
        clause=clause,
        context=context,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    return _json_object(
        {
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "rule_id": rule_ir.rule_id,
            "source_id": rule_ir.source_id,
            "rule_ir_hash": rule_ir.ir_hash(),
            "clause_id": clause.clause_id,
            "source_span": clause.source_span.to_payload(),
            "target": None if clause.target is None else clause.target.to_payload(),
            "target_unit_instance_ids": list(target_ids),
            "duration": None if clause.duration is None else clause.duration.to_payload(),
            "effect": effect.to_payload(),
            "context": context.to_payload(),
        }
    )


def _persisting_effect_or_none(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    effect_payload: dict[str, JsonValue],
    context: RuleExecutionContext,
) -> PersistingEffect | None:
    target_unit_instance_ids = _target_unit_instance_ids_for_clause(
        clause=clause,
        context=context,
        target_unit_instance_ids=None,
    )
    if context.state is None or not target_unit_instance_ids or clause.duration is None:
        return None
    expiration = _expiration_for_duration(duration=clause.duration, context=context)
    if expiration is None:
        return None
    effect = generic_rule_persisting_effect(
        effect_id=_effect_id(rule_ir=rule_ir, clause=clause),
        source_rule_id=rule_ir.source_id,
        owner_player_id=context.player_id,
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=context.battle_round,
        started_phase=context.phase,
        expiration=expiration,
        effect_payload=effect_payload,
    )
    context.state.record_persisting_effect(effect)
    return effect


def _expiration_for_duration(
    *,
    duration: RuleDuration,
    context: RuleExecutionContext,
) -> EffectExpiration | None:
    if duration.kind is RuleDurationKind.IMMEDIATE:
        return None
    if duration.kind is RuleDurationKind.PERMANENT:
        return EffectExpiration.end_of_battle()
    parameters = parameter_payload(duration.parameters)
    endpoint = parameters.get("endpoint")
    if duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT:
        if endpoint == "phase":
            if context.phase is None:
                raise GameLifecycleError("Phase duration requires execution phase.")
            return EffectExpiration.end_phase(
                battle_round=context.battle_round,
                phase=context.phase,
                player_id=context.player_id,
            )
        if endpoint == "turn":
            return EffectExpiration.end_turn(
                battle_round=context.battle_round,
                player_id=context.player_id,
            )
        if endpoint == "battle round":
            return EffectExpiration.end_battle_round(battle_round=context.battle_round)
        if endpoint == "battle":
            return EffectExpiration.end_of_battle()
        raise GameLifecycleError("Unsupported rule duration endpoint.")
    if duration.kind is RuleDurationKind.WHILE_CONDITION_TRUE:
        return None
    raise GameLifecycleError("Unsupported rule duration kind.")


def _aura_affected_unit_ids(
    *,
    clause: RuleClause,
    context: RuleExecutionContext,
) -> tuple[str, ...]:
    state = _require_state(context)
    if state.battlefield_state is None:
        raise GameLifecycleError("Aura evaluation requires battlefield_state.")
    source_unit_id = context.source_unit_instance_id
    if source_unit_id is None:
        raise GameLifecycleError("Aura evaluation requires source_unit_instance_id.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    source_placement = state.battlefield_state.unit_placement_by_id(source_unit_id)
    distance_inches = _aura_distance_inches(clause)
    allegiance = _aura_allegiance(clause)
    required_keywords = _required_keywords(clause.conditions)
    affected: list[str] = []
    for placed_army in state.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id == source_unit_id:
                continue
            if (
                allegiance == AURA_ALLEGIANCE_FRIENDLY
                and unit_placement.player_id != source_placement.player_id
            ):
                continue
            if (
                allegiance == AURA_ALLEGIANCE_ENEMY
                and unit_placement.player_id == source_placement.player_id
            ):
                continue
            unit = scenario.unit_instance_for_placement(unit_placement)
            if required_keywords and not set(required_keywords).issubset(set(unit.keywords)):
                continue
            if _unit_within_aura(
                scenario=scenario,
                source_placement=source_placement,
                target_placement=unit_placement,
                distance_inches=distance_inches,
            ):
                affected.append(unit_placement.unit_instance_id)
    return tuple(sorted(affected))


def _unit_within_aura(
    *,
    scenario: BattlefieldScenario,
    source_placement: UnitPlacement,
    target_placement: UnitPlacement,
    distance_inches: float,
) -> bool:
    for source_model_placement in source_placement.model_placements:
        source_model = scenario.model_instance_for_placement(source_model_placement)
        source_geometry = geometry_model_for_placement(
            model=source_model,
            placement=source_model_placement,
        )
        for target_model_placement in target_placement.model_placements:
            target_model = scenario.model_instance_for_placement(target_model_placement)
            target_geometry = geometry_model_for_placement(
                model=target_model,
                placement=target_model_placement,
            )
            measured = DistanceMeasurementContext.from_models(source_geometry, target_geometry)
            if measured.closest_distance_inches() <= distance_inches:
                return True
    return False


def _aura_distance_inches(clause: RuleClause) -> float:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        distance = parameters.get("distance_inches")
        if isinstance(distance, int | float) and type(distance) is not bool:
            return float(distance)
    raise GameLifecycleError("Aura clause requires a structured distance predicate.")


def _aura_allegiance(clause: RuleClause) -> str:
    if clause.target is None or clause.target.kind is not RuleTargetKind.AURA_UNITS:
        raise GameLifecycleError("Aura clause requires an aura_units target.")
    parameters = parameter_payload(clause.target.parameters)
    allegiance = parameters.get("allegiance")
    if type(allegiance) is not str:
        raise GameLifecycleError("Aura target requires structured allegiance.")
    if allegiance not in {
        AURA_ALLEGIANCE_ANY,
        AURA_ALLEGIANCE_ENEMY,
        AURA_ALLEGIANCE_FRIENDLY,
    }:
        raise GameLifecycleError("Aura target allegiance is unsupported.")
    return allegiance


def _required_keywords(conditions: tuple[RuleCondition, ...]) -> tuple[str, ...]:
    keywords: list[str] = []
    for condition in conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        keyword = parameters.get("required_keyword")
        if type(keyword) is str:
            keywords.append(keyword)
    return tuple(sorted(keywords))


def _clause_semantic_unavailable_reason(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    context: RuleExecutionContext,
    simulated_command_ledgers: dict[str, CommandPointLedger],
) -> str | None:
    target_reason = _effect_clause_target_unavailable_reason(clause=clause, context=context)
    if target_reason is not None:
        return target_reason
    duration_reason = _duration_unavailable_reason(clause=clause, context=context)
    if duration_reason is not None:
        return duration_reason
    for effect in clause.effects:
        effect_reason = _effect_semantic_unavailable_reason(
            rule_ir=rule_ir,
            effect=effect,
            context=context,
            simulated_command_ledgers=simulated_command_ledgers,
        )
        if effect_reason is not None:
            return effect_reason
    return None


def _effect_clause_target_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleExecutionContext,
) -> str | None:
    if not _clause_requires_unit_target(clause):
        return None
    if _target_unit_instance_ids_for_clause(
        clause=clause,
        context=context,
        target_unit_instance_ids=None,
    ):
        return None
    if clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT:
        return "missing_input:source_unit_instance_id"
    return "missing_target:unit_instance_ids"


def _clause_requires_unit_target(clause: RuleClause) -> bool:
    return (
        clause.target is not None
        and clause.target.kind in UNIT_EFFECT_TARGET_KINDS
        and any(effect.kind in TARGET_SCOPED_EFFECT_KINDS for effect in clause.effects)
    )


def _target_unit_instance_ids_for_clause(
    *,
    clause: RuleClause,
    context: RuleExecutionContext,
    target_unit_instance_ids: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT:
        if context.source_unit_instance_id is None:
            return ()
        return (context.source_unit_instance_id,)
    if target_unit_instance_ids is not None:
        return target_unit_instance_ids
    if context.target_unit_instance_ids:
        return context.target_unit_instance_ids
    return ()


def _duration_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleExecutionContext,
) -> str | None:
    if clause.duration is None:
        return None
    if (
        clause.duration.kind is not RuleDurationKind.IMMEDIATE
        and _clause_requires_unit_target(clause)
        and context.state is None
    ):
        return "missing_input:game_state"
    if clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT:
        return None
    parameters = parameter_payload(clause.duration.parameters)
    if parameters.get("endpoint") == "phase" and context.phase is None:
        return "missing_phase"
    return None


def _effect_semantic_unavailable_reason(
    *,
    rule_ir: RuleIR,
    effect: RuleEffectSpec,
    context: RuleExecutionContext,
    simulated_command_ledgers: dict[str, CommandPointLedger],
) -> str | None:
    if effect.kind is RuleEffectKind.ADD_VICTORY_POINTS and context.phase is None:
        return "missing_phase"
    if effect.kind is RuleEffectKind.MODIFY_COMMAND_POINTS:
        return _command_point_unavailable_reason(
            rule_ir=rule_ir,
            effect=effect,
            context=context,
            simulated_command_ledgers=simulated_command_ledgers,
        )
    return None


def _command_point_unavailable_reason(
    *,
    rule_ir: RuleIR,
    effect: RuleEffectSpec,
    context: RuleExecutionContext,
    simulated_command_ledgers: dict[str, CommandPointLedger],
) -> str | None:
    state = context.state
    if state is None:
        return "missing_input:game_state"
    delta = _int_parameter(effect, "delta")
    if delta == 0:
        return "zero_command_point_delta"
    ledger = simulated_command_ledgers.get(context.player_id)
    if ledger is None:
        ledger = state.command_point_ledger_for_player(context.player_id)
    if delta > 0:
        updated, gain_result = ledger.gain(
            battle_round=state.battle_round,
            amount=delta,
            source_id=rule_ir.source_id,
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=False,
        )
        if gain_result.status is not CommandPointGainStatus.APPLIED:
            return "command_point_gain_capped"
        simulated_command_ledgers[context.player_id] = updated
        return None
    updated, spend_result = ledger.spend(
        battle_round=state.battle_round,
        amount=abs(delta),
        source_id=rule_ir.source_id,
    )
    if spend_result.status is not CommandPointSpendStatus.APPLIED:
        return "insufficient_command_points"
    simulated_command_ledgers[context.player_id] = updated
    return None


def _binding_unavailable_reason(
    *,
    binding: RuleRuntimeBinding,
    context: RuleExecutionContext,
) -> str | None:
    for state_input in binding.required_state_inputs:
        if state_input == STATE_INPUT_GAME_STATE and context.state is None:
            return "missing_input:game_state"
        if state_input == STATE_INPUT_BATTLEFIELD_STATE and (
            context.state is None or context.state.battlefield_state is None
        ):
            return "missing_input:battlefield_state"
        if state_input == STATE_INPUT_SOURCE_UNIT and context.source_unit_instance_id is None:
            return "missing_input:source_unit_instance_id"
        if state_input == STATE_INPUT_EVENT_LOG and context.event_log is None:
            return "missing_input:event_log"
    for target_binding in binding.required_target_bindings:
        if target_binding == TARGET_BINDING_UNIT_IDS and not context.target_unit_instance_ids:
            return "missing_target:unit_instance_ids"
    return None


def _merge_applied_results(
    *,
    rule_ir: RuleIR,
    results: tuple[RuleExecutionResult, ...],
) -> RuleExecutionResult:
    applied_clause_ids: list[str] = []
    effect_payloads: list[dict[str, JsonValue]] = []
    target_bindings: list[dict[str, JsonValue]] = []
    aura_evaluations: list[dict[str, JsonValue]] = []
    victory_point_transactions: list[VictoryPointTransactionPayload] = []
    command_point_transactions: list[dict[str, JsonValue]] = []
    created_effects: list[PersistingEffect] = []
    event_records: list[EventRecord] = []
    for result in results:
        if result.status is not RuleExecutionStatus.APPLIED:
            raise GameLifecycleError("Rule execution merge requires applied subresults.")
        for clause_id in result.applied_clause_ids:
            if clause_id not in applied_clause_ids:
                applied_clause_ids.append(clause_id)
        effect_payloads.extend(result.effect_payloads)
        target_bindings.extend(result.target_bindings)
        aura_evaluations.extend(result.aura_evaluations)
        victory_point_transactions.extend(result.victory_point_transactions)
        command_point_transactions.extend(result.command_point_transactions)
        created_effects.extend(result.created_persisting_effects)
        event_records.extend(result.event_records)
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=tuple(applied_clause_ids),
        effect_payloads=tuple(effect_payloads),
        target_bindings=tuple(target_bindings),
        aura_evaluations=tuple(aura_evaluations),
        victory_point_transactions=tuple(victory_point_transactions),
        command_point_transactions=tuple(command_point_transactions),
        created_persisting_effects=tuple(created_effects),
        event_records=tuple(event_records),
        replay_payload={
            "executed_clause_count": len(applied_clause_ids),
            "event_count": len(event_records),
        },
    )


def _is_aura_clause(clause: RuleClause) -> bool:
    return clause.template_id == RULE_IR_AURA_TEMPLATE_ID or any(
        condition.kind is RuleConditionKind.AURA for condition in clause.conditions
    )


def _emit_event(
    *,
    context: RuleExecutionContext,
    event_type: str,
    payload: object,
    fallback_id: str,
) -> EventRecord:
    event_payload = validate_json_value(payload)
    if context.event_log is not None:
        appended = context.event_log.append(event_type, event_payload)
        if type(appended) is not EventRecord:
            raise GameLifecycleError("Rule execution event_log append returned invalid event.")
        return appended
    return EventRecord(
        event_id=fallback_id,
        event_type=event_type,
        payload=event_payload,
    )


def _fallback_event_id(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    suffix: str,
) -> str:
    effect_kind = "clause" if effect is None else effect.kind.value
    clause_suffix = clause.clause_id.rsplit(":", 1)[-1]
    return f"rule-event:{rule_ir.ir_hash()[:12]}:{clause_suffix}:{effect_kind}:{suffix}"


def _effect_id(*, rule_ir: RuleIR, clause: RuleClause) -> str:
    return f"rule-effect:{rule_ir.ir_hash()[:16]}:{clause.clause_id.rsplit(':', 1)[-1]}"


def _diagnostic_payloads(rule_ir: RuleIR) -> list[dict[str, JsonValue]]:
    return [
        _json_object(diagnostic.to_payload())
        for diagnostic in (
            *rule_ir.diagnostics,
            *(diagnostic for clause in rule_ir.clauses for diagnostic in clause.diagnostics),
        )
    ]


def _require_binding(binding: RuleRuntimeBinding | None) -> RuleRuntimeBinding:
    if binding is None:
        raise GameLifecycleError("Preflighted rule execution binding was not found.")
    return binding


def _require_effect(effect: RuleEffectSpec | None) -> RuleEffectSpec:
    if effect is None:
        raise GameLifecycleError("Rule execution handler requires an effect.")
    return effect


def _require_state(context: RuleExecutionContext) -> GameState:
    if context.state is None:
        raise GameLifecycleError("Rule execution requires GameState.")
    return context.state


def _positive_int_parameter(effect: RuleEffectSpec, key: str) -> int:
    value = _parameter(effect, key)
    if type(value) is not int:
        raise GameLifecycleError(f"Rule effect parameter {key} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"Rule effect parameter {key} must be positive.")
    return value


def _int_parameter(effect: RuleEffectSpec, key: str) -> int:
    value = _parameter(effect, key)
    if type(value) is not int:
        raise GameLifecycleError(f"Rule effect parameter {key} must be an integer.")
    return value


def _parameter(effect: RuleEffectSpec, key: str) -> RuleParameterValue:
    parameters = parameter_payload(effect.parameters)
    if key not in parameters:
        raise GameLifecycleError(f"Rule effect is missing {key} parameter.")
    return parameters[key]


def _validate_rule_ir(value: object) -> RuleIR:
    if type(value) is not RuleIR:
        raise GameLifecycleError("Rule execution requires a compiled RuleIR.")
    return value


def _validate_effect_kind_tuple(
    field_name: str,
    values: object,
) -> tuple[RuleEffectKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[RuleEffectKind] = []
    seen: set[RuleEffectKind] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not RuleEffectKind:
            raise GameLifecycleError(f"{field_name} values must be RuleEffectKind.")
        if value in seen:
            raise GameLifecycleError(f"{field_name} values must not be duplicated.")
        seen.add(value)
        validated.append(value)
    return tuple(sorted(validated, key=lambda kind: kind.value))


def _validate_json_object_tuple(
    field_name: str,
    values: object,
) -> tuple[dict[str, JsonValue], ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[dict[str, JsonValue]] = []
    for value in cast(tuple[object, ...], values):
        validated.append(_json_object(value))
    return tuple(validated)


def _json_object(value: object) -> dict[str, JsonValue]:
    validated = validate_json_value(value)
    if not isinstance(validated, dict):
        raise GameLifecycleError("Rule execution payload must be a JSON object.")
    return validated


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate values.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value


def _validate_optional_phase(
    field_name: str,
    value: object | None,
) -> BattlePhaseKind | None:
    if value is None:
        return None
    try:
        return battle_phase_kind_from_token(value)
    except ValueError as exc:
        raise GameLifecycleError(f"{field_name} must be a BattlePhaseKind.") from exc
