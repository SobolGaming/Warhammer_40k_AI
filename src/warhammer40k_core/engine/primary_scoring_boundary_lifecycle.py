from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.descriptor_hash import (
    canonical_payload_sha256,
    validate_sha256_hex,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundary_kinds,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringBoundaryKind
from warhammer40k_core.engine.scoring import VictoryPointSourceKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


PRIMARY_SCORING_BOUNDARY_LIFECYCLE_SCHEMA = "primary-scoring-boundary-lifecycle-v1"
_PRIMARY_SCORING_BOUNDARY_LIFECYCLE_ID_PREFIX = "primary-scoring-boundary-lifecycle"
_OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE = "end_boundary_objective_control_determined"

PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED = "phase_end_unit_destroyed_rule_required"
PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH = "return_on_death_placement_required"
PRIMARY_SCORING_PENDING_WINDOW_TURN_END_FACTION_RULE = "turn_end_faction_rule_required"
PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE = "primary_mission_turn_end_choice_required"
LEGAL_PRIMARY_SCORING_PENDING_WINDOWS = frozenset(
    {
        PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
        PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
        PRIMARY_SCORING_PENDING_WINDOW_TURN_END_FACTION_RULE,
        PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE,
    }
)


class PrimaryScoringBoundaryStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"


class PrimaryScoringBoundaryLifecyclePayload(TypedDict):
    schema_version: str
    objective_control_record_id: str
    objective_control_record_hash: str
    scoring_boundary_kind: str
    status: str
    pending_window: str | None
    pending_decision_request_id: str | None
    scoring_commit_checkpoint_id: str | None
    scoring_commit_checkpoint_hash: str | None
    evidence_id: str | None
    primary_transaction_ids: list[str]
    lifecycle_id: str
    lifecycle_hash: str


@dataclass(frozen=True, slots=True)
class PrimaryScoringBoundaryLifecycle:
    """Typed OC-capture → scoring-commit lifecycle for one required boundary."""

    schema_version: str
    objective_control_record_id: str
    objective_control_record_hash: str
    scoring_boundary_kind: PrimaryScoringBoundaryKind
    status: PrimaryScoringBoundaryStatus
    pending_window: str | None
    pending_decision_request_id: str | None
    scoring_commit_checkpoint_id: str | None
    scoring_commit_checkpoint_hash: str | None
    evidence_id: str | None
    primary_transaction_ids: tuple[str, ...]
    lifecycle_id: str
    lifecycle_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _identifier("PrimaryScoringBoundaryLifecycle schema_version", self.schema_version),
        )
        if self.schema_version != PRIMARY_SCORING_BOUNDARY_LIFECYCLE_SCHEMA:
            raise GameLifecycleError("Primary scoring boundary lifecycle schema is unsupported.")
        object.__setattr__(
            self,
            "objective_control_record_id",
            _identifier(
                "PrimaryScoringBoundaryLifecycle objective_control_record_id",
                self.objective_control_record_id,
            ),
        )
        object.__setattr__(
            self,
            "objective_control_record_hash",
            validate_sha256_hex(
                self.objective_control_record_hash,
                field_name="PrimaryScoringBoundaryLifecycle objective_control_record_hash",
                error_type=GameLifecycleError,
            ),
        )
        if type(self.scoring_boundary_kind) is not PrimaryScoringBoundaryKind:
            raise GameLifecycleError(
                "PrimaryScoringBoundaryLifecycle scoring_boundary_kind must be typed."
            )
        if type(self.status) is not PrimaryScoringBoundaryStatus:
            raise GameLifecycleError("PrimaryScoringBoundaryLifecycle status must be typed.")
        object.__setattr__(
            self,
            "pending_window",
            _optional_identifier(
                "PrimaryScoringBoundaryLifecycle pending_window",
                self.pending_window,
            ),
        )
        object.__setattr__(
            self,
            "pending_decision_request_id",
            _optional_identifier(
                "PrimaryScoringBoundaryLifecycle pending_decision_request_id",
                self.pending_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "scoring_commit_checkpoint_id",
            _optional_identifier(
                "PrimaryScoringBoundaryLifecycle scoring_commit_checkpoint_id",
                self.scoring_commit_checkpoint_id,
            ),
        )
        if self.scoring_commit_checkpoint_hash is not None:
            object.__setattr__(
                self,
                "scoring_commit_checkpoint_hash",
                validate_sha256_hex(
                    self.scoring_commit_checkpoint_hash,
                    field_name="PrimaryScoringBoundaryLifecycle scoring_commit_checkpoint_hash",
                    error_type=GameLifecycleError,
                ),
            )
        object.__setattr__(
            self,
            "evidence_id",
            _optional_identifier("PrimaryScoringBoundaryLifecycle evidence_id", self.evidence_id),
        )
        object.__setattr__(
            self,
            "primary_transaction_ids",
            _identifier_tuple(
                "PrimaryScoringBoundaryLifecycle primary_transaction_ids",
                self.primary_transaction_ids,
            ),
        )
        object.__setattr__(
            self,
            "lifecycle_hash",
            validate_sha256_hex(
                self.lifecycle_hash,
                field_name="PrimaryScoringBoundaryLifecycle lifecycle_hash",
                error_type=GameLifecycleError,
            ),
        )
        object.__setattr__(
            self,
            "lifecycle_id",
            _identifier("PrimaryScoringBoundaryLifecycle lifecycle_id", self.lifecycle_id),
        )
        expected_hash = canonical_payload_sha256(self._content_payload())
        if self.lifecycle_hash != expected_hash:
            raise GameLifecycleError("Primary scoring boundary lifecycle hash drifted.")
        if self.lifecycle_id != f"{_PRIMARY_SCORING_BOUNDARY_LIFECYCLE_ID_PREFIX}:{expected_hash}":
            raise GameLifecycleError("Primary scoring boundary lifecycle identity drifted.")
        self._validate_status_fields()

    def _validate_status_fields(self) -> None:
        if self.status is PrimaryScoringBoundaryStatus.PENDING:
            if (
                self.pending_window not in LEGAL_PRIMARY_SCORING_PENDING_WINDOWS
                or self.pending_decision_request_id is None
                or self.scoring_commit_checkpoint_id is not None
                or self.scoring_commit_checkpoint_hash is not None
                or self.evidence_id is not None
                or self.primary_transaction_ids
            ):
                raise GameLifecycleError(
                    "Pending Primary scoring boundary lifecycle fields are inconsistent."
                )
            return
        if (
            self.pending_window is not None
            or self.pending_decision_request_id is not None
            or self.scoring_commit_checkpoint_id is None
            or self.scoring_commit_checkpoint_hash is None
            or self.evidence_id is None
        ):
            raise GameLifecycleError(
                "Resolved Primary scoring boundary lifecycle fields are inconsistent."
            )

    @classmethod
    def pending(
        cls,
        *,
        record: ObjectiveControlRecord,
        scoring_boundary_kind: PrimaryScoringBoundaryKind,
        pending_window: str,
        pending_decision_request_id: str,
    ) -> Self:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "Pending Primary scoring boundary requires an ObjectiveControlRecord."
            )
        if type(scoring_boundary_kind) is not PrimaryScoringBoundaryKind:
            raise GameLifecycleError(
                "Pending Primary scoring boundary requires a typed boundary kind."
            )
        return cls.create(
            objective_control_record_id=record.record_id,
            objective_control_record_hash=_record_hash(record),
            scoring_boundary_kind=scoring_boundary_kind,
            status=PrimaryScoringBoundaryStatus.PENDING,
            pending_window=pending_window,
            pending_decision_request_id=pending_decision_request_id,
            scoring_commit_checkpoint_id=None,
            scoring_commit_checkpoint_hash=None,
            evidence_id=None,
            primary_transaction_ids=(),
        )

    @classmethod
    def resolved(
        cls,
        *,
        record: ObjectiveControlRecord,
        scoring_boundary_kind: PrimaryScoringBoundaryKind,
        scoring_commit_checkpoint_id: str,
        scoring_commit_checkpoint_hash: str,
        evidence_id: str,
        primary_transaction_ids: tuple[str, ...],
    ) -> Self:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "Resolved Primary scoring boundary requires an ObjectiveControlRecord."
            )
        if type(scoring_boundary_kind) is not PrimaryScoringBoundaryKind:
            raise GameLifecycleError(
                "Resolved Primary scoring boundary requires a typed boundary kind."
            )
        return cls.create(
            objective_control_record_id=record.record_id,
            objective_control_record_hash=_record_hash(record),
            scoring_boundary_kind=scoring_boundary_kind,
            status=PrimaryScoringBoundaryStatus.RESOLVED,
            pending_window=None,
            pending_decision_request_id=None,
            scoring_commit_checkpoint_id=scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=scoring_commit_checkpoint_hash,
            evidence_id=evidence_id,
            primary_transaction_ids=primary_transaction_ids,
        )

    @classmethod
    def create(
        cls,
        *,
        objective_control_record_id: str,
        objective_control_record_hash: str,
        scoring_boundary_kind: PrimaryScoringBoundaryKind,
        status: PrimaryScoringBoundaryStatus,
        pending_window: str | None,
        pending_decision_request_id: str | None,
        scoring_commit_checkpoint_id: str | None,
        scoring_commit_checkpoint_hash: str | None,
        evidence_id: str | None,
        primary_transaction_ids: tuple[str, ...],
    ) -> Self:
        content = _content_payload(
            schema_version=PRIMARY_SCORING_BOUNDARY_LIFECYCLE_SCHEMA,
            objective_control_record_id=objective_control_record_id,
            objective_control_record_hash=objective_control_record_hash,
            scoring_boundary_kind=scoring_boundary_kind,
            status=status,
            pending_window=pending_window,
            pending_decision_request_id=pending_decision_request_id,
            scoring_commit_checkpoint_id=scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=scoring_commit_checkpoint_hash,
            evidence_id=evidence_id,
            primary_transaction_ids=primary_transaction_ids,
        )
        digest = canonical_payload_sha256(content)
        return cls(
            schema_version=PRIMARY_SCORING_BOUNDARY_LIFECYCLE_SCHEMA,
            objective_control_record_id=objective_control_record_id,
            objective_control_record_hash=objective_control_record_hash,
            scoring_boundary_kind=scoring_boundary_kind,
            status=status,
            pending_window=pending_window,
            pending_decision_request_id=pending_decision_request_id,
            scoring_commit_checkpoint_id=scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=scoring_commit_checkpoint_hash,
            evidence_id=evidence_id,
            primary_transaction_ids=primary_transaction_ids,
            lifecycle_id=f"{_PRIMARY_SCORING_BOUNDARY_LIFECYCLE_ID_PREFIX}:{digest}",
            lifecycle_hash=digest,
        )

    def _content_payload(self) -> dict[str, object]:
        return _content_payload(
            schema_version=self.schema_version,
            objective_control_record_id=self.objective_control_record_id,
            objective_control_record_hash=self.objective_control_record_hash,
            scoring_boundary_kind=self.scoring_boundary_kind,
            status=self.status,
            pending_window=self.pending_window,
            pending_decision_request_id=self.pending_decision_request_id,
            scoring_commit_checkpoint_id=self.scoring_commit_checkpoint_id,
            scoring_commit_checkpoint_hash=self.scoring_commit_checkpoint_hash,
            evidence_id=self.evidence_id,
            primary_transaction_ids=self.primary_transaction_ids,
        )

    def to_payload(self) -> PrimaryScoringBoundaryLifecyclePayload:
        payload = {
            **self._content_payload(),
            "lifecycle_id": self.lifecycle_id,
            "lifecycle_hash": self.lifecycle_hash,
        }
        return cast(PrimaryScoringBoundaryLifecyclePayload, validate_json_value(payload))

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_object(payload)
        return cls(
            schema_version=cast(str, raw["schema_version"]),
            objective_control_record_id=cast(str, raw["objective_control_record_id"]),
            objective_control_record_hash=cast(str, raw["objective_control_record_hash"]),
            scoring_boundary_kind=_boundary_kind_from_token(raw["scoring_boundary_kind"]),
            status=_status_from_token(raw["status"]),
            pending_window=cast(str | None, raw["pending_window"]),
            pending_decision_request_id=cast(str | None, raw["pending_decision_request_id"]),
            scoring_commit_checkpoint_id=cast(str | None, raw["scoring_commit_checkpoint_id"]),
            scoring_commit_checkpoint_hash=cast(str | None, raw["scoring_commit_checkpoint_hash"]),
            evidence_id=cast(str | None, raw["evidence_id"]),
            primary_transaction_ids=tuple(
                cast(str, value) for value in cast(list[object], raw["primary_transaction_ids"])
            ),
            lifecycle_id=cast(str, raw["lifecycle_id"]),
            lifecycle_hash=cast(str, raw["lifecycle_hash"]),
        )


