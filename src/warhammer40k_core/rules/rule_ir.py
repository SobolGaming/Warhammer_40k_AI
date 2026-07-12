from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.parsed_tokens import TextSpan, TextSpanPayload


class RuleIRError(ValueError):
    """Raised when Phase 17C rule IR data violates source-boundary invariants."""


type RuleParameterValue = str | int | float | bool | None | tuple[str, ...]
type RuleParameterPayloadValue = str | int | float | bool | None | list[str]


class RuleParameterPayload(TypedDict):
    key: str
    value: RuleParameterPayloadValue


class RuleTriggerPayload(TypedDict):
    kind: str
    source_span: TextSpanPayload
    parameters: list[RuleParameterPayload]


class RuleConditionPayload(TypedDict):
    kind: str
    source_span: TextSpanPayload
    parameters: list[RuleParameterPayload]


class RuleTargetSpecPayload(TypedDict):
    kind: str
    source_span: TextSpanPayload
    parameters: list[RuleParameterPayload]


class RuleEffectSpecPayload(TypedDict):
    kind: str
    source_span: TextSpanPayload
    parameters: list[RuleParameterPayload]


class RuleDurationPayload(TypedDict):
    kind: str
    source_span: TextSpanPayload
    parameters: list[RuleParameterPayload]


class RuleParseDiagnosticPayload(TypedDict):
    reason: str
    message: str
    source_span: TextSpanPayload
    blocking: bool


class RuleClausePayload(TypedDict):
    clause_id: str
    template_id: str | None
    source_span: TextSpanPayload
    trigger: RuleTriggerPayload | None
    conditions: list[RuleConditionPayload]
    target: RuleTargetSpecPayload | None
    effects: list[RuleEffectSpecPayload]
    duration: RuleDurationPayload | None
    unsupported_reason: str | None
    diagnostics: list[RuleParseDiagnosticPayload]


class RuleIRPayload(TypedDict):
    rule_id: str
    source_id: str
    normalized_text: str
    parser_version: str
    schema_version: str
    clauses: list[RuleClausePayload]
    diagnostics: list[RuleParseDiagnosticPayload]
    ir_hash: str


class RuleTriggerKind(StrEnum):
    TIMING_WINDOW = "timing_window"
    DICE_ROLL = "dice_roll"
    UNIT_SELECTED = "unit_selected"
    UNIT_DESTROYED = "unit_destroyed"
    MODEL_DESTROYED = "model_destroyed"
    SETUP = "setup"


class RuleConditionKind(StrEnum):
    AURA = "aura"
    DICE_ROLL_GATE = "dice_roll_gate"
    DICE_ROLL_TYPE = "dice_roll_type"
    DISTANCE_PREDICATE = "distance_predicate"
    FREQUENCY_LIMIT = "frequency_limit"
    KEYWORD_GATE = "keyword_gate"
    PHASE_GATE = "phase_gate"
    TARGET_CONSTRAINT = "target_constraint"
    VISIBILITY_PREDICATE = "visibility_predicate"


class RuleTargetKind(StrEnum):
    AURA_UNITS = "aura_units"
    DICE_ROLL = "dice_roll"
    ENEMY_UNIT = "enemy_unit"
    FRIENDLY_UNIT = "friendly_unit"
    PLAYER = "player"
    SELECTED_TARGET = "selected_target"
    SELECTED_UNIT = "selected_unit"
    STRATAGEM_USE = "stratagem_use"
    THIS_MODEL = "this_model"
    THIS_UNIT = "this_unit"
    WEAPON = "weapon"


