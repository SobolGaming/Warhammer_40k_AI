"""Pile In endpoint constraints over the shared Fight movement authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.consolidation_model_constraints import consolidation_model_violation
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    ProposalValidationResult,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.game_state import GameState


def validate_pile_in_endpoint(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    after: UnitPlacement,
    state: GameState | None,
) -> ProposalValidationResult | None:
    from warhammer40k_core.engine.fight_resolution import (
        fight_base_contact_movement_violation,
        fight_continuing_engagement_violation,
        fight_moved_models_closer_to_targets_violation,
        fight_movement_endpoint_invalid,
        fight_unit_is_engaged_with_any,
    )

    before = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    base_contact_violation = fight_base_contact_movement_violation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=before,
        after=after,
        state=state,
    )
    if base_contact_violation is not None:
        return fight_movement_endpoint_invalid(proposal_request, base_contact_violation, "witness")
    closer_violation = fight_moved_models_closer_to_targets_violation(
        scenario=scenario,
        before=before,
        after=after,
        target_unit_instance_ids=proposal.pile_in_target_unit_instance_ids,
        state=state,
    )
    if closer_violation is not None:
        return fight_movement_endpoint_invalid(proposal_request, closer_violation, "witness")
    if not fight_unit_is_engaged_with_any(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=after,
        target_unit_instance_ids=proposal.pile_in_target_unit_instance_ids,
        state=state,
    ):
        return fight_movement_endpoint_invalid(
            proposal_request, "pile_in_unit_not_engaged_after", "witness"
        )
    continuing_violation = fight_continuing_engagement_violation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=before,
        after=after,
        state=state,
    )
    if continuing_violation is not None:
        return fight_movement_endpoint_invalid(proposal_request, continuing_violation, "witness")
    model_violation = consolidation_model_violation(
        scenario=scenario,
        before=before.model_placements,
        after=after.model_placements,
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        proposal=proposal,
        state=state,
    )
    if model_violation is not None:
        return fight_movement_endpoint_invalid(proposal_request, model_violation, "witness")
    return None
