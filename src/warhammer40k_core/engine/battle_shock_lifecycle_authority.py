from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.engine import command_battle_shock_history as _command
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


def apply_global_reroll_if_applicable(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    runtime_content_bundle: RuntimeContentBundle,
    reaction_queue: ReactionQueue,
    resolves_reaction_frame: bool,
    advance_until_decision_or_terminal: Callable[[], LifecycleStatus],
) -> LifecycleStatus | None:
    """Apply source-owned rerolls before dispatching by the current battle phase."""

    from warhammer40k_core.engine.battle_shock_test_service import (
        BattleShockTestRuntime,
        apply_stratagem_battle_shock_reroll_decision,
        is_stratagem_battle_shock_reroll_request,
    )
    from warhammer40k_core.engine.stratagems import (
        apply_command_reroll_decision,
        is_command_reroll_decision_request,
    )

    if is_command_reroll_decision_request(request):
        apply_command_reroll_decision(
            state=state,
            request=request,
            result=result,
            decisions=decisions,
        )
        if resolves_reaction_frame:
            reaction_queue.resolve_reaction(result=result, decisions=decisions)
        return advance_until_decision_or_terminal()
    if not is_stratagem_battle_shock_reroll_request(request):
        return None
    if decisions.queue.pending_requests:
        raise GameLifecycleError(
            "Stratagem Battle-shock reroll requires an otherwise empty decision queue."
        )
    apply_stratagem_battle_shock_reroll_decision(
        runtime=BattleShockTestRuntime.from_runtime_content_bundle(runtime_content_bundle),
        state=state,
        decisions=decisions,
        result=result,
    )
    nested_request = _stratagem_battle_shock_outcome_request(decisions)
    if resolves_reaction_frame:
        if nested_request is not None:
            advanced_status = advance_until_decision_or_terminal()
            if advanced_status.decision_request != nested_request:
                raise GameLifecycleError(
                    "Stratagem Battle-shock nested outcome decision status drifted."
                )
            reaction_queue.continue_reaction(
                result=result,
                next_request_id=nested_request.request_id,
                decisions=decisions,
            )
            return advanced_status
        reaction_queue.resolve_reaction(result=result, decisions=decisions)
    return advance_until_decision_or_terminal()


def _stratagem_battle_shock_outcome_request(
    decisions: DecisionController,
) -> DecisionRequest | None:
    pending_requests = decisions.queue.pending_requests
    if len(pending_requests) > 1:
        raise GameLifecycleError("Stratagem Battle-shock outcome queued multiple decisions.")
    if not pending_requests:
        return None
    from warhammer40k_core.engine.healing_decision_dispatch import HEALING_DECISION_TYPES

    pending_request = pending_requests[0]
    if pending_request.decision_type not in HEALING_DECISION_TYPES:
        raise GameLifecycleError(
            "Stratagem Battle-shock outcome queued an unsupported decision type."
        )
    return pending_request


def requires_command_prevalidation(*, state: GameState, request: DecisionRequest) -> bool:
    return _command.requires_command_prevalidation(state=state, request=request)


