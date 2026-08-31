from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecord,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
    model_destruction_cause_id,
)
from warhammer40k_core.engine.model_logical_death import (
    model_logical_death_boundary_id,
    model_logical_death_record_from_event,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathBindingKind,
    MortalWoundLogicalDeathCauseBinding,
    MortalWoundLogicalDeathCauseBindingPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
        MortalWoundApplicationProgress,
    )
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )


MORTAL_WOUND_APPLICATION_STARTED_EVENT = "mortal_wound_application_started"


class MortalWoundApplicationAuthorityPayload(TypedDict):
    game_id: str
    application_id: str
    source_rule_id: str
    source_context: JsonValue
    target_unit_instance_id: str
    defender_player_id: str
    mortal_wounds: int
    spill_over: bool
    destruction_evidence: JsonValue
    priority_model_ids: list[str]
    initial_logical_death_cause_binding: MortalWoundLogicalDeathCauseBindingPayload


@dataclass(frozen=True, slots=True)
class MortalWoundApplicationAuthority:
    game_id: str
    application_id: str
    source_rule_id: str
    source_context: JsonValue
    target_unit_instance_id: str
    defender_player_id: str
    mortal_wounds: int
    spill_over: bool
    destruction_evidence: MortalWoundDestructionEvidence | None
    priority_model_ids: tuple[str, ...]
    initial_logical_death_cause_binding: MortalWoundLogicalDeathCauseBinding

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
            MortalWoundDestructionEvidence,
        )

        for field_name in (
            "game_id",
            "application_id",
            "source_rule_id",
            "target_unit_instance_id",
            "defender_player_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(
                    f"Mortal-wound application authority {field_name}",
                    getattr(self, field_name),
                ),
            )
        object.__setattr__(self, "source_context", validate_json_value(self.source_context))
        if type(self.mortal_wounds) is not int or self.mortal_wounds < 1:
            raise GameLifecycleError(
                "Mortal-wound application authority mortal_wounds must be positive."
            )
        if type(self.spill_over) is not bool:
            raise GameLifecycleError(
                "Mortal-wound application authority spill_over must be a bool."
            )
        if self.destruction_evidence is not None and type(self.destruction_evidence) is not (
            MortalWoundDestructionEvidence
        ):
            raise GameLifecycleError(
                "Mortal-wound application authority destruction evidence is invalid."
            )
        priority_model_ids = _identifier_tuple(
            "Mortal-wound application authority priority_model_ids",
            self.priority_model_ids,
        )
        object.__setattr__(self, "priority_model_ids", priority_model_ids)
        binding = _initial_binding(self.initial_logical_death_cause_binding)
        object.__setattr__(self, "initial_logical_death_cause_binding", binding)

    def to_payload(self) -> MortalWoundApplicationAuthorityPayload:
        from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
            evidence_to_json,
        )

        return {
            "game_id": self.game_id,
            "application_id": self.application_id,
            "source_rule_id": self.source_rule_id,
            "source_context": self.source_context,
            "target_unit_instance_id": self.target_unit_instance_id,
            "defender_player_id": self.defender_player_id,
            "mortal_wounds": self.mortal_wounds,
            "spill_over": self.spill_over,
            "destruction_evidence": cast(
                JsonValue,
                evidence_to_json(self.destruction_evidence),
            ),
            "priority_model_ids": list(self.priority_model_ids),
            "initial_logical_death_cause_binding": (
                self.initial_logical_death_cause_binding.to_payload()
            ),
        }

    def validate_for_state(self, state: GameState) -> None:
        """Bind the serialized packet root to authoritative game ownership."""

        from warhammer40k_core.engine.game_state import GameState
        from warhammer40k_core.engine.rules_units import (
            current_rules_unit_views_for_canonical_identity,
        )

        if type(state) is not GameState:
            raise GameLifecycleError(
                "Mortal-wound application authority validation requires GameState."
            )
        if self.game_id != state.game_id:
            raise GameLifecycleError("Mortal-wound application authority game drift.")
        target_rules_units = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=self.target_unit_instance_id,
        )
        if {rules_unit.owner_player_id for rules_unit in target_rules_units} != {
            self.defender_player_id
        }:
            raise GameLifecycleError("Mortal-wound application defender owner drift.")
        if self.destruction_evidence is not None:
            self.destruction_evidence.validate_for_state(state)
        target_component_unit_ids = {
            component_unit_id
            for rules_unit in target_rules_units
            for component_unit_id in rules_unit.component_unit_instance_ids
        }
        if any(
            state.unit_instance_id_for_model(model_id) not in target_component_unit_ids
            for model_id in self.priority_model_ids
        ):
            raise GameLifecycleError(
                "Mortal-wound application priority model is outside the target rules unit."
            )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
            evidence_from_json,
        )

        raw = _exact_object(
            payload,
            expected_fields={
                "game_id",
                "application_id",
                "source_rule_id",
                "source_context",
                "target_unit_instance_id",
                "defender_player_id",
                "mortal_wounds",
                "spill_over",
                "destruction_evidence",
                "priority_model_ids",
                "initial_logical_death_cause_binding",
            },
        )
        priority_model_ids = raw["priority_model_ids"]
        if not isinstance(priority_model_ids, list) or any(
            type(value) is not str for value in priority_model_ids
        ):
            raise GameLifecycleError(
                "Mortal-wound application authority priority_model_ids must contain strings."
            )
        mortal_wounds = raw["mortal_wounds"]
        spill_over = raw["spill_over"]
        if type(mortal_wounds) is not int or type(spill_over) is not bool:
            raise GameLifecycleError(
                "Mortal-wound application authority scalar fields are invalid."
            )
        return cls(
            game_id=_identifier(raw, "game_id"),
            application_id=_identifier(raw, "application_id"),
            source_rule_id=_identifier(raw, "source_rule_id"),
            source_context=validate_json_value(raw["source_context"]),
            target_unit_instance_id=_identifier(raw, "target_unit_instance_id"),
            defender_player_id=_identifier(raw, "defender_player_id"),
            mortal_wounds=mortal_wounds,
            spill_over=spill_over,
            destruction_evidence=evidence_from_json(raw["destruction_evidence"]),
            priority_model_ids=tuple(cast(list[str], priority_model_ids)),
            initial_logical_death_cause_binding=MortalWoundLogicalDeathCauseBinding.from_payload(
                raw["initial_logical_death_cause_binding"]
            ),
        )


