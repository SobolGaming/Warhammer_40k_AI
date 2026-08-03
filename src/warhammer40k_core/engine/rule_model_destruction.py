from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
    PlacementError,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionDecision,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionReactionSourcePayload,
    build_destruction_reaction_request,
    destroy_model_by_rule,
    model_owner_player_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionProvenance,
    DestructionSourceKind,
)
from warhammer40k_core.engine.destruction_reaction_conditions import (
    optional_destruction_reaction_trigger_conditions_for_target,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_on_death import (
    restore_selected_model_awaiting_fight_on_death,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


RULE_MODEL_DESTRUCTION_CONTEXT_KIND = "rule_model_destroyed"


@dataclass(frozen=True, slots=True)
class RuleModelDestructionResult:
    model_destroyed_event_id: str
    removal_record: ModelRemovalRecord
    transition_batch: BattlefieldTransitionBatch
    status: LifecycleStatus | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_destroyed_event_id",
            _validate_identifier("model_destroyed_event_id", self.model_destroyed_event_id),
        )
        if type(self.removal_record) is not ModelRemovalRecord:
            raise GameLifecycleError("Rule destruction requires a removal record.")
        if type(self.transition_batch) is not BattlefieldTransitionBatch:
            raise GameLifecycleError("Rule destruction requires a transition batch.")
        if self.status is not None and type(self.status) is not LifecycleStatus:
            raise GameLifecycleError("Rule destruction status must be LifecycleStatus or None.")


def destroy_model_with_rule_reactions(
    *,
    state: GameState,
    decisions: DecisionController,
    model_instance_id: str,
    rules_unit_instance_id: str,
    destroying_player_id: str,
    source_rule_id: str,
    source_effect_ids: tuple[str, ...],
    source_phase: BattlePhase,
    source_step: str,
    source_result_id: str,
) -> RuleModelDestructionResult:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    requested_rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    requested_destroying_player_id = _validate_identifier(
        "destroying_player_id", destroying_player_id
    )
    requested_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    requested_effect_ids = _validate_identifier_tuple(
        "source_effect_ids", source_effect_ids, min_length=1
    )
    requested_step = _validate_identifier("source_step", source_step)
    requested_result_id = _validate_identifier("source_result_id", source_result_id)
    if type(source_phase) is not BattlePhase:
        raise GameLifecycleError("Rule destruction source_phase must be BattlePhase.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Rule destruction requires DecisionController.")
    if state.current_battle_phase is not source_phase:
        raise GameLifecycleError("Rule destruction source phase drift.")
    active_player_id = _active_player_id(state)
    physical_unit_id = state.unit_instance_id_for_model(requested_model_id)
    controller_player_id = model_owner_player_id(
        state=state,
        model_instance_id=requested_model_id,
    )
    sources = state.destruction_reaction_sources_for_model(model_instance_id=requested_model_id)
    mandatory_sources = tuple(source for source in sources if not source.optional)
    deadly_demise_sources = tuple(
        source
        for source in mandatory_sources
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
    )
    if deadly_demise_sources:
        source_ids = ", ".join(source.source_id for source in deadly_demise_sources)
        raise GameLifecycleError(
            f"Rule model destruction cannot resolve Deadly Demise before removal: {source_ids}."
        )

    placement_payload = _model_placement_payload(
        state=state,
        model_instance_id=requested_model_id,
    )
    destroy_model_by_rule(state=state, model_instance_id=requested_model_id)
    removal_record = ModelRemovalRecord(
        model_instance_id=requested_model_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        source_phase=source_phase.value,
        source_step=requested_step,
        source_rule_id=requested_rule_id,
        source_event_id=requested_result_id,
    )
    transition_batch = BattlefieldTransitionBatch(removals=(removal_record,))
    provenance = DestructionProvenance.for_non_attack(DestructionSourceKind.ABILITY)
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": source_phase.value,
                "destroying_player_id": requested_destroying_player_id,
                "target_unit_instance_id": physical_unit_id,
                "rules_unit_instance_id": requested_rules_unit_id,
                "model_instance_id": requested_model_id,
                "damage_kind": None,
                "damage_event_id": None,
                "source_rule_id": requested_rule_id,
                "source_effect_ids": list(requested_effect_ids),
                "destruction_provenance": provenance.to_payload(),
                "removal_record": removal_record.to_payload(),
                "transition_batch": transition_batch.to_payload(),
                "destroyed_model_placement": placement_payload,
                "destroyed_model_rules_triggered": True,
            }
        ),
    )
    _record_mandatory_sources_after_removal(
        state=state,
        decisions=decisions,
        sources=mandatory_sources,
        model_instance_id=requested_model_id,
        physical_unit_instance_id=physical_unit_id,
        rules_unit_instance_id=requested_rules_unit_id,
        model_destroyed_event_id=destroyed_event.event_id,
        provenance=provenance,
    )
    optional_sources = _active_optional_sources(
        state=state,
        decisions=decisions,
        sources=tuple(source for source in sources if source.optional),
        rules_unit_instance_id=requested_rules_unit_id,
        model_instance_id=requested_model_id,
        model_destroyed_event_id=destroyed_event.event_id,
        provenance=provenance,
    )
    status = None
    if optional_sources:
        destruction_context = validate_json_value(
            {
                "context_kind": RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": source_phase.value,
                "source_step": requested_step,
                "source_rule_id": requested_rule_id,
                "source_effect_ids": list(requested_effect_ids),
                "source_result_id": requested_result_id,
                "rules_unit_instance_id": requested_rules_unit_id,
                "target_unit_instance_id": physical_unit_id,
                "model_instance_id": requested_model_id,
                "destroyed_model_controller_player_id": controller_player_id,
                "model_destroyed_event_id": destroyed_event.event_id,
                "destruction_provenance": provenance.to_payload(),
                "removal_record": removal_record.to_payload(),
                "transition_batch": transition_batch.to_payload(),
            }
        )
        request = build_destruction_reaction_request(
            request_id=state.next_decision_request_id(),
            defender_player_id=controller_player_id,
            destruction_context=destruction_context,
            sources=optional_sources,
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "destruction_reaction_window_opened",
            validate_json_value(
                {
                    "model_instance_id": requested_model_id,
                    "target_unit_instance_id": physical_unit_id,
                    "rules_unit_instance_id": requested_rules_unit_id,
                    "model_destroyed_event_id": destroyed_event.event_id,
                    "destruction_provenance": provenance.to_payload(),
                    "sources": [source.to_payload() for source in optional_sources],
                    "request_id": request.request_id,
                }
            ),
        )
        status = LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload=validate_json_value(
                {
                    "phase": source_phase.value,
                    "decision_type": request.decision_type,
                    "context_kind": RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
                    "model_destroyed_event_id": destroyed_event.event_id,
                }
            ),
        )
    return RuleModelDestructionResult(
        model_destroyed_event_id=destroyed_event.event_id,
        removal_record=removal_record,
        transition_batch=transition_batch,
        status=status,
    )