def mark_pending_primary_scoring_boundaries(
    *,
    state: GameState,
    pending_window: str,
    pending_decision_request_id: str,
) -> None:
    """Record every currently unscoreed required boundary as pending for one wait."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Pending Primary scoring boundaries require GameState.")
    if pending_window not in LEGAL_PRIMARY_SCORING_PENDING_WINDOWS:
        raise GameLifecycleError("Primary scoring pending window is not a legal lifecycle wait.")
    request_id = _identifier("pending_decision_request_id", pending_decision_request_id)
    required = _required_boundary_keys(state=state)
    evidenced = {
        (evidence.objective_control_record_id, evidence.scoring_boundary_kind)
        for evidence in state.primary_scoring_state_evidence_records
    }
    unresolved = required - evidenced
    resolved_rows = tuple(
        row
        for row in state.primary_scoring_boundary_lifecycles
        if row.status is PrimaryScoringBoundaryStatus.RESOLVED
    )
    resolved_keys = {
        (row.objective_control_record_id, row.scoring_boundary_kind) for row in resolved_rows
    }
    stale_pending = resolved_keys & unresolved
    if stale_pending:
        raise GameLifecycleError(
            "Primary scoring boundary remains unclosed after the lifecycle has advanced."
        )
    records_by_id = {record.record_id: record for record in state.objective_control_records}
    pending_rows = tuple(
        PrimaryScoringBoundaryLifecycle.pending(
            record=records_by_id[record_id],
            scoring_boundary_kind=kind,
            pending_window=pending_window,
            pending_decision_request_id=request_id,
        )
        for record_id, kind in sorted(
            unresolved,
            key=lambda item: (item[0], item[1].value),
        )
    )
    state.replace_primary_scoring_boundary_lifecycles(
        _sorted_lifecycles((*resolved_rows, *pending_rows))
    )
    validate_primary_scoring_boundary_lifecycles(state=state)


def resolve_primary_scoring_boundary_lifecycle(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    scoring_boundary_kind: PrimaryScoringBoundaryKind,
    scoring_commit_checkpoint_id: str,
    scoring_commit_checkpoint_hash: str,
    evidence_id: str,
) -> None:
    """Mark one required boundary resolved after evidence and transactions commit."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Resolved Primary scoring boundary requires GameState.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Resolved Primary scoring boundary requires an ObjectiveControlRecord."
        )
    if type(scoring_boundary_kind) is not PrimaryScoringBoundaryKind:
        raise GameLifecycleError("Resolved Primary scoring boundary requires a typed kind.")
    transaction_ids = _primary_transaction_ids_for_evidence(
        state=state,
        evidence_id=evidence_id,
    )
    resolved = PrimaryScoringBoundaryLifecycle.resolved(
        record=record,
        scoring_boundary_kind=scoring_boundary_kind,
        scoring_commit_checkpoint_id=scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=scoring_commit_checkpoint_hash,
        evidence_id=evidence_id,
        primary_transaction_ids=transaction_ids,
    )
    retained = tuple(
        row
        for row in state.primary_scoring_boundary_lifecycles
        if not (
            row.objective_control_record_id == record.record_id
            and row.scoring_boundary_kind is scoring_boundary_kind
        )
    )
    state.replace_primary_scoring_boundary_lifecycles(_sorted_lifecycles((*retained, resolved)))
    validate_primary_scoring_boundary_lifecycles(state=state)


