from __future__ import annotations

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


def is_charge_move_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Charge proposal routing requires a DecisionRequest.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return (
        proposal_request.phase == BattlePhase.CHARGE.value
        or proposal_request.proposal_kind is ProposalKind.CHARGE_MOVE
    )


def is_fight_movement_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Fight proposal routing requires a DecisionRequest.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return proposal_request.phase == BattlePhase.FIGHT.value or proposal_request.proposal_kind in {
        ProposalKind.PILE_IN,
        ProposalKind.CONSOLIDATE,
    }