def is_rule_model_destruction_reaction_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Rule destruction reaction check requires DecisionRequest.")
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    context = payload.get("destruction_context")
    return isinstance(context, dict) and context.get("context_kind") == (
        RULE_MODEL_DESTRUCTION_CONTEXT_KIND
    )


def invalid_rule_model_destruction_reaction_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if not is_rule_model_destruction_reaction_request(request):
        raise GameLifecycleError("Rule destruction reaction request kind drift.")
    try:
        result.validate_for_request(request)
        context = _destruction_context(request)
        _validate_context_matches_state(state=state, decisions=None, context=context)
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Rule model destruction reaction context drifted.",
            payload=validate_json_value(
                {
                    "invalid_reason": "invalid_destruction_reaction_result",
                    "field": "destruction_context",
                    "diagnostic": str(exc),
                }
            ),
        )
    return None


def apply_rule_model_destruction_reaction_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> None:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_rule_model_destruction_reaction_request(request):
        raise GameLifecycleError("Rule destruction reaction result request kind drift.")
    decision = DestructionReactionDecision.from_result(request=request, result=result)
    context = _destruction_context(request)
    _validate_context_matches_state(state=state, decisions=decisions, context=context)
    selected_source = _selected_source(
        request=request,
        selected_source_id=decision.selected_source_id,
    )
    if selected_source is not None and selected_source.reaction_kind is not (
        decision.selected_reaction_kind
    ):
        raise GameLifecycleError("Rule destruction reaction kind drift.")
    if decision.player_id != _payload_string(context, "destroyed_model_controller_player_id"):
        raise GameLifecycleError("Rule destruction reaction controller drift.")
    if (
        selected_source is not None
        and selected_source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH
    ):
        restore_selected_model_awaiting_fight_on_death(
            state=state,
            decisions=decisions,
            model_destroyed_event_id=_payload_string(context, "model_destroyed_event_id"),
            model_instance_id=_payload_string(context, "model_instance_id"),
            source_id=selected_source.source_id,
            source_rule_id=selected_source.source_rule_id,
            source_phase=BattlePhaseKind.FIGHT,
        )
    decisions.event_log.append(
        "destruction_reaction_resolved",
        validate_json_value(
            {
                "decision": decision.to_payload(),
                "selected_source": (
                    None if selected_source is None else selected_source.to_payload()
                ),
                "selected_reaction_kind": (
                    None
                    if decision.selected_reaction_kind is None
                    else decision.selected_reaction_kind.value
                ),
                "action_host": _reaction_action_host(selected_source),
                "execution_status": (
                    "declined" if selected_source is None else "recorded_for_action_host"
                ),
            }
        ),
    )


