from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import rule_deadly_demise_mortal_wound_routing as _r
from warhammer40k_core.engine.attached_unit_reconciliation import (
    validate_attached_rules_unit_identity_after_destruction,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementPayload,
    ModelRemovalRecord,
    PlacementError,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DestructionReactionDecision,
    DestructionReactionKind,
    DestructionReactionSource,
    DestructionReactionSourcePayload,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    build_destruction_reaction_request,
    continue_mortal_wound_application,
    destroy_model_by_rule,
    model_owner_player_id,
    remove_destroyed_model_from_battlefield,
    unit_owner_player_id,
)
from warhammer40k_core.engine.deadly_demise import (
    deadly_demise_mortal_wounds_for_target,
    deadly_demise_target_unit_ids,
    resolve_deadly_demise_trigger,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionProvenance,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.destruction_reaction_conditions import (
    optional_destruction_reaction_trigger_conditions_for_target,
)
from warhammer40k_core.engine.destruction_source_attribution import (
    resolve_non_attack_destruction_source_identity,
    validate_non_attack_destruction_source_context,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_on_death import (
    restore_selected_model_awaiting_fight_on_death,
)
from warhammer40k_core.engine.model_destruction_cause_producers import (
    append_rule_effect_model_destroyed_event as _append_model_destroyed,
)
from warhammer40k_core.engine.model_destruction_cause_producers import (
    reserve_rule_effect_model_destruction_cause as _reserve_destruction_cause,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    mortal_wound_resolution_progress,
    resolve_mortal_wound_decision,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
    RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND,
    RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
    RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
    RuleDeadlyDemiseSecondaryContinuation,
    build_rule_deadly_demise_secondary_root_context,
    damage_application_from_rule_context,
    destroyed_damage_applications,
    destruction_provenance_from_rule_context,
)
from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
    RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
)
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    validate_applied_damage_rule_destruction_context,
)
from warhammer40k_core.engine.rule_model_destruction_fight_on_death import (
    fight_on_death_activation_result_id_for_rule_destruction,
)
from warhammer40k_core.engine.rule_model_destruction_source_liabilities import (
    consume_rule_destruction_source_liabilities,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


RULE_MODEL_DESTRUCTION_FINALIZED_EVENT = "rule_model_destruction_finalized"
is_rule_model_destruction_mortal_wound_request = _r.is_rule_model_destruction_mortal_wound_request
_mortal_wound_waiting_status = _r.rule_deadly_demise_mortal_wound_waiting_status


@dataclass(frozen=True, slots=True)
class RuleModelDestructionResult:
    model_destroyed_event_id: str | None
    removal_record: ModelRemovalRecord | None
    transition_batch: BattlefieldTransitionBatch | None
    status: LifecycleStatus | None = None

    def __post_init__(self) -> None:
        if self.model_destroyed_event_id is not None:
            object.__setattr__(
                self,
                "model_destroyed_event_id",
                _validate_identifier("model_destroyed_event_id", self.model_destroyed_event_id),
            )
        if self.removal_record is not None and type(self.removal_record) is not ModelRemovalRecord:
            raise GameLifecycleError("Rule destruction removal record is invalid.")
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError("Rule destruction transition batch is invalid.")
        if self.status is not None and type(self.status) is not LifecycleStatus:
            raise GameLifecycleError("Rule destruction status must be LifecycleStatus or None.")
        completed = (
            self.model_destroyed_event_id is not None
            and self.removal_record is not None
            and self.transition_batch is not None
        )
        if self.status is None and not completed:
            raise GameLifecycleError("Completed rule destruction requires removal artifacts.")


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
    completion_event_type: str,
    completion_event_payload: JsonValue,
    source_rules_unit_instance_id: str | None = None,
    source_model_instance_id: str | None = None,
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
    requested_completion_event_type = _validate_identifier(
        "completion_event_type", completion_event_type
    )
    requested_source_rules_unit_id, requested_source_model_id = (
        resolve_non_attack_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=source_rules_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            destroying_player_id=requested_destroying_player_id,
        )
    )
    validated_completion_payload = validate_json_value(completion_event_payload)
    if not isinstance(validated_completion_payload, dict):
        raise GameLifecycleError("Rule destruction completion payload must be an object.")
    if type(source_phase) is not BattlePhase:
        raise GameLifecycleError("Rule destruction source_phase must be BattlePhase.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Rule destruction requires DecisionController.")
    if state.current_battle_phase is not source_phase:
        raise GameLifecycleError("Rule destruction source phase drift.")
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Rule destruction requires active player.")
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
    placement_payload = _model_placement_payload(
        state=state,
        model_instance_id=requested_model_id,
    )
    root_context = cast(
        dict[str, JsonValue],
        validate_json_value(
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
                "destroying_player_id": requested_destroying_player_id,
                "source_rules_unit_instance_id": requested_source_rules_unit_id,
                "source_model_instance_id": requested_source_model_id,
                "destroyed_model_controller_player_id": controller_player_id,
                "destroyed_model_placement": placement_payload,
                "completion_event_type": requested_completion_event_type,
                "completion_event_payload": validated_completion_payload,
                "completion_kind": RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
                "post_removal_mandatory_sources": [
                    source.to_payload()
                    for source in mandatory_sources
                    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE
                ],
            }
        ),
    )
    destroy_model_by_rule(
        state=state,
        model_instance_id=requested_model_id,
        remove_from_battlefield=False,
    )
    deadly_demise_status = _continue_rule_deadly_demise_sources(
        state=state,
        decisions=decisions,
        root_context=root_context,
        sources=deadly_demise_sources,
    )
    if deadly_demise_status is not None:
        return RuleModelDestructionResult(
            model_destroyed_event_id=None,
            removal_record=None,
            transition_batch=None,
            status=deadly_demise_status,
        )
    return _remove_rule_destroyed_model_and_continue(
        state=state,
        decisions=decisions,
        root_context=root_context,
    )