def invalid_live_pending(
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    runtime_content_bundle: RuntimeContentBundle,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.battle_shock_pending_authority import (
        invalid_live_pending_battle_shock_reroll_status,
    )

    return invalid_live_pending_battle_shock_reroll_status(
        state=state,
        decisions=decisions,
        pending_request=request,
        result=result,
        runtime_content_bundle=runtime_content_bundle,
    )


def validate_loaded(
    state: GameState,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle,
) -> None:
    """Validate loaded Battle-shock producers and any pending Command reroll."""
    from warhammer40k_core.engine.command_phase_start_authority import (
        validate_command_phase_start_restore_authority,
    )

    validate_command_phase_start_restore_authority(
        state=state,
        decisions=decisions,
        registry=runtime_content_bundle.command_phase_start_hook_registry,
        runtime_content_bundle=runtime_content_bundle,
    )
    from warhammer40k_core.engine.battle_shock_event_authority import (
        validate_battle_shock_runtime_content_authority,
    )

    validate_battle_shock_runtime_content_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        runtime_content_bundle=runtime_content_bundle,
    )
    from warhammer40k_core.engine.command_insane_bravery_authority import (
        validate_loaded_command_auto_pass_authority,
    )

    validate_loaded_command_auto_pass_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        runtime_content_bundle=runtime_content_bundle,
    )
    from warhammer40k_core.engine.command_battle_shock_runtime_authority import (
        validate_loaded_command_battle_shock_authority,
    )

    validate_loaded_command_battle_shock_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        runtime_content_bundle=runtime_content_bundle,
    )
    from warhammer40k_core.engine.battle_shock_pending_authority import (
        validate_live_pending_battle_shock_reroll_authority,
    )

    for pending_request in decisions.queue.pending_requests:
        if (
            isinstance(pending_request.payload, dict)
            and "battle_shock_context" in pending_request.payload
        ):
            validate_live_pending_battle_shock_reroll_authority(
                state=state,
                event_records=decisions.event_log.records,
                decision_records=decisions.records,
                pending_request=pending_request,
                runtime_content_bundle=runtime_content_bundle,
            )
        validate_pending_outcome_request(
            state=state,
            decisions=decisions,
            request=pending_request,
            runtime_content_bundle=runtime_content_bundle,
        )
    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockCompletedOutcomeAuthorityContext,
    )

    runtime_content_bundle.battle_shock_hook_registry.validate_completed_outcome_authority(
        BattleShockCompletedOutcomeAuthorityContext(
            state=state,
            decisions=decisions,
        )
    )


def validate_pending_outcome_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    """Require any loaded Battle-shock outcome provider to authenticate its request."""

    if runtime_content_bundle is None:
        return

    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockPendingOutcomeAuthorityContext,
    )

    provider_source_ids = (
        runtime_content_bundle.battle_shock_hook_registry.pending_outcome_authority_source_ids()
    )
    fnp_source_rule_id = (
        runtime_content_bundle.mortal_wound_feel_no_pain_hook_registry.source_rule_id_for_request(
            request
        )
    )
    from warhammer40k_core.engine.healing_decision_dispatch import (
        healing_source_rule_id_for_request,
    )

    healing_source_rule_id = healing_source_rule_id_for_request(request)
    source_rule_ids = tuple(
        source_rule_id
        for source_rule_id in (fnp_source_rule_id, healing_source_rule_id)
        if source_rule_id is not None
    )
    if len(source_rule_ids) > 1:
        raise GameLifecycleError("Battle-shock outcome continuation source family is ambiguous.")
    continuation_source_rule_id = source_rule_ids[0] if source_rule_ids else None
    claim = runtime_content_bundle.battle_shock_hook_registry.pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=state,
            decisions=decisions,
            request=request,
        )
    )
    if continuation_source_rule_id in provider_source_ids and claim is None:
        raise GameLifecycleError(
            "Loaded Battle-shock outcome continuation lacks pending provider authority."
        )
    runtime_content_bundle.mortal_wound_feel_no_pain_hook_registry.binding_for_request(
        request,
        required_source_ids=provider_source_ids,
    )


def validate_pre_submission_outcome_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
        validate_catalog_selected_target_battle_shock_pre_submission,
    )

    validate_catalog_selected_target_battle_shock_pre_submission(
        state=state,
        decisions=decisions,
        request=request,
        runtime_content_bundle=runtime_content_bundle,
    )
    validate_pending_outcome_request(
        state=state,
        decisions=decisions,
        request=request,
        runtime_content_bundle=runtime_content_bundle,
    )


def validate_restore(
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    _command.validate_restore(
        state,
        event_records,
        decision_records,
        pending_decision_requests,
    )


__all__ = (
    "apply_global_reroll_if_applicable",
    "invalid_live_pending",
    "requires_command_prevalidation",
    "validate_loaded",
    "validate_pending_outcome_request",
    "validate_pre_submission_outcome_request",
    "validate_restore",
)
