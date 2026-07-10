from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.command_points import (
    CommandPointLedger,
    CommandPointSourceKind,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleEffectSpec, parameter_payload


@dataclass(frozen=True, slots=True)
class CommandPointRuleMutationResult:
    transaction_payload: dict[str, JsonValue] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.transaction_payload is None) == (self.reason is None):
            raise GameLifecycleError(
                "Command-point rule mutation requires exactly one payload or reason."
            )


def command_point_operation_and_delta(effect: RuleEffectSpec) -> tuple[str, int]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Command-point rule execution requires RuleEffectSpec.")
    parameters = parameter_payload(effect.parameters)
    operation = parameters.get("operation")
    delta = parameters.get("delta")
    if type(operation) is not str:
        raise GameLifecycleError("Command-point operation must be a string.")
    if type(delta) is not int:
        raise GameLifecycleError("Command-point delta must be an integer.")
    return operation, delta


def apply_command_point_rule_mutation(
    *,
    state: GameState,
    player_id: str,
    source_id: str,
    operation: str,
    delta: int,
) -> CommandPointRuleMutationResult:
    reason = command_point_operation_shape_reason(operation=operation, delta=delta)
    if reason is not None:
        return CommandPointRuleMutationResult(reason=reason)
    if operation == "gain":
        gain_result = state.gain_command_points(
            player_id=player_id,
            amount=delta,
            source_id=source_id,
            source_kind=CommandPointSourceKind.OTHER,
        )
        if gain_result.applied_amount == 0:
            return CommandPointRuleMutationResult(reason="command_point_gain_capped")
        transaction_payload = _json_object(gain_result.to_payload())
    elif operation == "refund":
        refund_result = state.refund_command_points(
            player_id=player_id,
            amount=delta,
            source_id=source_id,
        )
        if refund_result.applied_amount == 0:
            return CommandPointRuleMutationResult(reason="command_point_refund_capped")
        transaction_payload = _json_object(refund_result.to_payload())
    elif operation == "spend":
        spend_result = state.spend_command_points(
            player_id=player_id,
            amount=abs(delta),
            source_id=source_id,
        )
        if spend_result.status is not CommandPointSpendStatus.APPLIED:
            return CommandPointRuleMutationResult(reason="insufficient_command_points")
        transaction_payload = _json_object(spend_result.to_payload())
    else:
        raise GameLifecycleError("Validated command-point operation is unsupported.")
    return CommandPointRuleMutationResult(transaction_payload=transaction_payload)


def command_point_rule_unavailable_reason(
    *,
    state: GameState,
    player_id: str,
    source_id: str,
    operation: str,
    delta: int,
    simulated_ledgers: dict[str, CommandPointLedger],
) -> str | None:
    reason = command_point_operation_shape_reason(operation=operation, delta=delta)
    if reason is not None:
        return reason
    ledger = simulated_ledgers.get(player_id, state.command_point_ledger_for_player(player_id))
    if operation == "gain":
        updated_ledger, gain_result = ledger.gain(
            battle_round=state.battle_round,
            amount=delta,
            source_id=source_id,
            source_kind=CommandPointSourceKind.OTHER,
        )
        if gain_result.applied_amount == 0:
            return "command_point_gain_capped"
        simulated_ledgers[player_id] = updated_ledger
        return None
    if operation == "refund":
        updated_ledger, refund_result = ledger.refund(
            battle_round=state.battle_round,
            amount=delta,
            source_id=source_id,
        )
        if refund_result.applied_amount == 0:
            return "command_point_refund_capped"
        simulated_ledgers[player_id] = updated_ledger
        return None
    if operation == "spend":
        updated_ledger, spend_result = ledger.spend(
            battle_round=state.battle_round,
            amount=abs(delta),
            source_id=source_id,
        )
        if spend_result.status is not CommandPointSpendStatus.APPLIED:
            return "insufficient_command_points"
        simulated_ledgers[player_id] = updated_ledger
        return None
    raise GameLifecycleError("Validated command-point operation is unsupported.")


def command_point_operation_shape_reason(*, operation: str, delta: int) -> str | None:
    if delta == 0:
        return "zero_command_point_delta"
    if operation == "modify_stratagem_cost":
        return "stratagem_cost_context_required"
    if operation == "gain":
        return None if delta > 0 else "invalid_command_point_gain_delta"
    if operation == "refund":
        return None if delta > 0 else "invalid_command_point_refund_delta"
    if operation == "spend":
        return None if delta < 0 else "invalid_command_point_spend_delta"
    return f"unsupported_command_point_operation:{operation}"


def _json_object(value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Command-point transaction payload must be an object.")
    return payload
