from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockCompletedOutcomeAuthorityContext,
    BattleShockHookRegistry,
    BattleShockPendingOutcomeAuthority,
    BattleShockPendingOutcomeAuthorityContext,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockResolutionResult,
    is_battle_shock_reroll_request,
)
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    BattleShockResolutionAuthority,
    PendingBattleShockRerollAuthority,
    parse_battle_shock_resolution_authority,
    parse_pending_battle_shock_reroll_authority,
)
from warhammer40k_core.engine.battle_shock_source_family_authority import (
    validate_battle_shock_source_family_authority,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


class CatalogSelectedTargetBattleShockContinuationPhase(StrEnum):
    AWAITING_PROVIDER_OUTCOME = "awaiting_provider_outcome"
    AWAITING_REMAINING_EFFECTS = "awaiting_remaining_effects"
    AWAITING_REMAINING_BATTLE_SHOCK_REROLL = "awaiting_remaining_battle_shock_reroll"


class PendingCatalogSelectedTargetBattleShockContinuationPayload(TypedDict):
    continuation_phase: str
    selected_target_request: DecisionRequestPayload
    selected_target_result: DecisionResultPayload
    selected_target_payload: dict[str, JsonValue]
    phase: str
    final_event_type: str
    catalog_record_id: str
    source_rule_id: str
    source_unit_instance_id: str
    selection_clause_id: str
    effect_clause_id: str
    selected_target_unit_instance_id: str
    effect_index: int
    recorded_effects_before_battle_shock: list[dict[str, JsonValue]]
    resolved_battle_shock_payload: dict[str, JsonValue]
    remaining_effect_records: list[dict[str, JsonValue]]
    remaining_effect_start_index: int
    battle_shock_request_id: str
    battle_shock_result_id: str
    battle_shock_reroll_request_id: str | None
    battle_shock_reroll_result_id: str | None
    provider_pending_request: DecisionRequestPayload
    provider_battle_shock_result: BattleShockResultPayload
    provider_resolved_event_index: int


@dataclass(frozen=True, slots=True)
class CatalogSelectedTargetBattleShockRuntime:
    battle_shock_hooks: BattleShockHookRegistry
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]

    def __post_init__(self) -> None:
        if type(self.battle_shock_hooks) is not BattleShockHookRegistry:
            raise GameLifecycleError("Selected-target Battle-shock hooks must be a registry.")
        indexes = dict(self.ability_indexes_by_player_id)
        if any(type(player_id) is not str for player_id in indexes) or any(
            type(index) is not AbilityCatalogIndex for index in indexes.values()
        ):
            raise GameLifecycleError("Selected-target Battle-shock ability indexes are invalid.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(indexes))

    @classmethod
    def empty(cls) -> Self:
        return cls(
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            ability_indexes_by_player_id=MappingProxyType({}),
        )

    @classmethod
    def from_bundle(cls, bundle: RuntimeContentBundle) -> Self:
        return cls(
            battle_shock_hooks=bundle.battle_shock_hook_registry,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
        )

    def apply_reroll_if_applicable(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        result: DecisionResult,
        runtime_modifier_registry: RuntimeModifierRegistry,
    ) -> tuple[bool, LifecycleStatus | None]:
        from warhammer40k_core.engine.catalog_selected_target_battle_shock_reroll import (
            apply_catalog_selected_target_battle_shock_reroll_decision,
            is_catalog_selected_target_battle_shock_reroll_request,
        )

        record = decisions.record_for_result(result)
        if not is_catalog_selected_target_battle_shock_reroll_request(record.request):
            return False, None
        return True, apply_catalog_selected_target_battle_shock_reroll_decision(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=self.battle_shock_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
        )


@dataclass(frozen=True, slots=True)
class PendingCatalogSelectedTargetBattleShockContinuation:
    continuation_phase: CatalogSelectedTargetBattleShockContinuationPhase
    selected_target_request: DecisionRequest
    selected_target_result: DecisionResult
    selected_target_payload: dict[str, JsonValue]
    phase: BattlePhase
    final_event_type: str
    catalog_record_id: str
    source_rule_id: str
    source_unit_instance_id: str
    selection_clause_id: str
    effect_clause_id: str
    selected_target_unit_instance_id: str
    effect_index: int
    recorded_effects_before_battle_shock: tuple[dict[str, JsonValue], ...]
    resolved_battle_shock_payload: dict[str, JsonValue]
    remaining_effect_records: tuple[dict[str, JsonValue], ...]
    remaining_effect_start_index: int
    battle_shock_request_id: str
    battle_shock_result_id: str
    battle_shock_reroll_request_id: str | None
    battle_shock_reroll_result_id: str | None
    provider_pending_request: DecisionRequest
    provider_battle_shock_result: BattleShockResult
    provider_resolved_event_index: int

    def __post_init__(self) -> None:
        if type(self.continuation_phase) is not (CatalogSelectedTargetBattleShockContinuationPhase):
            raise GameLifecycleError("Catalog selected-target continuation phase is invalid.")
        if type(self.selected_target_request) is not DecisionRequest:
            raise GameLifecycleError("Catalog selected-target continuation request is invalid.")
        if type(self.selected_target_result) is not DecisionResult:
            raise GameLifecycleError("Catalog selected-target continuation result is invalid.")
        self.selected_target_result.validate_for_request(self.selected_target_request)
        object.__setattr__(
            self,
            "selected_target_payload",
            _json_object("selected_target_payload", self.selected_target_payload),
        )
        if self.selected_target_result.payload != self.selected_target_payload:
            raise GameLifecycleError("Catalog selected-target continuation payload drifted.")
        if type(self.phase) is not BattlePhase:
            raise GameLifecycleError("Catalog selected-target continuation phase is invalid.")
        for field_name in (
            "final_event_type",
            "catalog_record_id",
            "source_rule_id",
            "source_unit_instance_id",
            "selection_clause_id",
            "effect_clause_id",
            "selected_target_unit_instance_id",
            "battle_shock_request_id",
            "battle_shock_result_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        for field_name in (
            "battle_shock_reroll_request_id",
            "battle_shock_reroll_result_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        if (self.battle_shock_reroll_request_id is None) != (
            self.battle_shock_reroll_result_id is None
        ):
            raise GameLifecycleError("Catalog selected-target reroll identity is incomplete.")
        object.__setattr__(
            self,
            "recorded_effects_before_battle_shock",
            _json_object_tuple(
                "recorded_effects_before_battle_shock",
                self.recorded_effects_before_battle_shock,
            ),
        )
        object.__setattr__(
            self,
            "resolved_battle_shock_payload",
            _json_object(
                "resolved_battle_shock_payload",
                self.resolved_battle_shock_payload,
            ),
        )
        object.__setattr__(
            self,
            "remaining_effect_records",
            _json_object_tuple("remaining_effect_records", self.remaining_effect_records),
        )
        if type(self.effect_index) is not int or self.effect_index < 0:
            raise GameLifecycleError("Catalog selected-target effect index is invalid.")
        if type(self.remaining_effect_start_index) is not int or (
            self.remaining_effect_start_index < self.effect_index + 1
        ):
            raise GameLifecycleError(
                "Catalog selected-target remaining effect start index is invalid."
            )
        if type(self.provider_pending_request) is not DecisionRequest:
            raise GameLifecycleError("Catalog selected-target provider request is invalid.")
        if type(self.provider_battle_shock_result) is not BattleShockResult:
            raise GameLifecycleError("Catalog selected-target provider claim is invalid.")
        if type(self.provider_resolved_event_index) is not int or (
            self.provider_resolved_event_index < 0
        ):
            raise GameLifecycleError("Catalog selected-target provider event index is invalid.")
        _validate_retained_payload(self)

    def awaiting_remaining_effects(self) -> Self:
        return replace(
            self,
            continuation_phase=(
                CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS
            ),
        )

    def awaiting_remaining_battle_shock_reroll(self) -> Self:
        return replace(
            self,
            continuation_phase=(
                CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_BATTLE_SHOCK_REROLL
            ),
        )

    def with_provider_request(
        self,
        *,
        request: DecisionRequest,
        claim: BattleShockPendingOutcomeAuthority,
    ) -> Self:
        return replace(
            self,
            provider_pending_request=request,
            provider_battle_shock_result=claim.result,
            provider_resolved_event_index=claim.resolved_event_index,
        )

    def to_payload(self) -> PendingCatalogSelectedTargetBattleShockContinuationPayload:
        return {
            "continuation_phase": self.continuation_phase.value,
            "selected_target_request": self.selected_target_request.to_payload(),
            "selected_target_result": self.selected_target_result.to_payload(),
            "selected_target_payload": self.selected_target_payload,
            "phase": self.phase.value,
            "final_event_type": self.final_event_type,
            "catalog_record_id": self.catalog_record_id,
            "source_rule_id": self.source_rule_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "selection_clause_id": self.selection_clause_id,
            "effect_clause_id": self.effect_clause_id,
            "selected_target_unit_instance_id": self.selected_target_unit_instance_id,
            "effect_index": self.effect_index,
            "recorded_effects_before_battle_shock": list(self.recorded_effects_before_battle_shock),
            "resolved_battle_shock_payload": self.resolved_battle_shock_payload,
            "remaining_effect_records": list(self.remaining_effect_records),
            "remaining_effect_start_index": self.remaining_effect_start_index,
            "battle_shock_request_id": self.battle_shock_request_id,
            "battle_shock_result_id": self.battle_shock_result_id,
            "battle_shock_reroll_request_id": self.battle_shock_reroll_request_id,
            "battle_shock_reroll_result_id": self.battle_shock_reroll_result_id,
            "provider_pending_request": self.provider_pending_request.to_payload(),
            "provider_battle_shock_result": self.provider_battle_shock_result.to_payload(),
            "provider_resolved_event_index": self.provider_resolved_event_index,
        }

    @classmethod
    def from_payload(
        cls,
        payload: PendingCatalogSelectedTargetBattleShockContinuationPayload,
    ) -> Self:
        try:
            continuation_phase = CatalogSelectedTargetBattleShockContinuationPhase(
                payload["continuation_phase"]
            )
            phase = BattlePhase(payload["phase"])
        except ValueError as exc:
            raise GameLifecycleError(
                "Catalog selected-target continuation token is unsupported."
            ) from exc
        continuation = cls(
            continuation_phase=continuation_phase,
            selected_target_request=DecisionRequest.from_payload(
                payload["selected_target_request"]
            ),
            selected_target_result=DecisionResult.from_payload(payload["selected_target_result"]),
            selected_target_payload=payload["selected_target_payload"],
            phase=phase,
            final_event_type=payload["final_event_type"],
            catalog_record_id=payload["catalog_record_id"],
            source_rule_id=payload["source_rule_id"],
            source_unit_instance_id=payload["source_unit_instance_id"],
            selection_clause_id=payload["selection_clause_id"],
            effect_clause_id=payload["effect_clause_id"],
            selected_target_unit_instance_id=payload["selected_target_unit_instance_id"],
            effect_index=payload["effect_index"],
            recorded_effects_before_battle_shock=tuple(
                payload["recorded_effects_before_battle_shock"]
            ),
            resolved_battle_shock_payload=payload["resolved_battle_shock_payload"],
            remaining_effect_records=tuple(payload["remaining_effect_records"]),
            remaining_effect_start_index=payload["remaining_effect_start_index"],
            battle_shock_request_id=payload["battle_shock_request_id"],
            battle_shock_result_id=payload["battle_shock_result_id"],
            battle_shock_reroll_request_id=payload["battle_shock_reroll_request_id"],
            battle_shock_reroll_result_id=payload["battle_shock_reroll_result_id"],
            provider_pending_request=DecisionRequest.from_payload(
                payload["provider_pending_request"]
            ),
            provider_battle_shock_result=BattleShockResult.from_payload(
                payload["provider_battle_shock_result"]
            ),
            provider_resolved_event_index=payload["provider_resolved_event_index"],
        )
        if payload != continuation.to_payload():
            raise GameLifecycleError("Catalog selected-target continuation payload drifted.")
        return continuation


def retain_catalog_selected_target_battle_shock_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    resolution: BattleShockResolutionResult,
    phase: BattlePhase,
    final_event_type: str,
) -> LifecycleStatus:
    resolved_payload = resolution.resolved_payload
    status = resolution.pending_status
    if resolved_payload is None or status is None:
        raise GameLifecycleError(
            "Catalog selected-target continuation requires a resolved pending outcome."
        )
    request = _validate_pending_status_queue_head(decisions=decisions, status=status)
    authority = _resolution_authority(decisions=decisions, resolved_payload=resolved_payload)
    claim = _pending_claim(
        state=state,
        decisions=decisions,
        battle_shock_hooks=battle_shock_hooks,
        request=request,
        authority=authority,
    )
    continuation = _continuation_from_resolution(
        decisions=decisions,
        resolved_payload=resolved_payload,
        phase=phase,
        final_event_type=final_event_type,
        authority=authority,
        provider_request=request,
        provider_claim=claim,
    )
    existing = state.pending_catalog_selected_target_battle_shock_continuation
    if existing is not None:
        _validate_progressive_replacement(existing=existing, replacement=continuation)
    state.replace_catalog_selected_target_battle_shock_continuation(continuation)
    return status


