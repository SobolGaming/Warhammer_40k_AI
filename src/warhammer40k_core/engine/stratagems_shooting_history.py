"""Source-provider proof for the existing Stratagem shooting executors."""

from __future__ import annotations

from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState
from warhammer40k_core.engine.stratagem_use_history_authority import (
    FiniteStratagemUseHistoryAuthority,
    StratagemUseHistoryAuthority,
)
from warhammer40k_core.engine.stratagems_model import (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
)


def validate_stratagem_shooting_permission(
    *,
    shooting: OutOfPhaseShootingState,
    authority: StratagemUseHistoryAuthority | FiniteStratagemUseHistoryAuthority,
    preceding_events: tuple[EventRecord, ...],
) -> None:
    use = authority.use_record
    context = (
        authority.context
        if isinstance(authority, FiniteStratagemUseHistoryAuthority)
        else authority.submitted_proposal.context
    )
    expected: dict[str, JsonValue]
    if use.handler_id == CORE_FIRE_OVERWATCH_HANDLER_ID:
        expected = {
            "source_kind": "fire_overwatch",
            "stratagem_use": validate_json_value(use.to_payload()),
            "trigger_kind": context.trigger_kind.value,
            "trigger_payload": context.trigger_payload,
        }
        if shooting.source_rule_id != use.handler_id or shooting.target_unit_ids is not None:
            raise GameLifecycleError("Fire Overwatch shooting scope source drift.")
    elif use.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload
        from warhammer40k_core.engine.stratagems_generic_rule_ir import (
            _just_shot_unit_id_or_none,  # pyright: ignore[reportPrivateUsage]
            _rule_execution_result_grants_out_of_phase_shoot,  # pyright: ignore[reportPrivateUsage]
        )

        rule_ir = scoped_rule_ir_from_execution_payload(use.effect_payload)
        effects = tuple(
            event.payload
            for event in preceding_events
            if event.event_type == "rule_execution_effect_applied"
            and isinstance(event.payload, dict)
            and event.payload.get("rule_ir_hash") == rule_ir.ir_hash()
            and event.payload.get("source_id") == use.source_id
            and isinstance(effect_context := event.payload.get("context"), dict)
            and effect_context.get("player_id") == use.player_id
            and effect_context.get("source_unit_instance_id") == shooting.selected_unit_instance_id
        )
        target = _just_shot_unit_id_or_none(context)
        if (
            target is None
            or shooting.target_unit_ids != (target,)
            or shooting.source_rule_id != use.source_id
            or not _rule_execution_result_grants_out_of_phase_shoot(effects)
        ):
            raise GameLifecycleError("Stratagem shooting lacks its executed RuleIR permission.")
        expected = {
            "source_kind": "generic_rule_ir_stratagem",
            "stratagem_use": validate_json_value(use.to_payload()),
            "stratagem_context": validate_json_value(context.to_payload()),
            "trigger_kind": context.trigger_kind.value,
            "trigger_payload": context.trigger_payload,
            "target_unit_ids": [target],
        }
    else:
        raise GameLifecycleError("Stratagem source does not authorize out-of-phase shooting.")
    if shooting.source_context != expected:
        raise GameLifecycleError("Stratagem shooting source context drift.")
