from __future__ import annotations

from warhammer40k_core.engine.active_player_scopes import (
    ActivePlayerScope,
    ActivePlayerScopeKind,
    pop_scope,
    push_scope,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    ACTIVE_PLAYER_SOURCE_ID,
)


def fight_move_scope(request: DecisionRequest) -> ActivePlayerScope:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    if proposal.phase != BattlePhase.FIGHT.value or proposal.proposal_kind not in (
        ProposalKind.PILE_IN,
        ProposalKind.CONSOLIDATE,
    ):
        raise GameLifecycleError("Fight movement authority requires a Fight movement request.")
    return ActivePlayerScope(
        kind=ActivePlayerScopeKind.FIGHT_MOVE,
        player_id=proposal.actor_id,
        unit_instance_id=proposal.unit_instance_id,
        source_rule_id=ACTIVE_PLAYER_SOURCE_ID,
        selection_request_id=request.request_id,
        # Phase-step selection is engine-enumerated by the existing proposal owner.
        selection_result_id=proposal.source_decision_result_id,
    )


def begin_fight_move(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
) -> None:
    if decisions.queue.pending_requests != (request,):
        raise GameLifecycleError("Fight move selection requires its unique pending proposal.")
    scope = fight_move_scope(request)
    push_scope(state, scope)
    decisions.event_log.append("active_player_scope_started", scope.to_payload())


def end_fight_move(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    if not state.active_player_scopes:
        raise GameLifecycleError("Fight movement completed without selected-unit authority.")
    scope = state.active_player_scopes[-1]
    current = fight_move_scope(request)
    if (
        scope.kind is not current.kind
        or scope.player_id != current.player_id
        or scope.unit_instance_id != current.unit_instance_id
        or scope.source_rule_id != current.source_rule_id
        or scope.selection_result_id != current.selection_result_id
    ):
        raise GameLifecycleError("Fight move completion lost its selected-unit authority.")
    pop_scope(state, scope)
    decisions.event_log.append(
        "active_player_scope_completed",
        {"scope": scope.to_payload(), "result_id": result.result_id},
    )


def validate_fight_move_selection(
    scope: ActivePlayerScope,
    decisions: DecisionController,
    event_index: int,
) -> None:
    sources = tuple(
        event
        for event in decisions.event_log.records[:event_index]
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == scope.selection_request_id
    )
    from typing import cast

    from warhammer40k_core.engine.decision_request import DecisionRequestPayload

    if (
        len(sources) != 1
        or fight_move_scope(
            DecisionRequest.from_payload(cast(DecisionRequestPayload, sources[0].payload))
        )
        != scope
    ):
        raise GameLifecycleError("Fight movement scope lost its source proposal.")
