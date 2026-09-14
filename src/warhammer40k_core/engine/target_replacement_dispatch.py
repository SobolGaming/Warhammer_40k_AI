"""Replacement submissions use the same lifecycle preflight as every other choice."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine import charge_target_dispatch
from warhammer40k_core.engine.charge_target_continuation import is_charge_target_replacement_request
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.shooting_target_replacement import (
    active_shooting_sequence,
    next_shooting_target_replacement,
    replace_active_shooting_sequence,
)
from warhammer40k_core.engine.target_replacement import (
    SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
    replacement_selection,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def decision_dispatch_handlers(host: GameLifecycle) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validator(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        state = host._require_state()  # pyright: ignore[reportPrivateUsage]
        if is_charge_target_replacement_request(state=state, request=request):
            return charge_target_dispatch.validate_charge_replacement(host, request, result)
        try:
            current = next_shooting_target_replacement(
                handler=host._shooting_phase_handler,  # pyright: ignore[reportPrivateUsage]
                state=state,
                decisions=host.decision_controller,
                sequence=active_shooting_sequence(state),
            )
            if current is None:
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Target replacement is no longer available.",
                    payload={"invalid_reason": "target_replacement_context_drift"},
                )
            replacement_selection(request=request, result=result, current=current.context)
        except (GameLifecycleError, DecisionError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={"invalid_reason": "target_replacement_context_drift"},
            )
        return None

    def applier(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        state = host._require_state()  # pyright: ignore[reportPrivateUsage]
        if is_charge_target_replacement_request(state=state, request=record.request):
            return charge_target_dispatch.apply_charge_replacement(host, record, result)
        sequence = active_shooting_sequence(state)
        current = next_shooting_target_replacement(
            handler=host._shooting_phase_handler,  # pyright: ignore[reportPrivateUsage]
            state=state,
            decisions=host.decision_controller,
            sequence=sequence,
        )
        if current is None:
            raise GameLifecycleError("Prevalidated replacement disappeared.")
        target_ids = replacement_selection(
            request=record.request, result=result, current=current.context
        )
        replacements = (
            {} if target_ids is None else current.pools_by_option_id[result.selected_option_id]
        )
        pools = list(sequence.attack_pools)
        for index, pool in replacements.items():
            pools[index] = pool
        forgone = tuple(index for index in current.pool_indices if index not in replacements)
        used_indices = tuple(sorted((*sequence.used_pool_indices, *forgone)))
        remaining_indices = tuple(i for i in range(len(pools)) if i not in used_indices)
        updated = replace(
            sequence,
            pool_index=remaining_indices[0] if remaining_indices else len(pools),
            attack_pools=tuple(pools),
            used_pool_indices=used_indices,
            selected_target_unit_instance_id=None,
        )
        replace_active_shooting_sequence(state, updated)
        host.decision_controller.event_log.append(
            "target_replacement_resolved",
            {
                "context": current.context.to_payload(),
                "source_decision_request_id": result.request_id,
                "source_decision_result_id": result.result_id,
                "replacement_target_ids": None if target_ids is None else list(target_ids),
                "attack_pools": [pool.to_payload() for pool in updated.attack_pools],
                "used_pool_indices": list(updated.used_pool_indices),
                "pool_indices": list(current.pool_indices),
                "forgone_pool_indices": list(forgone),
            },
        )
        return host.advance_until_decision_or_terminal()

    return (
        *charge_target_dispatch.decision_dispatch_handlers(host),
        DecisionDispatchHandler(
            decision_type=SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
            pre_validator=pre_validator,
            applier=applier,
        ),
    )
