from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from warhammer40k_core.engine import attack_sequence_decision_family as _asdf
from warhammer40k_core.engine import attack_sequence_hazardous as _ash
from warhammer40k_core.engine import battle_shock_lifecycle_authority as _bsa
from warhammer40k_core.engine import lifecycle_state_queries as _lsq
from warhammer40k_core.engine import mortal_wound_model_allocation as _mw_model
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.attack_sequence import (
    HAZARDOUS_SOURCE_KIND,
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
    SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    current_legal_damage_allocation_model_ids,
)
from warhammer40k_core.engine.attack_sequence_psychic_modifiers import DECISION_TYPE
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_reaction_decision_validation import (
    invalid_destruction_reaction_context_status,
)
from warhammer40k_core.engine.dice_result_overrides import (
    DICE_RESULT_OVERRIDE_DECISION_TYPE,
    invalid_dice_result_override_status,
)
from warhammer40k_core.engine.finite_decision_validation import (
    invalid_finite_decision_status as _invalid_finite_decision_status,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.fight import invalid_fight_attack_sequence_selection_status
from warhammer40k_core.engine.psychic_modifier_validation import invalid_psychic_modifier_status
from warhammer40k_core.engine.retained_destruction_selection import (
    invalid_retention_request_status,
    is_retention_request,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler


def pre_validate_attack_sequence_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_phase_handler: ShootingPhaseHandler,
    runtime_content_bundle: RuntimeContentBundle | None,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if is_retention_request(request):
        return invalid_retention_request_status(state=state, request=request, result=result)
    if request.decision_type == DECISION_TYPE:
        return invalid_psychic_modifier_status(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            runtime_modifier_registry=shooting_phase_handler.runtime_modifier_registry,
        )
    if request.decision_type == DICE_RESULT_OVERRIDE_DECISION_TYPE:
        return invalid_dice_result_override_status(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    if request.decision_type in (
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
    ):
        if fight_attack_sequence_is_active_for_request(
            state=state,
            request=request,
        ):
            invalid_status = invalid_fight_attack_sequence_selection_status(
                state=state,
                request=request,
                result=result,
            )
        else:
            invalid_status = shooting_phase_handler.invalid_attack_sequence_selection_status(
                state=state,
                request=request,
                result=result,
            )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        invalid_status = _invalid_damage_allocation_model_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == _mw_model.SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE:
        invalid_status = _mw_model.invalid_mortal_wound_model_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
    if (
        request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
        and _mw_model.is_mortal_wound_resolution_request(request)
    ):
        _bsa.validate_pre_submission_outcome_request(
            state=state,
            decisions=decisions,
            request=request,
            runtime_content_bundle=runtime_content_bundle,
        )
        invalid_status = _mw_model.invalid_mortal_wound_feel_no_pain_status(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
        progress = _mw_model.mortal_wound_resolution_progress(request)
        source_context = progress.source_context
        if (
            isinstance(source_context, dict)
            and source_context.get("source_kind") == HAZARDOUS_SOURCE_KIND
        ):
            attack_sequence = _lsq.active_attack_sequence_for_state(state)
            if attack_sequence is None:
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message=("Pending Hazardous mortal wounds require an active attack sequence."),
                    payload={
                        "invalid_reason": "hazardous_authority_drift",
                        "field": "mortal_wound_context",
                    },
                )
            try:
                _ash.validate_hazardous_mortal_wound_source_context(
                    state=state,
                    attack_sequence=attack_sequence,
                    source_context_payload=progress.source_context,
                    mortal_wounds=progress.mortal_wounds,
                )
            except GameLifecycleError as exc:
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message=str(exc),
                    payload={
                        "invalid_reason": "hazardous_authority_drift",
                        "field": "mortal_wound_context",
                    },
                )
        if rule_model_destruction.is_rule_model_destruction_mortal_wound_request(request):
            invalid_status = (
                rule_model_destruction.invalid_rule_model_destruction_mortal_wound_status(
                    state=state,
                    request=request,
                    result=result,
                )
            )
            if invalid_status is not None:
                return invalid_status
    if request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
        invalid_status = _invalid_destruction_reaction_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
    return None


def fight_attack_sequence_is_active_for_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> bool:
    if request.decision_type not in _asdf.ATTACK_SEQUENCE_DECISION_TYPES:
        return False
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.attack_sequence is None:
        return False
    if _mw_model.is_mortal_wound_resolution_request(request):
        source_context = _mw_model.mortal_wound_resolution_source_context(request)
        return (
            isinstance(source_context, dict)
            and source_context.get("sequence_id") == fight_state.attack_sequence.sequence_id
        )
    if request.decision_type in _asdf.ATTACK_SEQUENCE_ACTIVE_CONTINUATION_DECISION_TYPES:
        return True
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    if request.decision_type == SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
        return payload.get("source_phase") == BattlePhase.FIGHT.value
    if request.decision_type == DICE_RESULT_OVERRIDE_DECISION_TYPE:
        return (
            payload.get("source_phase") == BattlePhase.FIGHT.value
            and payload.get("sequence_id") == fight_state.attack_sequence.sequence_id
        )
    if request.decision_type not in _asdf.ATTACK_SEQUENCE_CONTEXT_BOUND_DECISION_TYPES:
        return False
    sequence_id = payload.get("sequence_id")
    return type(sequence_id) is str and sequence_id == fight_state.attack_sequence.sequence_id


def _invalid_damage_allocation_model_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_damage_allocation_model_result",
    )
    if invalid_status is not None:
        return invalid_status
    request_payload = request.payload
    if not isinstance(request_payload, Mapping):
        raise GameLifecycleError("Damage allocation model request payload must be an object.")
    attack_context = request_payload.get("attack_context")
    if not isinstance(attack_context, Mapping):
        raise GameLifecycleError("Damage allocation model attack context must be an object.")
    attack_sequence = _lsq.active_attack_sequence_for_state(state)
    if attack_sequence is None or attack_sequence.pending_grouped_damage is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model has no pending grouped damage.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "pending_grouped_damage",
            },
        )
    pending = attack_sequence.pending_grouped_damage
    if pending.next_index >= len(pending.sorted_save_dice):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model pending die is exhausted.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "next_index",
            },
        )
    current_context = pending.sorted_save_dice[pending.next_index]["attack_context"]
    expected_fields: tuple[tuple[str, object], ...] = (
        ("sequence_id", attack_sequence.sequence_id),
        ("attack_context_id", current_context["attack_context_id"]),
        ("pool_index", attack_sequence.pool_index),
        ("attack_index", current_context["attack_index"]),
        ("generated_hit_index", current_context["generated_hit_index"]),
    )
    for field_name, expected_value in expected_fields:
        if attack_context.get(field_name) != expected_value:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Damage allocation model attack context no longer matches state.",
                payload={
                    "invalid_reason": "invalid_damage_allocation_model_result",
                    "field": field_name,
                },
            )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if not isinstance(selected_payload, Mapping):
        raise GameLifecycleError("Damage allocation model option payload must be an object.")
    selected_model_id = selected_payload.get("selected_model_id")
    if selected_model_id != result.selected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model selected model does not match the option.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "selected_model_id",
            },
        )
    legal_model_ids = current_legal_damage_allocation_model_ids(
        state=state,
        attack_sequence=attack_sequence,
    )
    if legal_model_ids is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model has no current allocation group.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "allocation_group",
            },
        )
    if selected_model_id not in legal_model_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Damage allocation model selected model is no longer legal.",
            payload={
                "invalid_reason": "invalid_damage_allocation_model_result",
                "field": "selected_model_id",
            },
        )
    return None


def _invalid_destruction_reaction_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_destruction_reaction_result",
    )
    if invalid_status is not None:
        return invalid_status
    return invalid_destruction_reaction_context_status(
        state=state,
        request=request,
        result=result,
        attack_sequence=_lsq.active_attack_sequence_for_state(state),
    )
