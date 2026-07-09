from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import apply_mortal_wounds_to_unit
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.stratagems_generic_metadata import (
    generic_rule_ir_execution_target_unit_ids,
    unit_by_id,
    unit_has_keyword,
)
from warhammer40k_core.engine.stratagems_model import (
    ENGAGED_ENEMY_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    HIT_ENEMY_UNIT_CONTEXT_KEY,
    HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemEligibilityContext,
    StratagemUseRecord,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.geometry.pose import Pose

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.healing import HealingEffect

GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND = "generic_rule_ir_charge_roll_modifier"

_validate_identifier = IdentifierValidator(GameLifecycleError)


def resolve_generic_rule_ir_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> None:
    resolution_kind = _optional_rule_effect_string_parameter(effect_payload, "resolution_kind")
    if resolution_kind is None:
        _resolve_generic_roll_pool_mortal_wounds(
            state=state,
            decisions=decisions,
            context=context,
            use_record=use_record,
            effect_payload=effect_payload,
        )
        return
    if resolution_kind != "roll_per_engaged_enemy_unit":
        raise GameLifecycleError("Generic mortal-wound resolution kind is unsupported.")
    _resolve_generic_roll_per_context_target_mortal_wounds(
        state=state,
        decisions=decisions,
        context=context,
        use_record=use_record,
        effect_payload=effect_payload,
    )


def record_generic_rule_ir_charge_roll_modifier(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result_payload: JsonValue,
    effect_payload: dict[str, JsonValue],
    expiration: EffectExpiration,
) -> None:
    if _required_rule_effect_string_parameter(effect_payload, "roll_type") != "charge":
        raise GameLifecycleError("Generic charge modifier requires charge roll_type.")
    target_unit_id = _trigger_payload_identifier(
        context,
        key=_required_rule_effect_string_parameter(effect_payload, "target_unit_context_key"),
    )
    source_rule_id = _rule_effect_source_id(effect_payload)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:charge-roll-modifier:{target_unit_id}",
        source_rule_id=source_rule_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=expiration,
        effect_payload={
            "effect_kind": GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND,
            "source_rule_id": source_rule_id,
            "stratagem_id": use_record.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "target_unit_instance_id": target_unit_id,
            "roll_type": "charge",
            "delta": _required_rule_effect_int_parameter(effect_payload, "delta"),
            "generic_rule_execution_result": rule_result_payload,
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_charge_roll_modifier_registered",
        _event_payload(state=state, context=context, use_record=use_record, effect=effect),
    )


def resolve_generic_rule_ir_context_battle_shock(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> None:
    required_source_keyword = _optional_rule_effect_string_parameter(
        effect_payload,
        "required_source_keyword",
    )
    if required_source_keyword is not None:
        source_unit_id = _single_execution_target_unit_id(use_record)
        if not unit_has_keyword(
            unit_by_id(state=state, unit_instance_id=source_unit_id),
            required_source_keyword,
        ):
            return
    target_unit_id = _trigger_payload_identifier(
        context,
        key=_required_rule_effect_string_parameter(effect_payload, "target_unit_context_key"),
    )
    _resolve_battle_shock_test(
        state=state,
        decisions=decisions,
        context=context,
        use_record=use_record,
        effect_payload=effect_payload,
        target_unit_id=target_unit_id,
    )


def apply_generic_rule_ir_reserve_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> None:
    if _required_rule_effect_string_parameter(effect_payload, "placement_kind") != (
        "strategic_reserves"
    ):
        raise GameLifecycleError("Generic reserve removal requires Strategic Reserves.")
    if _required_rule_effect_string_parameter(effect_payload, "operation") != "remove_to_reserves":
        raise GameLifecycleError("Generic reserve removal requires remove_to_reserves.")
    if _required_rule_effect_string_parameter(effect_payload, "reserve_origin") != (
        ReserveOrigin.DURING_BATTLE_STRATAGEM.value
    ):
        raise GameLifecycleError("Generic reserve removal requires Stratagem origin.")
    source_rule_id = _rule_effect_source_id(effect_payload)
    reserve_payloads: list[JsonValue] = []
    for unit_id in generic_rule_ir_execution_target_unit_ids(use_record):
        reserve_state = state.reposition_unit_to_strategic_reserves(
            player_id=use_record.player_id,
            unit_instance_id=unit_id,
            reserve_origin=ReserveOrigin.DURING_BATTLE_STRATAGEM,
            source_rule_ids=(source_rule_id,),
        )
        reserve_payloads.append(validate_json_value(reserve_state.to_payload()))
    decisions.event_log.append(
        "generic_stratagem_reserve_removal_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "active_player_id": context.active_player_id,
            "stratagem_use": validate_json_value(use_record.to_payload()),
            "reserve_states": reserve_payloads,
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )


def resolve_generic_rule_ir_restore_lost_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result_payload: JsonValue,
    effect_payload: dict[str, JsonValue],
) -> None:
    target_unit_id = _single_execution_target_unit_id(use_record)
    amount = _required_rule_effect_int_parameter(effect_payload, "amount")
    if amount <= 0:
        raise GameLifecycleError("Generic wound restoration amount must be positive.")
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked

    healing_effect = _healing_effect(
        state=state,
        use_record=use_record,
        effect_payload=effect_payload,
        effect_id=f"{use_record.use_id}:restore-lost-wounds:{target_unit_id}",
        target_unit_id=target_unit_id,
        amount=amount,
        source_context={
            "source_kind": "generic_rule_ir_stratagem",
            "stratagem_use": validate_json_value(use_record.to_payload()),
            "generic_rule_execution_result": rule_result_payload,
            "generic_rule_effect": validate_json_value(effect_payload),
            "single_model_heal": True,
            "heal_wounded_models_only": True,
        },
    )
    resolved, pending = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        effect=healing_effect,
    )
    _emit_healing_runtime_event(
        decisions=decisions,
        event_type="generic_stratagem_restore_lost_wounds_resolved",
        context=context,
        use_record=use_record,
        healing_effect=resolved,
        pending_request_id=None if pending is None else pending.request_id,
    )


