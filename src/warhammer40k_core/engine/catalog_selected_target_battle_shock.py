from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_leadership_target_for_unit,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockHookRegistry,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    active_player_id as _active_player_id,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_int as _payload_int,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    payload_string as _payload_string,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.unit_factory import UnitInstance


def payload_optional_string(payload: Mapping[str, object], *, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog selected-target payload {key} must be a string.")
    return value


def resolve_selected_target_battle_shock_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: Mapping[str, object],
    record: Mapping[str, object],
    effect_payload: Mapping[str, object],
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    target_unit_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    if len(target_unit_ids) != 1:
        raise GameLifecycleError("Catalog selected-target Battle-shock requires one target.")
    target_unit_id = target_unit_ids[0]
    target_unit, target_player_id = _unit_and_player_id_by_id(
        state=state,
        unit_instance_id=target_unit_id,
    )
    current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
        state=state,
        unit=target_unit,
    )
    if not current_model_ids:
        raise GameLifecycleError("Catalog selected-target Battle-shock target is not placed.")
    active_player_id = _active_player_id(state)
    phase_start_battle_shocked_unit_ids = tuple(state.battle_shocked_unit_ids)
    below_half_context = BelowHalfStrengthContext.from_unit(
        player_id=target_player_id,
        unit=target_unit,
        starting_strength=state.starting_strength_record_for_unit(target_unit_id),
        current_model_ids=current_model_ids,
    )
    dice_expression = battle_shock_hooks.dice_expression_for(
        BattleShockDiceExpressionContext(
            state=state,
            player_id=target_player_id,
            unit_instance_id=target_unit_id,
            reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
            active_player_id=active_player_id,
            phase=BattlePhase.SHOOTING,
            default_expression=DiceExpression(quantity=2, sides=6),
            phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        )
    )
    request = BattleShockTestRequest.for_unit(
        request_id=(
            f"catalog-selected-target-battle-shock:{state.battle_round:02d}:"
            f"{result.result_id}:{target_unit_id}:{_payload_int(record, key='effect_index'):03d}"
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=target_player_id,
        unit_instance_id=target_unit_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=battle_shock_leadership_target_for_unit(
            target_unit,
            current_model_ids=current_model_ids,
            ability_index=_ability_index_for_player(
                ability_indexes_by_player_id,
                player_id=target_player_id,
            ),
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        below_half_strength_context=below_half_context,
        dice_expression=dice_expression,
    )
    base_payload = _selected_target_battle_shock_base_payload(
        state=state,
        payload=payload,
        record=record,
        effect_payload=effect_payload,
        target_unit_id=target_unit_id,
        target_player_id=target_player_id,
    )
    decisions.event_log.append(
        "battle_shock_test_requested",
        validate_json_value(
            {
                **base_payload,
                "battle_shock_test_request": request.to_payload(),
            }
        ),
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(request.spec)
    result_record = BattleShockResult.from_roll_state(
        result_id=f"{request.request_id}:result",
        request=request,
        roll_state=roll_state,
        modifiers=battle_shock_hooks.modifiers_for(
            BattleShockModifierContext(
                state=state,
                request=request,
                active_player_id=active_player_id,
                phase=BattlePhase.SHOOTING,
                phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
            )
        ),
    )
    state_update = "not_required"
    if not result_record.passed:
        if target_unit_id in phase_start_battle_shocked_unit_ids:
            state_update = "already_battle_shocked"
        else:
            state.record_battle_shock_result(result_record)
            state_update = "recorded_battle_shocked"
    result_payload = validate_json_value(result_record.to_payload())
    resolved_payload = validate_json_value(
        {
            **base_payload,
            "battle_shock_result": result_payload,
            "auto_passed": False,
            "state_update": state_update,
        }
    )
    decisions.event_log.append("battle_shock_test_resolved", resolved_payload)
    decisions.event_log.append("catalog_selected_target_battle_shock_resolved", resolved_payload)
    battle_shock_hooks.resolve_outcomes(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            result=result_record,
            active_player_id=active_player_id,
            phase=BattlePhase.SHOOTING,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        )
    )
    return cast(dict[str, JsonValue], resolved_payload)


def _selected_target_battle_shock_base_payload(
    *,
    state: GameState,
    payload: Mapping[str, object],
    record: Mapping[str, object],
    effect_payload: Mapping[str, object],
    target_unit_id: str,
    target_player_id: str,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.SHOOTING.value,
                "source_kind": "catalog_selected_target_effect",
                "hook_id": _payload_string(payload, key="hook_id"),
                "catalog_record_id": _payload_string(record, key="catalog_record_id"),
                "source_rule_id": _payload_string(record, key="source_rule_id"),
                "source_unit_instance_id": _payload_string(
                    record,
                    key="source_unit_instance_id",
                ),
                "selection_clause_id": _payload_string(record, key="selection_clause_id"),
                "effect_clause_id": _payload_string(record, key="effect_clause_id"),
                "effect_index": _payload_int(record, key="effect_index"),
                "selected_target_unit_instance_id": _payload_string(
                    record,
                    key="selected_target_unit_instance_id",
                ),
                "target_unit_instance_id": target_unit_id,
                "target_player_id": target_player_id,
                "effect_payload": validate_json_value(effect_payload),
            }
        ),
    )


def _unit_and_player_id_by_id(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[UnitInstance, str]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit, army.player_id
    raise GameLifecycleError("Catalog selected-target Battle-shock target unit is unknown.")


def _ability_index_for_player(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    *,
    player_id: str,
) -> AbilityCatalogIndex:
    requested_player_id = _validate_identifier("player_id", player_id)
    ability_index = ability_indexes_by_player_id.get(requested_player_id)
    if ability_index is None:
        raise GameLifecycleError(
            "Catalog selected-target Battle-shock missing target ability index."
        )
    return ability_index


_validate_identifier = IdentifierValidator(GameLifecycleError)
