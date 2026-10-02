"""Scout movement over canonical rules units and their physical components."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.prebattle_records import record_prebattle_action
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.scout_movement_paths import append_scout_path_violations
from warhammer40k_core.engine.unit_coherency import UnitCoherencyContext
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    is_degenerate_endpoint_only_real_movement_path,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.prebattle import (
        PreBattleProposalRequest,
        PreBattleResolution,
        PreBattleViolation,
        ScoutMoveProposal,
    )


def apply_scout_move(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> PreBattleResolution:
    from warhammer40k_core.engine.prebattle import (
        PreBattleProposalRequest,
        ScoutMoveProposal,
        ScoutMoveProposalPayload,
        _require_battlefield_state,
        resolve_prebattle_proposal,
    )

    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    proposal = ScoutMoveProposal.from_payload(cast(ScoutMoveProposalPayload, result.payload))
    resolution = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        request=request_context,
        proposal=proposal,
        source_event_id=result.result_id,
    )
    if not resolution.is_valid:
        raise GameLifecycleError("Invalid Scout Move cannot mutate state.")
    if resolution.transition_batch is None:
        raise GameLifecycleError("Scout Move requires a transition batch.")
    battlefield = _require_battlefield_state(state)
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions), unit_instance_id=request_context.unit_instance_id
    )
    current = RulesUnitPlacement.from_battlefield(view=view, battlefield_state=battlefield)
    attempted = _scout_endpoint_placement(current, proposal.witness)
    for component in attempted.component_unit_placements:
        battlefield = battlefield.with_unit_placement(component)
    state.replace_battlefield_state(battlefield)
    record_prebattle_action(
        state=state,
        result=result,
        request=request,
        action_kind=proposal.action_kind,
        unit_instance_id=request_context.unit_instance_id,
        source_rule_id=request_context.source_rule_id,
        payload=validate_json_value(resolution.to_payload()),
    )
    decisions.event_log.append(
        "prebattle_scout_move_completed",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
            "player_id": request_context.player_id,
            "unit_instance_id": request_context.unit_instance_id,
            "action_kind": proposal.action_kind.value,
            "resolution": resolution.to_payload(),
        },
    )
    return resolution


def resolve_scout_move(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    request: PreBattleProposalRequest,
    proposal: ScoutMoveProposal,
    source_event_id: str | None,
) -> PreBattleResolution:
    from warhammer40k_core.engine.prebattle import (
        PreBattleResolution,
        PreBattleViolation,
        PreBattleViolationCode,
        _append_action_eligibility_violations,
        _require_battlefield_state,
        _validate_identifier,
        _validate_prebattle_state,
        start_is_eligible_for_scout_move,
    )

    _validate_prebattle_state(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=_require_battlefield_state(state),
    )
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=request.unit_instance_id,
    )
    current = RulesUnitPlacement.from_battlefield(
        view=view, battlefield_state=scenario.battlefield_state
    )
    violations: list[PreBattleViolation] = []
    _append_action_eligibility_violations(
        violations=violations,
        state=state,
        army_catalog=army_catalog,
        request=request,
        view=view,
    )
    if not start_is_eligible_for_scout_move(state=state, view=view):
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.DEPLOYMENT_ZONE_VIOLATION,
                message=(
                    "Scout Move requires the selected unit to start wholly in its deployment zone."
                ),
                field="unit_instance_id",
            )
        )
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in current.model_placements)
    )
    if tuple(sorted(proposal.witness.model_ids())) != expected_model_ids:
        violations.append(
            PreBattleViolation(
                violation_code=PreBattleViolationCode.WITNESS_MODEL_SET_DRIFT,
                message="Scout Move witness must include every alive placed model in the unit.",
                field="witness",
            )
        )
    for placement in current.model_placements:
        if placement.model_instance_id not in proposal.witness.model_ids():
            continue
        poses = proposal.witness.poses_for_model(placement.model_instance_id)
        if poses[0] != placement.pose:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.WITNESS_START_DRIFT,
                    message="Scout Move witness must start at the current model pose.",
                    field="witness",
                    model_instance_id=placement.model_instance_id,
                )
            )
        if is_degenerate_endpoint_only_real_movement_path(poses):
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.ENDPOINT_ONLY_PATH,
                    message="Scout Move witness must not repeat only endpoint poses.",
                    field="witness",
                    model_instance_id=placement.model_instance_id,
                )
            )
    if violations:
        return PreBattleResolution(
            proposal=proposal,
            violations=tuple(violations),
        )
    attempted_placement = _scout_endpoint_placement(current, proposal.witness)
    if not violations:
        append_scout_path_violations(
            violations=violations,
            state=state,
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            current=current,
            attempted=attempted_placement,
            witness=proposal.witness,
            scout_distance_inches=proposal.scout_distance_inches,
        )
    coherency_result = UnitCoherencyContext.from_ruleset_descriptor(
        ruleset_descriptor, unit_instance_id=view.unit_instance_id
    ).validate_models(attempted_placement.geometry_models(scenario))
    if not coherency_result.is_coherent:
        for model_id in coherency_result.offending_model_instance_ids:
            violations.append(
                PreBattleViolation(
                    violation_code=PreBattleViolationCode.UNIT_COHERENCY_BROKEN,
                    message="Scout Move endpoint breaks unit coherency.",
                    field="witness",
                    model_instance_id=model_id,
                )
            )
    _append_scout_enemy_distance_violations(
        violations=violations,
        state=state,
        scenario=scenario,
        attempted=attempted_placement,
    )
    if violations:
        return PreBattleResolution(
            proposal=proposal,
            violations=tuple(violations),
            coherency_result=coherency_result,
        )
    event_id = (
        request.source_decision_result_id
        if source_event_id is None
        else _validate_identifier("source_event_id", source_event_id)
    )
    transition_batch = BattlefieldTransitionBatch(
        displacements=tuple(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.SCOUT_MOVE,
                start_pose=placement.pose,
                end_pose=proposal.witness.final_pose_for_model(placement.model_instance_id),
                path_witness=PathWitness.for_paths(
                    (
                        (
                            placement.model_instance_id,
                            proposal.witness.poses_for_model(placement.model_instance_id),
                        ),
                    )
                ),
                source_phase=None,
                source_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
                source_rule_id=request.source_rule_id,
                source_event_id=event_id,
            )
            for placement in current.model_placements
            if placement.pose != proposal.witness.final_pose_for_model(placement.model_instance_id)
        )
    )
    return PreBattleResolution(
        proposal=proposal,
        violations=(),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
    )


def _append_scout_enemy_distance_violations(
    *,
    violations: list[PreBattleViolation],
    state: GameState,
    scenario: BattlefieldScenario,
    attempted: RulesUnitPlacement,
) -> None:
    from warhammer40k_core.engine.prebattle import (
        _EPSILON,
        SCOUT_ENEMY_DISTANCE_INCHES,
        PreBattleViolation,
        PreBattleViolationCode,
        enemy_geometry_models_for_player,
    )

    enemy_models = enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=attempted.player_id,
    )
    for placement in attempted.model_placements:
        model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for enemy_model in enemy_models:
            if model.base_distance_to(enemy_model) <= SCOUT_ENEMY_DISTANCE_INCHES + _EPSILON:
                violations.append(
                    PreBattleViolation(
                        violation_code=PreBattleViolationCode.SCOUT_ENEMY_DISTANCE,
                        message="Scout Move must end more than 8 inches from all enemy units.",
                        field="witness",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )


def _scout_endpoint_placement(
    current: RulesUnitPlacement, witness: PathWitness
) -> RulesUnitPlacement:
    return RulesUnitPlacement(
        rules_unit_instance_id=current.rules_unit_instance_id,
        component_unit_placements=tuple(
            component.with_model_placements(
                tuple(
                    model.with_pose(witness.final_pose_for_model(model.model_instance_id))
                    for model in component.model_placements
                )
            )
            for component in current.component_unit_placements
        ),
    )
