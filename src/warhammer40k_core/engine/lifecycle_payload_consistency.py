from __future__ import annotations

from warhammer40k_core.engine.army_muster_consistency import (
    validate_mustered_army_consistency,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    DeploymentPlacementRequest,
    is_deployment_placement_request,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.prebattle import (
    PreBattleProposalRequest,
    is_prebattle_proposal_request,
)


def validate_config_state_payload_consistency(
    *,
    state: GameState,
    config: GameConfig | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if config is None:
        return
    if state.game_id != config.game_id:
        raise GameLifecycleError("Lifecycle state game_id does not match config.")
    if state.player_ids != config.player_ids:
        raise GameLifecycleError("Lifecycle state player_ids do not match config.")
    if state.turn_order != config.turn_order:
        raise GameLifecycleError("Lifecycle state turn_order does not match config.")
    if state.tactical_secondary_draw_count != config.tactical_secondary_draw_count:
        raise GameLifecycleError(
            "Lifecycle state tactical secondary draw count does not match config."
        )
    expected_hash = config.ruleset_descriptor.descriptor_hash
    if state.ruleset_descriptor_hash != expected_hash:
        raise GameLifecycleError("Lifecycle state ruleset hash does not match config.")
    if state.rules_overlay_ids != config.ruleset_descriptor.rules_overlay_ids:
        raise GameLifecycleError("Lifecycle state rules overlays do not match config.")
    source_linked_setup_requires_config = state.mission_setup is not None and bool(
        state.mission_setup.objective_terrain_areas
    )
    if (
        config.mission_setup is not None or source_linked_setup_requires_config
    ) and state.mission_setup != config.mission_setup:
        raise GameLifecycleError("Lifecycle state mission_setup does not match config.")
    expected_setup = tuple(config.ruleset_descriptor.setup_sequence.steps)
    if state.setup_sequence != expected_setup:
        raise GameLifecycleError("Lifecycle state setup sequence does not match config.")
    expected_battle = tuple(config.ruleset_descriptor.battle_phase_sequence.phases)
    if state.battle_phase_sequence != expected_battle:
        raise GameLifecycleError("Lifecycle state battle phase sequence does not match config.")
    validate_mustered_army_consistency(
        state=state,
        catalog=config.army_catalog,
        muster_requests=config.army_muster_requests,
        model_geometries=config.model_geometries,
        event_records=event_records,
        decision_records=decision_records,
    )


def validate_pending_battlefield_request_consistency(
    *,
    state: GameState,
    pending_request: DecisionRequest | None,
) -> None:
    if pending_request is None:
        return
    if is_deployment_placement_request(pending_request):
        request_context: DeploymentPlacementRequest | PreBattleProposalRequest = (
            DeploymentPlacementRequest.from_decision_request_payload(pending_request.payload)
        )
        context_decision_type = SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
        context_setup_step = SetupStep.DEPLOY_ARMIES
    elif is_prebattle_proposal_request(pending_request):
        request_context = PreBattleProposalRequest.from_decision_request_payload(
            pending_request.payload
        )
        context_decision_type = request_context.decision_type
        context_setup_step = request_context.setup_step
    else:
        return
    if (
        pending_request.request_id != request_context.request_id
        or pending_request.decision_type != context_decision_type
        or pending_request.actor_id != request_context.actor_id
        or request_context.game_id != state.game_id
        or request_context.ruleset_descriptor_hash != state.ruleset_descriptor_hash
        or context_setup_step is not state.current_setup_step
    ):
        raise GameLifecycleError(
            "Lifecycle pending battlefield request identity drifted from state."
        )
    if state.mission_setup is None or request_context.mission_setup != state.mission_setup:
        raise GameLifecycleError(
            "Lifecycle pending battlefield request mission_setup drifted from state."
        )
    expected_deployment_zones = tuple(
        zone
        for zone in state.mission_setup.deployment_zones
        if zone.player_id == request_context.player_id
    )
    if request_context.deployment_zones != expected_deployment_zones:
        raise GameLifecycleError(
            "Lifecycle pending battlefield request deployment zones drifted from state."
        )
