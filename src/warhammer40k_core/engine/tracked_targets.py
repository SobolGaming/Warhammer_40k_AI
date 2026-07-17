from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.source_backed_rerolls import SourceBackedRerollPermissionContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_TRACKED_TARGET_DECISION_TYPE = "select_tracked_target"
TRACKED_TARGET_SELECTED_EVENT_TYPE = "tracked_target_selected"
TRACKED_TARGET_REPLACED_EVENT_TYPE = "tracked_target_replaced"
TRACKED_TARGET_EXPIRED_EVENT_TYPE = "tracked_target_expired"
TRACKED_TARGET_SUPPORTED_ATTACK_KINDS = ("melee", "ranged")
TRACKED_TARGET_SUPPORTED_ROLL_TYPES = ("attack_sequence.hit", "attack_sequence.wound")


class TrackedTargetRole(StrEnum):
    PREY = "prey"
    QUARRY = "quarry"


class TrackedTargetOwnerScope(StrEnum):
    THIS_MODEL = "this_model"
    THIS_UNIT = "this_unit"


class TrackedTargetRecordPayload(TypedDict):
    record_id: str
    source_rule_id: str
    source_ability_id: str
    source_clause_id: str
    source_effect_index: int
    owner_player_id: str
    source_unit_instance_id: str
    source_model_instance_id: str | None
    owner_scope: str
    role: str
    supported_attack_roll_pairs: list[JsonValue]
    supported_attack_kinds: list[str]
    supported_roll_types: list[str]
    target_unit_instance_id: str
    target_allegiance: str
    target_lifecycle: str
    selected_battle_round: int
    selection_request_id: str
    selection_result_id: str
    active: bool


