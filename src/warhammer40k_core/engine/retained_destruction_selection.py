from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    DestructionReactionSource,
    build_destruction_reaction_request,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import DestructionProvenance
from warhammer40k_core.engine.destruction_reaction_conditions import (
    optional_destruction_reaction_trigger_conditions_for_target,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.mission_action_eligibility import (
    action_restriction_prevents_shooting,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_attack_permissions import (
    RETAINED_ATTACK_REACTION_KINDS,
    RetainedAttackAction,
    retained_attack_options,
    retained_attack_selection,
)
from warhammer40k_core.engine.retained_destruction_state import (
    RETENTION_CONTEXT_KIND,
    DestructionOwnerKind,
    RetainedDestructionStage,
    RetainedModelDestruction,
    destruction_cause_ancestor_ids,
    pending_cause_for_model,
    record_retained_destruction,
    replace_retained_destruction,
    retained_destruction_for_model,
    retained_destructions,
    validate_retained_placement,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_fight_on_death_2026_09,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


_identifier = IdentifierValidator(GameLifecycleError)


def offer_fight_on_death_retention(
    *,
    state: GameState,
    decisions: DecisionController,
    model_instance_id: str,
    placement: ModelPlacement,
    owner_kind: DestructionOwnerKind,
    owner_context: dict[str, JsonValue],
    sources: tuple[DestructionReactionSource, ...],
    provenance: DestructionProvenance,
    manager: DiceRollManager,
) -> LifecycleStatus | None:
    existing = retained_destruction_for_model(state=state, model_instance_id=model_instance_id)
    if existing is not None:
        validate_retained_placement(state=state, record=existing)
        if existing.stage is RetainedDestructionStage.OFFERED:
            raise GameLifecycleError(
                "Retention decision must resolve before continuing destruction."
            )
        return None
    fight_sources = tuple(
        source for source in sources if source.reaction_kind in RETAINED_ATTACK_REACTION_KINDS
    )
    if not fight_sources:
        return None
    if any(not source.optional for source in fight_sources):
        raise GameLifecycleError("Fight On Death grants require a finite source decision.")
    cause = pending_cause_for_model(state=state, model_instance_id=model_instance_id)
    eligible = _eligible_sources(
        state=state,
        decisions=decisions,
        cause_id=cause.cause_id,
        logical_death_event_id=cause.logical_death_event.event_id,
        sources=fight_sources,
        model_instance_id=model_instance_id,
        target_unit_instance_id=cause.rules_unit_instance_id,
        player_id=placement.player_id,
        provenance=provenance,
        manager=manager,
    )
    record = RetainedModelDestruction(
        cause_id=cause.cause_id,
        logical_death_event_id=cause.logical_death_event.event_id,
        placement=placement,
        owner_kind=owner_kind,
        owner_context=owner_context,
        sources=sources,
        eligible_sources=eligible,
        excluded_actions=(RetainedAttackAction.SHOOT,)
        if retained_shooting_action_is_blocked(state=state, placement=placement)
        else (),
        stage=RetainedDestructionStage.OFFERED
        if eligible
        else RetainedDestructionStage.NOT_TRIGGERED,
        request_id=state.next_decision_request_id() if eligible else None,
    )
    record_retained_destruction(state=state, record=record)
    decisions.event_log.append(
        "fight_on_death_retention_opened",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": _identifier(
                "phase",
                None if state.current_battle_phase is None else state.current_battle_phase.value,
            ),
            "source_rule_id": core_fight_on_death_2026_09.FIGHT_ON_DEATH_SOURCE_ID,
            "destruction": record.to_payload(),
        },
    )
    if not eligible:
        return None
    request = retention_request(record)
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"context_kind": RETENTION_CONTEXT_KIND, "model_instance_id": model_instance_id},
    )


