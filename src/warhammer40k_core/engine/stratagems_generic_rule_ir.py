# ruff: noqa: F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_model import *
from warhammer40k_core.engine.stratagems_requests import *
from warhammer40k_core.engine.stratagems_selection import *
from warhammer40k_core.engine.stratagems_eligibility import *
from warhammer40k_core.engine.stratagems_targeting import *
from warhammer40k_core.engine.stratagems_geometry import *
from warhammer40k_core.engine.stratagems_ingress import *
from warhammer40k_core.engine.stratagems_generic_metadata import (
    generic_rule_ir_execution_target_unit_ids,
)
from warhammer40k_core.engine.stratagems_generic_rule_ir_context import (
    effect_selection_unit_id as _effect_selection_unit_id,
    rule_effect_source_unit_id_for_context as _rule_effect_source_unit_id_for_context,
)
from warhammer40k_core.engine.stratagems_generic_rule_ir_runtime import (
    apply_generic_rule_ir_reserve_removal,
    record_generic_rule_ir_charge_roll_modifier,
    resolve_generic_rule_ir_context_battle_shock,
    resolve_generic_rule_ir_mortal_wounds,
    resolve_generic_rule_ir_restore_lost_wounds,
    resolve_generic_rule_ir_return_destroyed_target,
)

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.core.modifiers import RollModifier
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rule_execution import RuleExecutionResult
    from warhammer40k_core.engine.triggered_movement import TriggeredMovementKind
    from warhammer40k_core.engine.unit_state import StartingStrengthRecord
# fmt: on

__all__ = (
    "_apply_generic_rule_ir_stratagem_handler",
    "_generic_rule_ir_from_stratagem_payload",
)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )


def _require_target_unit_id(binding: StratagemTargetBinding) -> str:
    if binding.target_unit_instance_id is None:
        raise GameLifecycleError("Stratagem target binding requires a unit id.")
    return binding.target_unit_instance_id


def _generic_rule_ir_from_stratagem_payload(effect_payload: JsonValue) -> object:
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    return rule_ir_from_execution_payload(effect_payload)


def _apply_generic_rule_ir_stratagem_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
) -> None:
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionContext,
        RuleExecutionStatus,
        execute_rule_ir,
        rule_ir_from_execution_payload,
    )

    rule_ir = rule_ir_from_execution_payload(definition.effect_payload)
    rule_result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
            timing_window_id=context.timing_window_id,
            source_unit_instance_id=_single_target_unit_id_or_none(use_record),
            target_unit_instance_ids=generic_rule_ir_execution_target_unit_ids(use_record),
            target_player_id=target_binding.target_player_id,
            trigger_payload=_generic_stratagem_rule_trigger_payload(
                context=context,
                definition=definition,
                use_record=use_record,
            ),
            state=state,
            event_log=decisions.event_log,
        ),
    )
    if rule_result.status is not RuleExecutionStatus.APPLIED:
        if rule_result.reason is None:
            raise GameLifecycleError("Generic Stratagem rule execution failed without reason.")
        raise GameLifecycleError(f"Generic Stratagem rule execution failed: {rule_result.reason}.")
    if _rule_execution_result_grants_out_of_phase_shoot(rule_result.effect_payloads):
        _request_generic_out_of_phase_shooting(
            state=state,
            decisions=decisions,
            context=context,
            definition=definition,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
        )
    _record_generic_rule_ir_stratagem_runtime_effects(
        state=state,
        decisions=decisions,
        context=context,
        target_binding=target_binding,
        use_record=use_record,
        rule_result=rule_result,
        ruleset_descriptor=ruleset_descriptor,
    )
    if _rule_execution_result_grants_triggered_normal_move(rule_result.effect_payloads):
        _request_generic_triggered_normal_move(
            state=state,
            decisions=decisions,
            context=context,
            definition=definition,
            use_record=use_record,
            rule_result=rule_result,
        )
    if _rule_execution_result_grants_strategic_reserves_placement(rule_result.effect_payloads):
        _request_generic_rule_ir_strategic_reserves_placement(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
            rule_result=rule_result,
        )
    if _rule_execution_result_forces_desperate_escape(rule_result.effect_payloads):
        _record_generic_rule_ir_force_desperate_escape(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
            rule_result=rule_result,
        )


def _single_target_unit_id_or_none(use_record: StratagemUseRecord) -> str | None:
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic Stratagem source binding requires use record.")
    if len(use_record.targeted_unit_instance_ids) == 1:
        return use_record.targeted_unit_instance_ids[0]
    return None