@dataclass(frozen=True, slots=True)
class TrackedTargetRecord:
    record_id: str
    source_rule_id: str
    source_ability_id: str
    source_clause_id: str
    source_effect_index: int
    owner_player_id: str
    source_unit_instance_id: str
    source_model_instance_id: str | None
    owner_scope: TrackedTargetOwnerScope
    role: TrackedTargetRole
    supported_attack_roll_pairs: tuple[tuple[str, str], ...]
    target_unit_instance_id: str
    target_allegiance: str
    target_lifecycle: str
    selected_battle_round: int
    selection_request_id: str
    selection_result_id: str
    active: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _validate_identifier("record_id", self.record_id))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_ability_id",
            _validate_identifier("source_ability_id", self.source_ability_id),
        )
        object.__setattr__(
            self,
            "source_clause_id",
            _validate_identifier("source_clause_id", self.source_clause_id),
        )
        object.__setattr__(
            self,
            "source_effect_index",
            _validate_non_negative_int("source_effect_index", self.source_effect_index),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("owner_player_id", self.owner_player_id),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_identifier("source_unit_instance_id", self.source_unit_instance_id),
        )
        object.__setattr__(
            self,
            "source_model_instance_id",
            _validate_optional_identifier(
                "source_model_instance_id",
                self.source_model_instance_id,
            ),
        )
        object.__setattr__(self, "owner_scope", _owner_scope_from_token(self.owner_scope))
        object.__setattr__(self, "role", _role_from_token(self.role))
        object.__setattr__(
            self,
            "supported_attack_roll_pairs",
            _validate_supported_attack_roll_pairs(self.supported_attack_roll_pairs),
        )
        if (
            self.owner_scope is TrackedTargetOwnerScope.THIS_MODEL
            and self.source_model_instance_id is None
        ):
            raise GameLifecycleError("Tracked target this_model records require source model.")
        if (
            self.owner_scope is TrackedTargetOwnerScope.THIS_UNIT
            and self.source_model_instance_id is not None
        ):
            raise GameLifecycleError(
                "Tracked target this_unit records must not store source model."
            )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_allegiance",
            _validate_supported_token(
                "target_allegiance",
                self.target_allegiance,
                supported=("enemy", "friendly"),
            ),
        )
        object.__setattr__(
            self,
            "target_lifecycle",
            _validate_supported_token(
                "target_lifecycle",
                self.target_lifecycle,
                supported=("until_destroyed",),
            ),
        )
        object.__setattr__(
            self,
            "selected_battle_round",
            _validate_positive_int("selected_battle_round", self.selected_battle_round),
        )
        object.__setattr__(
            self,
            "selection_request_id",
            _validate_identifier("selection_request_id", self.selection_request_id),
        )
        object.__setattr__(
            self,
            "selection_result_id",
            _validate_identifier("selection_result_id", self.selection_result_id),
        )
        if type(self.active) is not bool:
            raise GameLifecycleError("Tracked target active must be a bool.")

    def inactive(self) -> TrackedTargetRecord:
        if not self.active:
            return self
        return replace(self, active=False)

    def active_key(self) -> tuple[str, str, str | None, TrackedTargetOwnerScope, TrackedTargetRole]:
        return (
            self.source_rule_id,
            self.source_unit_instance_id,
            self.source_model_instance_id,
            self.owner_scope,
            self.role,
        )

    def to_payload(self) -> TrackedTargetRecordPayload:
        attack_roll_pairs = self.supported_attack_roll_pairs
        return {
            "record_id": self.record_id,
            "source_rule_id": self.source_rule_id,
            "source_ability_id": self.source_ability_id,
            "source_clause_id": self.source_clause_id,
            "source_effect_index": self.source_effect_index,
            "owner_player_id": self.owner_player_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "source_model_instance_id": self.source_model_instance_id,
            "owner_scope": self.owner_scope.value,
            "role": self.role.value,
            "supported_attack_roll_pairs": _attack_roll_pair_payloads(attack_roll_pairs),
            "supported_attack_kinds": list(_supported_attack_kinds_for_pairs(attack_roll_pairs)),
            "supported_roll_types": list(_supported_roll_types_for_pairs(attack_roll_pairs)),
            "target_unit_instance_id": self.target_unit_instance_id,
            "target_allegiance": self.target_allegiance,
            "target_lifecycle": self.target_lifecycle,
            "selected_battle_round": self.selected_battle_round,
            "selection_request_id": self.selection_request_id,
            "selection_result_id": self.selection_result_id,
            "active": self.active,
        }

    @classmethod
    def from_payload(cls, payload: TrackedTargetRecordPayload) -> TrackedTargetRecord:
        attack_roll_pairs = _validate_supported_attack_roll_pair_payloads(
            payload["supported_attack_roll_pairs"],
            key="supported_attack_roll_pairs",
        )
        _assert_supported_pair_projection_matches(
            supported_attack_roll_pairs=attack_roll_pairs,
            supported_attack_kinds=_validate_supported_attack_kinds(
                tuple(payload["supported_attack_kinds"])
            ),
            supported_roll_types=_validate_supported_roll_types(
                tuple(payload["supported_roll_types"])
            ),
        )
        return cls(
            record_id=payload["record_id"],
            source_rule_id=payload["source_rule_id"],
            source_ability_id=payload["source_ability_id"],
            source_clause_id=payload["source_clause_id"],
            source_effect_index=payload["source_effect_index"],
            owner_player_id=payload["owner_player_id"],
            source_unit_instance_id=payload["source_unit_instance_id"],
            source_model_instance_id=payload["source_model_instance_id"],
            owner_scope=_owner_scope_from_token(payload["owner_scope"]),
            role=_role_from_token(payload["role"]),
            supported_attack_roll_pairs=attack_roll_pairs,
            target_unit_instance_id=payload["target_unit_instance_id"],
            target_allegiance=payload["target_allegiance"],
            target_lifecycle=payload["target_lifecycle"],
            selected_battle_round=payload["selected_battle_round"],
            selection_request_id=payload["selection_request_id"],
            selection_result_id=payload["selection_result_id"],
            active=payload["active"],
        )


