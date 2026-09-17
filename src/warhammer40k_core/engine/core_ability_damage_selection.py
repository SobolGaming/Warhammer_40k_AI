"""Controlling-player source choices before mandatory Deadly Demise execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.ability_instance_selection import DUPLICATED_ABILITIES_SOURCE_ID
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    DamageApplication,
    DamageApplicationPayload,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionReactionSourcePayload,
    FeelNoPainResolution,
    FeelNoPainResolutionPayload,
    model_owner_player_id,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.attack_sequence_model import (
        AttackResolutionContextPayload,
        AttackSequenceHooks,
    )
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

_SELECTION_KIND = "duplicated_deadly_demise_instance"


def deadly_demise_sources(
    sources: tuple[DestructionReactionSource, ...],
) -> tuple[DestructionReactionSource, ...]:
    return tuple(
        sorted(
            (
                source
                for source in sources
                if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
            ),
            key=lambda source: source.source_id,
        )
    )


def build_deadly_demise_instance_request(
    *,
    request_id: str,
    player_id: str,
    context: dict[str, JsonValue],
    sources: tuple[DestructionReactionSource, ...],
) -> DecisionRequest:
    if len(sources) < 2 or deadly_demise_sources(sources) != sources:
        raise GameLifecycleError("Duplicated Deadly Demise requires its complete sorted inventory.")
    if any(source.optional for source in sources) or len(
        {source.source_id for source in sources}
    ) != len(sources):
        raise GameLifecycleError("Duplicated Deadly Demise requires distinct mandatory sources.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        actor_id=player_id,
        payload=validate_json_value(
            {
                "selection_kind": _SELECTION_KIND,
                "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                "destruction_context": context,
                "sources": [source.to_payload() for source in sources],
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=source.source_id,
                label=source.source_id,
                payload={
                    "source_id": source.source_id,
                    "reaction_kind": source.reaction_kind.value,
                    "optional": False,
                },
            )
            for source in sources
        ),
    )


def is_deadly_demise_instance_request(request: DecisionRequest) -> bool:
    return (
        request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        and isinstance(request.payload, dict)
        and request.payload.get("selection_kind") == _SELECTION_KIND
    )


def request_deadly_demise_instance_if_duplicated(
    *,
    state: GameState,
    decisions: DecisionController,
    context: dict[str, JsonValue],
    sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    instances = deadly_demise_sources(sources)
    if len(instances) < 2:
        return None
    model_id = _string(context, "model_instance_id")
    request = build_deadly_demise_instance_request(
        request_id=state.next_decision_request_id(),
        player_id=model_owner_player_id(state=state, model_instance_id=model_id),
        context=context,
        sources=instances,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(stage=state.stage, decision_request=request)


def validate_deadly_demise_instance_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> None:
    from warhammer40k_core.engine import lifecycle_state_queries as _lsq
    from warhammer40k_core.engine.attack_sequence_validation import (
        _validate_attack_context_matches_sequence,
    )

    if not is_deadly_demise_instance_request(request):
        raise GameLifecycleError("Deadly Demise instance request kind drift.")
    context = _context(request)
    model_id = _string(context, "model_instance_id")
    sources = deadly_demise_sources(
        state.destruction_reaction_sources_for_model(model_instance_id=model_id)
    )
    player_id = model_owner_player_id(state=state, model_instance_id=model_id)
    expected = build_deadly_demise_instance_request(
        request_id=request.request_id,
        player_id=player_id,
        context=context,
        sources=sources,
    )
    if expected != request:
        raise GameLifecycleError("Deadly Demise instance source inventory or controller drift.")
    if context.get("destroyed_model_controller_player_id") != player_id:
        raise GameLifecycleError("Deadly Demise instance context controller drift.")
    if context.get("context_kind") == "attack_sequence_model_destroyed_pre_removal":
        sequence = _lsq.active_attack_sequence_for_state(state)
        if sequence is None:
            raise GameLifecycleError("Deadly Demise instance choice requires its active attack.")
        attack_context = cast(
            "AttackResolutionContextPayload", _object(context.get("attack_context"))
        )
        _validate_attack_context_matches_sequence(
            attack_sequence=sequence,
            attack_context=attack_context,
            context_name="Deadly Demise instance",
        )
        damage = DamageApplication.from_payload(
            cast(DamageApplicationPayload, _object(context.get("damage_application")))
        )
        if damage.model_instance_id != model_id or not damage.destroyed:
            raise GameLifecycleError("Deadly Demise instance damage context drift.")
        from warhammer40k_core.engine.attack_sequence_destruction_authority import (
            reserved_attack_damage_destruction_attribution,
        )

        reserved_attack_damage_destruction_attribution(
            state=state, attack_sequence=sequence, damage=damage
        )
    elif context.get("context_kind") == "rule_model_destroyed":
        # Request validation is read-only: the cause was reserved before the
        # source choice. Resolve its existing identity instead of reserving again.
        from warhammer40k_core.engine.model_destruction_cause_producers import (
            rule_effect_model_destruction_cause_id,
        )
        from warhammer40k_core.engine.rule_model_destruction import (
            _validate_pre_removal_context_matches_state,
        )

        _validate_pre_removal_context_matches_state(state=state, context=context)
        cause_id = rule_effect_model_destruction_cause_id(state=state, root_context=context)
        if not any(
            cause.cause_id == cause_id for cause in state.model_destruction_cause_authorities
        ):
            raise GameLifecycleError("Deadly Demise instance choice has no reserved destruction.")
    else:
        raise GameLifecycleError("Deadly Demise instance destruction context is unsupported.")


def pending_deadly_demise_instance_cause_id(*, state: GameState, request: DecisionRequest) -> str:
    """Authenticate the source-choice pause as a pending destruction continuation."""
    from warhammer40k_core.engine.model_destruction_cause_producers import (
        attack_damage_model_destruction_cause_id_for_context,
        rule_effect_model_destruction_cause_id,
    )

    validate_deadly_demise_instance_request(state=state, request=request)
    context = _context(request)
    if context["context_kind"] == "rule_model_destroyed":
        return rule_effect_model_destruction_cause_id(state=state, root_context=context)
    attack_context = _object(context["attack_context"])
    return attack_damage_model_destruction_cause_id_for_context(
        state=state,
        sequence_id=_string(attack_context, "sequence_id"),
        attack_context_id=_string(attack_context, "attack_context_id"),
        model_instance_id=_string(context, "model_instance_id"),
    )


def invalid_deadly_demise_instance_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    result.validate_for_request(request)
    try:
        validate_deadly_demise_instance_request(state=state, request=request)
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "core_ability_instance_inventory_drift"},
        )
    return None


def selected_deadly_demise_instance(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> tuple[dict[str, JsonValue], DestructionReactionSource]:
    request = decisions.record_for_result(result).request
    validate_deadly_demise_instance_request(state=state, request=request)
    payload = _object(request.payload)
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise GameLifecycleError("Deadly Demise instance sources must be a list.")
    sources = tuple(
        DestructionReactionSource.from_payload(
            cast(DestructionReactionSourcePayload, _object(source))
        )
        for source in raw_sources
    )
    selected = tuple(source for source in sources if source.source_id == result.selected_option_id)
    if len(selected) != 1:
        raise GameLifecycleError("Deadly Demise requires exactly one active source instance.")
    context = _context(request)
    decisions.event_log.append(
        "core_ability_instance_selected",
        validate_json_value(
            {
                "request_id": request.request_id,
                "result_id": result.result_id,
                "player_id": result.actor_id,
                "ability_family": "deadly_demise",
                "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                "selected_source": selected[0].to_payload(),
                "destruction_context": context,
            }
        ),
    )
    return context, selected[0]


def apply_rule_deadly_demise_instance_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> None:
    from warhammer40k_core.engine.rule_model_destruction import (
        _continue_rule_deadly_demise_sources,
        _remove_rule_destroyed_model_and_continue,
    )

    context, source = selected_deadly_demise_instance(
        state=state, decisions=decisions, result=result
    )
    status = _continue_rule_deadly_demise_sources(
        state=state, decisions=decisions, root_context=context, sources=(source,)
    )
    if status is None:
        _remove_rule_destroyed_model_and_continue(
            state=state, decisions=decisions, root_context=context
        )


def apply_attack_deadly_demise_instance_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    manager: DiceRollManager,
    hooks: AttackSequenceHooks,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    from warhammer40k_core.engine.attack_destruction_reactions import (
        resolve_mandatory_destruction_reactions_before_removal,
    )
    from warhammer40k_core.engine.attack_sequence_damage_resolution import (
        _finish_resumed_deadly_demise_source_damage,
    )
    from warhammer40k_core.engine.attack_sequence_group_selection import (
        _continue_grouped_damage_after_interruption,
    )
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import (
        _attack_sequence_for_context,
    )

    context, source = selected_deadly_demise_instance(
        state=state, decisions=decisions, result=result
    )
    attack_context = cast("AttackResolutionContextPayload", _object(context.get("attack_context")))
    damage = DamageApplication.from_payload(
        cast(DamageApplicationPayload, _object(context.get("damage_application")))
    )
    feel_no_pain = FeelNoPainResolution.from_payload(
        cast(FeelNoPainResolutionPayload, _object(context.get("feel_no_pain")))
    )
    current = (
        _attack_sequence_for_context(attack_sequence=attack_sequence, attack_context=attack_context)
        if attack_sequence.pending_grouped_damage is not None
        else attack_sequence
    )
    sources = state.destruction_reaction_sources_for_model(
        model_instance_id=damage.model_instance_id
    )
    completion = context.get("source_damage_completion")
    from warhammer40k_core.engine.attack_sequence_destruction_authority import (
        reserved_attack_damage_parent_cause_ids,
    )

    status = resolve_mandatory_destruction_reactions_before_removal(
        parent_cause_ids=reserved_attack_damage_parent_cause_ids(
            state=state, attack_sequence=current, damage=damage
        ),
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=current,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=context.get("saving_throw"),
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=_string(
            context, "destroyed_model_controller_player_id"
        ),
        sources=(
            source,
            *(
                entry
                for entry in sources
                if not entry.optional
                and entry.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE
            ),
        ),
        source_damage_completion=completion,
    )
    updated: AttackSequence | None = current
    allocated = already_allocated_model_ids
    if status is None:
        updated, allocated, status = _finish_resumed_deadly_demise_source_damage(
            state=state,
            decisions=decisions,
            manager=manager,
            hooks=hooks,
            attack_sequence=current,
            already_allocated_model_ids=already_allocated_model_ids,
            attack_context=attack_context,
            damage=damage,
            saving_throw_payload=context.get("saving_throw"),
            feel_no_pain=feel_no_pain,
            destroyed_model_controller_player_id=_string(
                context, "destroyed_model_controller_player_id"
            ),
            source_damage_completion=completion,
        )
    if attack_sequence.pending_grouped_damage is not None:
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated,
            status=status,
            hooks=hooks,
            runtime_modifier_registry=runtime_modifier_registry,
            dice_manager=manager,
        )
    return updated, allocated, status


def _context(request: DecisionRequest) -> dict[str, JsonValue]:
    return _object(_object(request.payload).get("destruction_context"))


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Deadly Demise instance context must be an object.")
    return value


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value or value.strip() != value:
        raise GameLifecycleError(f"Deadly Demise instance context requires {key}.")
    return value
