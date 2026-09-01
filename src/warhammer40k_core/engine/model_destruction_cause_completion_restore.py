from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine import model_destruction_cause_payload_validation as _mdcpv
from warhammer40k_core.engine import mortal_wound_application_authority as _mwaa
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_on_death import (
    FIGHT_ON_DEATH_AWAITING_EFFECT_KIND,
)
from warhammer40k_core.engine.model_destruction_cause_attack_restore import (
    active_attack_destruction_context_ids,
    mortal_application_contains_damage,
    require_pending_attack_continuation,
    validate_pending_attack_destruction_boundary,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    MODEL_DESTROYED_EVENT_TYPE,
    MODEL_DESTRUCTION_CAUSE_ID_FIELD,
    ModelDestructionCauseAuthority,
    ModelDestructionCauseKind,
    model_destruction_cause_authority_by_id_or_none,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
        MortalWoundApplication,
    )
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
    from warhammer40k_core.engine.effects import PersistingEffect
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


def validate_pending_model_destruction_cause_inventory(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
    from warhammer40k_core.engine.damage_allocation import (
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        model_by_id,
    )
    from warhammer40k_core.engine.lifecycle_state_queries import (
        active_attack_sequence_for_state,
    )
    from warhammer40k_core.engine.model_destruction_cause_producers import (
        rule_effect_model_destruction_authority_context,
        rule_effect_model_destruction_cause_id,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
        mortal_wound_resolution_source_context,
    )
    from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
    )
    from warhammer40k_core.engine.rules_units import (
        rules_unit_owner_player_id,
        rules_unit_view_by_id,
    )

    active_attack_sequence = active_attack_sequence_for_state(state)
    expected_cause_ids: set[str] = set()
    if active_attack_sequence is not None:
        from warhammer40k_core.engine.model_destruction_cause_producers import (
            attack_damage_model_destruction_cause_id_for_context,
        )

        for pending in active_attack_sequence.pending_attack_destructions:
            validate_pending_attack_destruction_boundary(
                attack_sequence=active_attack_sequence,
                pending=pending,
                event_records=event_records,
            )
            cause_id = attack_damage_model_destruction_cause_id_for_context(
                state=state,
                sequence_id=active_attack_sequence.sequence_id,
                attack_context_id=pending.attack_context["attack_context_id"],
                model_instance_id=pending.damage_application.model_instance_id,
            )
            authority = model_destruction_cause_authority_by_id_or_none(
                state=state,
                cause_id=cause_id,
            )
            if authority is None:
                raise GameLifecycleError("Pending attack destruction cause is missing.")
            if authority.source_authority_finalized:
                if authority.model_destroyed_event is None or not any(
                    request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
                    and isinstance(request.payload, dict)
                    and isinstance(request.payload.get("destruction_context"), dict)
                    and cast(
                        dict[str, JsonValue],
                        request.payload["destruction_context"],
                    ).get("model_destroyed_event_id")
                    == authority.model_destroyed_event.event_id
                    for request in pending_decision_requests
                ):
                    raise GameLifecycleError(
                        "Finalized pending attack destruction lacks its reaction request."
                    )
            else:
                expected_cause_ids.add(
                    require_pending_attack_continuation(
                        state=state,
                        attack_sequence=active_attack_sequence,
                        event_records=event_records,
                        damage_payload=validate_json_value(pending.damage_application.to_payload()),
                        attack_context_id=pending.attack_context["attack_context_id"],
                    )
                )
    if (
        active_attack_sequence is not None
        and active_attack_sequence.pending_destroyed_transport_disembark is not None
    ):
        expected_cause_ids.add(
            require_pending_attack_continuation(
                state=state,
                attack_sequence=active_attack_sequence,
                event_records=event_records,
                damage_payload=validate_json_value(
                    active_attack_sequence.pending_destroyed_transport_disembark.damage_application.to_payload()
                ),
                attack_context_id=(
                    active_attack_sequence.pending_destroyed_transport_disembark.attack_context[
                        "attack_context_id"
                    ]
                ),
            )
        )
    for request in pending_decision_requests:
        if request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
            child_event_id = _pending_attack_deadly_demise_child_event_id_or_none(request)
            if child_event_id is not None:
                child_matches = tuple(
                    authority
                    for authority in state.model_destruction_cause_authorities
                    if authority.model_destroyed_event is not None
                    and authority.model_destroyed_event.event_id == child_event_id
                )
                if len(child_matches) != 1:
                    raise GameLifecycleError(
                        "Pending attack Deadly Demise continuation lacks its child cause."
                    )
                for parent_id in child_matches[0].parent_cause_ids:
                    parent = model_destruction_cause_authority_by_id_or_none(
                        state=state,
                        cause_id=parent_id,
                    )
                    if parent is None:
                        raise GameLifecycleError(
                            "Pending attack Deadly Demise parent cause is missing."
                        )
                    if not parent.source_authority_finalized:
                        expected_cause_ids.add(parent_id)
        if not is_mortal_wound_resolution_request(request):
            continue
        source_context = mortal_wound_resolution_source_context(request)
        if not isinstance(source_context, dict):
            continue
        source_kind = source_context.get("source_kind")
        if source_kind == DEADLY_DEMISE_SOURCE_KIND:
            if (
                active_attack_sequence is None
                or source_context.get("sequence_id") != active_attack_sequence.sequence_id
            ):
                raise GameLifecycleError("Pending attack destruction continuation drift.")
            expected_cause_ids.add(
                require_pending_attack_continuation(
                    state=state,
                    attack_sequence=active_attack_sequence,
                    event_records=event_records,
                    damage_payload=source_context.get("damage_application"),
                )
            )
        elif source_kind == RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND:
            root_context = _mdcpv.json_object_value(
                source_context.get("root_context"),
                "pending rule destruction root_context",
            )
            cause_id = rule_effect_model_destruction_cause_id(
                state=state,
                root_context=root_context,
            )
            authority = model_destruction_cause_authority_by_id_or_none(
                state=state,
                cause_id=cause_id,
            )
            if (
                authority is None
                or authority.source_authority_finalized
                or authority.producer_context
                != rule_effect_model_destruction_authority_context(root_context=root_context)
            ):
                raise GameLifecycleError("Pending rule destruction continuation drift.")
            expected_cause_ids.add(cause_id)
    for effect in state.persisting_effects:
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict) or effect_payload.get("effect_kind") != (
            FIGHT_ON_DEATH_AWAITING_EFFECT_KIND
        ):
            continue
        child_matches = tuple(
            authority
            for authority in state.model_destruction_cause_authorities
            if authority.model_destroyed_event is not None
            and effect.effect_id
            == f"fight-on-death-awaiting:{authority.model_destroyed_event.event_id}"
        )
        if len(child_matches) != 1:
            raise GameLifecycleError(
                "Fight On Death continuation lacks one consumed cause authority."
            )
        for parent_id in child_matches[0].parent_cause_ids:
            parent = model_destruction_cause_authority_by_id_or_none(
                state=state,
                cause_id=parent_id,
            )
            if parent is None:
                raise GameLifecycleError("Fight On Death continuation parent cause is missing.")
            if not parent.source_authority_finalized:
                expected_cause_ids.add(parent_id)
    pending_by_id = {
        authority.cause_id: authority
        for authority in state.model_destruction_cause_authorities
        if not authority.source_authority_finalized
    }
    pending_ancestor_ids = set(expected_cause_ids)
    queue = list(expected_cause_ids)
    while queue:
        cause_id = queue.pop()
        authority = pending_by_id.get(cause_id)
        if authority is None:
            raise GameLifecycleError("Destruction continuation lacks its pending cause authority.")
        for parent_id in authority.parent_cause_ids:
            if parent_id not in pending_by_id:
                raise GameLifecycleError("Pending destruction cause has a finalized parent.")
            if parent_id not in pending_ancestor_ids:
                pending_ancestor_ids.add(parent_id)
                queue.append(parent_id)
    if set(pending_by_id) != pending_ancestor_ids:
        raise GameLifecycleError("Pending destruction cause lacks an active continuation.")
    battlefield = state.battlefield_state
    if pending_by_id and battlefield is None:
        raise GameLifecycleError("Pending destruction cause requires battlefield state.")
    for authority in pending_by_id.values():
        model = model_by_id(state=state, model_instance_id=authority.model_instance_id)
        placement = (
            None
            if battlefield is None
            else battlefield.model_placement_or_none(authority.model_instance_id)
        )
        source_phase = authority.producer_context.get("source_phase")
        if (
            model.is_alive
            or placement is None
            or placement.unit_instance_id != authority.physical_unit_instance_id
            or state.current_battle_phase is None
            or state.current_battle_phase.value != source_phase
            or rules_unit_view_by_id(
                state=state,
                unit_instance_id=authority.physical_unit_instance_id,
            ).unit_instance_id
            != authority.rules_unit_instance_id
        ):
            raise GameLifecycleError("Pending destruction cause state binding drift.")
        if authority.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE:
            continue
        context = authority.producer_context
        if active_attack_sequence is None or (
            context.get("sequence_id") != active_attack_sequence.sequence_id
            or context.get("attack_context_id")
            not in active_attack_destruction_context_ids(active_attack_sequence)
            or context.get("attacker_player_id") != active_attack_sequence.attacker_player_id
            or context.get("attacking_unit_instance_id")
            != active_attack_sequence.attacking_unit_instance_id
            or rules_unit_owner_player_id(
                state=state,
                unit_instance_id=active_attack_sequence.attacking_unit_instance_id,
            )
            != active_attack_sequence.attacker_player_id
        ):
            raise GameLifecycleError("Pending attack destruction source binding drift.")


