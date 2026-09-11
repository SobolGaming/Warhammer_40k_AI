from __future__ import annotations

from warhammer40k_core.engine.catalog_command_restoration_runtime import (
    invalid_catalog_command_restoration_status,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.finite_decision_validation import invalid_finite_decision_status
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.command import (
    CommandPhaseHandler,
    invalid_command_phase_decision_status,
)


def invalid_command_phase_submission(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
    handler: CommandPhaseHandler,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_command_phase_decision_result",
    )
    if invalid_status is not None:
        return invalid_status
    context_invalid = invalid_command_phase_decision_status(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        battle_shock_hooks=handler.battle_shock_hooks,
    )
    if context_invalid is not None:
        return context_invalid
    if request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE:
        from warhammer40k_core.engine.command_phase_start_hooks import (
            CommandPhaseStartEffectContext,
        )
        from warhammer40k_core.engine.command_phase_start_selection import (
            invalid_selected_source_request,
        )

        if state.active_player_id is None:
            raise GameLifecycleError("Command-start choice requires an active player.")
        source_invalid = invalid_selected_source_request(
            context=CommandPhaseStartEffectContext(
                state=state,
                decisions=decisions,
                active_player_id=state.active_player_id,
                runtime_modifier_registry=handler.runtime_modifier_registry,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            ),
            registry=handler.command_phase_start_hooks,
            request=request,
        )
        if source_invalid is not None:
            return source_invalid
    restoration_invalid_status = invalid_catalog_command_restoration_status(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ability_indexes_by_player_id=(handler.ability_indexes_by_player_id),
    )
    if restoration_invalid_status is not None:
        return restoration_invalid_status
    return None