def invalid_rule_model_destruction_mortal_wound_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if not is_rule_model_destruction_mortal_wound_request(request):
        raise GameLifecycleError("Rule destruction mortal-wound request kind drift.")
    try:
        result.validate_for_request(request)
        source_context = _r.rule_deadly_demise_source_context(request)
        root_context = _payload_object_value(source_context, "root_context")
        _validate_pre_removal_context_matches_state(state=state, context=root_context)
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Rule model destruction mortal-wound context drifted.",
            payload=validate_json_value(
                {
                    "invalid_reason": "invalid_rule_model_destruction_mortal_wound_result",
                    "field": "source_context",
                    "diagnostic": str(exc),
                }
            ),
        )
    return None


def apply_rule_model_destruction_mortal_wound_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> LifecycleStatus | None:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_rule_model_destruction_mortal_wound_request(request):
        raise GameLifecycleError("Rule destruction mortal-wound result request kind drift.")
    source_context = _r.rule_deadly_demise_source_context(request)
    root_context = _payload_object_value(source_context, "root_context")
    _validate_pre_removal_context_matches_state(state=state, context=root_context)
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, _payload_object_value(source_context, "source"))
    )
    progress = mortal_wound_resolution_progress(request)
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    routed = resolve_mortal_wound_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
        remove_destroyed_models=False,
        logical_death_recorder=_r.rule_deadly_demise_logical_death_recorder(
            state=state,
            decisions=decisions,
            parent_root_context=root_context,
            source=source,
            progress=progress,
        ),
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return _mortal_wound_waiting_status(state=state, request=routed.request)
    if routed.application is None:
        raise GameLifecycleError("Rule destruction mortal wounds did not produce application.")
    descriptor = _payload_object_value(source_context, "descriptor")
    trigger_roll = validate_json_value(source_context.get("trigger_roll"))
    affected_target_ids = _payload_identifier_list(source_context, "affected_target_unit_ids")
    target_unit_id = _payload_string(source_context, "current_target_unit_instance_id")
    mortal_wounds = _payload_positive_int(source_context, "current_target_mortal_wounds")
    wound_roll = validate_json_value(source_context.get("current_target_mortal_wound_roll"))
    _emit_rule_deadly_demise_mortal_wounds_applied(
        decisions=decisions,
        root_context=root_context,
        source=source,
        target_unit_id=target_unit_id,
        mortal_wounds=mortal_wounds,
        application=routed.application,
        wound_roll_payload=wound_roll,
    )
    pending_target_ids = _payload_identifier_list(source_context, "pending_target_unit_ids")
    pending_sources = _payload_source_tuple(source_context, "pending_sources")
    status = _continue_rule_deadly_demise_secondary_destroyed_models(
        state=state,
        decisions=decisions,
        root_context=root_context,
        source=source,
        descriptor=descriptor,
        trigger_roll_payload=trigger_roll,
        affected_target_unit_ids=affected_target_ids,
        pending_target_unit_ids=pending_target_ids,
        pending_sources=pending_sources,
        secondary_damage_applications=destroyed_damage_applications(routed.application),
    )
    if status is not None:
        return status
    status = _route_rule_deadly_demise_targets(
        state=state,
        decisions=decisions,
        manager=manager,
        root_context=root_context,
        source=source,
        descriptor=descriptor,
        trigger_roll_payload=trigger_roll,
        affected_target_unit_ids=affected_target_ids,
        target_unit_ids=pending_target_ids,
        pending_sources=pending_sources,
    )
    if status is not None:
        return status
    _emit_rule_deadly_demise_resolution(
        decisions=decisions,
        root_context=root_context,
        source=source,
        descriptor=descriptor,
        trigger_roll_payload=trigger_roll,
        triggered=True,
        affected_target_unit_ids=affected_target_ids,
    )
    status = _continue_rule_deadly_demise_sources(
        state=state,
        decisions=decisions,
        root_context=root_context,
        sources=pending_sources,
    )
    if status is not None:
        return status
    removal = _remove_rule_destroyed_model_and_continue(
        state=state,
        decisions=decisions,
        root_context=root_context,
    )
    return removal.status


