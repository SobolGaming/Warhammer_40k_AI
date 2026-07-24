from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_identity_ids,
    rules_unit_is_battle_shocked,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

MISSION_ACTION_UNIT_OFF_BATTLEFIELD = "mission_action_unit_off_battlefield"
MISSION_ACTION_UNIT_WRONG_OWNER = "mission_action_unit_wrong_owner"
MISSION_ACTION_UNIT_AIRCRAFT = "mission_action_unit_aircraft"
MISSION_ACTION_UNIT_FORTIFICATION = "mission_action_unit_fortification"
MISSION_ACTION_UNIT_BATTLE_SHOCKED = "mission_action_unit_battle_shocked"
MISSION_ACTION_UNIT_ZERO_OBJECTIVE_CONTROL = "mission_action_unit_zero_objective_control"
MISSION_ACTION_UNIT_ENGAGED = "mission_action_unit_engaged"
MISSION_ACTION_UNIT_ADVANCED = "mission_action_unit_advanced"
MISSION_ACTION_UNIT_FELL_BACK = "mission_action_unit_fell_back"
MISSION_ACTION_UNIT_ALREADY_SHOT = "mission_action_unit_already_shot"
MISSION_ACTION_UNIT_ALREADY_STARTED_ACTION = "mission_action_unit_already_started_action"


def mission_action_unit_ineligibility_reason(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> str | None:
    _require_game_state(state, operation="eligibility")
    _require_runtime_modifier_registry(runtime_modifier_registry)
    requested_player_id = _validated_player_id(state=state, player_id=player_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != requested_player_id:
        return MISSION_ACTION_UNIT_WRONG_OWNER
    placed_alive_models = _placed_alive_models(state=state, rules_unit=rules_unit)
    if not placed_alive_models:
        return MISSION_ACTION_UNIT_OFF_BATTLEFIELD
    keyword_set = _rules_unit_keyword_set(rules_unit)
    if "AIRCRAFT" in keyword_set:
        return MISSION_ACTION_UNIT_AIRCRAFT
    if "FORTIFICATION" in keyword_set:
        return MISSION_ACTION_UNIT_FORTIFICATION
    state_unit_ids = _rules_unit_state_unit_ids(rules_unit)
    if rules_unit_is_battle_shocked(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    ):
        return MISSION_ACTION_UNIT_BATTLE_SHOCKED
    if not any(
        (
            characteristic := model_objective_control_characteristic(
                model,
                battle_shocked=False,
                state=state,
                unit_instance_id=component_unit_id,
                runtime_modifier_registry=runtime_modifier_registry,
                model_instance_id=model.model_instance_id,
            )
        ).is_numeric
        and characteristic.final > 0
        for component_unit_id, model in placed_alive_models
    ):
        return MISSION_ACTION_UNIT_ZERO_OBJECTIVE_CONTROL
    if "TITANIC" not in keyword_set and unit_within_enemy_engagement_range(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    ):
        return MISSION_ACTION_UNIT_ENGAGED
    if any(
        state.advanced_unit_state_for_unit(
            player_id=requested_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        is not None
        for unit_id in state_unit_ids
    ):
        return MISSION_ACTION_UNIT_ADVANCED
    if any(
        state.fell_back_unit_state_for_unit(
            player_id=requested_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        is not None
        for unit_id in state_unit_ids
    ):
        return MISSION_ACTION_UNIT_FELL_BACK
    if _rules_unit_has_shot_this_shooting_phase(
        state=state,
        state_unit_ids=state_unit_ids,
    ):
        return MISSION_ACTION_UNIT_ALREADY_SHOT
    if rules_unit_started_mission_action_this_turn(
        state=state,
        player_id=requested_player_id,
        unit_instance_id=rules_unit.unit_instance_id,
    ):
        return MISSION_ACTION_UNIT_ALREADY_STARTED_ACTION
    return None


def rules_unit_started_mission_action_this_turn(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    _require_game_state(state, operation="history")
    requested_player_id = _validated_player_id(state=state, player_id=player_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != requested_player_id:
        return False
    requested_identity_ids = frozenset(
        rules_unit_identity_ids(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
    )
    return any(
        action_state.player_id == requested_player_id
        and action_state.battle_round_started == state.battle_round
        and not requested_identity_ids.isdisjoint(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=action_state.unit_instance_id,
            )
        )
        for action_state in state.mission_action_states
    )


def mission_action_prevents_rules_unit_from_shooting_this_phase(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    _require_game_state(state, operation="shooting restriction")
    requested_player_id = _validated_player_id(state=state, player_id=player_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != requested_player_id:
        return False
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return False
    if "TITANIC" in _rules_unit_keyword_set(rules_unit):
        return False
    requested_identity_ids = frozenset(
        rules_unit_identity_ids(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
    )
    return any(
        action_state.player_id == requested_player_id
        and action_state.battle_round_started == state.battle_round
        and action_state.phase_started == BattlePhase.SHOOTING.value
        and not requested_identity_ids.isdisjoint(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=action_state.unit_instance_id,
            )
        )
        for action_state in state.mission_action_states
    )


def _placed_alive_models(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[tuple[str, ModelInstance], ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return ()
    placed_model_ids = frozenset(battlefield_state.placed_model_ids())
    return tuple(
        (component.unit.unit_instance_id, model)
        for component in rules_unit.components
        for model in component.unit.own_models
        if model.is_alive and model.model_instance_id in placed_model_ids
    )


def _rules_unit_state_unit_ids(rules_unit: RulesUnitView) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )


def _rules_unit_keyword_set(rules_unit: RulesUnitView) -> frozenset[str]:
    return frozenset(_canonical_keyword(keyword) for keyword in rules_unit.keywords)


def _rules_unit_has_shot_this_shooting_phase(
    *,
    state: GameState,
    state_unit_ids: tuple[str, ...],
) -> bool:
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return False
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return False
    return any(unit_id in shooting_state.shot_unit_ids for unit_id in state_unit_ids)


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).replace("-", " ").replace("_", " ").upper()


def _validated_player_id(*, state: GameState, player_id: str) -> str:
    requested_player_id = _validate_identifier("player_id", player_id)
    if requested_player_id not in state.player_ids:
        raise GameLifecycleError("Mission Action player is not in this game.")
    return requested_player_id


def _require_game_state(state: object, *, operation: str) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(f"Mission Action {operation} requires GameState.")


def _require_runtime_modifier_registry(registry: object) -> None:
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Mission Action eligibility requires a RuntimeModifierRegistry.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