def resolve_generic_rule_ir_return_destroyed_target(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result_payload: JsonValue,
    effect_payload: dict[str, JsonValue],
) -> None:
    target_unit_id = _single_execution_target_unit_id(use_record)
    target_unit = unit_by_id(state=state, unit_instance_id=target_unit_id)
    if not _unit_has_required_keyword_sequence(target_unit, effect_payload=effect_payload):
        return
    excluded_keyword = _optional_rule_effect_string_parameter(effect_payload, "excluded_keyword")
    if excluded_keyword is not None and unit_has_keyword(target_unit, excluded_keyword):
        return
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked

    healing_effect = _healing_effect(
        state=state,
        use_record=use_record,
        effect_payload=effect_payload,
        effect_id=f"{use_record.use_id}:return-destroyed-target:{target_unit_id}",
        target_unit_id=target_unit_id,
        amount=1,
        source_context={
            "source_kind": "generic_rule_ir_stratagem",
            "stratagem_use": validate_json_value(use_record.to_payload()),
            "generic_rule_execution_result": rule_result_payload,
            "generic_rule_effect": validate_json_value(effect_payload),
            "revive_destroyed_models_only": True,
            "revive_model_full_health": _required_rule_effect_string_parameter(
                effect_payload,
                "restore_wounds_mode",
            )
            == "full_health",
        },
    )
    resolved, pending = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        effect=healing_effect,
    )
    _emit_healing_runtime_event(
        decisions=decisions,
        event_type="generic_stratagem_return_destroyed_target_resolved",
        context=context,
        use_record=use_record,
        healing_effect=resolved,
        pending_request_id=None if pending is None else pending.request_id,
    )


def charge_roll_modifiers_from_generic_rule_ir(
    *,
    state: GameState,
    unit_instance_id: str,
    current_roll_modifiers: tuple[RollModifier, ...],
) -> tuple[RollModifier, ...]:
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    modifiers = list(current_roll_modifiers)
    for effect in state.persisting_effects_for_unit(unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND:
            continue
        if unit_id not in effect.target_unit_instance_ids:
            raise GameLifecycleError("Generic charge modifier target drift.")
        if payload.get("roll_type") != "charge":
            raise GameLifecycleError("Generic charge modifier roll_type drift.")
        delta = payload.get("delta")
        if type(delta) is not int:
            raise GameLifecycleError("Generic charge modifier delta must be an int.")
        source_id = payload.get("source_rule_id")
        if type(source_id) is not str:
            raise GameLifecycleError("Generic charge modifier source_rule_id is missing.")
        modifiers.append(
            RollModifier(
                modifier_id=effect.effect_id,
                source_id=_validate_identifier("source_rule_id", source_id),
                operand=delta,
            )
        )
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))


