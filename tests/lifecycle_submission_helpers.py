from __future__ import annotations

import json
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    apply_damage_allocation_model_decision,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import LifecycleStatus


def battle_lifecycle_payload(
    *,
    state: GameState,
    decisions: DecisionController,
) -> GameLifecyclePayload:
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def apply_pending_damage_allocation(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence | None,
    status: LifecycleStatus | None,
    already_allocated_model_ids: tuple[str, ...],
    dice_manager: DiceRollManager,
    selected_model_id: str,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if attack_sequence is None or status is None or status.decision_request is None:
        raise AssertionError("Expected a pending grouped-damage allocation decision.")
    request = status.decision_request
    if request.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        raise AssertionError("Expected a damage-allocation model decision.")
    result = DecisionResult.for_request(
        result_id=f"result:test-damage-allocation:{selected_model_id}",
        request=request,
        selected_option_id=selected_model_id,
    )
    decisions.submit_result(result)
    return apply_damage_allocation_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=attack_sequence,
        result=result,
        already_allocated_model_ids=already_allocated_model_ids,
        dice_manager=dice_manager,
    )