def build_select_tracked_target_request(
    *,
    state: GameState,
    actor_player_id: str,
    source_rule_id: str,
    source_ability_id: str,
    source_clause_id: str,
    source_effect_index: int,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
    owner_scope: TrackedTargetOwnerScope,
    role: TrackedTargetRole,
    supported_attack_roll_pairs: tuple[tuple[str, str], ...],
    target_allegiance: str,
    target_scope: str,
    replacement: bool,
) -> DecisionRequest | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Tracked target request requires GameState.")
    player_id = _validate_identifier("actor_player_id", actor_player_id)
    source_rule = _validate_identifier("source_rule_id", source_rule_id)
    source_ability = _validate_identifier("source_ability_id", source_ability_id)
    source_clause = _validate_identifier("source_clause_id", source_clause_id)
    source_effect = _validate_non_negative_int("source_effect_index", source_effect_index)
    source_unit = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    source_model = _validate_optional_identifier(
        "source_model_instance_id",
        source_model_instance_id,
    )
    scope = _owner_scope_from_token(owner_scope)
    tracked_role = _role_from_token(role)
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    source_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=source_unit)
    if scope is TrackedTargetOwnerScope.THIS_UNIT:
        source_unit = source_rules_unit.unit_instance_id
    else:
        if source_model is None:
            raise GameLifecycleError("THIS_MODEL tracked target requires a source model.")
        source_unit = source_rules_unit.component_unit_id_for_model(source_model)
    attack_roll_pairs = _validate_supported_attack_roll_pairs(supported_attack_roll_pairs)
    attack_kinds = _supported_attack_kinds_for_pairs(attack_roll_pairs)
    roll_types = _supported_roll_types_for_pairs(attack_roll_pairs)
    allegiance = _validate_supported_token(
        "target_allegiance",
        target_allegiance,
        supported=("enemy", "friendly"),
    )
    scope_token = _validate_supported_token(
        "target_scope",
        target_scope,
        supported=("enemy_unit", "friendly_unit"),
    )
    if (allegiance == "enemy") != (scope_token == "enemy_unit"):
        raise GameLifecycleError("Tracked target allegiance and target_scope drift.")
    if type(replacement) is not bool:
        raise GameLifecycleError("Tracked target replacement must be a bool.")
    if (
        not replacement
        and state.active_tracked_target_for(
            source_rule_id=source_rule,
            source_unit_instance_id=source_unit,
            source_model_instance_id=source_model,
            owner_scope=scope,
            role=tracked_role,
        )
        is not None
    ):
        return None
    legal_targets = _legal_target_unit_ids(
        state=state,
        owner_player_id=player_id,
        target_allegiance=allegiance,
    )
    if not legal_targets:
        return None
    common_payload = validate_json_value(
        {
            "submission_kind": SELECT_TRACKED_TARGET_DECISION_TYPE,
            "source_rule_id": source_rule,
            "source_ability_id": source_ability,
            "source_clause_id": source_clause,
            "source_effect_index": source_effect,
            "owner_scope": scope.value,
            "tracked_target_role": tracked_role.value,
            "supported_attack_roll_pairs": _attack_roll_pair_payloads(attack_roll_pairs),
            "supported_attack_kinds": list(attack_kinds),
            "supported_roll_types": list(roll_types),
            "target_allegiance": allegiance,
            "target_scope": scope_token,
            "replacement": replacement,
            "legal_target_unit_ids": list(legal_targets),
            "source_unit_instance_id": source_unit,
            "source_model_instance_id": source_model,
        }
    )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_TRACKED_TARGET_DECISION_TYPE,
        actor_id=player_id,
        payload=common_payload,
        options=tuple(
            DecisionOption(
                option_id=unit_id,
                label=unit_id,
                payload=validate_json_value(
                    {
                        **cast(dict[str, JsonValue], common_payload),
                        "target_unit_instance_id": unit_id,
                    }
                ),
            )
            for unit_id in legal_targets
        ),
    )