def ensure_started(
    state: GameState,
    event_log: EventLog,
    progress: MortalWoundApplicationProgress,
) -> EventRecord:
    """Append the immutable packet root before damage, or authenticate a resumed packet."""

    from warhammer40k_core.engine.damage_allocation import MortalWoundApplicationProgress
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Mortal-wound application authority requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Mortal-wound application authority requires EventLog.")
    if type(progress) is not MortalWoundApplicationProgress:
        raise GameLifecycleError(
            "Mortal-wound application authority requires typed application progress."
        )
    expected = _authority_for_progress(state=state, progress=progress)
    expected.validate_for_state(state)
    inventory = mortal_wound_application_authority_inventory(
        event_records=event_log.records,
        game_id=state.game_id,
    )
    existing = inventory.get(progress.application_id)
    if existing is None:
        _require_pristine_progress(progress)
        return event_log.append(MORTAL_WOUND_APPLICATION_STARTED_EVENT, expected.to_payload())
    event, authority = existing
    if authority != expected:
        raise GameLifecycleError("Mortal-wound application start authority drift.")
    _validate_progress_logical_death_authority(
        state=state,
        progress=progress,
        authority=authority,
        started_event=event,
        event_records=event_log.records,
        request_event=None,
    )
    return event


def append_direct_mortal_wound_application_started(
    *,
    state: GameState,
    event_log: EventLog,
    application_id: str,
    source_rule_id: str,
    source_context: JsonValue,
    target_unit_instance_id: str,
    defender_player_id: str,
    mortal_wounds: int,
    spill_over: bool,
    destruction_evidence: MortalWoundDestructionEvidence,
) -> EventRecord:
    """Record one immutable root before a non-resumable direct packet mutates state."""

    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("Direct mortal-wound authority requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Direct mortal-wound authority requires EventLog.")
    if type(destruction_evidence) is not MortalWoundDestructionEvidence:
        raise GameLifecycleError(
            "Direct mortal-wound authority requires typed destruction evidence."
        )
    destruction_evidence.validate_for_state(state)
    authority = MortalWoundApplicationAuthority(
        game_id=state.game_id,
        application_id=application_id,
        source_rule_id=source_rule_id,
        source_context=source_context,
        target_unit_instance_id=target_unit_instance_id,
        defender_player_id=defender_player_id,
        mortal_wounds=mortal_wounds,
        spill_over=spill_over,
        destruction_evidence=destruction_evidence,
        priority_model_ids=(),
        initial_logical_death_cause_binding=MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
            producer_id=application_id,
        ),
    )
    authority.validate_for_state(state)
    inventory = mortal_wound_application_authority_inventory(
        event_records=event_log.records,
        game_id=state.game_id,
    )
    if authority.application_id in inventory:
        raise GameLifecycleError("Direct mortal-wound application authority already exists.")
    return event_log.append(MORTAL_WOUND_APPLICATION_STARTED_EVENT, authority.to_payload())


def mortal_wound_application_authority_inventory(
    *,
    event_records: tuple[EventRecord, ...],
    game_id: str,
) -> dict[str, tuple[EventRecord, MortalWoundApplicationAuthority]]:
    requested_game_id = _validate_identifier(
        "Mortal-wound application authority game_id",
        game_id,
    )
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Mortal-wound application authority requires typed event history.")
    inventory: dict[str, tuple[EventRecord, MortalWoundApplicationAuthority]] = {}
    for event in event_records:
        if event.event_type != MORTAL_WOUND_APPLICATION_STARTED_EVENT:
            continue
        authority = mortal_wound_application_authority_from_event(event)
        if authority.game_id != requested_game_id:
            raise GameLifecycleError("Mortal-wound application authority game drift.")
        if authority.application_id in inventory:
            raise GameLifecycleError("Mortal-wound application start authority is duplicated.")
        inventory[authority.application_id] = (event, authority)
    return inventory


