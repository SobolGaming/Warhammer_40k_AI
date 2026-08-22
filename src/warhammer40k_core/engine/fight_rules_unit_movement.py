from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.objectives import ObjectiveMarker, ObjectiveMarkerPayload
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ENEMY_DISTANCE_INCHES,
    PILE_IN_TARGET_DISTANCE_INCHES,
    FightMovementEndpointPayload,
    FightMovementProposal,
    FightMovementResolution,
    fight_movement_maximum_distance_inches,
    fight_movement_resolution_violation,
    legal_consolidation_modes,
    resolve_fight_movement,
)
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    FightRulesUnitMovementResolution,
    FightRulesUnitPlacement,
    RulesUnitFightMovementResolution,
    RulesUnitMovementRollbackRecord,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    placed_alive_rules_unit_views,
    rules_unit_identity_ids,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.unit_coherency import rules_unit_coherency_result
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_BASE_CONTACT_EPSILON = 1e-9
_CLOSER_EPSILON = 1e-9


def rules_unit_fight_movement_maximum_distance_inches(
    *,
    state: GameState,
    unit_instance_id: str,
    proposal_kind: ProposalKind,
) -> float:
    rules_unit = _canonical_rules_unit(state=state, unit_instance_id=unit_instance_id)
    if not rules_unit.is_attached_rules_unit:
        return fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=unit_instance_id,
            proposal_kind=proposal_kind,
        )
    return max(
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=identity_id,
            proposal_kind=proposal_kind,
        )
        for identity_id in rules_unit_identity_ids(
            state=state,
            unit_instance_id=unit_instance_id,
        )
    )


def legal_rules_unit_pile_in_target_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    state: GameState,
) -> tuple[str, ...]:
    rules_unit = _canonical_rules_unit(state=state, unit_instance_id=unit_instance_id)
    engaged = _engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        state=state,
    )
    if engaged:
        return engaged
    source_models = _geometry_models_for_rules_unit(scenario=scenario, rules_unit=rules_unit)
    return tuple(
        target.unit_instance_id
        for target in _enemy_rules_units(state=state, rules_unit=rules_unit)
        if _closest_distance(
            source_models,
            _geometry_models_for_rules_unit(scenario=scenario, rules_unit=target),
        )
        <= PILE_IN_TARGET_DISTANCE_INCHES
    )


def legal_rules_unit_consolidation_modes(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    objective_markers: tuple[ObjectiveMarker, ...],
    state: GameState,
) -> tuple[ConsolidationModeKind, ...]:
    rules_unit = _canonical_rules_unit(state=state, unit_instance_id=unit_instance_id)
    if not rules_unit.is_attached_rules_unit:
        return legal_consolidation_modes(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=unit_instance_id,
            objective_markers=objective_markers,
            state=state,
        )
    if _engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        state=state,
    ):
        return (ConsolidationModeKind.ONGOING,)
    source_models = _geometry_models_for_rules_unit(scenario=scenario, rules_unit=rules_unit)
    if any(
        _closest_distance(
            source_models,
            _geometry_models_for_rules_unit(scenario=scenario, rules_unit=target),
        )
        <= CONSOLIDATE_ENEMY_DISTANCE_INCHES
        for target in _enemy_rules_units(state=state, rules_unit=rules_unit)
    ):
        return (ConsolidationModeKind.ENGAGING,)
    source_placements = _present_model_placements(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if any(
        _rules_unit_distance_to_objective(
            model_placements=source_placements,
            objective_marker=marker,
        )
        <= 3.0
        for marker in objective_markers
    ):
        return (ConsolidationModeKind.OBJECTIVE,)
    return ()


def fight_rules_unit_movement_rule_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    eligible_unit_ids: tuple[str, ...],
    state: GameState,
) -> ProposalValidationResult:
    target_ids = proposal.target_unit_instance_ids
    if len(target_ids) != len(set(target_ids)):
        target_field = (
            "pile_in_target_unit_instance_ids"
            if proposal.proposal_kind is ProposalKind.PILE_IN
            else "consolidate_target_unit_instance_ids"
        )
        return _invalid(
            request=proposal_request,
            code="fight_movement_target_ids_duplicated",
            message="Fight movement target unit IDs must be unique.",
            field=target_field,
        )
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    identity_violation = _target_identity_violation(
        state=state,
        request=proposal_request,
        target_unit_instance_ids=proposal.target_unit_instance_ids,
    )
    if identity_violation is not None:
        return identity_violation
    if proposal.unit_instance_id not in eligible_unit_ids:
        return _invalid(
            request=proposal_request,
            code="fight_movement_unit_not_eligible",
            message="Fight movement proposal unit is not eligible for this step.",
            field="unit_instance_id",
        )
    if proposal.is_no_move_choice:
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    if proposal.proposal_kind is ProposalKind.PILE_IN:
        return _pile_in_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            request=proposal_request,
            proposal=proposal,
            rules_unit=rules_unit,
            state=state,
        )
    return _consolidation_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        request=proposal_request,
        proposal=proposal,
        rules_unit=rules_unit,
        state=state,
    )