def _resolve_generic_roll_pool_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> None:
    required_keyword = _optional_rule_effect_string_parameter(
        effect_payload,
        "required_target_keyword",
    )
    if required_keyword is not None:
        unit_id = _single_execution_target_unit_id(use_record)
        unit = unit_by_id(state=state, unit_instance_id=unit_id)
        if not unit_has_keyword(unit, required_keyword):
            return
    target_unit_id = _effect_selection_unit_id(
        use_record,
        expected_selection_kind=_required_rule_effect_string_parameter(
            effect_payload,
            "effect_selection_kind",
        ),
    )
    quantity = _required_rule_effect_int_parameter(effect_payload, "roll_quantity")
    sides = _required_rule_effect_int_parameter(effect_payload, "roll_sides")
    threshold = _required_rule_effect_int_parameter(effect_payload, "success_threshold")
    wounds_per_success = _required_rule_effect_int_parameter(
        effect_payload,
        "mortal_wounds_per_success",
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    rolls = tuple(
        manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=sides),
                reason=f"{use_record.stratagem_id} mortal wound roll {index} for {target_unit_id}",
                roll_type=_required_rule_effect_string_parameter(effect_payload, "roll_type"),
                actor_id=use_record.player_id,
            )
        )
        for index in range(1, quantity + 1)
    )
    mortal_wounds = sum(wounds_per_success for roll in rolls if roll.current_total >= threshold)
    application_payload: JsonValue = None
    if mortal_wounds:
        application = apply_mortal_wounds_to_unit(
            state=state,
            target_unit_instance_id=target_unit_id,
            mortal_wounds=mortal_wounds,
            spill_over=_required_rule_effect_bool_parameter(effect_payload, "spill_over"),
            dice_manager=manager,
            defender_player_id=_unit_owner_player_id(state=state, unit_instance_id=target_unit_id),
        )
        application_payload = validate_json_value(application.to_payload())
    decisions.event_log.append(
        "generic_stratagem_roll_pool_mortal_wounds_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "effect_kind": _required_rule_effect_string_parameter(
                effect_payload,
                "replay_effect_kind",
            ),
            "target_unit_instance_id": target_unit_id,
            "rolls": [roll.to_payload() for roll in rolls],
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": application_payload,
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )


def _resolve_generic_roll_per_context_target_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> None:
    target_unit_ids = _trigger_payload_identifier_list(
        context,
        key=_required_rule_effect_string_parameter(effect_payload, "target_unit_context_key"),
    )
    source_unit = unit_by_id(
        state=state,
        unit_instance_id=_single_execution_target_unit_id(use_record),
    )
    bonus = _source_keyword_bonus(source_unit=source_unit, effect_payload=effect_payload)
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    target_results: list[JsonValue] = []
    for target_unit_id in target_unit_ids:
        roll = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(
                    quantity=_required_rule_effect_int_parameter(effect_payload, "roll_quantity"),
                    sides=_required_rule_effect_int_parameter(effect_payload, "roll_sides"),
                    modifier=bonus,
                ),
                reason=f"{use_record.stratagem_id} mortal wound roll for {target_unit_id}",
                roll_type=_required_rule_effect_string_parameter(effect_payload, "roll_type"),
                actor_id=use_record.player_id,
            )
        )
        mortal_wounds = _context_target_mortal_wounds(
            manager=manager,
            use_record=use_record,
            target_unit_id=target_unit_id,
            modified_total=roll.current_total,
            effect_payload=effect_payload,
        )
        application_payload: JsonValue = None
        if mortal_wounds:
            application = apply_mortal_wounds_to_unit(
                state=state,
                target_unit_instance_id=target_unit_id,
                mortal_wounds=mortal_wounds,
                spill_over=_required_rule_effect_bool_parameter(effect_payload, "spill_over"),
                dice_manager=manager,
                defender_player_id=_unit_owner_player_id(
                    state=state,
                    unit_instance_id=target_unit_id,
                ),
            )
            application_payload = validate_json_value(application.to_payload())
        target_results.append(
            {
                "target_unit_instance_id": target_unit_id,
                "roll": validate_json_value(roll.to_payload()),
                "mortal_wounds": mortal_wounds,
                "mortal_wound_application": application_payload,
            }
        )
    decisions.event_log.append(
        "generic_stratagem_roll_per_target_mortal_wounds_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": validate_json_value(use_record.to_payload()),
            "effect_kind": _required_rule_effect_string_parameter(
                effect_payload,
                "replay_effect_kind",
            ),
            "target_results": target_results,
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )


def _context_target_mortal_wounds(
    *,
    manager: DiceRollManager,
    use_record: StratagemUseRecord,
    target_unit_id: str,
    modified_total: int,
    effect_payload: dict[str, JsonValue],
) -> int:
    if 4 <= modified_total <= 5:
        value = _rule_effect_parameter(effect_payload, "mortal_wounds_on_4_5")
        if value != "D3":
            raise GameLifecycleError("Generic mortal wounds 4-5 value is unsupported.")
        return manager.roll_d3(
            reason=f"{use_record.stratagem_id} mortal wounds for {target_unit_id}",
            roll_type=f"{_required_rule_effect_string_parameter(effect_payload, 'roll_type')}_d3",
            actor_id=use_record.player_id,
        ).value
    if modified_total >= 6:
        return _required_rule_effect_int_parameter(effect_payload, "mortal_wounds_on_6_plus")
    return 0


def _resolve_battle_shock_test(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
    target_unit_id: str,
) -> None:
    target_owner = _unit_owner_player_id(state=state, unit_instance_id=target_unit_id)
    target_unit = unit_by_id(state=state, unit_instance_id=target_unit_id)
    current_model_ids = _current_battlefield_model_ids(state=state, unit=target_unit)
    request = BattleShockTestRequest.for_unit(
        request_id=f"{use_record.use_id}:battle-shock:{target_unit_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=target_owner,
        unit_instance_id=target_unit_id,
        reason=BattleShockTestReason.FORCED_BY_STRATAGEM,
        leadership_target=_best_current_model_characteristic(
            target_unit,
            current_model_ids=current_model_ids,
            characteristic=Characteristic.LEADERSHIP,
        ),
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id=target_owner,
            unit=target_unit,
            starting_strength=state.starting_strength_record_for_unit(target_unit_id),
            current_model_ids=current_model_ids,
        ),
    )
    decisions.event_log.append(
        "battle_shock_test_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": use_record.phase.value,
            "battle_shock_test_request": validate_json_value(request.to_payload()),
            "source_stratagem_use": use_record.to_payload(),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(request.spec)
    result = BattleShockResult.from_roll_state(
        result_id=f"{request.request_id}:result",
        request=request,
        roll_state=roll_state,
        modifiers=(),
    )
    state.record_battle_shock_result(result)
    decisions.event_log.append(
        "battle_shock_test_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": use_record.phase.value,
            "battle_shock_result": validate_json_value(result.to_payload()),
            "auto_passed": False,
            "source_stratagem_use": use_record.to_payload(),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )


def _healing_effect(
    *,
    state: GameState,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
    effect_id: str,
    target_unit_id: str,
    amount: int,
    source_context: dict[str, JsonValue],
) -> HealingEffect:
    from warhammer40k_core.engine.healing import HealingEffect

    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    return HealingEffect(
        effect_id=effect_id,
        target_unit_instance_id=target_unit_id,
        amount=amount,
        opposing_player_id=_opposing_player_id(state=state, player_id=use_record.player_id),
        selection_actor_player_id=_selection_actor_player_id(
            use_record=use_record,
            effect_payload=effect_payload,
        ),
        source_rule_id=_rule_effect_source_id(effect_payload),
        source_context=validate_json_value(source_context),
        phase_start_model_ids=_phase_start_model_ids(state=state, rules_unit=rules_unit),
        phase_start_enemy_engagement_model_ids=_phase_start_enemy_engagement_model_ids(
            state=state,
            rules_unit=rules_unit,
        ),
        revival_placements=_revival_placements_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
        ),
    )


