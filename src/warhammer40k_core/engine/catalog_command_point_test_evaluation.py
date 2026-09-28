"""Resumable modifier preflight and resolution for catalog CP test occurrences."""

from __future__ import annotations

# The source classifier remains owned by the catalog provider.
# pyright: reportPrivateUsage=false
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modified_dice import ModifiedRollResult, UnmodifiedRollResult
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_command_point_support import (
    clause_is_supported_phase_end_leadership_command_point_gain,
)
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    LEADERSHIP_TEST_ROLL_TYPE,
    selected_target_test_roll_modifiers,
)
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.events import RuntimeContentEventContext
from warhammer40k_core.engine.nonattack_modifier_evaluation import (
    LeadershipModifierEvaluation,
    evaluate_leadership_modifiers,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_id_for_unit_id
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import parameter_payload

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_command_point_runtime import _PhaseGainSource


def with_command_point_modifier_preflight(
    candidate: TimingRuleCandidate,
    *,
    context: RuntimeContentEventContext,
    source: _PhaseGainSource,
    unit: UnitInstance,
    source_model_instance_id: str,
    ability_index: AbilityCatalogIndex,
) -> TimingRuleCandidate:
    return replace(
        candidate,
        activate=partial(
            _activate_with_preflight,
            candidate,
            context=context,
            source=source,
            unit=unit,
            source_model_instance_id=source_model_instance_id,
            ability_index=ability_index,
        ),
    )


def _activate_with_preflight(
    candidate: TimingRuleCandidate,
    *,
    context: RuntimeContentEventContext,
    source: _PhaseGainSource,
    unit: UnitInstance,
    source_model_instance_id: str,
    ability_index: AbilityCatalogIndex,
) -> DecisionRequest | LifecycleStatus | None:
    evaluation = _leadership_evaluation(
        context=context,
        source=source,
        unit=unit,
        source_model_instance_id=source_model_instance_id,
        ability_index=ability_index,
    )
    if evaluation is not None and evaluation.pending_status is not None:
        return evaluation.pending_status
    return candidate.activate()


def _leadership_evaluation(
    *,
    context: RuntimeContentEventContext,
    source: _PhaseGainSource,
    unit: UnitInstance,
    source_model_instance_id: str,
    ability_index: AbilityCatalogIndex,
) -> LeadershipModifierEvaluation | None:
    from warhammer40k_core.engine import catalog_command_point_runtime as provider

    gate = provider.phase_gain_dice_gate(source.clause)
    if gate is None:
        return None
    parameters = parameter_payload(gate.parameters)
    if parameters.get("roll_type") != "leadership":
        return None
    unit_id = rules_unit_id_for_unit_id(
        armies=tuple(context.state.army_definitions),
        unit_instance_id=unit.unit_instance_id,
    )
    return evaluate_leadership_modifiers(
        state=context.state,
        decisions=context.decisions,
        unit_instance_id=unit_id,
        occurrence_id=f"{context.event.event_id}:{source.record.definition.source_id}:{source_model_instance_id}",
        ability_index=ability_index,
        runtime_modifier_registry=context.runtime_modifier_registry,
        model_instance_ids=None
        if parameters.get("test_target") == "this_unit"
        else (source_model_instance_id,),
        roll_model_instance_id=None
        if parameters.get("test_target") == "this_unit"
        else source_model_instance_id,
        roll_modifiers=selected_target_test_roll_modifiers(
            state=context.state,
            unit_instance_id=unit_id,
            roll_type=LEADERSHIP_TEST_ROLL_TYPE,
        ),
        source_context={
            "continuation": "phase",
            "source_kind": "command_point_test",
            "runtime_event_id": context.event.event_id,
            "source_rule_id": source.record.definition.source_id,
            "source_model_instance_id": source_model_instance_id,
        },
    )


def resolve_phase_command_point_gain(
    *,
    context: RuntimeContentEventContext,
    source: _PhaseGainSource,
    unit: UnitInstance,
    source_model_instance_id: str,
    ability_index: AbilityCatalogIndex,
) -> JsonValue:
    from warhammer40k_core.engine import catalog_command_point_runtime as provider

    gate = provider.phase_gain_dice_gate(source.clause)
    evaluation = _leadership_evaluation(
        context=context,
        source=source,
        unit=unit,
        source_model_instance_id=source_model_instance_id,
        ability_index=ability_index,
    )
    if evaluation is not None and evaluation.pending_status is not None:
        raise GameLifecycleError("CP test consumed before its modifier preflight completed.")
    roll_payload: JsonValue = None
    leadership_modified_roll_payload: JsonValue = None
    leadership_target: int | None = None
    success_threshold: int | None = None
    rules_unit_id: str | None = None
    test_kind = "automatic"
    passed = True
    if gate is not None:
        gate_parameters = parameter_payload(gate.parameters)
        roll_count = provider._mapping_positive_int(gate_parameters, key="roll_count")
        if gate_parameters.get("roll_type") == "leadership":
            test_kind = "leadership"
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=tuple(context.state.army_definitions),
                unit_instance_id=unit.unit_instance_id,
            )
            if evaluation is None:
                raise GameLifecycleError("CP Leadership test lacks its modifier evaluation.")
            leadership_target = evaluation.leadership_target
            success_threshold = leadership_target
            roll_type = "catalog_ir.command_point_leadership_test"
            reason = f"Command-point Leadership test for {source_model_instance_id}"
        elif gate_parameters.get("roll_type") == "command_point_gain":
            test_kind = "fixed_roll"
            success_threshold = provider._mapping_positive_int(
                gate_parameters,
                key="success_threshold",
            )
            roll_type = "catalog_ir.command_point_gain_test"
            reason = f"Command-point gain test for {source_model_instance_id}"
        else:
            raise GameLifecycleError("Catalog CP phase gain roll_type is unsupported.")
        roll = DiceRollManager(
            context.state.game_id,
            event_log=context.decisions.event_log,
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=roll_count, sides=6),
                reason=reason,
                roll_type=roll_type,
                actor_id=source_model_instance_id,
            )
        )
        roll_payload = cast(JsonValue, roll.to_payload())
        if test_kind == "leadership":
            if rules_unit_id is None or evaluation is None:
                raise GameLifecycleError("Leadership test requires its modifier evaluation.")
            modified_roll = ModifiedRollResult.from_unmodified(
                UnmodifiedRollResult.from_state(roll),
                modifiers=evaluation.roll_modifiers,
            )
            leadership_modified_roll_payload = cast(JsonValue, modified_roll.to_payload())
            passed = modified_roll.final_value >= success_threshold
        else:
            passed = roll.current_total >= success_threshold
    gain_payload: JsonValue = None
    if passed:
        gain = context.state.gain_command_points(
            player_id=source.owner_player_id,
            amount=provider._command_point_gain_amount(source.clause),
            source_id=source.record.definition.source_id,
            source_kind=CommandPointSourceKind.OTHER,
        )
        gain_payload = cast(JsonValue, gain.to_payload())
        context.decisions.event_log.append(
            "command_points_gained"
            if gain.status is CommandPointGainStatus.APPLIED
            else "command_points_gain_capped",
            gain_payload,
        )
    resolution = validate_json_value(
        {
            "runtime_event_id": context.event.event_id,
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": None if context.event.phase is None else context.event.phase.value,
            "player_id": source.owner_player_id,
            "source_rule_id": source.record.definition.source_id,
            "source_record_id": source.record.record_id,
            "source_clause_id": source.clause.clause_id,
            "source_unit_instance_id": (
                rules_unit_id if rules_unit_id is not None else unit.unit_instance_id
            ),
            "source_model_instance_id": source_model_instance_id,
            "test_kind": test_kind,
            "success_threshold": success_threshold,
            "roll": roll_payload,
            "leadership_target": leadership_target,
            "leadership_roll": roll_payload if test_kind == "leadership" else None,
            "leadership_modified_roll": leadership_modified_roll_payload,
            "passed": passed,
            "command_point_result": gain_payload,
        }
    )
    context.decisions.event_log.append(
        (
            provider.CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
            if clause_is_supported_phase_end_leadership_command_point_gain(source.clause)
            else provider.CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT
        ),
        resolution,
    )
    return resolution
