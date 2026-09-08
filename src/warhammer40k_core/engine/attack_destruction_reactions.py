from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import attack_sequence_destruction_authority as _asda
from warhammer40k_core.engine.attack_sequence_model import AttackResolutionContextPayload
from warhammer40k_core.engine.attack_sequence_validation import _state_destruction_reaction_sources
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainResolution,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(GameLifecycleError)


def resolve_mandatory_destruction_reactions_before_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str | None = None,
    sources: tuple[DestructionReactionSource, ...] | None = None,
    parent_cause_ids: tuple[str, ...] = (),
    source_damage_completion: JsonValue = None,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_sequence_damage_resolution import (
        _emit_mandatory_destruction_reaction_record,
        _resolve_deadly_demise_before_removal,
    )
    from warhammer40k_core.engine.retained_destruction_attack import (
        offer_attack_collateral_fight_on_death,
    )

    if damage is None or not damage.destroyed:
        return None
    _asda.reserve_destroyed_attack_damage_authority(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        damage=damage,
        parent_cause_ids=parent_cause_ids,
    )
    controller_player_id = (
        attack_context["defender_player_id"]
        if destroyed_model_controller_player_id is None
        else _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        )
    )
    active_sources = (
        _state_destruction_reaction_sources(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
        if sources is None
        else sources
    )
    retention_status = offer_attack_collateral_fight_on_death(
        manager=manager,
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        controller_player_id=controller_player_id,
        sources=active_sources,
        source_damage_completion=source_damage_completion,
    )
    if retention_status is not None:
        return retention_status
    mandatory_sources = tuple(source for source in active_sources if not source.optional)
    for source_index, source in enumerate(mandatory_sources):
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
            status = _resolve_deadly_demise_before_removal(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=attack_sequence,
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                destroyed_model_controller_player_id=controller_player_id,
                pending_sources=mandatory_sources[source_index + 1 :],
                source_damage_completion=source_damage_completion,
            )
            if status is not None:
                return status
            continue
        _emit_mandatory_destruction_reaction_record(
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            destroyed_model_controller_player_id=controller_player_id,
            execution_status="recorded_for_action_host",
        )
    return None