def _phase_start_model_ids(*, state: GameState, rules_unit: RulesUnitView) -> tuple[str, ...]:
    return tuple(
        sorted(
            placement.model_instance_id
            for placement in _rules_unit_placements(state=state, rules_unit=rules_unit)
        )
    )


def _phase_start_enemy_engagement_model_ids(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[str, ...]:
    battlefield = _battlefield_state(state)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    own_placements = _rules_unit_placements(state=state, rules_unit=rules_unit)
    engaged_enemy_ids: set[str] = set()
    for own_placement in own_placements:
        own_model_instance = scenario.model_instance_for_placement(own_placement)
        if not own_model_instance.is_alive:
            continue
        own_model = geometry_model_for_placement(model=own_model_instance, placement=own_placement)
        for placed_army in battlefield.placed_armies:
            if placed_army.player_id == rules_unit.owner_player_id:
                continue
            for unit_placement in placed_army.unit_placements:
                for enemy_placement in unit_placement.model_placements:
                    enemy_model_instance = scenario.model_instance_for_placement(enemy_placement)
                    if not enemy_model_instance.is_alive:
                        continue
                    enemy_model = geometry_model_for_placement(
                        model=enemy_model_instance,
                        placement=enemy_placement,
                    )
                    if own_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                        vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
                    ):
                        engaged_enemy_ids.add(enemy_placement.model_instance_id)
    return tuple(sorted(engaged_enemy_ids))


def _revival_placements_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    battlefield = _battlefield_state(state)
    removed_model_ids = set(battlefield.removed_model_ids)
    missing_models = tuple(
        sorted(
            (
                model
                for model in rules_unit.own_models
                if not model.is_alive and model.model_instance_id in removed_model_ids
            ),
            key=lambda model: model.model_instance_id,
        )
    )
    if not missing_models:
        return ()
    anchors = _rules_unit_placements(state=state, rules_unit=rules_unit)
    if not anchors:
        raise GameLifecycleError("Generic RuleIR revival requires placed anchors.")
    army_id = _army_id_for_rules_unit(state=state, rules_unit=rules_unit)
    placements: list[ModelPlacement] = []
    for index, model in enumerate(missing_models):
        anchor = anchors[index % len(anchors)]
        secondary_anchor = anchors[(index + 1) % len(anchors)] if len(anchors) > 1 else None
        placements.append(
            ModelPlacement(
                army_id=army_id,
                player_id=rules_unit.owner_player_id,
                unit_instance_id=rules_unit.component_unit_id_for_model(model.model_instance_id),
                model_instance_id=model.model_instance_id,
                pose=_candidate_revival_pose(
                    battlefield=battlefield,
                    anchor=anchor,
                    secondary_anchor=secondary_anchor,
                    index=index,
                ),
            )
        )
    return tuple(placements)


