"""FAQ20: finalize the completed Fight-on-Death casualty before its Deadly Demise.

The ordinary destruction owners still authenticate and consume the cause. This
module never removes a waiting casualty or grants movement to a retained model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine import model_destruction_cause_payload_validation as _mdcpv
from warhammer40k_core.engine.attack_sequence_model import (
    AttackSequenceHooks,
    DestroyedModelEmission,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
    ModelRemovalRecordPayload,
)
from warhammer40k_core.engine.damage_allocation import DamageApplication, FeelNoPainResolution
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.model_destruction_cause_authority import (
    MODEL_DESTRUCTION_CAUSE_ID_FIELD,
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_attack_permissions import RetainedAttackAction
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destruction_for_model,
    validate_retained_placement,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        ModelDestructionCauseAuthority,
    )
    from warhammer40k_core.engine.retained_destruction_state import RetainedModelDestruction

FAQ20_SOURCE_ID = "faq:ab92e97b-be2b-4125-9ded-fcfa6abe092e"


def retained_fight_removed_event(*, state: GameState, model_instance_id: str) -> EventRecord | None:
    retained = retained_destruction_for_model(state=state, model_instance_id=model_instance_id)
    if (
        retained is None
        or retained.selected_action is not RetainedAttackAction.FIGHT
        or retained.stage is not RetainedDestructionStage.REMOVED
    ):
        return None
    validate_retained_placement(state=state, record=retained)
    causes = [
        c for c in state.model_destruction_cause_authorities if c.cause_id == retained.cause_id
    ]
    if len(causes) != 1 or causes[0].model_destroyed_event is None:
        raise GameLifecycleError("Retained Fight removal lacks its consumed cause.")
    return causes[0].model_destroyed_event


def require_retained_attack_removed_cause(
    *, state: GameState, attack_sequence: AttackSequence, damage: DamageApplication
) -> ModelDestructionCauseAuthority:
    """Reuse only the consumed source of the still-active retained attack cleanup."""
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        model_destruction_cause_authority_by_id_or_none,
    )
    from warhammer40k_core.engine.model_destruction_cause_producers import (
        attack_damage_model_destruction_cause_id,
    )
    from warhammer40k_core.engine.retained_destruction_state import DestructionOwnerKind

    removed = retained_fight_removed_event(state=state, model_instance_id=damage.model_instance_id)
    retained = retained_destruction_for_model(
        state=state, model_instance_id=damage.model_instance_id
    )
    cause_id = attack_damage_model_destruction_cause_id(
        state=state, attack_sequence=attack_sequence, model_instance_id=damage.model_instance_id
    )
    cause = model_destruction_cause_authority_by_id_or_none(state=state, cause_id=cause_id)
    pending = attack_sequence.current_pending_attack_destruction
    if (
        removed is None
        or retained is None
        or retained.owner_kind is not DestructionOwnerKind.ATTACK
        or retained.cause_id != cause_id
        or cause is None
        or not cause.source_authority_finalized
        or cause.model_destroyed_event != removed
        or pending is None
        or pending.damage_application != damage
        or pending.destroyed_model_placement != retained.placement.to_payload()
        or cause.physical_unit_instance_id != retained.placement.unit_instance_id
        or cause.rules_unit_instance_id != damage.target_unit_instance_id
        or cause.producer_context.get("sequence_id") != attack_sequence.sequence_id
        or cause.producer_context.get("attack_context_id") != attack_sequence.attack_context_id()
        or cause.producer_context.get("damage_application") != damage.to_payload()
        or cause.producer_context.get("source_phase") != attack_sequence.source_phase.value
        or cause.producer_context.get("attacker_player_id") != attack_sequence.attacker_player_id
        or cause.producer_context.get("attacking_unit_instance_id")
        != attack_sequence.attacking_unit_instance_id
        or not isinstance(removed.payload, dict)
        or removed.payload.get("model_destruction_cause_id") != cause_id
        or removed.payload.get("sequence_id") != attack_sequence.sequence_id
        or removed.payload.get("attack_context_id") != attack_sequence.attack_context_id()
        or removed.payload.get("model_instance_id") != damage.model_instance_id
        or removed.payload.get("target_unit_instance_id") != damage.target_unit_instance_id
        or removed.payload.get("removal_record") != cause.producer_context.get("removal_record")
    ):
        raise GameLifecycleError("Retained attack consumed cause continuation drift.")
    return cause


def retained_fight_is_completing(*, state: GameState, model_instance_id: str) -> bool:
    retained = retained_destruction_for_model(state=state, model_instance_id=model_instance_id)
    return (
        retained is not None
        and retained.selected_action is RetainedAttackAction.FIGHT
        and retained.stage is RetainedDestructionStage.RESOLVING
    )


def finalize_attack_casualty(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    hooks: AttackSequenceHooks,
) -> DestroyedModelEmission:
    from warhammer40k_core.engine import attack_sequence_destruction_authority as authority
    from warhammer40k_core.engine.attack_sequence_hit_wound import (
        _destroyed_model_placement_payload,
        _emit_damage_event,
    )
    from warhammer40k_core.engine.damage_allocation import remove_destroyed_model_from_battlefield

    removed = retained_fight_removed_event(state=state, model_instance_id=damage.model_instance_id)
    if removed is not None:
        payload = removed.payload
        if (
            not isinstance(payload, dict)
            or payload.get("sequence_id") != attack_sequence.sequence_id
            or payload.get("model_instance_id") != damage.model_instance_id
            or payload.get("target_unit_instance_id") != damage.target_unit_instance_id
        ):
            raise GameLifecycleError("Retained attack removal continuation identity drift.")
        removal = payload.get("removal_record")
        damage_event_id = payload.get("damage_event_id")
        if not isinstance(removal, dict) or not isinstance(damage_event_id, str):
            raise GameLifecycleError("Retained attack removal artifacts are missing.")
        record = ModelRemovalRecord.from_payload(cast(ModelRemovalRecordPayload, removal))
        require_retained_attack_removed_cause(
            state=state, attack_sequence=attack_sequence, damage=damage
        )
        return DestroyedModelEmission(
            damage_event_id=damage_event_id,
            model_destroyed_event_id=removed.event_id,
            removal_record=record,
            transition_batch=BattlefieldTransitionBatch(removals=(record,)),
        )
    attribution = authority.reserved_attack_damage_destruction_attribution(
        state=state,
        attack_sequence=attack_sequence,
        damage=damage,
    )
    placement = _destroyed_model_placement_payload(
        state=state, model_instance_id=damage.model_instance_id
    )
    pending = attack_sequence.current_pending_attack_destruction
    if (
        pending is not None
        and pending.damage_application.model_instance_id == damage.model_instance_id
        and pending.destroyed_model_placement != placement
    ):
        raise GameLifecycleError("Deferred attack destruction placement drift.")
    remove_destroyed_model_from_battlefield(state=state, model_instance_id=damage.model_instance_id)
    emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        destroyed_model_placement=placement,
        destruction_attribution=attribution,
    )
    if emission is None:
        raise GameLifecycleError("Destroyed attack casualty did not emit its authority.")
    return emission


def is_post_removal_deadly_demise_child(
    *,
    state: GameState,
    parent: ModelDestructionCauseAuthority,
    child: ModelDestructionCauseAuthority,
    event_records: tuple[EventRecord, ...],
    retained_history: tuple[RetainedModelDestruction, ...],
) -> bool:
    """Authenticate FAQ20's causal descendant, independent of parent cleanup."""
    from warhammer40k_core.engine import model_destruction_cause_payload_validation as _mdcpv
    from warhammer40k_core.engine.model_destruction_cause_authority import ModelDestructionCauseKind
    from warhammer40k_core.engine.model_destruction_cause_completion_restore import (
        attack_deadly_demise_parent_and_application,
    )

    removed = parent.model_destroyed_event
    if (
        removed is None
        or child.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE
        or not any(
            record.cause_id == parent.cause_id
            and record.model_instance_id == parent.model_instance_id
            and record.selected_action is RetainedAttackAction.FIGHT
            and record.stage is RetainedDestructionStage.REMOVED
            for record in retained_history
        )
    ):
        return False
    authenticated_parent, parent_damage, applied = attack_deadly_demise_parent_and_application(
        state=state,
        authority=child,
        damage_payload=child.producer_context.get("damage_application"),
        event_records=event_records,
        require_parent_finalized=True,
    )
    if authenticated_parent != parent:
        raise GameLifecycleError("Post-removal Deadly Demise parent identity drift.")
    applied_payload = _mdcpv.json_object_value(applied.payload, "post-removal Deadly Demise")
    started = tuple(
        event
        for event in event_records
        if event.event_type == "mortal_wound_application_started"
        and isinstance(event.payload, dict)
        and isinstance(context := event.payload.get("source_context"), dict)
        and context.get("source_kind") == "deadly_demise"
        and context.get("sequence_id") == child.producer_context.get("sequence_id")
        and isinstance(attack_context := context.get("attack_context"), dict)
        and attack_context.get("attack_context_id")
        == child.producer_context.get("attack_context_id")
        and context.get("damage_application") == parent_damage.to_payload()
        and context.get("source") == applied_payload.get("source")
        and event.payload.get("target_unit_instance_id")
        == applied_payload.get("target_unit_instance_id")
    )
    if len(started) != 1:
        raise GameLifecycleError("Post-removal Deadly Demise lacks one application start.")
    if not (
        _mdcpv.event_index(event_records, removed)
        < _mdcpv.event_index(event_records, started[0])
        < _mdcpv.event_index(event_records, child.logical_death_event)
        < _mdcpv.event_index(event_records, applied)
    ):
        raise GameLifecycleError("Post-removal Deadly Demise causal chronology drift.")
    return True