def _generic_stratagem_rule_trigger_payload(
    *,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
) -> JsonValue:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Generic Stratagem trigger payload requires context.")
    if type(definition) is not StratagemDefinition:
        raise GameLifecycleError("Generic Stratagem trigger payload requires definition.")
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic Stratagem trigger payload requires use record.")
    payload: dict[str, JsonValue] = {}
    if isinstance(context.trigger_payload, dict):
        payload.update(context.trigger_payload)
    elif context.trigger_payload is not None:
        payload["source_trigger_payload"] = context.trigger_payload
    payload.update(
        {
            "stratagem_id": definition.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "effect_selection": use_record.effect_selection,
            "stratagem_context": validate_json_value(context.to_payload()),
        }
    )
    return validate_json_value(payload)


def _rule_execution_result_grants_out_of_phase_shoot(
    effect_payloads: tuple[dict[str, JsonValue], ...],
) -> bool:
    return _rule_execution_result_grants_ability(
        effect_payloads=effect_payloads,
        ability="out_of_phase_shoot",
    )


def _rule_execution_result_grants_triggered_normal_move(
    effect_payloads: tuple[dict[str, JsonValue], ...],
) -> bool:
    return _rule_execution_result_grants_ability(
        effect_payloads=effect_payloads,
        ability="triggered_normal_move",
    )


def _rule_execution_result_grants_strategic_reserves_placement(
    effect_payloads: tuple[dict[str, JsonValue], ...],
) -> bool:
    return any(
        _rule_effect_payload_kind(effect_payload) == "placement_permission"
        and _rule_effect_parameter(effect_payload, "placement_kind") == "strategic_reserves"
        and _rule_effect_parameter(effect_payload, "operation") != "remove_to_reserves"
        for effect_payload in effect_payloads
    )


def _rule_execution_result_forces_desperate_escape(
    effect_payloads: tuple[dict[str, JsonValue], ...],
) -> bool:
    return any(
        _rule_effect_payload_kind(effect_payload) == "force_desperate_escape_tests"
        for effect_payload in effect_payloads
    )


def _rule_execution_result_grants_ability(
    *,
    effect_payloads: tuple[dict[str, JsonValue], ...],
    ability: str,
) -> bool:
    if type(effect_payloads) is not tuple:
        raise GameLifecycleError("Generic Stratagem effect payloads must be a tuple.")
    requested_ability = _validate_identifier("generic Stratagem ability", ability)
    granted = False
    for effect_payload in effect_payloads:
        effect = effect_payload.get("effect")
        if not isinstance(effect, dict):
            raise GameLifecycleError("Generic Stratagem effect payload requires effect object.")
        if effect.get("kind") != "grant_ability":
            continue
        parameters = effect.get("parameters")
        if not isinstance(parameters, list):
            raise GameLifecycleError("Generic Stratagem effect parameters must be a list.")
        for parameter in parameters:
            if not isinstance(parameter, dict):
                raise GameLifecycleError("Generic Stratagem effect parameter must be an object.")
            if parameter.get("key") == "ability" and parameter.get("value") == requested_ability:
                granted = True
    return granted


