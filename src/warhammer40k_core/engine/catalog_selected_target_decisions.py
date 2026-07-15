from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogRecord
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    active_player_id,
    payload_object,
    payload_string,
    payload_string_tuple,
    selected_payload,
    validate_effect_record_tuple,
    validate_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class SelectedTargetOption:
    option_id: str
    target_unit_instance_id: str
    effect_records: tuple[dict[str, JsonValue], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", _validate_identifier("option_id", self.option_id))
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "effect_records",
            validate_effect_record_tuple(self.effect_records),
        )


@dataclass(frozen=True, slots=True)
class SelectedTargetGroup:
    record: AbilityCatalogRecord
    player_id: str
    unit: UnitInstance
    source_model_instance_id: str | None
    selection_clause: RuleClause
    effect_clauses: tuple[RuleClause, ...]
    options: tuple[SelectedTargetOption, ...]
    phase: BattlePhase
    hook_id: str
    submission_kind: str
    optional: bool = False
    attack_sequence: AttackSequence | None = None
    attack_sequence_completed_event_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.record) is not AbilityCatalogRecord:
            raise GameLifecycleError("Catalog selected-target group requires ability record.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        validate_unit(self.unit)
        if self.source_model_instance_id is not None:
            object.__setattr__(
                self,
                "source_model_instance_id",
                _validate_identifier("source_model_instance_id", self.source_model_instance_id),
            )
        if type(self.selection_clause) is not RuleClause:
            raise GameLifecycleError("Catalog selected-target group requires selection clause.")
        if type(self.effect_clauses) is not tuple or not self.effect_clauses:
            raise GameLifecycleError("Catalog selected-target group requires effect clauses.")
        for clause in self.effect_clauses:
            if type(clause) is not RuleClause:
                raise GameLifecycleError("Catalog selected-target effect clauses are invalid.")
        if type(self.options) is not tuple or not self.options:
            raise GameLifecycleError("Catalog selected-target group requires options.")
        options = tuple(_validate_option(option) for option in self.options)
        if len({option.option_id for option in options}) != len(options):
            raise GameLifecycleError("Catalog selected-target options must not duplicate IDs.")
        object.__setattr__(self, "options", tuple(sorted(options, key=lambda item: item.option_id)))
        if type(self.phase) is not BattlePhase:
            raise GameLifecycleError("Catalog selected-target group requires BattlePhase.")
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(
            self,
            "submission_kind",
            _validate_identifier("submission_kind", self.submission_kind),
        )
        if type(self.optional) is not bool:
            raise GameLifecycleError("Catalog selected-target optional flag must be bool.")
        if self.attack_sequence is not None and type(self.attack_sequence) is not AttackSequence:
            raise GameLifecycleError("Catalog selected-target group attack_sequence is invalid.")
        if self.attack_sequence_completed_event_id is not None:
            object.__setattr__(
                self,
                "attack_sequence_completed_event_id",
                _validate_identifier(
                    "attack_sequence_completed_event_id",
                    self.attack_sequence_completed_event_id,
                ),
            )

    @property
    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.unit.unit_instance_id,
            self.record.record_id,
            self.selection_clause.clause_id,
            "" if self.source_model_instance_id is None else self.source_model_instance_id,
            (
                ""
                if self.attack_sequence_completed_event_id is None
                else self.attack_sequence_completed_event_id
            ),
        )


def selected_target_request(
    *,
    state: GameState,
    group: SelectedTargetGroup,
    decision_type: str,
) -> DecisionRequest:
    common_payload = selected_target_base_payload(state=state, group=group)
    target_options = tuple(
        DecisionOption(
            option_id=option.option_id,
            label=f"Select {option.target_unit_instance_id}",
            payload=validate_json_value(
                {
                    **common_payload,
                    **({"use_ability": True} if group.optional else {}),
                    "selected_catalog_target_effect": selected_target_option_selection_payload(
                        option
                    ),
                    "generic_rule_effect_records": list(option.effect_records),
                }
            ),
        )
        for option in group.options
    )
    decline_options: tuple[DecisionOption, ...] = ()
    if group.optional:
        decline_options = (
            DecisionOption(
                option_id=f"{group.hook_id}:{group.record.record_id}:decline",
                label="Do not use this ability",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "use_ability": False,
                        "selected_catalog_target_effect": None,
                        "generic_rule_effect_records": [],
                    }
                ),
            ),
        )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=decision_type,
        actor_id=group.player_id,
        payload=validate_json_value(
            {
                **common_payload,
                "available_target_unit_instance_ids": [
                    option.target_unit_instance_id for option in group.options
                ],
                "available_catalog_selected_target_options": [
                    selected_target_option_selection_payload(option) for option in group.options
                ],
                **({"optional": True} if group.optional else {}),
            }
        ),
        options=(*target_options, *decline_options),
    )