def _active_optional_sources(
    *,
    state: GameState,
    decisions: DecisionController,
    sources: tuple[DestructionReactionSource, ...],
    rules_unit_instance_id: str,
    model_instance_id: str,
    model_destroyed_event_id: str,
    provenance: DestructionProvenance,
) -> tuple[DestructionReactionSource, ...]:
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    active: list[DestructionReactionSource] = []
    for source in sources:
        descriptor = _trigger_descriptor(source)
        if descriptor is None:
            active.append(source)
            continue
        if not optional_destruction_reaction_trigger_conditions_for_target(
            state=state,
            destruction_provenance=provenance,
            target_unit_instance_id=rules_unit_instance_id,
            descriptor=descriptor,
        ):
            decisions.event_log.append(
                "destruction_reaction_trigger_not_applicable",
                validate_json_value(
                    {
                        "model_instance_id": model_instance_id,
                        "target_unit_instance_id": rules_unit_instance_id,
                        "model_destroyed_event_id": model_destroyed_event_id,
                        "destruction_provenance": provenance.to_payload(),
                        "selected_source": source.to_payload(),
                        "descriptor": descriptor,
                    }
                ),
            )
            continue
        threshold = _payload_d6_target(descriptor, "trigger_roll_threshold")
        roll_type = descriptor.get("trigger_roll_type", "destruction_reaction_trigger")
        if type(roll_type) is not str or not roll_type:
            raise GameLifecycleError("Rule destruction reaction roll type is invalid.")
        roll = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Destruction reaction trigger",
                roll_type=roll_type,
                actor_id=model_owner_player_id(
                    state=state,
                    model_instance_id=model_instance_id,
                ),
            )
        )
        triggered = roll.current_total >= threshold
        decisions.event_log.append(
            "destruction_reaction_trigger_rolled",
            validate_json_value(
                {
                    "model_instance_id": model_instance_id,
                    "target_unit_instance_id": rules_unit_instance_id,
                    "model_destroyed_event_id": model_destroyed_event_id,
                    "destruction_provenance": provenance.to_payload(),
                    "selected_source": source.to_payload(),
                    "descriptor": descriptor,
                    "trigger_roll": roll.to_payload(),
                    "trigger_roll_threshold": threshold,
                    "triggered": triggered,
                }
            ),
        )
        if triggered:
            active.append(source)
    return tuple(active)


def _record_mandatory_sources_after_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    sources: tuple[DestructionReactionSource, ...],
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    model_destroyed_event_id: str,
    provenance: DestructionProvenance,
) -> None:
    for source in sources:
        if source.optional or source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
            raise GameLifecycleError("Rule destruction mandatory source routing drift.")
        decisions.event_log.append(
            "destruction_reaction_resolved",
            validate_json_value(
                {
                    "resolution_kind": "mandatory",
                    "decision": None,
                    "selected_source": source.to_payload(),
                    "selected_reaction_kind": source.reaction_kind.value,
                    "action_host": _reaction_action_host(source),
                    "execution_status": "recorded_for_action_host",
                    "model_instance_id": model_instance_id,
                    "target_unit_instance_id": physical_unit_instance_id,
                    "rules_unit_instance_id": rules_unit_instance_id,
                    "model_destroyed_event_id": model_destroyed_event_id,
                    "destruction_provenance": provenance.to_payload(),
                    "battle_round": state.battle_round,
                }
            ),
        )


