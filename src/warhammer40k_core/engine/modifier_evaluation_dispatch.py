"""Before-pop validation and shared lifecycle continuation for modifier subsets."""

from __future__ import annotations

# The dispatch adapter owns access to the lifecycle's already-loaded authorities.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import CharacteristicError
from warhammer40k_core.engine.catalog_modifier_ignore import modifier_ignore_permissions_for_subject
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.modifier_evaluation import (
    SELECT_MODIFIER_IGNORES_DECISION_TYPE,
    ModifierEvaluationSubject,
    modifier_evaluation_options,
    permission_attack_context_from_source,
    selection_history,
)
from warhammer40k_core.engine.modifier_evaluation_history import validate_modifier_origin
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def modifier_evaluation_dispatch_handler(lifecycle: GameLifecycle) -> DecisionDispatchHandler:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        try:
            _validate(lifecycle, request, result)
        except (
            GameLifecycleError,
            DecisionError,
            CharacteristicError,
            ValueError,
            KeyError,
        ) as exc:
            return LifecycleStatus.invalid(
                stage=lifecycle._require_state().stage,
                message=str(exc),
                payload={"invalid_reason": "modifier_evaluation_context_drift"},
            )
        return None

    return DecisionDispatchHandler(
        decision_type=SELECT_MODIFIER_IGNORES_DECISION_TYPE,
        pre_validator=validate,
        applier=lambda record, _result: _resume(lifecycle, record.request),
    )


def _validate(lifecycle: GameLifecycle, request: DecisionRequest, result: DecisionResult) -> None:
    state = lifecycle._require_state()
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Modifier choice payload must be an object.")
    if request.options != modifier_evaluation_options(payload):
        raise GameLifecycleError("Modifier choice options drifted from source inventory.")
    result.validate_for_request(request)
    subject = ModifierEvaluationSubject.from_payload(payload["subject"])
    owner = rules_unit_view_by_id(state=state, unit_instance_id=subject.unit_instance_id)
    if owner.owner_player_id != request.actor_id:
        raise GameLifecycleError("Modifier choice actor differs from subject owner.")
    index = lifecycle._require_runtime_content_bundle().ability_indexes_by_player_id[
        owner.owner_player_id
    ]
    source_context = payload["source_context"]
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Modifier choice source context must be an object.")
    permissions = modifier_ignore_permissions_for_subject(
        state=state,
        ability_index=index,
        unit_instance_id=subject.unit_instance_id,
        kind=subject.kind,
        model_instance_id=subject.model_instance_id,
        weapon_profile_id=subject.weapon_profile_id,
        attack_context=permission_attack_context_from_source(source_context),
    )
    if payload["permissions"] != [permission.to_payload() for permission in permissions]:
        raise GameLifecycleError("Modifier evaluation source permission drifted.")
    previous = selection_history(
        decision_records=lifecycle.decision_controller.records,
        occurrence_id=str(payload["occurrence_id"]),
        subject=subject,
    )
    if previous is not None and previous != payload:
        raise GameLifecycleError("Modifier evaluation pending cursor drifted.")
    if previous is None and (payload["decided_modifier_ids"] or payload["ignored_modifier_ids"]):
        raise GameLifecycleError("Modifier evaluation initial cursor drifted.")
    validate_modifier_origin(lifecycle, lifecycle._modifier_evaluation_history_origin)


def _resume(lifecycle: GameLifecycle, request: DecisionRequest) -> LifecycleStatus:
    payload = request.payload
    if not isinstance(payload, dict) or not isinstance(payload["source_context"], dict):
        raise GameLifecycleError("Modifier continuation requires source context.")
    context = payload["source_context"]
    if context.get("continuation") == "mission_action":
        from warhammer40k_core.engine.mission_decisions import request_mission_action_start

        player_id = context["player_id"]
        action_id = context["mission_action_id"]
        if not isinstance(player_id, str) or not isinstance(action_id, str):
            raise GameLifecycleError("Mission-action modifier continuation identities drifted.")
        return request_mission_action_start(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            player_id=player_id,
            mission_action_id=action_id,
            runtime_modifier_registry=lifecycle._require_runtime_content_bundle().runtime_modifier_registry,
        )
    if context.get("continuation") == "movement_proposal":
        result_id = context["movement_proposal_result_id"]
        records = tuple(
            record
            for record in lifecycle.decision_controller.records
            if record.result.result_id == result_id
        )
        if len(records) != 1:
            raise GameLifecycleError("Desperate Escape requires its accepted movement proposal.")
        status = lifecycle._movement_phase_handler.apply_decision(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            result=records[0].result,
            reaction_queue=lifecycle.reaction_queue,
        )
        if status is not None:
            return status
    if context.get("continuation") == "battle_shock_modifiers":
        from warhammer40k_core.engine.battle_shock_modifier_continuation import (
            resume_battle_shock_modifier_choices,
        )

        bundle = lifecycle._require_runtime_content_bundle()
        status = resume_battle_shock_modifier_choices(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            context=context,
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
            battle_shock_hooks=bundle.battle_shock_hook_registry,
        )
        if status is not None:
            return status
        accepted = tuple(
            record
            for record in lifecycle.decision_controller.records
            if record.request.request_id == request.request_id
        )
        if len(accepted) != 1:
            raise GameLifecycleError("Completed modifier test lacks its accepted decision.")
        lifecycle._command_phase_handler.apply_command_phase_start_nested_result(
            state=lifecycle._require_state(),
            decisions=lifecycle.decision_controller,
            request=request,
            result=accepted[0].result,
        )
    return lifecycle.advance_until_decision_or_terminal()
