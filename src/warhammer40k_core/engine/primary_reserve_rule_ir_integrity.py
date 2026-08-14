from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    parameter_payload,
)

__all__ = [
    "ValidatedPrimaryReserveRuleIRPlacementEffect",
    "expected_primary_reserve_stratagem_rule_execution_context",
    "validate_exact_primary_reserve_rule_ir_placement_effect",
]

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import (
        StratagemEligibilityContext,
        StratagemUseRecord,
    )


@dataclass(frozen=True, slots=True)
class ValidatedPrimaryReserveRuleIRPlacementEffect:
    parameters: dict[str, JsonValue]
    target_unit_instance_ids: tuple[str, ...]


def expected_primary_reserve_stratagem_rule_execution_context(
    *,
    state: GameState,
    use: StratagemUseRecord,
    eligibility_context: StratagemEligibilityContext,
    target_player_id: str | None,
    target_unit_instance_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    """Reconstruct the exact generic Stratagem execution context from authority."""
    trigger_payload: dict[str, JsonValue] = {}
    if isinstance(eligibility_context.trigger_payload, dict):
        trigger_payload.update(
            cast(dict[str, JsonValue], validate_json_value(eligibility_context.trigger_payload))
        )
    elif eligibility_context.trigger_payload is not None:
        trigger_payload["source_trigger_payload"] = eligibility_context.trigger_payload
    trigger_payload.update(
        {
            "stratagem_id": use.stratagem_id,
            "stratagem_use_id": use.use_id,
            "effect_selection": use.effect_selection,
            "stratagem_context": validate_json_value(eligibility_context.to_payload()),
        }
    )
    return {
        "game_id": state.game_id,
        "player_id": use.player_id,
        "battle_round": use.battle_round,
        "phase": use.phase.value,
        "active_player_id": use.active_player_id,
        "timing_window_id": use.timing_window_id,
        "source_unit_instance_id": (
            use.targeted_unit_instance_ids[0] if len(use.targeted_unit_instance_ids) == 1 else None
        ),
        "source_model_instance_id": None,
        "target_unit_instance_ids": list(target_unit_instance_ids),
        "target_player_id": target_player_id,
        "source_keywords": [],
        "trigger_payload": trigger_payload,
        "record_persisting_effects": True,
    }


def validate_exact_primary_reserve_rule_ir_placement_effect(
    *,
    rule_ir: RuleIR,
    executed_effect_payload: JsonValue,
) -> ValidatedPrimaryReserveRuleIRPlacementEffect:
    """Bind carried reserve evidence to one immutable RuleIR effect slot."""
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Primary reserve RuleIR authority requires a RuleIR.")
    if not isinstance(executed_effect_payload, dict):
        raise GameLifecycleError("Primary reserve RuleIR effect must be an object.")
    effect_payload = executed_effect_payload
    clause_id = effect_payload.get("clause_id")
    effect_index = effect_payload.get("effect_index")
    matching_clauses = tuple(clause for clause in rule_ir.clauses if clause.clause_id == clause_id)
    if len(matching_clauses) != 1 or type(effect_index) is not int:
        raise GameLifecycleError("Primary reserve RuleIR effect identity drift.")
    clause = matching_clauses[0]
    if not 0 <= effect_index < len(clause.effects):
        raise GameLifecycleError("Primary reserve RuleIR effect index drift.")
    effect = clause.effects[effect_index]
    expected_conditions = validate_json_value(
        [condition.to_payload() for condition in clause.conditions]
    )
    expected_keys = {
        "effect_kind",
        "rule_id",
        "source_id",
        "rule_ir_hash",
        "clause_id",
        "effect_index",
        "source_span",
        "target",
        "target_unit_instance_ids",
        "duration",
        "effect",
        "context",
    }
    if clause.conditions:
        expected_keys.add("conditions")
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    raw_context = effect_payload.get("context")
    if (
        set(effect_payload) != expected_keys
        or effect.kind is not RuleEffectKind.PLACEMENT_PERMISSION
        or effect_payload.get("effect_kind") != "generic_rule_execution"
        or effect_payload.get("rule_id") != rule_ir.rule_id
        or effect_payload.get("source_id") != rule_ir.source_id
        or effect_payload.get("rule_ir_hash") != rule_ir.ir_hash()
        or effect_payload.get("source_span") != clause.source_span.to_payload()
        or effect_payload.get("target")
        != (None if clause.target is None else clause.target.to_payload())
        or effect_payload.get("duration")
        != (None if clause.duration is None else clause.duration.to_payload())
        or effect_payload.get("effect") != effect.to_payload()
        or effect_payload.get("conditions", []) != expected_conditions
        or not isinstance(raw_target_ids, list)
        or not isinstance(raw_context, dict)
    ):
        raise GameLifecycleError("Primary reserve RuleIR effect descriptor drift.")
    target_ids = tuple(
        target_id
        for target_id in cast(list[object], raw_target_ids)
        if type(target_id) is str and target_id.strip()
    )
    if len(target_ids) != len(raw_target_ids) or not target_ids:
        raise GameLifecycleError("Primary reserve RuleIR effect targets are malformed.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Primary reserve RuleIR effect targets are duplicated.")
    raw_parameters = validate_json_value(parameter_payload(effect.parameters))
    if not isinstance(raw_parameters, dict):
        raise GameLifecycleError("Primary reserve RuleIR parameters are malformed.")
    return ValidatedPrimaryReserveRuleIRPlacementEffect(
        parameters=raw_parameters,
        target_unit_instance_ids=target_ids,
    )