def retain_catalog_selected_target_remaining_battle_shock_reroll(
    *,
    state: GameState,
    decisions: DecisionController,
    status: LifecycleStatus,
) -> LifecycleStatus:
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None or continuation.continuation_phase is not (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS
    ):
        raise GameLifecycleError(
            "Catalog selected-target later Battle-shock reroll lacks its retained parent."
        )
    request = _validate_pending_status_queue_head(decisions=decisions, status=status)
    if not is_battle_shock_reroll_request(
        request,
        source_kind="catalog_selected_target_effect",
    ):
        raise GameLifecycleError(
            "Catalog selected-target later Battle-shock status is not a reroll request."
        )
    authority = parse_pending_battle_shock_reroll_authority(request)
    _validate_remaining_battle_shock_reroll_ancestry(
        continuation=continuation,
        authority=authority,
    )
    state.replace_catalog_selected_target_battle_shock_continuation(
        continuation.awaiting_remaining_battle_shock_reroll()
    )
    return status


def complete_catalog_selected_target_remaining_battle_shock_reroll(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> None:
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None:
        return
    if continuation.continuation_phase is not (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_BATTLE_SHOCK_REROLL
    ):
        raise GameLifecycleError("Catalog selected-target later Battle-shock reroll phase drifted.")
    record = decisions.record_for_result(result)
    authority = parse_pending_battle_shock_reroll_authority(record.request)
    _validate_remaining_battle_shock_reroll_ancestry(
        continuation=continuation,
        authority=authority,
    )
    state.replace_catalog_selected_target_battle_shock_continuation(
        continuation.awaiting_remaining_effects()
    )


def refresh_catalog_selected_target_battle_shock_provider_request(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
) -> None:
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None or continuation.continuation_phase is not (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_PROVIDER_OUTCOME
    ):
        return
    pending = decisions.queue.pending_requests
    if len(pending) != 1:
        raise GameLifecycleError(
            "Catalog selected-target provider outcome must be the sole queue head."
        )
    provider_records = _provider_decision_records(
        continuation=continuation,
        decisions=decisions,
    )
    if pending[0] == continuation.provider_pending_request:
        if provider_records:
            raise GameLifecycleError(
                "Catalog selected-target pending provider request is already completed."
            )
    elif len(provider_records) != 1:
        raise GameLifecycleError(
            "Catalog selected-target provider request advanced without exact decision closure."
        )
    authority = _validate_continuation_authority(
        continuation=continuation,
        decisions=decisions,
    )
    claim = _pending_claim(
        state=state,
        decisions=decisions,
        battle_shock_hooks=battle_shock_hooks,
        request=pending[0],
        authority=authority,
    )
    state.replace_catalog_selected_target_battle_shock_continuation(
        continuation.with_provider_request(request=pending[0], claim=claim)
    )


def validate_pending_catalog_selected_target_battle_shock_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle,
    require_pending_request: bool,
) -> None:
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None:
        return
    _validate_continuation_authority(continuation=continuation, decisions=decisions)
    final_event_count = _final_event_count(continuation=continuation, decisions=decisions)
    pending = decisions.queue.pending_requests
    if continuation.continuation_phase is (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_PROVIDER_OUTCOME
    ):
        if _provider_decision_records(continuation=continuation, decisions=decisions):
            raise GameLifecycleError(
                "Catalog selected-target pending provider request is already completed."
            )
        if final_event_count:
            raise GameLifecycleError(
                "Catalog selected-target final event preceded its provider outcome."
            )
        if len(pending) != 1:
            raise GameLifecycleError(
                "Catalog selected-target provider outcome must be the sole queue head."
            )
        if pending[0] != continuation.provider_pending_request:
            raise GameLifecycleError("Catalog selected-target provider request drifted.")
        authority = _validate_continuation_authority(
            continuation=continuation,
            decisions=decisions,
        )
        claim = _pending_claim(
            state=state,
            decisions=decisions,
            battle_shock_hooks=runtime_content_bundle.battle_shock_hook_registry,
            request=pending[0],
            authority=authority,
        )
        if (
            claim.result != continuation.provider_battle_shock_result
            or claim.resolved_event_index != continuation.provider_resolved_event_index
        ):
            raise GameLifecycleError("Catalog selected-target provider claim drifted.")
        return

    if continuation.provider_pending_request in pending:
        raise GameLifecycleError(
            "Catalog selected-target completed provider request remains queued."
        )
    _validate_provider_completion(
        continuation=continuation,
        state=state,
        decisions=decisions,
        battle_shock_hooks=runtime_content_bundle.battle_shock_hook_registry,
    )
    if final_event_count:
        if pending:
            raise GameLifecycleError(
                "Catalog selected-target final event cannot retain a pending continuation."
            )
        return
    if not pending:
        if require_pending_request:
            raise GameLifecycleError(
                "Restored catalog selected-target continuation lacks a pending request."
            )
        return
    if len(pending) != 1:
        raise GameLifecycleError(
            "Catalog selected-target continuation requires one decision queue head."
        )
    _validate_remaining_effect_pending_request(
        continuation=continuation,
        state=state,
        decisions=decisions,
        request=pending[0],
        runtime_content_bundle=runtime_content_bundle,
    )


