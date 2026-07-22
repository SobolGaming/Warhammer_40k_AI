from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.stratagems import (
    apply_heroic_intervention_charge_move,
    is_heroic_intervention_charge_move_request,
)


def apply_heroic_intervention_charge_move_lifecycle_decision(
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
        raise GameLifecycleError("Heroic Intervention Charge Move actor is missing.")
    ability_index = runtime_content_bundle.ability_indexes_by_player_id.get(actor_id)
    if ability_index is None:
        raise GameLifecycleError("Heroic Intervention Charge Move actor has no Ability index.")
    heroic_status = apply_heroic_intervention_charge_move(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        ability_index=ability_index,
    )
    if heroic_status is not None:
        if resolves_reaction_frame:
            retry_request = pending_decision_request()
            if retry_request is not None and is_heroic_intervention_charge_move_request(
                retry_request
            ):
                reaction_queue.continue_reaction(
                    result=result,
                    next_request_id=retry_request.request_id,
                    decisions=decisions,
                )
        return heroic_status
    if resolves_reaction_frame:
        reaction_queue.resolve_reaction(result=result, decisions=decisions)
    return advance_until_decision_or_terminal()