def pending_primary_scoring_boundary_keys(
    *,
    state: GameState,
) -> frozenset[tuple[str, PrimaryScoringBoundaryKind]]:
    return frozenset(
        (row.objective_control_record_id, row.scoring_boundary_kind)
        for row in state.primary_scoring_boundary_lifecycles
        if row.status is PrimaryScoringBoundaryStatus.PENDING
    )


def validate_primary_scoring_boundary_lifecycles(*, state: GameState) -> None:
    """Require lifecycle rows to match OC inventory, evidence, and current battle context."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(
            "Primary scoring boundary lifecycle validation requires GameState."
        )
    rows = tuple(state.primary_scoring_boundary_lifecycles)
    if any(type(row) is not PrimaryScoringBoundaryLifecycle for row in rows):
        raise GameLifecycleError(
            "GameState primary_scoring_boundary_lifecycles must contain typed rows."
        )
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, PrimaryScoringBoundaryKind]] = set()
    pending_windows: set[str] = set()
    pending_request_ids: set[str] = set()
    records_by_id = {record.record_id: record for record in state.objective_control_records}
    evidence_by_key = {
        (evidence.objective_control_record_id, evidence.scoring_boundary_kind): evidence
        for evidence in state.primary_scoring_state_evidence_records
    }
    required = _required_boundary_keys(state=state)
    for row in rows:
        if row.lifecycle_id in seen_ids:
            raise GameLifecycleError("Primary scoring boundary lifecycle identity is duplicated.")
        key = (row.objective_control_record_id, row.scoring_boundary_kind)
        if key in seen_keys:
            raise GameLifecycleError("Primary scoring boundary lifecycle key is duplicated.")
        seen_ids.add(row.lifecycle_id)
        seen_keys.add(key)
        record = records_by_id.get(row.objective_control_record_id)
        if record is None:
            raise GameLifecycleError(
                "Primary scoring boundary lifecycle references a missing Objective Control record."
            )
        if _record_hash(record) != row.objective_control_record_hash:
            raise GameLifecycleError(
                "Primary scoring boundary lifecycle Objective Control hash drifted."
            )
        if key not in required:
            raise GameLifecycleError(
                "Primary scoring boundary lifecycle is not required for the stored record."
            )
        evidence = evidence_by_key.get(key)
        if row.status is PrimaryScoringBoundaryStatus.PENDING:
            if evidence is not None:
                raise GameLifecycleError(
                    "Pending Primary scoring boundary must not have committed evidence."
                )
            _validate_pending_matches_current_battle(state=state, record=record)
            if row.pending_window is not None:
                pending_windows.add(row.pending_window)
            if row.pending_decision_request_id is not None:
                pending_request_ids.add(row.pending_decision_request_id)
            continue
        if evidence is None:
            raise GameLifecycleError(
                "Resolved Primary scoring boundary requires committed evidence."
            )
        if (
            row.evidence_id != evidence.evidence_id
            or row.scoring_commit_checkpoint_id != evidence.scoring_commit_checkpoint_id
            or row.scoring_commit_checkpoint_hash != evidence.scoring_commit_checkpoint_hash
        ):
            raise GameLifecycleError(
                "Resolved Primary scoring boundary lifecycle drifted from committed evidence."
            )
        expected_transaction_ids = _primary_transaction_ids_for_evidence(
            state=state,
            evidence_id=evidence.evidence_id,
        )
        if row.primary_transaction_ids != expected_transaction_ids:
            raise GameLifecycleError(
                "Resolved Primary scoring boundary transactions drifted from the ledger."
            )
    if len(pending_windows) > 1 or len(pending_request_ids) > 1:
        raise GameLifecycleError(
            "Pending Primary scoring boundaries must share one lifecycle window and request."
        )
    pending_keys = set(pending_primary_scoring_boundary_keys(state=state))
    evidenced_keys = set(evidence_by_key)
    if pending_keys & evidenced_keys:
        raise GameLifecycleError("Pending Primary scoring boundary also has committed evidence.")
    if pending_keys and pending_keys | evidenced_keys != required:
        raise GameLifecycleError(
            "Primary scoring boundary lifecycle registry is incomplete or unexpected."
        )


def validate_pending_primary_scoring_boundary_restore_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Prove a pending scoreable boundary from queue head and append-only OC events."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Pending Primary scoring restore requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Pending Primary scoring restore requires typed event records.")
    if type(pending_decision_requests) is not tuple or any(
        type(request) is not DecisionRequest for request in pending_decision_requests
    ):
        raise GameLifecycleError(
            "Pending Primary scoring restore requires typed pending decision requests."
        )
    pending_rows = tuple(
        row
        for row in state.primary_scoring_boundary_lifecycles
        if row.status is PrimaryScoringBoundaryStatus.PENDING
    )
    if not pending_rows:
        if pending_primary_scoring_boundary_keys(state=state):
            raise GameLifecycleError("Pending Primary scoring boundary registry drifted.")
        return
    request_ids = {row.pending_decision_request_id for row in pending_rows}
    windows = {row.pending_window for row in pending_rows}
    if len(request_ids) != 1 or len(windows) != 1:
        raise GameLifecycleError(
            "Pending Primary scoring restore requires one window and request identity."
        )
    pending_request_id = next(iter(request_ids))
    if pending_request_id is None:
        raise GameLifecycleError("Pending Primary scoring restore requires a decision request.")
    if not pending_decision_requests:
        raise GameLifecycleError(
            "Pending Primary scoring boundary has no corresponding queue authority."
        )
    queue_head = pending_decision_requests[0]
    if queue_head.request_id != pending_request_id:
        raise GameLifecycleError(
            "Pending Primary scoring boundary request does not match the queue head."
        )
    record_ids = {row.objective_control_record_id for row in pending_rows}
    for record_id in record_ids:
        matches = tuple(
            event
            for event in event_records
            if event.event_type == _OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE
            and isinstance(event.payload, dict)
            and event.payload.get("record_ids") == [record_id]
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Pending Primary scoring boundary has no corresponding event authority."
            )
        payload = matches[0].payload
        if not isinstance(payload, dict):
            raise GameLifecycleError(
                "Pending Primary scoring Objective Control event payload is invalid."
            )
        record = next(
            stored for stored in state.objective_control_records if stored.record_id == record_id
        )
        if (
            payload.get("game_id") != record.game_id
            or payload.get("battle_round") != record.battle_round
            or payload.get("phase") != record.phase
        ):
            raise GameLifecycleError(
                "Pending Primary scoring Objective Control event context drifted."
            )


def _required_boundary_keys(
    *,
    state: GameState,
) -> set[tuple[str, PrimaryScoringBoundaryKind]]:
    if state.mission_setup is None:
        if state.objective_control_records or state.primary_scoring_boundary_lifecycles:
            raise GameLifecycleError(
                "Primary scoring boundary lifecycle requires MissionSetup when records exist."
            )
        return set()
    from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup

    policies = mission_scoring_policies_from_setup(state.mission_setup)
    return {
        (record.record_id, kind)
        for record in state.objective_control_records
        for kind in required_primary_scoring_boundary_kinds(
            policies=policies,
            record=record,
            turn_order=state.turn_order,
        )
    }


def _validate_pending_matches_current_battle(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
) -> None:
    current_phase = state.current_battle_phase
    if (
        state.active_player_id is None
        or current_phase is None
        or record.battle_round != state.battle_round
        or record.active_player_id != state.active_player_id
        or record.phase != current_phase.value
    ):
        raise GameLifecycleError(
            "Primary scoring boundary remains unclosed after the lifecycle has advanced."
        )


def _primary_transaction_ids_for_evidence(
    *,
    state: GameState,
    evidence_id: str,
) -> tuple[str, ...]:
    requested = _identifier("evidence_id", evidence_id)
    transaction_ids: list[str] = []
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if transaction.source_kind is not VictoryPointSourceKind.PRIMARY:
                continue
            if not isinstance(transaction.metadata, dict):
                raise GameLifecycleError("Primary VP transaction metadata must be an object.")
            if transaction.metadata.get("primary_scoring_state_evidence_id") != requested:
                continue
            transaction_ids.append(transaction.transaction_id)
    return tuple(sorted(transaction_ids))


def _sorted_lifecycles(
    rows: tuple[PrimaryScoringBoundaryLifecycle, ...],
) -> list[PrimaryScoringBoundaryLifecycle]:
    return sorted(
        rows,
        key=lambda row: (
            row.objective_control_record_id,
            row.scoring_boundary_kind.value,
            row.lifecycle_id,
        ),
    )


def _record_hash(record: ObjectiveControlRecord) -> str:
    from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
        objective_control_record_hash,
    )

    return objective_control_record_hash(record)


def _content_payload(
    *,
    schema_version: str,
    objective_control_record_id: str,
    objective_control_record_hash: str,
    scoring_boundary_kind: PrimaryScoringBoundaryKind,
    status: PrimaryScoringBoundaryStatus,
    pending_window: str | None,
    pending_decision_request_id: str | None,
    scoring_commit_checkpoint_id: str | None,
    scoring_commit_checkpoint_hash: str | None,
    evidence_id: str | None,
    primary_transaction_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "objective_control_record_id": objective_control_record_id,
        "objective_control_record_hash": objective_control_record_hash,
        "scoring_boundary_kind": scoring_boundary_kind.value,
        "status": status.value,
        "pending_window": pending_window,
        "pending_decision_request_id": pending_decision_request_id,
        "scoring_commit_checkpoint_id": scoring_commit_checkpoint_id,
        "scoring_commit_checkpoint_hash": scoring_commit_checkpoint_hash,
        "evidence_id": evidence_id,
        "primary_transaction_ids": list(primary_transaction_ids),
    }


def _payload_object(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Primary scoring boundary lifecycle payload must be an object.")
    raw = cast(dict[str, object], payload)
    expected = tuple(PrimaryScoringBoundaryLifecyclePayload.__annotations__)
    missing = [key for key in expected if key not in raw]
    if missing:
        raise GameLifecycleError(
            f"Primary scoring boundary lifecycle payload missing field: {missing[0]}."
        )
    unexpected = [key for key in raw if key not in expected]
    if unexpected:
        raise GameLifecycleError(
            "Primary scoring boundary lifecycle payload contains unexpected field: "
            f"{unexpected[0]}."
        )
    return raw


def _boundary_kind_from_token(value: object) -> PrimaryScoringBoundaryKind:
    if value == PrimaryScoringBoundaryKind.ORDINARY.value:
        return PrimaryScoringBoundaryKind.ORDINARY
    if value == PrimaryScoringBoundaryKind.END_OF_BATTLE.value:
        return PrimaryScoringBoundaryKind.END_OF_BATTLE
    raise GameLifecycleError("Primary scoring boundary lifecycle kind is invalid.")


def _status_from_token(value: object) -> PrimaryScoringBoundaryStatus:
    if value == PrimaryScoringBoundaryStatus.PENDING.value:
        return PrimaryScoringBoundaryStatus.PENDING
    if value == PrimaryScoringBoundaryStatus.RESOLVED.value:
        return PrimaryScoringBoundaryStatus.RESOLVED
    raise GameLifecycleError("Primary scoring boundary lifecycle status is invalid.")


def _optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _identifier(field_name, value)


def _identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(_identifier(field_name, value) for value in cast(tuple[object, ...], values))


_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "LEGAL_PRIMARY_SCORING_PENDING_WINDOWS",
    "PRIMARY_SCORING_BOUNDARY_LIFECYCLE_SCHEMA",
    "PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED",
    "PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE",
    "PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH",
    "PRIMARY_SCORING_PENDING_WINDOW_TURN_END_FACTION_RULE",
    "PrimaryScoringBoundaryLifecycle",
    "PrimaryScoringBoundaryLifecyclePayload",
    "PrimaryScoringBoundaryStatus",
    "mark_pending_primary_scoring_boundaries",
    "pending_primary_scoring_boundary_keys",
    "resolve_primary_scoring_boundary_lifecycle",
    "validate_pending_primary_scoring_boundary_restore_authority",
    "validate_primary_scoring_boundary_lifecycles",
)