def finalize_rule_model_destruction(
    *,
    state: GameState,
    decisions: DecisionController,
    context: dict[str, JsonValue],
    resume_completion_continuation: bool = True,
) -> LifecycleStatus | None:
    _validate_post_removal_context_matches_state(state=state, decisions=decisions, context=context)
    rules_unit_id = _payload_string(context, "rules_unit_instance_id")
    source_effect_ids = _payload_identifier_list(context, "source_effect_ids")
    completion_kind = _payload_string(context, "completion_kind")
    if completion_kind == RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND:
        consume_rule_destruction_source_liabilities(
            state=state,
            source_effect_ids=source_effect_ids,
            rules_unit_instance_id=rules_unit_id,
        )
    elif completion_kind not in {
        RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND,
    }:
        raise GameLifecycleError("Rule destruction completion kind is unsupported.")
    elif source_effect_ids:
        raise GameLifecycleError("Applied rule destruction cannot consume source liabilities.")
    validate_attached_rules_unit_identity_after_destruction(
        state=state,
        rules_unit_instance_id=rules_unit_id,
    )
    if completion_kind in {
        RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
    }:
        completion_payload = _payload_object_value(context, "completion_event_payload").copy()
        completion_payload["model_destroyed_event_id"] = _payload_string(
            context, "model_destroyed_event_id"
        )
        decisions.event_log.append(
            _payload_string(context, "completion_event_type"),
            validate_json_value(completion_payload),
        )
    model_destroyed_event_id = _payload_string(context, "model_destroyed_event_id")
    if not any(
        record.event_type == RULE_MODEL_DESTRUCTION_FINALIZED_EVENT
        and isinstance(record.payload, dict)
        and record.payload.get("model_destroyed_event_id") == model_destroyed_event_id
        for record in decisions.event_log.records
    ):
        decisions.event_log.append(
            RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": _payload_string(context, "phase"),
                    "model_destroyed_event_id": model_destroyed_event_id,
                    "model_instance_id": _payload_string(context, "model_instance_id"),
                    "physical_unit_instance_id": _payload_string(
                        context, "target_unit_instance_id"
                    ),
                    "rules_unit_instance_id": rules_unit_id,
                    "completion_kind": completion_kind,
                }
            ),
        )
    continuation = context.get("completion_continuation")
    if continuation is None or not resume_completion_continuation:
        return None
    if not isinstance(continuation, dict):
        raise GameLifecycleError("Rule destruction completion continuation must be an object.")
    return _resume_rule_deadly_demise_secondary_continuation(
        state=state,
        decisions=decisions,
        continuation=continuation,
    )


