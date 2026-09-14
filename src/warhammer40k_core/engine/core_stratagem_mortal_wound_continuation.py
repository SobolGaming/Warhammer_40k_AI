from __future__ import annotations

from typing import Literal

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.stratagems_effect_handlers import (
    apply_crushing_impact_mortal_wound_decision,
    apply_explosives_mortal_wound_feel_no_pain_decision,
    complete_crushing_impact_mortal_wounds,
    complete_explosives_mortal_wounds,
)

_CRUSHING_IMPACT_SOURCE_KINDS = frozenset({"crushing_impact_self", "crushing_impact_enemy"})


def core_stratagem_mortal_wound_bindings() -> tuple[
    MortalWoundFeelNoPainContinuationHookBinding, ...
]:
    return tuple(
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id=f"core-stratagem:{source_kind}:mortal-wound-continuation",
            source_id=source_id,
            source_kind=source_kind,
            handler=_apply_registered_decision,
            completion_handler=completion,
        )
        for source_kind, source_id, completion in (
            (
                "crushing_impact_self",
                "gw-11e-core-stratagems:core:crushing-impact",
                complete_crushing_impact_mortal_wounds,
            ),
            (
                "crushing_impact_enemy",
                "gw-11e-core-stratagems:core:crushing-impact",
                complete_crushing_impact_mortal_wounds,
            ),
            (
                "explosives",
                "gw-11e-core-stratagems:core:explosives",
                complete_explosives_mortal_wounds,
            ),
        )
    )


def _apply_registered_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    status = apply_core_stratagem_mortal_wound_decision_if_applicable(
        state=context.state,
        decisions=context.decisions,
        result=context.result,
        source_context=context.source_context,
    )
    if status is False:
        raise GameLifecycleError("Core Stratagem mortal wound provider identity drifted.")
    return status


def apply_core_stratagem_mortal_wound_decision_if_applicable(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    source_context: JsonValue,
) -> LifecycleStatus | None | Literal[False]:
    if not isinstance(source_context, dict):
        return False
    source_kind = source_context.get("source_kind")
    if source_kind in _CRUSHING_IMPACT_SOURCE_KINDS:
        return apply_crushing_impact_mortal_wound_decision(
            state=state,
            decisions=decisions,
            result=result,
        )
    if source_kind == "explosives":
        return apply_explosives_mortal_wound_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            result=result,
        )
    return False
