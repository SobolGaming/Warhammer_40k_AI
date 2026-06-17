from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowError,
    TimingWindowPayload,
    timing_trigger_kind_from_token,
)

OPPORTUNITY_ACTION_SUBMISSION_KIND = "opportunity_action"
OPPORTUNITY_REQUEST_FAMILY = "opportunity_window"
OPPORTUNITY_SUBMISSION_PAYLOAD_KEY = "opportunity_submission"


class OpportunityWindowError(ValueError):
    """Raised when an opportunity-window contract violates CORE V2 invariants."""


class OpportunityActionKind(StrEnum):
    STRATAGEM = "stratagem"
    ABILITY = "ability"
    REROLL = "reroll"
    REACTION = "reaction"
    SIDE_ACTION = "side_action"
    PASS = "pass"


class TriggerBatchingMode(StrEnum):
    NONE = "none"
    ONE_OF = "one_of"
    ANY_SUBSET = "any_subset"
    QUANTITY = "quantity"
    WHOLE_GROUP = "whole_group"


class IntentMaterializationStatus(StrEnum):
    MATERIALIZED = "materialized"
    REQUEST_MISMATCH = "request_mismatch"
    EXPIRED = "expired"
    STALE_STATE_HASH = "stale_state_hash"
    WRONG_TIMING = "wrong_timing"
    PLAYER_NOT_ELIGIBLE = "player_not_eligible"
    ACTION_UNAVAILABLE = "action_unavailable"
    TARGET_MISMATCH = "target_mismatch"


class OpportunityLegalActionPayload(TypedDict):
    action_id: str
    source_id: str
    action_kind: str
    controller_id: str | None
    label: str
    cost: list[JsonValue]
    target_ids: list[str]
    target_spec: JsonValue
    batching_mode: str
    payload: JsonValue


class OpportunityWindowPayload(TypedDict):
    window_id: str
    timing_window: TimingWindowPayload
    state_hash: str
    sequence_number: int
    revision: int
    anchor_event_ids: list[str]
    acting_player_id: str | None
    eligible_player_ids: list[str]
    priority_order: list[str]
    legal_actions: list[OpportunityLegalActionPayload]
    default_action_id: str
    closes_on: str
    metadata: JsonValue


class WindowPassPayload(TypedDict):
    window_id: str
    player_id: str
    revision: int
    legal_action_fingerprint: str


class WindowPassLedgerPayload(TypedDict):
    passes: list[WindowPassPayload]


class InterfaceIntentPayload(TypedDict):
    intent_id: str
    player_id: str
    action_id: str
    source_id: str
    target_ids: list[str]
    trigger_kind: str | None
    created_sequence_number: int
    expires_after_sequence: int
    based_on_state_hash: str | None
    payload: JsonValue


class IntentMaterializationPayload(TypedDict):
    status: str
    diagnostic: JsonValue
    result: DecisionResultPayload | None


class OpportunityBoundaryHashPayload(TypedDict):
    state: JsonValue
    event_count: int
    last_event_id: str | None


class OpportunityBoundaryGameStatePayload(TypedDict):
    game_id: str
    ruleset_descriptor_hash: str
    stage: str
    battle_phase_index: int | None
    battle_round: int
    active_player_id: str | None
    player_ids: list[str]
    turn_order: list[str]
    decision_request_count: int
    command_point_ledgers: JsonValue
    stratagem_use_records: JsonValue
    faction_rule_states: JsonValue


def _new_passes() -> list[WindowPass]:
    return []


