from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import CharacteristicValue, CharacteristicValuePayload
from warhammer40k_core.core.descriptor_hash import (
    canonical_payload_sha256,
    validate_sha256_hex,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlHookRegistry,
    StickyObjectiveControlState,
    StickyObjectiveControlStatePayload,
    apply_sticky_objective_control,
    sticky_objective_control_state_is_expired,
)
from warhammer40k_core.engine.stratagems_generic_metadata import objective_marker_id_or_none
from warhammer40k_core.engine.stratagems_model import (
    StratagemUseRecord,
    StratagemUseRecordPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
        PrimaryMissionBoundaryCheckpoint,
    )
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex


OBJECTIVE_CONTROL_RECORD_AUTHORITY_SCHEMA = "objective-control-record-authority-v1"
_OBJECTIVE_CONTROL_RECORD_AUTHORITY_ID_PREFIX = "objective-control-record-authority"
_OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE = "end_boundary_objective_control_determined"
_OBJECTIVE_CONTROL_BOUNDARY_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
)
_LIFECYCLE_TIMING_SOURCE_RULE_ID = "core-rules-lifecycle-timing"
_PHASE_HOOK_STICKY_EVENT_TYPE = "sticky_objective_control_state_recorded"
_GENERIC_STRATAGEM_STICKY_EVENT_TYPE = "generic_stratagem_sticky_objective_control_registered"


class ObjectiveControlRecordAuthorityPayload(TypedDict):
    schema_version: str
    objective_control_record_id: str
    objective_control_record_hash: str
    boundary_checkpoint: dict[str, JsonValue]
    retained_sticky_objective_control_states: list[StickyObjectiveControlStatePayload]
    authority_id: str
    authority_hash: str


@dataclass(frozen=True, slots=True)
class ObjectiveControlRecordAuthority:
    schema_version: str
    objective_control_record_id: str
    objective_control_record_hash: str
    boundary_checkpoint: PrimaryMissionBoundaryCheckpoint
    retained_sticky_objective_control_states: tuple[StickyObjectiveControlState, ...]
    authority_id: str
    authority_hash: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
            PrimaryMissionBoundaryCheckpoint,
        )

        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("schema_version", self.schema_version),
        )
        if self.schema_version != OBJECTIVE_CONTROL_RECORD_AUTHORITY_SCHEMA:
            raise GameLifecycleError("ObjectiveControlRecord authority schema is unsupported.")
        object.__setattr__(
            self,
            "objective_control_record_id",
            _validate_identifier(
                "objective_control_record_id",
                self.objective_control_record_id,
            ),
        )
        object.__setattr__(
            self,
            "objective_control_record_hash",
            validate_sha256_hex(
                self.objective_control_record_hash,
                field_name="objective_control_record_hash",
                error_type=GameLifecycleError,
            ),
        )
        if type(self.boundary_checkpoint) is not PrimaryMissionBoundaryCheckpoint:
            raise GameLifecycleError(
                "ObjectiveControlRecord authority requires a typed boundary checkpoint."
            )
        object.__setattr__(
            self,
            "retained_sticky_objective_control_states",
            _sticky_state_witnesses(self.retained_sticky_objective_control_states),
        )
        object.__setattr__(
            self,
            "authority_id",
            _validate_identifier("authority_id", self.authority_id),
        )
        object.__setattr__(
            self,
            "authority_hash",
            validate_sha256_hex(
                self.authority_hash,
                field_name="authority_hash",
                error_type=GameLifecycleError,
            ),
        )
        expected_hash = canonical_payload_sha256(self._content_payload())
        if self.authority_hash != expected_hash:
            raise GameLifecycleError("ObjectiveControlRecord authority hash drifted.")
        if self.authority_id != f"{_OBJECTIVE_CONTROL_RECORD_AUTHORITY_ID_PREFIX}:{expected_hash}":
            raise GameLifecycleError("ObjectiveControlRecord authority identity drifted.")

    @classmethod
    def create(
        cls,
        *,
        record: ObjectiveControlRecord,
        boundary_checkpoint: PrimaryMissionBoundaryCheckpoint,
        retained_sticky_objective_control_states: tuple[StickyObjectiveControlState, ...],
    ) -> Self:
        from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
            PrimaryMissionBoundaryCheckpoint,
        )

        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError("ObjectiveControlRecord authority requires a typed record.")
        if type(boundary_checkpoint) is not PrimaryMissionBoundaryCheckpoint:
            raise GameLifecycleError(
                "ObjectiveControlRecord authority requires a typed boundary checkpoint."
            )
        witnesses = _sticky_state_witnesses(retained_sticky_objective_control_states)
        content: dict[str, object] = {
            "schema_version": OBJECTIVE_CONTROL_RECORD_AUTHORITY_SCHEMA,
            "objective_control_record_id": record.record_id,
            "objective_control_record_hash": objective_control_record_hash(record),
            "boundary_checkpoint": boundary_checkpoint.to_payload(),
            "retained_sticky_objective_control_states": [state.to_payload() for state in witnesses],
        }
        digest = canonical_payload_sha256(content)
        return cls(
            schema_version=OBJECTIVE_CONTROL_RECORD_AUTHORITY_SCHEMA,
            objective_control_record_id=record.record_id,
            objective_control_record_hash=objective_control_record_hash(record),
            boundary_checkpoint=boundary_checkpoint,
            retained_sticky_objective_control_states=witnesses,
            authority_id=f"{_OBJECTIVE_CONTROL_RECORD_AUTHORITY_ID_PREFIX}:{digest}",
            authority_hash=digest,
        )

    def _content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "objective_control_record_id": self.objective_control_record_id,
            "objective_control_record_hash": self.objective_control_record_hash,
            "boundary_checkpoint": self.boundary_checkpoint.to_payload(),
            "retained_sticky_objective_control_states": [
                state.to_payload() for state in self.retained_sticky_objective_control_states
            ],
        }

    def to_payload(self) -> ObjectiveControlRecordAuthorityPayload:
        payload = {
            **self._content_payload(),
            "authority_id": self.authority_id,
            "authority_hash": self.authority_hash,
        }
        return cast(ObjectiveControlRecordAuthorityPayload, validate_json_value(payload))

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
            PrimaryMissionBoundaryCheckpoint,
        )

        raw = _payload_object(payload)
        return cls(
            schema_version=_payload_string(raw, "schema_version"),
            objective_control_record_id=_payload_string(
                raw,
                "objective_control_record_id",
            ),
            objective_control_record_hash=_payload_string(
                raw,
                "objective_control_record_hash",
            ),
            boundary_checkpoint=PrimaryMissionBoundaryCheckpoint.from_payload(
                raw["boundary_checkpoint"]
            ),
            retained_sticky_objective_control_states=tuple(
                StickyObjectiveControlState.from_payload(
                    cast(StickyObjectiveControlStatePayload, value)
                )
                for value in _payload_list(
                    raw,
                    "retained_sticky_objective_control_states",
                )
            ),
            authority_id=_payload_string(raw, "authority_id"),
            authority_hash=_payload_string(raw, "authority_hash"),
        )