def _continue_rule_deadly_demise_sources(
    *,
    state: GameState,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    _reserve_destruction_cause(
        state=state,
        decisions=decisions,
        root_context=root_context,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    model_id = _payload_string(root_context, "model_instance_id")
    controller_player_id = _payload_string(root_context, "destroyed_model_controller_player_id")
    for source_index, source in enumerate(sources):
        if source.optional or source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE:
            raise GameLifecycleError("Rule destruction Deadly Demise source routing drift.")
        descriptor, trigger_roll_payload, triggered = resolve_deadly_demise_trigger(
            state=state,
            manager=manager,
            source=source,
            player_id=controller_player_id,
            model_instance_id=model_id,
        )
        if not triggered:
            _emit_rule_deadly_demise_resolution(
                decisions=decisions,
                root_context=root_context,
                source=source,
                descriptor=descriptor,
                trigger_roll_payload=trigger_roll_payload,
                triggered=False,
                affected_target_unit_ids=(),
            )
            continue
        range_inches = _payload_positive_number(descriptor, "range_inches")
        target_ids = deadly_demise_target_unit_ids(
            state=state,
            source_model_instance_id=model_id,
            range_inches=range_inches,
        )
        status = _route_rule_deadly_demise_targets(
            state=state,
            decisions=decisions,
            manager=manager,
            root_context=root_context,
            source=source,
            descriptor=descriptor,
            trigger_roll_payload=trigger_roll_payload,
            affected_target_unit_ids=target_ids,
            target_unit_ids=target_ids,
            pending_sources=sources[source_index + 1 :],
        )
        if status is not None:
            return status
        _emit_rule_deadly_demise_resolution(
            decisions=decisions,
            root_context=root_context,
            source=source,
            descriptor=descriptor,
            trigger_roll_payload=trigger_roll_payload,
            triggered=True,
            affected_target_unit_ids=target_ids,
        )
    return None


def _route_rule_deadly_demise_targets(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    root_context: dict[str, JsonValue],
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    controller_player_id = _payload_string(root_context, "destroyed_model_controller_player_id")
    for target_index, target_unit_id in enumerate(target_unit_ids):
        mortal_wounds, wound_roll_payload = deadly_demise_mortal_wounds_for_target(
            manager=manager,
            source=source,
            descriptor=descriptor,
            player_id=controller_player_id,
            target_unit_instance_id=target_unit_id,
        )
        source_context = validate_json_value(
            {
                "source_kind": RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
                "root_context": root_context,
                "source": source.to_payload(),
                "descriptor": descriptor,
                "trigger_roll": trigger_roll_payload,
                "affected_target_unit_ids": list(affected_target_unit_ids),
                "current_target_unit_instance_id": target_unit_id,
                "current_target_mortal_wounds": mortal_wounds,
                "current_target_mortal_wound_roll": wound_roll_payload,
                "pending_target_unit_ids": list(target_unit_ids[target_index + 1 :]),
                "pending_sources": [item.to_payload() for item in pending_sources],
            }
        )
        logical_death_binding = _r.rule_deadly_demise_logical_death_binding()
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{_payload_string(root_context, 'source_result_id')}:deadly-demise:"
                f"{source.source_id}:{target_unit_id}:mortal-wounds"
            ),
            source_rule_id=source.source_rule_id,
            source_context=source_context,
            target_unit_instance_id=target_unit_id,
            defender_player_id=unit_owner_player_id(state=state, unit_instance_id=target_unit_id),
            mortal_wounds=mortal_wounds,
            spill_over=True,
            destruction_evidence=None,
            logical_death_cause_binding=logical_death_binding,
        )
        routed = continue_mortal_wound_application(
            state=state,
            decisions=decisions,
            request_id=state.next_decision_request_id(),
            progress=progress,
            dice_manager=manager,
            remove_destroyed_models=False,
            logical_death_recorder=_r.rule_deadly_demise_logical_death_recorder(
                state=state,
                decisions=decisions,
                parent_root_context=root_context,
                source=source,
            ),
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return _mortal_wound_waiting_status(state=state, request=routed.request)
        if routed.application is None:
            raise GameLifecycleError("Rule Deadly Demise did not produce mortal-wound application.")
        _emit_rule_deadly_demise_mortal_wounds_applied(
            decisions=decisions,
            root_context=root_context,
            source=source,
            target_unit_id=target_unit_id,
            mortal_wounds=mortal_wounds,
            application=routed.application,
            wound_roll_payload=wound_roll_payload,
        )
        status = _continue_rule_deadly_demise_secondary_destroyed_models(
            state=state,
            decisions=decisions,
            root_context=root_context,
            source=source,
            descriptor=descriptor,
            trigger_roll_payload=trigger_roll_payload,
            affected_target_unit_ids=affected_target_unit_ids,
            pending_target_unit_ids=target_unit_ids[target_index + 1 :],
            pending_sources=pending_sources,
            secondary_damage_applications=destroyed_damage_applications(routed.application),
        )
        if status is not None:
            return status
    return None


def _remove_rule_destroyed_model_and_continue(
    *,
    state: GameState,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    resume_completion_continuation: bool = True,
) -> RuleModelDestructionResult:
    _validate_pre_removal_context_matches_state(state=state, context=root_context)
    model_id = _payload_string(root_context, "model_instance_id")
    rules_unit_id = _payload_string(root_context, "rules_unit_instance_id")
    physical_unit_id = _payload_string(root_context, "target_unit_instance_id")
    remove_destroyed_model_from_battlefield(state=state, model_instance_id=model_id)
    removal_record = ModelRemovalRecord(
        model_instance_id=model_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        source_phase=_payload_string(root_context, "phase"),
        source_step=_payload_string(root_context, "source_step"),
        source_rule_id=_payload_string(root_context, "source_rule_id"),
        source_event_id=_payload_string(root_context, "source_result_id"),
    )
    transition_batch = BattlefieldTransitionBatch(removals=(removal_record,))
    damage = damage_application_from_rule_context(root_context)
    provenance = destruction_provenance_from_rule_context(root_context)
    attribution = ModelDestructionAttribution(
        destroying_player_id=_payload_string(root_context, "destroying_player_id"),
        source_rules_unit_instance_id=_optional_payload_string(
            root_context,
            "source_rules_unit_instance_id",
        ),
        source_model_instance_id=_optional_payload_string(
            root_context,
            "source_model_instance_id",
        ),
        attacking_unit_instance_id=None,
        attacking_model_instance_id=None,
        destruction_provenance=provenance,
    )
    raw_destroyed_placement = root_context.get("destroyed_model_placement")
    if not isinstance(raw_destroyed_placement, dict):
        raise GameLifecycleError("Rule destruction requires exact pre-removal placement evidence.")
    destroyed_model_placement = ModelPlacement.from_payload(
        cast(ModelPlacementPayload, raw_destroyed_placement)
    )
    if (
        destroyed_model_placement.model_instance_id != model_id
        or destroyed_model_placement.unit_instance_id != physical_unit_id
    ):
        raise GameLifecycleError("Rule destruction placement identity drift.")
    destroyed_rules_unit_objective_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=rules_unit_id,
        included_destroyed_model_placement=destroyed_model_placement,
    )
    source_rules_unit_objective_witness = destruction_source_objective_proximity_witness(
        state=state,
        event_log=decisions.event_log,
        attribution=attribution,
        destroyed_model_placement=destroyed_model_placement,
    )
    destroyed_event = _append_model_destroyed(
        state=state,
        decisions=decisions,
        root_context=root_context,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _payload_string(root_context, "active_player_id"),
            "phase": _payload_string(root_context, "phase"),
            **attribution.to_payload(),
            "source_rules_unit_objective_proximity_witness": (
                None
                if source_rules_unit_objective_witness is None
                else source_rules_unit_objective_witness.to_payload()
            ),
            "destroyed_rules_unit_objective_proximity_witness": (
                destroyed_rules_unit_objective_witness.to_payload()
            ),
            "target_unit_instance_id": physical_unit_id,
            "rules_unit_instance_id": rules_unit_id,
            "model_instance_id": model_id,
            "damage_kind": None if damage is None else damage.damage_kind.value,
            "damage_event_id": None,
            "source_rule_id": _payload_string(root_context, "source_rule_id"),
            "source_effect_ids": list(_payload_identifier_list(root_context, "source_effect_ids")),
            "removal_record": removal_record.to_payload(),
            "transition_batch": transition_batch.to_payload(),
            "destroyed_model_placement": root_context.get("destroyed_model_placement"),
            "damage_application": None if damage is None else damage.to_payload(),
            "destroyed_model_rules_triggered": True,
        },
    )
    destruction_context = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                **root_context,
                "model_destroyed_event_id": destroyed_event.event_id,
                "destruction_provenance": provenance.to_payload(),
                "removal_record": removal_record.to_payload(),
                "transition_batch": transition_batch.to_payload(),
            }
        ),
    )
    mandatory_sources = _payload_source_tuple(root_context, "post_removal_mandatory_sources")
    _record_mandatory_sources_after_removal(
        state=state,
        decisions=decisions,
        sources=mandatory_sources,
        model_instance_id=model_id,
        physical_unit_instance_id=physical_unit_id,
        rules_unit_instance_id=rules_unit_id,
        model_destroyed_event_id=destroyed_event.event_id,
        provenance=provenance,
    )
    optional_sources = _active_optional_sources(
        state=state,
        decisions=decisions,
        sources=tuple(
            source
            for source in state.destruction_reaction_sources_for_model(model_instance_id=model_id)
            if source.optional
        ),
        rules_unit_instance_id=rules_unit_id,
        model_instance_id=model_id,
        model_destroyed_event_id=destroyed_event.event_id,
        provenance=provenance,
    )
    status = None
    if optional_sources:
        request = build_destruction_reaction_request(
            request_id=state.next_decision_request_id(),
            defender_player_id=_payload_string(
                root_context, "destroyed_model_controller_player_id"
            ),
            destruction_context=validate_json_value(destruction_context),
            sources=optional_sources,
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "destruction_reaction_window_opened",
            validate_json_value(
                {
                    "model_instance_id": model_id,
                    "target_unit_instance_id": physical_unit_id,
                    "rules_unit_instance_id": rules_unit_id,
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
                    "phase": _payload_string(root_context, "phase"),
                    "decision_type": request.decision_type,
                    "context_kind": RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
                    "model_destroyed_event_id": destroyed_event.event_id,
                }
            ),
        )
    else:
        status = finalize_rule_model_destruction(
            state=state,
            decisions=decisions,
            context=destruction_context,
            resume_completion_continuation=resume_completion_continuation,
        )
    return RuleModelDestructionResult(
        model_destroyed_event_id=destroyed_event.event_id,
        removal_record=removal_record,
        transition_batch=transition_batch,
        status=status,
    )