def resume_catalog_selected_target_battle_shock_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if continuation is None:
        return None
    if decisions.queue.pending_requests:
        raise GameLifecycleError(
            "Catalog selected-target continuation cannot resume with a pending request."
        )
    _validate_continuation_authority(continuation=continuation, decisions=decisions)
    if continuation.continuation_phase is (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_BATTLE_SHOCK_REROLL
    ):
        raise GameLifecycleError(
            "Catalog selected-target later Battle-shock reroll disappeared before resolution."
        )
    if continuation.continuation_phase is (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS
    ):
        if _final_event_count(continuation=continuation, decisions=decisions) != 1:
            raise GameLifecycleError(
                "Catalog selected-target nested continuation closed without its final event."
            )
        state.replace_catalog_selected_target_battle_shock_continuation(None)
        return None
    _validate_provider_completion(
        continuation=continuation,
        state=state,
        decisions=decisions,
        battle_shock_hooks=battle_shock_hooks,
    )
    state.replace_catalog_selected_target_battle_shock_continuation(
        continuation.awaiting_remaining_effects()
    )
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        continue_selected_target_effect_records,
    )
    from warhammer40k_core.engine.catalog_selected_target_event import (
        append_selected_target_event,
    )

    prefix = (
        *continuation.recorded_effects_before_battle_shock,
        continuation.resolved_battle_shock_payload,
    )
    recording = continue_selected_target_effect_records(
        state=state,
        decisions=decisions,
        result=continuation.selected_target_result,
        payload=continuation.selected_target_payload,
        effect_records=continuation.remaining_effect_records,
        phase=continuation.phase,
        event_type=continuation.final_event_type,
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        initial_recorded=prefix,
        effect_index_offset=continuation.remaining_effect_start_index,
    )
    if recording.pending_status is not None:
        return recording.pending_status
    append_selected_target_event(
        state=state,
        decisions=decisions,
        result=continuation.selected_target_result,
        payload=continuation.selected_target_payload,
        effects=recording.effects,
        event_type=continuation.final_event_type,
        phase=continuation.phase,
    )
    if _final_event_count(continuation=continuation, decisions=decisions) != 1:
        raise GameLifecycleError("Catalog selected-target final event was not unique.")
    state.replace_catalog_selected_target_battle_shock_continuation(None)
    return None


