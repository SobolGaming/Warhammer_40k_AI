from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.engine.catalog_setup_reactive_charge_move import (
    apply_catalog_setup_reactive_charge_move,
    invalid_catalog_setup_reactive_charge_move_status,
    is_catalog_setup_reactive_charge_move_request,
)
from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
    SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
    apply_catalog_setup_reactive_shoot_charge_result,
    invalid_catalog_setup_reactive_shoot_charge_status,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.reaction_queue import ReactionQueue


def is_setup_reactive_lifecycle_request(request: DecisionRequest) -> bool:
    return request.decision_type == SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE or (
        request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and is_catalog_setup_reactive_charge_move_request(request)
    )


def invalid_setup_reactive_lifecycle_status(
    *,
    state: GameState,
    config: GameConfig,
    runtime_content_bundle: RuntimeContentBundle,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    request: DecisionRequest,
    result: DecisionResult,
    resolves_reaction_frame: bool,
) -> LifecycleStatus | None:
    if request.decision_type == SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE:
        if resolves_reaction_frame:
            reaction_queue.validate_result(result)
        return invalid_setup_reactive_shoot_charge_lifecycle_status(
            state=state,
            config=config,
            runtime_content_bundle=runtime_content_bundle,
            decisions=decisions,
            request=request,
            result=result,
        )
    if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE and (
        is_catalog_setup_reactive_charge_move_request(request)
    ):
        result.validate_for_request(request)
        return invalid_setup_reactive_charge_move_lifecycle_status(
            state=state,
            config=config,
            runtime_content_bundle=runtime_content_bundle,
            decisions=decisions,
            request=request,
            result=result,
        )
    raise GameLifecycleError("Setup-reactive lifecycle validation received wrong request.")


def invalid_setup_reactive_shoot_charge_lifecycle_status(
    *,
    state: GameState,
    config: GameConfig,
    runtime_content_bundle: RuntimeContentBundle,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return invalid_catalog_setup_reactive_shoot_charge_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ability_indexes_by_player_id=runtime_content_bundle.ability_indexes_by_player_id,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )


def invalid_setup_reactive_charge_move_lifecycle_status(
    *,
    state: GameState,
    config: GameConfig,
    runtime_content_bundle: RuntimeContentBundle,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return invalid_catalog_setup_reactive_charge_move_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        charge_target_restriction_hooks=(
            runtime_content_bundle.charge_target_restriction_hook_registry
        ),
    )


def apply_setup_reactive_lifecycle_decision_if_applicable(
    *,
    state: GameState,
    config: GameConfig,
    runtime_content_bundle: RuntimeContentBundle,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    record: DecisionRecord,
    result: DecisionResult,
    resolves_reaction_frame: bool,
    pending_decision_request: Callable[[], DecisionRequest | None],
    advance_until_decision_or_terminal: Callable[[], LifecycleStatus],
) -> LifecycleStatus | None:
    if record.request.decision_type == SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE:
        return apply_setup_reactive_shoot_charge_lifecycle_decision(
            state=state,
            config=config,
            runtime_content_bundle=runtime_content_bundle,
            decisions=decisions,
            reaction_queue=reaction_queue,
            result=result,
            resolves_reaction_frame=resolves_reaction_frame,
            advance_until_decision_or_terminal=advance_until_decision_or_terminal,
        )
    if record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE and (
        is_catalog_setup_reactive_charge_move_request(record.request)
    ):
        return apply_setup_reactive_charge_move_lifecycle_decision(
            state=state,
            config=config,
            runtime_content_bundle=runtime_content_bundle,
            decisions=decisions,
            reaction_queue=reaction_queue,
            record=record,
            result=result,
            resolves_reaction_frame=resolves_reaction_frame,
            pending_decision_request=pending_decision_request,
            advance_until_decision_or_terminal=advance_until_decision_or_terminal,
        )
    return None


def apply_setup_reactive_shoot_charge_lifecycle_decision(
    *,
    state: GameState,
    config: GameConfig,
    runtime_content_bundle: RuntimeContentBundle,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    result: DecisionResult,
    resolves_reaction_frame: bool,
    advance_until_decision_or_terminal: Callable[[], LifecycleStatus],
) -> LifecycleStatus:
    ability_index = runtime_content_bundle.ability_indexes_by_player_id.get(result.actor_id or "")
    if ability_index is None:
        raise GameLifecycleError("Setup-reactive action actor has no Ability index.")
    status = apply_catalog_setup_reactive_shoot_charge_result(
        state=state,
        decisions=decisions,
        result=result,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_content_bundle.runtime_modifier_registry,
        charge_target_restriction_hooks=(
            runtime_content_bundle.charge_target_restriction_hook_registry
        ),
    )
    if resolves_reaction_frame:
        if status is not None and status.decision_request is not None:
            reaction_queue.continue_reaction(
                result=result,
                next_request_id=status.decision_request.request_id,
                decisions=decisions,
            )
            return status
        if status is not None:
            return status
        reaction_queue.resolve_reaction(result=result, decisions=decisions)
    return advance_until_decision_or_terminal()


def apply_setup_reactive_charge_move_lifecycle_decision(
    *,
    state: GameState,
    config: GameConfig,
    runtime_content_bundle: RuntimeContentBundle,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    record: DecisionRecord,
    result: DecisionResult,
    resolves_reaction_frame: bool,
    pending_decision_request: Callable[[], DecisionRequest | None],
    advance_until_decision_or_terminal: Callable[[], LifecycleStatus],
) -> LifecycleStatus:
    actor_id = result.actor_id
    if actor_id is None:
        raise GameLifecycleError("Setup-reactive Charge Move actor is missing.")
    ability_index = runtime_content_bundle.ability_indexes_by_player_id.get(actor_id)
    if ability_index is None:
        raise GameLifecycleError("Setup-reactive Charge Move actor has no Ability index.")
    charge_status = apply_catalog_setup_reactive_charge_move(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        ability_index=ability_index,
    )
    if charge_status is not None:
        if resolves_reaction_frame:
            retry_request = pending_decision_request()
            if retry_request is not None and is_catalog_setup_reactive_charge_move_request(
                retry_request
            ):
                reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=retry_request.request_id,
                    decisions=decisions,
                )
        return charge_status
    if resolves_reaction_frame:
        reaction_queue.resolve_reaction(result=result, decisions=decisions)
    return advance_until_decision_or_terminal()