def _emit_rule_deadly_demise_resolution(
    *,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    trigger_roll_payload: JsonValue,
    triggered: bool,
    affected_target_unit_ids: tuple[str, ...],
) -> None:
    decisions.event_log.append(
        "destruction_reaction_resolved",
        validate_json_value(
            {
                "resolution_kind": "mandatory",
                "decision": None,
                "selected_source": source.to_payload(),
                "selected_reaction_kind": source.reaction_kind.value,
                "action_host": "explosion",
                "execution_status": "resolved" if triggered else "resolved_no_effect",
                "model_instance_id": _payload_string(root_context, "model_instance_id"),
                "target_unit_instance_id": _payload_string(root_context, "target_unit_instance_id"),
                "rules_unit_instance_id": _payload_string(root_context, "rules_unit_instance_id"),
                "model_destroyed_event_id": None,
                "destruction_provenance": destruction_provenance_from_rule_context(
                    root_context
                ).to_payload(),
                "battle_round": root_context.get("battle_round"),
                "deadly_demise": {
                    "descriptor": descriptor,
                    "trigger_roll": trigger_roll_payload,
                    "triggered": triggered,
                    "affected_target_unit_ids": list(affected_target_unit_ids),
                },
            }
        ),
    )


def _emit_rule_deadly_demise_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    source: DestructionReactionSource,
    target_unit_id: str,
    mortal_wounds: int,
    application: MortalWoundApplication,
    wound_roll_payload: JsonValue,
) -> None:
    decisions.event_log.append(
        "deadly_demise_mortal_wounds_applied",
        validate_json_value(
            {
                "source_result_id": _payload_string(root_context, "source_result_id"),
                "source": source.to_payload(),
                "source_rule_id": source.source_rule_id,
                "target_unit_instance_id": target_unit_id,
                "mortal_wounds": mortal_wounds,
                "mortal_wound_roll": wound_roll_payload,
                "mortal_wound_application": application.to_payload(),
            }
        ),
    )