def advance_catalog_selected_target_battle_shock_lifecycle(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_request: DecisionRequest | None,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> LifecycleStatus | None:
    continuation = state.pending_catalog_selected_target_battle_shock_continuation
    if pending_request is not None:
        if continuation is not None:
            bundle = _require_runtime_content_bundle(runtime_content_bundle)
            refresh_catalog_selected_target_battle_shock_provider_request(
                state=state,
                decisions=decisions,
                battle_shock_hooks=bundle.battle_shock_hook_registry,
            )
            pending_request = decisions.queue.peek_next()
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=pending_request,
            payload={
                "game_id": state.game_id,
                "pending_request_id": pending_request.request_id,
            },
        )
    if continuation is None:
        return None
    bundle = _require_runtime_content_bundle(runtime_content_bundle)
    return resume_catalog_selected_target_battle_shock_continuation(
        state=state,
        decisions=decisions,
        battle_shock_hooks=bundle.battle_shock_hook_registry,
        runtime_modifier_registry=bundle.runtime_modifier_registry,
        ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
    )


def validate_catalog_selected_target_battle_shock_submitted_status(
    *,
    state: GameState,
    decisions: DecisionController,
    status: LifecycleStatus,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    if (
        state.pending_catalog_selected_target_battle_shock_continuation is None
        or not decisions.queue.pending_requests
    ):
        return
    bundle = _require_runtime_content_bundle(runtime_content_bundle)
    refresh_catalog_selected_target_battle_shock_provider_request(
        state=state,
        decisions=decisions,
        battle_shock_hooks=bundle.battle_shock_hook_registry,
    )
    validate_pending_catalog_selected_target_battle_shock_continuation(
        state=state,
        decisions=decisions,
        runtime_content_bundle=bundle,
        require_pending_request=True,
    )
    if status.decision_request != decisions.queue.peek_next():
        raise GameLifecycleError(
            "Catalog selected-target continuation status is not the queue head."
        )


def validate_catalog_selected_target_battle_shock_pre_submission(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    if state.pending_catalog_selected_target_battle_shock_continuation is None:
        return
    bundle = _require_runtime_content_bundle(runtime_content_bundle)
    validate_pending_catalog_selected_target_battle_shock_continuation(
        state=state,
        decisions=decisions,
        runtime_content_bundle=bundle,
        require_pending_request=True,
    )
    if decisions.queue.peek_next() != request:
        raise GameLifecycleError(
            "Catalog selected-target continuation submission is not the queue head."
        )


def validate_restored_catalog_selected_target_battle_shock_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    if state.pending_catalog_selected_target_battle_shock_continuation is None:
        return
    bundle = _require_runtime_content_bundle(runtime_content_bundle)
    validate_pending_catalog_selected_target_battle_shock_continuation(
        state=state,
        decisions=decisions,
        runtime_content_bundle=bundle,
        require_pending_request=True,
    )


def _require_runtime_content_bundle(
    bundle: RuntimeContentBundle | None,
) -> RuntimeContentBundle:
    if bundle is None:
        raise GameLifecycleError(
            "Catalog selected-target Battle-shock continuation requires runtime content."
        )
    return bundle


def _continuation_from_resolution(
    *,
    decisions: DecisionController,
    resolved_payload: dict[str, JsonValue],
    phase: BattlePhase,
    final_event_type: str,
    authority: BattleShockResolutionAuthority,
    provider_request: DecisionRequest,
    provider_claim: BattleShockPendingOutcomeAuthority,
) -> PendingCatalogSelectedTargetBattleShockContinuation:
    selected_result = DecisionResult.from_payload(
        cast(
            DecisionResultPayload,
            _payload_object(resolved_payload, "selected_target_decision_result"),
        )
    )
    selected_request = DecisionRequest.from_payload(
        cast(
            DecisionRequestPayload,
            _payload_object(resolved_payload, "selected_target_decision_request"),
        )
    )
    source_record = decisions.record_for_result(selected_result)
    if source_record.request != selected_request:
        raise GameLifecycleError("Catalog selected-target source decision authority drifted.")
    reroll = authority.reroll
    return PendingCatalogSelectedTargetBattleShockContinuation(
        continuation_phase=(
            CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_PROVIDER_OUTCOME
        ),
        selected_target_request=selected_request,
        selected_target_result=selected_result,
        selected_target_payload=_payload_object(resolved_payload, "selected_target_payload"),
        phase=phase,
        final_event_type=final_event_type,
        catalog_record_id=_payload_identifier(resolved_payload, "catalog_record_id"),
        source_rule_id=_payload_identifier(resolved_payload, "source_rule_id"),
        source_unit_instance_id=_payload_identifier(resolved_payload, "source_unit_instance_id"),
        selection_clause_id=_payload_identifier(resolved_payload, "selection_clause_id"),
        effect_clause_id=_payload_identifier(resolved_payload, "effect_clause_id"),
        selected_target_unit_instance_id=_payload_identifier(
            resolved_payload, "selected_target_unit_instance_id"
        ),
        effect_index=_payload_non_negative_int(resolved_payload, "effect_index"),
        recorded_effects_before_battle_shock=_payload_object_tuple(
            resolved_payload,
            "selected_target_recorded_effects_before_battle_shock",
        ),
        resolved_battle_shock_payload=resolved_payload,
        remaining_effect_records=_payload_object_tuple(
            resolved_payload,
            "selected_target_remaining_effect_records_after_battle_shock",
        ),
        remaining_effect_start_index=_payload_non_negative_int(
            resolved_payload,
            "selected_target_remaining_effect_start_index",
        ),
        battle_shock_request_id=authority.result.request.request_id,
        battle_shock_result_id=authority.result.result_id,
        battle_shock_reroll_request_id=(
            None if reroll is None else reroll.decision_record.request.request_id
        ),
        battle_shock_reroll_result_id=(
            None if reroll is None else reroll.decision_record.result.result_id
        ),
        provider_pending_request=provider_request,
        provider_battle_shock_result=provider_claim.result,
        provider_resolved_event_index=provider_claim.resolved_event_index,
    )


def _validate_retained_payload(
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
) -> None:
    payload = continuation.resolved_battle_shock_payload
    raw_result = _payload_object(payload, "battle_shock_result")
    battle_shock_result = BattleShockResult.from_payload(cast(BattleShockResultPayload, raw_result))
    expected = {
        "phase": continuation.phase.value,
        "selected_target_final_event_type": continuation.final_event_type,
        "catalog_record_id": continuation.catalog_record_id,
        "source_rule_id": continuation.source_rule_id,
        "source_unit_instance_id": continuation.source_unit_instance_id,
        "selection_clause_id": continuation.selection_clause_id,
        "effect_clause_id": continuation.effect_clause_id,
        "selected_target_unit_instance_id": continuation.selected_target_unit_instance_id,
        "effect_index": continuation.effect_index,
        "selected_target_decision_request": continuation.selected_target_request.to_payload(),
        "selected_target_decision_result": continuation.selected_target_result.to_payload(),
        "selected_target_payload": continuation.selected_target_payload,
        "selected_target_recorded_effects_before_battle_shock": list(
            continuation.recorded_effects_before_battle_shock
        ),
        "selected_target_remaining_effect_records_after_battle_shock": list(
            continuation.remaining_effect_records
        ),
        "selected_target_remaining_effect_start_index": (continuation.remaining_effect_start_index),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise GameLifecycleError("Catalog selected-target retained payload drifted.")
    if (
        battle_shock_result.request.request_id != continuation.battle_shock_request_id
        or battle_shock_result.result_id != continuation.battle_shock_result_id
        or battle_shock_result != continuation.provider_battle_shock_result
    ):
        raise GameLifecycleError("Catalog selected-target Battle-shock identity drifted.")


def _validate_continuation_authority(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    decisions: DecisionController,
) -> BattleShockResolutionAuthority:
    source_record = decisions.record_for_result(continuation.selected_target_result)
    if source_record.request != continuation.selected_target_request:
        raise GameLifecycleError("Catalog selected-target source decision drifted.")
    authority = _resolution_authority(
        decisions=decisions,
        resolved_payload=continuation.resolved_battle_shock_payload,
    )
    reroll = authority.reroll
    reroll_request_id = None if reroll is None else reroll.decision_record.request.request_id
    reroll_result_id = None if reroll is None else reroll.decision_record.result.result_id
    if (
        authority.result.request.request_id != continuation.battle_shock_request_id
        or authority.result.result_id != continuation.battle_shock_result_id
        or authority.phase is not continuation.phase
        or authority.resolved_event_index != continuation.provider_resolved_event_index
        or reroll_request_id != continuation.battle_shock_reroll_request_id
        or reroll_result_id != continuation.battle_shock_reroll_result_id
    ):
        raise GameLifecycleError("Catalog selected-target Battle-shock authority drifted.")
    return authority


def _resolution_authority(
    *,
    decisions: DecisionController,
    resolved_payload: dict[str, JsonValue],
) -> BattleShockResolutionAuthority:
    result = BattleShockResult.from_payload(
        cast(
            BattleShockResultPayload,
            _payload_object(resolved_payload, "battle_shock_result"),
        )
    )
    matches = tuple(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "battle_shock_test_resolved" and event.payload == resolved_payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Catalog selected-target continuation requires one Battle-shock occurrence."
        )
    authority = parse_battle_shock_resolution_authority(
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        resolved_index=matches[0],
        resolved_payload=resolved_payload,
        result=result,
    )
    validate_battle_shock_source_family_authority(
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        resolved_index=authority.resolved_event_index,
        request_payload=cast(
            dict[str, JsonValue],
            validate_json_value(result.request.to_payload()),
        ),
        request_context=authority.request_context,
        request_base=authority.base_payload,
        result=result,
    )
    if authority.base_payload.get("source_kind") != "catalog_selected_target_effect":
        raise GameLifecycleError("Catalog selected-target Battle-shock source kind drifted.")
    return authority


def _pending_claim(
    *,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
    request: DecisionRequest,
    authority: BattleShockResolutionAuthority,
) -> BattleShockPendingOutcomeAuthority:
    claim = battle_shock_hooks.pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=state,
            decisions=decisions,
            request=request,
        )
    )
    if (
        claim is None
        or claim.result != authority.result
        or claim.resolved_event_index != authority.resolved_event_index
    ):
        raise GameLifecycleError(
            "Catalog selected-target continuation lacks exact provider authority."
        )
    return claim


def _validate_provider_completion(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    state: GameState,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
) -> None:
    provider_records = _provider_decision_records(
        continuation=continuation,
        decisions=decisions,
    )
    if len(provider_records) != 1:
        raise GameLifecycleError(
            "Catalog selected-target provider outcome lacks exact decision closure."
        )
    battle_shock_hooks.validate_completed_outcome_authority(
        BattleShockCompletedOutcomeAuthorityContext(state=state, decisions=decisions)
    )


def _provider_decision_records(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    decisions: DecisionController,
) -> tuple[DecisionRecord, ...]:
    return tuple(
        record
        for record in decisions.records
        if record.request == continuation.provider_pending_request
    )


def _validate_remaining_effect_pending_request(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    if is_battle_shock_reroll_request(
        request,
        source_kind="catalog_selected_target_effect",
    ):
        if continuation.continuation_phase is not (
            CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_BATTLE_SHOCK_REROLL
        ):
            raise GameLifecycleError(
                "Catalog selected-target later Battle-shock reroll phase drifted."
            )
        from warhammer40k_core.engine.battle_shock_pending_authority import (
            validate_live_pending_battle_shock_reroll_authority,
        )

        authority = validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_request=request,
            runtime_content_bundle=runtime_content_bundle,
        )
        _validate_remaining_battle_shock_reroll_ancestry(
            continuation=continuation,
            authority=authority,
        )
        return
    if continuation.continuation_phase is not (
        CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS
    ):
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects continuation phase drifted."
        )
    _validate_remaining_mortal_wound_pending_request(
        continuation=continuation,
        decisions=decisions,
        request=request,
    )