def _record_generic_rule_ir_stratagem_runtime_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    rule_result_payload = validate_json_value(rule_result.to_payload())
    for effect_payload in rule_result.effect_payloads:
        effect_kind = _rule_effect_payload_kind(effect_payload)
        if effect_kind == "grant_ability":
            ability = _rule_effect_parameter(effect_payload, "ability")
            if ability == "charge_after_fall_back":
                _record_generic_charge_after_fall_back_effect(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    rule_result=rule_result,
                    effect_payload=effect_payload,
                )
            continue
        if effect_kind == "set_contextual_status":
            status = _rule_effect_parameter(effect_payload, "status")
            if status == "smokescreen_target_restriction":
                _record_generic_smokescreen_target_restriction_effect(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    rule_result=rule_result,
                    effect_payload=effect_payload,
                )
            elif status == "unit_action_restriction":
                _record_generic_unit_action_restriction_effect(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    rule_result=rule_result,
                    effect_payload=effect_payload,
                )
            elif status == "detection_range_bonus":
                _record_generic_detection_range_bonus_effect(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    rule_result=rule_result,
                    effect_payload=effect_payload,
                )
            elif status == "benefit_of_cover":
                _record_generic_benefit_of_cover_denial_effect(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    rule_result=rule_result,
                    effect_payload=effect_payload,
                )
            elif status == "force_battle_shock_test":
                if (
                    _optional_rule_effect_string_parameter(
                        effect_payload,
                        "target_unit_context_key",
                    )
                    is None
                ):
                    _resolve_generic_forced_battle_shock_test(
                        state=state,
                        decisions=decisions,
                        context=context,
                        use_record=use_record,
                        effect_payload=effect_payload,
                    )
                else:
                    resolve_generic_rule_ir_context_battle_shock(
                        state=state,
                        decisions=decisions,
                        context=context,
                        use_record=use_record,
                        effect_payload=effect_payload,
                    )
            continue
        if effect_kind == "inflict_mortal_wounds":
            resolve_generic_rule_ir_mortal_wounds(
                state=state,
                decisions=decisions,
                context=context,
                use_record=use_record,
                effect_payload=effect_payload,
            )
            continue
        if effect_kind == "modify_dice_roll":
            if (
                _optional_rule_effect_string_parameter(effect_payload, "roll_type") == "charge"
                and _optional_rule_effect_string_parameter(
                    effect_payload,
                    "target_unit_context_key",
                )
                is not None
            ):
                record_generic_rule_ir_charge_roll_modifier(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    rule_result_payload=rule_result_payload,
                    effect_payload=effect_payload,
                    expiration=_expiration_for_rule_effect_payload(
                        effect_payload=effect_payload,
                        context=context,
                        use_record=use_record,
                    ),
                )
            continue
        if effect_kind == "placement_permission":
            if _optional_rule_effect_string_parameter(effect_payload, "operation") == (
                "remove_to_reserves"
            ):
                apply_generic_rule_ir_reserve_removal(
                    state=state,
                    decisions=decisions,
                    context=context,
                    use_record=use_record,
                    effect_payload=effect_payload,
                )
            continue
        if effect_kind == "restore_lost_wounds":
            resolve_generic_rule_ir_restore_lost_wounds(
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                context=context,
                use_record=use_record,
                rule_result_payload=rule_result_payload,
                effect_payload=effect_payload,
            )
            continue
        if effect_kind == "return_destroyed_target":
            resolve_generic_rule_ir_return_destroyed_target(
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                context=context,
                use_record=use_record,
                rule_result_payload=rule_result_payload,
                effect_payload=effect_payload,
            )


def _record_generic_charge_after_fall_back_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    from warhammer40k_core.engine.phases.charge import CHARGE_AFTER_FALL_BACK_EFFECT_KIND

    unit_id = _single_target_unit_id(use_record)
    source_effect_kind = _optional_rule_effect_string_parameter(
        effect_payload,
        "source_effect_kind",
    )
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:charge-after-fall-back:{unit_id}",
        source_rule_id=_rule_effect_source_id(effect_payload),
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=_expiration_for_rule_effect_payload(
            effect_payload=effect_payload,
            context=context,
            use_record=use_record,
        ),
        effect_payload={
            "effect_kind": CHARGE_AFTER_FALL_BACK_EFFECT_KIND,
            "source_effect_kind": source_effect_kind,
            "stratagem_id": use_record.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_charge_after_fall_back_registered",
        _generic_runtime_effect_event_payload(
            state=state,
            context=context,
            use_record=use_record,
            effect=effect,
        ),
    )


def _record_generic_smokescreen_target_restriction_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND

    unit_id = _single_target_unit_id(use_record)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:smokescreen-target-restriction:{unit_id}",
        source_rule_id=_rule_effect_source_id(effect_payload),
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=_expiration_for_rule_effect_payload(
            effect_payload=effect_payload,
            context=context,
            use_record=use_record,
        ),
        effect_payload={
            "effect_kind": SMOKESCREEN_EFFECT_KIND,
            "source_effect_kind": _required_rule_effect_string_parameter(
                effect_payload,
                "source_effect_kind",
            ),
            "stratagem_id": use_record.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "hit_roll_modifier": _required_rule_effect_int_parameter(
                effect_payload,
                "hit_roll_modifier",
            ),
            "targeting_max_range_inches": _required_rule_effect_number_parameter(
                effect_payload,
                "targeting_max_range_inches",
            ),
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_smokescreen_target_restriction_registered",
        _generic_runtime_effect_event_payload(
            state=state,
            context=context,
            use_record=use_record,
            effect=effect,
        ),
    )


