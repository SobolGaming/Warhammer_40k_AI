from __future__ import annotations

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleStage, SetupStep


def state_requires_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    create_step_index = _setup_step_index_or_none(state, SetupStep.CREATE_BATTLEFIELD)
    if create_step_index is None:
        return False
    return state.setup_step_index > create_step_index


def state_requires_deployed_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    deploy_step_index = _setup_step_index_or_none(state, SetupStep.DEPLOY_ARMIES)
    if deploy_step_index is None:
        return False
    return state.setup_step_index > deploy_step_index


def state_allows_battlefield_state(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    create_step_index = _setup_step_index_or_none(state, SetupStep.CREATE_BATTLEFIELD)
    if create_step_index is None:
        return False
    return state.setup_step_index >= create_step_index


def state_is_before_deploy_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return False
    if state.setup_step_index is None:
        return False
    deploy_step_index = _setup_step_index_or_none(state, SetupStep.DEPLOY_ARMIES)
    if deploy_step_index is None:
        return False
    return state.setup_step_index < deploy_step_index


def _setup_step_index_or_none(state: GameState, step: SetupStep) -> int | None:
    for index, candidate in enumerate(state.setup_sequence):
        if candidate is step:
            return index
    return None


__all__ = (
    "state_allows_battlefield_state",
    "state_is_before_deploy_armies",
    "state_requires_battlefield_state",
    "state_requires_deployed_battlefield_state",
)
