# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import (
    FightPhaseStepKind,
    FightPolicyDescriptor,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_movement_active_player import begin_fight_move, end_fight_move
from warhammer40k_core.engine.fight_movement_target_authority import (
    build_fight_movement_target_authority_witness,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightMovementStepState,
    FightPhaseState,
)
from warhammer40k_core.engine.fight_resolution import (
    FightMovementResolution,
    build_fight_movement_request,
    fight_movement_proposal_from_payload,
)
from warhammer40k_core.engine.fight_rules_unit_movement import (
    apply_fight_rules_unit_movement_resolution,
    fight_rules_unit_movement_resolution_violation,
    fight_rules_unit_movement_transition_batch,
    resolve_rules_unit_fight_movement,
    rules_unit_fight_movement_maximum_distance_inches,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.fight import FightPhaseHandler


def request_fight_movement(
    *,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    movement_state: FightMovementStepState,
    unit_instance_id: str,
) -> LifecycleStatus:
    from warhammer40k_core.engine.phases.fight import (
        _FIGHT_CONSOLIDATE_REQUIRED_STATUS,
        _FIGHT_PILE_IN_REQUIRED_STATUS,
        fight_movement_request_context,
        proposal_kind_for_fight_step,
    )

    proposal_kind = proposal_kind_for_fight_step(movement_state.step)
    context = fight_movement_request_context(
        state=state,
        fight_state=fight_state,
        movement_state=movement_state,
        unit_instance_id=unit_instance_id,
    )
    request = build_fight_movement_request(
        state_game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        request_id=state.next_decision_request_id(),
        actor_id=movement_state.next_player_id,
        unit_instance_id=unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id=(
            f"fight-step:{state.battle_round}:{movement_state.step.value}:request"
        ),
        source_decision_result_id=(
            f"fight-step:{state.battle_round}:{movement_state.step.value}:result"
        ),
        spatial_context_hash=state.physical_proposal_context_hash(),
        context=context,
    )
    decisions.request_decision(request)
    begin_fight_move(state=state, decisions=decisions, request=request)
    phase_body_status = (
        _FIGHT_PILE_IN_REQUIRED_STATUS
        if movement_state.step is FightPhaseStepKind.PILE_IN
        else _FIGHT_CONSOLIDATE_REQUIRED_STATUS
    )
    decisions.event_log.append(
        "fight_movement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": phase_body_status,
                "request_id": request.request_id,
                "player_id": movement_state.next_player_id,
                "unit_instance_id": unit_instance_id,
                "proposal_kind": proposal_kind.value,
                "context": context,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": phase_body_status,
            "unit_instance_id": unit_instance_id,
            "proposal_kind": proposal_kind.value,
        },
    )


def request_overrun_pile_in(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
) -> LifecycleStatus:
    from warhammer40k_core.engine.phases.fight import (
        _FIGHT_PILE_IN_REQUIRED_STATUS,
        fight_movement_request_context,
        require_fight_state,
    )

    fight_state = require_fight_state(state)
    context = fight_movement_request_context(
        state=state,
        fight_state=fight_state,
        movement_state=FightMovementStepState.start(
            step=FightPhaseStepKind.PILE_IN,
            next_player_id=activation.player_id,
        ),
        unit_instance_id=activation.unit_instance_id,
    )
    context["fight_movement_timing"] = "overrun"
    request = build_fight_movement_request(
        state_game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        request_id=state.next_decision_request_id(),
        actor_id=activation.player_id,
        unit_instance_id=activation.unit_instance_id,
        proposal_kind=ProposalKind.PILE_IN,
        source_decision_request_id=activation.request_id,
        source_decision_result_id=activation.result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        context=context,
    )
    decisions.request_decision(request)
    begin_fight_move(state=state, decisions=decisions, request=request)
    decisions.event_log.append(
        "overrun_pile_in_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_PILE_IN_REQUIRED_STATUS,
                "request_id": request.request_id,
                "activation_selection": activation.to_payload(),
                "proposal_kind": ProposalKind.PILE_IN.value,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_PILE_IN_REQUIRED_STATUS,
            "unit_instance_id": activation.unit_instance_id,
            "proposal_kind": ProposalKind.PILE_IN.value,
        },
    )