def validate_pending_mortal_wound_application_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    progress: MortalWoundApplicationProgress,
    request_event: EventRecord,
    inventory: dict[str, tuple[EventRecord, MortalWoundApplicationAuthority]],
) -> MortalWoundLogicalDeathCauseBinding:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Pending mortal-wound authority requires GameState.")
    existing = inventory.get(progress.application_id)
    if existing is None:
        raise GameLifecycleError("Pending mortal-wound progress lacks its start authority.")
    started_event, authority = existing
    expected = _authority_for_progress(state=state, progress=progress)
    if authority != expected:
        raise GameLifecycleError("Pending mortal-wound start authority drift.")
    return _validate_progress_logical_death_authority(
        state=state,
        progress=progress,
        authority=authority,
        started_event=started_event,
        event_records=event_records,
        request_event=request_event,
    )


def validate_mortal_wound_application_authority_closure(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[object, ...],
    inventory: dict[str, tuple[EventRecord, MortalWoundApplicationAuthority]],
) -> None:
    """Require each packet root to have one pending request or terminal continuation."""

    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        is_mortal_wound_feel_no_pain_request,
    )
    from warhammer40k_core.engine.decision_request import DecisionRequest

    if type(pending_decision_requests) is not tuple or any(
        type(request) is not DecisionRequest for request in pending_decision_requests
    ):
        raise GameLifecycleError(
            "Mortal-wound application authority requires typed pending requests."
        )
    pending_application_ids: list[str] = []
    for request in cast(tuple[DecisionRequest, ...], pending_decision_requests):
        if not is_mortal_wound_feel_no_pain_request(request):
            continue
        request_payload = request.payload
        if not isinstance(request_payload, dict):
            raise GameLifecycleError("Pending mortal-wound request payload is invalid.")
        progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
            request_payload.get("lost_wound_context")
        )
        pending_application_ids.append(progress.application_id)
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_indexes) != len(event_records):
        raise GameLifecycleError("Mortal-wound application authority history is duplicated.")
    for application_id, (started_event, authority) in inventory.items():
        authority.validate_for_state(state)
        pending_count = pending_application_ids.count(application_id)
        completion_events = _completion_events_for_authority(
            authority=authority,
            event_records=event_records,
        )
        active_continuation_count = (
            0
            if pending_count or completion_events
            else _active_self_mortal_wound_continuation_count(
                state=state,
                authority=authority,
            )
        )
        if pending_count + len(completion_events) + active_continuation_count != 1:
            raise GameLifecycleError(
                "Mortal-wound application start authority lacks exactly one continuation."
            )
        if (
            completion_events
            and event_indexes[completion_events[0].event_id]
            <= (event_indexes[started_event.event_id])
        ):
            raise GameLifecycleError(
                "Mortal-wound application completion must follow its start authority."
            )
        if completion_events:
            _validate_completed_logical_death_order(
                state=state,
                authority=authority,
                started_event=started_event,
                completion_event=completion_events[0],
                event_records=event_records,
            )
        elif active_continuation_count:
            _validate_active_logical_death_order(
                state=state,
                authority=authority,
                started_event=started_event,
                event_records=event_records,
            )
        if authority.destruction_evidence is not None and completion_events:
            _validate_ordinary_completion_payload(
                state=state,
                authority=authority,
                event=completion_events[0],
                event_records=event_records,
            )
    for completion_event in _supported_completion_events(event_records):
        matching_application_ids = tuple(
            application_id
            for application_id, (_started_event, authority) in inventory.items()
            if completion_event
            in _completion_events_for_authority(
                authority=authority,
                event_records=(completion_event,),
            )
        )
        if len(matching_application_ids) != 1:
            raise GameLifecycleError(
                "Mortal-wound application terminal lacks exactly one start authority."
            )


def validate_direct_mortal_wound_application_event_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    """Validate direct mortal-wound progress snapshots and completed packets."""

    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
        MortalWoundDestructionFinalizationKind,
        mortal_wound_destruction_finalization_kind_from_event,
    )

    inventory = mortal_wound_application_authority_inventory(
        event_records=event_records,
        game_id=state.game_id,
    )
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_indexes) != len(event_records):
        raise GameLifecycleError("Mortal-wound application authority history is duplicated.")
    for event in event_records:
        progress = _direct_mortal_wound_progress_from_event(event)
        if progress is None:
            continue
        validate_pending_mortal_wound_application_authority(
            state=state,
            event_records=event_records,
            progress=progress,
            request_event=event,
            inventory=inventory,
        )
    claimed_application_ids: set[str] = set()
    for event in event_records:
        if event.event_type != MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT:
            continue
        if mortal_wound_destruction_finalization_kind_from_event(event) is not (
            MortalWoundDestructionFinalizationKind.APPLICATION_PACKET
        ):
            continue
        matches = tuple(
            (started_event, authority)
            for started_event, authority in inventory.values()
            if _ordinary_completion_matches(authority=authority, event=event)
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Mortal-wound application terminal lacks exactly one start authority."
            )
        started_event, authority = matches[0]
        if authority.application_id in claimed_application_ids:
            raise GameLifecycleError("Mortal-wound application was completed twice.")
        claimed_application_ids.add(authority.application_id)
        authority.validate_for_state(state)
        if event_indexes[started_event.event_id] >= event_indexes[event.event_id]:
            raise GameLifecycleError(
                "Mortal-wound application completion must follow its start authority."
            )
        _validate_completed_logical_death_order(
            state=state,
            authority=authority,
            started_event=started_event,
            completion_event=event,
            event_records=event_records,
        )
        _validate_ordinary_completion_payload(
            state=state,
            authority=authority,
            event=event,
            event_records=event_records,
        )


