"""Consolidation's mode and final-position validation owner (P12)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.consolidation_model_constraints import consolidation_model_violation
from warhammer40k_core.engine.consolidation_objectives import (
    consolidation_objective_by_id,
    consolidation_objective_distances,
    legal_consolidation_objective_ids,
)
from warhammer40k_core.engine.fight_geometry import (
    enemy_fight_unit_ids_within_distance as _enemy_unit_ids_within_distance,
)
from warhammer40k_core.engine.fight_geometry import (
    enemy_unit_ids_for_fight_placement as _enemy_unit_ids_for_placement,
)
from warhammer40k_core.engine.fight_movement_target_authority import (
    selectable_enemy_unit_ids_in_canonical_inventory,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ENEMY_DISTANCE_INCHES,
    FightMovementProposal,
    fight_base_contact_movement_violation,
    fight_continuing_engagement_violation,
    fight_moved_models_closer_to_targets_violation,
    fight_movement_endpoint_invalid,
    fight_objective_markers_from_context,
    fight_scenario_with_unit_placement,
    fight_unit_is_engaged_with_any,
    invalid_consolidation_mode,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    ProposalValidationResult,
)
from warhammer40k_core.engine.physical_engagement import (
    scenario_physically_engaged_enemy_rules_unit_ids,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_consolidation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    state: GameState | None,
) -> ProposalValidationResult:
    if proposal.consolidation_mode is None:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="consolidation_mode_required",
            message="Consolidation movement requires a consolidation mode.",
            field="consolidation_mode",
        )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    physically_engaged_ids = scenario_physically_engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=proposal.unit_instance_id,
    )
    selectable_enemy_ids = _enemy_unit_ids_for_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    engaged = selectable_enemy_unit_ids_in_canonical_inventory(
        scenario=scenario,
        selectable_enemy_ids=selectable_enemy_ids,
        canonical_inventory=physically_engaged_ids,
    )
    if physically_engaged_ids:
        if not engaged:
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="consolidation_no_selectable_engaged_target",
                message="Destroyed-only physical Engagement grants no Consolidation target.",
                field="consolidation_mode",
            )
        if proposal.consolidation_mode is not ConsolidationModeKind.ONGOING:
            return invalid_consolidation_mode(proposal_request, "ongoing")
        if set(proposal.consolidate_target_unit_instance_ids) != set(engaged):
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="ongoing_consolidation_targets_must_be_complete",
                message="Ongoing Consolidation must select every engaged enemy unit.",
                field="consolidate_target_unit_instance_ids",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    enemies_within_3 = _enemy_unit_ids_within_distance(
        scenario=scenario,
        unit_placement=unit_placement,
        distance_inches=CONSOLIDATE_ENEMY_DISTANCE_INCHES,
        state=state,
    )
    if enemies_within_3:
        if proposal.consolidation_mode is not ConsolidationModeKind.ENGAGING:
            return invalid_consolidation_mode(proposal_request, "engaging")
        selected = set(proposal.consolidate_target_unit_instance_ids)
        if not selected or selected - set(enemies_within_3):
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="engaging_consolidation_target_not_legal",
                message=(
                    "Engaging Consolidation requires one or more enemy targets within 3 inches."
                ),
                field="consolidate_target_unit_instance_ids",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    objective_ids = legal_consolidation_objective_ids(
        scenario=scenario,
        placements=unit_placement.model_placements,
        markers=fight_objective_markers_from_context(proposal_request),
        state=state,
    )
    if objective_ids:
        if proposal.consolidation_mode is not ConsolidationModeKind.OBJECTIVE:
            return invalid_consolidation_mode(proposal_request, "objective")
        if proposal.objective_id not in objective_ids:
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="objective_consolidation_target_not_legal",
                message="Objective Consolidation requires one objective marker within range.",
                field="objective_id",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code="consolidation_no_legal_mode",
        message="Consolidation proposal has no legal mode.",
        field="consolidation_mode",
    )


def validate_consolidation_endpoint(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    after: UnitPlacement,
    state: GameState | None,
) -> ProposalValidationResult | None:
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
    if proposal.consolidation_mode in {
        ConsolidationModeKind.ONGOING,
        ConsolidationModeKind.ENGAGING,
    }:
        closer_violation = fight_moved_models_closer_to_targets_violation(
            scenario=scenario,
            before=before,
            after=after,
            target_unit_instance_ids=proposal.consolidate_target_unit_instance_ids,
            state=state,
        )
        if closer_violation is not None:
            return fight_movement_endpoint_invalid(proposal_request, closer_violation, "witness")
        if proposal.consolidation_mode is ConsolidationModeKind.ONGOING:
            continuing_violation = fight_continuing_engagement_violation(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                before=before,
                after=after,
                state=state,
            )
            if continuing_violation is not None:
                return fight_movement_endpoint_invalid(
                    proposal_request, continuing_violation, "witness"
                )
        if proposal.consolidation_mode is ConsolidationModeKind.ENGAGING:
            for target_id in proposal.consolidate_target_unit_instance_ids:
                if not fight_unit_is_engaged_with_any(
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    unit_placement=after,
                    target_unit_instance_ids=(target_id,),
                    state=state,
                ):
                    return fight_movement_endpoint_invalid(
                        proposal_request,
                        "engaging_consolidation_target_not_engaged_after",
                        "witness",
                    )
    if proposal.consolidation_mode is ConsolidationModeKind.OBJECTIVE:
        attempted_scenario = fight_scenario_with_unit_placement(
            scenario=scenario,
            placement=after,
        )
        if scenario_physically_engaged_enemy_rules_unit_ids(
            scenario=attempted_scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=proposal.unit_instance_id,
        ):
            return fight_movement_endpoint_invalid(
                proposal_request,
                "objective_consolidation_unit_engaged_after",
                "witness",
            )
        objective = consolidation_objective_by_id(
            objective_id=proposal.objective_id,
            markers=fight_objective_markers_from_context(proposal_request),
            state=state,
        )
        if not any(
            distance.within_control_range
            for distance in consolidation_objective_distances(
                scenario=scenario,
                placements=after.model_placements,
                objective=objective,
            )
        ):
            return fight_movement_endpoint_invalid(
                proposal_request, "objective_consolidation_not_in_range", "witness"
            )
    violation = consolidation_model_violation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        proposal=proposal,
        before=before.model_placements,
        after=after.model_placements,
        state=state,
    )
    return (
        None
        if violation is None
        else fight_movement_endpoint_invalid(proposal_request, violation, "witness")
    )