def _continue_rule_deadly_demise_secondary_destroyed_models(
    *,
    state: GameState,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    secondary_damage_applications: tuple[DamageApplication, ...],
) -> LifecycleStatus | None:
    secondary_contexts = tuple(
        build_rule_deadly_demise_secondary_root_context(
            state=state,
            parent_root_context=root_context,
            source=source,
            damage=damage,
            completion_continuation=RuleDeadlyDemiseSecondaryContinuation(
                root_context=root_context,
                source=source,
                descriptor=descriptor,
                trigger_roll_payload=trigger_roll_payload,
                affected_target_unit_ids=affected_target_unit_ids,
                pending_target_unit_ids=pending_target_unit_ids,
                pending_sources=pending_sources,
                pending_secondary_damage_applications=secondary_damage_applications[
                    damage_index + 1 :
                ],
            ).to_payload(),
        )
        for damage_index, damage in enumerate(secondary_damage_applications)
    )
    for secondary_context in secondary_contexts:
        _reserve_destruction_cause(
            state=state,
            decisions=decisions,
            root_context=secondary_context,
        )
    for damage, secondary_context in zip(
        secondary_damage_applications,
        secondary_contexts,
        strict=True,
    ):
        sources = state.destruction_reaction_sources_for_model(
            model_instance_id=damage.model_instance_id
        )
        mandatory_status = _continue_rule_deadly_demise_sources(
            state=state,
            decisions=decisions,
            root_context=secondary_context,
            sources=tuple(
                item
                for item in sources
                if not item.optional and item.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
            ),
        )
        if mandatory_status is not None:
            return mandatory_status
        removal = _remove_rule_destroyed_model_and_continue(
            state=state,
            decisions=decisions,
            root_context=secondary_context,
            resume_completion_continuation=False,
        )
        if removal.status is not None:
            return removal.status
    return None


