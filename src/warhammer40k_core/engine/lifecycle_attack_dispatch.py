from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from warhammer40k_core.engine import mortal_wound_model_allocation as _mw_model
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice_result_overrides import (
    DICE_RESULT_OVERRIDE_DECISION_TYPE,
    apply_dice_result_override_decision,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_destruction_selection import (
    apply_retention_selection,
    is_retention_request,
)
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedDestructionStage,
)

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


class FightReactionContinuation(Protocol):
    def __call__(self, *, result: DecisionResult, status: LifecycleStatus) -> None: ...


class ShootingReactionContinuation(Protocol):
    def __call__(
        self, *, result: DecisionResult, status: LifecycleStatus | None
    ) -> LifecycleStatus | None: ...


@dataclass(frozen=True, slots=True)
class AttackDecisionDispatchContext:
    state: GameState
    decisions: DecisionController
    ruleset_descriptor: Callable[[], RulesetDescriptor]
    runtime_modifier_registry: Callable[[], RuntimeModifierRegistry]
    fight_owned: bool
    resolves_reaction_frame: bool
    fight_decision_types: frozenset[str]
    shooting_decision_types: frozenset[str]
    advance: Callable[[], LifecycleStatus]
    apply_fight: Callable[[DecisionRecord, DecisionResult], LifecycleStatus]
    apply_shooting: Callable[[DecisionRecord, DecisionResult], LifecycleStatus]
    apply_mortal_wounds: Callable[[DecisionRecord, DecisionResult], LifecycleStatus]
    continue_fight_reaction: FightReactionContinuation
    continue_shooting_reaction: ShootingReactionContinuation


def apply_attack_sequence_decision(
    context: AttackDecisionDispatchContext,
    record: DecisionRecord,
    result: DecisionResult,
) -> LifecycleStatus:
    state = context.state
    if is_retention_request(record.request):
        retained = apply_retention_selection(
            state=state, decisions=context.decisions, result=result
        )
        if (
            retained.owner_kind is DestructionOwnerKind.RULE
            and retained.stage is RetainedDestructionStage.DECLINED
        ):
            from warhammer40k_core.engine.retained_destruction_rule import (
                resume_retained_rule_destruction,
            )

            status = resume_retained_rule_destruction(
                state=state, decisions=context.decisions, record=retained
            )
            if status is not None:
                return status
        elif (
            retained.owner_kind is DestructionOwnerKind.ATTACK_COLLATERAL
            and retained.stage is RetainedDestructionStage.DECLINED
        ):
            from warhammer40k_core.engine.retained_destruction_dispatch import (
                resume_declined_attack_collateral,
            )

            status = resume_declined_attack_collateral(
                state=state, decisions=context.decisions, record=retained
            )
            if status is not None:
                return status
        return context.advance()
    from warhammer40k_core.engine.retained_destruction_cleanup import (
        active_retained_attack_destruction,
    )

    active_retained = active_retained_attack_destruction(state=state)
    if (
        active_retained is not None
        and record.request.decision_type != DICE_RESULT_OVERRIDE_DECISION_TYPE
    ):
        from warhammer40k_core.engine.retained_destruction_dispatch import (
            apply_retained_attack_destruction_decision,
        )

        status = apply_retained_attack_destruction_decision(
            state=state,
            decisions=context.decisions,
            record=active_retained,
            result=result,
            ruleset_descriptor=context.ruleset_descriptor(),
            runtime_modifier_registry=context.runtime_modifier_registry(),
        )
        return context.advance() if status is None else status
    if record.request.decision_type == DICE_RESULT_OVERRIDE_DECISION_TYPE:
        resolves_reaction_frame = context.resolves_reaction_frame
        fight_owned = context.fight_owned
        apply_dice_result_override_decision(
            state=state,
            decisions=context.decisions,
            request=record.request,
            result=result,
        )
        advanced_status = context.advance()
        if resolves_reaction_frame:
            if fight_owned:
                context.continue_fight_reaction(
                    result=result,
                    status=advanced_status,
                )
            else:
                handled_status = context.continue_shooting_reaction(
                    result=result,
                    status=advanced_status,
                )
                if handled_status is not None:
                    return handled_status
        return advanced_status
    if _mw_model.is_mortal_wound_resolution_request(record.request):
        return context.apply_mortal_wounds(record, result)
    if rule_model_destruction.is_rule_model_destruction_reaction_request(record.request):
        destruction_phase = rule_model_destruction.rule_model_destruction_phase(record.request)
        if destruction_phase is BattlePhase.FIGHT:
            return context.apply_fight(record, result)
        if destruction_phase is BattlePhase.SHOOTING:
            return context.apply_shooting(record, result)
        raise GameLifecycleError("Rule destruction reaction phase has no action host.")
    if record.request.decision_type in context.fight_decision_types and context.fight_owned:
        return context.apply_fight(record, result)
    if record.request.decision_type in context.shooting_decision_types:
        return context.apply_shooting(record, result)
    if record.request.decision_type in context.fight_decision_types:
        return context.apply_fight(record, result)
    raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")