def _trigger_descriptor(source: DestructionReactionSource) -> dict[str, JsonValue] | None:
    if source.payload is None:
        return None
    if not isinstance(source.payload, dict):
        raise GameLifecycleError("Rule destruction reaction payload must be an object.")
    if "trigger_roll_threshold" not in source.payload:
        return None
    return source.payload


def _destruction_context(request: DecisionRequest) -> dict[str, JsonValue]:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Rule destruction request payload must be an object.")
    context = payload.get("destruction_context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Rule destruction context must be an object.")
    if context.get("context_kind") != RULE_MODEL_DESTRUCTION_CONTEXT_KIND:
        raise GameLifecycleError("Rule destruction context kind drift.")
    return context


def _validate_context_matches_state(
    *,
    state: GameState,
    decisions: DecisionController | None,
    context: dict[str, JsonValue],
) -> None:
    if context.get("game_id") != state.game_id:
        raise GameLifecycleError("Rule destruction game drift.")
    if context.get("battle_round") != state.battle_round:
        raise GameLifecycleError("Rule destruction battle round drift.")
    if context.get("active_player_id") != state.active_player_id:
        raise GameLifecycleError("Rule destruction active player drift.")
    if context.get("phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Rule destruction phase payload drift.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Rule destruction phase drift.")
    model_id = _payload_string(context, "model_instance_id")
    if state.unit_instance_id_for_model(model_id) != _payload_string(
        context, "target_unit_instance_id"
    ):
        raise GameLifecycleError("Rule destruction physical unit drift.")
    from warhammer40k_core.engine.damage_allocation import model_by_id

    if model_by_id(state=state, model_instance_id=model_id).is_alive:
        raise GameLifecycleError("Rule destruction model is no longer destroyed.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rule destruction requires battlefield state.")
    if battlefield.model_placement_or_none(model_id) is not None:
        raise GameLifecycleError("Rule destruction model removal drift.")
    if decisions is None:
        return
    event_id = _payload_string(context, "model_destroyed_event_id")
    matches = tuple(record for record in decisions.event_log.records if record.event_id == event_id)
    if len(matches) != 1 or matches[0].event_type != "model_destroyed":
        raise GameLifecycleError("Rule destruction event drift.")


def _selected_source(
    *,
    request: DecisionRequest,
    selected_source_id: str | None,
) -> DestructionReactionSource | None:
    if selected_source_id is None:
        return None
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Rule destruction request payload must be an object.")
    source_payloads = payload.get("sources")
    if not isinstance(source_payloads, list):
        raise GameLifecycleError("Rule destruction sources must be a list.")
    if not all(isinstance(item, dict) for item in source_payloads):
        raise GameLifecycleError("Rule destruction source entry must be an object.")
    sources = tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, item))
        for item in source_payloads
    )
    matches = tuple(source for source in sources if source.source_id == selected_source_id)
    if len(matches) != 1:
        raise GameLifecycleError("Rule destruction selected source drift.")
    return matches[0]


def _model_placement_payload(*, state: GameState, model_instance_id: str) -> JsonValue:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rule destruction requires battlefield state.")
    try:
        placement = battlefield.model_placement_by_id(model_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Rule destruction requires a placed model.") from exc
    return validate_json_value(placement.to_payload())


def _reaction_action_host(source: DestructionReactionSource | None) -> str | None:
    if source is None:
        return None
    if source.reaction_kind is DestructionReactionKind.SHOOT_ON_DEATH:
        return "shooting"
    if source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH:
        return "fight"
    if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
        return "explosion"
    raise GameLifecycleError("Rule destruction reaction kind is unsupported.")


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Rule destruction {key} must be a string.")
    return value


def _payload_d6_target(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or not 2 <= value <= 6:
        raise GameLifecycleError(f"Rule destruction {key} must be a D6 target.")
    return value


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Rule destruction requires active player.")
    return state.active_player_id


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Rule destruction {field_name} must be a tuple.")
    typed = tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )
    if len(typed) < min_length or len(set(typed)) != len(typed):
        raise GameLifecycleError(f"Rule destruction {field_name} is invalid.")
    return tuple(sorted(typed))


_validate_identifier = IdentifierValidator(GameLifecycleError)
