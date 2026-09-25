"""Authenticate historical shooting scopes against their accepted source choice."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState
from warhammer40k_core.engine.retained_attack_permissions import (
    RetainedAttackAction,
    retained_attack_selection,
)
from warhammer40k_core.engine.retained_destruction_selection import is_retention_request
from warhammer40k_core.engine.retained_shooting import RetainedShootingExecution
from warhammer40k_core.engine.stratagem_use_history_authority import validate_stratagem_use_history
from warhammer40k_core.engine.stratagems_model import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemUseRecord,
    StratagemUseRecordPayload,
)


def validate_shooting_scope_source(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting: OutOfPhaseShootingState,
    record: DecisionRecord,
    event_index: int,
    retained: tuple[RetainedShootingExecution, ...],
) -> None:
    if (
        record.result.result_id != shooting.source_decision_result_id
        or record.result.actor_id != shooting.player_id
        or shooting.attack_sequence is not None
        or shooting.pending_completed_attack_sequence is not None
    ):
        raise GameLifecycleError("Active-player shooting selection authority drift.")
    context = _object(shooting.source_context)
    if record.request.decision_type in (
        STRATAGEM_DECISION_TYPE,
        STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    ):
        use = StratagemUseRecord.from_payload(
            cast(StratagemUseRecordPayload, context["stratagem_use"])
        )
        authority = validate_stratagem_use_history(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            use_record=use,
            mutation_index=event_index,
        )
        from warhammer40k_core.engine.stratagems_shooting_history import (
            validate_stratagem_shooting_permission,
        )

        validate_stratagem_shooting_permission(
            shooting=shooting,
            authority=authority,
            preceding_events=decisions.event_log.records[
                authority.used_event_index + 1 : event_index
            ],
        )
        if (
            use.request_id != record.request.request_id
            or use.result_id != record.result.result_id
            or use.player_id != shooting.player_id
            or use.battle_round != shooting.battle_round
            or use.phase != shooting.parent_phase
            or shooting.source_rule_id not in (use.source_id, use.handler_id)
            or shooting.selected_unit_instance_id not in use.targeted_unit_instance_ids
            or not use.effects_resolved
        ):
            raise GameLifecycleError("Active-player shooting Stratagem source drift.")
    elif record.request.decision_type == "select_catalog_setup_reactive_shoot_charge":
        if (
            context != record.result.payload
            or context.get("action") != "shoot"
            or context.get("source_rule_id") != shooting.source_rule_id
            or context.get("source_unit_instance_id") != shooting.selected_unit_instance_id
            or shooting.target_unit_ids != (context.get("target_unit_instance_id"),)
        ):
            raise GameLifecycleError("Active-player setup shooting source drift.")
    elif is_retention_request(record.request):
        source, action = retained_attack_selection(request=record.request, result=record.result)
        destruction = _object(_object(record.request.payload)["destruction_context"])
        if not retained:
            raise GameLifecycleError("Active-player retained shooting lacks an executor.")
        execution = retained[-1]
        if (
            action is not RetainedAttackAction.SHOOT
            or source != execution.source_id
            or execution.source_rule_id != shooting.source_rule_id
            or execution.source_request_id != record.request.request_id
            or execution.source_result_id != record.result.result_id
            or destruction.get("cause_id") != context.get("cause_id")
            or execution.cause_id != context.get("cause_id")
            or destruction.get("model_instance_id") != context.get("model_instance_id")
            or destruction.get("target_unit_instance_id") != shooting.selected_unit_instance_id
            or destruction.get("destroyed_model_controller_player_id") != shooting.player_id
        ):
            raise GameLifecycleError("Active-player retained shooting source drift.")
    else:
        raise GameLifecycleError("Active-player shooting requires an accepted shooting source.")


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Active-player shooting source context requires an object.")
    return value
