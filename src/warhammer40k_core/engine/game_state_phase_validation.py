from __future__ import annotations

from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
    PendingCatalogSelectedTargetBattleShockContinuation,
)
from warhammer40k_core.engine.fight_order import FightPhaseState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.charge import ChargePhaseState
from warhammer40k_core.engine.phases.movement_state import MovementPhaseState
from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState


def validate_optional_movement_phase_state(value: object | None) -> MovementPhaseState | None:
    if value is None:
        return None
    if type(value) is not MovementPhaseState:
        raise GameLifecycleError("GameState movement_phase_state must be a MovementPhaseState.")
    return value


def validate_optional_catalog_selected_target_battle_shock_continuation(
    value: object | None,
) -> PendingCatalogSelectedTargetBattleShockContinuation | None:
    if value is None:
        return None
    if type(value) is not PendingCatalogSelectedTargetBattleShockContinuation:
        raise GameLifecycleError(
            "GameState catalog selected-target Battle-shock continuation is invalid."
        )
    return value


def validate_optional_charge_phase_state(value: object | None) -> ChargePhaseState | None:
    if value is None:
        return None
    if type(value) is not ChargePhaseState:
        raise GameLifecycleError("GameState charge_phase_state must be a ChargePhaseState.")
    return value


def validate_optional_fight_phase_state(value: object | None) -> FightPhaseState | None:
    if value is None:
        return None
    if type(value) is not FightPhaseState:
        raise GameLifecycleError("GameState fight_phase_state must be a FightPhaseState.")
    return value


def validate_optional_shooting_phase_state(value: object | None) -> ShootingPhaseState | None:
    if value is None:
        return None
    if type(value) is not ShootingPhaseState:
        raise GameLifecycleError("GameState shooting_phase_state must be a ShootingPhaseState.")
    return value


__all__ = (
    "validate_optional_catalog_selected_target_battle_shock_continuation",
    "validate_optional_charge_phase_state",
    "validate_optional_fight_phase_state",
    "validate_optional_movement_phase_state",
    "validate_optional_shooting_phase_state",
)