def direct_mortal_wound_damage_applications_from_event(
    event: EventRecord,
) -> tuple[DamageApplication, ...]:
    """Return cumulative direct mortal-wound damage retained by a canonical event."""

    snapshot = direct_mortal_wound_damage_snapshot_from_event(event)
    return () if snapshot is None else snapshot[1]


def direct_mortal_wound_damage_snapshot_from_event(
    event: EventRecord,
) -> tuple[str, tuple[DamageApplication, ...]] | None:
    """Return one application identity and its cumulative canonical damage snapshot."""

    progress = _direct_mortal_wound_progress_from_event(event)
    if progress is not None:
        return progress.application_id, progress.applications
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationPayload,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
        MortalWoundDestructionFinalizationKind,
        mortal_wound_destruction_finalization_kind_from_event,
    )

    if event.event_type != MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT:
        return None
    if mortal_wound_destruction_finalization_kind_from_event(event) is not (
        MortalWoundDestructionFinalizationKind.APPLICATION_PACKET
    ):
        return None
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Direct mortal-wound terminal payload is invalid.")
    raw_application = payload.get("application")
    if not isinstance(raw_application, dict):
        raise GameLifecycleError("Direct mortal-wound terminal application is invalid.")
    application_id = _validate_identifier(
        "Direct mortal-wound terminal application_id",
        payload.get("application_id"),
    )
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, raw_application)
    )
    destroyed_model_ids = {
        damage.model_instance_id for damage in application.applications if damage.destroyed
    }
    return (
        application_id,
        tuple(
            damage
            for damage in application.applications
            if damage.model_instance_id not in destroyed_model_ids
        ),
    )


def _direct_mortal_wound_progress_from_event(
    event: EventRecord,
) -> MortalWoundApplicationProgress | None:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        is_mortal_wound_feel_no_pain_request,
    )
    from warhammer40k_core.engine.decision_request import (
        DecisionError,
        DecisionRequest,
        DecisionRequestPayload,
    )

    if event.event_type != "decision_requested" or not isinstance(event.payload, dict):
        return None
    try:
        request = DecisionRequest.from_payload(cast(DecisionRequestPayload, event.payload))
    except (DecisionError, KeyError, TypeError) as exc:
        raise GameLifecycleError("Direct mortal-wound request event is invalid.") from exc
    if not is_mortal_wound_feel_no_pain_request(request):
        return None
    request_payload = request.payload
    if not isinstance(request_payload, dict):
        raise GameLifecycleError("Direct mortal-wound request payload is invalid.")
    progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
        request_payload.get("lost_wound_context")
    )
    return progress if progress.destruction_evidence is not None else None


def mortal_wound_application_authority_from_event(
    event: EventRecord,
) -> MortalWoundApplicationAuthority:
    if type(event) is not EventRecord or event.event_type != (
        MORTAL_WOUND_APPLICATION_STARTED_EVENT
    ):
        raise GameLifecycleError("Mortal-wound application authority requires its exact event.")
    return MortalWoundApplicationAuthority.from_payload(event.payload)


def _completion_events_for_authority(
    *,
    authority: MortalWoundApplicationAuthority,
    event_records: tuple[EventRecord, ...],
) -> tuple[EventRecord, ...]:
    if authority.destruction_evidence is not None:
        from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
            MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
        )

        return tuple(
            event
            for event in event_records
            if event.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT
            and _ordinary_completion_matches(authority=authority, event=event)
        )
    source_context = authority.source_context
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Retained mortal-wound authority source must be an object.")
    from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
    from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
    )
    from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
    )

    source_kind = source_context.get("source_kind")
    if source_kind == DEADLY_DEMISE_SOURCE_KIND:
        return tuple(
            event
            for event in event_records
            if event.event_type == "deadly_demise_mortal_wounds_applied"
            and _attack_deadly_demise_completion_matches(authority=authority, event=event)
        )
    if source_kind == RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND:
        return tuple(
            event
            for event in event_records
            if event.event_type == "deadly_demise_mortal_wounds_applied"
            and _rule_deadly_demise_completion_matches(authority=authority, event=event)
        )
    if source_kind == SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND:
        return tuple(
            event
            for event in event_records
            if event.event_type == SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT
            and _self_mortal_wound_completion_matches(authority=authority, event=event)
        )
    raise GameLifecycleError("Retained mortal-wound application source is unsupported.")