def selected_target_base_payload(
    *,
    state: GameState,
    group: SelectedTargetGroup,
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    rule_ir = rule_ir_from_execution_payload(group.record.definition.replay_payload)
    payload: dict[str, JsonValue] = {
        "submission_kind": group.submission_kind,
        "hook_id": group.hook_id,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": group.phase.value,
        "active_player_id": active_player_id(state),
        "player_id": group.player_id,
        "catalog_record_id": group.record.record_id,
        "ability_id": group.record.definition.ability_id,
        "ability_name": group.record.definition.name,
        "source_rule_id": group.record.definition.source_id,
        "rule_ir_hash": rule_ir.ir_hash(),
        "source_unit_instance_id": group.unit.unit_instance_id,
        "source_model_instance_id": group.source_model_instance_id,
        "selection_clause_id": group.selection_clause.clause_id,
        "effect_clause_ids": [clause.clause_id for clause in group.effect_clauses],
    }
    if group.attack_sequence is not None:
        payload["attack_sequence_id"] = group.attack_sequence.sequence_id
        payload["attack_sequence"] = validate_json_value(group.attack_sequence.to_payload())
    if group.attack_sequence_completed_event_id is not None:
        payload["attack_sequence_completed_event_id"] = group.attack_sequence_completed_event_id
    if group.optional:
        payload["optional"] = True
    return payload


def invalid_selected_target_effect_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    expected_decision_type: str,
    expected_submission_kind: str,
    expected_phase: BattlePhase,
    invalid_reason: str,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason=invalid_reason,
    )
    if invalid_status is not None:
        return invalid_status
    payload = payload_object(result.payload)
    request_payload = payload_object(request.payload)
    drift_field = _selected_target_drift_field(
        state=state,
        request=request,
        payload=payload,
        request_payload=request_payload,
        expected_decision_type=expected_decision_type,
        expected_submission_kind=expected_submission_kind,
        expected_phase=expected_phase,
    )
    if drift_field is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog selected-target result drifted.",
        payload=validate_json_value({"invalid_reason": invalid_reason, "field": drift_field}),
    )


def selected_target_option_id(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    source_model_instance_id: str | None,
    selection_clause: RuleClause,
    target_unit_instance_id: str,
    attack_sequence_completed_event_id: str | None,
) -> str:
    parts = [
        "catalog-ir",
        "selected-target",
        record.record_id,
        unit.unit_instance_id,
        "model",
        "unit" if source_model_instance_id is None else source_model_instance_id,
        selection_clause.clause_id,
    ]
    if attack_sequence_completed_event_id is not None:
        parts.append(attack_sequence_completed_event_id)
    parts.extend(("target", target_unit_instance_id))
    return ":".join(parts)


def selected_target_option_selection_payload(
    option: SelectedTargetOption,
) -> dict[str, JsonValue]:
    return {
        "option_id": option.option_id,
        "target_unit_instance_id": option.target_unit_instance_id,
    }


def post_shoot_group_key(group: SelectedTargetGroup) -> tuple[str, str, str, str, str]:
    if group.attack_sequence is None or group.attack_sequence_completed_event_id is None:
        raise GameLifecycleError("Catalog post-shoot group missing attack sequence.")
    return (
        group.attack_sequence_completed_event_id,
        group.attack_sequence.sequence_id,
        group.record.record_id,
        group.unit.unit_instance_id,
        group.selection_clause.clause_id,
    )


def resolved_post_shoot_target_effect_group_keys(
    decisions: DecisionController,
    *,
    event_type: str,
) -> frozenset[tuple[str, str, str, str, str]]:
    requested_event_type = _validate_identifier("event_type", event_type)
    keys: set[tuple[str, str, str, str, str]] = set()
    for event in decisions.event_log.records:
        if event.event_type != requested_event_type:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Catalog post-shoot selected event payload is malformed.")
        payload_value = cast(dict[str, object], payload)
        keys.add(
            (
                payload_string(payload_value, key="attack_sequence_completed_event_id"),
                payload_string(payload_value, key="attack_sequence_id"),
                payload_string(payload_value, key="catalog_record_id"),
                payload_string(payload_value, key="source_unit_instance_id"),
                payload_string(payload_value, key="selection_clause_id"),
            )
        )
    return frozenset(keys)