def _validate_remaining_mortal_wound_pending_request(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    decisions: DecisionController,
    request: DecisionRequest,
) -> None:
    from warhammer40k_core.engine.catalog_selected_target_mortal_wounds import (
        CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_SOURCE_KIND,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
        mortal_wound_resolution_source_context,
    )

    if not is_mortal_wound_resolution_request(request):
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects request is not a supported continuation."
        )
    if any(record.request == request for record in decisions.records):
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects request is already completed."
        )
    request_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if len(request_events) != 1:
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects request event authority drifted."
        )
    source_context = _json_object(
        "remaining_effect_source_context",
        mortal_wound_resolution_source_context(request),
    )
    if source_context.get("source_kind") != CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects request source kind drifted."
        )
    if (
        source_context.get("selected_target_decision_result")
        != continuation.selected_target_result.to_payload()
        or source_context.get("selected_target_payload") != continuation.selected_target_payload
    ):
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects request parent authority drifted."
        )
    effect_record = _payload_object(source_context, "selected_target_effect_record")
    remaining_after = _payload_object_tuple(
        source_context,
        "selected_target_remaining_effect_records_after_mortal_wounds",
    )
    remaining_start_index = _payload_non_negative_int(
        source_context,
        "selected_target_remaining_effect_start_index",
    )
    matches = tuple(
        index
        for index, record in enumerate(continuation.remaining_effect_records)
        if record == effect_record
        and record.get("immediate_effect_kind") == "inflict_mortal_wounds"
        and tuple(continuation.remaining_effect_records[index + 1 :]) == remaining_after
        and continuation.remaining_effect_start_index + index + 1 == remaining_start_index
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Catalog selected-target remaining-effects request ancestry drifted."
        )