def _record_generic_unit_action_restriction_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    unit_id = _single_target_unit_id(use_record)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:unit-action-restriction:{unit_id}",
        source_rule_id=_rule_effect_source_id(effect_payload),
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=_expiration_for_rule_effect_payload(
            effect_payload=effect_payload,
            context=context,
            use_record=use_record,
        ),
        effect_payload={
            "effect_kind": _required_rule_effect_string_parameter(effect_payload, "effect_kind"),
            "charge_forbidden": _required_rule_effect_bool_parameter(
                effect_payload,
                "charge_forbidden",
            ),
            "embark_transport_forbidden": _required_rule_effect_bool_parameter(
                effect_payload,
                "embark_transport_forbidden",
            ),
            "stratagem_use_id": use_record.use_id,
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_unit_action_restriction_registered",
        _generic_runtime_effect_event_payload(
            state=state,
            context=context,
            use_record=use_record,
            effect=effect,
        ),
    )


def _record_generic_detection_range_bonus_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    from warhammer40k_core.engine.ranged_rule_effects import detection_range_bonus_payload

    target_unit_id = _effect_selection_unit_id(
        use_record,
        expected_selection_kind=_required_rule_effect_string_parameter(
            effect_payload,
            "effect_selection_kind",
        ),
    )
    source_unit_id = _rule_effect_source_unit_id_for_context(
        context=context,
        use_record=use_record,
        effect_payload=effect_payload,
    )
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:detection-range-bonus:{target_unit_id}",
        source_rule_id=_rule_effect_source_id(effect_payload),
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=_expiration_for_rule_effect_payload(
            effect_payload=effect_payload,
            context=context,
            use_record=use_record,
        ),
        effect_payload=detection_range_bonus_payload(
            bonus_inches=_required_rule_effect_int_parameter(effect_payload, "bonus_inches"),
            source_rule_kind=_required_rule_effect_string_parameter(
                effect_payload,
                "source_rule_kind",
            ),
            source_unit_instance_id=source_unit_id,
            source_decision_request_id=use_record.request_id,
            source_decision_result_id=use_record.result_id,
            stratagem_use_id=use_record.use_id,
        ),
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_detection_range_bonus_registered",
        {
            **_generic_runtime_effect_event_payload(
                state=state,
                context=context,
                use_record=use_record,
                effect=effect,
            ),
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )


def _record_generic_benefit_of_cover_denial_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    if _required_rule_effect_string_parameter(effect_payload, "rules_context") != "status_denial":
        raise GameLifecycleError("Generic cover denial requires status-denial context.")
    if _required_rule_effect_string_parameter(effect_payload, "operation") != "deny":
        raise GameLifecycleError("Generic cover denial requires deny operation.")
    if _required_rule_effect_string_parameter(effect_payload, "status") != "benefit_of_cover":
        raise GameLifecycleError("Generic cover denial requires Benefit of Cover status.")
    target_scope = _required_rule_effect_string_parameter(effect_payload, "target_scope")
    if target_scope not in {"selected_unit", "models_in_selected_unit"}:
        raise GameLifecycleError("Generic cover denial target scope is unsupported.")
    source_rule_id = _rule_effect_source_id(effect_payload)
    effect_selection_kind = _required_rule_effect_string_parameter(
        effect_payload, "effect_selection_kind"
    )
    target_unit_id = _effect_selection_unit_id(
        use_record,
        expected_selection_kind=effect_selection_kind,
    )
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:benefit-of-cover-denial:{target_unit_id}",
        source_rule_id=source_rule_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=_expiration_for_rule_effect_payload(
            effect_payload=effect_payload,
            context=context,
            use_record=use_record,
        ),
        effect_payload={
            "effect_kind": "generic_stratagem_benefit_of_cover_denial",
            "stratagem_id": use_record.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "source_rule_id": source_rule_id,
            "target_unit_instance_id": target_unit_id,
            "status": "benefit_of_cover",
            "status_label": "Benefit of Cover",
            "operation": "deny",
            "target_scope": target_scope,
            "benefit_of_cover_denied": True,
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_benefit_of_cover_denial_registered",
        _generic_runtime_effect_event_payload(
            state=state,
            context=context,
            use_record=use_record,
            effect=effect,
        ),
    )