@dataclass(frozen=True, slots=True)
class OpportunityLegalAction:
    action_id: str
    source_id: str
    action_kind: OpportunityActionKind
    controller_id: str | None
    label: str
    cost: tuple[JsonValue, ...] = ()
    target_ids: tuple[str, ...] = ()
    target_spec: JsonValue = None
    batching_mode: TriggerBatchingMode = TriggerBatchingMode.NONE
    payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("OpportunityLegalAction action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("OpportunityLegalAction source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "action_kind",
            opportunity_action_kind_from_token(self.action_kind),
        )
        object.__setattr__(
            self,
            "controller_id",
            _validate_optional_identifier(
                "OpportunityLegalAction controller_id",
                self.controller_id,
            ),
        )
        object.__setattr__(
            self,
            "label",
            _validate_identifier("OpportunityLegalAction label", self.label),
        )
        object.__setattr__(
            self,
            "cost",
            _validate_json_tuple("OpportunityLegalAction cost", self.cost),
        )
        object.__setattr__(
            self,
            "target_ids",
            _validate_identifier_tuple(
                "OpportunityLegalAction target_ids",
                self.target_ids,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(self, "target_spec", validate_json_value(self.target_spec))
        object.__setattr__(
            self,
            "batching_mode",
            trigger_batching_mode_from_token(self.batching_mode),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))
        if self.action_kind is not OpportunityActionKind.PASS and self.controller_id is None:
            raise OpportunityWindowError("Non-pass opportunity actions require a controller.")

    def is_available_to(self, player_id: str) -> bool:
        requested_player = _validate_identifier("player_id", player_id)
        if self.controller_id == requested_player:
            return True
        return self.action_kind is OpportunityActionKind.PASS and self.controller_id is None

    def to_payload(self) -> OpportunityLegalActionPayload:
        return {
            "action_id": self.action_id,
            "source_id": self.source_id,
            "action_kind": self.action_kind.value,
            "controller_id": self.controller_id,
            "label": self.label,
            "cost": list(self.cost),
            "target_ids": list(self.target_ids),
            "target_spec": self.target_spec,
            "batching_mode": self.batching_mode.value,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: OpportunityLegalActionPayload) -> Self:
        return cls(
            action_id=payload["action_id"],
            source_id=payload["source_id"],
            action_kind=opportunity_action_kind_from_token(payload["action_kind"]),
            controller_id=payload["controller_id"],
            label=payload["label"],
            cost=tuple(payload["cost"]),
            target_ids=tuple(payload["target_ids"]),
            target_spec=payload["target_spec"],
            batching_mode=trigger_batching_mode_from_token(payload["batching_mode"]),
            payload=payload["payload"],
        )


@dataclass(frozen=True, slots=True)
class OpportunityWindow:
    window_id: str
    timing_window: TimingWindow
    state_hash: str
    sequence_number: int
    revision: int
    anchor_event_ids: tuple[str, ...]
    acting_player_id: str | None
    eligible_player_ids: tuple[str, ...]
    priority_order: tuple[str, ...]
    legal_actions: tuple[OpportunityLegalAction, ...]
    default_action_id: str
    closes_on: str = "all_players_pass_current_revision"
    metadata: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _validate_identifier("OpportunityWindow window_id", self.window_id),
        )
        if type(self.timing_window) is not TimingWindow:
            raise OpportunityWindowError("OpportunityWindow timing_window must be a TimingWindow.")
        object.__setattr__(
            self,
            "state_hash",
            _validate_identifier("OpportunityWindow state_hash", self.state_hash),
        )
        object.__setattr__(
            self,
            "sequence_number",
            _validate_non_negative_int("OpportunityWindow sequence_number", self.sequence_number),
        )
        object.__setattr__(
            self,
            "revision",
            _validate_positive_int("OpportunityWindow revision", self.revision),
        )
        object.__setattr__(
            self,
            "anchor_event_ids",
            _validate_identifier_tuple(
                "OpportunityWindow anchor_event_ids",
                self.anchor_event_ids,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "acting_player_id",
            _validate_optional_identifier(
                "OpportunityWindow acting_player_id",
                self.acting_player_id,
            ),
        )
        eligible = _validate_identifier_tuple(
            "OpportunityWindow eligible_player_ids",
            self.eligible_player_ids,
            min_length=1,
            sort_values=True,
        )
        object.__setattr__(self, "eligible_player_ids", eligible)
        priority = _validate_identifier_tuple(
            "OpportunityWindow priority_order",
            self.priority_order,
            min_length=1,
            sort_values=False,
        )
        if set(priority) != set(eligible):
            raise OpportunityWindowError(
                "OpportunityWindow priority_order must cover eligible players."
            )
        object.__setattr__(self, "priority_order", priority)
        legal_actions = _validate_legal_actions(self.legal_actions)
        for action in legal_actions:
            if action.controller_id is not None and action.controller_id not in eligible:
                raise OpportunityWindowError("Opportunity action controller must be eligible.")
        default_action = _action_by_id(legal_actions, self.default_action_id)
        if default_action.action_kind is not OpportunityActionKind.PASS:
            raise OpportunityWindowError("OpportunityWindow default action must be a pass action.")
        object.__setattr__(self, "legal_actions", legal_actions)
        object.__setattr__(
            self,
            "default_action_id",
            _validate_identifier("OpportunityWindow default_action_id", self.default_action_id),
        )
        object.__setattr__(
            self,
            "closes_on",
            _validate_identifier("OpportunityWindow closes_on", self.closes_on),
        )
        object.__setattr__(self, "metadata", validate_json_value(self.metadata))

    def action_by_id(self, action_id: str) -> OpportunityLegalAction:
        return _action_by_id(self.legal_actions, action_id)

    def legal_actions_for_player(self, player_id: str) -> tuple[OpportunityLegalAction, ...]:
        requested_player = _validate_identifier("player_id", player_id)
        if requested_player not in self.eligible_player_ids:
            raise OpportunityWindowError("Player is not eligible for this opportunity window.")
        actions = tuple(
            action for action in self.legal_actions if action.is_available_to(requested_player)
        )
        if not actions:
            raise OpportunityWindowError("Opportunity window has no legal actions for player.")
        return actions

    def legal_action_fingerprint(self, player_id: str) -> str:
        payload = [
            action.to_payload()
            for action in sorted(
                self.legal_actions_for_player(player_id),
                key=lambda item: item.action_id,
            )
        ]
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def decision_options_for_player(self, player_id: str) -> tuple[DecisionOption, ...]:
        requested_player = _validate_identifier("player_id", player_id)
        fingerprint = self.legal_action_fingerprint(requested_player)
        return tuple(
            DecisionOption(
                option_id=action.action_id,
                label=action.label,
                payload=self.submission_payload_for_action(
                    action=action,
                    player_id=requested_player,
                    legal_action_fingerprint=fingerprint,
                ),
            )
            for action in self.legal_actions_for_player(requested_player)
        )

    def decision_request(
        self,
        *,
        request_id: str,
        actor_id: str,
        decision_type: str,
        handler_payload: JsonValue = None,
    ) -> DecisionRequest:
        requested_actor = _validate_identifier("actor_id", actor_id)
        request_payload = validate_json_value(
            {
                "submission_family": OPPORTUNITY_REQUEST_FAMILY,
                "opportunity_window": self.to_payload(),
                "opportunity_window_id": self.window_id,
                "legal_action_fingerprint": self.legal_action_fingerprint(requested_actor),
                "handler_payload": handler_payload,
            }
        )
        return DecisionRequest(
            request_id=request_id,
            decision_type=decision_type,
            actor_id=requested_actor,
            payload=request_payload,
            options=self.decision_options_for_player(requested_actor),
        )

    def submission_payload_for_action(
        self,
        *,
        action: OpportunityLegalAction,
        player_id: str,
        legal_action_fingerprint: str,
    ) -> JsonValue:
        requested_player = _validate_identifier("player_id", player_id)
        if not action.is_available_to(requested_player):
            raise OpportunityWindowError("Opportunity action is not available to player.")
        return validate_json_value(
            {
                "submission_kind": OPPORTUNITY_ACTION_SUBMISSION_KIND,
                "window_id": self.window_id,
                "state_hash": self.state_hash,
                "sequence_number": self.sequence_number,
                "revision": self.revision,
                "legal_action_fingerprint": _validate_identifier(
                    "legal_action_fingerprint",
                    legal_action_fingerprint,
                ),
                "action": action.to_payload(),
            }
        )

    def to_payload(self) -> OpportunityWindowPayload:
        return {
            "window_id": self.window_id,
            "timing_window": self.timing_window.to_payload(),
            "state_hash": self.state_hash,
            "sequence_number": self.sequence_number,
            "revision": self.revision,
            "anchor_event_ids": list(self.anchor_event_ids),
            "acting_player_id": self.acting_player_id,
            "eligible_player_ids": list(self.eligible_player_ids),
            "priority_order": list(self.priority_order),
            "legal_actions": [action.to_payload() for action in self.legal_actions],
            "default_action_id": self.default_action_id,
            "closes_on": self.closes_on,
            "metadata": self.metadata,
        }

    @classmethod
    def from_payload(cls, payload: OpportunityWindowPayload) -> Self:
        return cls(
            window_id=payload["window_id"],
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
            state_hash=payload["state_hash"],
            sequence_number=payload["sequence_number"],
            revision=payload["revision"],
            anchor_event_ids=tuple(payload["anchor_event_ids"]),
            acting_player_id=payload["acting_player_id"],
            eligible_player_ids=tuple(payload["eligible_player_ids"]),
            priority_order=tuple(payload["priority_order"]),
            legal_actions=tuple(
                OpportunityLegalAction.from_payload(action) for action in payload["legal_actions"]
            ),
            default_action_id=payload["default_action_id"],
            closes_on=payload["closes_on"],
            metadata=payload["metadata"],
        )


@dataclass(frozen=True, slots=True)
class WindowPass:
    window_id: str
    player_id: str
    revision: int
    legal_action_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _validate_identifier("WindowPass window_id", self.window_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("WindowPass player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "revision",
            _validate_positive_int("WindowPass revision", self.revision),
        )
        object.__setattr__(
            self,
            "legal_action_fingerprint",
            _validate_identifier(
                "WindowPass legal_action_fingerprint",
                self.legal_action_fingerprint,
            ),
        )

    @classmethod
    def for_window(cls, *, window: OpportunityWindow, player_id: str) -> Self:
        return cls(
            window_id=window.window_id,
            player_id=player_id,
            revision=window.revision,
            legal_action_fingerprint=window.legal_action_fingerprint(player_id),
        )

    def matches(self, *, window: OpportunityWindow) -> bool:
        if window.window_id != self.window_id:
            return False
        if window.revision != self.revision:
            return False
        return window.legal_action_fingerprint(self.player_id) == self.legal_action_fingerprint

    def to_payload(self) -> WindowPassPayload:
        return {
            "window_id": self.window_id,
            "player_id": self.player_id,
            "revision": self.revision,
            "legal_action_fingerprint": self.legal_action_fingerprint,
        }

    @classmethod
    def from_payload(cls, payload: WindowPassPayload) -> Self:
        return cls(
            window_id=payload["window_id"],
            player_id=payload["player_id"],
            revision=payload["revision"],
            legal_action_fingerprint=payload["legal_action_fingerprint"],
        )


@dataclass(slots=True)
class WindowPassLedger:
    _passes: list[WindowPass] = field(default_factory=_new_passes)

    @property
    def passes(self) -> tuple[WindowPass, ...]:
        return tuple(self._passes)

    def record_pass(self, *, window: OpportunityWindow, player_id: str) -> WindowPass:
        recorded = WindowPass.for_window(window=window, player_id=player_id)
        self._passes = [
            item
            for item in self._passes
            if item.window_id != recorded.window_id or item.player_id != recorded.player_id
        ]
        self._passes.append(recorded)
        self._passes.sort(key=lambda item: (item.window_id, item.player_id))
        return recorded

    def has_current_pass(self, *, window: OpportunityWindow, player_id: str) -> bool:
        requested_player = _validate_identifier("player_id", player_id)
        return any(
            item.player_id == requested_player and item.matches(window=window)
            for item in self._passes
        )

    def should_prompt(self, *, window: OpportunityWindow, player_id: str) -> bool:
        return not self.has_current_pass(window=window, player_id=player_id)

    def to_payload(self) -> WindowPassLedgerPayload:
        return {"passes": [item.to_payload() for item in self._passes]}

    @classmethod
    def from_payload(cls, payload: WindowPassLedgerPayload) -> Self:
        ledger = cls()
        ledger._passes = [WindowPass.from_payload(item) for item in payload["passes"]]
        ledger._passes.sort(key=lambda item: (item.window_id, item.player_id))
        return ledger


@dataclass(frozen=True, slots=True)
class InterfaceIntent:
    intent_id: str
    player_id: str
    action_id: str
    source_id: str
    target_ids: tuple[str, ...]
    trigger_kind: TimingTriggerKind | None
    created_sequence_number: int
    expires_after_sequence: int
    based_on_state_hash: str | None = None
    payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intent_id",
            _validate_identifier("InterfaceIntent intent_id", self.intent_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("InterfaceIntent player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("InterfaceIntent action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("InterfaceIntent source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "target_ids",
            _validate_identifier_tuple(
                "InterfaceIntent target_ids",
                self.target_ids,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            _validate_optional_trigger_kind("InterfaceIntent trigger_kind", self.trigger_kind),
        )
        object.__setattr__(
            self,
            "created_sequence_number",
            _validate_non_negative_int(
                "InterfaceIntent created_sequence_number",
                self.created_sequence_number,
            ),
        )
        object.__setattr__(
            self,
            "expires_after_sequence",
            _validate_non_negative_int(
                "InterfaceIntent expires_after_sequence",
                self.expires_after_sequence,
            ),
        )
        if self.expires_after_sequence < self.created_sequence_number:
            raise OpportunityWindowError("InterfaceIntent expiration must not precede creation.")
        object.__setattr__(
            self,
            "based_on_state_hash",
            _validate_optional_identifier(
                "InterfaceIntent based_on_state_hash",
                self.based_on_state_hash,
            ),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def materialize(
        self,
        *,
        window: OpportunityWindow,
        request: DecisionRequest,
        current_sequence_number: int,
        result_id: str,
    ) -> IntentMaterialization:
        sequence_number = _validate_non_negative_int(
            "current_sequence_number",
            current_sequence_number,
        )
        if type(window) is not OpportunityWindow:
            raise OpportunityWindowError("Intent materialization requires an OpportunityWindow.")
        request_window = _request_window(request=request)
        if request_window is None:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.REQUEST_MISMATCH,
                diagnostic={"request_id": request.request_id, "window_id": window.window_id},
            )
        if window.to_payload() != request_window.to_payload():
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.REQUEST_MISMATCH,
                diagnostic={
                    "intent_id": self.intent_id,
                    "reason": "window_payload_mismatch",
                    "request_id": request.request_id,
                    "window_id": window.window_id,
                },
            )
        window = request_window
        if sequence_number > self.expires_after_sequence:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.EXPIRED,
                diagnostic={
                    "intent_id": self.intent_id,
                    "current_sequence_number": sequence_number,
                    "expires_after_sequence": self.expires_after_sequence,
                },
            )
        if self.based_on_state_hash is not None and self.based_on_state_hash != window.state_hash:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.STALE_STATE_HASH,
                diagnostic={
                    "intent_id": self.intent_id,
                    "intent_state_hash": self.based_on_state_hash,
                    "window_state_hash": window.state_hash,
                },
            )
        if (
            self.trigger_kind is not None
            and self.trigger_kind is not window.timing_window.descriptor.trigger_kind
        ):
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.WRONG_TIMING,
                diagnostic={
                    "intent_id": self.intent_id,
                    "intent_trigger_kind": self.trigger_kind.value,
                    "window_trigger_kind": window.timing_window.descriptor.trigger_kind.value,
                },
            )
        if self.player_id not in window.eligible_player_ids or request.actor_id != self.player_id:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.PLAYER_NOT_ELIGIBLE,
                diagnostic={
                    "intent_id": self.intent_id,
                    "player_id": self.player_id,
                    "window_id": window.window_id,
                },
            )

        try:
            action = window.action_by_id(self.action_id)
        except OpportunityWindowError:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.ACTION_UNAVAILABLE,
                diagnostic={
                    "intent_id": self.intent_id,
                    "action_id": self.action_id,
                    "source_id": self.source_id,
                },
            )
        if not action.is_available_to(self.player_id) or action.source_id != self.source_id:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.ACTION_UNAVAILABLE,
                diagnostic={
                    "intent_id": self.intent_id,
                    "action_id": self.action_id,
                    "source_id": self.source_id,
                },
            )
        if self.target_ids != action.target_ids:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.TARGET_MISMATCH,
                diagnostic={
                    "intent_id": self.intent_id,
                    "intent_target_ids": list(self.target_ids),
                    "action_target_ids": list(action.target_ids),
                },
            )
        try:
            result = DecisionResult.for_request(
                result_id=result_id,
                request=request,
                selected_option_id=action.action_id,
            )
        except DecisionError as exc:
            return IntentMaterialization.rejected(
                IntentMaterializationStatus.ACTION_UNAVAILABLE,
                diagnostic={"intent_id": self.intent_id, "reason": str(exc)},
            )
        return IntentMaterialization(
            status=IntentMaterializationStatus.MATERIALIZED,
            result=result,
            diagnostic={"intent_id": self.intent_id, "window_id": window.window_id},
        )

    def to_payload(self) -> InterfaceIntentPayload:
        return {
            "intent_id": self.intent_id,
            "player_id": self.player_id,
            "action_id": self.action_id,
            "source_id": self.source_id,
            "target_ids": list(self.target_ids),
            "trigger_kind": None if self.trigger_kind is None else self.trigger_kind.value,
            "created_sequence_number": self.created_sequence_number,
            "expires_after_sequence": self.expires_after_sequence,
            "based_on_state_hash": self.based_on_state_hash,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: InterfaceIntentPayload) -> Self:
        trigger_token = payload["trigger_kind"]
        return cls(
            intent_id=payload["intent_id"],
            player_id=payload["player_id"],
            action_id=payload["action_id"],
            source_id=payload["source_id"],
            target_ids=tuple(payload["target_ids"]),
            trigger_kind=None
            if trigger_token is None
            else timing_trigger_kind_from_token(trigger_token),
            created_sequence_number=payload["created_sequence_number"],
            expires_after_sequence=payload["expires_after_sequence"],
            based_on_state_hash=payload["based_on_state_hash"],
            payload=payload["payload"],
        )