def _validate_remaining_battle_shock_reroll_ancestry(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    authority: PendingBattleShockRerollAuthority,
) -> None:
    base = authority.base_payload
    selected_request = continuation.selected_target_request.to_payload()
    selected_result = continuation.selected_target_result.to_payload()
    recorded_before = _payload_object_tuple(
        base,
        "selected_target_recorded_effects_before_battle_shock",
    )
    remaining_after = _payload_object_tuple(
        base,
        "selected_target_remaining_effect_records_after_battle_shock",
    )
    remaining_start_index = _payload_non_negative_int(
        base,
        "selected_target_remaining_effect_start_index",
    )
    matches = _remaining_battle_shock_effect_indices(
        continuation=continuation,
        battle_shock_payload=base,
    )
    retained_prefix = (
        *continuation.recorded_effects_before_battle_shock,
        continuation.resolved_battle_shock_payload,
    )
    if (
        authority.source_kind != "catalog_selected_target_effect"
        or base.get("selected_target_decision_request") != selected_request
        or base.get("selected_target_decision_result") != selected_result
        or base.get("selected_target_payload") != continuation.selected_target_payload
        or base.get("phase") != continuation.phase.value
        or base.get("selected_target_final_event_type") != continuation.final_event_type
        or len(matches) != 1
        or tuple(continuation.remaining_effect_records[matches[0] + 1 :]) != remaining_after
        or continuation.remaining_effect_start_index + matches[0] + 1 != remaining_start_index
        or recorded_before[: len(retained_prefix)] != retained_prefix
    ):
        raise GameLifecycleError(
            "Catalog selected-target later Battle-shock reroll ancestry drifted."
        )