def _resolve_generic_forced_battle_shock_test(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.core.modifiers import RollModifier
    from warhammer40k_core.engine.battle_shock import (
        BattleShockResult,
        BattleShockTestReason,
        BattleShockTestRequest,
    )
    from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

    target_unit_id = _effect_selection_unit_id(
        use_record,
        expected_selection_kind=_required_rule_effect_string_parameter(
            effect_payload,
            "effect_selection_kind",
        ),
    )
    target_owner = unit_owner_player_id(state=state, unit_instance_id=target_unit_id)
    target_unit = _unit_by_id(state=state, unit_instance_id=target_unit_id)
    current_model_ids = _current_battlefield_model_ids(state=state, unit=target_unit)
    starting_strength = _starting_strength_record(state=state, unit_instance_id=target_unit_id)
    below_half_context = BelowHalfStrengthContext.from_unit(
        player_id=target_owner,
        unit=target_unit,
        starting_strength=starting_strength,
        current_model_ids=current_model_ids,
    )
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
        below_half_strength_context=below_half_context,
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
    modifiers = _generic_battle_shock_modifiers(
        context=context,
        use_record=use_record,
        effect_payload=effect_payload,
        target_unit_id=target_unit_id,
    )
    result = BattleShockResult.from_roll_state(
        result_id=f"{request.request_id}:result",
        request=request,
        roll_state=roll_state,
        modifiers=modifiers,
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


def _request_generic_rule_ir_strategic_reserves_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
) -> None:
    reserve_state = _reserve_state_for_target(state=state, target_binding=target_binding)
    if reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES:
        raise GameLifecycleError("Generic RuleIR placement requires a Strategic Reserves target.")
    effect_payload = _single_rule_effect_payload(
        rule_result.effect_payloads,
        effect_kind="placement_permission",
    )
    if _rule_effect_parameter(effect_payload, "from_start_of_battle") is not True:
        raise GameLifecycleError("Generic RuleIR placement must allow start-of-battle use.")
    if _rule_effect_parameter(effect_payload, "placement_scope") != "strategic_reserves_only":
        raise GameLifecycleError("Generic RuleIR placement must be Strategic Reserves only.")
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=context.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=reserve_state.unit_instance_id,
        proposal_kind=ProposalKind.STRATEGIC_RESERVES,
        source_decision_request_id=use_record.request_id,
        source_decision_result_id=use_record.result_id,
        placement_kinds=(BattlefieldPlacementKind.STRATEGIC_RESERVES,),
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
                    "stratagem_use": validate_json_value(use_record.to_payload()),
                    "reserve_state": validate_json_value(reserve_state.to_payload()),
                    "from_start_of_battle": True,
                    "mark_movement_phase_reinforcement_arrival": (
                        context.active_player_id == context.player_id
                    ),
                    "placement_scope": "strategic_reserves_only",
                    "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
                    "generic_rule_effect": validate_json_value(effect_payload),
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": context.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": ProposalKind.STRATEGIC_RESERVES.value,
            "placement_kinds": [BattlefieldPlacementKind.STRATEGIC_RESERVES.value],
            "request_id": request.request_id,
            "source_decision_request_id": use_record.request_id,
            "source_decision_result_id": use_record.result_id,
            "stratagem_use_id": use_record.use_id,
            "phase_body_status": "generic_rule_ir_placement_proposal_required",
        },
    )


def _record_generic_rule_ir_force_desperate_escape(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    fall_back_unit_id = _fall_back_unit_id_or_none(context)
    if fall_back_unit_id is None:
        raise GameLifecycleError("Generic RuleIR force Desperate Escape requires context.")
    effect_payload = _single_rule_effect_payload(
        rule_result.effect_payloads,
        effect_kind="force_desperate_escape_tests",
    )
    required_mode = _rule_effect_parameter(effect_payload, "required_fall_back_mode")
    if required_mode is None:
        required_mode = "desperate_escape"
    if required_mode != "desperate_escape":
        raise GameLifecycleError("Generic RuleIR force Desperate Escape has unsupported mode.")
    source_rule_id = _rule_effect_source_id(effect_payload)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:force-desperate-escape:{fall_back_unit_id}",
        source_rule_id=source_rule_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(fall_back_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=BattlePhase.MOVEMENT,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND,
            "stratagem_use_id": use_record.use_id,
            "source_rule_id": source_rule_id,
            "source_stratagem_id": use_record.stratagem_id,
            "forcing_unit_instance_id": target_unit_id,
            "fall_back_unit_instance_id": fall_back_unit_id,
            "required_fall_back_mode": "desperate_escape",
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "forced_fall_back_desperate_escape_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": context.active_player_id,
            "stratagem_use": use_record.to_payload(),
            "forcing_unit_instance_id": target_unit_id,
            "fall_back_unit_instance_id": fall_back_unit_id,
            "persisting_effect": effect.to_payload(),
        },
    )


def _single_rule_effect_payload(
    effect_payloads: tuple[dict[str, JsonValue], ...],
    *,
    effect_kind: str,
) -> dict[str, JsonValue]:
    matching = tuple(
        effect_payload
        for effect_payload in effect_payloads
        if _rule_effect_payload_kind(effect_payload) == effect_kind
    )
    if len(matching) != 1:
        raise GameLifecycleError("Generic RuleIR Stratagem must produce exactly one effect.")
    return matching[0]