def validate_model_logical_death_inventory(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Bind every private logical-death boundary to one authority or pending router."""

    from warhammer40k_core.engine.damage_allocation import (
        is_mortal_wound_feel_no_pain_request,
        model_by_id,
    )
    from warhammer40k_core.engine.model_logical_death import (
        MODEL_LOGICAL_DEATH_RECORDED_EVENT,
        model_logical_death_record_from_event,
    )
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
        mortal_wound_resolution_progress,
        validate_mortal_wound_feel_no_pain_request_authority,
    )

    canonical_by_id = {event.event_id: event for event in event_records}
    if len(canonical_by_id) != len(event_records):
        raise GameLifecycleError("Logical-death event history contains duplicate IDs.")
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    application_authorities = _mwaa.mortal_wound_application_authority_inventory(
        event_records=event_records,
        game_id=state.game_id,
    )
    _mwaa.validate_mortal_wound_application_authority_closure(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
        inventory=application_authorities,
    )
    validate_attack_deadly_demise_collateral_finalization_inventory(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )
    claims_by_event_id: dict[str, str] = {}
    for authority in state.model_destruction_cause_authorities:
        _claim_logical_death_event(
            event=authority.logical_death_event,
            claimant=f"cause:{authority.cause_id}",
            canonical_by_id=canonical_by_id,
            claims_by_event_id=claims_by_event_id,
        )
    for request in pending_decision_requests:
        if not is_mortal_wound_resolution_request(request):
            continue
        progress = mortal_wound_resolution_progress(request)
        target_lineage = progress.target_lineage
        if target_lineage is None:
            raise GameLifecycleError("Pending mortal-wound progress lacks target lineage.")
        request_events = tuple(
            event
            for event in event_records
            if event.event_type == "decision_requested" and event.payload == request.to_payload()
        )
        if len(request_events) != 1:
            raise GameLifecycleError("Pending mortal-wound progress lacks one request event.")
        request_index = event_indexes[request_events[0].event_id]
        _mwaa.validate_pending_mortal_wound_application_authority(
            state=state,
            event_records=event_records,
            progress=progress,
            request_event=request_events[0],
            inventory=application_authorities,
        )
        if is_mortal_wound_feel_no_pain_request(request):
            validate_mortal_wound_feel_no_pain_request_authority(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                request=request,
                request_event=request_events[0],
            )
        for event in progress.logical_death_events:
            _claim_logical_death_event(
                event=event,
                claimant=f"pending-request:{request.request_id}",
                canonical_by_id=canonical_by_id,
                claims_by_event_id=claims_by_event_id,
            )
            if event_indexes[event.event_id] >= request_index:
                raise GameLifecycleError(
                    "Pending mortal-wound logical death must precede its request."
                )
            record = model_logical_death_record_from_event(event)
            model = model_by_id(state=state, model_instance_id=record.model_instance_id)
            battlefield = state.battlefield_state
            if battlefield is None:
                raise GameLifecycleError(
                    "Pending mortal-wound logical death requires battlefield state."
                )
            placement = battlefield.model_placement_or_none(record.model_instance_id)
            placement_matches = (
                placement == record.destroyed_model_placement
                if record.placement_retained
                else placement is None and record.model_instance_id in battlefield.removed_model_ids
            )
            if (
                model.is_alive
                or state.unit_instance_id_for_model(record.model_instance_id)
                != record.physical_unit_instance_id
                or record.rules_unit_instance_id != progress.target_unit_instance_id
                or record.physical_unit_instance_id
                not in target_lineage.component_unit_instance_ids
                or not placement_matches
            ):
                raise GameLifecycleError("Pending mortal-wound logical-death state binding drift.")
    logical_events = tuple(
        event for event in event_records if event.event_type == MODEL_LOGICAL_DEATH_RECORDED_EVENT
    )
    if len(claims_by_event_id) != len(logical_events) or any(
        event.event_id not in claims_by_event_id for event in logical_events
    ):
        raise GameLifecycleError("Every model logical-death event must have exactly one authority.")


def _claim_logical_death_event(
    *,
    event: EventRecord,
    claimant: str,
    canonical_by_id: dict[str, EventRecord],
    claims_by_event_id: dict[str, str],
) -> None:
    from warhammer40k_core.engine.model_logical_death import (
        model_logical_death_record_from_event,
    )

    model_logical_death_record_from_event(event)
    if canonical_by_id.get(event.event_id) != event:
        raise GameLifecycleError("Model logical-death event authority drift.")
    existing = claims_by_event_id.get(event.event_id)
    if existing is not None:
        raise GameLifecycleError("Model logical-death event has more than one authority.")
    claims_by_event_id[event.event_id] = claimant


def mortal_wound_completion_event_for_restore(
    *,
    authority: ModelDestructionCauseAuthority,
    destroyed_event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> EventRecord:
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionFinalizationKind,
        mortal_wound_destruction_finalization_kind_from_event,
    )

    matches = tuple(
        event
        for event in event_records
        if event.event_type == "mortal_wound_model_destructions_finalized"
        and mortal_wound_destruction_finalization_kind_from_event(event)
        is MortalWoundDestructionFinalizationKind.APPLICATION_PACKET
        and isinstance(event.payload, dict)
        and event.payload.get("application_id") == authority.producer_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Mortal-wound destruction lacks one canonical completion event.")
    if _mdcpv.event_index(event_records, matches[0]) <= _mdcpv.event_index(
        event_records, destroyed_event
    ):
        raise GameLifecycleError(
            "Mortal-wound destruction completion must follow model destruction."
        )
    return matches[0]


def validate_mortal_wound_completion_inventory(
    *,
    state: GameState,
    application_id: str,
    event_records: tuple[EventRecord, ...],
    destroyed_model_ids: tuple[str, ...],
    destroyed_event_ids: tuple[str, ...],
    source_rule_id: str,
    source_context: JsonValue,
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, JsonValue]]:
    requested_application_id = _mdcpv.json_identifier(
        {"application_id": application_id},
        "application_id",
        "mortal-wound completion",
    )
    if tuple(sorted(destroyed_model_ids)) != destroyed_model_ids:
        raise GameLifecycleError("Mortal-wound completion model inventory is non-canonical.")
    events_by_id = {event.event_id: event for event in event_records}
    if len(events_by_id) != len(event_records):
        raise GameLifecycleError("Mortal-wound completion event history is duplicated.")
    physical_unit_ids: set[str] = set()
    rules_unit_ids: set[str] = set()
    removal_payloads: list[dict[str, JsonValue]] = []
    for model_id, event_id in zip(destroyed_model_ids, destroyed_event_ids, strict=True):
        event = events_by_id.get(event_id)
        if event is None or event.event_type != MODEL_DESTROYED_EVENT_TYPE:
            raise GameLifecycleError("Mortal-wound completion references a missing destruction.")
        payload = _mdcpv.json_object_value(event.payload, "mortal-wound completion destruction")
        placement = _mdcpv.json_object_value(
            payload.get("destroyed_model_placement"),
            "mortal-wound completion destroyed placement",
        )
        removal = _mdcpv.json_object_value(
            payload.get("removal_record"),
            "mortal-wound completion removal record",
        )
        physical_unit_id = _mdcpv.json_identifier(
            placement,
            "unit_instance_id",
            "mortal-wound completion destroyed placement",
        )
        rules_unit_id = _mdcpv.json_identifier(
            payload,
            "rules_unit_instance_id",
            "mortal-wound completion destruction",
        )
        raw_cause_id = payload.get(MODEL_DESTRUCTION_CAUSE_ID_FIELD)
        linked_cause = (
            None
            if type(raw_cause_id) is not str
            else model_destruction_cause_authority_by_id_or_none(
                state=state,
                cause_id=raw_cause_id,
            )
        )
        if (
            payload.get("model_instance_id") != model_id
            or placement.get("model_instance_id") != model_id
            or payload.get("target_unit_instance_id") != physical_unit_id
            or payload.get("mortal_wound_application_id") != requested_application_id
            or payload.get("source_rule_id") != source_rule_id
            or payload.get("source_context") != source_context
            or linked_cause is None
            or linked_cause.cause_kind is not ModelDestructionCauseKind.MORTAL_WOUND
            or linked_cause.producer_id != requested_application_id
            or linked_cause.model_instance_id != model_id
            or linked_cause.physical_unit_instance_id != physical_unit_id
            or linked_cause.rules_unit_instance_id != rules_unit_id
            or linked_cause.model_destroyed_event != event
            or removal.get("model_instance_id") != model_id
        ):
            raise GameLifecycleError("Mortal-wound completion destruction binding drift.")
        physical_unit_ids.add(physical_unit_id)
        rules_unit_ids.add(rules_unit_id)
        removal_payloads.append(removal)
    application_event_ids = tuple(
        event.event_id
        for event in event_records
        if event.event_type == MODEL_DESTROYED_EVENT_TYPE
        and isinstance(event.payload, dict)
        and event.payload.get("mortal_wound_application_id") == requested_application_id
    )
    if application_event_ids != destroyed_event_ids:
        raise GameLifecycleError("Mortal-wound completion event inventory drift.")
    transition = validate_json_value(
        {
            "placements": [],
            "removals": removal_payloads,
            "displacements": [],
        }
    )
    if not isinstance(transition, dict):
        raise GameLifecycleError("Mortal-wound completion transition is invalid.")
    return tuple(sorted(physical_unit_ids)), tuple(sorted(rules_unit_ids)), transition


def validate_mortal_wound_application_inventory(
    *,
    state: GameState,
    application: MortalWoundApplication,
    destroyed_model_ids: tuple[str, ...],
    destroyed_event_ids: tuple[str, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.engine.rules_units import (
        current_rules_unit_views_for_canonical_identity,
    )

    target_views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=application.target_unit_instance_id,
    )
    destroyed_applications_by_model: dict[str, DamageApplication] = {}
    for item in application.applications:
        physical_unit_id = state.unit_instance_id_for_model(item.model_instance_id)
        if item.target_unit_instance_id != application.target_unit_instance_id or all(
            physical_unit_id not in view.component_unit_instance_ids for view in target_views
        ):
            raise GameLifecycleError("Mortal-wound application target inventory drift.")
        if not item.destroyed:
            continue
        if item.model_instance_id in destroyed_applications_by_model:
            raise GameLifecycleError("Mortal-wound destroyed application models are duplicated.")
        destroyed_applications_by_model[item.model_instance_id] = item
    application_destroyed_ids = tuple(sorted(destroyed_applications_by_model))
    if application_destroyed_ids != destroyed_model_ids:
        raise GameLifecycleError("Mortal-wound destroyed application inventory drift.")
    events_by_id = {event.event_id: event for event in event_records}
    for model_id, event_id in zip(destroyed_model_ids, destroyed_event_ids, strict=True):
        event = events_by_id.get(event_id)
        payload = None if event is None else event.payload
        if (
            not isinstance(payload, dict)
            or payload.get("damage_application")
            != destroyed_applications_by_model[model_id].to_payload()
        ):
            raise GameLifecycleError("Mortal-wound destroyed damage application drift.")


def validate_attack_deadly_demise_collateral_finalization_inventory(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Bind every attack Deadly Demise casualty aggregate to its exact child cause."""

    from warhammer40k_core.engine.damage_allocation import (
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    )
    from warhammer40k_core.engine.destruction_provenance import (
        DestructionSourceKind,
        ModelDestructionAttribution,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
        MortalWoundDestructionFinalizationKind,
        mortal_wound_destruction_finalization_kind_from_event,
    )

    collateral_events: list[EventRecord] = []
    for event in event_records:
        if event.event_type != MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT:
            continue
        if mortal_wound_destruction_finalization_kind_from_event(event) is (
            MortalWoundDestructionFinalizationKind.DEADLY_DEMISE_COLLATERAL_CAUSE
        ):
            collateral_events.append(event)
    child_authorities: list[ModelDestructionCauseAuthority] = []
    for authority in state.model_destruction_cause_authorities:
        destroyed_event = authority.model_destroyed_event
        if (
            authority.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE
            or not authority.source_authority_finalized
            or destroyed_event is None
        ):
            continue
        destroyed_payload = _mdcpv.json_object_value(
            destroyed_event.payload,
            "attack Deadly Demise collateral destruction",
        )
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
        if attribution.destruction_provenance.destruction_source_kind is (
            DestructionSourceKind.DEADLY_DEMISE
        ):
            child_authorities.append(authority)

    pending_by_child_event_id: dict[str, list[DecisionRequest]] = {}
    for request in pending_decision_requests:
        if request.decision_type != SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
            continue
        child_event_id = _pending_attack_deadly_demise_child_event_id_or_none(request)
        if child_event_id is None:
            continue
        pending_by_child_event_id.setdefault(child_event_id, []).append(request)

    claimed_event_ids: set[str] = set()
    claimed_pending_child_ids: set[str] = set()
    for authority in child_authorities:
        destroyed_event = _mdcpv.required_destroyed_event(authority)
        expected_application_id = f"{destroyed_event.event_id}:deadly-demise-finalization"
        matching_events = tuple(
            event
            for event in collateral_events
            if isinstance(event.payload, dict)
            and event.payload.get("application_id") == expected_application_id
        )
        pending_requests = tuple(pending_by_child_event_id.get(destroyed_event.event_id, ()))
        if len(matching_events) + len(pending_requests) != 1:
            raise GameLifecycleError(
                "Attack Deadly Demise collateral cause lacks exactly one continuation."
            )
        if matching_events:
            event = matching_events[0]
            _validate_attack_deadly_demise_collateral_finalization(
                state=state,
                authority=authority,
                event=event,
                event_records=event_records,
            )
            if event.event_id in claimed_event_ids:
                raise GameLifecycleError(
                    "Attack Deadly Demise collateral finalization was claimed twice."
                )
            claimed_event_ids.add(event.event_id)
            continue
        _validate_pending_attack_deadly_demise_collateral_continuation(
            state=state,
            authority=authority,
            request=pending_requests[0],
            event_records=event_records,
        )
        claimed_pending_child_ids.add(destroyed_event.event_id)
    if len(claimed_event_ids) != len(collateral_events):
        raise GameLifecycleError(
            "Attack Deadly Demise collateral finalization lacks one child cause."
        )
    if set(pending_by_child_event_id) != claimed_pending_child_ids:
        raise GameLifecycleError(
            "Pending attack Deadly Demise collateral continuation lacks one child cause."
        )


def _validate_attack_deadly_demise_collateral_finalization(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.core.ruleset_descriptor import (
        battle_phase_kind_from_token,
    )
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldRemovalKind,
        BattlefieldTransitionBatch,
        ModelRemovalRecord,
    )
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
        DestructionReactionSourcePayload,
    )
    from warhammer40k_core.engine.destruction_provenance import (
        ModelDestructionAttribution,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionFinalizationKind,
    )

    destroyed_event = _mdcpv.required_destroyed_event(authority)
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "attack Deadly Demise collateral destruction",
    )
    damage = _mdcpv.parse_damage_application(authority.producer_context.get("damage_application"))
    parent, parent_damage, applied_event = _attack_deadly_demise_parent_and_application(
        state=state,
        authority=authority,
        damage_payload=validate_json_value(damage.to_payload()),
        event_records=event_records,
        require_parent_finalized=True,
    )
    applied_payload = _mdcpv.json_object_value(
        applied_event.payload,
        "attack Deadly Demise mortal-wound application",
    )
    source_payload = _mdcpv.json_object_value(
        applied_payload.get("source"),
        "attack Deadly Demise source",
    )
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, source_payload)
    )
    if (
        source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE
        or source
        not in state.destruction_reaction_sources_for_model(
            model_instance_id=parent.model_instance_id
        )
    ):
        raise GameLifecycleError("Attack Deadly Demise collateral source drift.")
    payload = _mdcpv.json_object_value(
        event.payload,
        "attack Deadly Demise collateral finalization",
    )
    expected_fields = {
        "game_id",
        "battle_round",
        "active_player_id",
        "application_id",
        "finalization_kind",
        "source_rule_id",
        "source_context",
        "target_unit_instance_id",
        "destroyed_model_instance_ids",
        "model_destroyed_event_ids",
        "physical_unit_instance_ids",
        "rules_unit_instance_ids",
        "application",
        "destruction_evidence",
        "transition_batch",
    }
    if set(payload) != expected_fields:
        raise GameLifecycleError("Attack Deadly Demise collateral finalization fields are invalid.")
    evidence = _mdcpv.parse_mortal_wound_destruction_evidence(payload.get("destruction_evidence"))
    evidence.validate_for_state(state)
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    expected_application_id = f"{destroyed_event.event_id}:deadly-demise-finalization"
    expected_removal = ModelRemovalRecord(
        model_instance_id=authority.model_instance_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        source_phase=evidence.parent_battle_phase.value,
        source_step="deadly_demise_collateral",
        source_rule_id=source.source_rule_id,
        source_event_id=expected_application_id,
    )
    expected_transition = BattlefieldTransitionBatch(removals=(expected_removal,)).to_payload()
    expected_source_context: dict[str, JsonValue] = {
        "sequence_id": authority.producer_context.get("sequence_id"),
        "attack_context_id": authority.producer_context.get("attack_context_id"),
        "model_destroyed_event_id": destroyed_event.event_id,
        "source_damage_application": validate_json_value(parent_damage.to_payload()),
        "deadly_demise_source": validate_json_value(source.to_payload()),
    }
    expected_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": destroyed_payload.get("battle_round"),
        "active_player_id": destroyed_payload.get("active_player_id"),
        "application_id": expected_application_id,
        "finalization_kind": (
            MortalWoundDestructionFinalizationKind.DEADLY_DEMISE_COLLATERAL_CAUSE.value
        ),
        "source_rule_id": source.source_rule_id,
        "source_context": validate_json_value(expected_source_context),
        "target_unit_instance_id": damage.target_unit_instance_id,
        "destroyed_model_instance_ids": [authority.model_instance_id],
        "model_destroyed_event_ids": [destroyed_event.event_id],
        "physical_unit_instance_ids": [authority.physical_unit_instance_id],
        "rules_unit_instance_ids": [authority.rules_unit_instance_id],
        "application": validate_json_value({"applications": [damage.to_payload()]}),
        "destruction_evidence": validate_json_value(evidence.to_payload()),
        "transition_batch": validate_json_value(expected_transition),
    }
    event_indexes = {record.event_id: index for index, record in enumerate(event_records)}
    if (
        payload != expected_payload
        or evidence.destruction_attribution != attribution
        or evidence.action_phase
        is not battle_phase_kind_from_token(
            _mdcpv.json_identifier(
                authority.producer_context,
                "source_phase",
                "attack Deadly Demise collateral cause",
            )
        )
        or evidence.source_step != "deadly_demise_collateral"
        or event_indexes[applied_event.event_id] >= event_indexes[destroyed_event.event_id]
        or event_indexes[destroyed_event.event_id] >= event_indexes[event.event_id]
    ):
        raise GameLifecycleError("Attack Deadly Demise collateral finalization binding drift.")


