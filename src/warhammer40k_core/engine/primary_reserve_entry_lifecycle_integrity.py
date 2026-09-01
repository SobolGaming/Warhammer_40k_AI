from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import ReserveDestructionTimingKind
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
)
from warhammer40k_core.engine.cult_ambush_reserve_entry_integrity import (
    validate_cult_ambush_reserve_arrival_source,
)
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_RESERVE_ENTRY_MUTATION_EVENT,
    PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    reserve_entry_evidence_payload,
)
from warhammer40k_core.engine.primary_reserve_arrival_integrity import (
    validate_primary_reserve_arrival_event_authority,
    validate_primary_reserve_arrival_ingress_use_authority,
    validate_primary_reserve_arrival_placement_authority,
    validate_primary_reserve_arrival_request_chain,
    validate_primary_reserve_arrival_request_source,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
    PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT,
    PrimaryReserveEntryAbilityAuthorityKind,
    PrimaryReserveEntryLifecycleOccurrence,
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
    validate_accepted_primary_reserve_entry_provider,
    validate_primary_reserve_entry_provider_registration,
)
from warhammer40k_core.engine.primary_reserve_entry_provider_defaults import (
    default_primary_reserve_entry_ability_provider_definitions,
    default_primary_reserve_entry_occurrence_validators,
)
from warhammer40k_core.engine.primary_reserve_entry_source_integrity import (
    validate_primary_reserve_entry_source_requirements,
    validate_primary_reserve_entry_source_terminal_semantics,
)
from warhammer40k_core.engine.reserve_restriction_integrity import (
    reserve_arrival_restriction_expiry_is_proven,
)
from warhammer40k_core.engine.reserves import (
    ReserveOrigin,
    ReserveState,
    ReserveStatePayload,
    ReserveStatus,
)
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity
from warhammer40k_core.engine.stratagems_geometry import (
    _proposal_request_is_rapid_ingress,
)
from warhammer40k_core.engine.stratagems_model import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemUseRecord,
    StratagemUseRecordPayload,
)
from warhammer40k_core.engine.stratagems_selection import (
    stratagem_selection_from_decision_result,
    stratagem_selection_from_target_proposal_result,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_SOURCE_BINDING_KEYS = frozenset(("occurrence_id", "provider", "reserve_entry_state"))
_PROVIDER_TERMINAL_KEYS = frozenset(
    (
        "occurrence_id",
        "provider",
        "reserve_entry_state",
        "source_terminal_event_id",
        "source_terminal_event_type",
    )
)


@dataclass(frozen=True, slots=True)
class _SourceBinding:
    occurrence_id: str
    provider: PrimaryReserveEntryProvider
    reserve_entry_state: dict[str, JsonValue]
    source_terminal: EventRecord

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "occurrence_id": self.occurrence_id,
            "provider": self.provider.to_payload(),
            "reserve_entry_state": self.reserve_entry_state,
        }


@dataclass(frozen=True, slots=True)
class _ReserveArrivalOccurrence:
    event_order: int
    request_event_order: int
    recorded_event_order: int
    decision_record_id: str
    decision_request_id: str
    decision_result_id: str
    unit_instance_id: str
    active_player_id: str
    battle_round: int
    phase: str
    large_model_exception_used: bool
    post_arrival_restrictions: tuple[str, ...]


