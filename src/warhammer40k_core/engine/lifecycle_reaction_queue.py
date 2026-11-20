from __future__ import annotations

from collections.abc import Collection

from warhammer40k_core.engine.attack_sequence import (
    is_destroyed_transport_disembark_proposal_request,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_setup_reactive_charge_move import (
    is_catalog_setup_reactive_charge_move_request,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.fight_activation_units import active_fight_activation_rules_unit
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.move_completion_effects import (
    SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueueFrame,
)
from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
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
    charge = state.charge_phase_state
    charge_active = charge is not None and charge.interruption is not None
    charge_types = {
        "select_charging_unit",
        "select_charge_declaration_grant",
        "select_charge_targets",
        "select_target_replacement",
        # Shared completion hooks finish before the interrupted Charge releases its frame.
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
        SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE,
        SEQUENCING_DECISION_TYPE,
    }
    if (
        pending_request.decision_type not in reaction_frame_decision_types
        and not (charge_active and pending_request.decision_type in charge_types)
        and not _is_interrupted_fight_melee_request(state, pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending decision_type drift.")
    if (
        pending_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and not is_stratagem_placement_proposal_request(pending_request)
        and not is_destroyed_transport_disembark_proposal_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending placement decision drift.")
    if (
        pending_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and not is_catalog_setup_reactive_charge_move_request(pending_request)
        and not charge_active
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


def _is_interrupted_fight_melee_request(state: GameState, request: DecisionRequest) -> bool:
    fight = state.fight_phase_state
    if (
        request.decision_type != SUBMIT_MELEE_DECLARATION_DECISION_TYPE
        or state.current_battle_phase is not BattlePhase.FIGHT
        or fight is None
    ):
        return False
    activation = fight.active_activation
    if (
        activation is None
        or activation.interrupt_id is None
        or request.actor_id != activation.player_id
    ):
        return False
    proposal = (
        request.payload.get("proposal_request") if isinstance(request.payload, dict) else None
    )
    if not isinstance(proposal, dict) or proposal.get("phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Lifecycle melee proposal_request phase drift.")
    if proposal.get("decision_type") != request.decision_type:
        raise GameLifecycleError("Lifecycle melee proposal_request decision_type drift.")
    melee = MeleeDeclarationProposalRequest.from_decision_request(request)
    rules_unit = active_fight_activation_rules_unit(state=state, activation=activation)
    return (
        rules_unit is not None
        and melee.unit_instance_id == rules_unit.unit_instance_id
        and melee.request_id == request.request_id
        and melee.actor_id == activation.player_id
        and melee.game_id == state.game_id
        and melee.battle_round == state.battle_round
        and melee.active_player_id == fight.active_player_id
        and melee.ruleset_descriptor_hash == state.ruleset_descriptor_hash
        and melee.source_decision_request_id == activation.request_id
        and melee.source_decision_result_id == activation.result_id
    )


def validate_melee_reaction_continuation(
    *, frame: ReactionQueueFrame, event_records: tuple[EventRecord, ...]
) -> None:
    for event in reversed(event_records):
        # The continuation is recorded after issuing the declaration in the same submission.
        if event.event_type == "decision_recorded":
            break
        if event.event_type == "reaction_window_continued":
            payload = event.payload
            if (
                isinstance(payload, dict)
                and payload.get("next_request_id") == frame.request_id
                and payload.get("resume_token") == frame.resume_token
                and payload.get("parent_phase") == frame.parent_phase.value
                and payload.get("parent_step") == frame.parent_step
                and payload.get("reaction_window") == frame.reaction_window.to_payload()
            ):
                return
            break
    raise GameLifecycleError("Lifecycle melee reaction continuation drift.")
