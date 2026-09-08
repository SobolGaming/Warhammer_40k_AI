from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_model import (
    AttackResolutionContextPayload,
    AttackSequenceHooks,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageApplicationPayload,
    DestructionReactionSource,
    FeelNoPainResolution,
    FeelNoPainResolutionPayload,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_destruction_selection import offer_fight_on_death_retention
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedModelDestruction,
    retained_destruction_for_model,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def offer_attack_collateral_fight_on_death(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    controller_player_id: str,
    sources: tuple[DestructionReactionSource, ...],
    source_damage_completion: JsonValue,
    manager: DiceRollManager,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_sequence_destruction_authority import (
        reserved_attack_damage_destruction_attribution,
    )
    from warhammer40k_core.engine.attack_sequence_hit_wound import (
        _destroyed_model_placement_payload,
    )

    existing = retained_destruction_for_model(
        state=state, model_instance_id=damage.model_instance_id
    )
    if existing is not None:
        return None
    if source_damage_completion is None:
        return None
    attribution = reserved_attack_damage_destruction_attribution(
        state=state,
        attack_sequence=attack_sequence,
        damage=damage,
    )
    placement = ModelPlacement.from_payload(
        cast(
            ModelPlacementPayload,
            _destroyed_model_placement_payload(
                state=state, model_instance_id=damage.model_instance_id
            ),
        )
    )
    return offer_fight_on_death_retention(
        manager=manager,
        state=state,
        decisions=decisions,
        model_instance_id=damage.model_instance_id,
        placement=placement,
        owner_kind=DestructionOwnerKind.ATTACK_COLLATERAL,
        owner_context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "attack_sequence": attack_sequence.to_payload(),
                    "attack_context": attack_context,
                    "damage_application": damage.to_payload(),
                    "saving_throw_payload": saving_throw_payload,
                    "feel_no_pain": feel_no_pain.to_payload(),
                    "controller_player_id": controller_player_id,
                    "source_damage_completion": source_damage_completion,
                }
            ),
        ),
        sources=sources,
        provenance=attribution.destruction_provenance,
    )


def resume_retained_attack_collateral(
    *,
    state: GameState,
    decisions: DecisionController,
    record: RetainedModelDestruction,
    attack_sequence: AttackSequence,
) -> tuple[AttackSequence | None, LifecycleStatus | None]:
    from warhammer40k_core.engine.attack_sequence_damage_resolution import (
        _finish_resumed_deadly_demise_source_damage,
    )

    if record.owner_kind is not DestructionOwnerKind.ATTACK_COLLATERAL:
        raise GameLifecycleError("Retained collateral continuation kind drift.")
    context = record.owner_context
    damage = DamageApplication.from_payload(
        cast(DamageApplicationPayload, context["damage_application"])
    )
    feel_no_pain = FeelNoPainResolution.from_payload(
        cast(FeelNoPainResolutionPayload, context["feel_no_pain"])
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    from warhammer40k_core.engine.attack_destruction_reactions import (
        resolve_mandatory_destruction_reactions_before_removal,
    )

    status = resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=cast(AttackResolutionContextPayload, context["attack_context"]),
        damage=damage,
        saving_throw_payload=context["saving_throw_payload"],
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=record.placement.player_id,
        sources=record.sources,
        parent_cause_ids=tuple(
            cause
            for authority in state.model_destruction_cause_authorities
            if authority.cause_id == record.cause_id
            for cause in authority.parent_cause_ids
        ),
        source_damage_completion=context["source_damage_completion"],
    )
    if status is not None:
        return attack_sequence, status
    sequence, _allocated, status = _finish_resumed_deadly_demise_source_damage(
        state=state,
        decisions=decisions,
        manager=manager,
        hooks=AttackSequenceHooks.empty(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        attack_context=cast(AttackResolutionContextPayload, context["attack_context"]),
        damage=damage,
        saving_throw_payload=context["saving_throw_payload"],
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=record.placement.player_id,
        source_damage_completion=context["source_damage_completion"],
    )
    return sequence, status