def consumed_retained_rule_mortal_request(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> DecisionRequest | None:
    """Recognize only the removed retained rule source's exact mortal continuation."""
    from warhammer40k_core.engine.damage_allocation import DestructionReactionKind
    from warhammer40k_core.engine.model_destruction_cause_producers import (
        rule_effect_model_destruction_authority_context,
        rule_effect_model_destruction_cause_id,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        mortal_wound_resolution_progress,
    )
    from warhammer40k_core.engine.retained_attack_permissions import RetainedAttackAction
    from warhammer40k_core.engine.retained_destruction_state import (
        DestructionOwnerKind,
        RetainedDestructionStage,
        retained_destruction_for_model,
        validate_retained_placement,
    )
    from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
        is_rule_model_destruction_mortal_wound_request,
        rule_deadly_demise_logical_death_binding,
        rule_deadly_demise_source_context,
    )

    matches: list[DecisionRequest] = []
    for request in pending_decision_requests:
        if not is_rule_model_destruction_mortal_wound_request(request):
            continue
        source_context = rule_deadly_demise_source_context(request)
        root_context = _mdcpv.json_object_value(
            source_context.get("root_context"), "retained rule mortal root_context"
        )
        if (
            rule_effect_model_destruction_cause_id(state=state, root_context=root_context)
            == authority.cause_id
        ):
            matches.append(request)
    if not matches:
        return None
    if len(matches) != 1:
        raise GameLifecycleError("Retained rule mortal continuation is ambiguous.")
    request = matches[0]
    source_context = rule_deadly_demise_source_context(request)
    root_context = _mdcpv.json_object_value(
        source_context.get("root_context"), "retained rule mortal root_context"
    )
    retained = retained_destruction_for_model(
        state=state, model_instance_id=authority.model_instance_id
    )
    if (
        authority.cause_kind is not ModelDestructionCauseKind.RULE_EFFECT
        or not authority.source_authority_finalized
        or not authority.is_consumed
        or retained is None
        or retained.cause_id != authority.cause_id
        or retained.owner_kind is not DestructionOwnerKind.RULE
        or retained.selected_action is not RetainedAttackAction.FIGHT
        or retained.stage is not RetainedDestructionStage.REMOVED
        or retained.owner_context != root_context
        or root_context.get("game_id") != authority.game_id
        or retained.placement.unit_instance_id != authority.physical_unit_instance_id
    ):
        raise GameLifecycleError("Retained rule consumed cause continuation drift.")
    validate_retained_placement(state=state, record=retained)
    removed = _mdcpv.required_destroyed_event(authority)
    removed_payload = _mdcpv.json_object_value(removed.payload, "retained rule model_destroyed")
    expected_context = {
        **rule_effect_model_destruction_authority_context(root_context=root_context),
        "source_decision_record_ids": [
            record.record_id for record in authority.source_decision_records
        ],
        "model_destroyed_payload": {
            key: value
            for key, value in removed_payload.items()
            if key != MODEL_DESTRUCTION_CAUSE_ID_FIELD
        },
    }
    if (
        authority.producer_context != expected_context
        or root_context.get("source_result_id") != authority.producer_id
        or root_context.get("model_instance_id") != authority.model_instance_id
        or root_context.get("target_unit_instance_id") != authority.physical_unit_instance_id
        or root_context.get("rules_unit_instance_id") != authority.rules_unit_instance_id
        or removed_payload.get(MODEL_DESTRUCTION_CAUSE_ID_FIELD) != authority.cause_id
    ):
        raise GameLifecycleError("Retained rule consumed cause context drift.")
    sources = tuple(
        source
        for source in retained.sources
        if not source.optional
        and source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
        and source.to_payload() == source_context.get("source")
    )
    if len(sources) != 1:
        raise GameLifecycleError("Retained rule mortal source drift.")
    source = sources[0]
    progress = mortal_wound_resolution_progress(request)
    if (
        progress.application_id
        != (
            f"{authority.producer_id}:deadly-demise:{source.source_id}:"
            f"{progress.target_unit_instance_id}:mortal-wounds"
        )
        or progress.source_rule_id != source.source_rule_id
        or progress.target_unit_instance_id != source_context.get("current_target_unit_instance_id")
        or progress.mortal_wounds != source_context.get("current_target_mortal_wounds")
        or not progress.spill_over
        or progress.destruction_evidence is not None
        or progress.logical_death_cause_binding != rule_deadly_demise_logical_death_binding()
    ):
        raise GameLifecycleError("Retained rule mortal application binding drift.")
    request_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if (
        len(request_events) != 1
        or tuple(event for event in event_records if event.event_id == removed.event_id)
        != (removed,)
        or _mdcpv.event_index(event_records, removed)
        >= _mdcpv.event_index(event_records, request_events[0])
    ):
        raise GameLifecycleError("Retained rule consumed cause mortal request drift.")
    # The enclosing restore still authenticates retained history and the mortal
    # application/FNP allocation inventory; this only classifies its removed owner.
    return request