class RuleEffectKind(StrEnum):
    ADD_VICTORY_POINTS = "add_victory_points"
    FORCE_DESPERATE_ESCAPE_TESTS = "force_desperate_escape_tests"
    GRANT_ABILITY = "grant_ability"
    GRANT_WEAPON_ABILITY = "grant_weapon_ability"
    INFLICT_MORTAL_WOUNDS = "inflict_mortal_wounds"
    MODIFY_CHARACTERISTIC = "modify_characteristic"
    MODIFY_COMMAND_POINTS = "modify_command_points"
    MODIFY_DICE_ROLL = "modify_dice_roll"
    MODIFY_MOVE_DISTANCE = "modify_move_distance"
    MUSTERING_SELECTION = "mustering_selection"
    MOVEMENT_TRANSIT_PERMISSION = "movement_transit_permission"
    OUT_OF_PHASE_ACTION = "out_of_phase_action"
    PLACEMENT_PERMISSION = "placement_permission"
    PLACEMENT_RESTRICTION = "placement_restriction"
    REROLL_PERMISSION = "reroll_permission"
    RESTORE_LOST_WOUNDS = "restore_lost_wounds"
    RETURN_DESTROYED_TARGET = "return_destroyed_target"
    SELECT_TRACKED_TARGET = "select_tracked_target"
    SET_CONTEXTUAL_STATUS = "set_contextual_status"
    SET_CHARACTERISTIC = "set_characteristic"


class RuleDurationKind(StrEnum):
    IMMEDIATE = "immediate"
    PERMANENT = "permanent"
    UNTIL_TIMING_ENDPOINT = "until_timing_endpoint"
    WHILE_CONDITION_TRUE = "while_condition_true"


class RuleUnsupportedReason(StrEnum):
    AMBIGUOUS_LANGUAGE = "ambiguous_language"
    EMPTY_RULE = "empty_rule"
    RAW_TEXT_NOT_NORMALIZED = "raw_text_not_normalized"
    UNSUPPORTED_DURATION = "unsupported_duration"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    UNSUPPORTED_TARGET = "unsupported_target"


@dataclass(frozen=True, slots=True)
class RuleParameter:
    key: str
    value: RuleParameterValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _validate_identifier("RuleParameter key", self.key))
        object.__setattr__(
            self,
            "value",
            _validate_parameter_value("RuleParameter value", self.value),
        )

    def to_payload(self) -> RuleParameterPayload:
        value = list(self.value) if type(self.value) is tuple else self.value
        return {"key": self.key, "value": cast(RuleParameterPayloadValue, value)}

    @classmethod
    def from_payload(cls, payload: RuleParameterPayload) -> Self:
        raw_value = payload["value"]
        value = tuple(raw_value) if type(raw_value) is list else raw_value
        return cls(key=payload["key"], value=cast(RuleParameterValue, value))