def _supported_completion_events(
    event_records: tuple[EventRecord, ...],
) -> tuple[EventRecord, ...]:
    from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
        MortalWoundDestructionFinalizationKind,
        mortal_wound_destruction_finalization_kind_from_event,
    )

    supported: list[EventRecord] = []
    for event in event_records:
        if event.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT:
            finalization_kind = mortal_wound_destruction_finalization_kind_from_event(event)
            if finalization_kind is MortalWoundDestructionFinalizationKind.APPLICATION_PACKET:
                supported.append(event)
            continue
        if event.event_type in {
            SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
            "deadly_demise_mortal_wounds_applied",
        }:
            supported.append(event)
    return tuple(supported)


def _ordinary_completion_matches(
    *,
    authority: MortalWoundApplicationAuthority,
    event: EventRecord,
) -> bool:
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionFinalizationKind,
        evidence_to_json,
        mortal_wound_destruction_finalization_kind_from_event,
    )

    payload = event.payload
    if not isinstance(payload, dict):
        return False
    return (
        mortal_wound_destruction_finalization_kind_from_event(event)
        is MortalWoundDestructionFinalizationKind.APPLICATION_PACKET
        and payload.get("game_id") == authority.game_id
        and payload.get("application_id") == authority.application_id
        and payload.get("source_rule_id") == authority.source_rule_id
        and payload.get("source_context") == authority.source_context
        and payload.get("target_unit_instance_id") == authority.target_unit_instance_id
        and payload.get("destruction_evidence") == evidence_to_json(authority.destruction_evidence)
        and _completion_application_matches(authority=authority, payload=payload)
    )


def _validate_ordinary_completion_payload(
    *,
    state: GameState,
    authority: MortalWoundApplicationAuthority,
    event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.engine import (
        model_destruction_cause_completion_restore as _mdccr,
    )
    from warhammer40k_core.engine import (
        model_destruction_cause_payload_validation as _mdcpv,
    )
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationPayload,
    )
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionFinalizationKind,
        evidence_to_json,
    )

    payload = event.payload
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
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise GameLifecycleError("Mortal-wound application terminal fields are invalid.")
    battle_round = payload.get("battle_round")
    active_player_id = payload.get("active_player_id")
    if (
        type(battle_round) is not int
        or battle_round < 1
        or type(active_player_id) is not str
        or active_player_id not in state.player_ids
    ):
        raise GameLifecycleError("Mortal-wound application terminal turn identity is invalid.")
    raw_application = payload.get("application")
    if not isinstance(raw_application, dict):
        raise GameLifecycleError("Mortal-wound application terminal result is invalid.")
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, raw_application)
    )
    destroyed_model_ids = _mdcpv.json_identifier_list(
        payload.get("destroyed_model_instance_ids"),
        "mortal-wound terminal destroyed_model_instance_ids",
    )
    destroyed_event_ids = _mdcpv.json_identifier_list(
        payload.get("model_destroyed_event_ids"),
        "mortal-wound terminal model_destroyed_event_ids",
    )
    if len(destroyed_model_ids) != len(destroyed_event_ids):
        raise GameLifecycleError("Mortal-wound application terminal inventory drift.")
    _mdccr.validate_mortal_wound_application_inventory(
        state=state,
        application=application,
        destroyed_model_ids=destroyed_model_ids,
        destroyed_event_ids=destroyed_event_ids,
        event_records=event_records,
    )
    expected_physical_ids, expected_rules_ids, expected_transition = (
        _mdccr.validate_mortal_wound_completion_inventory(
            state=state,
            application_id=authority.application_id,
            event_records=event_records,
            destroyed_model_ids=destroyed_model_ids,
            destroyed_event_ids=destroyed_event_ids,
            source_rule_id=authority.source_rule_id,
            source_context=authority.source_context,
        )
    )
    event_indexes = {record.event_id: index for index, record in enumerate(event_records)}
    completion_index = event_indexes[event.event_id]
    if any(event_indexes[event_id] >= completion_index for event_id in destroyed_event_ids):
        raise GameLifecycleError(
            "Mortal-wound application destructions must precede their terminal."
        )
    if (
        payload.get("game_id") != authority.game_id
        or payload.get("application_id") != authority.application_id
        or payload.get("finalization_kind")
        != MortalWoundDestructionFinalizationKind.APPLICATION_PACKET.value
        or payload.get("source_rule_id") != authority.source_rule_id
        or payload.get("source_context") != authority.source_context
        or payload.get("target_unit_instance_id") != authority.target_unit_instance_id
        or application.target_unit_instance_id != authority.target_unit_instance_id
        or application.mortal_wounds != authority.mortal_wounds
        or application.spill_over is not authority.spill_over
        or payload.get("destruction_evidence") != evidence_to_json(authority.destruction_evidence)
        or _mdcpv.json_identifier_list(
            payload.get("physical_unit_instance_ids"),
            "mortal-wound terminal physical_unit_instance_ids",
        )
        != expected_physical_ids
        or _mdcpv.json_identifier_list(
            payload.get("rules_unit_instance_ids"),
            "mortal-wound terminal rules_unit_instance_ids",
        )
        != expected_rules_ids
        or payload.get("transition_batch") != expected_transition
    ):
        raise GameLifecycleError("Mortal-wound application terminal binding drift.")


