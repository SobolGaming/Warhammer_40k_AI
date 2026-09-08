from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.damage_allocation import DestructionReactionKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_destruction_selection import offer_fight_on_death_retention
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedDestructionStage,
    RetainedModelDestruction,
)
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    destruction_provenance_from_rule_context,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def offer_rule_fight_on_death(
    *, state: GameState, decisions: DecisionController, root_context: dict[str, JsonValue]
) -> LifecycleStatus | None:
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    placement = ModelPlacement.from_payload(
        cast(ModelPlacementPayload, root_context["destroyed_model_placement"])
    )
    return offer_fight_on_death_retention(
        manager=manager,
        state=state,
        decisions=decisions,
        model_instance_id=placement.model_instance_id,
        placement=placement,
        owner_kind=DestructionOwnerKind.RULE,
        owner_context=root_context,
        sources=state.destruction_reaction_sources_for_model(
            model_instance_id=placement.model_instance_id
        ),
        provenance=destruction_provenance_from_rule_context(root_context),
    )


def resume_retained_rule_destruction(
    *, state: GameState, decisions: DecisionController, record: RetainedModelDestruction
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.rule_model_destruction import (
        continue_rule_deadly_demise_sources,
        remove_rule_destroyed_model_and_continue,
    )

    if record.owner_kind is not DestructionOwnerKind.RULE or record.stage not in (
        RetainedDestructionStage.RESOLVING,
        RetainedDestructionStage.DECLINED,
    ):
        raise GameLifecycleError("Retained rule destruction continuation is not ready.")
    status = continue_rule_deadly_demise_sources(
        state=state,
        decisions=decisions,
        root_context=record.owner_context,
        sources=tuple(
            source
            for source in record.sources
            if not source.optional and source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
        ),
    )
    if status is not None:
        return status
    return remove_rule_destroyed_model_and_continue(
        state=state,
        decisions=decisions,
        root_context=record.owner_context,
    ).status