def _pending_attack_deadly_demise_child_event_id_or_none(
    request: DecisionRequest,
) -> str | None:
    from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND

    request_payload = request.payload
    if not isinstance(request_payload, dict):
        raise GameLifecycleError("Pending destruction reaction payload must be an object.")
    destruction_context = request_payload.get("destruction_context")
    if not isinstance(destruction_context, dict):
        raise GameLifecycleError("Pending destruction reaction context must be an object.")
    continuation = destruction_context.get("continuation")
    if not isinstance(continuation, dict) or continuation.get("source_kind") != (
        DEADLY_DEMISE_SOURCE_KIND
    ):
        return None
    if continuation.get("continuation_kind") != "secondary_destroyed_model_reaction":
        raise GameLifecycleError("Pending attack Deadly Demise continuation kind drift.")
    return _mdcpv.json_identifier(
        continuation,
        "resolved_secondary_model_destroyed_event_id",
        "pending attack Deadly Demise continuation",
    )


def _validate_pending_attack_deadly_demise_collateral_continuation(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    request: DecisionRequest,
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionSourcePayload,
    )
    from warhammer40k_core.engine.destruction_provenance import (
        ModelDestructionAttribution,
    )
    from warhammer40k_core.engine.lifecycle_state_queries import (
        active_attack_sequence_for_state,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_owner_player_id

    destroyed_event = _mdcpv.required_destroyed_event(authority)
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "pending attack Deadly Demise collateral destruction",
    )
    damage = _mdcpv.parse_damage_application(authority.producer_context.get("damage_application"))
    _parent, parent_damage, applied_event = _attack_deadly_demise_parent_and_application(
        state=state,
        authority=authority,
        damage_payload=validate_json_value(damage.to_payload()),
        event_records=event_records,
        require_parent_finalized=False,
    )
    applied_payload = _mdcpv.json_object_value(
        applied_event.payload,
        "pending attack Deadly Demise mortal-wound application",
    )
    source_payload = _mdcpv.json_object_value(
        applied_payload.get("source"),
        "pending attack Deadly Demise source",
    )
    # Parse here so malformed nested source evidence fails before comparison.
    from warhammer40k_core.engine.damage_allocation import DestructionReactionSource

    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, source_payload)
    )
    request_payload = _mdcpv.json_object_value(
        request.payload,
        "pending attack Deadly Demise request",
    )
    destruction_context = _mdcpv.json_object_value(
        request_payload.get("destruction_context"),
        "pending attack Deadly Demise destruction context",
    )
    continuation = _mdcpv.json_object_value(
        destruction_context.get("continuation"),
        "pending attack Deadly Demise continuation",
    )
    context_fields = {
        "context_kind",
        "attack_context",
        "destruction_provenance",
        "damage_application",
        "model_destroyed_event_id",
        "damage_event_id",
        "target_unit_instance_id",
        "model_instance_id",
        "destroyed_model_controller_player_id",
        "source_phase",
        "source_step",
        "removal_record",
        "transition_batch",
        "destroyed_model_rules_triggered",
        "continuation",
    }
    continuation_fields = {
        "source_kind",
        "continuation_kind",
        "attack_context",
        "damage_application",
        "resolved_secondary_damage_application",
        "resolved_secondary_model_destroyed_event_id",
        "saving_throw",
        "feel_no_pain",
        "source",
        "descriptor",
        "destroyed_model_controller_player_id",
        "trigger_roll",
        "affected_target_unit_ids",
        "pending_target_unit_ids",
        "pending_sources",
        "pending_secondary_damage_applications",
    }
    attack_context = _mdcpv.json_object_value(
        destruction_context.get("attack_context"),
        "pending attack Deadly Demise attack context",
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    active_attack_sequence = active_attack_sequence_for_state(state)
    request_events = tuple(
        event
        for event in event_records
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    expected_owner = rules_unit_owner_player_id(
        state=state,
        unit_instance_id=authority.physical_unit_instance_id,
    )
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    if (
        set(destruction_context) != context_fields
        or set(continuation) != continuation_fields
        or destruction_context.get("context_kind") != "attack_sequence_model_destroyed"
        or destruction_context.get("destruction_provenance")
        != attribution.destruction_provenance.to_payload()
        or destruction_context.get("damage_application") != damage.to_payload()
        or destruction_context.get("model_destroyed_event_id") != destroyed_event.event_id
        or destruction_context.get("damage_event_id") != destroyed_payload.get("damage_event_id")
        or destruction_context.get("target_unit_instance_id") != damage.target_unit_instance_id
        or destruction_context.get("model_instance_id") != authority.model_instance_id
        or destruction_context.get("destroyed_model_controller_player_id") != expected_owner
        or destruction_context.get("source_phase") != authority.producer_context.get("source_phase")
        or destruction_context.get("source_step") != "damage"
        or destruction_context.get("removal_record") != destroyed_payload.get("removal_record")
        or destruction_context.get("transition_batch") != destroyed_payload.get("transition_batch")
        or destruction_context.get("destroyed_model_rules_triggered") is not True
        or continuation.get("source_kind") != DEADLY_DEMISE_SOURCE_KIND
        or continuation.get("continuation_kind") != "secondary_destroyed_model_reaction"
        or continuation.get("attack_context") != attack_context
        or continuation.get("damage_application") != parent_damage.to_payload()
        or continuation.get("resolved_secondary_damage_application") != damage.to_payload()
        or continuation.get("resolved_secondary_model_destroyed_event_id")
        != destroyed_event.event_id
        or continuation.get("source") != source.to_payload()
        or continuation.get("destroyed_model_controller_player_id")
        != attribution.destroying_player_id
        or request.actor_id != expected_owner
        or active_attack_sequence is None
        or active_attack_sequence.sequence_id != authority.producer_context.get("sequence_id")
        or active_attack_sequence.attack_context_id()
        != authority.producer_context.get("attack_context_id")
        or len(request_events) != 1
        or event_indexes[destroyed_event.event_id] >= event_indexes[request_events[0].event_id]
    ):
        raise GameLifecycleError(
            "Pending attack Deadly Demise collateral continuation binding drift."
        )


def _attack_deadly_demise_parent_and_application(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    damage_payload: JsonValue,
    event_records: tuple[EventRecord, ...],
    require_parent_finalized: bool,
) -> tuple[ModelDestructionCauseAuthority, DamageApplication, EventRecord]:
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
        DestructionReactionSourcePayload,
    )

    if len(authority.parent_cause_ids) != 1:
        raise GameLifecycleError("Attack Deadly Demise collateral parent cause drift.")
    parent = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=authority.parent_cause_ids[0],
    )
    if (
        parent is None
        or parent.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE
        or parent.producer_id != authority.producer_id
        or (require_parent_finalized and not parent.source_authority_finalized)
    ):
        raise GameLifecycleError("Attack Deadly Demise collateral parent authority drift.")
    parent_damage = _mdcpv.parse_damage_application(
        parent.producer_context.get("damage_application")
    )
    applied_events = tuple(
        event
        for event in event_records
        if event.event_type == "deadly_demise_mortal_wounds_applied"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == authority.producer_context.get("sequence_id")
        and event.payload.get("attack_context_id")
        == authority.producer_context.get("attack_context_id")
        and event.payload.get("target_unit_instance_id")
        == _mdcpv.json_object_value(
            damage_payload,
            "attack Deadly Demise collateral damage",
        ).get("target_unit_instance_id")
        and mortal_application_contains_damage(
            event.payload.get("mortal_wound_application"),
            damage_payload=damage_payload,
        )
    )
    if len(applied_events) != 1:
        raise GameLifecycleError(
            "Attack Deadly Demise collateral application authority is ambiguous."
        )
    applied_payload = _mdcpv.json_object_value(
        applied_events[0].payload,
        "attack Deadly Demise collateral application",
    )
    source_payload = _mdcpv.json_object_value(
        applied_payload.get("source"),
        "attack Deadly Demise collateral source",
    )
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, source_payload)
    )
    if (
        source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE
        or applied_payload.get("source_rule_id") != source.source_rule_id
        or source
        not in state.destruction_reaction_sources_for_model(
            model_instance_id=parent.model_instance_id
        )
    ):
        raise GameLifecycleError("Attack Deadly Demise collateral application source drift.")
    return parent, parent_damage, applied_events[0]