def retention_request(record: RetainedModelDestruction) -> DecisionRequest:
    if record.stage is not RetainedDestructionStage.OFFERED or record.request_id is None:
        raise GameLifecycleError("Retention request requires a pending source selection.")
    request = build_destruction_reaction_request(
        request_id=record.request_id,
        defender_player_id=record.placement.player_id,
        destruction_context={
            "context_kind": RETENTION_CONTEXT_KIND,
            "cause_id": record.cause_id,
            "logical_death_event_id": record.logical_death_event_id,
            "model_instance_id": record.model_instance_id,
            "target_unit_instance_id": record.placement.unit_instance_id,
            "destroyed_model_controller_player_id": record.placement.player_id,
            "retention_sha256": hashlib.sha256(
                canonical_json(record.to_payload()).encode("utf-8")
            ).hexdigest(),
        },
        sources=record.eligible_sources,
    )
    return replace(
        request,
        options=retained_attack_options(
            record.eligible_sources, excluded_actions=record.excluded_actions
        ),
    )


def is_retention_request(request: DecisionRequest) -> bool:
    if request.decision_type != SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
        return False
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    context = payload.get("destruction_context")
    return isinstance(context, dict) and context.get("context_kind") == RETENTION_CONTEXT_KIND


def validate_retention_request(
    *, state: GameState, request: DecisionRequest, result: DecisionResult
) -> RetainedModelDestruction:
    result.validate_for_request(request)
    if not is_retention_request(request):
        raise GameLifecycleError("Fight On Death retention request kind drift.")
    payload = cast(dict[str, JsonValue], request.payload)
    context = cast(dict[str, JsonValue], payload["destruction_context"])
    record = retained_destruction_for_model(
        state=state,
        model_instance_id=_identifier("model_instance_id", context.get("model_instance_id")),
    )
    if record is None:
        raise GameLifecycleError("Fight On Death retention request authority drift.")
    validate_retained_placement(state=state, record=record)
    if retention_request(record) != request:
        raise GameLifecycleError("Fight On Death finite options drift.")
    validate_retention_grants(state=state, record=record)
    _source, action = retained_attack_selection(request=request, result=result)
    if action is RetainedAttackAction.SHOOT:
        validate_retained_shooting_activity(state=state, record=record)
    return record


def validate_retention_grants(*, state: GameState, record: RetainedModelDestruction) -> None:
    current_sources = state.destruction_reaction_sources_for_model(
        model_instance_id=record.model_instance_id
    )
    if current_sources != record.sources:
        raise GameLifecycleError("Fight On Death destruction sources drift.")
    from warhammer40k_core.engine.retained_destruction_trigger_history import (
        retained_destruction_provenance,
    )

    cause = pending_cause_for_model(state=state, model_instance_id=record.model_instance_id)
    for source in record.eligible_sources:
        if isinstance(source.payload, dict) and not (
            optional_destruction_reaction_trigger_conditions_for_target(
                state=state,
                destruction_provenance=retained_destruction_provenance(record),
                target_unit_instance_id=cause.rules_unit_instance_id,
                descriptor=source.payload,
            )
        ):
            raise GameLifecycleError("Fight On Death granting conditions drift.")


def invalid_retention_request_status(
    *, state: GameState, request: DecisionRequest, result: DecisionResult
) -> LifecycleStatus | None:
    try:
        validate_retention_request(state=state, request=request, result=result)
    except (DecisionError, GameLifecycleError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight On Death retention context drifted.",
            payload={"invalid_reason": "fight_on_death_retention_drift", "diagnostic": str(exc)},
        )
    return None


def apply_retention_selection(
    *, state: GameState, decisions: DecisionController, result: DecisionResult
) -> RetainedModelDestruction:
    request = decisions.record_for_result(result).request
    record = validate_retention_request(state=state, request=request, result=result)
    selected, action = retained_attack_selection(request=request, result=result)
    updated = replace(
        record,
        stage=RetainedDestructionStage.WAITING
        if selected is not None
        else RetainedDestructionStage.DECLINED,
        result_id=result.result_id,
        selected_source_id=selected,
        selected_action=action,
    )
    replace_retained_destruction(state=state, original=record, updated=updated)
    decisions.event_log.append(
        "fight_on_death_retention_selected",
        {
            "cause_id": record.cause_id,
            "logical_death_event_id": record.logical_death_event_id,
            "model_instance_id": record.model_instance_id,
            "request_id": request.request_id,
            "result_id": result.result_id,
            "selected_source_id": selected,
            "selected_action": None if action is None else action.value,
            "stage": updated.stage.value,
            "model_placement": record.placement.to_payload(),
        },
    )
    if updated.is_retained:
        cause = pending_cause_for_model(state=state, model_instance_id=updated.model_instance_id)
        ancestors = destruction_cause_ancestor_ids(state=state, cause_id=cause.cause_id)
        for parent in retained_destructions(state=state):
            if parent.cause_id in ancestors and parent.stage is RetainedDestructionStage.RESOLVING:
                suspended = replace(parent, stage=RetainedDestructionStage.SUSPENDED)
                replace_retained_destruction(state=state, original=parent, updated=suspended)
                decisions.event_log.append(
                    "fight_on_death_destruction_suspended",
                    {
                        "cause_id": parent.cause_id,
                        "model_instance_id": parent.model_instance_id,
                        "child_cause_id": cause.cause_id,
                    },
                )
    return updated


