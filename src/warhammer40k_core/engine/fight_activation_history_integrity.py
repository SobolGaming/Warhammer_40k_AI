from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.damage_allocation import (
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    DestructionReactionDecision,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionReactionSourcePayload,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_on_death import (
    FIGHT_ON_DEATH_AWAITING_EFFECT_KIND,
    fight_on_death_model_ids_awaiting_attack,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
)
from warhammer40k_core.engine.rule_model_destruction_source_liabilities import (
    validate_rule_destruction_source_liabilities,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_identities_share_lineage,
    rules_unit_identity_history_contains,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.effects import PersistingEffect
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


_ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND = "attack_sequence_model_destroyed"


def validate_restore(
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    _validate_activation_history(state=state)
    _validate_fight_on_death_restore(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )


def _validate_activation_history(*, state: GameState) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return
    order_state = fight_state.fight_order_state
    selections = order_state.activation_selections
    result_ids = tuple(selection.result_id for selection in selections)
    if len(result_ids) != len(set(result_ids)):
        raise GameLifecycleError("Fight activation selection result IDs must be unique.")
    for selection in selections:
        if selection.battle_round != fight_state.battle_round:
            raise GameLifecycleError("Fight activation selection battle round drift.")
        if not rules_unit_identity_history_contains(
            state=state,
            identity_ids=order_state.selected_to_fight_unit_ids,
            unit_instance_id=selection.unit_instance_id,
        ):
            raise GameLifecycleError("Fight activation selection is missing from selected history.")
    selection_unit_ids = tuple(selection.unit_instance_id for selection in selections)
    for selected_unit_id in order_state.selected_to_fight_unit_ids:
        if not rules_unit_identity_history_contains(
            state=state,
            identity_ids=selection_unit_ids,
            unit_instance_id=selected_unit_id,
        ):
            raise GameLifecycleError("Fight selected history is missing an activation selection.")
    for index, selection in enumerate(selections):
        if any(
            rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=selection.unit_instance_id,
                second_unit_instance_id=prior.unit_instance_id,
            )
            for prior in selections[:index]
        ):
            raise GameLifecycleError("Fight activation selection repeats a rules-unit lineage.")
    active = fight_state.active_activation
    if active is None:
        return
    matching = tuple(
        selection for selection in selections if selection.result_id == active.result_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Active Fight activation must match exactly one selection.")
    if matching[0] != active:
        raise GameLifecycleError("Active Fight activation selection drift.")
    if not rules_unit_identity_history_contains(
        state=state,
        identity_ids=order_state.selected_to_fight_unit_ids,
        unit_instance_id=active.unit_instance_id,
    ):
        raise GameLifecycleError("Active Fight activation is missing from selected history.")


def _validate_fight_on_death_restore(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    effects = tuple(
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == FIGHT_ON_DEATH_AWAITING_EFFECT_KIND
    )
    if not effects:
        return
    fight_on_death_model_ids_awaiting_attack(state=state)
    for effect in effects:
        payload = _payload_object(
            effect.effect_payload,
            field_name="Fight On Death effect payload",
        )
        context_value = payload.get("completion_context")
        if context_value is None:
            continue
        context = _payload_object(
            context_value,
            field_name="Fight On Death completion context",
        )
        context_kind = _payload_string(context, key="context_kind")
        if context_kind not in {
            _ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND,
            RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
        }:
            raise GameLifecycleError("Fight On Death completion context kind is unsupported.")
        _validate_completion_event(
            state=state,
            event_records=event_records,
            effect=effect,
            context=context,
            context_kind=context_kind,
        )
        _validate_activation_result_binding(
            state=state,
            decision_records=decision_records,
            effect=effect,
            payload=payload,
            context=context,
            context_kind=context_kind,
        )
        if context_kind == RULE_MODEL_DESTRUCTION_CONTEXT_KIND:
            _validate_rule_source_liabilities(state=state, context=context)


def _validate_completion_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    effect: PersistingEffect,
    context: dict[str, JsonValue],
    context_kind: str,
) -> None:
    event_id = _payload_string(context, key="model_destroyed_event_id")
    matching_events = tuple(record for record in event_records if record.event_id == event_id)
    if len(matching_events) != 1 or matching_events[0].event_type != "model_destroyed":
        raise GameLifecycleError(
            "Fight On Death completion requires one authoritative model_destroyed event."
        )
    event_payload = _payload_object(
        matching_events[0].payload,
        field_name="Fight On Death model_destroyed event payload",
    )
    model_id = _payload_string(context, key="model_instance_id")
    controller_id = _payload_string(context, key="destroyed_model_controller_player_id")
    context_target_id = _payload_string(context, key="target_unit_instance_id")
    physical_unit_id = state.unit_instance_id_for_model(model_id)
    placement = _payload_object(
        event_payload.get("destroyed_model_placement"),
        field_name="Fight On Death destroyed model placement",
    )
    if (
        event_payload.get("game_id") != state.game_id
        or event_payload.get("battle_round") != state.battle_round
        or event_payload.get("phase")
        != (None if effect.started_phase is None else effect.started_phase.value)
        or event_payload.get("model_instance_id") != model_id
        or event_payload.get("target_unit_instance_id") != context_target_id
        or placement.get("model_instance_id") != model_id
        or placement.get("unit_instance_id") != physical_unit_id
        or placement.get("player_id") != controller_id
    ):
        raise GameLifecycleError("Fight On Death model_destroyed event identity drift.")
    rules_unit_id = context_target_id
    if context_kind == RULE_MODEL_DESTRUCTION_CONTEXT_KIND:
        rules_unit_id = _payload_string(context, key="rules_unit_instance_id")
        if (
            context.get("game_id") != state.game_id
            or context.get("battle_round") != state.battle_round
            or context.get("active_player_id") != state.active_player_id
            or context.get("phase")
            != (None if effect.started_phase is None else effect.started_phase.value)
            or event_payload.get("rules_unit_instance_id") != rules_unit_id
            or event_payload.get("source_rule_id") != context.get("source_rule_id")
        ):
            raise GameLifecycleError("Rule Fight On Death model_destroyed event drift.")
    if not rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=rules_unit_id,
        second_unit_instance_id=physical_unit_id,
    ):
        raise GameLifecycleError("Fight On Death model_destroyed rules-unit lineage drift.")


def _validate_activation_result_binding(
    *,
    state: GameState,
    decision_records: tuple[DecisionRecord, ...],
    effect: PersistingEffect,
    payload: dict[str, JsonValue],
    context: dict[str, JsonValue],
    context_kind: str,
) -> None:
    activation_result_id = _payload_string(payload, key="activation_result_id")
    bound_to_active = context_kind == RULE_MODEL_DESTRUCTION_CONTEXT_KIND and (
        _matches_active_activation(
            state=state,
            activation_result_id=activation_result_id,
            context=context,
            owner_player_id=effect.owner_player_id,
        )
    )
    matching_reactions = tuple(
        record
        for record in decision_records
        if record.request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        and isinstance(record.request.payload, dict)
        and record.request.payload.get("destruction_context") == context
    )
    if len(matching_reactions) != 1:
        raise GameLifecycleError(
            "Fight On Death completion must match one destruction reaction record."
        )
    record = matching_reactions[0]
    if not bound_to_active and record.result.result_id != activation_result_id:
        raise GameLifecycleError("Fight On Death activation result decision binding drift.")
    _validate_accepted_reaction(
        effect=effect,
        context=context,
        record=record,
    )


def _validate_accepted_reaction(
    *,
    effect: PersistingEffect,
    context: dict[str, JsonValue],
    record: DecisionRecord,
) -> None:
    request_payload = _payload_object(
        record.request.payload,
        field_name="Fight On Death destruction reaction request payload",
    )
    decision = DestructionReactionDecision.from_result(
        request=record.request,
        result=record.result,
    )
    if (
        decision.selected_reaction_kind is not DestructionReactionKind.FIGHT_ON_DEATH
        or decision.selected_source_id is None
        or decision.player_id != effect.owner_player_id
        or decision.destruction_context != context
    ):
        raise GameLifecycleError("Fight On Death destruction reaction result drift.")
    sources_value = request_payload.get("sources")
    if not isinstance(sources_value, list) or not all(
        isinstance(value, dict) for value in sources_value
    ):
        raise GameLifecycleError("Fight On Death destruction reaction sources are invalid.")
    sources = tuple(
        DestructionReactionSource.from_payload(
            cast(DestructionReactionSourcePayload, source_payload)
        )
        for source_payload in sources_value
    )
    selected_sources = tuple(
        source for source in sources if source.source_id == decision.selected_source_id
    )
    if (
        len(selected_sources) != 1
        or selected_sources[0].reaction_kind is not DestructionReactionKind.FIGHT_ON_DEATH
        or selected_sources[0].source_rule_id != effect.source_rule_id
    ):
        raise GameLifecycleError("Fight On Death selected reaction source drift.")


def _matches_active_activation(
    *,
    state: GameState,
    activation_result_id: str,
    context: dict[str, JsonValue],
    owner_player_id: str,
) -> bool:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return False
    matching = tuple(
        selection
        for selection in fight_state.fight_order_state.activation_selections
        if selection.result_id == activation_result_id
    )
    if not matching:
        return False
    if len(matching) != 1:
        raise GameLifecycleError("Rule Fight On Death activation result is ambiguous.")
    selection = matching[0]
    active = fight_state.active_activation
    rules_unit_id = _payload_string(context, key="rules_unit_instance_id")
    if (
        active != selection
        or selection.player_id != owner_player_id
        or not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=selection.unit_instance_id,
            second_unit_instance_id=rules_unit_id,
        )
    ):
        raise GameLifecycleError("Rule Fight On Death active activation binding drift.")
    return True


def _validate_rule_source_liabilities(
    *,
    state: GameState,
    context: dict[str, JsonValue],
) -> None:
    raw_effect_ids = context.get("source_effect_ids")
    if not isinstance(raw_effect_ids, list) or not all(
        type(effect_id) is str and bool(effect_id.strip()) for effect_id in raw_effect_ids
    ):
        raise GameLifecycleError("Rule Fight On Death source effect IDs are invalid.")
    source_effect_ids = cast(list[str], raw_effect_ids)
    if len(source_effect_ids) != len(set(source_effect_ids)):
        raise GameLifecycleError("Rule Fight On Death source effect IDs are duplicated.")
    rules_unit_id = _payload_string(context, key="rules_unit_instance_id")
    try:
        validate_rule_destruction_source_liabilities(
            state=state,
            source_effect_ids=tuple(source_effect_ids),
            rules_unit_instance_id=rules_unit_id,
        )
    except GameLifecycleError as exc:
        raise GameLifecycleError("Rule Fight On Death source liability drift.") from exc
    rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)


def _payload_object(value: JsonValue | None, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Fight On Death {key} must be a string.")
    return value


__all__ = ("validate_restore",)
