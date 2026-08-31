from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_leadership_target_for_rules_unit,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockHookRegistry,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockPassedStatePolicy,
    BattleShockResolutionResult,
    resolve_battle_shock_test_with_optional_reroll,
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
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_placed_alive_rules_unit_view_for_identity,
    current_rules_unit_views_for_identity,
)
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


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
    recorded_effects_before_battle_shock: tuple[dict[str, JsonValue], ...] = (),
    remaining_effect_records_after_battle_shock: tuple[dict[str, JsonValue], ...] = (),
    remaining_effect_start_index: int = 0,
    phase: BattlePhase,
    final_event_type: str,
) -> BattleShockResolutionResult:
    if len(target_unit_ids) != 1:
        raise GameLifecycleError("Catalog selected-target Battle-shock requires one target.")
    selected_target_unit_id = target_unit_ids[0]
    identity_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=selected_target_unit_id,
    )
    target_player_ids = {view.owner_player_id for view in identity_views}
    if len(target_player_ids) != 1:
        raise GameLifecycleError("Catalog selected-target Battle-shock owner identity drifted.")
    target_player_id = next(iter(target_player_ids))
    target_rules_unit = current_placed_alive_rules_unit_view_for_identity(
        state=state,
        unit_instance_id=selected_target_unit_id,
    )
    target_unit_id = (
        selected_target_unit_id if target_rules_unit is None else target_rules_unit.unit_instance_id
    )
    base_payload = _selected_target_battle_shock_base_payload(
        state=state,
        result=result,
        payload=payload,
        record=record,
        effect_payload=effect_payload,
        target_unit_id=target_unit_id,
        target_player_id=target_player_id,
        recorded_effects_before_battle_shock=recorded_effects_before_battle_shock,
        remaining_effect_records_after_battle_shock=remaining_effect_records_after_battle_shock,
        remaining_effect_start_index=remaining_effect_start_index,
        selected_target_request=decisions.record_for_result(result).request,
        phase=phase,
        final_event_type=final_event_type,
    )
    if target_rules_unit is None:
        skipped_payload = cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    **base_payload,
                    "battle_shock_result": None,
                    "skip_reason": "no_surviving_target_models",
                    "state_update": "not_required",
                    "target_identity_resolution": "no_surviving_rules_unit",
                }
            ),
        )
        decisions.event_log.append(
            "catalog_selected_target_battle_shock_skipped",
            skipped_payload,
        )
        return BattleShockResolutionResult(
            resolved_payload=skipped_payload,
            pending_status=None,
        )
    current_model_ids = tuple(
        sorted(
            model_id
            for component in target_rules_unit.components
            for model_id in catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=state,
                unit=component.unit,
            )
        )
    )
    if not current_model_ids:
        raise GameLifecycleError("Catalog selected-target survivor resolution drifted.")
    active_player_id = _active_player_id(state)
    phase_start_battle_shocked_unit_ids = tuple(state.battle_shocked_unit_ids)
    below_half_context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=target_rules_unit,
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
            phase=phase,
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
        leadership_target=battle_shock_leadership_target_for_rules_unit(
            target_rules_unit,
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
    return resolve_battle_shock_test_with_optional_reroll(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=battle_shock_hooks,
        request=request,
        roll_state=roll_state,
        active_player_id=active_player_id,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
        source_kind="catalog_selected_target_effect",
        base_payload=base_payload,
        resolved_event_types=(
            "battle_shock_test_resolved",
            "catalog_selected_target_battle_shock_resolved",
        ),
        pending_phase_body_status="catalog_selected_target_battle_shock_reroll_pending",
    )


def _selected_target_battle_shock_base_payload(
    *,
    state: GameState,
    result: DecisionResult,
    payload: Mapping[str, object],
    record: Mapping[str, object],
    effect_payload: Mapping[str, object],
    target_unit_id: str,
    target_player_id: str,
    recorded_effects_before_battle_shock: tuple[dict[str, JsonValue], ...],
    remaining_effect_records_after_battle_shock: tuple[dict[str, JsonValue], ...],
    remaining_effect_start_index: int,
    selected_target_request: DecisionRequest,
    phase: BattlePhase,
    final_event_type: str,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": phase.value,
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
                "target_identity_resolution": (
                    "unchanged"
                    if target_unit_id
                    == _payload_string(record, key="selected_target_unit_instance_id")
                    else "attached_unit_split_survivor"
                ),
                "target_player_id": target_player_id,
                "effect_payload": validate_json_value(effect_payload),
                "selected_target_decision_request": validate_json_value(
                    selected_target_request.to_payload()
                ),
                "selected_target_decision_result": validate_json_value(result.to_payload()),
                "selected_target_payload": validate_json_value(dict(payload)),
                "selected_target_final_event_type": final_event_type,
                "selected_target_recorded_effects_before_battle_shock": [
                    validate_json_value(recorded_effect)
                    for recorded_effect in recorded_effects_before_battle_shock
                ],
                "selected_target_remaining_effect_records_after_battle_shock": [
                    validate_json_value(remaining_record)
                    for remaining_record in remaining_effect_records_after_battle_shock
                ],
                "selected_target_remaining_effect_start_index": remaining_effect_start_index,
            }
        ),
    )


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