def apply_select_tracked_target_decision(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions_event_log: object,
) -> TrackedTargetRecord:
    from warhammer40k_core.engine.event_log import EventLog
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Tracked target decision requires GameState.")
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Tracked target decision requires DecisionRequest.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Tracked target decision requires DecisionResult.")
    if type(decisions_event_log) is not EventLog:
        raise GameLifecycleError("Tracked target decision requires EventLog.")
    result.validate_for_request(request)
    request_payload = _payload_object(request.payload)
    result_payload = _payload_object(result.payload)
    if result_payload.get("submission_kind") != SELECT_TRACKED_TARGET_DECISION_TYPE:
        raise GameLifecycleError("Tracked target submission_kind drift.")
    _assert_payload_context_matches(request_payload=request_payload, result_payload=result_payload)
    target_unit_id = _validate_identifier(
        "target_unit_instance_id",
        result_payload.get("target_unit_instance_id"),
    )
    legal_target_ids = _payload_identifier_list(request_payload, key="legal_target_unit_ids")
    if target_unit_id not in set(legal_target_ids):
        raise GameLifecycleError("Tracked target result selected a non-option target.")
    actor_id = _validate_identifier("actor_id", result.actor_id)
    current_legal_ids = _legal_target_unit_ids(
        state=state,
        owner_player_id=actor_id,
        target_allegiance=_payload_string(request_payload, key="target_allegiance"),
    )
    if target_unit_id not in set(current_legal_ids):
        raise GameLifecycleError("Tracked target selected unit is no longer legal.")
    owner_scope = _owner_scope_from_token(_payload_string(request_payload, key="owner_scope"))
    role = _role_from_token(_payload_string(request_payload, key="tracked_target_role"))
    supported_attack_roll_pairs = _payload_supported_attack_roll_pairs(
        request_payload,
        key="supported_attack_roll_pairs",
    )
    supported_roll_types = _payload_supported_roll_types(
        request_payload,
        key="supported_roll_types",
    )
    supported_attack_kinds = _payload_supported_attack_kinds(
        request_payload,
        key="supported_attack_kinds",
    )
    _assert_supported_pair_projection_matches(
        supported_attack_roll_pairs=supported_attack_roll_pairs,
        supported_attack_kinds=supported_attack_kinds,
        supported_roll_types=supported_roll_types,
    )
    replacement = _payload_bool(request_payload, key="replacement")
    source_rule_id = _payload_string(request_payload, key="source_rule_id")
    source_unit_id = _payload_string(request_payload, key="source_unit_instance_id")
    source_model_id = _payload_optional_string(request_payload, key="source_model_instance_id")
    replaced_records: tuple[TrackedTargetRecord, ...] = ()
    if replacement:
        active_record = state.active_tracked_target_for(
            source_rule_id=source_rule_id,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=source_model_id,
            owner_scope=owner_scope,
            role=role,
        )
        if active_record is not None:
            replaced_records = (state.expire_tracked_target(active_record.record_id),)
    record = TrackedTargetRecord(
        record_id=(
            f"tracked-target:{result.result_id}:{source_rule_id}:"
            f"{source_unit_id}:{source_model_id or 'unit'}:{role.value}"
        ),
        source_rule_id=source_rule_id,
        source_ability_id=_payload_string(request_payload, key="source_ability_id"),
        source_clause_id=_payload_string(request_payload, key="source_clause_id"),
        source_effect_index=_payload_int(request_payload, key="source_effect_index"),
        owner_player_id=actor_id,
        source_unit_instance_id=source_unit_id,
        source_model_instance_id=source_model_id,
        owner_scope=owner_scope,
        role=role,
        supported_attack_roll_pairs=supported_attack_roll_pairs,
        target_unit_instance_id=target_unit_id,
        target_allegiance=_payload_string(request_payload, key="target_allegiance"),
        target_lifecycle="until_destroyed",
        selected_battle_round=_tracked_target_selection_battle_round(state),
        selection_request_id=request.request_id,
        selection_result_id=result.result_id,
        active=True,
    )
    state.record_tracked_target(record)
    event_type = (
        TRACKED_TARGET_REPLACED_EVENT_TYPE if replacement else TRACKED_TARGET_SELECTED_EVENT_TYPE
    )
    decisions_event_log.append(
        event_type,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "request_id": request.request_id,
            "result_id": result.result_id,
            "tracked_target_record": record.to_payload(),
            "replaced_record_ids": [stored.record_id for stored in replaced_records],
        },
    )
    return record


def _tracked_target_selection_battle_round(state: GameState) -> int:
    if state.battle_round >= 1:
        return state.battle_round
    if (
        state.stage is GameLifecycleStage.SETUP
        and state.setup_step_index is not None
        and state.setup_step_index + 1 == len(state.setup_sequence)
    ):
        return 1
    raise GameLifecycleError("Tracked target selection requires battle round context.")


def invalid_select_tracked_target_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Tracked target invalid status requires GameState.")
    if type(request) is not DecisionRequest or type(result) is not DecisionResult:
        raise GameLifecycleError("Tracked target invalid status requires request/result.")
    try:
        result.validate_for_request(request)
        request_payload = _payload_object(request.payload)
        result_payload = _payload_object(result.payload)
        if result_payload.get("submission_kind") != SELECT_TRACKED_TARGET_DECISION_TYPE:
            invalid_reason = "submission_kind_drift"
        else:
            _assert_payload_context_matches(
                request_payload=request_payload,
                result_payload=result_payload,
            )
            target_unit_id = _validate_identifier(
                "target_unit_instance_id",
                result_payload.get("target_unit_instance_id"),
            )
            if target_unit_id not in set(
                _payload_identifier_list(request_payload, key="legal_target_unit_ids")
            ):
                invalid_reason = "selected_target_not_in_options"
            elif target_unit_id not in set(
                _legal_target_unit_ids(
                    state=state,
                    owner_player_id=_validate_identifier("actor_id", result.actor_id),
                    target_allegiance=_payload_string(request_payload, key="target_allegiance"),
                )
            ):
                invalid_reason = "selected_target_no_longer_legal"
            else:
                return None
    except (DecisionError, GameLifecycleError, ValueError, TypeError, KeyError) as exc:
        invalid_reason = f"malformed:{type(exc).__name__}"
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Tracked target selection is invalid.",
        payload={
            "game_id": state.game_id,
            "request_id": request.request_id,
            "result_id": result.result_id,
            "invalid_reason": invalid_reason,
        },
    )