def _validate_progressive_replacement(
    *,
    existing: PendingCatalogSelectedTargetBattleShockContinuation,
    replacement: PendingCatalogSelectedTargetBattleShockContinuation,
) -> None:
    prefix = (
        *existing.recorded_effects_before_battle_shock,
        existing.resolved_battle_shock_payload,
    )
    matches = _remaining_battle_shock_effect_indices(
        continuation=existing,
        battle_shock_payload=replacement.resolved_battle_shock_payload,
    )
    if (
        existing.continuation_phase
        is not (CatalogSelectedTargetBattleShockContinuationPhase.AWAITING_REMAINING_EFFECTS)
        or replacement.selected_target_request != existing.selected_target_request
        or replacement.selected_target_result != existing.selected_target_result
        or replacement.phase is not existing.phase
        or replacement.final_event_type != existing.final_event_type
        or len(matches) != 1
        or tuple(existing.remaining_effect_records[matches[0] + 1 :])
        != replacement.remaining_effect_records
        or existing.remaining_effect_start_index + matches[0] + 1
        != replacement.remaining_effect_start_index
        or replacement.recorded_effects_before_battle_shock[: len(prefix)] != prefix
    ):
        raise GameLifecycleError("Catalog selected-target continuation replacement drifted.")


def _remaining_battle_shock_effect_indices(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    battle_shock_payload: dict[str, JsonValue],
) -> tuple[int, ...]:
    effect_payload = _payload_object(battle_shock_payload, "effect_payload")
    return tuple(
        index
        for index, record in enumerate(continuation.remaining_effect_records)
        if record.get("immediate_effect_kind") == "force_battle_shock_test"
        and record.get("catalog_record_id") == battle_shock_payload.get("catalog_record_id")
        and record.get("source_rule_id") == battle_shock_payload.get("source_rule_id")
        and record.get("source_unit_instance_id")
        == battle_shock_payload.get("source_unit_instance_id")
        and record.get("selection_clause_id") == battle_shock_payload.get("selection_clause_id")
        and record.get("effect_clause_id") == battle_shock_payload.get("effect_clause_id")
        and record.get("effect_index") == battle_shock_payload.get("effect_index")
        and record.get("selected_target_unit_instance_id")
        == battle_shock_payload.get("selected_target_unit_instance_id")
        and record.get("effect_payload") == effect_payload
    )