def validate_rule_effect_completion_or_pending_window(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    attribution: ModelDestructionAttribution,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    destroyed_event = _mdcpv.required_destroyed_event(authority)
    context = authority.producer_context
    finalization_events = tuple(
        event
        for event in event_records
        if event.event_type == "rule_model_destruction_finalized"
        and isinstance(event.payload, dict)
        and event.payload.get("model_destroyed_event_id") == destroyed_event.event_id
    )
    pending_request_values: list[DecisionRequest] = []
    for request in pending_decision_requests:
        request_payload = request.payload
        if not isinstance(request_payload, dict):
            continue
        request_context = request_payload.get("destruction_context")
        if (
            isinstance(request_context, dict)
            and request_context.get("context_kind") == "rule_model_destroyed"
            and request_context.get("model_destroyed_event_id") == destroyed_event.event_id
        ):
            pending_request_values.append(request)
    pending_requests = tuple(pending_request_values)
    awaiting_effects = tuple(
        effect
        for effect in state.persisting_effects
        if effect.effect_id == f"fight-on-death-awaiting:{destroyed_event.event_id}"
    )
    if len(finalization_events) == 1 and not pending_requests and not awaiting_effects:
        event = finalization_events[0]
        payload = _mdcpv.json_object_value(event.payload, "rule destruction finalization")
        destroyed_payload = _mdcpv.json_object_value(
            destroyed_event.payload,
            "rule model_destroyed",
        )
        expected_payload = {
            "game_id": authority.game_id,
            "battle_round": destroyed_payload.get("battle_round"),
            "phase": context.get("source_phase"),
            "model_destroyed_event_id": destroyed_event.event_id,
            "model_instance_id": authority.model_instance_id,
            "physical_unit_instance_id": authority.physical_unit_instance_id,
            "rules_unit_instance_id": authority.rules_unit_instance_id,
            "completion_kind": context.get("completion_kind"),
        }
        if (
            _mdcpv.event_index(event_records, event)
            <= _mdcpv.event_index(event_records, destroyed_event)
            or payload != expected_payload
        ):
            raise GameLifecycleError("Rule destruction finalization binding drift.")
        _validate_rule_mode_completion_event(
            authority=authority,
            destroyed_event=destroyed_event,
            generic_finalization_event=event,
            event_records=event_records,
        )
        return
    if finalization_events or (pending_requests and awaiting_effects):
        raise GameLifecycleError("Rule destruction completion authority is ambiguous.")
    _require_rule_mode_completion_absent(
        authority=authority,
        destroyed_event=destroyed_event,
        event_records=event_records,
    )
    if not pending_requests:
        if len(awaiting_effects) != 1:
            raise GameLifecycleError("Rule destruction completion authority is ambiguous.")
        _validate_pending_rule_fight_on_death_effect(
            authority=authority,
            attribution=attribution,
            destroyed_event=destroyed_event,
            effect=awaiting_effects[0],
            event_records=event_records,
        )
        return
    if len(pending_requests) != 1 or awaiting_effects:
        raise GameLifecycleError("Rule destruction completion authority is ambiguous.")
    request = pending_requests[0]
    request_payload = _mdcpv.json_object_value(
        request.payload,
        "pending rule destruction request",
    )
    destruction_context = _mdcpv.json_object_value(
        request_payload.get("destruction_context"),
        "pending rule destruction context",
    )
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "pending rule model_destroyed",
    )
    if (
        destruction_context.get("game_id") != authority.game_id
        or destruction_context.get("completion_kind") != context.get("completion_kind")
        or destruction_context.get("source_rule_id") != context.get("source_rule_id")
        or destruction_context.get("source_result_id") != authority.producer_id
        or destruction_context.get("source_effect_ids") != context.get("source_effect_ids")
        or destruction_context.get("model_instance_id") != authority.model_instance_id
        or destruction_context.get("target_unit_instance_id") != authority.physical_unit_instance_id
        or destruction_context.get("rules_unit_instance_id") != authority.rules_unit_instance_id
        or destruction_context.get("damage_application") != context.get("damage_application")
        or destruction_context.get("destruction_provenance")
        != attribution.destruction_provenance.to_payload()
        or destruction_context.get("removal_record") != destroyed_payload.get("removal_record")
        or destruction_context.get("transition_batch") != destroyed_payload.get("transition_batch")
    ):
        raise GameLifecycleError("Pending rule destruction reaction context drift.")
    window_events = tuple(
        event
        for event in event_records
        if event.event_type == "destruction_reaction_window_opened"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request.request_id
        and event.payload.get("model_destroyed_event_id") == destroyed_event.event_id
    )
    if len(window_events) != 1:
        raise GameLifecycleError("Pending rule destruction lacks its reaction window.")
    window_payload = _mdcpv.json_object_value(
        window_events[0].payload,
        "rule destruction reaction window",
    )
    if (
        _mdcpv.event_index(event_records, window_events[0])
        <= _mdcpv.event_index(event_records, destroyed_event)
        or window_payload.get("model_instance_id") != authority.model_instance_id
        or window_payload.get("target_unit_instance_id") != authority.physical_unit_instance_id
        or window_payload.get("rules_unit_instance_id") != authority.rules_unit_instance_id
        or window_payload.get("destruction_provenance")
        != attribution.destruction_provenance.to_payload()
    ):
        raise GameLifecycleError("Rule destruction reaction window binding drift.")