def _attack_deadly_demise_completion_matches(
    *,
    authority: MortalWoundApplicationAuthority,
    event: EventRecord,
) -> bool:
    payload = event.payload
    source_context = authority.source_context
    if not isinstance(payload, dict) or not isinstance(source_context, dict):
        return False
    attack_context = source_context.get("attack_context")
    return (
        isinstance(attack_context, dict)
        and payload.get("sequence_id") == source_context.get("sequence_id")
        and payload.get("attack_context_id") == attack_context.get("attack_context_id")
        and payload.get("source") == source_context.get("source")
        and payload.get("source_rule_id") == authority.source_rule_id
        and payload.get("target_unit_instance_id") == authority.target_unit_instance_id
        and payload.get("mortal_wounds") == authority.mortal_wounds
        and payload.get("mortal_wound_roll") == source_context.get("mortal_wound_roll")
        and _completion_application_matches(authority=authority, payload=payload)
    )


def _rule_deadly_demise_completion_matches(
    *,
    authority: MortalWoundApplicationAuthority,
    event: EventRecord,
) -> bool:
    payload = event.payload
    source_context = authority.source_context
    if not isinstance(payload, dict) or not isinstance(source_context, dict):
        return False
    root_context = source_context.get("root_context")
    return (
        isinstance(root_context, dict)
        and payload.get("source_result_id") == root_context.get("source_result_id")
        and payload.get("source") == source_context.get("source")
        and payload.get("source_rule_id") == authority.source_rule_id
        and payload.get("target_unit_instance_id") == authority.target_unit_instance_id
        and payload.get("mortal_wounds") == authority.mortal_wounds
        and payload.get("mortal_wound_roll")
        == source_context.get("current_target_mortal_wound_roll")
        and _completion_application_matches(authority=authority, payload=payload)
    )


def _self_mortal_wound_completion_matches(
    *,
    authority: MortalWoundApplicationAuthority,
    event: EventRecord,
) -> bool:
    payload = event.payload
    source_context = authority.source_context
    if not isinstance(payload, dict) or not isinstance(source_context, dict):
        return False
    return all(payload.get(key) == value for key, value in source_context.items()) and (
        _completion_application_matches(authority=authority, payload=payload)
    )


def _completion_application_matches(
    *,
    authority: MortalWoundApplicationAuthority,
    payload: dict[str, JsonValue],
) -> bool:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationPayload,
    )

    raw_application = payload.get("application", payload.get("mortal_wound_application"))
    if not isinstance(raw_application, dict):
        return False
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, raw_application)
    )
    return (
        application.target_unit_instance_id == authority.target_unit_instance_id
        and application.mortal_wounds == authority.mortal_wounds
        and application.spill_over is authority.spill_over
    )


def _validate_completed_logical_death_order(
    *,
    state: GameState,
    authority: MortalWoundApplicationAuthority,
    started_event: EventRecord,
    completion_event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationPayload,
    )

    payload = completion_event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Mortal-wound application completion payload is invalid.")
    raw_application = payload.get("application", payload.get("mortal_wound_application"))
    if not isinstance(raw_application, dict):
        raise GameLifecycleError("Mortal-wound application completion result is invalid.")
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, raw_application)
    )
    destroyed_model_ids = tuple(
        sorted(damage.model_instance_id for damage in application.applications if damage.destroyed)
    )
    if len(destroyed_model_ids) != len(set(destroyed_model_ids)):
        raise GameLifecycleError("Mortal-wound completed logical-death models are duplicated.")
    _validate_owned_logical_death_order(
        state=state,
        authority=authority,
        started_event=started_event,
        terminal_event=completion_event,
        expected_model_ids=destroyed_model_ids,
        event_records=event_records,
    )


def _validate_active_logical_death_order(
    *,
    state: GameState,
    authority: MortalWoundApplicationAuthority,
    started_event: EventRecord,
    event_records: tuple[EventRecord, ...],
) -> None:
    binding = authority.initial_logical_death_cause_binding
    expected_model_ids = tuple(
        sorted(
            cause.model_instance_id
            for cause in state.model_destruction_cause_authorities
            if cause.cause_kind is binding.cause_kind
            and cause.producer_id
            == _expected_producer_id(
                authority=authority,
                binding=binding,
                model_instance_id=cause.model_instance_id,
            )
        )
    )
    if not expected_model_ids:
        raise GameLifecycleError(
            "Active mortal-wound continuation lacks its logical-death authority."
        )
    _validate_owned_logical_death_order(
        state=state,
        authority=authority,
        started_event=started_event,
        terminal_event=None,
        expected_model_ids=expected_model_ids,
        event_records=event_records,
    )