def _rules_unit_placements(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    battlefield = _battlefield_state(state)
    component_ids = set(rules_unit.component_unit_instance_ids)
    model_ids = {model.model_instance_id for model in rules_unit.own_models}
    placements: list[ModelPlacement] = []
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id != rules_unit.owner_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id not in component_ids:
                continue
            placements.extend(
                placement
                for placement in unit_placement.model_placements
                if placement.model_instance_id in model_ids
            )
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def _candidate_revival_pose(
    *,
    battlefield: BattlefieldRuntimeState,
    anchor: ModelPlacement,
    secondary_anchor: ModelPlacement | None,
    index: int,
) -> Pose:
    if secondary_anchor is not None:
        anchor_position = anchor.pose.position
        secondary_position = secondary_anchor.pose.position
        return Pose.at(
            (anchor_position.x + secondary_position.x) / 2.0,
            (anchor_position.y + secondary_position.y) / 2.0,
            max(anchor_position.z, secondary_position.z),
        )
    offset = 0.5 + (index * 0.1)
    anchor_position = anchor.pose.position
    candidate_x = anchor_position.x + offset
    candidate_y = anchor_position.y
    if candidate_x > battlefield.battlefield_width_inches:
        candidate_x = anchor_position.x - offset
    if candidate_x < 0:
        candidate_x = anchor_position.x
        candidate_y = anchor_position.y + offset
    if candidate_y > battlefield.battlefield_depth_inches:
        candidate_y = anchor_position.y - offset
    if candidate_y < 0:
        raise GameLifecycleError("Generic RuleIR revival could not derive placement.")
    return Pose.at(candidate_x, candidate_y, anchor_position.z)


def _emit_healing_runtime_event(
    *,
    decisions: DecisionController,
    event_type: str,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    healing_effect: HealingEffect,
    pending_request_id: str | None,
) -> None:
    decisions.event_log.append(
        event_type,
        {
            "game_id": context.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "active_player_id": context.active_player_id,
            "stratagem_use": validate_json_value(use_record.to_payload()),
            "healing_effect": validate_json_value(healing_effect.to_payload()),
            "pending_request_id": pending_request_id,
        },
    )


def _selection_actor_player_id(
    *,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> str | None:
    actor = _optional_rule_effect_string_parameter(effect_payload, "selection_actor")
    if actor is None:
        return None
    if actor != "owner":
        raise GameLifecycleError("Generic healing selection actor is unsupported.")
    return use_record.player_id


def _unit_has_required_keyword_sequence(
    unit: UnitInstance,
    *,
    effect_payload: dict[str, JsonValue],
) -> bool:
    required_keywords = _optional_rule_effect_string_tuple_parameter(
        effect_payload,
        "required_keyword_sequence",
    )
    if required_keywords is None:
        return True
    return all(unit_has_keyword(unit, keyword) for keyword in required_keywords)


def _single_execution_target_unit_id(use_record: StratagemUseRecord) -> str:
    target_ids = generic_rule_ir_execution_target_unit_ids(use_record)
    if len(target_ids) != 1:
        raise GameLifecycleError("Generic RuleIR effect requires one target unit.")
    return target_ids[0]


def _effect_selection_unit_id(
    use_record: StratagemUseRecord,
    *,
    expected_selection_kind: str,
) -> str:
    selection_kind = _validate_identifier("effect_selection_kind", expected_selection_kind)
    selection = use_record.effect_selection
    if not isinstance(selection, dict):
        raise GameLifecycleError("Generic Stratagem effect requires effect selection.")
    if selection.get("effect_selection_kind") != selection_kind:
        raise GameLifecycleError("Generic Stratagem effect selection kind drift.")
    if selection_kind == HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        key = HIT_ENEMY_UNIT_CONTEXT_KEY
    elif selection_kind == ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        key = ENGAGED_ENEMY_UNIT_CONTEXT_KEY
    else:
        raise GameLifecycleError("Generic Stratagem effect selection kind is unsupported.")
    value = selection.get(key)
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem effect selection is missing unit.")
    return _validate_identifier("effect_selection_unit_id", value)


def _source_keyword_bonus(
    *,
    source_unit: UnitInstance,
    effect_payload: dict[str, JsonValue],
) -> int:
    keyword = _optional_rule_effect_string_parameter(effect_payload, "bonus_if_source_has_keyword")
    if keyword is None or not unit_has_keyword(source_unit, keyword):
        return 0
    return _required_rule_effect_int_parameter(effect_payload, "bonus")


def _trigger_payload_identifier(
    context: StratagemEligibilityContext,
    *,
    key: str,
) -> str:
    requested_key = _validate_identifier("trigger_payload key", key)
    payload = context.trigger_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Generic Stratagem requires structured trigger payload.")
    value = payload.get(requested_key)
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem trigger payload is missing identifier.")
    return _validate_identifier(requested_key, value)


def _trigger_payload_identifier_list(
    context: StratagemEligibilityContext,
    *,
    key: str,
) -> tuple[str, ...]:
    requested_key = _validate_identifier("trigger_payload key", key)
    payload = context.trigger_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Generic Stratagem requires structured trigger payload.")
    context_value = payload.get(requested_key)
    if not isinstance(context_value, list):
        raise GameLifecycleError("Generic Stratagem trigger payload list is missing.")
    identifiers = tuple(
        _validate_identifier(requested_key, value) for value in context_value if type(value) is str
    )
    if len(identifiers) != len(context_value):
        raise GameLifecycleError("Generic Stratagem trigger payload list must contain IDs.")
    if not identifiers:
        raise GameLifecycleError("Generic Stratagem trigger payload list must not be empty.")
    return tuple(sorted(identifiers))


def _current_battlefield_model_ids(*, state: GameState, unit: UnitInstance) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Generic Battle-shock requires battlefield state.")
    try:
        placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Generic Battle-shock target unit is not placed.") from exc
    unit_model_by_id = {model.model_instance_id: model for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        model = unit_model_by_id.get(model_placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("Battlefield placement contains unknown model.")
        if model.is_alive:
            current_ids.append(model.model_instance_id)
    if not current_ids:
        raise GameLifecycleError("Generic Battle-shock target unit has no current models.")
    return tuple(sorted(current_ids))


def _best_current_model_characteristic(
    unit: UnitInstance,
    *,
    current_model_ids: tuple[str, ...],
    characteristic: Characteristic,
) -> int:
    model_ids = set(current_model_ids)
    values = tuple(
        _model_characteristic(model, characteristic=characteristic)
        for model in unit.own_models
        if model.model_instance_id in model_ids
    )
    if not values:
        raise GameLifecycleError("Generic Battle-shock found no current characteristic.")
    return min(values)


def _model_characteristic(model: ModelInstance, *, characteristic: Characteristic) -> int:
    for candidate in model.characteristics:
        if candidate.characteristic is characteristic:
            return candidate.final
    raise GameLifecycleError("Generic Battle-shock target model is missing characteristic.")


def _army_id_for_rules_unit(*, state: GameState, rules_unit: RulesUnitView) -> str:
    for army in state.army_definitions:
        if army.player_id != rules_unit.owner_player_id:
            continue
        if any(
            unit.unit_instance_id in rules_unit.component_unit_instance_ids for unit in army.units
        ):
            return army.army_id
    raise GameLifecycleError("Generic RuleIR rules unit army is unknown.")


def _opposing_player_id(*, state: GameState, player_id: str) -> str:
    opponents = tuple(candidate for candidate in state.player_ids if candidate != player_id)
    if len(opponents) != 1:
        raise GameLifecycleError("Generic healing requires exactly one opposing player.")
    return opponents[0]


def _unit_owner_player_id(*, state: GameState, unit_instance_id: str) -> str:
    return rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id).owner_player_id


def _battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Generic RuleIR runtime effect requires battlefield_state.")
    return battlefield


def _event_payload(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect: PersistingEffect,
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "player_id": use_record.player_id,
        "battle_round": use_record.battle_round,
        "phase": use_record.phase.value,
        "active_player_id": context.active_player_id,
        "stratagem_use": validate_json_value(use_record.to_payload()),
        "persisting_effect": validate_json_value(effect.to_payload()),
    }


def _rule_effect_parameter(effect_payload: dict[str, JsonValue], key: str) -> JsonValue:
    requested_key = _validate_identifier("generic Stratagem effect parameter", key)
    effect = effect_payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic Stratagem effect payload requires effect object.")
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic Stratagem effect parameters must be a list.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Generic Stratagem effect parameter must be an object.")
        if parameter.get("key") == requested_key:
            return validate_json_value(parameter.get("value"))
    return None


def _rule_effect_source_id(effect_payload: dict[str, JsonValue]) -> str:
    value = effect_payload.get("source_id")
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem effect payload requires source_id.")
    return _validate_identifier("generic Stratagem source_id", value)


def _required_rule_effect_string_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> str:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not str:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a string.")
    return _validate_identifier(key, value)


def _optional_rule_effect_string_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> str | None:
    value = _rule_effect_parameter(effect_payload, key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a string.")
    return _validate_identifier(key, value)


def _required_rule_effect_int_parameter(effect_payload: dict[str, JsonValue], key: str) -> int:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not int:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be an int.")
    return value


def _required_rule_effect_bool_parameter(effect_payload: dict[str, JsonValue], key: str) -> bool:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a bool.")
    return value


def _optional_rule_effect_string_tuple_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> tuple[str, ...] | None:
    value = _rule_effect_parameter(effect_payload, key)
    if value is None:
        return None
    if not isinstance(value, list | tuple):
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a list.")
    values: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(
                f"Generic Stratagem effect parameter {key} must contain strings."
            )
        values.append(_validate_identifier(key, item))
    return tuple(values)