@dataclass(frozen=True, slots=True)
class IntentMaterialization:
    status: IntentMaterializationStatus
    result: DecisionResult | None
    diagnostic: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "status",
            intent_materialization_status_from_token(self.status),
        )
        if self.result is not None and type(self.result) is not DecisionResult:
            raise OpportunityWindowError("IntentMaterialization result must be a DecisionResult.")
        object.__setattr__(self, "diagnostic", validate_json_value(self.diagnostic))
        if self.status is IntentMaterializationStatus.MATERIALIZED and self.result is None:
            raise OpportunityWindowError("Materialized intents require a DecisionResult.")
        if self.status is not IntentMaterializationStatus.MATERIALIZED and self.result is not None:
            raise OpportunityWindowError("Rejected intents must not carry a DecisionResult.")

    @classmethod
    def rejected(
        cls,
        status: IntentMaterializationStatus,
        *,
        diagnostic: JsonValue,
    ) -> Self:
        status_value = intent_materialization_status_from_token(status)
        if status_value is IntentMaterializationStatus.MATERIALIZED:
            raise OpportunityWindowError("Rejected intent status cannot be materialized.")
        return cls(status=status_value, result=None, diagnostic=diagnostic)

    def to_payload(self) -> IntentMaterializationPayload:
        return {
            "status": self.status.value,
            "diagnostic": self.diagnostic,
            "result": None if self.result is None else self.result.to_payload(),
        }