def _validate_pending_status_queue_head(
    *,
    decisions: DecisionController,
    status: LifecycleStatus,
) -> DecisionRequest:
    pending = decisions.queue.pending_requests
    if (
        len(pending) != 1
        or status.decision_request is None
        or status.decision_request != pending[0]
    ):
        raise GameLifecycleError(
            "Catalog selected-target outcome status must identify the sole queue head."
        )
    return pending[0]


def _final_event_count(
    *,
    continuation: PendingCatalogSelectedTargetBattleShockContinuation,
    decisions: DecisionController,
) -> int:
    count = sum(
        1
        for event in decisions.event_log.records
        if event.event_type == continuation.final_event_type
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == continuation.selected_target_result.request_id
        and event.payload.get("result_id") == continuation.selected_target_result.result_id
        and event.payload.get("phase") == continuation.phase.value
        and event.payload.get("catalog_record_id") == continuation.catalog_record_id
        and event.payload.get("source_rule_id") == continuation.source_rule_id
        and event.payload.get("source_unit_instance_id") == continuation.source_unit_instance_id
        and event.payload.get("selection_clause_id") == continuation.selection_clause_id
        and event.payload.get("target_unit_instance_id")
        == continuation.selected_target_unit_instance_id
    )
    if count > 1:
        raise GameLifecycleError("Catalog selected-target final event occurred more than once.")
    return count


def _payload_object(
    payload: dict[str, JsonValue],
    key: str,
) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be an object.")
    return cast(dict[str, JsonValue], validate_json_value(value))


def _payload_object_tuple(
    payload: dict[str, JsonValue],
    key: str,
) -> tuple[dict[str, JsonValue], ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be a list.")
    return _json_object_tuple(key, tuple(value))


def _payload_identifier(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(key, payload.get(key))


def _payload_non_negative_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"Catalog selected-target payload {key} is invalid.")
    return value


def _json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Catalog selected-target {field_name} must be an object.")
    typed_value = cast(dict[str, object], value)
    return cast(dict[str, JsonValue], validate_json_value(typed_value))


def _json_object_tuple(
    field_name: str,
    value: object,
) -> tuple[dict[str, JsonValue], ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Catalog selected-target {field_name} must be a tuple.")
    typed_value = cast(tuple[object, ...], value)
    return tuple(_json_object(field_name, item) for item in typed_value)


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "CatalogSelectedTargetBattleShockContinuationPhase",
    "CatalogSelectedTargetBattleShockRuntime",
    "PendingCatalogSelectedTargetBattleShockContinuation",
    "PendingCatalogSelectedTargetBattleShockContinuationPayload",
    "advance_catalog_selected_target_battle_shock_lifecycle",
    "complete_catalog_selected_target_remaining_battle_shock_reroll",
    "refresh_catalog_selected_target_battle_shock_provider_request",
    "resume_catalog_selected_target_battle_shock_continuation",
    "retain_catalog_selected_target_battle_shock_continuation",
    "retain_catalog_selected_target_remaining_battle_shock_reroll",
    "validate_catalog_selected_target_battle_shock_pre_submission",
    "validate_catalog_selected_target_battle_shock_submitted_status",
    "validate_pending_catalog_selected_target_battle_shock_continuation",
    "validate_restored_catalog_selected_target_battle_shock_continuation",
)
