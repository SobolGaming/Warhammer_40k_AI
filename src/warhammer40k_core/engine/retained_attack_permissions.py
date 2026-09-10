"""Source-authorized alternatives for one retained destruction entitlement."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_reaction_kind import DestructionReactionKind
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import DestructionReactionSource


class RetainedAttackAction(StrEnum):
    SHOOT = "shoot"
    FIGHT = "fight"


RETAINED_ATTACK_REACTION_KINDS = frozenset(
    (
        DestructionReactionKind.SHOOT_ON_DEATH,
        DestructionReactionKind.FIGHT_ON_DEATH,
        DestructionReactionKind.SHOOT_OR_FIGHT_ON_DEATH,
    )
)


def retained_attack_actions(source: DestructionReactionSource) -> tuple[RetainedAttackAction, ...]:
    if source.reaction_kind is DestructionReactionKind.SHOOT_ON_DEATH:
        return (RetainedAttackAction.SHOOT,)
    if source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH:
        return (RetainedAttackAction.FIGHT,)
    if source.reaction_kind is DestructionReactionKind.SHOOT_OR_FIGHT_ON_DEATH:
        return (RetainedAttackAction.SHOOT, RetainedAttackAction.FIGHT)
    raise GameLifecycleError("Destruction source does not grant a retained attack.")


def retained_attack_options(
    sources: tuple[DestructionReactionSource, ...],
    *,
    excluded_actions: tuple[RetainedAttackAction, ...] = (),
) -> tuple[DecisionOption, ...]:
    from warhammer40k_core.engine.damage_allocation import DECLINE_DESTRUCTION_REACTION_OPTION_ID

    options = [
        DecisionOption(
            option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
            label="Decline Destruction Reaction",
            payload={"source_id": None, "reaction_kind": None, "action": None},
        )
    ]
    for source in sources:
        actions = retained_attack_actions(source)
        for action in actions:
            if action in excluded_actions:
                continue
            options.append(
                DecisionOption(
                    option_id=source.source_id
                    if len(actions) == 1
                    else f"{source.source_id}:{action.value}",
                    label=f"{source.source_id}: {action.value}",
                    payload={
                        "source_id": source.source_id,
                        "reaction_kind": source.reaction_kind.value,
                        "optional": source.optional,
                        "action": action.value,
                    },
                )
            )
    return tuple(options)


def retained_attack_selection(
    *, request: DecisionRequest, result: DecisionResult
) -> tuple[str | None, RetainedAttackAction | None]:
    result.validate_for_request(request)
    payload = request.option_by_id(result.selected_option_id).payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Retained attack option requires source and action authority.")
    source_id, action = payload.get("source_id"), payload.get("action")
    if source_id is None and action is None:
        return None, None
    if type(source_id) is not str or not source_id or type(action) is not str:
        raise GameLifecycleError("Retained attack option source or action is invalid.")
    try:
        return source_id, RetainedAttackAction(action)
    except ValueError as exc:
        raise GameLifecycleError("Retained attack action is unsupported.") from exc