def _validate_owned_logical_death_order(
    *,
    state: GameState,
    authority: MortalWoundApplicationAuthority,
    started_event: EventRecord,
    terminal_event: EventRecord | None,
    expected_model_ids: tuple[str, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    from warhammer40k_core.engine.model_logical_death import (
        MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    )

    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    started_index = event_indexes[started_event.event_id]
    terminal_index = None if terminal_event is None else event_indexes[terminal_event.event_id]
    binding = authority.initial_logical_death_cause_binding
    for model_instance_id in expected_model_ids:
        producer_id = _expected_producer_id(
            authority=authority,
            binding=binding,
            model_instance_id=model_instance_id,
        )
        expected_cause_id = model_destruction_cause_id(
            game_id=state.game_id,
            cause_kind=binding.cause_kind,
            producer_id=producer_id,
            model_instance_id=model_instance_id,
        )
        expected_boundary_id = model_logical_death_boundary_id(
            game_id=state.game_id,
            cause_id=expected_cause_id,
            model_instance_id=model_instance_id,
        )
        matches = tuple(
            event
            for event in event_records
            if event.event_type == MODEL_LOGICAL_DEATH_RECORDED_EVENT
            and (record := model_logical_death_record_from_event(event)).game_id == state.game_id
            and record.cause_id == expected_cause_id
            and record.boundary_id == expected_boundary_id
            and record.cause_kind is binding.cause_kind
            and record.producer_id == producer_id
            and record.model_instance_id == model_instance_id
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Mortal-wound application lacks exactly one completed logical death."
            )
        logical_index = event_indexes[matches[0].event_id]
        if started_index >= logical_index or (
            terminal_index is not None and logical_index >= terminal_index
        ):
            raise GameLifecycleError(
                "Mortal-wound application start must precede completed logical death."
            )


def _active_self_mortal_wound_continuation_count(
    *,
    state: GameState,
    authority: MortalWoundApplicationAuthority,
) -> int:
    from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
    )

    source_context = authority.source_context
    if not isinstance(source_context, dict) or source_context.get("source_kind") != (
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND
    ):
        return 0
    return sum(
        cause.producer_id == authority.application_id
        and cause.producer_context.get("completion_event_type")
        == SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT
        for cause in state.model_destruction_cause_authorities
    )


def _validate_progress_logical_death_authority(
    *,
    state: GameState,
    progress: MortalWoundApplicationProgress,
    authority: MortalWoundApplicationAuthority,
    started_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    request_event: EventRecord | None,
) -> MortalWoundLogicalDeathCauseBinding:
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_indexes) != len(event_records) or started_event.event_id not in event_indexes:
        raise GameLifecycleError("Mortal-wound application authority history drift.")
    started_index = event_indexes[started_event.event_id]
    if request_event is not None:
        request_index = event_indexes.get(request_event.event_id)
        if request_index is None or started_index >= request_index:
            raise GameLifecycleError(
                "Mortal-wound application start authority must precede its request."
            )
    binding = authority.initial_logical_death_cause_binding
    for event in progress.logical_death_events:
        logical_index = event_indexes.get(event.event_id)
        if logical_index is None or started_index >= logical_index:
            raise GameLifecycleError(
                "Mortal-wound application start authority must precede logical death."
            )
        record = model_logical_death_record_from_event(event)
        producer_id = _expected_producer_id(
            authority=authority,
            binding=binding,
            model_instance_id=record.model_instance_id,
        )
        expected_cause_id = model_destruction_cause_id(
            game_id=state.game_id,
            cause_kind=binding.cause_kind,
            producer_id=producer_id,
            model_instance_id=record.model_instance_id,
        )
        expected_boundary_id = model_logical_death_boundary_id(
            game_id=state.game_id,
            cause_id=expected_cause_id,
            model_instance_id=record.model_instance_id,
        )
        if (
            record.game_id != state.game_id
            or record.producer_id != producer_id
            or record.cause_kind is not binding.cause_kind
            or record.cause_id != expected_cause_id
            or record.boundary_id != expected_boundary_id
        ):
            raise GameLifecycleError("Pending mortal-wound logical-death authority drift.")
        binding = binding.with_logical_death_event(event)
    if progress.logical_death_cause_binding != binding:
        raise GameLifecycleError("Pending mortal-wound logical-death binding drift.")
    return binding


def _authority_for_progress(
    *,
    state: GameState,
    progress: MortalWoundApplicationProgress,
) -> MortalWoundApplicationAuthority:
    binding = progress.logical_death_cause_binding
    if type(binding) is not MortalWoundLogicalDeathCauseBinding:
        raise GameLifecycleError("Mortal-wound application lacks logical-death binding authority.")
    initial_binding = _initial_binding(binding)
    _validate_initial_binding_source(state=state, progress=progress, binding=initial_binding)
    authority = MortalWoundApplicationAuthority(
        game_id=state.game_id,
        application_id=progress.application_id,
        source_rule_id=progress.source_rule_id,
        source_context=progress.source_context,
        target_unit_instance_id=progress.target_unit_instance_id,
        defender_player_id=progress.defender_player_id,
        mortal_wounds=progress.mortal_wounds,
        spill_over=progress.spill_over,
        destruction_evidence=progress.destruction_evidence,
        priority_model_ids=progress.priority_model_ids,
        initial_logical_death_cause_binding=initial_binding,
    )
    authority.validate_for_state(state)
    return authority