def capture_objective_control_record_authority(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecordAuthority:
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        capture_primary_mission_boundary_checkpoint,
    )

    registry = (
        RuntimeModifierRegistry.empty()
        if runtime_modifier_registry is None
        else runtime_modifier_registry
    )
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "ObjectiveControlRecord authority requires a RuntimeModifierRegistry."
        )
    witnesses = _relevant_sticky_state_witnesses(
        record=record,
        values=tuple(state.sticky_objective_control_states),
    )
    checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="objective_control",
        player_id=record.active_player_id,
        runtime_modifier_registry=registry,
    )
    authority = ObjectiveControlRecordAuthority.create(
        record=record,
        boundary_checkpoint=checkpoint,
        retained_sticky_objective_control_states=witnesses,
    )
    validate_objective_control_record_authority(
        state=state,
        record=record,
        authority=authority,
    )
    return authority


def validate_objective_control_record_authorities(
    values: object,
    *,
    state: GameState,
    records: tuple[ObjectiveControlRecord, ...],
) -> list[ObjectiveControlRecordAuthority]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState ObjectiveControlRecord authorities must be a list.")
    if type(records) is not tuple or any(
        type(record) is not ObjectiveControlRecord for record in records
    ):
        raise GameLifecycleError("ObjectiveControlRecord authority validation requires records.")
    authorities: list[ObjectiveControlRecordAuthority] = []
    seen_authority_ids: set[str] = set()
    seen_record_ids: set[str] = set()
    records_by_id = {record.record_id: record for record in records}
    for value in cast(list[object], values):
        if type(value) is not ObjectiveControlRecordAuthority:
            raise GameLifecycleError(
                "GameState ObjectiveControlRecord authorities must contain typed records."
            )
        authority = value
        if authority.authority_id in seen_authority_ids:
            raise GameLifecycleError("ObjectiveControlRecord authority identity is duplicated.")
        if authority.objective_control_record_id in seen_record_ids:
            raise GameLifecycleError("ObjectiveControlRecord authority record is duplicated.")
        record = records_by_id.get(authority.objective_control_record_id)
        if record is None:
            raise GameLifecycleError(
                "ObjectiveControlRecord authority references a missing record."
            )
        validate_objective_control_record_authority(
            state=state,
            record=record,
            authority=authority,
            record_history=records,
        )
        seen_authority_ids.add(authority.authority_id)
        seen_record_ids.add(authority.objective_control_record_id)
        authorities.append(authority)
    if seen_record_ids != set(records_by_id):
        raise GameLifecycleError("ObjectiveControlRecord authority registry is incomplete.")
    authorities_by_record_id = {
        authority.objective_control_record_id: authority for authority in authorities
    }
    return [authorities_by_record_id[record.record_id] for record in records]