def _validate_pending_rule_fight_on_death_effect(
    *,
    authority: ModelDestructionCauseAuthority,
    attribution: ModelDestructionAttribution,
    destroyed_event: EventRecord,
    effect: PersistingEffect,
    event_records: tuple[EventRecord, ...],
) -> None:
    context = authority.producer_context
    payload = _mdcpv.json_object_value(
        effect.effect_payload,
        "pending rule Fight On Death effect",
    )
    completion_context = _mdcpv.json_object_value(
        payload.get("completion_context"),
        "pending rule Fight On Death completion context",
    )
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "pending rule Fight On Death model_destroyed",
    )
    awaiting_events = tuple(
        event
        for event in event_records
        if event.event_type == "fight_on_death_model_awaiting_attack"
        and isinstance(event.payload, dict)
        and event.payload.get("effect_id") == effect.effect_id
    )
    if len(awaiting_events) != 1:
        raise GameLifecycleError("Pending rule Fight On Death lacks one canonical awaiting event.")
    awaiting_event = awaiting_events[0]
    awaiting_payload = _mdcpv.json_object_value(
        awaiting_event.payload,
        "pending rule Fight On Death awaiting event",
    )
    attribution_payload = attribution.to_payload()
    if (
        payload.get("effect_kind") != FIGHT_ON_DEATH_AWAITING_EFFECT_KIND
        or payload.get("model_instance_id") != authority.model_instance_id
        or type(payload.get("activation_result_id")) is not str
        or not payload.get("activation_result_id")
        or effect.target_unit_instance_ids != (authority.physical_unit_instance_id,)
        or _mdcpv.event_index(event_records, awaiting_event)
        <= _mdcpv.event_index(event_records, destroyed_event)
        or awaiting_payload.get("game_id") != authority.game_id
        or awaiting_payload.get("battle_round") != destroyed_payload.get("battle_round")
        or awaiting_payload.get("phase") != context.get("source_phase")
        or awaiting_payload.get("model_instance_id") != authority.model_instance_id
        or awaiting_payload.get("unit_instance_id") != authority.physical_unit_instance_id
        or type(awaiting_payload.get("source_id")) is not str
        or not awaiting_payload.get("source_id")
        or awaiting_payload.get("source_rule_id") != effect.source_rule_id
        or awaiting_payload.get("effect_id") != effect.effect_id
        or awaiting_payload.get("model_placement") != context.get("destroyed_model_placement")
        or completion_context.get("context_kind") != "rule_model_destroyed"
        or completion_context.get("game_id") != authority.game_id
        or completion_context.get("completion_kind") != context.get("completion_kind")
        or completion_context.get("completion_event_type") != context.get("completion_event_type")
        or completion_context.get("completion_event_payload")
        != context.get("completion_event_payload")
        or completion_context.get("source_rule_id") != context.get("source_rule_id")
        or completion_context.get("source_result_id") != authority.producer_id
        or completion_context.get("source_effect_ids") != context.get("source_effect_ids")
        or completion_context.get("phase") != context.get("source_phase")
        or completion_context.get("source_step") != context.get("source_step")
        or completion_context.get("model_instance_id") != authority.model_instance_id
        or completion_context.get("target_unit_instance_id") != authority.physical_unit_instance_id
        or completion_context.get("rules_unit_instance_id") != authority.rules_unit_instance_id
        or completion_context.get("destroyed_model_placement")
        != context.get("destroyed_model_placement")
        or completion_context.get("damage_application") != context.get("damage_application")
        or completion_context.get("model_destroyed_event_id") != destroyed_event.event_id
        or completion_context.get("removal_record") != destroyed_payload.get("removal_record")
        or completion_context.get("transition_batch") != destroyed_payload.get("transition_batch")
        or any(completion_context.get(key) != value for key, value in attribution_payload.items())
        or completion_context.get("destroyed_model_controller_player_id") != effect.owner_player_id
    ):
        raise GameLifecycleError("Pending rule Fight On Death authority binding drift.")


