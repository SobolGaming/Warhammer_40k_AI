# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.fight_phase_end_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    FightPhaseEndRequestContext,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartRequestContext,
)
from warhammer40k_core.engine.phase_start_sequencing import selected_request_is_current
from warhammer40k_core.engine.timing_request_candidates import selected_timing_request_is_current
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine import fight_activation_abilities as _fa
from warhammer40k_core.engine import fight_unit_selected_hooks as _fu
from warhammer40k_core.engine.catalog_post_fight_selected_target_runtime import (
    SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE,
    invalid_catalog_post_fight_hit_target_effect_status,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fight_order import FIGHT_ACTIVATION_DECISION_TYPE
from warhammer40k_core.engine.fight_phase_decisions import invalid_fight_phase_faction_rule_status
from warhammer40k_core.engine.fight_resolution import SUBMIT_MELEE_DECLARATION_DECISION_TYPE
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.fight import (
    invalid_fight_activation_ability_status,
    invalid_fight_activation_status,
    invalid_melee_declaration_status,
)


def pre_validate_fight_decision(
    lifecycle: GameLifecycle,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    state = lifecycle._require_state()
    if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
        result.validate_for_request(request)
        if lifecycle._result_resolves_active_reaction_frame(result):
            lifecycle.reaction_queue.validate_result(result)
        invalid_status = invalid_melee_declaration_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=lifecycle._require_config().ruleset_descriptor,
            army_catalog=lifecycle._require_config().army_catalog,
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == _fu.SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE:
        invalid_status = lifecycle._fight_phase_handler.invalid_fight_unit_selected_grant_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE:
        invalid_status = invalid_catalog_post_fight_hit_target_effect_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
    invalid_status = invalid_fight_phase_faction_rule_status(
        state=state,
        request=request,
        result=result,
    )
    if invalid_status is not None:
        return invalid_status
    if request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE:
        config = lifecycle._require_config()
        candidates = lifecycle._fight_phase_handler.fight_phase_start_hooks.candidates_for(
            FightPhaseStartRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
                runtime_modifier_registry=lifecycle._fight_phase_handler.runtime_modifier_registry,
            )
        )
        if not selected_request_is_current(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            candidates=candidates,
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Fight-start rule is no longer eligible.",
                payload={"invalid_reason": "fight_phase_start_source_drift"},
            )
    if request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE:
        candidates = lifecycle._fight_phase_handler.fight_phase_end_hooks.candidates_for(
            FightPhaseEndRequestContext(state=state, decisions=lifecycle.decision_controller)
        )
        if not selected_timing_request_is_current(
            decisions=lifecycle.decision_controller,
            context=boundary_context(state, TimingTriggerKind.END_PHASE),
            request=request,
            candidates=candidates,
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Fight-end rule is no longer eligible.",
                payload={"invalid_reason": "fight_phase_end_source_drift"},
            )
    if request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
        invalid_status = invalid_fight_activation_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=lifecycle._require_config().ruleset_descriptor,
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == _fa.FIGHT_ACTIVATION_ABILITY_DECISION_TYPE:
        invalid_status = invalid_fight_activation_ability_status(
            state=state,
            request=request,
            result=result,
            decisions=lifecycle.decision_controller,
        )
        if invalid_status is not None:
            return invalid_status
    return None