def fight_rules_unit_movement_witness_matches_current_status(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
) -> ProposalValidationResult | None:
    witness = proposal.witness
    if witness is None:
        return None
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    if rules_unit.is_attached_rules_unit:
        placements = _present_model_placements(
            scenario=scenario,
            rules_unit=rules_unit,
        )
    else:
        placements = scenario.battlefield_state.unit_placement_by_id(
            proposal.unit_instance_id
        ).model_placements
    expected_model_ids = tuple(sorted(placement.model_instance_id for placement in placements))
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        return _invalid(
            request=proposal_request,
            code="fight_movement_witness_model_drift",
            message="Fight movement witness must match selected rules-unit models.",
            field="witness",
            status="stale",
        )
    for placement in placements:
        if witness.poses_for_model(placement.model_instance_id)[0] != placement.pose:
            return _invalid(
                request=proposal_request,
                code="fight_movement_witness_start_drift",
                message="Fight movement witness must start at current model poses.",
                field="witness",
                status="stale",
            )
    return None


def resolve_rules_unit_fight_movement(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal: FightMovementProposal,
    maximum_distance_inches: float,
    state: GameState,
) -> FightRulesUnitMovementResolution:
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit:
        physical_proposal = _proposal_with_physical_target_ids(
            scenario=scenario,
            state=state,
            proposal=proposal,
        )
        resolution = resolve_fight_movement(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            proposal=physical_proposal,
            maximum_distance_inches=maximum_distance_inches,
            state=state,
        )
        return replace(
            resolution,
            endpoint_witness=_canonical_standalone_endpoint_witness(
                endpoint_witness=resolution.endpoint_witness,
                proposal=proposal,
                state=state,
            ),
        )
    before = _present_rules_unit_placement(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if proposal.is_no_move_choice:
        return RulesUnitFightMovementResolution(
            unit_instance_id=rules_unit.unit_instance_id,
            proposal_kind=proposal.proposal_kind,
            movement_phase_action=proposal.movement_phase_action,
            movement_mode=proposal.movement_mode,
            maximum_distance_inches=maximum_distance_inches,
            before_rules_unit_placement=before,
            attempted_rules_unit_placement=before,
            witness=None,
            endpoint_witness=_endpoint_witness(
                before_scenario=scenario,
                after_scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                rules_unit=rules_unit,
                before=before,
                after=before,
                target_unit_instance_ids=(),
                objective_id=None,
                state=state,
            ),
            path_validation_results=(),
            terrain_path_legality_results=(),
            coherency_result=None,
            rollback_record=None,
        )
    witness = proposal.witness
    if witness is None:
        raise GameLifecycleError("Rules-unit Fight movement requires a PathWitness.")
    _require_witness_matches_placement(witness=witness, placement=before)
    attempted = _attempted_rules_unit_placement(before=before, witness=witness)
    attempted_scenario = _scenario_with_rules_unit_placement(
        scenario=scenario,
        placement=attempted,
    )
    path_results: list[PathValidationResult] = []
    terrain_results: list[TerrainPathLegalityResult] = []
    physical_target_ids = _physical_target_ids(
        scenario=scenario,
        state=state,
        target_unit_instance_ids=proposal.target_unit_instance_ids,
    )
    attempted_by_component = {
        placement.unit_instance_id: placement for placement in attempted.component_unit_placements
    }
    for before_component in before.component_unit_placements:
        component_scenario = _scenario_with_component_placement(
            scenario=attempted_scenario,
            placement=before_component,
        )
        component_witness = PathWitness.for_paths(
            tuple(
                (
                    placement.model_instance_id,
                    witness.poses_for_model(placement.model_instance_id),
                )
                for placement in before_component.model_placements
            )
        )
        component_proposal = replace(
            proposal,
            unit_instance_id=before_component.unit_instance_id,
            pile_in_target_unit_instance_ids=(
                physical_target_ids if proposal.proposal_kind is ProposalKind.PILE_IN else ()
            ),
            consolidate_target_unit_instance_ids=(
                physical_target_ids if proposal.proposal_kind is ProposalKind.CONSOLIDATE else ()
            ),
            witness=component_witness,
        )
        component_resolution = resolve_fight_movement(
            scenario=component_scenario,
            ruleset_descriptor=ruleset_descriptor,
            proposal=component_proposal,
            maximum_distance_inches=maximum_distance_inches,
            state=state,
        )
        if (
            component_resolution.attempted_placement
            != attempted_by_component[before_component.unit_instance_id]
        ):
            raise GameLifecycleError("Rules-unit Fight movement component resolution drift.")
        path_results.extend(component_resolution.path_validation_results)
        terrain_results.extend(component_resolution.terrain_path_legality_results)
    coherency_result = rules_unit_coherency_result(
        scenario=attempted_scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
    )
    rollback = (
        None
        if coherency_result.is_coherent
        else RulesUnitMovementRollbackRecord(
            unit_instance_id=rules_unit.unit_instance_id,
            displacement_kind=_displacement_kind(proposal.proposal_kind),
            before_rules_unit_placement=before,
            attempted_rules_unit_placement=attempted,
            coherency_result=coherency_result,
        )
    )
    return RulesUnitFightMovementResolution(
        unit_instance_id=rules_unit.unit_instance_id,
        proposal_kind=proposal.proposal_kind,
        movement_phase_action=proposal.movement_phase_action,
        movement_mode=proposal.movement_mode,
        maximum_distance_inches=maximum_distance_inches,
        before_rules_unit_placement=before,
        attempted_rules_unit_placement=attempted,
        witness=witness,
        endpoint_witness=_endpoint_witness(
            before_scenario=scenario,
            after_scenario=attempted_scenario,
            ruleset_descriptor=ruleset_descriptor,
            rules_unit=rules_unit,
            before=before,
            after=attempted,
            target_unit_instance_ids=proposal.target_unit_instance_ids,
            objective_id=proposal.objective_id,
            state=state,
        ),
        path_validation_results=tuple(path_results),
        terrain_path_legality_results=tuple(terrain_results),
        coherency_result=coherency_result,
        rollback_record=rollback,
    )


def fight_rules_unit_movement_resolution_violation(
    *,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    resolution: FightRulesUnitMovementResolution,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    state: GameState,
) -> ProposalValidationResult | None:
    if isinstance(resolution, FightMovementResolution):
        physical_proposal = _proposal_with_physical_target_ids(
            scenario=scenario,
            state=state,
            proposal=proposal,
        )
        return fight_movement_resolution_violation(
            proposal_request=proposal_request,
            proposal=physical_proposal,
            resolution=resolution,
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            state=state,
        )
    rules_unit = _canonical_rules_unit(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
    )
    for path_result in resolution.path_validation_results:
        if not path_result.is_valid:
            violation = path_result.violations[0]
            return _invalid(
                request=proposal_request,
                code=violation.violation_code,
                message=violation.message,
                field="witness",
            )
    for terrain_result in resolution.terrain_path_legality_results:
        if not terrain_result.is_valid:
            terrain_violation = terrain_result.violations[0]
            return _invalid(
                request=proposal_request,
                code=terrain_violation.violation_code,
                message=terrain_violation.message,
                field="witness",
            )
    if resolution.rollback_record is not None:
        return _invalid(
            request=proposal_request,
            code="unit_coherency_invalid",
            message="Fight movement endpoint violates rules-unit coherency.",
            field="witness",
        )
    if proposal.is_no_move_choice:
        return None
    before = resolution.before_rules_unit_placement
    after = resolution.attempted_rules_unit_placement
    after_scenario = _scenario_with_rules_unit_placement(
        scenario=scenario,
        placement=after,
    )
    return _endpoint_validation(
        before_scenario=scenario,
        after_scenario=after_scenario,
        ruleset_descriptor=ruleset_descriptor,
        request=proposal_request,
        proposal=proposal,
        rules_unit=rules_unit,
        before=before,
        after=after,
        state=state,
    )


def fight_rules_unit_movement_transition_batch(
    *,
    scenario: BattlefieldScenario,
    resolution: FightRulesUnitMovementResolution,
) -> BattlefieldTransitionBatch:
    if isinstance(resolution, RulesUnitFightMovementResolution):
        return resolution.transition_batch()
    before = scenario.battlefield_state.unit_placement_by_id(resolution.unit_instance_id)
    return resolution.transition_batch(before=before)


def apply_fight_rules_unit_movement_resolution(
    *,
    battlefield_state: BattlefieldRuntimeState,
    resolution: FightRulesUnitMovementResolution,
) -> BattlefieldRuntimeState:
    if isinstance(resolution, FightMovementResolution):
        return battlefield_state.with_unit_placement(resolution.attempted_placement)
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid rules-unit Fight movement cannot mutate state.")
    for before in resolution.before_rules_unit_placement.component_unit_placements:
        if battlefield_state.unit_placement_by_id(before.unit_instance_id) != before:
            raise GameLifecycleError("Rules-unit Fight movement application context drift.")
    if resolution.before_rules_unit_placement == resolution.attempted_rules_unit_placement:
        return battlefield_state
    updated = battlefield_state
    for attempted in resolution.attempted_rules_unit_placement.component_unit_placements:
        updated = updated.with_unit_placement(attempted)
    return updated


def _pile_in_rule_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    request: MovementProposalRequest,
    proposal: FightMovementProposal,
    rules_unit: RulesUnitView,
    state: GameState,
) -> ProposalValidationResult:
    legal_targets = legal_rules_unit_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=rules_unit.unit_instance_id,
        state=state,
    )
    if not legal_targets:
        return _invalid(
            request=request,
            code="pile_in_no_legal_targets",
            message="Pile In proposal has no legal target units.",
            field="pile_in_target_unit_instance_ids",
        )
    selected = proposal.pile_in_target_unit_instance_ids
    if not selected:
        return _invalid(
            request=request,
            code="pile_in_target_required",
            message="Pile In movement requires one or more target units.",
            field="pile_in_target_unit_instance_ids",
        )
    engaged = _engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        state=state,
    )
    if engaged and set(selected) != set(engaged):
        return _invalid(
            request=request,
            code="pile_in_engaged_targets_must_be_complete",
            message="An engaged rules unit must select every engaged enemy rules unit.",
            field="pile_in_target_unit_instance_ids",
        )
    if set(selected) - set(legal_targets):
        return _invalid(
            request=request,
            code="pile_in_target_not_legal",
            message="Pile In selected a target outside legal target rules units.",
            field="pile_in_target_unit_instance_ids",
        )
    return ProposalValidationResult.valid(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
    )


