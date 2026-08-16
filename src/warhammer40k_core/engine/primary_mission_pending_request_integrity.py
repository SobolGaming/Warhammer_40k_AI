from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_decisions import (
    START_MISSION_ACTION_DECISION_TYPE,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_mission_action_battlefield_evidence import (
    MissionActionBattlefieldBoundaryEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionStartAuthorityEvidence,
    MissionActionStartAuthorityOptionEvidence,
    canonical_json_object,
)
from warhammer40k_core.engine.primary_mission_action_request_authority import (
    validate_recomputed_primary_mission_action_direct_authority,
    validate_recomputed_primary_mission_action_opportunity_authority,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    primary_mission_boundary_checkpoint_for_request,
    validate_primary_mission_action_request_checkpoint,
    validate_primary_mission_boundary_checkpoint_modifier_sources,
)
from warhammer40k_core.engine.primary_mission_boundary_state import (
    primary_mission_action_boundary_state_from_checkpoint,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    CONSECRATE_CHOICE_KIND,
    LOCATE_AND_DENY_CHOICE_KIND,
    PUNISHMENT_CHOICE_KIND,
    SENSOR_SWEEP_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    invalid_primary_mission_choice_request_status,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.start_battle_hooks import is_start_battle_boundary

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex


_DECISION_REQUESTED_EVENT: Final = "decision_requested"
_DECISION_RECORDED_EVENT: Final = "decision_recorded"
_PRIMARY_MISSION_CHOICE_REQUESTED_EVENT: Final = "primary_mission_choice_requested"
_MISSION_ACTION_COMPLETED_EVENT: Final = "mission_action_completed"
_STEP4_PENDING_DECISION_TYPES: Final = frozenset(
    {
        START_MISSION_ACTION_DECISION_TYPE,
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    }
)


def validate_primary_mission_pending_request_integrity(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    """Authenticate every unresolved Phase 17N Step 4 decision request.

    A pending request is authoritative adapter state. Restoration therefore
    requires the exact engine-emitted request event, an unresolved queue head,
    the current lifecycle boundary, and a request regenerated through the same
    live option builders used for submission validation.
    """

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Pending Primary mission integrity requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Pending Primary mission integrity requires DecisionController.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Pending Primary mission integrity requires RuntimeModifierRegistry."
        )

    pending_requests = decisions.queue.pending_requests
    step4_requests = tuple(
        request
        for request in pending_requests
        if request.decision_type in _STEP4_PENDING_DECISION_TYPES
    )
    if not step4_requests:
        return
    if len(step4_requests) != 1 or pending_requests != step4_requests:
        raise GameLifecycleError(
            "Pending Step 4 request must be the sole authoritative queue head."
        )
    request = step4_requests[0]
    _validate_latest_request_identity(state=state, request=request)
    request_index = _exact_request_event_index(decisions=decisions, request=request)
    _reject_recorded_pending_request(decisions=decisions, request=request)

    if request.decision_type == START_MISSION_ACTION_DECISION_TYPE:
        _validate_action_request_suffix(
            event_records=decisions.event_log.records,
            request_index=request_index,
        )
        _validate_authoritative_action_request(
            state=state,
            decisions=decisions,
            request=request,
            runtime_modifier_registry=runtime_modifier_registry,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        return

    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    _validate_choice_lifecycle_boundary(
        state=state,
        choice=choice,
        request=request,
        event_records=decisions.event_log.records,
        request_index=request_index,
    )
    invalid = invalid_primary_mission_choice_request_status(
        state=state,
        decisions=decisions,
        request=request,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if invalid is not None:
        raise GameLifecycleError(
            "Pending Step 4 Primary choice request drifted from its authoritative inventory."
        )


def _validate_latest_request_identity(*, state: GameState, request: DecisionRequest) -> None:
    if state.decision_request_count < 1:
        raise GameLifecycleError("Pending Step 4 request lacks an issued request identity.")
    expected_request_id = f"decision-request-{state.decision_request_count:06d}"
    if request.request_id != expected_request_id:
        raise GameLifecycleError("Pending Step 4 request is not the current request identity.")


def _exact_request_event_index(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
) -> int:
    matching_id_rows: list[tuple[int, EventRecord]] = []
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type != _DECISION_REQUESTED_EVENT or not isinstance(event.payload, dict):
            continue
        if event.payload.get("request_id") == request.request_id:
            matching_id_rows.append((index, event))
    if len(matching_id_rows) != 1 or matching_id_rows[0][1].payload != request.to_payload():
        raise GameLifecycleError(
            "Pending Step 4 request requires one exact decision_requested event."
        )
    return matching_id_rows[0][0]


def _reject_recorded_pending_request(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
) -> None:
    if any(record.request.request_id == request.request_id for record in decisions.records):
        raise GameLifecycleError("Pending Step 4 request already has a DecisionRecord.")
    for event in decisions.event_log.records:
        if event.event_type != _DECISION_RECORDED_EVENT or not isinstance(event.payload, dict):
            continue
        recorded_request = event.payload.get("request")
        recorded_result = event.payload.get("result")
        if (
            isinstance(recorded_request, dict)
            and recorded_request.get("request_id") == request.request_id
        ) or (
            isinstance(recorded_result, dict)
            and recorded_result.get("request_id") == request.request_id
        ):
            raise GameLifecycleError("Pending Step 4 request already has a recorded result.")


def _validate_action_request_suffix(
    *,
    event_records: tuple[EventRecord, ...],
    request_index: int,
) -> None:
    if event_records[request_index + 1 :]:
        raise GameLifecycleError(
            "Pending Mission Action request has an impossible post-request event suffix."
        )


def _validate_authoritative_action_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None,
    runtime_content_activation: RuntimeContentActivation | None,
) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Pending Mission Action request requires battle state.")
    if request.actor_id is None or request.actor_id != state.active_player_id:
        raise GameLifecycleError("Pending Mission Action request actor drifted from the turn.")
    if type(request.payload) is not dict:
        raise GameLifecycleError("Pending Mission Action request payload must be an object.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.mission_action_opportunity_declined:
        raise GameLifecycleError(
            "Pending Mission Action request drifted from its authoritative inventory."
        )
    payload = request.payload
    checkpoint_reference, checkpoint, _checkpoint_index = (
        primary_mission_boundary_checkpoint_for_request(
            event_records=decisions.event_log.records,
            request_id=request.request_id,
        )
    )
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Pending Mission Action request requires a battle phase.")
    checkpoint = validate_primary_mission_action_request_checkpoint(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        request_id=request.request_id,
        reference=checkpoint_reference,
        player_id=request.actor_id,
        battle_round=state.battle_round,
        phase=current_phase.value,
        rule_ir_authority_index=rule_ir_authority_index,
        faction_rule_execution_registry=faction_rule_execution_registry,
        runtime_content_activation=runtime_content_activation,
    )
    validate_primary_mission_boundary_checkpoint_modifier_sources(
        state=state,
        checkpoint=checkpoint,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    boundary_state = primary_mission_action_boundary_state_from_checkpoint(
        state=state,
        checkpoint=checkpoint,
    )
    battlefield = boundary_state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Pending Mission Action request requires battlefield state.")
    opportunity = payload.get("mission_action_opportunity") is True
    authority = MissionActionStartAuthorityEvidence(
        request_kind="opportunity" if opportunity else "direct",
        request_payload_json=canonical_json_object(request.payload),
        battlefield_boundary=MissionActionBattlefieldBoundaryEvidence.from_battlefield_state(
            battlefield
        ),
        options=tuple(
            MissionActionStartAuthorityOptionEvidence(
                option_id=option.option_id,
                label=option.label,
                payload_json=canonical_json_object(option.payload),
            )
            for option in request.options
        ),
        candidate_units=(),
        terrain_model_inventory=(),
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
    )
    mission_action_id = payload.get("mission_action_id")
    if not opportunity and (type(mission_action_id) is not str or not mission_action_id.strip()):
        raise GameLifecycleError("Pending direct Mission Action request lacks mission_action_id.")
    try:
        if opportunity:
            validate_recomputed_primary_mission_action_opportunity_authority(
                state=boundary_state,
                player_id=request.actor_id,
                battle_round=state.battle_round,
                authority=authority,
            )
            validate_recomputed_primary_mission_action_opportunity_authority(
                state=state,
                player_id=request.actor_id,
                battle_round=state.battle_round,
                authority=authority,
                runtime_modifier_registry=runtime_modifier_registry,
            )
        else:
            validate_recomputed_primary_mission_action_direct_authority(
                state=boundary_state,
                player_id=request.actor_id,
                battle_round=state.battle_round,
                mission_action_id=cast(str, mission_action_id),
                authority=authority,
            )
            validate_recomputed_primary_mission_action_direct_authority(
                state=state,
                player_id=request.actor_id,
                battle_round=state.battle_round,
                mission_action_id=cast(str, mission_action_id),
                authority=authority,
                runtime_modifier_registry=runtime_modifier_registry,
            )
    except GameLifecycleError as exc:
        raise GameLifecycleError(
            "Pending Mission Action request drifted from its authoritative inventory."
        ) from exc


def _validate_choice_lifecycle_boundary(
    *,
    state: GameState,
    choice: PrimaryMissionChoiceData,
    request: DecisionRequest,
    event_records: tuple[EventRecord, ...],
    request_index: int,
) -> None:
    if choice.choice_kind == LOCATE_AND_DENY_CHOICE_KIND:
        if not is_start_battle_boundary(state):
            raise GameLifecycleError("Pending Locate and Deny request is outside start of battle.")
        if event_records[request_index + 1 :]:
            raise GameLifecycleError(
                "Pending Locate and Deny request has an impossible post-request event suffix."
            )
        return

    if choice.choice_kind == PUNISHMENT_CHOICE_KIND:
        if not (
            state.stage is GameLifecycleStage.BATTLE
            and state.current_battle_phase is BattlePhase.COMMAND
            and state.battle_phase_index == 0
            and state.active_player_id == request.actor_id
        ):
            raise GameLifecycleError("Pending Punishment request is outside turn start.")
    elif choice.choice_kind in {CONSECRATE_CHOICE_KIND, SENSOR_SWEEP_CHOICE_KIND}:
        if not (
            state.stage is GameLifecycleStage.BATTLE
            and state.battle_phase_index is not None
            and state.battle_phase_index + 1 == len(state.battle_phase_sequence)
            and state.active_player_id == request.actor_id
        ):
            raise GameLifecycleError("Pending turn-end Primary choice is outside turn end.")
        if choice.choice_kind == SENSOR_SWEEP_CHOICE_KIND:
            _validate_pending_sensor_completion_order(
                state=state,
                choice=choice,
                event_records=event_records,
                request_index=request_index,
            )
    else:
        raise GameLifecycleError("Pending Primary mission choice kind is unsupported.")

    expected_suffix_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": cast(BattlePhase, state.current_battle_phase).value,
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
    }
    suffix = event_records[request_index + 1 :]
    if (
        len(suffix) != 1
        or suffix[0].event_type != _PRIMARY_MISSION_CHOICE_REQUESTED_EVENT
        or suffix[0].payload != expected_suffix_payload
    ):
        raise GameLifecycleError(
            "Pending Primary mission choice has an impossible request event suffix."
        )


def _validate_pending_sensor_completion_order(
    *,
    state: GameState,
    choice: PrimaryMissionChoiceData,
    event_records: tuple[EventRecord, ...],
    request_index: int,
) -> None:
    if choice.source_action_id is None:
        raise GameLifecycleError("Pending Sensor Sweep choice lacks Action provenance.")
    actions = tuple(
        action
        for action in state.mission_action_states
        if action.action_id == choice.source_action_id
    )
    if len(actions) != 1 or type(actions[0]) is not MissionActionState:
        raise GameLifecycleError("Pending Sensor Sweep choice cites an unknown Action.")
    action = actions[0]
    completion_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == _MISSION_ACTION_COMPLETED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("mission_action_state") == action.to_payload()
    )
    if len(completion_indices) != 1 or completion_indices[0] >= request_index:
        raise GameLifecycleError(
            "Pending Sensor Sweep request lacks prior completed Action authority."
        )


__all__ = ("validate_primary_mission_pending_request_integrity",)