def _resume_rule_deadly_demise_secondary_continuation(
    *,
    state: GameState,
    decisions: DecisionController,
    continuation: dict[str, JsonValue],
) -> LifecycleStatus | None:
    restored = RuleDeadlyDemiseSecondaryContinuation.from_payload(continuation)
    root_context = restored.root_context
    _validate_pre_removal_context_matches_state(state=state, context=root_context)
    status = _continue_rule_deadly_demise_secondary_destroyed_models(
        state=state,
        decisions=decisions,
        root_context=root_context,
        source=restored.source,
        descriptor=restored.descriptor,
        trigger_roll_payload=restored.trigger_roll_payload,
        affected_target_unit_ids=restored.affected_target_unit_ids,
        pending_target_unit_ids=restored.pending_target_unit_ids,
        pending_sources=restored.pending_sources,
        secondary_damage_applications=restored.pending_secondary_damage_applications,
    )
    if status is not None:
        return status
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    status = _route_rule_deadly_demise_targets(
        state=state,
        decisions=decisions,
        manager=manager,
        root_context=root_context,
        source=restored.source,
        descriptor=restored.descriptor,
        trigger_roll_payload=restored.trigger_roll_payload,
        affected_target_unit_ids=restored.affected_target_unit_ids,
        target_unit_ids=restored.pending_target_unit_ids,
        pending_sources=restored.pending_sources,
    )
    if status is not None:
        return status
    _emit_rule_deadly_demise_resolution(
        decisions=decisions,
        root_context=root_context,
        source=restored.source,
        descriptor=restored.descriptor,
        trigger_roll_payload=restored.trigger_roll_payload,
        triggered=True,
        affected_target_unit_ids=restored.affected_target_unit_ids,
    )
    status = _continue_rule_deadly_demise_sources(
        state=state,
        decisions=decisions,
        root_context=root_context,
        sources=restored.pending_sources,
    )
    if status is not None:
        return status
    return _remove_rule_destroyed_model_and_continue(
        state=state,
        decisions=decisions,
        root_context=root_context,
    ).status


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