def validate_objective_control_record_authority(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    authority: ObjectiveControlRecordAuthority,
    record_history: tuple[ObjectiveControlRecord, ...] = (),
) -> None:
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("ObjectiveControlRecord authority requires a typed record.")
    if type(authority) is not ObjectiveControlRecordAuthority:
        raise GameLifecycleError("ObjectiveControlRecord authority record is invalid.")
    checkpoint = authority.boundary_checkpoint
    if (
        authority.objective_control_record_id != record.record_id
        or authority.objective_control_record_hash != objective_control_record_hash(record)
    ):
        raise GameLifecycleError("ObjectiveControlRecord authority record binding drifted.")
    if (
        checkpoint.boundary_kind != "objective_control"
        or checkpoint.game_id != record.game_id
        or checkpoint.player_id != record.active_player_id
        or checkpoint.active_player_id != record.active_player_id
        or checkpoint.battle_round != record.battle_round
        or checkpoint.phase != record.phase
        or checkpoint.battlefield_id != record.battlefield_id
    ):
        raise GameLifecycleError("ObjectiveControlRecord authority boundary context drifted.")
    _validate_checkpoint_model_identity(state=state, checkpoint=checkpoint)
    _validate_sticky_state_provenance(
        state=state,
        record=record,
        values=authority.retained_sticky_objective_control_states,
        record_history=record_history,
    )
    _validate_current_boundary_battle_shock(
        state=state,
        record=record,
        checkpoint=checkpoint,
        record_history=record_history,
    )
    spatial_record = _frozen_spatial_record(
        state=state,
        record=record,
        checkpoint=checkpoint,
    )
    spatial_results_by_id = {result.objective_id: result for result in spatial_record.results}
    if set(spatial_results_by_id) != {result.objective_id for result in record.results}:
        raise GameLifecycleError("ObjectiveControlRecord objective source inventory drifted.")
    base_results = tuple(
        _base_result_from_authority(
            result=result,
            spatial_result=spatial_results_by_id[result.objective_id],
            checkpoint=checkpoint,
        )
        for result in record.results
    )
    base_record = ObjectiveControlRecord(
        record_id=record.record_id,
        game_id=record.game_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        timing=record.timing,
        phase=record.phase,
        battlefield_id=record.battlefield_id,
        results=base_results,
    )
    expected = apply_sticky_objective_control(
        record=base_record,
        states=authority.retained_sticky_objective_control_states,
    )
    if expected.results != record.results:
        raise GameLifecycleError(
            "ObjectiveControlRecord authority score, status, or retained-control "
            "provenance drifted."
        )


