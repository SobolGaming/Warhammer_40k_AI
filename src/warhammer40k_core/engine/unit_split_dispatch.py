"""Split choices use the lifecycle's shared pre-validation and mutation dispatch."""

from __future__ import annotations

from typing import Protocol

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.unit_split_decisions import SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE
from warhammer40k_core.engine.unit_split_runtime import (
    apply_unit_split_decision,
    next_unit_split_request,
    preview_unit_split_decision,
)


class UnitSplitLifecycleHost(Protocol):
    decision_controller: DecisionController

    def _require_state(self) -> GameState: ...

    def advance_until_decision_or_terminal(self) -> LifecycleStatus: ...


def decision_dispatch_handlers(host: UnitSplitLifecycleHost) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validator(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        state = host._require_state()  # pyright: ignore[reportPrivateUsage]
        try:
            expected = next_unit_split_request(state=state, decisions=host.decision_controller)
            if request != expected:
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Unit split pending request drift.",
                    payload={"reason": "invalid_unit_split"},
                )
            result.validate_for_request(request)
            preview_unit_split_decision(
                state=state,
                records=(
                    *host.decision_controller.records,
                    DecisionRecord("split-validation", request, result),
                ),
            )
        except (GameLifecycleError, DecisionError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage, message=str(exc), payload={"reason": "invalid_unit_split"}
            )
        return None

    def applier(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        apply_unit_split_decision(
            state=host._require_state(),  # pyright: ignore[reportPrivateUsage]
            decisions=host.decision_controller,
        )
        return host.advance_until_decision_or_terminal()

    return (
        DecisionDispatchHandler(
            decision_type=SELECT_UNIT_SPLIT_MEMBERSHIP_DECISION_TYPE,
            pre_validator=pre_validator,
            applier=applier,
        ),
    )