def opportunity_boundary_state_hash(
    *,
    state_payload: JsonValue,
    event_count: int,
    last_event_id: str | None,
) -> str:
    payload: OpportunityBoundaryHashPayload = {
        "state": validate_json_value(state_payload),
        "event_count": _validate_non_negative_int("event_count", event_count),
        "last_event_id": _validate_optional_identifier("last_event_id", last_event_id),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def opportunity_boundary_game_state_payload(
    *,
    game_id: str,
    ruleset_descriptor_hash: str,
    stage: str,
    battle_phase_index: int | None,
    battle_round: int,
    active_player_id: str | None,
    player_ids: tuple[str, ...],
    turn_order: tuple[str, ...],
    decision_request_count: int,
    command_point_ledgers: JsonValue,
    stratagem_use_records: JsonValue,
    faction_rule_states: JsonValue,
) -> JsonValue:
    payload: OpportunityBoundaryGameStatePayload = {
        "game_id": _validate_identifier("game_id", game_id),
        "ruleset_descriptor_hash": _validate_identifier(
            "ruleset_descriptor_hash",
            ruleset_descriptor_hash,
        ),
        "stage": _validate_identifier("stage", stage),
        "battle_phase_index": (
            None
            if battle_phase_index is None
            else _validate_non_negative_int("battle_phase_index", battle_phase_index)
        ),
        "battle_round": _validate_non_negative_int("battle_round", battle_round),
        "active_player_id": _validate_optional_identifier("active_player_id", active_player_id),
        "player_ids": list(
            _validate_identifier_tuple(
                "player_ids",
                player_ids,
                min_length=1,
                sort_values=False,
            )
        ),
        "turn_order": list(
            _validate_identifier_tuple(
                "turn_order",
                turn_order,
                min_length=1,
                sort_values=False,
            )
        ),
        "decision_request_count": _validate_non_negative_int(
            "decision_request_count",
            decision_request_count,
        ),
        "command_point_ledgers": validate_json_value(command_point_ledgers),
        "stratagem_use_records": validate_json_value(stratagem_use_records),
        "faction_rule_states": validate_json_value(faction_rule_states),
    }
    return validate_json_value(payload)


def opportunity_submission_invalid_reason(
    *,
    request: DecisionRequest,
    result: DecisionResult,
    current_state_hash: str,
    current_sequence_number: int,
) -> str | None:
    if type(request) is not DecisionRequest:
        raise OpportunityWindowError("Opportunity validation requires a DecisionRequest.")
    if type(result) is not DecisionResult:
        raise OpportunityWindowError("Opportunity validation requires a DecisionResult.")
    request_payload = request.payload
    if not isinstance(request_payload, dict):
        return None
    if request_payload.get("submission_family") is None:
        return None
    if request_payload.get("submission_family") != OPPORTUNITY_REQUEST_FAMILY:
        return "malformed_opportunity_request"
    window_payload = request_payload.get("opportunity_window")
    if not isinstance(window_payload, dict):
        return "malformed_opportunity_request"
    try:
        window = OpportunityWindow.from_payload(cast(OpportunityWindowPayload, window_payload))
    except (KeyError, OpportunityWindowError):  # fmt: skip
        return "malformed_opportunity_request"
    if request_payload.get("opportunity_window_id") != window.window_id:
        return "opportunity_window_id_mismatch"
    expected_fingerprint = request_payload.get("legal_action_fingerprint")
    if type(expected_fingerprint) is not str:
        return "malformed_opportunity_request"
    actor_id = request.actor_id
    if actor_id is None:
        return "opportunity_actor_required"
    if window.legal_action_fingerprint(actor_id) != expected_fingerprint:
        return "opportunity_fingerprint_mismatch"
    if _validate_identifier("current_state_hash", current_state_hash) != window.state_hash:
        return "stale_opportunity_state_hash"
    if (
        _validate_non_negative_int("current_sequence_number", current_sequence_number)
        != window.sequence_number
    ):
        return "stale_opportunity_sequence"
    result_payload = result.payload
    if not isinstance(result_payload, dict):
        return "malformed_opportunity_submission"
    submission_payload = result_payload.get(OPPORTUNITY_SUBMISSION_PAYLOAD_KEY)
    if (
        submission_payload is None
        and result_payload.get("submission_kind") == OPPORTUNITY_ACTION_SUBMISSION_KIND
    ):
        submission_payload = result_payload
    if not isinstance(submission_payload, dict):
        return "malformed_opportunity_submission"
    return _opportunity_submission_payload_invalid_reason(
        window=window,
        actor_id=actor_id,
        selected_option_id=result.selected_option_id,
        expected_fingerprint=expected_fingerprint,
        submission_payload=submission_payload,
    )


def _opportunity_submission_payload_invalid_reason(
    *,
    window: OpportunityWindow,
    actor_id: str,
    selected_option_id: str,
    expected_fingerprint: str,
    submission_payload: dict[str, JsonValue],
) -> str | None:
    if submission_payload.get("submission_kind") != OPPORTUNITY_ACTION_SUBMISSION_KIND:
        return "malformed_opportunity_submission"
    if submission_payload.get("window_id") != window.window_id:
        return "opportunity_window_id_mismatch"
    if submission_payload.get("state_hash") != window.state_hash:
        return "stale_opportunity_state_hash"
    if submission_payload.get("sequence_number") != window.sequence_number:
        return "stale_opportunity_sequence"
    if submission_payload.get("revision") != window.revision:
        return "opportunity_revision_mismatch"
    if submission_payload.get("legal_action_fingerprint") != expected_fingerprint:
        return "opportunity_fingerprint_mismatch"
    action_payload = submission_payload.get("action")
    if not isinstance(action_payload, dict):
        return "malformed_opportunity_submission"
    try:
        action = OpportunityLegalAction.from_payload(
            cast(OpportunityLegalActionPayload, action_payload)
        )
    except (KeyError, OpportunityWindowError):  # fmt: skip
        return "malformed_opportunity_submission"
    if action.action_id != selected_option_id:
        return "opportunity_action_mismatch"
    try:
        current_action = window.action_by_id(action.action_id)
    except OpportunityWindowError:
        return "opportunity_action_unavailable"
    if current_action.to_payload() != action.to_payload():
        return "opportunity_action_drift"
    if not current_action.is_available_to(actor_id):
        return "opportunity_action_wrong_player"
    return None


def opportunity_action_kind_from_token(token: object) -> OpportunityActionKind:
    if type(token) is OpportunityActionKind:
        return token
    if type(token) is not str:
        raise OpportunityWindowError("OpportunityActionKind token must be a string.")
    try:
        return OpportunityActionKind(token)
    except ValueError as exc:
        raise OpportunityWindowError(f"Unsupported OpportunityActionKind token: {token}.") from exc


def trigger_batching_mode_from_token(token: object) -> TriggerBatchingMode:
    if type(token) is TriggerBatchingMode:
        return token
    if type(token) is not str:
        raise OpportunityWindowError("TriggerBatchingMode token must be a string.")
    try:
        return TriggerBatchingMode(token)
    except ValueError as exc:
        raise OpportunityWindowError(f"Unsupported TriggerBatchingMode token: {token}.") from exc


def intent_materialization_status_from_token(token: object) -> IntentMaterializationStatus:
    if type(token) is IntentMaterializationStatus:
        return token
    if type(token) is not str:
        raise OpportunityWindowError("IntentMaterializationStatus token must be a string.")
    try:
        return IntentMaterializationStatus(token)
    except ValueError as exc:
        raise OpportunityWindowError(
            f"Unsupported IntentMaterializationStatus token: {token}."
        ) from exc


def _request_window(*, request: DecisionRequest) -> OpportunityWindow | None:
    if type(request) is not DecisionRequest:
        raise OpportunityWindowError("Intent materialization requires a DecisionRequest.")
    payload = request.payload
    if not isinstance(payload, dict):
        return None
    opportunity_window_id = payload.get("opportunity_window_id")
    opportunity_window_payload = payload.get("opportunity_window")
    if not isinstance(opportunity_window_payload, dict):
        return None
    try:
        window = OpportunityWindow.from_payload(
            cast(OpportunityWindowPayload, opportunity_window_payload)
        )
    except (KeyError, OpportunityWindowError):  # fmt: skip
        return None
    if opportunity_window_id != window.window_id:
        return None
    return window


def _action_by_id(
    actions: tuple[OpportunityLegalAction, ...],
    action_id: object,
) -> OpportunityLegalAction:
    requested_id = _validate_identifier("action_id", action_id)
    for action in actions:
        if action.action_id == requested_id:
            return action
    raise OpportunityWindowError("Opportunity action_id is not legal in this window.")


def _validate_legal_actions(
    actions: object,
) -> tuple[OpportunityLegalAction, ...]:
    if type(actions) is not tuple:
        raise OpportunityWindowError("OpportunityWindow legal_actions must be a tuple.")
    raw_actions = cast(tuple[object, ...], actions)
    if not raw_actions:
        raise OpportunityWindowError("OpportunityWindow legal_actions must not be empty.")
    validated: list[OpportunityLegalAction] = []
    seen: set[str] = set()
    for action in raw_actions:
        if type(action) is not OpportunityLegalAction:
            raise OpportunityWindowError(
                "OpportunityWindow legal_actions must contain OpportunityLegalAction values."
            )
        if action.action_id in seen:
            raise OpportunityWindowError("OpportunityWindow legal_actions duplicate action_id.")
        seen.add(action.action_id)
        validated.append(action)
    return tuple(sorted(validated, key=lambda item: item.action_id))


def _validate_json_tuple(field_name: str, values: object) -> tuple[JsonValue, ...]:
    if type(values) is not tuple:
        raise OpportunityWindowError(f"{field_name} must be a tuple.")
    validated = validate_json_value(list(cast(tuple[object, ...], values)))
    if not isinstance(validated, list):
        raise OpportunityWindowError(f"{field_name} must validate as a JSON list.")
    return tuple(validated)


def _validate_optional_trigger_kind(
    field_name: str,
    value: object | None,
) -> TimingTriggerKind | None:
    if value is None:
        return None
    try:
        return timing_trigger_kind_from_token(value)
    except TimingWindowError as exc:
        raise OpportunityWindowError(f"{field_name} must be a supported trigger kind.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise OpportunityWindowError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise OpportunityWindowError(f"{field_name} must not be empty.")
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
        raise OpportunityWindowError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise OpportunityWindowError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise OpportunityWindowError(f"{field_name} must contain at least {min_length} value.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise OpportunityWindowError(f"{field_name} must be an integer.")
    if value < 0:
        raise OpportunityWindowError(f"{field_name} must not be negative.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise OpportunityWindowError(f"{field_name} must be an integer.")
    if value < 1:
        raise OpportunityWindowError(f"{field_name} must be at least 1.")
    return value