def validate_objective_control_record_authority_lifecycle_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
    phase_end_objective_control_hook_registry: (PhaseEndObjectiveControlHookRegistry | None) = None,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    """Authenticate embedded OC checkpoints against lifecycle events and runtime sources."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        validate_primary_mission_boundary_checkpoint,
        validate_primary_mission_boundary_checkpoint_runtime_source_registry,
    )
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        validate_primary_mission_boundary_physical_authority,
    )
    from warhammer40k_core.engine.primary_mission_boundary_unit_history_authority import (
        validate_primary_mission_boundary_unit_history_authority,
    )
    from warhammer40k_core.engine.primary_mission_objective_control_source_authority import (
        validate_primary_mission_oc_effect_event_authority,
    )

    if type(state) is not GameState:
        raise GameLifecycleError("ObjectiveControlRecord lifecycle authority requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord lifecycle authority requires EventRecord history."
        )
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord lifecycle authority requires DecisionRecord history."
        )
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "ObjectiveControlRecord lifecycle authority requires a RuntimeModifierRegistry."
        )
    if (
        phase_end_objective_control_hook_registry is not None
        and type(phase_end_objective_control_hook_registry)
        is not PhaseEndObjectiveControlHookRegistry
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord lifecycle authority requires a phase-end hook registry."
        )
    records_by_id = {record.record_id: record for record in state.objective_control_records}
    _validate_current_sticky_state_event_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        phase_end_objective_control_hook_registry=(phase_end_objective_control_hook_registry),
    )
    from warhammer40k_core.engine.objective_control_boundary_history_integrity import (
        validate_objective_control_boundary_history_integrity,
    )

    validate_objective_control_boundary_history_integrity(
        state=state,
        event_records=event_records,
        records=tuple(state.objective_control_records),
        authorities=tuple(state.objective_control_record_authorities),
    )
    for authority in state.objective_control_record_authorities:
        record = records_by_id[authority.objective_control_record_id]
        checkpoint = authority.boundary_checkpoint
        validate_primary_mission_boundary_checkpoint(
            state=state,
            checkpoint=checkpoint,
            validate_retained_same_turn_state=True,
        )
        validate_primary_mission_boundary_checkpoint_runtime_source_registry(
            checkpoint=checkpoint,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        boundary_index = _objective_control_boundary_event_index_or_none(
            event_records=event_records,
            record=record,
        )
        if boundary_index is None:
            if authority.retained_sticky_objective_control_states:
                raise GameLifecycleError(
                    "ObjectiveControlRecord retained sticky authority lacks an exact "
                    "boundary event."
                )
            continue
        validate_primary_mission_boundary_physical_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            checkpoint_index=boundary_index,
            checkpoint=checkpoint,
        )
        validate_primary_mission_boundary_unit_history_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            checkpoint_index=boundary_index,
            checkpoint=checkpoint,
        )
        validate_primary_mission_oc_effect_event_authority(
            state=state,
            event_records=event_records,
            checkpoint_index=boundary_index,
            checkpoint=checkpoint,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        _validate_sticky_witness_event_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            boundary_index=boundary_index,
            witnesses=authority.retained_sticky_objective_control_states,
            phase_end_objective_control_hook_registry=(phase_end_objective_control_hook_registry),
        )


def objective_control_record_hash(record: ObjectiveControlRecord) -> str:
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("ObjectiveControlRecord hash requires a typed record.")
    return canonical_payload_sha256(record.to_payload())


def _objective_control_boundary_event_index_or_none(
    *,
    event_records: tuple[EventRecord, ...],
    record: ObjectiveControlRecord,
) -> int | None:
    expected_payload: dict[str, JsonValue] = {
        "game_id": record.game_id,
        "battle_round": record.battle_round,
        "phase": record.phase,
        "record_ids": [record.record_id],
        "source_rule_id": _OBJECTIVE_CONTROL_BOUNDARY_SOURCE_RULE_ID,
    }
    matches = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == _OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE
        and event.payload == expected_payload
    )
    if len(matches) > 1:
        raise GameLifecycleError("ObjectiveControlRecord authority lacks an exact boundary event.")
    return None if not matches else matches[0]


def _validate_sticky_witness_event_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    boundary_index: int,
    witnesses: tuple[StickyObjectiveControlState, ...],
    phase_end_objective_control_hook_registry: (PhaseEndObjectiveControlHookRegistry | None),
) -> None:
    prior_events = event_records[:boundary_index]
    for witness in witnesses:
        _validate_sticky_state_event_authority(
            state=state,
            event_records=prior_events,
            decision_records=decision_records,
            witness=witness,
            phase_end_objective_control_hook_registry=(phase_end_objective_control_hook_registry),
        )


def _validate_current_sticky_state_event_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    phase_end_objective_control_hook_registry: (PhaseEndObjectiveControlHookRegistry | None),
) -> None:
    for witness in state.sticky_objective_control_states:
        _validate_sticky_state_event_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            witness=witness,
            phase_end_objective_control_hook_registry=(phase_end_objective_control_hook_registry),
        )


def _validate_sticky_state_event_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    witness: StickyObjectiveControlState,
    phase_end_objective_control_hook_registry: (PhaseEndObjectiveControlHookRegistry | None),
) -> None:
    candidates = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type in {_PHASE_HOOK_STICKY_EVENT_TYPE, _GENERIC_STRATAGEM_STICKY_EVENT_TYPE}
        and isinstance(event.payload, dict)
        and event.payload.get("sticky_objective_control_state") == witness.to_payload()
    )
    if len(candidates) != 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord sticky witness lacks exact creation-event authority."
        )
    creation_index, creation_event = candidates[0]
    if creation_event.event_type == _PHASE_HOOK_STICKY_EVENT_TYPE:
        _validate_phase_hook_sticky_event(
            state=state,
            event=creation_event,
            witness=witness,
            phase_end_objective_control_hook_registry=(phase_end_objective_control_hook_registry),
        )
        return
    _validate_generic_stratagem_sticky_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        creation_index=creation_index,
        event=creation_event,
        witness=witness,
    )


def _validate_phase_hook_sticky_event(
    *,
    state: GameState,
    event: EventRecord,
    witness: StickyObjectiveControlState,
    phase_end_objective_control_hook_registry: (PhaseEndObjectiveControlHookRegistry | None),
) -> None:
    expected_payload: dict[str, JsonValue] = {
        "game_id": witness.game_id,
        "battle_round": witness.battle_round,
        "active_player_id": witness.active_player_id,
        "phase": witness.phase,
        "sticky_objective_control_state": validate_json_value(witness.to_payload()),
    }
    if event.payload != expected_payload:
        raise GameLifecycleError("ObjectiveControlRecord phase-hook sticky creation event drifted.")
    matching_bindings = (
        ()
        if phase_end_objective_control_hook_registry is None
        else tuple(
            binding
            for binding in phase_end_objective_control_hook_registry.all_bindings()
            if binding.source_id == witness.source_rule_id
        )
    )
    if not matching_bindings:
        raise GameLifecycleError(
            "ObjectiveControlRecord sticky source is absent from the loaded phase-hook registry."
        )
    _validate_phase_hook_sticky_semantics(state=state, witness=witness)


def _validate_phase_hook_sticky_semantics(
    *,
    state: GameState,
    witness: StickyObjectiveControlState,
) -> None:
    originating_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=witness.originating_unit_instance_id,
    )
    if originating_rules_unit.owner_player_id != witness.player_id:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky originating unit ownership drifted."
        )
    source_records = tuple(
        record
        for record in state.objective_control_records
        if record.game_id == witness.game_id
        and record.battle_round == witness.battle_round
        and record.active_player_id == witness.active_player_id
        and record.phase == witness.phase
        and record.timing is ObjectiveControlTiming.PHASE_END
    )
    if len(source_records) != 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky lacks one source boundary."
        )
    source_results = tuple(
        result
        for result in source_records[0].results
        if result.objective_id == witness.objective_id
    )
    if len(source_results) != 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky objective source drifted."
        )
    result = source_results[0]
    component_ids = set(originating_rules_unit.component_unit_instance_ids)
    if result.controlled_by_player_id != witness.player_id or not any(
        contribution.unit_instance_id in component_ids for contribution in result.contributors
    ):
        raise GameLifecycleError("ObjectiveControlRecord phase-hook sticky control source drifted.")
    _validate_phase_hook_sticky_replay_payload(witness)


def _validate_phase_hook_sticky_replay_payload(witness: StickyObjectiveControlState) -> None:
    payload = witness.replay_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky replay payload must be an object."
        )
    if payload.get("objective_id") != witness.objective_id:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky replay objective drifted."
        )
    originating_keys = (
        "originating_unit_instance_id",
        "unit_instance_id",
        "attacking_unit_instance_id",
    )
    originating_values = tuple(payload[key] for key in originating_keys if key in payload)
    if not originating_values or any(
        value != witness.originating_unit_instance_id for value in originating_values
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky replay originating unit drifted."
        )
    if (
        "destroyed_unit_instance_id" in payload
        and payload["destroyed_unit_instance_id"] != witness.destroyed_unit_instance_id
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-hook sticky replay destroyed unit drifted."
        )
    if "source_rule_id" in payload and payload["source_rule_id"] != witness.source_rule_id:
        raise GameLifecycleError("ObjectiveControlRecord phase-hook sticky replay source drifted.")
    player_keys = ("controlling_player_id", "player_id", "owner_player_id")
    if any(key in payload and payload[key] != witness.player_id for key in player_keys):
        raise GameLifecycleError("ObjectiveControlRecord phase-hook sticky replay player drifted.")


def _validate_generic_stratagem_sticky_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    creation_index: int,
    event: EventRecord,
    witness: StickyObjectiveControlState,
) -> None:
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky event is invalid."
        )
    raw_use = payload.get("stratagem_use")
    if not isinstance(raw_use, dict):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky event lacks its use."
        )
    use = StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, raw_use))
    expected_payload: dict[str, JsonValue] = {
        "game_id": witness.game_id,
        "player_id": use.player_id,
        "battle_round": use.battle_round,
        "phase": use.phase.value,
        "active_player_id": use.active_player_id,
        "stratagem_use": validate_json_value(use.to_payload()),
        "sticky_objective_control_state": validate_json_value(witness.to_payload()),
    }
    if (
        payload != expected_payload
        or witness.player_id != use.player_id
        or witness.source_event_id != use.use_id
        or witness.battle_round != use.battle_round
        or witness.phase != use.phase.value
        or witness.active_player_id != use.active_player_id
        or witness.originating_unit_instance_id not in use.targeted_unit_instance_ids
    ):
        raise GameLifecycleError("ObjectiveControlRecord generic Stratagem sticky source drifted.")
    _validate_generic_stratagem_sticky_semantics(use=use, witness=witness)
    stored_uses = tuple(stored for stored in state.stratagem_use_records if stored == use)
    if len(stored_uses) != 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky use lacks state authority."
        )
    used_events = tuple(
        candidate
        for candidate in event_records[:creation_index]
        if candidate.event_type == "stratagem_used" and candidate.payload == use.to_payload()
    )
    if len(used_events) != 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky use lacks exact event authority."
        )
    decisions = tuple(
        record
        for record in decision_records
        if record.request.request_id == use.request_id and record.result.result_id == use.result_id
    )
    if (
        len(decisions) != 1
        or decisions[0].request.actor_id != use.player_id
        or decisions[0].result.selected_option_id != use.selected_option_id
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky use lacks decision authority."
        )


def _validate_generic_stratagem_sticky_semantics(
    *,
    use: StratagemUseRecord,
    witness: StickyObjectiveControlState,
) -> None:
    objective_id = objective_marker_id_or_none(use.effect_selection)
    if objective_id != witness.objective_id or len(use.targeted_unit_instance_ids) != 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky target semantics drifted."
        )
    target_unit_id = use.targeted_unit_instance_ids[0]
    if (
        witness.state_id != f"{use.use_id}:sticky-objective:{objective_id}"
        or witness.source_event_id != use.use_id
        or witness.originating_unit_instance_id != target_unit_id
        or witness.destroyed_unit_instance_id != target_unit_id
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky identity semantics drifted."
        )
    replay = witness.replay_payload
    if not isinstance(replay, dict):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky replay payload must be an object."
        )
    if (
        replay.get("stratagem_id") != use.stratagem_id
        or replay.get("stratagem_use_id") != use.use_id
        or replay.get("target_unit_instance_id") != target_unit_id
        or replay.get("objective_id") != objective_id
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky replay semantics drifted."
        )
    generic_effect = replay.get("generic_rule_effect")
    if not isinstance(generic_effect, dict) or generic_effect.get("source_id") != (
        witness.source_rule_id
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky effect source drifted."
        )
    if not isinstance(replay.get("generic_rule_execution_result"), dict):
        raise GameLifecycleError(
            "ObjectiveControlRecord generic Stratagem sticky execution evidence is invalid."
        )


def _base_result_from_authority(
    *,
    result: ObjectiveControlResult,
    spatial_result: ObjectiveControlResult,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> ObjectiveControlResult:
    if result.status is ObjectiveControlStatus.UNSUPPORTED:
        reason = result.unsupported_reason
        if reason is None or spatial_result != result:
            raise GameLifecycleError("Unsupported ObjectiveControlRecord result lacks a reason.")
        return ObjectiveControlResult.unsupported(
            objective_id=result.objective_id,
            unsupported_reason=reason,
        )
    spatial_contributors = {
        contribution.model_instance_id: contribution for contribution in spatial_result.contributors
    }
    if set(spatial_contributors) != {
        contribution.model_instance_id for contribution in result.contributors
    }:
        raise GameLifecycleError("ObjectiveControlRecord contributor objective membership drifted.")
    models_by_id = {row.model_instance_id: row for row in checkpoint.model_states}
    for contribution in result.contributors:
        model = models_by_id.get(contribution.model_instance_id)
        spatial = spatial_contributors[contribution.model_instance_id]
        if model is None:
            raise GameLifecycleError(
                "ObjectiveControlRecord contributor model lacks checkpoint authority."
            )
        shocked = bool(
            {model.rules_unit_instance_id, model.component_unit_instance_id}.intersection(
                checkpoint.battle_shocked_unit_instance_ids
            )
        )
        resolved = CharacteristicValue.from_payload(
            cast(
                CharacteristicValuePayload,
                _canonical_json_object(model.resolved_objective_control_json),
            )
        )
        expected_effective = 0 if shocked else resolved.final
        if (
            contribution.player_id != model.owner_player_id
            or contribution.unit_instance_id != model.component_unit_instance_id
            or (
                contribution.player_id,
                contribution.unit_instance_id,
                contribution.model_instance_id,
                contribution.horizontal_distance_inches,
                contribution.vertical_gap_inches,
            )
            != (
                spatial.player_id,
                spatial.unit_instance_id,
                spatial.model_instance_id,
                spatial.horizontal_distance_inches,
                spatial.vertical_gap_inches,
            )
            or not model.alive
            or model.presence != "battlefield"
            or contribution.battle_shocked is not shocked
            or contribution.objective_control != resolved.final
            or contribution.effective_objective_control != expected_effective
        ):
            raise GameLifecycleError(
                "ObjectiveControlRecord contributor identity or characteristic authority drifted."
            )
    return ObjectiveControlResult.from_contributors(
        objective_id=result.objective_id,
        contributors=result.contributors,
    )


def _frozen_spatial_record(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> ObjectiveControlRecord:
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldRuntimeState,
        BattlefieldScenario,
        ModelPlacement,
        ModelPlacementPayload,
        PlacedArmy,
        UnitPlacement,
    )
    from warhammer40k_core.engine.objective_control_sources import (
        resolve_objective_control_sources,
    )

    setup = state.mission_setup
    current_battlefield = state.battlefield_state
    if setup is None:
        raise GameLifecycleError(
            "ObjectiveControlRecord authority requires mission battlefield state."
        )
    if current_battlefield is None:
        raise GameLifecycleError(
            "ObjectiveControlRecord authority cannot restore with missing battlefield_state."
        )
    checkpoint_by_model_id = {row.model_instance_id: row for row in checkpoint.model_states}
    frozen_armies = tuple(
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(
                            model,
                            wounds_remaining=checkpoint_by_model_id[
                                model.model_instance_id
                            ].wounds_remaining,
                        )
                        for model in unit.own_models
                    ),
                )
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    )
    placements_by_unit_id: dict[str, list[ModelPlacement]] = {}
    for row in checkpoint.model_states:
        if row.model_placement_json is None:
            continue
        placement = ModelPlacement.from_payload(
            cast(
                ModelPlacementPayload,
                _canonical_json_object(row.model_placement_json),
            )
        )
        placements_by_unit_id.setdefault(placement.unit_instance_id, []).append(placement)
    placed_armies_by_id: dict[str, list[UnitPlacement]] = {}
    army_owner_by_id: dict[str, str] = {}
    for placements in placements_by_unit_id.values():
        first = placements[0]
        army_owner_by_id[first.army_id] = first.player_id
        placed_armies_by_id.setdefault(first.army_id, []).append(
            UnitPlacement(
                army_id=first.army_id,
                player_id=first.player_id,
                unit_instance_id=first.unit_instance_id,
                model_placements=tuple(placements),
            )
        )
    frozen_battlefield = BattlefieldRuntimeState(
        battlefield_id=checkpoint.battlefield_id,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=current_battlefield.terrain_features,
        placed_armies=tuple(
            PlacedArmy(
                army_id=army_id,
                player_id=army_owner_by_id[army_id],
                unit_placements=tuple(unit_placements),
            )
            for army_id, unit_placements in sorted(placed_armies_by_id.items())
        ),
        removed_model_ids=tuple(
            row.model_instance_id for row in checkpoint.model_states if row.presence == "destroyed"
        ),
    )
    all_markers = tuple(marker.to_objective_marker() for marker in setup.objective_markers)
    ruleset = state.ruleset_descriptor_for_runtime_policy()
    objective_markers, terrain_objectives, terrain_areas = resolve_objective_control_sources(
        objective_markers=all_markers,
        terrain_features=frozen_battlefield.terrain_features,
        ruleset_descriptor=ruleset,
        explicit_terrain_objectives=(),
        objective_terrain_areas=setup.objective_terrain_areas,
    )
    linked_marker_ids = {definition.objective_marker_id for definition in terrain_areas}
    resolved = resolve_objective_control(
        ObjectiveControlContext(
            game_id=record.game_id,
            scenario=BattlefieldScenario(
                armies=frozen_armies,
                battlefield_state=frozen_battlefield,
            ),
            objective_markers=objective_markers,
            battle_shocked_unit_ids=checkpoint.battle_shocked_unit_instance_ids,
            timing=record.timing,
            phase=record.phase,
            battle_round=record.battle_round,
            active_player_id=record.active_player_id,
            ruleset_descriptor=ruleset,
            terrain_objectives=terrain_objectives,
            terrain_features=frozen_battlefield.terrain_features,
            objective_terrain_areas=terrain_areas,
            objective_terrain_area_markers=tuple(
                marker for marker in all_markers if marker.objective_marker_id in linked_marker_ids
            ),
            terrain_areas=setup.terrain_areas,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    return replace(resolved, record_id=record.record_id)


def _validate_checkpoint_model_identity(
    *,
    state: GameState,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    expected = {
        model.model_instance_id: (army.player_id, unit.unit_instance_id, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if set(expected) != {row.model_instance_id for row in checkpoint.model_states}:
        raise GameLifecycleError("ObjectiveControlRecord checkpoint model inventory drifted.")
    for row in checkpoint.model_states:
        owner_id, component_id, model = expected[row.model_instance_id]
        source = CharacteristicValue.from_payload(
            cast(
                CharacteristicValuePayload,
                _canonical_json_object(row.source_objective_control_json),
            )
        )
        source_from_model = next(
            (
                value
                for value in model.characteristics
                if value.characteristic is source.characteristic
            ),
            None,
        )
        if (row.owner_player_id, row.component_unit_instance_id) != (
            owner_id,
            component_id,
        ) or source_from_model != source:
            raise GameLifecycleError("ObjectiveControlRecord checkpoint model identity drifted.")


def _validate_sticky_state_provenance(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    values: tuple[StickyObjectiveControlState, ...],
    record_history: tuple[ObjectiveControlRecord, ...],
) -> None:
    known_unit_ids = {
        unit.unit_instance_id for army in state.army_definitions for unit in army.units
    }
    objective_ids = {result.objective_id for result in record.results}
    record_positions = {stored.record_id: index for index, stored in enumerate(record_history)}
    record_position = record_positions.get(record.record_id)
    for witness in values:
        if (
            witness.game_id != record.game_id
            or witness.player_id not in state.player_ids
            or witness.active_player_id not in state.player_ids
            or witness.objective_id not in objective_ids
            or witness.battle_round > record.battle_round
            or witness.originating_unit_instance_id not in known_unit_ids
            or witness.destroyed_unit_instance_id not in known_unit_ids
        ):
            raise GameLifecycleError(
                "ObjectiveControlRecord retained-control source provenance drifted."
            )
        if witness in state.sticky_objective_control_states:
            continue
        later_records = () if record_position is None else record_history[record_position + 1 :]
        if any(
            sticky_objective_control_state_is_expired(
                state=witness,
                record=later_record,
                player_ids=state.player_ids,
            )
            for later_record in later_records
        ):
            continue
        raise GameLifecycleError(
            "ObjectiveControlRecord retained-control source lacks state or expiry authority."
        )


def _validate_current_boundary_battle_shock(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
    record_history: tuple[ObjectiveControlRecord, ...],
) -> None:
    latest_record_id = record.record_id if not record_history else record_history[-1].record_id
    current_phase = state.current_battle_phase
    if (
        latest_record_id != record.record_id
        or state.battle_round != checkpoint.battle_round
        or state.active_player_id != checkpoint.active_player_id
        or current_phase is None
        or current_phase.value != checkpoint.phase
    ):
        return
    if set(checkpoint.battle_shocked_unit_instance_ids) != set(state.battle_shocked_unit_ids):
        raise GameLifecycleError(
            "ObjectiveControlRecord current-boundary Battle-shock authority drifted."
        )


def _relevant_sticky_state_witnesses(
    *,
    record: ObjectiveControlRecord,
    values: tuple[StickyObjectiveControlState, ...],
) -> tuple[StickyObjectiveControlState, ...]:
    witnesses = _sticky_state_witnesses(values)
    selected: list[StickyObjectiveControlState] = []
    for result in record.results:
        source_id = result.retained_control_source_id
        controller_id = result.controlled_by_player_id
        if source_id is None or controller_id is None:
            continue
        matches = tuple(
            state
            for state in witnesses
            if state.objective_id == result.objective_id and state.player_id == controller_id
        )
        if not matches or matches[-1].source_rule_id != source_id:
            raise GameLifecycleError(
                "ObjectiveControlRecord retained-control result lacks an exact sticky witness."
            )
        selected.append(matches[-1])
    return _sticky_state_witnesses(tuple(selected))


def _sticky_state_witnesses(
    values: object,
) -> tuple[StickyObjectiveControlState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ObjectiveControlRecord sticky witnesses must be a tuple.")
    witnesses: list[StickyObjectiveControlState] = []
    seen_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not StickyObjectiveControlState:
            raise GameLifecycleError(
                "ObjectiveControlRecord sticky witnesses must contain typed states."
            )
        if value.state_id in seen_ids:
            raise GameLifecycleError("ObjectiveControlRecord sticky witness is duplicated.")
        seen_ids.add(value.state_id)
        witnesses.append(value)
    return tuple(sorted(witnesses, key=lambda value: value.state_id))


def _canonical_json_object(value: str) -> dict[str, object]:
    try:
        decoded: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GameLifecycleError(
            "ObjectiveControlRecord characteristic evidence is invalid JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise GameLifecycleError(
            "ObjectiveControlRecord characteristic evidence must encode an object."
        )
    return cast(dict[str, object], decoded)


def _payload_object(payload: object) -> dict[str, JsonValue]:
    keys = {
        "schema_version",
        "objective_control_record_id",
        "objective_control_record_hash",
        "boundary_checkpoint",
        "retained_sticky_objective_control_states",
        "authority_id",
        "authority_hash",
    }
    if not isinstance(payload, dict):
        raise GameLifecycleError("ObjectiveControlRecord authority payload must be an object.")
    raw = cast(dict[object, object], payload)
    if any(type(key) is not str for key in raw) or set(raw) != keys:
        raise GameLifecycleError("ObjectiveControlRecord authority payload fields drifted.")
    return cast(dict[str, JsonValue], validate_json_value(raw))


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"ObjectiveControlRecord authority {key} must be a string.")
    return value


def _payload_list(payload: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"ObjectiveControlRecord authority {key} must be a list.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "OBJECTIVE_CONTROL_RECORD_AUTHORITY_SCHEMA",
    "ObjectiveControlRecordAuthority",
    "ObjectiveControlRecordAuthorityPayload",
    "capture_objective_control_record_authority",
    "objective_control_record_hash",
    "validate_objective_control_record_authorities",
    "validate_objective_control_record_authority",
    "validate_objective_control_record_authority_lifecycle_integrity",
)
