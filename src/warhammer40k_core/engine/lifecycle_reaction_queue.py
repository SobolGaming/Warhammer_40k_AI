from __future__ import annotations

from collections.abc import Collection

from warhammer40k_core.engine.attack_sequence import (
    is_destroyed_transport_disembark_proposal_request,
)
from warhammer40k_core.engine.catalog_setup_reactive_charge_move import (
    is_catalog_setup_reactive_charge_move_request,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.reaction_queue import REACTION_DECISION_TYPE, ReactionQueue
from warhammer40k_core.engine.stratagems import (
    is_heroic_intervention_charge_move_request,
    is_stratagem_placement_proposal_request,
)


def validate_reaction_queue_consistency(
    *,
    state: GameState,
    reaction_queue: ReactionQueue,
    pending_request: DecisionRequest | None,
    reaction_frame_decision_types: Collection[str],
) -> None:
    frames = reaction_queue.frames
    if not frames:
        if pending_request is not None and pending_request.decision_type == REACTION_DECISION_TYPE:
            raise GameLifecycleError("Lifecycle pending reaction decision requires a frame.")
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Lifecycle reaction queue requires battle stage.")
    if state.current_battle_phase is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a current battle phase.")
    if pending_request is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a pending decision.")
    if pending_request.decision_type not in reaction_frame_decision_types:
        raise GameLifecycleError("Lifecycle reaction queue pending decision_type drift.")
    if (
        pending_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and not is_stratagem_placement_proposal_request(pending_request)
        and not is_destroyed_transport_disembark_proposal_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending placement decision drift.")
    if (
        pending_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and not is_heroic_intervention_charge_move_request(pending_request)
        and not is_catalog_setup_reactive_charge_move_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending movement decision drift.")
    seen_request_ids: set[str] = set()
    for frame in frames:
        if frame.request_id is None:
            raise GameLifecycleError("Lifecycle reaction queue frame requires request_id.")
        if frame.request_id in seen_request_ids:
            raise GameLifecycleError("Lifecycle reaction queue request_ids must be unique.")
        seen_request_ids.add(frame.request_id)
        if frame.reaction_window.timing_window.game_id != state.game_id:
            raise GameLifecycleError("Lifecycle reaction queue frame game_id drift.")
        if frame.parent_phase is not state.current_battle_phase:
            raise GameLifecycleError("Lifecycle reaction queue frame phase drift.")
    if frames[-1].request_id != pending_request.request_id:
        raise GameLifecycleError("Lifecycle reaction queue active frame request_id drift.")