def _validate_rule_mode_completion_event(
    *,
    authority: ModelDestructionCauseAuthority,
    destroyed_event: EventRecord,
    generic_finalization_event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    expected = _rule_mode_completion_identity(
        authority=authority,
        destroyed_event=destroyed_event,
    )
    if expected is None:
        return
    event_type, event_payload = expected
    matches = tuple(
        event
        for event in event_records
        if event.event_type == event_type and event.payload == event_payload
    )
    if (
        len(matches) != 1
        or _mdcpv.event_index(event_records, matches[0])
        <= _mdcpv.event_index(event_records, destroyed_event)
        or _mdcpv.event_index(event_records, matches[0])
        >= _mdcpv.event_index(event_records, generic_finalization_event)
    ):
        raise GameLifecycleError("Rule destruction mode completion event drift.")


def _require_rule_mode_completion_absent(
    *,
    authority: ModelDestructionCauseAuthority,
    destroyed_event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    expected = _rule_mode_completion_identity(
        authority=authority,
        destroyed_event=destroyed_event,
    )
    if expected is None:
        return
    event_type, event_payload = expected
    if any(
        event.event_type == event_type and event.payload == event_payload for event in event_records
    ):
        raise GameLifecycleError("Pending rule destruction completed its producer event early.")


def _rule_mode_completion_identity(
    *,
    authority: ModelDestructionCauseAuthority,
    destroyed_event: EventRecord,
) -> tuple[str, dict[str, JsonValue]] | None:
    context = authority.producer_context
    event_type = context.get("completion_event_type")
    raw_payload = context.get("completion_event_payload")
    if event_type is None and raw_payload is None:
        if context.get("completion_kind") != "deadly_demise_collateral":
            raise GameLifecycleError("Rule destruction completion event identity is missing.")
        return None
    if type(event_type) is not str or not event_type or not isinstance(raw_payload, dict):
        raise GameLifecycleError("Rule destruction completion event identity is invalid.")
    payload = validate_json_value(
        {
            **raw_payload,
            "model_destroyed_event_id": destroyed_event.event_id,
        }
    )
    if not isinstance(payload, dict):
        raise GameLifecycleError("Rule destruction completion event payload is invalid.")
    return event_type, payload


__all__ = (
    "mortal_wound_completion_event_for_restore",
    "validate_model_logical_death_inventory",
    "validate_mortal_wound_completion_inventory",
    "validate_pending_model_destruction_cause_inventory",
    "validate_rule_effect_completion_or_pending_window",
)