def _validate_initial_binding_source(
    *,
    state: GameState,
    progress: MortalWoundApplicationProgress,
    binding: MortalWoundLogicalDeathCauseBinding,
) -> None:
    if progress.destruction_evidence is not None:
        expected = MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
            producer_id=progress.application_id,
        )
        if binding != expected:
            raise GameLifecycleError("Mortal-wound application start binding drift.")
        return
    source_context = progress.source_context
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Retained mortal-wound source context must be an object.")
    source_kind = source_context.get("source_kind")
    from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
    from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
        validate_selected_to_fight_self_mortal_wound_progress,
    )
    from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
        rule_deadly_demise_logical_death_binding,
    )

    if source_kind == DEADLY_DEMISE_SOURCE_KIND:
        from warhammer40k_core.engine.attack_sequence_mortal_wound_logical_death import (
            attack_deadly_demise_logical_death_binding,
        )
        from warhammer40k_core.engine.lifecycle_state_queries import (
            active_attack_sequence_for_state,
        )

        active_attack_sequence = active_attack_sequence_for_state(state)
        attack_context = source_context.get("attack_context")
        if (
            active_attack_sequence is None
            or source_context.get("sequence_id") != active_attack_sequence.sequence_id
            or not isinstance(attack_context, dict)
            or attack_context.get("attack_context_id") != active_attack_sequence.attack_context_id()
            or binding != attack_deadly_demise_logical_death_binding(active_attack_sequence)
        ):
            raise GameLifecycleError("Attack Deadly Demise application start binding drift.")
        return
    if source_kind == RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND:
        if binding != rule_deadly_demise_logical_death_binding():
            raise GameLifecycleError("Rule Deadly Demise application start binding drift.")
        return
    if source_kind == SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND:
        validate_selected_to_fight_self_mortal_wound_progress(progress)
        if binding != _initial_binding(progress.logical_death_cause_binding):
            raise GameLifecycleError("Self mortal-wound application start binding drift.")
        return
    raise GameLifecycleError("Retained mortal-wound application source is unsupported.")


def _expected_producer_id(
    *,
    authority: MortalWoundApplicationAuthority,
    binding: MortalWoundLogicalDeathCauseBinding,
    model_instance_id: str,
) -> str:
    if binding.binding_kind is MortalWoundLogicalDeathBindingKind.FIXED_PRODUCER:
        producer_id = binding.fixed_producer_id
        if producer_id is None:
            raise GameLifecycleError("Fixed mortal-wound application producer is missing.")
        return producer_id
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionSource,
        DestructionReactionSourcePayload,
    )
    from warhammer40k_core.engine.rule_deadly_demise_continuation import (
        rule_deadly_demise_secondary_source_result_id,
    )
    from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
    )

    source_context = authority.source_context
    if not isinstance(source_context, dict) or source_context.get("source_kind") != (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND
    ):
        raise GameLifecycleError("Per-model mortal-wound producer source is unsupported.")
    root_context = _nested_object(source_context, "root_context")
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, _nested_object(source_context, "source"))
    )
    return rule_deadly_demise_secondary_source_result_id(
        parent_root_context=root_context,
        source=source,
        model_instance_id=model_instance_id,
    )


def _initial_binding(
    binding: MortalWoundLogicalDeathCauseBinding | None,
) -> MortalWoundLogicalDeathCauseBinding:
    if type(binding) is not MortalWoundLogicalDeathCauseBinding:
        raise GameLifecycleError("Mortal-wound application binding is invalid.")
    if binding.binding_kind is MortalWoundLogicalDeathBindingKind.FIXED_PRODUCER:
        return binding
    return MortalWoundLogicalDeathCauseBinding.per_model(cause_kind=binding.cause_kind)


def _require_pristine_progress(progress: MortalWoundApplicationProgress) -> None:
    if (
        progress.remaining_mortal_wounds != progress.mortal_wounds
        or progress.applications
        or progress.feel_no_pain_resolutions
        or progress.ignored_mortal_wounds
        or progress.remaining_mortal_wounds_lost
        or progress.destroyed_model_placements
        or progress.logical_death_events
        or progress.logical_death_cause_binding
        != _initial_binding(progress.logical_death_cause_binding)
    ):
        raise GameLifecycleError(
            "Mortal-wound application start authority must precede packet resolution."
        )


def _exact_object(value: object, *, expected_fields: set[str]) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise GameLifecycleError("Mortal-wound application authority payload must be an object.")
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        raise GameLifecycleError("Mortal-wound application authority keys are invalid.")
    typed = cast(dict[str, JsonValue], value)
    if set(typed) != expected_fields:
        raise GameLifecycleError("Mortal-wound application authority fields are invalid.")
    return typed


def _identifier(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(f"Mortal-wound application authority {key}", payload.get(key))


def _identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )
    if len(validated) != len(set(validated)) or validated != tuple(sorted(validated)):
        raise GameLifecycleError(f"{field_name} must be unique and sorted.")
    return validated


def _nested_object(payload: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Mortal-wound application source {key} must be an object.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MORTAL_WOUND_APPLICATION_STARTED_EVENT",
    "MortalWoundApplicationAuthority",
    "MortalWoundApplicationAuthorityPayload",
    "append_direct_mortal_wound_application_started",
    "direct_mortal_wound_damage_applications_from_event",
    "direct_mortal_wound_damage_snapshot_from_event",
    "ensure_started",
    "mortal_wound_application_authority_from_event",
    "mortal_wound_application_authority_inventory",
    "validate_direct_mortal_wound_application_event_authority",
    "validate_mortal_wound_application_authority_closure",
    "validate_pending_mortal_wound_application_authority",
)