def resolved_shooting_start_group_keys(
    decisions: DecisionController,
    *,
    event_type: str,
) -> frozenset[tuple[str, str, str, str, str]]:
    requested_event_type = _validate_identifier("event_type", event_type)
    keys: set[tuple[str, str, str, str, str]] = set()
    for event in decisions.event_log.records:
        if event.event_type != requested_event_type:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Catalog Shooting-start selected event payload is malformed.")
        payload_value = cast(dict[str, object], payload)
        source_model_id = payload_value.get("source_model_instance_id")
        if source_model_id is not None and type(source_model_id) is not str:
            raise GameLifecycleError(
                "Catalog Shooting-start selected event source model is malformed."
            )
        keys.add(
            (
                payload_string(payload_value, key="source_unit_instance_id"),
                payload_string(payload_value, key="catalog_record_id"),
                payload_string(payload_value, key="selection_clause_id"),
                "" if source_model_id is None else source_model_id,
                "",
            )
        )
    return frozenset(keys)


def _selected_target_drift_field(
    *,
    state: GameState,
    request: DecisionRequest,
    payload: dict[str, object],
    request_payload: dict[str, object],
    expected_decision_type: str,
    expected_submission_kind: str,
    expected_phase: BattlePhase,
) -> str | None:
    if request.decision_type != expected_decision_type:
        return "request_decision_type"
    if state.current_battle_phase is not expected_phase:
        return "state_phase"
    if payload_string(payload, key="submission_kind") != expected_submission_kind:
        return "submission_kind"
    for key in (
        "hook_id",
        "game_id",
        "battle_round",
        "phase",
        "active_player_id",
        "player_id",
        "catalog_record_id",
        "source_rule_id",
        "source_unit_instance_id",
        "selection_clause_id",
    ):
        if payload.get(key) != request_payload.get(key):
            return key
    if payload.get("game_id") != state.game_id:
        return "game_id"
    if payload.get("battle_round") != state.battle_round:
        return "battle_round"
    if payload.get("phase") != expected_phase.value:
        return "phase"
    if payload.get("active_player_id") != state.active_player_id:
        return "active_player_id"
    is_optional = request_payload.get("optional") is True
    use_ability = payload.get("use_ability", True)
    if type(use_ability) is not bool:
        return "use_ability"
    if not is_optional and use_ability is not True:
        return "use_ability"
    if not use_ability:
        if payload.get("selected_catalog_target_effect") is not None:
            return "selected_catalog_target_effect"
        if payload.get("generic_rule_effect_records") != []:
            return "generic_rule_effect_records"
        return None
    selected = selected_payload(payload)
    selected_target_id = payload_string(selected, key="target_unit_instance_id")
    available_target_ids = payload_string_tuple(
        request_payload,
        key="available_target_unit_instance_ids",
    )
    if selected_target_id not in available_target_ids:
        return "target_unit_instance_id"
    if state.battlefield_state is None:
        return "battlefield_state"
    if state.battlefield_state.unit_placement_or_none(selected_target_id) is None:
        return "target_unit_instance_id"
    return None


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="request_id")
    if result.decision_type != request.decision_type:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="decision_type")
    if result.actor_id != request.actor_id:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="actor_id")
    option_payload_by_id = {option.option_id: option.payload for option in request.options}
    selected_option_payload = option_payload_by_id.get(result.selected_option_id)
    if selected_option_payload is None:
        return _invalid_status(
            state=state,
            invalid_reason=invalid_reason,
            field="selected_option_id",
        )
    if result.payload != selected_option_payload:
        return _invalid_status(state=state, invalid_reason=invalid_reason, field="payload")
    return None


def _invalid_status(*, state: GameState, invalid_reason: str, field: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog selected-target result is invalid.",
        payload=validate_json_value({"invalid_reason": invalid_reason, "field": field}),
    )


def _validate_option(value: object) -> SelectedTargetOption:
    if type(value) is not SelectedTargetOption:
        raise GameLifecycleError("Catalog selected-target option is invalid.")
    return value