@dataclass(frozen=True, slots=True)
class RuleTrigger:
    kind: RuleTriggerKind
    source_span: TextSpan
    parameters: tuple[RuleParameter, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", rule_trigger_kind_from_token(self.kind))
        _validate_span_object("RuleTrigger source_span", self.source_span)
        object.__setattr__(
            self,
            "parameters",
            _validate_parameters("RuleTrigger parameters", self.parameters),
        )

    def to_payload(self) -> RuleTriggerPayload:
        return {
            "kind": self.kind.value,
            "source_span": self.source_span.to_payload(),
            "parameters": [parameter.to_payload() for parameter in self.parameters],
        }

    @classmethod
    def from_payload(cls, payload: RuleTriggerPayload) -> Self:
        return cls(
            kind=rule_trigger_kind_from_token(payload["kind"]),
            source_span=_span_from_payload(payload["source_span"]),
            parameters=tuple(
                RuleParameter.from_payload(parameter) for parameter in payload["parameters"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RuleCondition:
    kind: RuleConditionKind
    source_span: TextSpan
    parameters: tuple[RuleParameter, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", rule_condition_kind_from_token(self.kind))
        _validate_span_object("RuleCondition source_span", self.source_span)
        object.__setattr__(
            self,
            "parameters",
            _validate_parameters("RuleCondition parameters", self.parameters),
        )

    def to_payload(self) -> RuleConditionPayload:
        return {
            "kind": self.kind.value,
            "source_span": self.source_span.to_payload(),
            "parameters": [parameter.to_payload() for parameter in self.parameters],
        }

    @classmethod
    def from_payload(cls, payload: RuleConditionPayload) -> Self:
        return cls(
            kind=rule_condition_kind_from_token(payload["kind"]),
            source_span=_span_from_payload(payload["source_span"]),
            parameters=tuple(
                RuleParameter.from_payload(parameter) for parameter in payload["parameters"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RuleTargetSpec:
    kind: RuleTargetKind
    source_span: TextSpan
    parameters: tuple[RuleParameter, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", rule_target_kind_from_token(self.kind))
        _validate_span_object("RuleTargetSpec source_span", self.source_span)
        object.__setattr__(
            self,
            "parameters",
            _validate_parameters("RuleTargetSpec parameters", self.parameters),
        )

    def to_payload(self) -> RuleTargetSpecPayload:
        return {
            "kind": self.kind.value,
            "source_span": self.source_span.to_payload(),
            "parameters": [parameter.to_payload() for parameter in self.parameters],
        }

    @classmethod
    def from_payload(cls, payload: RuleTargetSpecPayload) -> Self:
        return cls(
            kind=rule_target_kind_from_token(payload["kind"]),
            source_span=_span_from_payload(payload["source_span"]),
            parameters=tuple(
                RuleParameter.from_payload(parameter) for parameter in payload["parameters"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RuleEffectSpec:
    kind: RuleEffectKind
    source_span: TextSpan
    parameters: tuple[RuleParameter, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", rule_effect_kind_from_token(self.kind))
        _validate_span_object("RuleEffectSpec source_span", self.source_span)
        object.__setattr__(
            self,
            "parameters",
            _validate_parameters("RuleEffectSpec parameters", self.parameters),
        )

    def to_payload(self) -> RuleEffectSpecPayload:
        return {
            "kind": self.kind.value,
            "source_span": self.source_span.to_payload(),
            "parameters": [parameter.to_payload() for parameter in self.parameters],
        }

    @classmethod
    def from_payload(cls, payload: RuleEffectSpecPayload) -> Self:
        return cls(
            kind=rule_effect_kind_from_token(payload["kind"]),
            source_span=_span_from_payload(payload["source_span"]),
            parameters=tuple(
                RuleParameter.from_payload(parameter) for parameter in payload["parameters"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RuleDuration:
    kind: RuleDurationKind
    source_span: TextSpan
    parameters: tuple[RuleParameter, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", rule_duration_kind_from_token(self.kind))
        _validate_span_object("RuleDuration source_span", self.source_span)
        object.__setattr__(
            self,
            "parameters",
            _validate_parameters("RuleDuration parameters", self.parameters),
        )

    def to_payload(self) -> RuleDurationPayload:
        return {
            "kind": self.kind.value,
            "source_span": self.source_span.to_payload(),
            "parameters": [parameter.to_payload() for parameter in self.parameters],
        }

    @classmethod
    def from_payload(cls, payload: RuleDurationPayload) -> Self:
        return cls(
            kind=rule_duration_kind_from_token(payload["kind"]),
            source_span=_span_from_payload(payload["source_span"]),
            parameters=tuple(
                RuleParameter.from_payload(parameter) for parameter in payload["parameters"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RuleParseDiagnostic:
    reason: RuleUnsupportedReason
    message: str
    source_span: TextSpan
    blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", rule_unsupported_reason_from_token(self.reason))
        object.__setattr__(
            self,
            "message",
            _validate_identifier("RuleParseDiagnostic message", self.message),
        )
        _validate_span_object("RuleParseDiagnostic source_span", self.source_span)
        if type(self.blocking) is not bool:
            raise RuleIRError("RuleParseDiagnostic blocking must be a boolean.")

    def to_payload(self) -> RuleParseDiagnosticPayload:
        return {
            "reason": self.reason.value,
            "message": self.message,
            "source_span": self.source_span.to_payload(),
            "blocking": self.blocking,
        }

    @classmethod
    def from_payload(cls, payload: RuleParseDiagnosticPayload) -> Self:
        return cls(
            reason=rule_unsupported_reason_from_token(payload["reason"]),
            message=payload["message"],
            source_span=_span_from_payload(payload["source_span"]),
            blocking=payload["blocking"],
        )


@dataclass(frozen=True, slots=True)
class RuleClause:
    clause_id: str
    source_span: TextSpan
    trigger: RuleTrigger | None = None
    conditions: tuple[RuleCondition, ...] = ()
    target: RuleTargetSpec | None = None
    effects: tuple[RuleEffectSpec, ...] = ()
    duration: RuleDuration | None = None
    unsupported_reason: RuleUnsupportedReason | None = None
    diagnostics: tuple[RuleParseDiagnostic, ...] = ()
    template_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "clause_id", _validate_identifier("RuleClause id", self.clause_id))
        _validate_span_object("RuleClause source_span", self.source_span)
        if self.trigger is not None and type(self.trigger) is not RuleTrigger:
            raise RuleIRError("RuleClause trigger must be a RuleTrigger.")
        object.__setattr__(
            self,
            "conditions",
            _validate_component_tuple("RuleClause conditions", self.conditions, RuleCondition),
        )
        if self.target is not None and type(self.target) is not RuleTargetSpec:
            raise RuleIRError("RuleClause target must be a RuleTargetSpec.")
        object.__setattr__(
            self,
            "effects",
            _validate_component_tuple("RuleClause effects", self.effects, RuleEffectSpec),
        )
        if self.duration is not None and type(self.duration) is not RuleDuration:
            raise RuleIRError("RuleClause duration must be a RuleDuration.")
        unsupported_reason = self.unsupported_reason
        if unsupported_reason is not None:
            object.__setattr__(
                self,
                "unsupported_reason",
                rule_unsupported_reason_from_token(unsupported_reason),
            )
        object.__setattr__(
            self,
            "diagnostics",
            _validate_component_tuple(
                "RuleClause diagnostics",
                self.diagnostics,
                RuleParseDiagnostic,
            ),
        )
        if self.template_id is not None:
            object.__setattr__(
                self,
                "template_id",
                _validate_identifier("RuleClause template_id", self.template_id),
            )
        if unsupported_reason is None and not self.has_supported_component:
            raise RuleIRError("RuleClause must contain supported components or unsupported_reason.")
        if unsupported_reason is not None and not self.diagnostics:
            raise RuleIRError("Unsupported RuleClause must include diagnostics.")

    @property
    def has_supported_component(self) -> bool:
        return (
            self.trigger is not None
            or bool(self.conditions)
            or self.target is not None
            or bool(self.effects)
            or self.duration is not None
        )

    @property
    def is_supported(self) -> bool:
        return self.unsupported_reason is None and not any(
            diagnostic.blocking for diagnostic in self.diagnostics
        )

    def to_payload(self) -> RuleClausePayload:
        return {
            "clause_id": self.clause_id,
            "template_id": self.template_id,
            "source_span": self.source_span.to_payload(),
            "trigger": None if self.trigger is None else self.trigger.to_payload(),
            "conditions": [condition.to_payload() for condition in self.conditions],
            "target": None if self.target is None else self.target.to_payload(),
            "effects": [effect.to_payload() for effect in self.effects],
            "duration": None if self.duration is None else self.duration.to_payload(),
            "unsupported_reason": (
                None if self.unsupported_reason is None else self.unsupported_reason.value
            ),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: RuleClausePayload) -> Self:
        trigger_payload = payload["trigger"]
        target_payload = payload["target"]
        duration_payload = payload["duration"]
        unsupported_reason = payload["unsupported_reason"]
        return cls(
            clause_id=payload["clause_id"],
            template_id=payload["template_id"],
            source_span=_span_from_payload(payload["source_span"]),
            trigger=None if trigger_payload is None else RuleTrigger.from_payload(trigger_payload),
            conditions=tuple(
                RuleCondition.from_payload(condition) for condition in payload["conditions"]
            ),
            target=None if target_payload is None else RuleTargetSpec.from_payload(target_payload),
            effects=tuple(RuleEffectSpec.from_payload(effect) for effect in payload["effects"]),
            duration=(
                None if duration_payload is None else RuleDuration.from_payload(duration_payload)
            ),
            unsupported_reason=(
                None
                if unsupported_reason is None
                else rule_unsupported_reason_from_token(unsupported_reason)
            ),
            diagnostics=tuple(
                RuleParseDiagnostic.from_payload(diagnostic)
                for diagnostic in payload["diagnostics"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RuleIR:
    rule_id: str
    source_id: str
    normalized_text: str
    parser_version: str
    clauses: tuple[RuleClause, ...]
    diagnostics: tuple[RuleParseDiagnostic, ...] = ()
    schema_version: str = "phase17c-rule-ir-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _validate_identifier("RuleIR rule_id", self.rule_id))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("RuleIR source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "normalized_text",
            _validate_identifier("RuleIR normalized_text", self.normalized_text),
        )
        object.__setattr__(
            self,
            "parser_version",
            _validate_identifier("RuleIR parser_version", self.parser_version),
        )
        clauses = _validate_component_tuple("RuleIR clauses", self.clauses, RuleClause)
        if not clauses:
            raise RuleIRError("RuleIR clauses must not be empty.")
        diagnostics = _validate_component_tuple(
            "RuleIR diagnostics",
            self.diagnostics,
            RuleParseDiagnostic,
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("RuleIR schema_version", self.schema_version),
        )
        _validate_unique_clause_ids(clauses)
        _validate_all_spans_belong_to_text(self.normalized_text, clauses, diagnostics)
        object.__setattr__(self, "clauses", clauses)
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def is_supported(self) -> bool:
        return all(clause.is_supported for clause in self.clauses) and not any(
            diagnostic.blocking for diagnostic in self.diagnostics
        )

    def ir_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()

    def to_payload(self) -> RuleIRPayload:
        payload = self._payload_without_hash()
        payload["ir_hash"] = self.ir_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: RuleIRPayload) -> Self:
        rule_ir = cls(
            rule_id=payload["rule_id"],
            source_id=payload["source_id"],
            normalized_text=payload["normalized_text"],
            parser_version=payload["parser_version"],
            schema_version=payload["schema_version"],
            clauses=tuple(RuleClause.from_payload(clause) for clause in payload["clauses"]),
            diagnostics=tuple(
                RuleParseDiagnostic.from_payload(diagnostic)
                for diagnostic in payload["diagnostics"]
            ),
        )
        if rule_ir.ir_hash() != payload["ir_hash"]:
            raise RuleIRError("RuleIR ir_hash is stale.")
        return rule_ir

    def _payload_without_hash(self) -> RuleIRPayload:
        return {
            "rule_id": self.rule_id,
            "source_id": self.source_id,
            "normalized_text": self.normalized_text,
            "parser_version": self.parser_version,
            "schema_version": self.schema_version,
            "clauses": [clause.to_payload() for clause in self.clauses],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "ir_hash": "",
        }


def rule_trigger_kind_from_token(token: object) -> RuleTriggerKind:
    if type(token) is RuleTriggerKind:
        return token
    if type(token) is not str:
        raise RuleIRError("RuleTriggerKind token must be a string.")
    try:
        return RuleTriggerKind(token)
    except ValueError as exc:
        raise RuleIRError(f"Unsupported RuleTriggerKind token: {token}.") from exc


def rule_condition_kind_from_token(token: object) -> RuleConditionKind:
    if type(token) is RuleConditionKind:
        return token
    if type(token) is not str:
        raise RuleIRError("RuleConditionKind token must be a string.")
    try:
        return RuleConditionKind(token)
    except ValueError as exc:
        raise RuleIRError(f"Unsupported RuleConditionKind token: {token}.") from exc


def rule_target_kind_from_token(token: object) -> RuleTargetKind:
    if type(token) is RuleTargetKind:
        return token
    if type(token) is not str:
        raise RuleIRError("RuleTargetKind token must be a string.")
    try:
        return RuleTargetKind(token)
    except ValueError as exc:
        raise RuleIRError(f"Unsupported RuleTargetKind token: {token}.") from exc


def rule_effect_kind_from_token(token: object) -> RuleEffectKind:
    if type(token) is RuleEffectKind:
        return token
    if type(token) is not str:
        raise RuleIRError("RuleEffectKind token must be a string.")
    try:
        return RuleEffectKind(token)
    except ValueError as exc:
        raise RuleIRError(f"Unsupported RuleEffectKind token: {token}.") from exc


def rule_duration_kind_from_token(token: object) -> RuleDurationKind:
    if type(token) is RuleDurationKind:
        return token
    if type(token) is not str:
        raise RuleIRError("RuleDurationKind token must be a string.")
    try:
        return RuleDurationKind(token)
    except ValueError as exc:
        raise RuleIRError(f"Unsupported RuleDurationKind token: {token}.") from exc


def rule_unsupported_reason_from_token(token: object) -> RuleUnsupportedReason:
    if type(token) is RuleUnsupportedReason:
        return token
    if type(token) is not str:
        raise RuleIRError("RuleUnsupportedReason token must be a string.")
    try:
        return RuleUnsupportedReason(token)
    except ValueError as exc:
        raise RuleIRError(f"Unsupported RuleUnsupportedReason token: {token}.") from exc


def parameters_from_pairs(
    pairs: tuple[tuple[str, RuleParameterValue], ...],
) -> tuple[RuleParameter, ...]:
    return tuple(RuleParameter(key=key, value=value) for key, value in pairs)


def parameter_payload(parameters: tuple[RuleParameter, ...]) -> dict[str, RuleParameterValue]:
    return {parameter.key: parameter.value for parameter in parameters}


def _span_from_payload(payload: TextSpanPayload) -> TextSpan:
    return TextSpan(text=payload["text"], start=payload["start"], end=payload["end"])


_validate_identifier = IdentifierValidator(RuleIRError)


def _validate_parameter_value(field_name: str, value: object) -> RuleParameterValue:
    if value is None:
        return None
    if type(value) is str:
        return value
    if type(value) is int:
        return value
    if type(value) is bool:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise RuleIRError(f"{field_name} float must be finite.")
        return value
    if type(value) is tuple:
        return _validate_parameter_string_tuple(field_name, cast(tuple[object, ...], value))
    raise RuleIRError(f"{field_name} must be JSON scalar data or a string tuple.")


def _validate_parameter_string_tuple(
    field_name: str,
    value: tuple[object, ...],
) -> tuple[str, ...]:
    validated: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise RuleIRError(f"{field_name} tuple values must be non-empty strings.")
        validated.append(item.strip())
    return tuple(validated)


def _validate_span_object(field_name: str, span: object) -> TextSpan:
    if type(span) is not TextSpan:
        raise RuleIRError(f"{field_name} must be a TextSpan.")
    return span


def _validate_parameters(
    field_name: str,
    parameters: tuple[RuleParameter, ...],
) -> tuple[RuleParameter, ...]:
    if type(parameters) is not tuple:
        raise RuleIRError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[RuleParameter] = []
    for parameter in parameters:
        if type(parameter) is not RuleParameter:
            raise RuleIRError(f"{field_name} must contain RuleParameter values.")
        _validate_typed_parameter_shape(parameter)
        if parameter.key in seen:
            raise RuleIRError(f"{field_name} must not contain duplicate keys.")
        seen.add(parameter.key)
        validated.append(parameter)
    return tuple(sorted(validated, key=lambda parameter: parameter.key))


def _validate_typed_parameter_shape(parameter: RuleParameter) -> None:
    tuple_parameter_keys = {
        "model_keyword_any",
        "movement_modes",
        "required_keyword_any",
        "required_keyword_sequence",
        "roll_types",
        "weapon_names",
    }
    if parameter.key in tuple_parameter_keys:
        if type(parameter.value) is not tuple:
            raise RuleIRError(f"RuleParameter {parameter.key} must be a string tuple.")
        if not parameter.value:
            raise RuleIRError(f"RuleParameter {parameter.key} must not be empty.")
        return
    if parameter.key == "weapon_scope" and parameter.value not in {"all", "melee", "ranged"}:
        raise RuleIRError("RuleParameter weapon_scope must be all, melee, or ranged.")


def _validate_component_tuple[T](
    field_name: str,
    values: tuple[T, ...],
    expected_type: type[T],
) -> tuple[T, ...]:
    if type(values) is not tuple:
        raise RuleIRError(f"{field_name} must be a tuple.")
    for value in values:
        if type(value) is not expected_type:
            raise RuleIRError(f"{field_name} contains an invalid value.")
    return values


def _validate_unique_clause_ids(clauses: tuple[RuleClause, ...]) -> None:
    seen: set[str] = set()
    previous_key: tuple[int, int, str] | None = None
    for clause in clauses:
        if clause.clause_id in seen:
            raise RuleIRError("RuleIR clause IDs must be unique.")
        seen.add(clause.clause_id)
        key = (clause.source_span.start, clause.source_span.end, clause.clause_id)
        if previous_key is not None and key < previous_key:
            raise RuleIRError("RuleIR clauses must be deterministically ordered.")
        previous_key = key


def _validate_all_spans_belong_to_text(
    normalized_text: str,
    clauses: tuple[RuleClause, ...],
    diagnostics: tuple[RuleParseDiagnostic, ...],
) -> None:
    for clause in clauses:
        _validate_span_belongs_to_text(
            normalized_text, "RuleClause source_span", clause.source_span
        )
        if clause.trigger is not None:
            _validate_span_belongs_to_text(
                normalized_text,
                "RuleTrigger source_span",
                clause.trigger.source_span,
            )
        for condition in clause.conditions:
            _validate_span_belongs_to_text(
                normalized_text,
                "RuleCondition source_span",
                condition.source_span,
            )
        if clause.target is not None:
            _validate_span_belongs_to_text(
                normalized_text,
                "RuleTargetSpec source_span",
                clause.target.source_span,
            )
        for effect in clause.effects:
            _validate_span_belongs_to_text(
                normalized_text,
                "RuleEffectSpec source_span",
                effect.source_span,
            )
        if clause.duration is not None:
            _validate_span_belongs_to_text(
                normalized_text,
                "RuleDuration source_span",
                clause.duration.source_span,
            )
        for diagnostic in clause.diagnostics:
            _validate_span_belongs_to_text(
                normalized_text,
                "RuleParseDiagnostic source_span",
                diagnostic.source_span,
            )
    for diagnostic in diagnostics:
        _validate_span_belongs_to_text(
            normalized_text,
            "RuleIR diagnostic source_span",
            diagnostic.source_span,
        )


def _validate_span_belongs_to_text(
    normalized_text: str,
    field_name: str,
    span: TextSpan,
) -> None:
    if span.end > len(normalized_text):
        raise RuleIRError(f"{field_name} is outside normalized_text.")
    if normalized_text[span.start : span.end] != span.text:
        raise RuleIRError(f"{field_name} text does not match normalized_text.")


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