def validate_primary_reserve_entry_lifecycle_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex] | None,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None = None,
) -> None:
    """Close every reserve-entry source terminal against active runtime authority.

    Departure provenance validates the forward chain from an engine mutation to
    its derived Primary evidence.  This complementary audit starts at every
    registered source terminal, so an orphan or duplicated source event cannot
    hide outside that forward walk.  Generic Stratagem providers are also bound
    to the player's active runtime catalog instead of trusting a replay-carried
    catalog record to authenticate itself.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Reserve-entry lifecycle integrity requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Reserve-entry lifecycle integrity requires EventRecords.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Reserve-entry lifecycle integrity requires DecisionRecords.")

    ability_terminal_types = {
        definition.source_terminal_event_type
        for definition in default_primary_reserve_entry_ability_provider_definitions()
    }
    if len(ability_terminal_types) != len(
        default_primary_reserve_entry_ability_provider_definitions()
    ):
        raise GameLifecycleError("Reserve-entry ability source terminal types are duplicated.")
    registered_terminal_types = {
        GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT,
        *ability_terminal_types,
    }
    event_index_by_id = {record.event_id: index for index, record in enumerate(event_records)}
    if len(event_index_by_id) != len(event_records):
        raise GameLifecycleError("Reserve-entry lifecycle event IDs are duplicated.")
    decisions = _decision_controller_for_integrity_audit(
        event_records=event_records,
        decision_records=decision_records,
    )

    bindings_by_occurrence: dict[str, _SourceBinding] = {}
    for source_terminal in event_records:
        if source_terminal.event_type not in registered_terminal_types:
            continue
        source_bindings = _source_terminal_bindings(
            source_terminal=source_terminal,
            generic=(
                source_terminal.event_type == GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT
            ),
        )
        for binding in source_bindings:
            if binding.occurrence_id in bindings_by_occurrence:
                raise GameLifecycleError("Reserve-entry source terminal occurrence is duplicated.")
            validate_primary_reserve_entry_provider_registration(
                state=state,
                provider=binding.provider,
            )
            _validate_source_provider_authority(
                state=state,
                decisions=decisions,
                source_terminal=source_terminal,
                binding=binding,
                event_index_by_id=event_index_by_id,
            )
            bindings_by_occurrence[binding.occurrence_id] = binding
        if source_terminal.event_type == GENERIC_STRATAGEM_RESERVE_REMOVAL_RESOLVED_EVENT:
            _validate_generic_source_terminal(
                state=state,
                source_terminal=source_terminal,
                bindings=source_bindings,
            )
        else:
            _validate_ability_source_terminal(
                source_terminal=source_terminal,
                bindings=source_bindings,
            )

    provider_terminals_by_occurrence = _provider_terminals_by_occurrence(event_records)
    if set(provider_terminals_by_occurrence) != set(bindings_by_occurrence):
        raise GameLifecycleError("Reserve-entry source/provider terminal closure drift.")
    for occurrence_id, binding in bindings_by_occurrence.items():
        terminal = provider_terminals_by_occurrence[occurrence_id]
        payload = _closed_json_object(
            terminal.payload,
            field_name="Reserve-entry provider terminal",
            expected_keys=_PROVIDER_TERMINAL_KEYS,
        )
        if (
            payload.get("provider") != binding.provider.to_payload()
            or payload.get("reserve_entry_state") != binding.reserve_entry_state
            or payload.get("source_terminal_event_id") != binding.source_terminal.event_id
            or payload.get("source_terminal_event_type") != binding.source_terminal.event_type
        ):
            raise GameLifecycleError("Reserve-entry provider terminal binding drift.")
        if (
            event_index_by_id[binding.source_terminal.event_id]
            >= event_index_by_id[terminal.event_id]
        ):
            raise GameLifecycleError("Reserve-entry source/provider terminal ordering drift.")

    generic_providers = tuple(
        binding.provider
        for binding in bindings_by_occurrence.values()
        if binding.provider.provider_kind
        is PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM
    )
    _validate_active_stratagem_catalog_authority(
        state=state,
        decision_records=decision_records,
        providers=generic_providers,
        stratagem_indexes_by_player_id=stratagem_indexes_by_player_id,
    )
    _validate_active_ability_catalog_authority(
        decisions=decisions,
        bindings=tuple(bindings_by_occurrence.values()),
        ability_indexes_by_player_id=ability_indexes_by_player_id,
    )
    provider_occurrences = tuple(
        PrimaryReserveEntryLifecycleOccurrence(
            event_order=event_index_by_id[binding.source_terminal.event_id],
            historical_unit_instance_id=binding.provider.target_rules_unit_instance_id,
            reserve_entry_state=binding.reserve_entry_state,
        )
        for binding in bindings_by_occurrence.values()
    )
    aircraft_occurrences = _validated_aircraft_reserve_entry_occurrences(
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    registered_occurrences = tuple(
        occurrence
        for validator in default_primary_reserve_entry_occurrence_validators()
        for occurrence in validator(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            event_index_by_id=event_index_by_id,
        )
    )
    all_entry_occurrences = (
        *provider_occurrences,
        *aircraft_occurrences,
        *registered_occurrences,
    )
    relevant_player_ids: dict[str, str] = {}
    for occurrence in all_entry_occurrences:
        player_id = _required_identifier(
            occurrence.reserve_entry_state.get("player_id"),
            field_name="Reserve-entry occurrence player",
        )
        existing_player_id = relevant_player_ids.setdefault(
            occurrence.historical_unit_instance_id,
            player_id,
        )
        if existing_player_id != player_id:
            raise GameLifecycleError("Reserve-entry occurrence player identity drift.")
    arrival_occurrences = _validated_reserve_arrival_occurrences(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index_by_id=event_index_by_id,
        relevant_player_id_by_unit_instance_id=relevant_player_ids,
        reserve_entry_occurrences=all_entry_occurrences,
        stratagem_indexes_by_player_id=stratagem_indexes_by_player_id,
    )
    _validate_during_battle_reserve_state_reverse_closure(
        state=state,
        event_records=event_records,
        occurrences=all_entry_occurrences,
        arrival_occurrences=arrival_occurrences,
        event_index_by_id=event_index_by_id,
    )


def _decision_controller_for_integrity_audit(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> DecisionController:
    payload: DecisionControllerPayload = {
        "queue": {"pending_requests": []},
        "records": [record.to_payload() for record in decision_records],
        "event_log": [record.to_payload() for record in event_records],
    }
    try:
        return DecisionController.from_payload(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise GameLifecycleError("Reserve-entry decision history is invalid.") from exc


def _validate_source_provider_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    source_terminal: EventRecord,
    binding: _SourceBinding,
    event_index_by_id: dict[str, int],
) -> None:
    provider = binding.provider
    validate_accepted_primary_reserve_entry_provider(
        state=state,
        decisions=decisions,
        provider=provider,
    )
    matching_decisions = tuple(
        decision
        for decision in decisions.records
        if decision.record_id == provider.decision_record_id
        and decision.request.request_id == provider.decision_request_id
        and decision.result.result_id == provider.decision_result_id
    )
    if len(matching_decisions) != 1:
        raise GameLifecycleError("Reserve-entry provider accepted decision is missing.")
    decision = matching_decisions[0]
    requested_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "decision_requested"
        and event.payload == decision.request.to_payload()
    )
    recorded_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "decision_recorded" and event.payload == decision.to_payload()
    )
    if len(requested_events) != 1 or len(recorded_events) != 1:
        raise GameLifecycleError(
            "Reserve-entry provider requires exact requested and recorded decision events."
        )
    source_order = event_index_by_id[source_terminal.event_id]
    requested_order = event_index_by_id[requested_events[0].event_id]
    recorded_order = event_index_by_id[recorded_events[0].event_id]
    if not requested_order < recorded_order < source_order:
        raise GameLifecycleError("Reserve-entry provider decision/source ordering drift.")
    source_payload = _json_object(
        source_terminal.payload,
        field_name="Reserve-entry source terminal",
    )
    validate_primary_reserve_entry_source_terminal_semantics(
        state=state,
        provider=provider,
        decision=decision,
        reserve_entry=binding.reserve_entry_state,
        source_terminal=source_terminal,
        event_records=decisions.event_log.records,
    )
    validate_primary_reserve_entry_source_requirements(
        state=state,
        provider=provider,
        reserve_entry=binding.reserve_entry_state,
        source_terminal=source_terminal,
    )
    if provider.provider_kind is PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
        return
    if provider.stratagem_use_id is None:
        raise GameLifecycleError("Generic reserve-entry provider use identity is missing.")
    matching_uses = tuple(
        use for use in state.stratagem_use_records if use.use_id == provider.stratagem_use_id
    )
    if len(matching_uses) != 1:
        raise GameLifecycleError("Generic reserve-entry provider use identity is missing.")
    use = matching_uses[0]
    used_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "stratagem_used" and event.payload == use.to_payload()
    )
    executed_effect = source_payload.get("generic_rule_effect")
    executed_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "rule_execution_effect_applied" and event.payload == executed_effect
    )
    if len(used_events) != 1 or len(executed_events) != 1:
        raise GameLifecycleError("Generic reserve-entry provider execution closure drift.")
    if not (
        recorded_order
        < event_index_by_id[used_events[0].event_id]
        < event_index_by_id[executed_events[0].event_id]
        < source_order
    ):
        raise GameLifecycleError("Generic reserve-entry provider execution ordering drift.")


def _validated_aircraft_reserve_entry_occurrences(
    *,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> tuple[PrimaryReserveEntryLifecycleOccurrence, ...]:
    """Collect Aircraft entries after the departure audit authenticated their chain."""
    occurrences: list[PrimaryReserveEntryLifecycleOccurrence] = []
    for record in event_records:
        if record.event_type != PRIMARY_RESERVE_ENTRY_MUTATION_EVENT:
            continue
        payload = _json_object(record.payload, field_name="Reserve-entry mutation")
        if payload.get("provider") is not None:
            continue
        if payload.get("transition_batch") is None:
            raise GameLifecycleError(
                "Provider-free reserve-entry mutation requires an Aircraft transition."
            )
        reserve_entry = _json_object(
            payload.get("reserve_entry_state"),
            field_name="Aircraft reserve-entry evidence",
        )
        if reserve_entry.get("reserve_origin") != ReserveOrigin.DURING_BATTLE_OTHER.value:
            raise GameLifecycleError("Aircraft reserve-entry origin drift.")
        unit_instance_id = _required_identifier(
            reserve_entry.get("unit_instance_id"),
            field_name="Aircraft reserve-entry unit",
        )
        occurrences.append(
            PrimaryReserveEntryLifecycleOccurrence(
                event_order=event_index_by_id[record.event_id],
                historical_unit_instance_id=unit_instance_id,
                reserve_entry_state=reserve_entry,
            )
        )
    return tuple(occurrences)


def _validated_reserve_arrival_occurrences(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    relevant_player_id_by_unit_instance_id: Mapping[str, str],
    reserve_entry_occurrences: tuple[PrimaryReserveEntryLifecycleOccurrence, ...],
    stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex] | None,
) -> tuple[_ReserveArrivalOccurrence, ...]:
    occurrences: list[_ReserveArrivalOccurrence] = []
    authenticated_occurrences: list[_ReserveArrivalOccurrence] = []
    for arrival_event in event_records:
        if arrival_event.event_type != "reinforcement_unit_arrived":
            continue
        payload = _json_object(
            arrival_event.payload,
            field_name="Reserve arrival event",
        )
        requested_unit_id = _required_identifier(
            payload.get("unit_instance_id"),
            field_name="Reserve arrival unit",
        )
        raw_stratagem_use = payload.get("stratagem_use")
        authoritative_views = current_rules_unit_views_for_identity(
            state=state,
            unit_instance_id=requested_unit_id,
        )
        authoritative_owner_ids = {view.owner_player_id for view in authoritative_views}
        if len(authoritative_owner_ids) != 1:
            raise GameLifecycleError("Reserve arrival rules-unit owner is ambiguous.")
        authoritative_owner_id = next(iter(authoritative_owner_ids))
        expected_owner_id = relevant_player_id_by_unit_instance_id.get(
            requested_unit_id,
            authoritative_owner_id,
        )
        if expected_owner_id != authoritative_owner_id:
            raise GameLifecycleError("Reserve arrival occurrence owner identity drift.")
        request_id = _required_identifier(
            payload.get("request_id"),
            field_name="Reserve arrival request",
        )
        result_id = _required_identifier(
            payload.get("result_id"),
            field_name="Reserve arrival result",
        )
        matching_decisions = tuple(
            decision
            for decision in decision_records
            if decision.request.request_id == request_id and decision.result.result_id == result_id
        )
        if len(matching_decisions) != 1:
            raise GameLifecycleError("Reserve arrival lacks one accepted placement decision.")
        decision = matching_decisions[0]
        if (
            decision.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
            or decision.result.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
        ):
            raise GameLifecycleError("Reserve arrival decision type drift.")
        try:
            proposal_request = MovementProposalRequest.from_decision_request_payload(
                decision.request.payload
            )
            submitted = PlacementProposalPayload.from_payload(
                cast(PlacementProposalPayloadPayload, decision.result.payload)
            )
            transition_payload = _json_object(
                payload.get("transition_batch"),
                field_name="Reserve arrival transition",
            )
            transition = BattlefieldTransitionBatch.from_payload(
                cast(BattlefieldTransitionBatchPayload, transition_payload)
            )
        except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
            raise GameLifecycleError("Reserve arrival placement evidence is invalid.") from exc
        event_player_id = _required_identifier(
            payload.get("player_id"),
            field_name="Reserve arrival owner",
        )
        active_player_id = _required_identifier(
            payload.get("active_player_id"),
            field_name="Reserve arrival active player",
        )
        battle_round = payload.get("battle_round")
        phase = payload.get("phase")
        large_exception = payload.get("large_model_exception_used")
        restrictions = _unique_identifier_list(
            payload.get("post_arrival_restrictions"),
            field_name="Reserve arrival restrictions",
        )
        submitted_placement = submitted.resolved_rules_unit_placement()
        submitted_pose_by_model_id = {
            placement.model_instance_id: placement.pose
            for placement in submitted_placement.model_placements
        }
        transition_pose_by_model_id = {
            placement.model_instance_id: placement.pose for placement in transition.placements
        }
        event_rules_placement = payload.get("rules_unit_placement")
        requested_events = tuple(
            event
            for event in event_records
            if event.event_type == "decision_requested"
            and event.payload == decision.request.to_payload()
        )
        if len(requested_events) != 1:
            raise GameLifecycleError("Reserve arrival decision request closure drift.")
        placement_request_order = event_index_by_id[requested_events[0].event_id]
        if proposal_request.proposal_kind is not ProposalKind.CULT_AMBUSH:
            validate_primary_reserve_arrival_request_source(
                proposal_request=proposal_request,
                expected_owner_id=expected_owner_id,
                placement_request_order=placement_request_order,
                reserve_entry_occurrences=reserve_entry_occurrences,
                event_records=event_records,
                event_index_by_id=event_index_by_id,
            )
            validate_primary_reserve_arrival_placement_authority(
                state=state,
                proposal_request=proposal_request,
                submitted=submitted,
                transition=transition,
                expected_owner_id=expected_owner_id,
            )
        ingress_use: StratagemUseRecord | None = None
        if raw_stratagem_use is None:
            if (
                proposal_request.context is not None
                and proposal_request.context.get("stratagem_use") is not None
            ):
                raise GameLifecycleError("Normal reserve arrival has Stratagem source drift.")
            if proposal_request.proposal_kind is ProposalKind.CULT_AMBUSH:
                source_active_player_id = validate_cult_ambush_reserve_arrival_source(
                    state=state,
                    proposal_request=proposal_request,
                    arrival_event=arrival_event,
                    event_records=event_records,
                    decision_records=decision_records,
                    event_index_by_id=event_index_by_id,
                    placement_request_order=placement_request_order,
                )
            else:
                source_active_player_id = event_player_id
        elif isinstance(raw_stratagem_use, dict):
            try:
                ingress_use = StratagemUseRecord.from_payload(
                    cast(StratagemUseRecordPayload, raw_stratagem_use)
                )
            except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
                raise GameLifecycleError("Rapid Ingress arrival use evidence is invalid.") from exc
            matching_uses = tuple(use for use in state.stratagem_use_records if use == ingress_use)
            proposal_context = proposal_request.context or {}
            if (
                len(matching_uses) != 1
                or not _proposal_request_is_rapid_ingress(proposal_request)
                or proposal_context.get("stratagem_handler_id") != ingress_use.handler_id
                or ingress_use.player_id != event_player_id
                or ingress_use.request_id != proposal_request.source_decision_request_id
                or ingress_use.result_id != proposal_request.source_decision_result_id
                or proposal_context.get("stratagem_use") != raw_stratagem_use
            ):
                raise GameLifecycleError("Rapid Ingress arrival source identity drift.")
            source_active_player_id = _required_identifier(
                ingress_use.active_player_id,
                field_name="Rapid Ingress active player",
            )
        else:
            raise GameLifecycleError("Reserve arrival Stratagem use evidence is malformed.")
        if proposal_request.proposal_kind is not ProposalKind.CULT_AMBUSH:
            validate_primary_reserve_arrival_event_authority(
                payload=payload,
                proposal_request=proposal_request,
                submitted=submitted,
                ingress_use=ingress_use,
            )
            validate_primary_reserve_arrival_request_chain(
                proposal_request=proposal_request,
                placement_decision=decision,
                expected_owner_id=expected_owner_id,
                ingress_use=ingress_use,
                event_records=event_records,
                decision_records=decision_records,
                event_index_by_id=event_index_by_id,
            )
        if (
            type(battle_round) is not int
            or battle_round <= 0
            or type(phase) is not str
            or phase != BattlePhase.MOVEMENT.value
            or type(large_exception) is not bool
            or payload.get("game_id") != state.game_id
            or event_player_id != expected_owner_id
            or active_player_id != source_active_player_id
            or proposal_request.game_id != state.game_id
            or active_player_id not in state.player_ids
            or proposal_request.request_id != request_id
            or proposal_request.unit_instance_id != requested_unit_id
            or proposal_request.actor_id != event_player_id
            or proposal_request.battle_round != battle_round
            or proposal_request.phase != phase
            or submitted.proposal_request_id != request_id
            or submitted.unit_instance_id != requested_unit_id
            or submitted.placement_kind.value != payload.get("placement_kind")
            or decision.request.actor_id != event_player_id
            or decision.result.actor_id != event_player_id
            or transition.removals
            or transition.displacements
            or submitted_pose_by_model_id != transition_pose_by_model_id
            or any(
                placement.placement_kind is not submitted.placement_kind
                for placement in transition.placements
            )
            or (
                event_rules_placement is not None
                and event_rules_placement != submitted_placement.to_payload()
            )
        ):
            raise GameLifecycleError("Reserve arrival placement identity drift.")
        recorded_events = tuple(
            event
            for event in event_records
            if event.event_type == "decision_recorded" and event.payload == decision.to_payload()
        )
        if len(recorded_events) != 1:
            raise GameLifecycleError("Reserve arrival decision event closure drift.")
        if not (
            event_index_by_id[requested_events[0].event_id]
            < event_index_by_id[recorded_events[0].event_id]
            < event_index_by_id[arrival_event.event_id]
        ):
            raise GameLifecycleError("Reserve arrival decision ordering drift.")
        if ingress_use is not None:
            validate_primary_reserve_arrival_ingress_use_authority(
                state=state,
                use=ingress_use,
                proposal_request=proposal_request,
                event_records=event_records,
                decision_records=decision_records,
                event_index_by_id=event_index_by_id,
                placement_request_order=placement_request_order,
                stratagem_indexes_by_player_id=stratagem_indexes_by_player_id,
            )
        occurrence = _ReserveArrivalOccurrence(
            event_order=event_index_by_id[arrival_event.event_id],
            request_event_order=event_index_by_id[requested_events[0].event_id],
            recorded_event_order=event_index_by_id[recorded_events[0].event_id],
            decision_record_id=decision.record_id,
            decision_request_id=request_id,
            decision_result_id=result_id,
            unit_instance_id=requested_unit_id,
            active_player_id=active_player_id,
            battle_round=battle_round,
            phase=phase,
            large_model_exception_used=large_exception,
            post_arrival_restrictions=restrictions,
        )
        authenticated_occurrences.append(occurrence)
        if requested_unit_id in relevant_player_id_by_unit_instance_id:
            occurrences.append(occurrence)
    for identity_values, field_name in (
        (
            tuple(occurrence.decision_record_id for occurrence in authenticated_occurrences),
            "decision record",
        ),
        (
            tuple(occurrence.decision_request_id for occurrence in authenticated_occurrences),
            "decision request",
        ),
        (
            tuple(occurrence.decision_result_id for occurrence in authenticated_occurrences),
            "decision result",
        ),
    ):
        if len(set(identity_values)) != len(identity_values):
            raise GameLifecycleError(f"Reserve arrival {field_name} is reused.")
    return tuple(occurrences)


def _validate_during_battle_reserve_state_reverse_closure(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    occurrences: tuple[PrimaryReserveEntryLifecycleOccurrence, ...],
    arrival_occurrences: tuple[_ReserveArrivalOccurrence, ...],
    event_index_by_id: dict[str, int],
) -> None:
    during_battle_origins = {
        ReserveOrigin.DURING_BATTLE_ABILITY,
        ReserveOrigin.DURING_BATTLE_STRATAGEM,
        ReserveOrigin.DURING_BATTLE_OTHER,
    }
    occurrences_by_historical_unit_id: dict[str, list[PrimaryReserveEntryLifecycleOccurrence]] = {}
    for occurrence in occurrences:
        occurrences_by_historical_unit_id.setdefault(
            occurrence.historical_unit_instance_id,
            [],
        ).append(occurrence)
    first_entry_order_by_unit_id = {
        unit_instance_id: min(occurrence.event_order for occurrence in unit_occurrences)
        for unit_instance_id, unit_occurrences in occurrences_by_historical_unit_id.items()
    }
    scoped_arrival_occurrences = tuple(
        arrival
        for arrival in arrival_occurrences
        if arrival.event_order > first_entry_order_by_unit_id[arrival.unit_instance_id]
    )
    arrivals_by_unit_id: dict[str, list[_ReserveArrivalOccurrence]] = {}
    for arrival in scoped_arrival_occurrences:
        arrivals_by_unit_id.setdefault(arrival.unit_instance_id, []).append(arrival)
    consumed_arrival_orders: set[int] = set()
    for historical_unit_id, historical_occurrences in occurrences_by_historical_unit_id.items():
        ordered_entries = tuple(
            sorted(historical_occurrences, key=lambda occurrence: occurrence.event_order)
        )
        ordered_arrivals = tuple(
            sorted(
                arrivals_by_unit_id.get(historical_unit_id, []),
                key=lambda arrival: arrival.event_order,
            )
        )
        for prior_entry, later_entry in pairwise(ordered_entries):
            intervening = tuple(
                arrival
                for arrival in ordered_arrivals
                if prior_entry.event_order < arrival.event_order < later_entry.event_order
            )
            if len(intervening) != 1:
                raise GameLifecycleError(
                    "Repeated reserve entry lacks one authenticated intervening arrival."
                )
            if intervening[0].request_event_order <= prior_entry.event_order:
                raise GameLifecycleError(
                    "Repeated reserve arrival decision predates its entry occurrence."
                )
            consumed_arrival_orders.add(intervening[0].event_order)
    current_reserve_ids = {reserve_state.unit_instance_id for reserve_state in state.reserve_states}
    missing_current_ids = set(occurrences_by_historical_unit_id).difference(current_reserve_ids)
    if missing_current_ids:
        raise GameLifecycleError(
            "Authoritative reserve-entry occurrence lacks its canonical ReserveState."
        )
    for reserve_state in state.reserve_states:
        if reserve_state.reserve_origin not in during_battle_origins:
            continue
        direct_occurrences = occurrences_by_historical_unit_id.get(
            reserve_state.unit_instance_id,
            [],
        )
        if not direct_occurrences:
            raise GameLifecycleError(
                "During-battle ReserveState lacks an authoritative entry occurrence."
            )
        latest = max(direct_occurrences, key=lambda occurrence: occurrence.event_order)
        if reserve_entry_evidence_payload(reserve_state) != latest.reserve_entry_state:
            raise GameLifecycleError(
                "During-battle ReserveState drifted from its authoritative entry occurrence."
            )
        consumed_order = _validate_current_reserve_status(
            state=state,
            reserve_state=reserve_state,
            entry_order=latest.event_order,
            arrival_occurrences=tuple(
                arrival
                for arrival in arrivals_by_unit_id.get(reserve_state.unit_instance_id, [])
                if arrival.event_order > latest.event_order
            ),
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
        if consumed_order is not None:
            consumed_arrival_orders.add(consumed_order)
    all_arrival_orders = {arrival.event_order for arrival in scoped_arrival_occurrences}
    if len(all_arrival_orders) != len(scoped_arrival_occurrences) or (
        all_arrival_orders != consumed_arrival_orders
    ):
        raise GameLifecycleError("Reserve arrival occurrence consumption drift.")


def _validate_current_reserve_status(
    *,
    state: GameState,
    reserve_state: ReserveState,
    entry_order: int,
    arrival_occurrences: tuple[_ReserveArrivalOccurrence, ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int | None:
    if any(arrival.request_event_order <= entry_order for arrival in arrival_occurrences):
        raise GameLifecycleError("Reserve arrival decision predates its entry occurrence.")
    if reserve_state.status is ReserveStatus.IN_RESERVES:
        if arrival_occurrences:
            raise GameLifecycleError("Unarrived ReserveState has authenticated arrival evidence.")
        return None
    if reserve_state.status is ReserveStatus.ARRIVED:
        if len(arrival_occurrences) != 1:
            raise GameLifecycleError("Arrived ReserveState lacks one authenticated arrival.")
        arrival = arrival_occurrences[0]
        restrictions_match = (
            tuple(restriction.value for restriction in reserve_state.post_arrival_restrictions)
            == arrival.post_arrival_restrictions
            and reserve_state.restriction_battle_round
            == (arrival.battle_round if arrival.post_arrival_restrictions else None)
        ) or (
            bool(arrival.post_arrival_restrictions)
            and not reserve_state.post_arrival_restrictions
            and reserve_state.restriction_battle_round is None
            and reserve_arrival_restriction_expiry_is_proven(
                state=state,
                arrival_active_player_id=arrival.active_player_id,
                restriction_battle_round=arrival.battle_round,
            )
        )
        if (
            reserve_state.arrived_battle_round != arrival.battle_round
            or reserve_state.arrived_phase != arrival.phase
            or reserve_state.large_model_exception_used != arrival.large_model_exception_used
            or not restrictions_match
        ):
            raise GameLifecycleError("Arrived ReserveState transition evidence drift.")
        return arrival.event_order
    if arrival_occurrences:
        raise GameLifecycleError("Destroyed unarrived ReserveState has arrival evidence.")
    _validate_reserve_deadline_destruction(
        state=state,
        reserve_state=reserve_state,
        entry_order=entry_order,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    return None


def _validate_reserve_deadline_destruction(
    *,
    state: GameState,
    reserve_state: ReserveState,
    entry_order: int,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    destroyed_round = reserve_state.destroyed_battle_round
    if destroyed_round is None:
        raise GameLifecycleError("Destroyed ReserveState lacks its destruction round.")
    policy = reserve_state.destruction_deadline_policy
    boundary_kind = (
        "end-of-battle"
        if policy.timing_kind is ReserveDestructionTimingKind.END_OF_BATTLE
        else "round-boundary"
    )
    expected_mutation_id = f"{policy.source_id}:round-{destroyed_round:02d}:{boundary_kind}"
    candidates = tuple(
        destruction
        for destruction in state.primary_unit_destruction_states
        if destruction.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
        and destruction.source_mutation_id == expected_mutation_id
        and destruction.destroyed_player_id == reserve_state.player_id
        and destruction.battle_round == destroyed_round
        and destruction.destroyed_unit_instance_id == reserve_state.unit_instance_id
    )
    if len(candidates) != 1:
        raise GameLifecycleError(
            "Destroyed ReserveState lacks one authenticated reserve-deadline destruction."
        )
    destruction = candidates[0]
    matching_events = tuple(
        event
        for event in event_records
        if event.event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("primary_unit_destruction_state") == destruction.to_payload()
    )
    if len(matching_events) != 1 or event_index_by_id[matching_events[0].event_id] <= entry_order:
        raise GameLifecycleError("Reserve-deadline destruction event closure drift.")


def _source_terminal_bindings(
    *,
    source_terminal: EventRecord,
    generic: bool,
) -> tuple[_SourceBinding, ...]:
    payload = _json_object(
        source_terminal.payload,
        field_name="Reserve-entry source terminal payload",
    )
    raw_bindings = payload.get(PRIMARY_RESERVE_ENTRY_SOURCE_BINDINGS_KEY)
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise GameLifecycleError("Reserve-entry source terminal requires non-empty bindings.")
    bindings: list[_SourceBinding] = []
    local_occurrence_ids: set[str] = set()
    expected_kind = (
        PrimaryReserveEntryProviderKind.GENERIC_RULE_IR_STRATAGEM
        if generic
        else PrimaryReserveEntryProviderKind.TURN_END_ABILITY
    )
    for raw_binding in raw_bindings:
        binding_payload = _closed_json_object(
            raw_binding,
            field_name="Reserve-entry source terminal binding",
            expected_keys=_SOURCE_BINDING_KEYS,
        )
        provider = PrimaryReserveEntryProvider.from_payload(binding_payload.get("provider"))
        occurrence_id = _required_identifier(
            binding_payload.get("occurrence_id"),
            field_name="Reserve-entry source terminal occurrence",
        )
        reserve_entry = _json_object(
            binding_payload.get("reserve_entry_state"),
            field_name="Reserve-entry source terminal reserve evidence",
        )
        if (
            occurrence_id != provider.occurrence_id
            or provider.source_terminal_event_type != source_terminal.event_type
            or provider.provider_kind is not expected_kind
        ):
            raise GameLifecycleError("Reserve-entry source terminal provider identity drift.")
        if occurrence_id in local_occurrence_ids:
            raise GameLifecycleError("Reserve-entry source terminal occurrence is duplicated.")
        local_occurrence_ids.add(occurrence_id)
        bindings.append(
            _SourceBinding(
                occurrence_id=occurrence_id,
                provider=provider,
                reserve_entry_state=reserve_entry,
                source_terminal=source_terminal,
            )
        )
    return tuple(bindings)


def _validate_generic_source_terminal(
    *,
    state: GameState,
    source_terminal: EventRecord,
    bindings: tuple[_SourceBinding, ...],
) -> None:
    payload = _json_object(
        source_terminal.payload,
        field_name="Generic reserve-entry source terminal",
    )
    use_ids = {binding.provider.stratagem_use_id for binding in bindings}
    if len(use_ids) != 1 or None in use_ids:
        raise GameLifecycleError("Generic reserve-entry source terminal use identity drift.")
    use_id = next(iter(use_ids))
    uses = tuple(use for use in state.stratagem_use_records if use.use_id == use_id)
    if len(uses) != 1:
        raise GameLifecycleError("Generic reserve-entry source terminal use is missing.")
    use = uses[0]
    if (
        payload.get("player_id") != use.player_id
        or payload.get("stratagem_use") != use.to_payload()
        or payload.get("stratagem_effect_payload") != use.effect_payload
        or any(binding.provider.player_id != use.player_id for binding in bindings)
    ):
        raise GameLifecycleError("Generic reserve-entry source terminal use context drift.")
    reserve_states = _source_terminal_reserve_states(payload)
    _validate_source_binding_reserve_states(bindings=bindings, reserve_states=reserve_states)
    effect_payload = _json_object(
        payload.get("generic_rule_effect"),
        field_name="Generic reserve-entry source terminal effect",
    )
    target_ids = _unique_identifier_list(
        effect_payload.get("target_unit_instance_ids"),
        field_name="Generic reserve-entry effect target IDs",
    )
    binding_target_ids = tuple(
        binding.provider.target_rules_unit_instance_id for binding in bindings
    )
    if set(target_ids) != set(binding_target_ids) or len(target_ids) != len(binding_target_ids):
        raise GameLifecycleError("Generic reserve-entry source terminal target-set drift.")
    if any(
        effect_payload.get("source_id") != binding.provider.source_rule_id for binding in bindings
    ):
        raise GameLifecycleError("Generic reserve-entry source terminal RuleIR source drift.")


def _validate_ability_source_terminal(
    *,
    source_terminal: EventRecord,
    bindings: tuple[_SourceBinding, ...],
) -> None:
    if len(bindings) != 1:
        raise GameLifecycleError("Ability reserve-entry source terminal cardinality drift.")
    payload = _json_object(
        source_terminal.payload,
        field_name="Ability reserve-entry source terminal",
    )
    reserve_states = _source_terminal_reserve_states(payload)
    if len(reserve_states) != 1:
        raise GameLifecycleError("Ability reserve-entry source terminal state cardinality drift.")
    _validate_source_binding_reserve_states(bindings=bindings, reserve_states=reserve_states)


def _source_terminal_reserve_states(
    payload: dict[str, JsonValue],
) -> tuple[ReserveState, ...]:
    raw_single = payload.get("reserve_state")
    raw_multiple = payload.get("reserve_states")
    if (raw_single is None) == (raw_multiple is None):
        raise GameLifecycleError("Reserve-entry source terminal reserve-state shape drift.")
    raw_states: list[JsonValue]
    if raw_single is not None:
        raw_states = [raw_single]
    elif isinstance(raw_multiple, list) and raw_multiple:
        raw_states = raw_multiple
    else:
        raise GameLifecycleError("Reserve-entry source terminal reserve states are malformed.")
    states: list[ReserveState] = []
    unit_ids: set[str] = set()
    for raw_state in raw_states:
        if not isinstance(raw_state, dict):
            raise GameLifecycleError("Reserve-entry source terminal ReserveState is malformed.")
        try:
            reserve_state = ReserveState.from_payload(cast(ReserveStatePayload, raw_state))
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError(
                "Reserve-entry source terminal ReserveState is invalid."
            ) from exc
        if (
            reserve_state.status is not ReserveStatus.IN_RESERVES
            or reserve_state.arrived_battle_round is not None
            or reserve_state.arrived_phase is not None
            or reserve_state.destroyed_battle_round is not None
            or reserve_state.post_arrival_restrictions
            or reserve_state.restriction_battle_round is not None
            or reserve_state.large_model_exception_used
        ):
            raise GameLifecycleError(
                "Reserve-entry source terminal must preserve entry-time ReserveState."
            )
        if reserve_state.unit_instance_id in unit_ids:
            raise GameLifecycleError("Reserve-entry source terminal ReserveState is duplicated.")
        unit_ids.add(reserve_state.unit_instance_id)
        states.append(reserve_state)
    return tuple(states)


def _validate_source_binding_reserve_states(
    *,
    bindings: tuple[_SourceBinding, ...],
    reserve_states: tuple[ReserveState, ...],
) -> None:
    states_by_unit_id = {state.unit_instance_id: state for state in reserve_states}
    if len(states_by_unit_id) != len(bindings):
        raise GameLifecycleError("Reserve-entry source terminal state/binding cardinality drift.")
    for binding in bindings:
        reserve_state = states_by_unit_id.get(binding.provider.target_rules_unit_instance_id)
        if reserve_state is None:
            raise GameLifecycleError("Reserve-entry source terminal state/binding target drift.")
        if (
            binding.provider.player_id != reserve_state.player_id
            or binding.provider.reserve_origin is not reserve_state.reserve_origin
            or reserve_state.source_rule_ids != (binding.provider.source_rule_id,)
            or binding.reserve_entry_state != reserve_entry_evidence_payload(reserve_state)
        ):
            raise GameLifecycleError("Reserve-entry source terminal state/binding identity drift.")


def _provider_terminals_by_occurrence(
    event_records: tuple[EventRecord, ...],
) -> dict[str, EventRecord]:
    terminals: dict[str, EventRecord] = {}
    for terminal in event_records:
        if terminal.event_type != PRIMARY_RESERVE_ENTRY_PROVIDER_RESOLVED_EVENT:
            continue
        payload = _closed_json_object(
            terminal.payload,
            field_name="Reserve-entry provider terminal",
            expected_keys=_PROVIDER_TERMINAL_KEYS,
        )
        provider = PrimaryReserveEntryProvider.from_payload(payload.get("provider"))
        occurrence_id = _required_identifier(
            payload.get("occurrence_id"),
            field_name="Reserve-entry provider terminal occurrence",
        )
        reserve_entry = _json_object(
            payload.get("reserve_entry_state"),
            field_name="Reserve-entry provider terminal reserve evidence",
        )
        if occurrence_id != provider.occurrence_id:
            raise GameLifecycleError("Reserve-entry provider terminal occurrence drift.")
        if occurrence_id in terminals:
            raise GameLifecycleError("Reserve-entry provider terminal occurrence is duplicated.")
        if not reserve_entry:
            raise GameLifecycleError("Reserve-entry provider terminal reserve evidence is empty.")
        terminals[occurrence_id] = terminal
    return terminals


def _validate_active_ability_catalog_authority(
    *,
    decisions: DecisionController,
    bindings: tuple[_SourceBinding, ...],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None,
) -> None:
    definitions = default_primary_reserve_entry_ability_provider_definitions()
    for binding in bindings:
        provider = binding.provider
        if provider.provider_kind is not PrimaryReserveEntryProviderKind.TURN_END_ABILITY:
            continue
        matching_definitions = tuple(
            definition
            for definition in definitions
            if definition.provider_id == provider.provider_id
            and definition.source_terminal_event_type == provider.source_terminal_event_type
        )
        if len(matching_definitions) != 1:
            raise GameLifecycleError("Ability reserve-entry provider definition drift.")
        definition = matching_definitions[0]
        if definition.authority_kind is not PrimaryReserveEntryAbilityAuthorityKind.CATALOG_RULE_IR:
            continue
        if ability_indexes_by_player_id is None:
            raise GameLifecycleError(
                "Catalog reserve-entry provider requires active Ability catalog authority."
            )
        player_index = ability_indexes_by_player_id.get(provider.player_id)
        if type(player_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "Catalog reserve-entry provider lacks its active player Ability index."
            )
        source_payload = _json_object(
            binding.source_terminal.payload,
            field_name="Catalog reserve-entry source terminal",
        )
        catalog_record_id = _required_identifier(
            source_payload.get("catalog_record_id"),
            field_name="Catalog reserve-entry record",
        )
        active_records = tuple(
            record for record in player_index.all_records() if record.record_id == catalog_record_id
        )
        matching_decisions = tuple(
            decision
            for decision in decisions.records
            if decision.record_id == provider.decision_record_id
            and decision.request.request_id == provider.decision_request_id
            and decision.result.result_id == provider.decision_result_id
        )
        if len(active_records) != 1 or len(matching_decisions) != 1:
            raise GameLifecycleError("Catalog reserve-entry active Ability authority drift.")
        active_record = active_records[0]
        decision = matching_decisions[0]
        request_payload = _json_object(
            decision.request.payload,
            field_name="Catalog reserve-entry request",
        )
        result_payload = _json_object(
            decision.result.payload,
            field_name="Catalog reserve-entry result",
        )
        if (
            active_record.disabled
            or active_record.definition.source_id != provider.source_rule_id
            or request_payload.get("catalog_record_id") != active_record.record_id
            or result_payload.get("catalog_record_id") != active_record.record_id
            or source_payload.get("ability_id") != active_record.definition.ability_id
            or source_payload.get("ability_name") != active_record.definition.name
            or request_payload.get("ability_id") != active_record.definition.ability_id
            or request_payload.get("ability_name") != active_record.definition.name
            or result_payload.get("ability_id") != active_record.definition.ability_id
            or result_payload.get("ability_name") != active_record.definition.name
        ):
            raise GameLifecycleError("Catalog reserve-entry active Ability authority drift.")


def _validate_active_stratagem_catalog_authority(
    *,
    state: GameState,
    decision_records: tuple[DecisionRecord, ...],
    providers: tuple[PrimaryReserveEntryProvider, ...],
    stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex] | None,
) -> None:
    if not providers:
        return
    if stratagem_indexes_by_player_id is None:
        raise GameLifecycleError(
            "Generic reserve-entry provider requires active runtime Stratagem catalog authority."
        )
    validated_use_ids: set[str] = set()
    for provider in providers:
        if provider.stratagem_use_id is None:
            raise GameLifecycleError("Generic reserve-entry provider use identity is missing.")
        if provider.stratagem_use_id in validated_use_ids:
            continue
        validated_use_ids.add(provider.stratagem_use_id)
        player_index = stratagem_indexes_by_player_id.get(provider.player_id)
        if type(player_index) is not StratagemCatalogIndex:
            raise GameLifecycleError(
                "Generic reserve-entry provider lacks its active player Stratagem index."
            )
        decisions = tuple(
            record
            for record in decision_records
            if record.record_id == provider.decision_record_id
            and record.request.request_id == provider.decision_request_id
            and record.result.result_id == provider.decision_result_id
        )
        if len(decisions) != 1:
            raise GameLifecycleError("Generic reserve-entry provider accepted decision is missing.")
        decision = decisions[0]
        if decision.request.decision_type == STRATAGEM_DECISION_TYPE:
            selection = stratagem_selection_from_decision_result(decision.result)
        elif decision.request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
            selection = stratagem_selection_from_target_proposal_result(decision.result)
        else:
            selection = None
        if selection is None:
            raise GameLifecycleError(
                "Generic reserve-entry provider accepted catalog selection is malformed."
            )
        _context, selected_record, _target_binding, _effect_selection = selection
        active_records = tuple(
            record
            for record in player_index.all_records()
            if record.record_id == selected_record.record_id
        )
        if (
            len(active_records) != 1
            or active_records[0].to_payload() != selected_record.to_payload()
            or active_records[0].disabled
        ):
            raise GameLifecycleError(
                "Generic reserve-entry provider active catalog authority drift."
            )
        uses = tuple(
            use for use in state.stratagem_use_records if use.use_id == provider.stratagem_use_id
        )
        if len(uses) != 1:
            raise GameLifecycleError("Generic reserve-entry provider active use is missing.")
        use = uses[0]
        active_definition = active_records[0].definition
        if (
            use.player_id != provider.player_id
            or use.stratagem_id != active_definition.stratagem_id
            or use.source_id != active_definition.source_id
            or use.handler_id != active_definition.handler_id
            or use.effect_payload != active_definition.effect_payload
        ):
            raise GameLifecycleError(
                "Generic reserve-entry provider active Stratagem definition drift."
            )
        from warhammer40k_core.engine.rule_execution import (
            scoped_rule_ir_from_execution_payload,
        )
        from warhammer40k_core.rules.rule_ir import RuleIRError

        try:
            rule_ir = scoped_rule_ir_from_execution_payload(active_definition.effect_payload)
        except RuleIRError as exc:
            raise GameLifecycleError(
                "Generic reserve-entry provider active RuleIR is invalid."
            ) from exc
        if rule_ir.source_id != provider.source_rule_id:
            raise GameLifecycleError("Generic reserve-entry provider active RuleIR source drift.")


def _closed_json_object(
    value: object,
    *,
    field_name: str,
    expected_keys: frozenset[str],
) -> dict[str, JsonValue]:
    payload = _json_object(value, field_name=field_name)
    if set(payload) != set(expected_keys):
        raise GameLifecycleError(f"{field_name} fields are malformed.")
    return payload


def _json_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _required_identifier(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


def _unique_identifier_list(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{field_name} must be an identifier list.")
    raw_values = cast(list[object], value)
    if any(type(item) is not str for item in raw_values):
        raise GameLifecycleError(f"{field_name} must be an identifier list.")
    identifiers = tuple(cast(str, item) for item in raw_values)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return identifiers


__all__ = ("validate_primary_reserve_entry_lifecycle_integrity",)