def apply_fight_movement_proposal(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.phases.fight import (
        _ENDPOINT_ONLY_PATH_VIOLATION_CODE,
        _FIGHT_MOVEMENT_COMPLETED_STATUS,
        _battlefield_scenario,
        _fight_step_for_proposal_kind,
        _first_proposal_violation_code,
        _is_overrun_movement_request,
        _movement_step_state,
        _proposal_validation_has_code,
        _with_movement_step_state,
        fight_movement_invalid_message,
        reject_recorded_invalid_fight_movement,
        require_fight_state,
    )

    del handler
    record = decisions.record_for_result(result)
    proposal_request = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    proposal = fight_movement_proposal_from_payload(result.payload)
    target_authority_witness = build_fight_movement_target_authority_witness(
        state=state,
        target_unit_instance_ids=proposal.target_unit_instance_ids,
    )
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        if not _proposal_validation_has_code(
            proposal_validation,
            _ENDPOINT_ONLY_PATH_VIOLATION_CODE,
        ):
            raise GameLifecycleError("Recorded fight movement proposal drifted before application.")
        return reject_recorded_invalid_fight_movement(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            resolution=None,
            target_authority_witness=target_authority_witness,
            message="Fight movement PathWitness must not repeat only endpoint poses.",
        )
    scenario = _battlefield_scenario(state)
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        proposal=proposal,
        maximum_distance_inches=rules_unit_fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=proposal.unit_instance_id,
            proposal_kind=proposal.proposal_kind,
        ),
        state=state,
    )
    resolution_violation = fight_rules_unit_movement_resolution_violation(
        proposal_request=proposal_request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        state=state,
    )
    if resolution_violation is not None:
        violation_code = _first_proposal_violation_code(resolution_violation)
        return reject_recorded_invalid_fight_movement(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=resolution_violation,
            resolution=resolution,
            target_authority_witness=target_authority_witness,
            message=fight_movement_invalid_message(violation_code),
        )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight movement requires battlefield_state.")
    transition_batch = fight_rules_unit_movement_transition_batch(
        scenario=scenario,
        resolution=resolution,
    )
    state.replace_battlefield_state(
        apply_fight_rules_unit_movement_resolution(
            battlefield_state=battlefield_state,
            resolution=resolution,
        )
    )
    fight_state = require_fight_state(state)
    if _is_overrun_movement_request(proposal_request):
        activation = fight_state.active_activation
        if activation is None:
            raise GameLifecycleError("Overrun pile-in application requires active activation.")
        state.replace_fight_phase_state(
            fight_state.with_overrun_pile_in_completed(
                activation_result_id=activation.result_id,
            )
        )
    else:
        movement_state = _movement_step_state(
            fight_state=fight_state,
            step=_fight_step_for_proposal_kind(proposal.proposal_kind),
        ).with_completed_unit(unit_instance_id=proposal.unit_instance_id)
        state.replace_fight_phase_state(
            _with_movement_step_state(
                fight_state=fight_state,
                movement_state=movement_state,
            )
        )
    completed_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": fight_state.active_player_id,
        "phase": BattlePhase.FIGHT.value,
        "phase_body_status": _FIGHT_MOVEMENT_COMPLETED_STATUS,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "proposal_request_id": proposal_request.request_id,
        "proposal_kind": proposal.proposal_kind.value,
        "unit_instance_id": proposal.unit_instance_id,
        "transition_batch": validate_json_value(transition_batch.to_payload()),
        "resolution": validate_json_value(resolution.to_payload()),
        "target_authority_witness": target_authority_witness,
    }
    if isinstance(resolution, FightMovementResolution):
        completed_payload["movement_endpoint_placement"] = validate_json_value(
            resolution.attempted_placement.to_payload()
        )
    from warhammer40k_core.engine.move_completion_triggers import record_move_completion_event

    movement_event = record_move_completion_event(
        state=state,
        decisions=decisions,
        event_type="fight_movement_completed",
        payload=validate_json_value(completed_payload),
    )
    end_fight_move(state=state, decisions=decisions, request=record.request, result=result)
    from warhammer40k_core.engine.consolidation_fight_queue import start_consolidation_fight_queue

    start_consolidation_fight_queue(
        state=state,
        decisions=decisions,
        proposal=proposal,
        movement_event=movement_event,
    )
    return None