def _rule_effect_payload_kind(effect_payload: dict[str, JsonValue]) -> str | None:
    effect = effect_payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic Stratagem effect payload requires effect object.")
    value = effect.get("kind")
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem effect kind must be a string.")
    return value


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
        if parameter.get("key") != requested_key:
            continue
        return validate_json_value(parameter.get("value"))
    return None


def _rule_effect_source_id(effect_payload: dict[str, JsonValue]) -> str:
    value = effect_payload.get("source_id")
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem effect payload requires source_id.")
    return _validate_identifier("generic Stratagem source_id", value)


def _request_generic_out_of_phase_shooting(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
) -> None:
    shooting_unit_id = _single_target_unit_id_or_none(use_record)
    if shooting_unit_id is None:
        raise GameLifecycleError("Generic out-of-phase shooting requires one target unit.")
    enemy_unit_id = _just_shot_unit_id_or_none(context)
    if enemy_unit_id is None:
        raise GameLifecycleError("Generic out-of-phase shooting requires just-shot unit context.")
    request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=use_record.player_id,
        unit_instance_id=shooting_unit_id,
        parent_phase=context.phase,
        source_rule_id=definition.source_id,
        source_decision_request_id=use_record.request_id,
        source_decision_result_id=use_record.result_id,
        source_context=validate_json_value(
            {
                "source_kind": "generic_rule_ir_stratagem",
                "stratagem_use": use_record.to_payload(),
                "stratagem_context": context.to_payload(),
                "trigger_kind": context.trigger_kind.value,
                "trigger_payload": context.trigger_payload,
                "target_unit_ids": [enemy_unit_id],
            }
        ),
        target_unit_ids=(enemy_unit_id,),
        shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
    )
    decisions.event_log.append(
        "generic_stratagem_out_of_phase_shooting_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "shooting_unit_instance_id": shooting_unit_id,
            "target_unit_instance_id": enemy_unit_id,
        },
    )


def _request_generic_triggered_normal_move(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
) -> None:
    from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementEligibleUnit,
        TriggeredMovementKind,
        triggered_movement_unit_selection_request,
    )

    moving_unit_id = _single_target_unit_id_or_none(use_record)
    if moving_unit_id is None:
        raise GameLifecycleError("Generic triggered movement requires one target unit.")
    effect_payload = _single_grant_ability_effect_payload(
        rule_result.effect_payloads,
        ability="triggered_normal_move",
    )
    roll_payload, max_distance = _generic_triggered_move_distance_roll(
        state=state,
        decisions=decisions,
        definition=definition,
        use_record=use_record,
        effect_payload=effect_payload,
        moving_unit_id=moving_unit_id,
    )
    source_step = _optional_rule_effect_string_parameter(effect_payload, "source_step")
    if source_step is None:
        source_step = "generic_rule_ir_triggered_normal_move"
    descriptor = TriggeredMovementDescriptor(
        movement_kind=_generic_triggered_movement_kind(effect_payload),
        source_rule_id=definition.source_id,
        trigger_timing=ReactionWindow(
            phase=context.phase,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=source_step,
            source_event_id=_generic_triggered_move_source_event_id(
                context=context,
                use_record=use_record,
                effect_payload=effect_payload,
            ),
        ),
        max_distance_inches=float(max_distance),
        movement_mode=_generic_triggered_movement_mode(effect_payload),
        allow_battle_shocked=_optional_rule_effect_bool_parameter(
            effect_payload,
            "allow_battle_shocked",
            default=False,
        ),
        allow_within_engagement_range=_optional_rule_effect_bool_parameter(
            effect_payload,
            "allow_within_engagement_range",
            default=False,
        ),
        one_per_phase=_optional_rule_effect_bool_parameter(
            effect_payload,
            "one_per_phase",
            default=False,
        ),
        optional=_optional_rule_effect_bool_parameter(effect_payload, "optional", default=True),
    )
    replay_effect_kind = _optional_rule_effect_string_parameter(
        effect_payload, "replay_effect_kind"
    )
    if replay_effect_kind is None:
        replay_effect_kind = "generic_rule_ir_triggered_normal_move"
    request = triggered_movement_unit_selection_request(
        state=state,
        player_id=use_record.player_id,
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(
                unit_instance_id=moving_unit_id,
                hook_id=definition.handler_id,
                source_id=definition.source_id,
                replay_payload={
                    "effect_kind": replay_effect_kind,
                    "stratagem_use_id": use_record.use_id,
                    "distance_roll": roll_payload,
                    "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
                    "generic_rule_effect": validate_json_value(effect_payload),
                },
                decision_effect_payload=None,
            ),
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "generic_stratagem_triggered_normal_move_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "unit_instance_id": moving_unit_id,
            "max_distance_inches": max_distance,
            "distance_roll": roll_payload,
            "request_id": request.request_id,
            "phase_body_status": _optional_rule_effect_string_parameter(
                effect_payload,
                "phase_body_status",
            ),
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )


def _generic_triggered_move_distance_roll(
    *,
    state: GameState,
    decisions: DecisionController,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
    moving_unit_id: str,
) -> tuple[JsonValue, int]:
    roll_sides = _optional_rule_effect_int_parameter(effect_payload, "roll_sides")
    if roll_sides is None:
        d3_result = DiceRollManager(state.game_id, event_log=decisions.event_log).roll_d3(
            reason=f"{definition.stratagem_id} triggered normal move for {moving_unit_id}",
            roll_type="generic_rule_ir_triggered_normal_move_d3",
            actor_id=use_record.player_id,
        )
        return validate_json_value(d3_result.to_payload()), d3_result.value + 3
    quantity = _optional_rule_effect_int_parameter(effect_payload, "roll_quantity")
    quantity = 1 if quantity is None else quantity
    distance_bonus = _optional_rule_effect_int_parameter(effect_payload, "distance_bonus")
    distance_bonus = 0 if distance_bonus is None else distance_bonus
    roll_type = _optional_rule_effect_string_parameter(effect_payload, "roll_type")
    roll_type = "generic_rule_ir_triggered_normal_move" if roll_type is None else roll_type
    roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=quantity, sides=roll_sides),
            reason=f"{definition.stratagem_id} triggered normal move for {moving_unit_id}",
            roll_type=roll_type,
            actor_id=use_record.player_id,
        )
    )
    return validate_json_value(roll_state.to_payload()), roll_state.current_total + distance_bonus


def _generic_triggered_movement_kind(
    effect_payload: dict[str, JsonValue],
) -> TriggeredMovementKind:
    from warhammer40k_core.engine.triggered_movement import TriggeredMovementKind

    token = _optional_rule_effect_string_parameter(effect_payload, "movement_kind")
    if token is None:
        return TriggeredMovementKind.TRIGGERED
    try:
        return TriggeredMovementKind(token)
    except ValueError as exc:
        raise GameLifecycleError("Generic triggered movement kind is unsupported.") from exc


def _generic_triggered_movement_mode(effect_payload: dict[str, JsonValue]) -> MovementMode:
    token = _optional_rule_effect_string_parameter(effect_payload, "movement_mode")
    if token is None:
        return MovementMode.NORMAL
    try:
        return MovementMode(token)
    except ValueError as exc:
        raise GameLifecycleError("Generic triggered movement mode is unsupported.") from exc


def _generic_triggered_move_source_event_id(
    *,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> str:
    context_key = _optional_rule_effect_string_parameter(
        effect_payload, "source_event_id_context_key"
    )
    if context_key is None:
        return use_record.use_id
    return _trigger_payload_identifier(context, key=context_key)


def _single_grant_ability_effect_payload(
    effect_payloads: tuple[dict[str, JsonValue], ...],
    *,
    ability: str,
) -> dict[str, JsonValue]:
    matching = tuple(
        effect_payload
        for effect_payload in effect_payloads
        if _rule_effect_payload_kind(effect_payload) == "grant_ability"
        and _rule_effect_parameter(effect_payload, "ability") == ability
    )
    if len(matching) != 1:
        raise GameLifecycleError("Generic RuleIR Stratagem must produce exactly one ability grant.")
    return matching[0]


def _single_target_unit_id(use_record: StratagemUseRecord) -> str:
    unit_id = _single_target_unit_id_or_none(use_record)
    if unit_id is None:
        raise GameLifecycleError("Generic Stratagem effect requires one target unit.")
    return unit_id


def _trigger_payload_identifier(context: StratagemEligibilityContext, *, key: str) -> str:
    requested_key = _validate_identifier("trigger_payload key", key)
    payload = context.trigger_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Generic Stratagem requires structured trigger payload.")
    value = payload.get(requested_key)
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem trigger payload is missing identifier.")
    return _validate_identifier(requested_key, value)


def _expiration_for_rule_effect_payload(
    *,
    effect_payload: dict[str, JsonValue],
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
) -> EffectExpiration:
    duration = effect_payload.get("duration")
    if not isinstance(duration, dict):
        raise GameLifecycleError("Generic persisted Stratagem effect requires duration.")
    kind = duration.get("kind")
    if kind == "permanent":
        return EffectExpiration.end_of_battle()
    if kind != "until_timing_endpoint":
        raise GameLifecycleError("Generic persisted Stratagem effect duration is unsupported.")
    endpoint = _duration_parameter(duration, "endpoint")
    if endpoint == "phase":
        return EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        )
    if endpoint == "turn":
        return EffectExpiration.end_turn(
            battle_round=use_record.battle_round,
            player_id=context.active_player_id or use_record.player_id,
        )
    if endpoint == "battle":
        return EffectExpiration.end_of_battle()
    raise GameLifecycleError("Generic persisted Stratagem effect endpoint is unsupported.")