def _consolidation_rule_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    request: MovementProposalRequest,
    proposal: FightMovementProposal,
    rules_unit: RulesUnitView,
    state: GameState,
) -> ProposalValidationResult:
    mode = proposal.consolidation_mode
    if mode is None:
        return _invalid(
            request=request,
            code="consolidation_mode_required",
            message="Consolidation movement requires a consolidation mode.",
            field="consolidation_mode",
        )
    engaged = _engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        state=state,
    )
    if engaged:
        if mode is not ConsolidationModeKind.ONGOING:
            return _invalid_consolidation_mode(request=request, expected="ongoing")
        if set(proposal.consolidate_target_unit_instance_ids) != set(engaged):
            return _invalid(
                request=request,
                code="ongoing_consolidation_targets_must_be_complete",
                message="Ongoing Consolidation must select every engaged enemy rules unit.",
                field="consolidate_target_unit_instance_ids",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )
    source_models = _geometry_models_for_rules_unit(scenario=scenario, rules_unit=rules_unit)
    enemies_within_three = tuple(
        target.unit_instance_id
        for target in _enemy_rules_units(state=state, rules_unit=rules_unit)
        if _closest_distance(
            source_models,
            _geometry_models_for_rules_unit(scenario=scenario, rules_unit=target),
        )
        <= CONSOLIDATE_ENEMY_DISTANCE_INCHES
    )
    if enemies_within_three:
        if mode is not ConsolidationModeKind.ENGAGING:
            return _invalid_consolidation_mode(request=request, expected="engaging")
        selected = set(proposal.consolidate_target_unit_instance_ids)
        if not selected or selected - set(enemies_within_three):
            return _invalid(
                request=request,
                code="engaging_consolidation_target_not_legal",
                message=(
                    "Engaging Consolidation requires one or more enemy rules units within 3 inches."
                ),
                field="consolidate_target_unit_instance_ids",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )
    source_placements = _present_model_placements(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    objective_ids = {
        marker.objective_marker_id
        for marker in _objective_markers_from_request(request)
        if _rules_unit_distance_to_objective(
            model_placements=source_placements,
            objective_marker=marker,
        )
        <= marker.control_horizontal_inches
    }
    if objective_ids:
        if mode is not ConsolidationModeKind.OBJECTIVE:
            return _invalid_consolidation_mode(request=request, expected="objective")
        if proposal.objective_id not in objective_ids:
            return _invalid(
                request=request,
                code="objective_consolidation_target_not_legal",
                message="Objective Consolidation requires one objective marker within range.",
                field="objective_id",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )
    return _invalid(
        request=request,
        code="consolidation_no_legal_mode",
        message="Consolidation proposal has no legal mode.",
        field="consolidation_mode",
    )


def _endpoint_validation(
    *,
    before_scenario: BattlefieldScenario,
    after_scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    request: MovementProposalRequest,
    proposal: FightMovementProposal,
    rules_unit: RulesUnitView,
    before: FightRulesUnitPlacement,
    after: FightRulesUnitPlacement,
    state: GameState,
) -> ProposalValidationResult | None:
    before_models = _geometry_models_for_placement(
        scenario=before_scenario,
        placement=before,
    )
    after_models = _geometry_models_for_placement(
        scenario=after_scenario,
        placement=after,
    )
    after_by_id = {model.model_id: model for model in after_models}
    if proposal.proposal_kind is ProposalKind.PILE_IN or proposal.consolidation_mode in {
        ConsolidationModeKind.ONGOING,
        ConsolidationModeKind.ENGAGING,
    }:
        enemy_models_before = _enemy_geometry_models(
            scenario=before_scenario,
            state=state,
            player_id=rules_unit.owner_player_id,
        )
        for model in before_models:
            if (
                any(model.range_to(enemy) <= _BASE_CONTACT_EPSILON for enemy in enemy_models_before)
                and after_by_id[model.model_id].pose != model.pose
            ):
                return _endpoint_invalid(request=request, code="base_contact_model_moved")
        closer_violation = _moved_model_closer_violation(
            before_scenario=before_scenario,
            after_scenario=after_scenario,
            before_models=before_models,
            after_models=after_models,
            target_unit_instance_ids=proposal.target_unit_instance_ids,
            state=state,
        )
        if closer_violation is not None:
            return _endpoint_invalid(request=request, code=closer_violation)
    if proposal.proposal_kind is ProposalKind.PILE_IN:
        if not _rules_unit_engaged_with_targets(
            scenario=after_scenario,
            ruleset_descriptor=ruleset_descriptor,
            source_models=after_models,
            target_unit_instance_ids=proposal.pile_in_target_unit_instance_ids,
            state=state,
        ):
            return _endpoint_invalid(request=request, code="pile_in_unit_not_engaged_after")
        continuing = _continuing_engagement_violation(
            before_scenario=before_scenario,
            after_scenario=after_scenario,
            ruleset_descriptor=ruleset_descriptor,
            rules_unit=rules_unit,
            before_models=before_models,
            after_models=after_models,
            state=state,
        )
        return None if continuing is None else _endpoint_invalid(request=request, code=continuing)
    if proposal.consolidation_mode is ConsolidationModeKind.ONGOING:
        continuing = _continuing_engagement_violation(
            before_scenario=before_scenario,
            after_scenario=after_scenario,
            ruleset_descriptor=ruleset_descriptor,
            rules_unit=rules_unit,
            before_models=before_models,
            after_models=after_models,
            state=state,
        )
        return None if continuing is None else _endpoint_invalid(request=request, code=continuing)
    if proposal.consolidation_mode is ConsolidationModeKind.ENGAGING:
        for target_id in proposal.consolidate_target_unit_instance_ids:
            if not _rules_unit_engaged_with_targets(
                scenario=after_scenario,
                ruleset_descriptor=ruleset_descriptor,
                source_models=after_models,
                target_unit_instance_ids=(target_id,),
                state=state,
            ):
                return _endpoint_invalid(
                    request=request,
                    code="engaging_consolidation_target_not_engaged_after",
                )
        return None
    if proposal.consolidation_mode is ConsolidationModeKind.OBJECTIVE:
        if _engaged_enemy_rules_unit_ids(
            scenario=after_scenario,
            ruleset_descriptor=ruleset_descriptor,
            rules_unit=rules_unit,
            state=state,
        ):
            return _endpoint_invalid(
                request=request,
                code="objective_consolidation_unit_engaged_after",
            )
        marker = _objective_marker_by_id(
            request=request,
            objective_id=proposal.objective_id,
        )
        if (
            _rules_unit_distance_to_objective(
                model_placements=after.model_placements,
                objective_marker=marker,
            )
            > marker.control_horizontal_inches
        ):
            return _endpoint_invalid(
                request=request,
                code="objective_consolidation_not_in_range",
            )
    return None


def _moved_model_closer_violation(
    *,
    before_scenario: BattlefieldScenario,
    after_scenario: BattlefieldScenario,
    before_models: tuple[GeometryModel, ...],
    after_models: tuple[GeometryModel, ...],
    target_unit_instance_ids: tuple[str, ...],
    state: GameState,
) -> str | None:
    if not target_unit_instance_ids:
        return "target_unit_required"
    after_by_id = {model.model_id: model for model in after_models}
    before_targets = _geometry_models_for_target_ids(
        scenario=before_scenario,
        state=state,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    after_targets = _geometry_models_for_target_ids(
        scenario=after_scenario,
        state=state,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    for before_model in before_models:
        after_model = after_by_id[before_model.model_id]
        if after_model.pose == before_model.pose:
            continue
        before_distance = min(before_model.range_to(target) for target in before_targets)
        after_distance = min(after_model.range_to(target) for target in after_targets)
        if not after_distance < before_distance - _CLOSER_EPSILON:
            return "moved_model_not_closer_to_target"
    return None


def _continuing_engagement_violation(
    *,
    before_scenario: BattlefieldScenario,
    after_scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    before_models: tuple[GeometryModel, ...],
    after_models: tuple[GeometryModel, ...],
    state: GameState,
) -> str | None:
    after_by_id = {model.model_id: model for model in after_models}
    for target in _enemy_rules_units(state=state, rules_unit=rules_unit):
        target_before = _geometry_models_for_rules_unit(
            scenario=before_scenario,
            rules_unit=target,
        )
        target_after = _geometry_models_for_rules_unit(
            scenario=after_scenario,
            rules_unit=target,
        )
        for before_model in before_models:
            if not _model_engaged(
                model=before_model,
                target_models=target_before,
                ruleset_descriptor=ruleset_descriptor,
            ):
                continue
            if not _model_engaged(
                model=after_by_id[before_model.model_id],
                target_models=target_after,
                ruleset_descriptor=ruleset_descriptor,
            ):
                return "started_engaged_model_not_engaged_after"
    return None


def _endpoint_witness(
    *,
    before_scenario: BattlefieldScenario,
    after_scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    before: FightRulesUnitPlacement,
    after: FightRulesUnitPlacement,
    target_unit_instance_ids: tuple[str, ...],
    objective_id: str | None,
    state: GameState,
) -> FightMovementEndpointPayload:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    return {
        "target_unit_instance_ids": list(target_unit_instance_ids),
        "objective_id": objective_id,
        "moved_model_instance_ids": [
            placement.model_instance_id
            for placement in after.model_placements
            if placement.pose != before_poses[placement.model_instance_id]
        ],
        "engaged_before_unit_ids": list(
            _engaged_enemy_rules_unit_ids(
                scenario=before_scenario,
                ruleset_descriptor=ruleset_descriptor,
                rules_unit=rules_unit,
                state=state,
            )
        ),
        "engaged_after_unit_ids": list(
            _engaged_enemy_rules_unit_ids(
                scenario=after_scenario,
                ruleset_descriptor=ruleset_descriptor,
                rules_unit=rules_unit,
                state=state,
            )
        ),
    }


def _engaged_enemy_rules_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    state: GameState,
) -> tuple[str, ...]:
    source_models = _geometry_models_for_rules_unit(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    return tuple(
        target.unit_instance_id
        for target in _enemy_rules_units(state=state, rules_unit=rules_unit)
        if any(
            source.is_within_engagement_range(
                enemy,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            )
            for source in source_models
            for enemy in _geometry_models_for_rules_unit(
                scenario=scenario,
                rules_unit=target,
            )
        )
    )


def _rules_unit_engaged_with_targets(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    source_models: tuple[GeometryModel, ...],
    target_unit_instance_ids: tuple[str, ...],
    state: GameState,
) -> bool:
    target_models = _geometry_models_for_target_ids(
        scenario=scenario,
        state=state,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    return any(
        source.is_within_engagement_range(
            target,
            horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
            vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
        )
        for source in source_models
        for target in target_models
    )


def _model_engaged(
    *,
    model: GeometryModel,
    target_models: tuple[GeometryModel, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    return any(
        model.is_within_engagement_range(
            target,
            horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
            vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
        )
        for target in target_models
    )


def _geometry_models_for_target_ids(
    *,
    scenario: BattlefieldScenario,
    state: GameState,
    target_unit_instance_ids: tuple[str, ...],
) -> tuple[GeometryModel, ...]:
    return tuple(
        model
        for target_id in target_unit_instance_ids
        for model in _geometry_models_for_rules_unit(
            scenario=scenario,
            rules_unit=_canonical_rules_unit(state=state, unit_instance_id=target_id),
        )
    )


def _enemy_geometry_models(
    *,
    scenario: BattlefieldScenario,
    state: GameState,
    player_id: str,
) -> tuple[GeometryModel, ...]:
    return tuple(
        model
        for rules_unit in placed_alive_rules_unit_views(state=state)
        if rules_unit.owner_player_id != player_id
        for model in _geometry_models_for_rules_unit(
            scenario=scenario,
            rules_unit=rules_unit,
        )
    )


def _geometry_models_for_rules_unit(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    models: list[GeometryModel] = []
    for placement in _present_model_placements(
        scenario=scenario,
        rules_unit=rules_unit,
    ):
        models.append(
            geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            )
        )
    return tuple(models)


def _geometry_models_for_placement(
    *,
    scenario: BattlefieldScenario,
    placement: FightRulesUnitPlacement,
) -> tuple[GeometryModel, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in placement.model_placements
        if scenario.model_is_present_at_placement(model_placement)
    )


def _present_model_placements(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    placements: list[ModelPlacement] = []
    for component in rules_unit.components:
        unit_placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if unit_placement is None:
            if any(model.is_alive for model in component.unit.own_models):
                raise GameLifecycleError(
                    "Fight rules-unit geometry requires every living component to be placed."
                )
            continue
        placements.extend(
            placement
            for placement in unit_placement.model_placements
            if scenario.model_is_present_at_placement(placement)
        )
    if not placements:
        raise GameLifecycleError("Fight rules unit requires present models.")
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def _present_rules_unit_placement(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> FightRulesUnitPlacement:
    present_model_ids = {
        placement.model_instance_id
        for placement in _present_model_placements(
            scenario=scenario,
            rules_unit=rules_unit,
        )
    }
    components: list[UnitPlacement] = []
    for component in rules_unit.components:
        placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if placement is None:
            continue
        selected = tuple(
            model_placement
            for model_placement in placement.model_placements
            if model_placement.model_instance_id in present_model_ids
        )
        if selected:
            components.append(placement.with_model_placements(selected))
    return FightRulesUnitPlacement(
        rules_unit_instance_id=rules_unit.unit_instance_id,
        component_unit_placements=tuple(components),
    )


def _attempted_rules_unit_placement(
    *,
    before: FightRulesUnitPlacement,
    witness: PathWitness,
) -> FightRulesUnitPlacement:
    return FightRulesUnitPlacement(
        rules_unit_instance_id=before.rules_unit_instance_id,
        component_unit_placements=tuple(
            component.with_model_placements(
                tuple(
                    placement.with_pose(witness.final_pose_for_model(placement.model_instance_id))
                    for placement in component.model_placements
                )
            )
            for component in before.component_unit_placements
        ),
    )


def _scenario_with_rules_unit_placement(
    *,
    scenario: BattlefieldScenario,
    placement: FightRulesUnitPlacement,
) -> BattlefieldScenario:
    battlefield = scenario.battlefield_state
    for component in placement.component_unit_placements:
        battlefield = battlefield.with_unit_placement(component)
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=battlefield,
        present_destroyed_model_ids=scenario.present_destroyed_model_ids,
    )


def _scenario_with_component_placement(
    *,
    scenario: BattlefieldScenario,
    placement: UnitPlacement,
) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(placement),
        present_destroyed_model_ids=scenario.present_destroyed_model_ids,
    )


def _physical_target_ids(
    *,
    scenario: BattlefieldScenario,
    state: GameState,
    target_unit_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        component.unit.unit_instance_id
        for target_id in target_unit_instance_ids
        for component in _canonical_rules_unit(
            state=state,
            unit_instance_id=target_id,
        ).components
        if scenario.battlefield_state.is_unit_placed(component.unit.unit_instance_id)
    )


def _proposal_with_physical_target_ids(
    *,
    scenario: BattlefieldScenario,
    state: GameState,
    proposal: FightMovementProposal,
) -> FightMovementProposal:
    physical_target_ids = _physical_target_ids(
        scenario=scenario,
        state=state,
        target_unit_instance_ids=proposal.target_unit_instance_ids,
    )
    if proposal.proposal_kind is ProposalKind.PILE_IN:
        return replace(
            proposal,
            pile_in_target_unit_instance_ids=physical_target_ids,
        )
    return replace(
        proposal,
        consolidate_target_unit_instance_ids=physical_target_ids,
    )


def _canonical_standalone_endpoint_witness(
    *,
    endpoint_witness: FightMovementEndpointPayload,
    proposal: FightMovementProposal,
    state: GameState,
) -> FightMovementEndpointPayload:
    canonical = dict(endpoint_witness)
    canonical["target_unit_instance_ids"] = list(proposal.target_unit_instance_ids)
    for field in ("engaged_before_unit_ids", "engaged_after_unit_ids"):
        identity_ids = endpoint_witness[field]
        canonical[field] = sorted(
            {
                rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=identity_id,
                ).unit_instance_id
                for identity_id in identity_ids
            }
        )
    return cast(FightMovementEndpointPayload, canonical)


def _target_identity_violation(
    *,
    state: GameState,
    request: MovementProposalRequest,
    target_unit_instance_ids: tuple[str, ...],
) -> ProposalValidationResult | None:
    canonical_by_identity = {
        identity_id: view.unit_instance_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        for identity_id in (view.unit_instance_id, *view.component_unit_instance_ids)
    }
    for target_id in target_unit_instance_ids:
        canonical_id = canonical_by_identity.get(target_id)
        if canonical_id is not None and canonical_id != target_id:
            return _invalid(
                request=request,
                code="fight_movement_target_identity_not_canonical",
                message="Fight movement targets must use canonical rules-unit identities.",
                field=(
                    "pile_in_target_unit_instance_ids"
                    if request.proposal_kind is ProposalKind.PILE_IN
                    else "consolidate_target_unit_instance_ids"
                ),
            )
    return None


def _require_witness_matches_placement(
    *,
    witness: PathWitness,
    placement: FightRulesUnitPlacement,
) -> None:
    expected = _model_ids(placement)
    if tuple(sorted(witness.model_ids())) != expected:
        raise GameLifecycleError("Fight movement witness model identity drift.")
    for model_placement in placement.model_placements:
        if witness.poses_for_model(model_placement.model_instance_id)[0] != model_placement.pose:
            raise GameLifecycleError("Fight movement witness start pose drift.")


def _enemy_rules_units(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[RulesUnitView, ...]:
    return tuple(
        view
        for view in placed_alive_rules_unit_views(state=state)
        if view.owner_player_id != rules_unit.owner_player_id
    )


def _canonical_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> RulesUnitView:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_id)
    if rules_unit.unit_instance_id != requested_id:
        raise GameLifecycleError("Fight movement rules-unit identity must be canonical.")
    return rules_unit


def _closest_distance(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> float:
    if not first_models or not second_models:
        raise GameLifecycleError("Fight rules-unit distance requires present models.")
    return min(first.range_to(second) for first in first_models for second in second_models)


def _rules_unit_distance_to_objective(
    *,
    model_placements: tuple[ModelPlacement, ...],
    objective_marker: ObjectiveMarker,
) -> float:
    marker_pose = Pose.at(objective_marker.x_inches, objective_marker.y_inches)
    return min(
        placement.pose.position.distance_2d_to(marker_pose.position)
        for placement in model_placements
    )


def _objective_markers_from_request(
    request: MovementProposalRequest,
) -> tuple[ObjectiveMarker, ...]:
    context = request.context
    if not isinstance(context, dict):
        raise GameLifecycleError("Consolidation request context must be an object.")
    payloads = context.get("objective_markers")
    if not isinstance(payloads, list):
        raise GameLifecycleError("Consolidation request objective_markers must be a list.")
    markers: list[ObjectiveMarker] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            raise GameLifecycleError("Consolidation objective marker must be an object.")
        markers.append(ObjectiveMarker.from_payload(cast(ObjectiveMarkerPayload, payload)))
    return tuple(markers)


def _objective_marker_by_id(
    *,
    request: MovementProposalRequest,
    objective_id: str | None,
) -> ObjectiveMarker:
    requested_id = _validate_identifier("objective_id", objective_id)
    for marker in _objective_markers_from_request(request):
        if marker.objective_marker_id == requested_id:
            return marker
    raise GameLifecycleError("Consolidation objective is not in the pending request.")


def _endpoint_invalid(
    *,
    request: MovementProposalRequest,
    code: str,
) -> ProposalValidationResult:
    return _invalid(
        request=request,
        code=code,
        message=f"Fight movement endpoint violates {code}.",
        field="witness",
    )


def _invalid_consolidation_mode(
    *,
    request: MovementProposalRequest,
    expected: str,
) -> ProposalValidationResult:
    return _invalid(
        request=request,
        code="consolidation_mode_not_legal",
        message=f"Consolidation mode must be {expected}.",
        field="consolidation_mode",
    )


def _invalid(
    *,
    request: MovementProposalRequest,
    code: str,
    message: str,
    field: str,
    status: str = "invalid",
) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        violation_code=code,
        message=message,
        field=field,
        status=status,
    )


def _model_ids(placement: FightRulesUnitPlacement) -> tuple[str, ...]:
    return tuple(sorted(model.model_instance_id for model in placement.model_placements))


def _displacement_kind(proposal_kind: ProposalKind) -> ModelDisplacementKind:
    if proposal_kind is ProposalKind.PILE_IN:
        return ModelDisplacementKind.PILE_IN
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return ModelDisplacementKind.CONSOLIDATE
    raise GameLifecycleError("Fight movement displacement kind is unsupported.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