def rule_model_destruction_phase(request: DecisionRequest) -> BattlePhase:
    if not is_rule_model_destruction_reaction_request(request):
        raise GameLifecycleError("Rule destruction phase requires a rule destruction request.")
    phase_token = _payload_string(_destruction_context(request), "phase")
    matches = tuple(phase for phase in BattlePhase if phase.value == phase_token)
    if len(matches) != 1:
        raise GameLifecycleError("Rule destruction request phase is unsupported.")
    return matches[0]


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
) -> dict[str, JsonValue] | None:
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
            activation_result_id=(
                fight_on_death_activation_result_id_for_rule_destruction(
                    state=state,
                    context=context,
                    reaction_result_id=result.result_id,
                )
            ),
            completion_context=context,
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
    if (
        selected_source is not None
        and selected_source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH
    ):
        return context
    finalize_rule_model_destruction(state=state, decisions=decisions, context=context)
    return None


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
    _validate_post_removal_context_matches_state(
        state=state,
        decisions=decisions,
        context=context,
    )


def _validate_pre_removal_context_matches_state(
    *,
    state: GameState,
    context: dict[str, JsonValue],
) -> None:
    _validate_rule_context_identity(state=state, context=context)
    model_id = _payload_string(context, "model_instance_id")
    from warhammer40k_core.engine.damage_allocation import model_by_id

    if model_by_id(state=state, model_instance_id=model_id).is_alive:
        raise GameLifecycleError("Rule destruction model is not marked destroyed.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rule destruction requires battlefield state.")
    if battlefield.model_placement_or_none(model_id) is None:
        raise GameLifecycleError("Rule destruction pre-removal placement drift.")


def _validate_post_removal_context_matches_state(
    *,
    state: GameState,
    decisions: DecisionController | None,
    context: dict[str, JsonValue],
) -> None:
    _validate_rule_context_identity(state=state, context=context)
    model_id = _payload_string(context, "model_instance_id")
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


def _validate_rule_context_identity(
    *,
    state: GameState,
    context: dict[str, JsonValue],
) -> None:
    if context.get("game_id") != state.game_id:
        raise GameLifecycleError("Rule destruction game drift.")
    if context.get("battle_round") != state.battle_round:
        raise GameLifecycleError("Rule destruction battle round drift.")
    if context.get("active_player_id") != state.active_player_id:
        raise GameLifecycleError("Rule destruction active player drift.")
    phase = _payload_string(context, "phase")
    if state.current_battle_phase is None or state.current_battle_phase.value != phase:
        raise GameLifecycleError("Rule destruction phase drift.")
    model_id = _payload_string(context, "model_instance_id")
    if state.unit_instance_id_for_model(model_id) != _payload_string(
        context, "target_unit_instance_id"
    ):
        raise GameLifecycleError("Rule destruction physical unit drift.")
    validate_non_attack_destruction_source_context(state=state, context=context)
    validate_applied_damage_rule_destruction_context(state=state, context=context)


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


def _optional_payload_string(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _validate_identifier(key, value)


def _payload_d6_target(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or not 2 <= value <= 6:
        raise GameLifecycleError(f"Rule destruction {key} must be a D6 target.")
    return value


def _payload_positive_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Rule destruction {key} must be a positive integer.")
    return value


def _payload_positive_number(payload: dict[str, JsonValue], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise GameLifecycleError(f"Rule destruction {key} must be positive.")
    return float(value)


def _payload_object_value(payload: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Rule destruction {key} must be an object.")
    return value


def _payload_identifier_list(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Rule destruction {key} must be a list.")
    identifiers = tuple(_validate_identifier(key, item) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"Rule destruction {key} contains duplicates.")
    return identifiers


def _payload_source_tuple(
    payload: dict[str, JsonValue], key: str
) -> tuple[DestructionReactionSource, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise GameLifecycleError(f"Rule destruction {key} must be a source list.")
    return tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, item))
        for item in value
    )


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


continue_rule_deadly_demise_sources = _continue_rule_deadly_demise_sources
remove_rule_destroyed_model_and_continue = _remove_rule_destroyed_model_and_continue
_validate_identifier = IdentifierValidator(GameLifecycleError)