def tracked_target_reroll_permission_context_for_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    model_instance_id: str | None,
    roll_type: str,
    timing_window: str,
    attack_kind: str | None,
    target_unit_instance_id: str | None,
) -> SourceBackedRerollPermissionContext | None:
    requested_player = _validate_identifier("player_id", player_id)
    requested_unit = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_model = _validate_optional_identifier("model_instance_id", model_instance_id)
    requested_roll_type = _validate_identifier("roll_type", roll_type)
    requested_timing = _validate_identifier("timing_window", timing_window)
    requested_attack_kind = (
        None if attack_kind is None else _validate_supported_attack_kind("attack_kind", attack_kind)
    )
    requested_target = (
        None
        if target_unit_instance_id is None
        else _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    )
    if requested_target is None:
        return None
    contexts: list[SourceBackedRerollPermissionContext] = []
    for record in state.tracked_target_records:
        if not record.active:
            continue
        if record.owner_player_id != requested_player:
            continue
        if record.source_unit_instance_id != requested_unit:
            continue
        if record.owner_scope is TrackedTargetOwnerScope.THIS_MODEL and (
            requested_model is None or record.source_model_instance_id != requested_model
        ):
            continue
        if record.target_unit_instance_id != requested_target:
            continue
        if requested_attack_kind is None:
            continue
        if (requested_attack_kind, requested_roll_type) not in set(
            record.supported_attack_roll_pairs
        ):
            continue
        if requested_timing != requested_roll_type:
            continue
        supported_attack_roll_pairs = record.supported_attack_roll_pairs
        permission = RerollPermission(
            source_id=f"{record.record_id}:{requested_roll_type}:reroll",
            timing_window=requested_timing,
            owning_player_id=requested_player,
            eligible_roll_type=requested_roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
        contexts.append(
            SourceBackedRerollPermissionContext(
                permission=permission,
                source_payload={
                    "effect_kind": "tracked_target_reroll",
                    "tracked_target_record_id": record.record_id,
                    "source_rule_id": record.source_rule_id,
                    "source_ability_id": record.source_ability_id,
                    "source_clause_id": record.source_clause_id,
                    "source_unit_instance_id": record.source_unit_instance_id,
                    "source_model_instance_id": record.source_model_instance_id,
                    "owner_scope": record.owner_scope.value,
                    "tracked_target_role": record.role.value,
                    "supported_attack_roll_pairs": _attack_roll_pair_payloads(
                        supported_attack_roll_pairs
                    ),
                    "supported_attack_kinds": list(
                        _supported_attack_kinds_for_pairs(supported_attack_roll_pairs)
                    ),
                    "supported_roll_types": list(
                        _supported_roll_types_for_pairs(supported_attack_roll_pairs)
                    ),
                    "attack_kind": requested_attack_kind,
                    "roll_type": requested_roll_type,
                    "target_unit_instance_id": record.target_unit_instance_id,
                },
            )
        )
    if len(contexts) > 1:
        raise GameLifecycleError("Multiple tracked-target reroll permissions are available.")
    return contexts[0] if contexts else None


def _legal_target_unit_ids(
    *,
    state: GameState,
    owner_player_id: str,
    target_allegiance: str,
) -> tuple[str, ...]:
    owner = _validate_identifier("owner_player_id", owner_player_id)
    allegiance = _validate_supported_token(
        "target_allegiance",
        target_allegiance,
        supported=("enemy", "friendly"),
    )
    removed_model_ids = set(
        () if state.battlefield_state is None else state.battlefield_state.removed_model_ids
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    legal: set[str] = set()
    for army in state.army_definitions:
        owner_matches = army.player_id == owner
        if allegiance == "enemy" and owner_matches:
            continue
        if allegiance == "friendly" and not owner_matches:
            continue
        for unit in army.units:
            rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
            if not any(
                model.is_alive and model.model_instance_id not in removed_model_ids
                for model in rules_unit.own_models
            ):
                continue
            legal.add(rules_unit.unit_instance_id)
    return tuple(sorted(legal))


def _assert_payload_context_matches(
    *,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    for key in (
        "submission_kind",
        "source_rule_id",
        "source_ability_id",
        "source_clause_id",
        "source_effect_index",
        "owner_scope",
        "tracked_target_role",
        "supported_attack_roll_pairs",
        "supported_attack_kinds",
        "supported_roll_types",
        "target_allegiance",
        "target_scope",
        "replacement",
        "legal_target_unit_ids",
        "source_unit_instance_id",
        "source_model_instance_id",
    ):
        if result_payload.get(key) != request_payload.get(key):
            raise GameLifecycleError(f"Tracked target payload drift for {key}.")


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Tracked target payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Tracked target payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _payload_optional_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    if key not in payload:
        raise GameLifecycleError(f"Tracked target payload missing {key}.")
    return _validate_optional_identifier(key, payload[key])


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Tracked target payload missing {key}.")
    return _validate_non_negative_int(key, payload[key])


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    if key not in payload or type(payload[key]) is not bool:
        raise GameLifecycleError(f"Tracked target payload {key} must be a bool.")
    return cast(bool, payload[key])


def _payload_identifier_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Tracked target payload {key} must be a list.")
    return tuple(_validate_identifier(key, item) for item in value)


def _payload_supported_attack_roll_pairs(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[tuple[str, str], ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Tracked target payload {key} must be a list.")
    return _validate_supported_attack_roll_pair_payloads(value, key=key)


def _payload_supported_roll_types(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Tracked target payload {key} must be a list.")
    return _validate_supported_roll_types(tuple(value))


def _payload_supported_attack_kinds(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Tracked target payload {key} must be a list.")
    return _validate_supported_attack_kinds(tuple(value))


def _role_from_token(token: object) -> TrackedTargetRole:
    if type(token) is TrackedTargetRole:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Tracked target role must be a string.")
    try:
        return TrackedTargetRole(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported tracked target role: {token}.") from exc


def _owner_scope_from_token(token: object) -> TrackedTargetOwnerScope:
    if type(token) is TrackedTargetOwnerScope:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Tracked target owner_scope must be a string.")
    try:
        return TrackedTargetOwnerScope(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported tracked target owner_scope: {token}.") from exc


def _validate_supported_token(
    field_name: str,
    value: object,
    *,
    supported: tuple[str, ...],
) -> str:
    token = _validate_identifier(field_name, value)
    if token not in set(supported):
        raise GameLifecycleError(f"Unsupported tracked target {field_name}: {token}.")
    return token


def _validate_supported_attack_kind(field_name: str, value: object) -> str:
    return _validate_supported_token(
        field_name,
        value,
        supported=TRACKED_TARGET_SUPPORTED_ATTACK_KINDS,
    )


def _validate_supported_attack_roll_pairs(
    attack_roll_pairs: tuple[object, ...],
) -> tuple[tuple[str, str], ...]:
    if type(attack_roll_pairs) is not tuple:
        raise GameLifecycleError("Tracked target supported_attack_roll_pairs must be a tuple.")
    validated: list[tuple[str, str]] = []
    for pair in attack_roll_pairs:
        if type(pair) is not tuple:
            raise GameLifecycleError(
                "Tracked target supported_attack_roll_pairs entries must be two-item tuples."
            )
        pair_tuple = cast(tuple[object, ...], pair)
        if len(pair_tuple) != 2:
            raise GameLifecycleError(
                "Tracked target supported_attack_roll_pairs entries must be two-item tuples."
            )
        attack_kind = _validate_supported_attack_kind(
            "supported_attack_roll_pairs.attack_kind",
            pair_tuple[0],
        )
        roll_type = _validate_supported_token(
            "supported_attack_roll_pairs.roll_type",
            pair_tuple[1],
            supported=TRACKED_TARGET_SUPPORTED_ROLL_TYPES,
        )
        validated.append((attack_kind, roll_type))
    if not validated:
        raise GameLifecycleError("Tracked target supported_attack_roll_pairs must not be empty.")
    if len(set(validated)) != len(validated):
        raise GameLifecycleError("Tracked target supported_attack_roll_pairs must be unique.")
    supported = set(validated)
    return tuple(
        (attack_kind, roll_type)
        for attack_kind in TRACKED_TARGET_SUPPORTED_ATTACK_KINDS
        for roll_type in TRACKED_TARGET_SUPPORTED_ROLL_TYPES
        if (attack_kind, roll_type) in supported
    )


def _validate_supported_attack_roll_pair_payloads(
    value: object,
    *,
    key: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"Tracked target payload {key} must be a list.")
    pairs: list[tuple[object, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise GameLifecycleError(f"Tracked target payload {key} entries must be objects.")
        pair_payload = cast(dict[object, object], item)
        if set(pair_payload) != {"attack_kind", "roll_type"}:
            raise GameLifecycleError(
                f"Tracked target payload {key} entries must contain attack_kind and roll_type."
            )
        pairs.append((pair_payload["attack_kind"], pair_payload["roll_type"]))
    return _validate_supported_attack_roll_pairs(tuple(pairs))


def _attack_roll_pair_payloads(
    attack_roll_pairs: tuple[tuple[str, str], ...],
) -> list[JsonValue]:
    payloads: list[JsonValue] = []
    for attack_kind, roll_type in attack_roll_pairs:
        payloads.append(validate_json_value({"attack_kind": attack_kind, "roll_type": roll_type}))
    return payloads


def _supported_attack_kinds_for_pairs(
    attack_roll_pairs: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    supported = {attack_kind for attack_kind, _ in attack_roll_pairs}
    return tuple(
        attack_kind
        for attack_kind in TRACKED_TARGET_SUPPORTED_ATTACK_KINDS
        if attack_kind in supported
    )


def _supported_roll_types_for_pairs(
    attack_roll_pairs: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    supported = {roll_type for _, roll_type in attack_roll_pairs}
    return tuple(
        roll_type for roll_type in TRACKED_TARGET_SUPPORTED_ROLL_TYPES if roll_type in supported
    )


def _assert_supported_pair_projection_matches(
    *,
    supported_attack_roll_pairs: tuple[tuple[str, str], ...],
    supported_attack_kinds: tuple[str, ...],
    supported_roll_types: tuple[str, ...],
) -> None:
    if _supported_attack_kinds_for_pairs(supported_attack_roll_pairs) != supported_attack_kinds:
        raise GameLifecycleError(
            "Tracked target supported_attack_kinds drift from attack-roll pairs."
        )
    if _supported_roll_types_for_pairs(supported_attack_roll_pairs) != supported_roll_types:
        raise GameLifecycleError(
            "Tracked target supported_roll_types drift from attack-roll pairs."
        )


def _validate_supported_attack_kinds(attack_kinds: tuple[object, ...]) -> tuple[str, ...]:
    if type(attack_kinds) is not tuple:
        raise GameLifecycleError("Tracked target supported_attack_kinds must be a tuple.")
    validated = tuple(
        _validate_supported_attack_kind("supported_attack_kinds", attack_kind)
        for attack_kind in attack_kinds
    )
    if not validated:
        raise GameLifecycleError("Tracked target supported_attack_kinds must not be empty.")
    if len(set(validated)) != len(validated):
        raise GameLifecycleError("Tracked target supported_attack_kinds must be unique.")
    return tuple(
        attack_kind
        for attack_kind in TRACKED_TARGET_SUPPORTED_ATTACK_KINDS
        if attack_kind in set(validated)
    )


def _validate_supported_roll_types(roll_types: tuple[object, ...]) -> tuple[str, ...]:
    if type(roll_types) is not tuple:
        raise GameLifecycleError("Tracked target supported_roll_types must be a tuple.")
    validated = tuple(
        _validate_supported_token(
            "supported_roll_types",
            roll_type,
            supported=TRACKED_TARGET_SUPPORTED_ROLL_TYPES,
        )
        for roll_type in roll_types
    )
    if not validated:
        raise GameLifecycleError("Tracked target supported_roll_types must not be empty.")
    if len(set(validated)) != len(validated):
        raise GameLifecycleError("Tracked target supported_roll_types must be unique.")
    return tuple(
        roll_type
        for roll_type in TRACKED_TARGET_SUPPORTED_ROLL_TYPES
        if roll_type in set(validated)
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"Tracked target {field_name} must be non-negative int.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Tracked target {field_name} must be positive int.")
    return value