def _duration_parameter(duration_payload: dict[str, JsonValue], key: str) -> str:
    requested_key = _validate_identifier("duration parameter", key)
    parameters = duration_payload.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic effect duration parameters must be a list.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Generic effect duration parameter must be an object.")
        if parameter.get("key") != requested_key:
            continue
        value = parameter.get("value")
        if type(value) is not str:
            raise GameLifecycleError("Generic effect duration parameter must be a string.")
        return _validate_identifier(requested_key, value)
    raise GameLifecycleError("Generic effect duration parameter is missing.")


def _generic_runtime_effect_event_payload(
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


def _generic_battle_shock_modifiers(
    *,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
    target_unit_id: str,
) -> tuple[RollModifier, ...]:
    from warhammer40k_core.core.modifiers import RollModifier

    modifier = _optional_rule_effect_int_parameter(effect_payload, "modifier_if_destroyed_target")
    if modifier is None:
        return ()
    if target_unit_id not in destroyed_target_unit_ids_from_context(context):
        return ()
    source_suffix = _optional_rule_effect_string_parameter(effect_payload, "modifier_source_suffix")
    if source_suffix is None:
        source_suffix = "battle-shock-modifier"
    return (
        RollModifier(
            modifier_id=f"{use_record.use_id}:{source_suffix}",
            source_id=_rule_effect_source_id(effect_payload),
            operand=modifier,
        ),
    )


def _current_battlefield_model_ids(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.battlefield_state import PlacementError

    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Generic forced Battle-shock requires battlefield state.")
    try:
        placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Generic forced Battle-shock target unit is not placed.") from exc
    unit_model_by_id = {model.model_instance_id: model for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        model = unit_model_by_id.get(model_placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("Battlefield placement contains unknown model.")
        if model.is_alive:
            current_ids.append(model.model_instance_id)
    if not current_ids:
        raise GameLifecycleError("Generic forced Battle-shock target unit has no current models.")
    return tuple(sorted(current_ids))


def _starting_strength_record(*, state: GameState, unit_instance_id: str) -> StartingStrengthRecord:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for record in state.starting_strength_records:
        if record.unit_instance_id == requested_unit_id:
            return record
    raise GameLifecycleError("Generic forced Battle-shock target is missing starting strength.")


def _best_current_model_characteristic(
    unit: UnitInstance,
    *,
    current_model_ids: tuple[str, ...],
    characteristic: Characteristic,
) -> int:
    model_ids = set(_validate_identifier_tuple("current_model_ids", current_model_ids))
    values = tuple(
        _model_characteristic(model, characteristic=characteristic)
        for model in unit.own_models
        if model.model_instance_id in model_ids
    )
    if not values:
        raise GameLifecycleError("Generic forced Battle-shock found no current characteristic.")
    return min(values)


def _model_characteristic(model: object, *, characteristic: Characteristic) -> int:
    from warhammer40k_core.engine.unit_factory import ModelInstance

    if not isinstance(model, ModelInstance):
        raise GameLifecycleError("Generic characteristic lookup requires a ModelInstance.")
    for candidate in model.characteristics:
        if candidate.characteristic is characteristic:
            return candidate.final
    raise GameLifecycleError("Generic forced Battle-shock target model is missing characteristic.")


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


def _required_rule_effect_int_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> int:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not int:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be an int.")
    return value


def _optional_rule_effect_int_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> int | None:
    value = _rule_effect_parameter(effect_payload, key)
    if value is None:
        return None
    if type(value) is not int:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be an int.")
    return value


def _required_rule_effect_number_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> float:
    value = _rule_effect_parameter(effect_payload, key)
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be numeric.")
    return float(value)


def _required_rule_effect_bool_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> bool:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a bool.")
    return value


def _optional_rule_effect_bool_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
    *,
    default: bool,
) -> bool:
    value = _rule_effect_parameter(effect_payload, key)
    if value is None:
        return default
    if type(value) is not bool:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a bool.")
    return value