def _eligible_sources(
    *,
    state: GameState,
    decisions: DecisionController,
    cause_id: str,
    logical_death_event_id: str,
    sources: tuple[DestructionReactionSource, ...],
    model_instance_id: str,
    target_unit_instance_id: str,
    player_id: str,
    provenance: DestructionProvenance,
    manager: DiceRollManager,
) -> tuple[DestructionReactionSource, ...]:
    active: list[DestructionReactionSource] = []
    for source in sources:
        descriptor = source.payload
        if descriptor is None:
            active.append(source)
            continue
        if not isinstance(descriptor, dict):
            raise GameLifecycleError("Fight On Death descriptor must be an object.")
        applicable = optional_destruction_reaction_trigger_conditions_for_target(
            state=state,
            destruction_provenance=provenance,
            target_unit_instance_id=target_unit_instance_id,
            descriptor=descriptor,
        )
        if descriptor.get("requires_not_shot_or_fought_this_phase") is True:
            from warhammer40k_core.engine.model_attack_history import model_has_attacked_this_phase

            if state.current_battle_phase is None or state.active_player_id is None:
                raise GameLifecycleError("Retained attack prior-action condition requires a phase.")
            applicable = applicable and not model_has_attacked_this_phase(
                event_records=decisions.event_log.records,
                model_instance_id=model_instance_id,
                battle_round=state.battle_round,
                active_player_id=state.active_player_id,
                phase=state.current_battle_phase.value,
            )
        roll = None
        triggered = applicable
        if applicable and "trigger_roll_threshold" in descriptor:
            threshold = descriptor["trigger_roll_threshold"]
            if type(threshold) is not int or not 1 <= threshold <= 6:
                raise GameLifecycleError("Fight On Death threshold must be on a D6.")
            roll = manager.roll(
                DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="Destruction reaction trigger",
                    roll_type=_identifier(
                        "trigger_roll_type",
                        descriptor.get("trigger_roll_type", "destruction_reaction_trigger"),
                    ),
                    actor_id=player_id,
                )
            )
            triggered = roll.current_total >= threshold
        decisions.event_log.append(
            "fight_on_death_retention_trigger_resolved",
            {
                "cause_id": cause_id,
                "logical_death_event_id": logical_death_event_id,
                "model_instance_id": model_instance_id,
                "target_unit_instance_id": target_unit_instance_id,
                "source": source.to_payload(),
                "destruction_provenance": provenance.to_payload(),
                "applicable": applicable,
                "trigger_roll": None if roll is None else roll.to_payload(),
                "triggered": triggered,
            },
        )
        if triggered:
            active.append(source)
    return tuple(active)


def validate_retained_shooting_activity(
    *, state: GameState, record: RetainedModelDestruction
) -> None:
    if retained_shooting_action_is_blocked(state=state, placement=record.placement):
        raise GameLifecycleError("Action restriction prevents retained shooting.")


def retained_shooting_action_is_blocked(*, state: GameState, placement: ModelPlacement) -> bool:
    from warhammer40k_core.engine.rules_units import (
        rules_unit_view_by_id,
        rules_unit_view_with_retained_models,
    )

    view = rules_unit_view_by_id(state=state, unit_instance_id=placement.unit_instance_id)
    # Evaluate the offered entitlement with its destroyed model retained. This
    # preserves its canonical keywords before the selection establishes retention.
    view = rules_unit_view_with_retained_models(
        view=view,
        retained_model_ids=tuple(sorted({*view.retained_model_ids, placement.model_instance_id})),
    )
    return action_restriction_prevents_shooting(state=state, rules_unit=view)
