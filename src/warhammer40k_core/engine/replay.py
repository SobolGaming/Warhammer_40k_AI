from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.rng import RandomSource, RandomSourcePayload
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.event_log import (
    EventRecord,
    EventRecordPayload,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind

REPLAY_ARTIFACT_SCHEMA_VERSION = "replay-artifact-v1-phase18b"


class ReplayArtifactError(ValueError):
    """Raised when a replay artifact or replay runner contract is invalid."""


class ReplayRunStatus(StrEnum):
    REPRODUCED = "reproduced"
    DRIFTED = "drifted"


class ReplayDiagnosticCode(StrEnum):
    NO_PENDING_REQUEST = "no_pending_request"
    REQUEST_ID_DRIFT = "request_id_drift"
    DECISION_TYPE_DRIFT = "decision_type_drift"
    ACTOR_DRIFT = "actor_drift"
    REQUEST_PAYLOAD_HASH_DRIFT = "request_payload_hash_drift"
    LEGAL_OPTION_FINGERPRINT_DRIFT = "legal_option_fingerprint_drift"
    SUBMISSION_REJECTED = "submission_rejected"
    SUBMISSION_INVALID = "submission_invalid"
    SUBMISSION_UNSUPPORTED = "submission_unsupported"
    SUBMISSION_RECORD_DRIFT = "submission_record_drift"
    EVENT_COUNT_DRIFT = "event_count_drift"
    EVENT_LOG_HASH_DRIFT = "event_log_hash_drift"
    EVENT_STREAM_DRIFT = "event_stream_drift"
    PROJECTION_PROVIDER_MISSING = "projection_provider_missing"
    PROJECTION_SCHEMA_DRIFT = "projection_schema_drift"
    PROJECTION_HASH_DRIFT = "projection_hash_drift"


class ReplaySourceIdentityPayload(TypedDict):
    game_id: str
    game_config_hash: str
    ruleset_descriptor_hash: str
    catalog_id: str
    catalog_hash: str
    source_package_id: str
    source_ids: list[str]


class ReplayProjectionCheckpointPayload(TypedDict):
    checkpoint_id: str
    decision_record_index: int
    event_count: int
    event_log_hash: str
    viewer_player_id: str
    projection_schema: str
    projection_state_hash: str


class ReplayProjectionSnapshotPayload(TypedDict):
    viewer_player_id: str
    projection_schema: str
    projection_state_hash: str


class ReplayArtifactPayload(TypedDict):
    schema_version: str
    artifact_id: str
    source_identity: ReplaySourceIdentityPayload
    initial_rng_state: RandomSourcePayload
    initial_lifecycle: GameLifecyclePayload
    decision_records: list[DecisionRecordPayload]
    event_records: list[EventRecordPayload]
    projection_checkpoints: list[ReplayProjectionCheckpointPayload]


class ReplayDriftDiagnosticPayload(TypedDict):
    diagnostic_code: str
    message: str
    decision_record_index: int | None
    record_id: str | None
    checkpoint_id: str | None
    expected: JsonValue
    actual: JsonValue


class ReplayRunResultPayload(TypedDict):
    status: str
    artifact_id: str
    reproduced_decision_count: int
    reproduced_event_count: int
    final_event_log_hash: str
    diagnostics: list[ReplayDriftDiagnosticPayload]


type ReplayProjectionProvider = Callable[
    [GameLifecycle, "ReplayProjectionCheckpoint"], "ReplayProjectionSnapshot"
]


@dataclass(frozen=True, slots=True)
class ReplaySourceIdentity:
    game_id: str
    game_config_hash: str
    ruleset_descriptor_hash: str
    catalog_id: str
    catalog_hash: str
    source_package_id: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(
            self,
            "game_config_hash",
            _validate_sha256("game_config_hash", self.game_config_hash),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_sha256("ruleset_descriptor_hash", self.ruleset_descriptor_hash),
        )
        object.__setattr__(self, "catalog_id", _validate_identifier("catalog_id", self.catalog_id))
        object.__setattr__(
            self,
            "catalog_hash",
            _validate_sha256("catalog_hash", self.catalog_hash),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("source_package_id", self.source_package_id),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("source_ids", self.source_ids),
        )

    @classmethod
    def from_config(cls, config: GameConfig) -> Self:
        if type(config) is not GameConfig:
            raise ReplayArtifactError("Replay source identity requires a GameConfig.")
        catalog = config.army_catalog
        return cls(
            game_id=config.game_id,
            game_config_hash=_payload_hash(config.to_payload()),
            ruleset_descriptor_hash=config.ruleset_descriptor.descriptor_hash,
            catalog_id=catalog.catalog_id,
            catalog_hash=_payload_hash(catalog.to_payload()),
            source_package_id=catalog.source_package_id,
            source_ids=catalog.source_ids,
        )

    def to_payload(self) -> ReplaySourceIdentityPayload:
        return {
            "game_id": self.game_id,
            "game_config_hash": self.game_config_hash,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "catalog_id": self.catalog_id,
            "catalog_hash": self.catalog_hash,
            "source_package_id": self.source_package_id,
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: ReplaySourceIdentityPayload) -> Self:
        return cls(
            game_id=payload["game_id"],
            game_config_hash=payload["game_config_hash"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            catalog_id=payload["catalog_id"],
            catalog_hash=payload["catalog_hash"],
            source_package_id=payload["source_package_id"],
            source_ids=tuple(payload["source_ids"]),
        )


@dataclass(frozen=True, slots=True)
class ReplayProjectionSnapshot:
    viewer_player_id: str
    projection_schema: str
    projection_state_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "viewer_player_id",
            _validate_identifier("viewer_player_id", self.viewer_player_id),
        )
        object.__setattr__(
            self,
            "projection_schema",
            _validate_identifier("projection_schema", self.projection_schema),
        )
        object.__setattr__(
            self,
            "projection_state_hash",
            _validate_sha256("projection_state_hash", self.projection_state_hash),
        )

    def to_payload(self) -> ReplayProjectionSnapshotPayload:
        return {
            "viewer_player_id": self.viewer_player_id,
            "projection_schema": self.projection_schema,
            "projection_state_hash": self.projection_state_hash,
        }

    @classmethod
    def from_payload(cls, payload: ReplayProjectionSnapshotPayload) -> Self:
        return cls(
            viewer_player_id=payload["viewer_player_id"],
            projection_schema=payload["projection_schema"],
            projection_state_hash=payload["projection_state_hash"],
        )


@dataclass(frozen=True, slots=True)
class ReplayProjectionCheckpoint:
    checkpoint_id: str
    decision_record_index: int
    event_count: int
    event_log_hash: str
    viewer_player_id: str
    projection_schema: str
    projection_state_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "checkpoint_id",
            _validate_identifier("checkpoint_id", self.checkpoint_id),
        )
        object.__setattr__(
            self,
            "decision_record_index",
            _validate_non_negative_int("decision_record_index", self.decision_record_index),
        )
        object.__setattr__(
            self,
            "event_count",
            _validate_non_negative_int("event_count", self.event_count),
        )
        object.__setattr__(
            self,
            "event_log_hash",
            _validate_sha256("event_log_hash", self.event_log_hash),
        )
        object.__setattr__(
            self,
            "viewer_player_id",
            _validate_identifier("viewer_player_id", self.viewer_player_id),
        )
        object.__setattr__(
            self,
            "projection_schema",
            _validate_identifier("projection_schema", self.projection_schema),
        )
        object.__setattr__(
            self,
            "projection_state_hash",
            _validate_sha256("projection_state_hash", self.projection_state_hash),
        )

    @classmethod
    def from_lifecycle(
        cls,
        *,
        lifecycle: GameLifecycle,
        checkpoint_id: str,
        decision_record_index: int,
        viewer_player_id: str,
        projection_schema: str,
        projection_state_hash: str,
    ) -> Self:
        if type(lifecycle) is not GameLifecycle:
            raise ReplayArtifactError("Replay checkpoint requires a GameLifecycle.")
        return cls(
            checkpoint_id=checkpoint_id,
            decision_record_index=decision_record_index,
            event_count=len(lifecycle.decision_controller.event_log.records),
            event_log_hash=replay_event_log_hash(lifecycle),
            viewer_player_id=viewer_player_id,
            projection_schema=projection_schema,
            projection_state_hash=projection_state_hash,
        )

    def snapshot(self) -> ReplayProjectionSnapshot:
        return ReplayProjectionSnapshot(
            viewer_player_id=self.viewer_player_id,
            projection_schema=self.projection_schema,
            projection_state_hash=self.projection_state_hash,
        )

    def to_payload(self) -> ReplayProjectionCheckpointPayload:
        return {
            "checkpoint_id": self.checkpoint_id,
            "decision_record_index": self.decision_record_index,
            "event_count": self.event_count,
            "event_log_hash": self.event_log_hash,
            "viewer_player_id": self.viewer_player_id,
            "projection_schema": self.projection_schema,
            "projection_state_hash": self.projection_state_hash,
        }

    @classmethod
    def from_payload(cls, payload: ReplayProjectionCheckpointPayload) -> Self:
        return cls(
            checkpoint_id=payload["checkpoint_id"],
            decision_record_index=payload["decision_record_index"],
            event_count=payload["event_count"],
            event_log_hash=payload["event_log_hash"],
            viewer_player_id=payload["viewer_player_id"],
            projection_schema=payload["projection_schema"],
            projection_state_hash=payload["projection_state_hash"],
        )


@dataclass(frozen=True, slots=True)
class ReplayArtifact:
    artifact_id: str
    source_identity: ReplaySourceIdentity
    initial_rng_state: RandomSourcePayload
    initial_lifecycle_payload: GameLifecyclePayload
    decision_records: tuple[DecisionRecord, ...]
    event_records: tuple[EventRecord, ...]
    projection_checkpoints: tuple[ReplayProjectionCheckpoint, ...]
    schema_version: str = REPLAY_ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _validate_schema_version(self.schema_version),
        )
        object.__setattr__(
            self,
            "artifact_id",
            _validate_identifier("artifact_id", self.artifact_id),
        )
        if type(self.source_identity) is not ReplaySourceIdentity:
            raise ReplayArtifactError("ReplayArtifact source_identity is invalid.")
        initial_payload = _lifecycle_payload(self.initial_lifecycle_payload)
        initial_lifecycle = GameLifecycle.from_payload(initial_payload)
        if ReplaySourceIdentity.from_config(initial_lifecycle.config) != self.source_identity:
            raise ReplayArtifactError("ReplayArtifact source identity drifted from snapshot.")
        object.__setattr__(self, "initial_lifecycle_payload", initial_payload)

        rng_state = _rng_state_payload(self.initial_rng_state)
        RandomSource.from_payload(rng_state)
        if rng_state != _initial_rng_state_payload(initial_lifecycle):
            raise ReplayArtifactError("ReplayArtifact initial_rng_state drifted from snapshot.")
        object.__setattr__(self, "initial_rng_state", rng_state)

        records = _validate_decision_record_tuple(self.decision_records)
        events = _validate_event_record_tuple(self.event_records)
        checkpoints = _validate_projection_checkpoint_tuple(self.projection_checkpoints)
        _validate_tail_record_ids(
            initial_lifecycle=initial_lifecycle,
            decision_records=records,
            event_records=events,
        )
        _validate_checkpoints(
            checkpoints=checkpoints,
            decision_count=len(records),
            initial_event_count=len(initial_lifecycle.decision_controller.event_log.records),
        )
        object.__setattr__(self, "decision_records", records)
        object.__setattr__(self, "event_records", events)
        object.__setattr__(self, "projection_checkpoints", checkpoints)

    @classmethod
    def capture(
        cls,
        *,
        artifact_id: str,
        initial_lifecycle_payload: GameLifecyclePayload,
        final_lifecycle: GameLifecycle,
        projection_checkpoints: tuple[ReplayProjectionCheckpoint, ...] = (),
    ) -> Self:
        if type(final_lifecycle) is not GameLifecycle:
            raise ReplayArtifactError("ReplayArtifact capture requires a final GameLifecycle.")
        initial_payload = _lifecycle_payload(initial_lifecycle_payload)
        initial_lifecycle = GameLifecycle.from_payload(initial_payload)
        source_identity = ReplaySourceIdentity.from_config(initial_lifecycle.config)
        if ReplaySourceIdentity.from_config(final_lifecycle.config) != source_identity:
            raise ReplayArtifactError("ReplayArtifact final lifecycle source identity drifted.")
        initial_record_count = len(initial_lifecycle.decision_controller.records)
        initial_event_count = len(initial_lifecycle.decision_controller.event_log.records)
        final_records = final_lifecycle.decision_controller.records
        final_events = final_lifecycle.decision_controller.event_log.records
        if len(final_records) < initial_record_count:
            raise ReplayArtifactError("ReplayArtifact final record stream is shorter than start.")
        if len(final_events) < initial_event_count:
            raise ReplayArtifactError("ReplayArtifact final event stream is shorter than start.")
        return cls(
            artifact_id=artifact_id,
            source_identity=source_identity,
            initial_rng_state=_initial_rng_state_payload(initial_lifecycle),
            initial_lifecycle_payload=initial_payload,
            decision_records=tuple(final_records[initial_record_count:]),
            event_records=tuple(final_events[initial_event_count:]),
            projection_checkpoints=projection_checkpoints,
        )

    def to_payload(self) -> ReplayArtifactPayload:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "source_identity": self.source_identity.to_payload(),
            "initial_rng_state": self.initial_rng_state,
            "initial_lifecycle": self.initial_lifecycle_payload,
            "decision_records": [record.to_payload() for record in self.decision_records],
            "event_records": [record.to_payload() for record in self.event_records],
            "projection_checkpoints": [
                checkpoint.to_payload() for checkpoint in self.projection_checkpoints
            ],
        }

    @classmethod
    def from_payload(cls, payload: ReplayArtifactPayload) -> Self:
        return cls(
            schema_version=payload["schema_version"],
            artifact_id=payload["artifact_id"],
            source_identity=ReplaySourceIdentity.from_payload(payload["source_identity"]),
            initial_rng_state=payload["initial_rng_state"],
            initial_lifecycle_payload=payload["initial_lifecycle"],
            decision_records=tuple(
                DecisionRecord.from_payload(record_payload)
                for record_payload in payload["decision_records"]
            ),
            event_records=tuple(
                EventRecord.from_payload(event_payload)
                for event_payload in payload["event_records"]
            ),
            projection_checkpoints=tuple(
                ReplayProjectionCheckpoint.from_payload(checkpoint)
                for checkpoint in payload["projection_checkpoints"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplayDriftDiagnostic:
    diagnostic_code: ReplayDiagnosticCode
    message: str
    decision_record_index: int | None = None
    record_id: str | None = None
    checkpoint_id: str | None = None
    expected: JsonValue = None
    actual: JsonValue = None

    def __post_init__(self) -> None:
        if type(self.diagnostic_code) is not ReplayDiagnosticCode:
            raise ReplayArtifactError("Replay diagnostic code is invalid.")
        object.__setattr__(self, "message", _validate_identifier("message", self.message))
        object.__setattr__(
            self,
            "decision_record_index",
            _validate_optional_non_negative_int(
                "decision_record_index", self.decision_record_index
            ),
        )
        object.__setattr__(
            self,
            "record_id",
            _validate_optional_identifier("record_id", self.record_id),
        )
        object.__setattr__(
            self,
            "checkpoint_id",
            _validate_optional_identifier("checkpoint_id", self.checkpoint_id),
        )
        object.__setattr__(self, "expected", validate_json_value(self.expected))
        object.__setattr__(self, "actual", validate_json_value(self.actual))

    def to_payload(self) -> ReplayDriftDiagnosticPayload:
        return {
            "diagnostic_code": self.diagnostic_code.value,
            "message": self.message,
            "decision_record_index": self.decision_record_index,
            "record_id": self.record_id,
            "checkpoint_id": self.checkpoint_id,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(frozen=True, slots=True)
class ReplayRunResult:
    status: ReplayRunStatus
    artifact_id: str
    reproduced_decision_count: int
    reproduced_event_count: int
    final_event_log_hash: str
    diagnostics: tuple[ReplayDriftDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not ReplayRunStatus:
            raise ReplayArtifactError("Replay run status is invalid.")
        object.__setattr__(
            self,
            "artifact_id",
            _validate_identifier("artifact_id", self.artifact_id),
        )
        object.__setattr__(
            self,
            "reproduced_decision_count",
            _validate_non_negative_int("reproduced_decision_count", self.reproduced_decision_count),
        )
        object.__setattr__(
            self,
            "reproduced_event_count",
            _validate_non_negative_int("reproduced_event_count", self.reproduced_event_count),
        )
        object.__setattr__(
            self,
            "final_event_log_hash",
            _validate_sha256("final_event_log_hash", self.final_event_log_hash),
        )
        object.__setattr__(
            self,
            "diagnostics",
            _validate_diagnostic_tuple(self.diagnostics),
        )
        if self.status is ReplayRunStatus.REPRODUCED and self.diagnostics:
            raise ReplayArtifactError("Reproduced replay result must not include diagnostics.")
        if self.status is ReplayRunStatus.DRIFTED and not self.diagnostics:
            raise ReplayArtifactError("Drifted replay result requires diagnostics.")

    @property
    def reproduced_exactly(self) -> bool:
        return self.status is ReplayRunStatus.REPRODUCED

    def to_payload(self) -> ReplayRunResultPayload:
        return {
            "status": self.status.value,
            "artifact_id": self.artifact_id,
            "reproduced_decision_count": self.reproduced_decision_count,
            "reproduced_event_count": self.reproduced_event_count,
            "final_event_log_hash": self.final_event_log_hash,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ReplayRunner:
    artifact: ReplayArtifact
    projection_provider: ReplayProjectionProvider | None = None

    def __post_init__(self) -> None:
        if type(self.artifact) is not ReplayArtifact:
            raise ReplayArtifactError("ReplayRunner artifact is invalid.")

    @classmethod
    def from_payload(
        cls,
        payload: ReplayArtifactPayload,
        *,
        projection_provider: ReplayProjectionProvider | None = None,
    ) -> Self:
        return cls(
            artifact=ReplayArtifact.from_payload(payload),
            projection_provider=projection_provider,
        )

    def run(self) -> ReplayRunResult:
        lifecycle = GameLifecycle.from_payload(self.artifact.initial_lifecycle_payload)
        initial_event_count = len(lifecycle.decision_controller.event_log.records)
        initial_record_count = len(lifecycle.decision_controller.records)
        checkpoint_diagnostic = self._checkpoint_diagnostic(
            lifecycle=lifecycle,
            decision_record_index=0,
        )
        if checkpoint_diagnostic is not None:
            return self._drifted_result(
                lifecycle=lifecycle,
                reproduced_decision_count=0,
                diagnostics=(checkpoint_diagnostic,),
            )

        for decision_record_index, expected_record in enumerate(
            self.artifact.decision_records,
            start=1,
        ):
            request_diagnostic = _request_drift_diagnostic(
                lifecycle=lifecycle,
                expected_record=expected_record,
                decision_record_index=decision_record_index,
            )
            if request_diagnostic is not None:
                return self._drifted_result(
                    lifecycle=lifecycle,
                    reproduced_decision_count=decision_record_index - 1,
                    diagnostics=(request_diagnostic,),
                )
            submission_diagnostic = self._submit_record_or_diagnostic(
                lifecycle=lifecycle,
                expected_record=expected_record,
                decision_record_index=decision_record_index,
                expected_record_count=initial_record_count + decision_record_index,
            )
            if submission_diagnostic is not None:
                return self._drifted_result(
                    lifecycle=lifecycle,
                    reproduced_decision_count=decision_record_index - 1,
                    diagnostics=(submission_diagnostic,),
                )
            checkpoint_diagnostic = self._checkpoint_diagnostic(
                lifecycle=lifecycle,
                decision_record_index=decision_record_index,
            )
            if checkpoint_diagnostic is not None:
                return self._drifted_result(
                    lifecycle=lifecycle,
                    reproduced_decision_count=decision_record_index,
                    diagnostics=(checkpoint_diagnostic,),
                )

        expected_tail = [record.to_payload() for record in self.artifact.event_records]
        actual_tail = [
            record.to_payload()
            for record in lifecycle.decision_controller.event_log.records[initial_event_count:]
        ]
        if _payload_hash(expected_tail) != _payload_hash(actual_tail):
            diagnostic = ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.EVENT_STREAM_DRIFT,
                message="Replay event stream drifted from artifact tail.",
                decision_record_index=len(self.artifact.decision_records),
                expected={"event_stream_hash": _payload_hash(expected_tail)},
                actual={"event_stream_hash": _payload_hash(actual_tail)},
            )
            return self._drifted_result(
                lifecycle=lifecycle,
                reproduced_decision_count=len(self.artifact.decision_records),
                diagnostics=(diagnostic,),
            )
        return ReplayRunResult(
            status=ReplayRunStatus.REPRODUCED,
            artifact_id=self.artifact.artifact_id,
            reproduced_decision_count=len(self.artifact.decision_records),
            reproduced_event_count=len(lifecycle.decision_controller.event_log.records),
            final_event_log_hash=replay_event_log_hash(lifecycle),
        )

    def _submit_record_or_diagnostic(
        self,
        *,
        lifecycle: GameLifecycle,
        expected_record: DecisionRecord,
        decision_record_index: int,
        expected_record_count: int,
    ) -> ReplayDriftDiagnostic | None:
        try:
            status = lifecycle.submit_decision(expected_record.result)
        except DecisionError as exc:
            return ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.SUBMISSION_REJECTED,
                message="Replay decision submission was rejected by the decision controller.",
                decision_record_index=decision_record_index,
                record_id=expected_record.record_id,
                expected=_json_payload(expected_record.to_payload()),
                actual={"error": str(exc)},
            )
        except GameLifecycleError as exc:
            return ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.SUBMISSION_REJECTED,
                message="Replay decision submission was rejected by the lifecycle.",
                decision_record_index=decision_record_index,
                record_id=expected_record.record_id,
                expected=_json_payload(expected_record.to_payload()),
                actual={"error": str(exc)},
            )
        if status.status_kind is LifecycleStatusKind.INVALID:
            return ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.SUBMISSION_INVALID,
                message="Replay decision submission returned an invalid lifecycle status.",
                decision_record_index=decision_record_index,
                record_id=expected_record.record_id,
                expected=_json_payload(expected_record.to_payload()),
                actual=status_payload(status),
            )
        if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
            return ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.SUBMISSION_UNSUPPORTED,
                message="Replay decision submission returned an unsupported lifecycle status.",
                decision_record_index=decision_record_index,
                record_id=expected_record.record_id,
                expected=_json_payload(expected_record.to_payload()),
                actual=status_payload(status),
            )
        records = lifecycle.decision_controller.records
        if len(records) != expected_record_count:
            return ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.SUBMISSION_RECORD_DRIFT,
                message="Replay decision did not produce the expected record count.",
                decision_record_index=decision_record_index,
                record_id=expected_record.record_id,
                expected={"record_count": expected_record_count},
                actual={"record_count": len(records)},
            )
        actual_record = records[-1]
        if actual_record.to_payload() != expected_record.to_payload():
            return ReplayDriftDiagnostic(
                diagnostic_code=ReplayDiagnosticCode.SUBMISSION_RECORD_DRIFT,
                message="Replay decision record payload drifted.",
                decision_record_index=decision_record_index,
                record_id=expected_record.record_id,
                expected=_json_payload(expected_record.to_payload()),
                actual=_json_payload(actual_record.to_payload()),
            )
        return None

    def _checkpoint_diagnostic(
        self,
        *,
        lifecycle: GameLifecycle,
        decision_record_index: int,
    ) -> ReplayDriftDiagnostic | None:
        for checkpoint in self.artifact.projection_checkpoints:
            if checkpoint.decision_record_index != decision_record_index:
                continue
            actual_event_count = len(lifecycle.decision_controller.event_log.records)
            if actual_event_count != checkpoint.event_count:
                return ReplayDriftDiagnostic(
                    diagnostic_code=ReplayDiagnosticCode.EVENT_COUNT_DRIFT,
                    message="Replay checkpoint event count drifted.",
                    decision_record_index=decision_record_index,
                    checkpoint_id=checkpoint.checkpoint_id,
                    expected={"event_count": checkpoint.event_count},
                    actual={"event_count": actual_event_count},
                )
            actual_event_log_hash = replay_event_log_hash(lifecycle)
            if actual_event_log_hash != checkpoint.event_log_hash:
                return ReplayDriftDiagnostic(
                    diagnostic_code=ReplayDiagnosticCode.EVENT_LOG_HASH_DRIFT,
                    message="Replay checkpoint event log hash drifted.",
                    decision_record_index=decision_record_index,
                    checkpoint_id=checkpoint.checkpoint_id,
                    expected={"event_log_hash": checkpoint.event_log_hash},
                    actual={"event_log_hash": actual_event_log_hash},
                )
            if self.projection_provider is None:
                return ReplayDriftDiagnostic(
                    diagnostic_code=ReplayDiagnosticCode.PROJECTION_PROVIDER_MISSING,
                    message="Replay checkpoint requires a projection provider.",
                    decision_record_index=decision_record_index,
                    checkpoint_id=checkpoint.checkpoint_id,
                    expected=_json_payload(checkpoint.snapshot().to_payload()),
                    actual=None,
                )
            actual_projection = self.projection_provider(lifecycle, checkpoint)
            if actual_projection.viewer_player_id != checkpoint.viewer_player_id:
                return ReplayDriftDiagnostic(
                    diagnostic_code=ReplayDiagnosticCode.PROJECTION_HASH_DRIFT,
                    message="Replay checkpoint projection viewer drifted.",
                    decision_record_index=decision_record_index,
                    checkpoint_id=checkpoint.checkpoint_id,
                    expected=_json_payload(checkpoint.snapshot().to_payload()),
                    actual=_json_payload(actual_projection.to_payload()),
                )
            if actual_projection.projection_schema != checkpoint.projection_schema:
                return ReplayDriftDiagnostic(
                    diagnostic_code=ReplayDiagnosticCode.PROJECTION_SCHEMA_DRIFT,
                    message="Replay checkpoint projection schema drifted.",
                    decision_record_index=decision_record_index,
                    checkpoint_id=checkpoint.checkpoint_id,
                    expected=_json_payload(checkpoint.snapshot().to_payload()),
                    actual=_json_payload(actual_projection.to_payload()),
                )
            if actual_projection.projection_state_hash != checkpoint.projection_state_hash:
                return ReplayDriftDiagnostic(
                    diagnostic_code=ReplayDiagnosticCode.PROJECTION_HASH_DRIFT,
                    message="Replay checkpoint projection hash drifted.",
                    decision_record_index=decision_record_index,
                    checkpoint_id=checkpoint.checkpoint_id,
                    expected=_json_payload(checkpoint.snapshot().to_payload()),
                    actual=_json_payload(actual_projection.to_payload()),
                )
        return None

    def _drifted_result(
        self,
        *,
        lifecycle: GameLifecycle,
        reproduced_decision_count: int,
        diagnostics: tuple[ReplayDriftDiagnostic, ...],
    ) -> ReplayRunResult:
        return ReplayRunResult(
            status=ReplayRunStatus.DRIFTED,
            artifact_id=self.artifact.artifact_id,
            reproduced_decision_count=reproduced_decision_count,
            reproduced_event_count=len(lifecycle.decision_controller.event_log.records),
            final_event_log_hash=replay_event_log_hash(lifecycle),
            diagnostics=diagnostics,
        )


class ReplayTraceExporter:
    def human_readable_timeline(self, artifact: ReplayArtifact) -> str:
        if type(artifact) is not ReplayArtifact:
            raise ReplayArtifactError("Replay trace export requires a ReplayArtifact.")
        lines = [
            f"ReplayArtifact {artifact.artifact_id}",
            (
                "Source "
                f"game={artifact.source_identity.game_id} "
                f"catalog={artifact.source_identity.catalog_id} "
                f"source_package={artifact.source_identity.source_package_id}"
            ),
        ]
        for index, record in enumerate(artifact.decision_records, start=1):
            lines.append(
                "Decision "
                f"{index} {record.record_id} "
                f"request={record.request.request_id} "
                f"type={record.request.decision_type} "
                f"actor={record.request.actor_id} "
                f"selected={record.result.selected_option_id} "
                f"payload_hash={decision_request_payload_hash(record.request)} "
                f"options={decision_request_options_fingerprint(record.request)}"
            )
        for event in artifact.event_records:
            lines.append(
                "Event "
                f"{event.event_id} "
                f"type={event.event_type} "
                f"payload_hash={_payload_hash(event.payload)}"
            )
        return "\n".join(lines)

    def decision_records_jsonl(self, artifact: ReplayArtifact) -> str:
        if type(artifact) is not ReplayArtifact:
            raise ReplayArtifactError("Replay DecisionRecord export requires a ReplayArtifact.")
        lines = [canonical_json(record.to_payload()) for record in artifact.decision_records]
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    def failure_triage_payload(
        self,
        *,
        artifact: ReplayArtifact,
        result: ReplayRunResult,
    ) -> JsonValue:
        if type(artifact) is not ReplayArtifact:
            raise ReplayArtifactError("Replay failure triage requires a ReplayArtifact.")
        if type(result) is not ReplayRunResult:
            raise ReplayArtifactError("Replay failure triage requires a ReplayRunResult.")
        return validate_json_value(
            {
                "schema_version": artifact.schema_version,
                "artifact_id": artifact.artifact_id,
                "source_identity": artifact.source_identity.to_payload(),
                "initial_rng_state": artifact.initial_rng_state,
                "decision_record_count": len(artifact.decision_records),
                "event_record_count": len(artifact.event_records),
                "expected_event_stream_hash": _payload_hash(
                    [record.to_payload() for record in artifact.event_records]
                ),
                "run_result": result.to_payload(),
            }
        )


def replay_event_log_hash(lifecycle: GameLifecycle) -> str:
    if type(lifecycle) is not GameLifecycle:
        raise ReplayArtifactError("Replay event log hash requires a GameLifecycle.")
    return _payload_hash(lifecycle.decision_controller.event_log.to_payload())


def decision_request_payload_hash(request: DecisionRequest) -> str:
    if type(request) is not DecisionRequest:
        raise ReplayArtifactError("Decision request payload hash requires a DecisionRequest.")
    return _payload_hash(request.payload)


def decision_request_options_fingerprint(request: DecisionRequest) -> str:
    if type(request) is not DecisionRequest:
        raise ReplayArtifactError(
            "Decision request options fingerprint requires a DecisionRequest."
        )
    return _payload_hash([option.to_payload() for option in request.options])


def status_payload(status: LifecycleStatus) -> JsonValue:
    if type(status) is not LifecycleStatus:
        raise ReplayArtifactError("Lifecycle status payload requires a LifecycleStatus.")
    payload: dict[str, JsonValue] = {}
    payload["status_kind"] = status.status_kind.value
    payload["message"] = (
        None if status.message is None else _validate_identifier("message", status.message)
    )
    payload["payload"] = validate_json_value(status.payload)
    return payload


def _request_drift_diagnostic(
    *,
    lifecycle: GameLifecycle,
    expected_record: DecisionRecord,
    decision_record_index: int,
) -> ReplayDriftDiagnostic | None:
    pending_requests = lifecycle.decision_controller.queue.pending_requests
    if not pending_requests:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.NO_PENDING_REQUEST,
            message="Replay expected a pending DecisionRequest.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected=_json_payload(expected_record.request.to_payload()),
            actual=None,
        )
    actual_request = pending_requests[0]
    expected_request = expected_record.request
    if actual_request.request_id != expected_request.request_id:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.REQUEST_ID_DRIFT,
            message="Replayed DecisionRequest ID drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"request_id": expected_request.request_id},
            actual={"request_id": actual_request.request_id},
        )
    if actual_request.decision_type != expected_request.decision_type:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.DECISION_TYPE_DRIFT,
            message="Replayed DecisionRequest type drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"decision_type": expected_request.decision_type},
            actual={"decision_type": actual_request.decision_type},
        )
    if actual_request.actor_id != expected_request.actor_id:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.ACTOR_DRIFT,
            message="Replayed DecisionRequest actor drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"actor_id": expected_request.actor_id},
            actual={"actor_id": actual_request.actor_id},
        )
    expected_payload_hash = decision_request_payload_hash(expected_request)
    actual_payload_hash = decision_request_payload_hash(actual_request)
    if actual_payload_hash != expected_payload_hash:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.REQUEST_PAYLOAD_HASH_DRIFT,
            message="Replayed DecisionRequest payload hash drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"payload_hash": expected_payload_hash},
            actual={"payload_hash": actual_payload_hash},
        )
    expected_option_hash = decision_request_options_fingerprint(expected_request)
    actual_option_hash = decision_request_options_fingerprint(actual_request)
    if actual_option_hash != expected_option_hash:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.LEGAL_OPTION_FINGERPRINT_DRIFT,
            message="Replayed legal option fingerprint drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"legal_option_fingerprint": expected_option_hash},
            actual={"legal_option_fingerprint": actual_option_hash},
        )
    return None


def _validate_schema_version(value: object) -> str:
    schema = _validate_identifier("schema_version", value)
    if schema != REPLAY_ARTIFACT_SCHEMA_VERSION:
        raise ReplayArtifactError("ReplayArtifact schema_version is unsupported.")
    return schema


def _lifecycle_payload(payload: GameLifecyclePayload) -> GameLifecyclePayload:
    return cast(GameLifecyclePayload, validate_json_value(payload))


def _rng_state_payload(payload: RandomSourcePayload) -> RandomSourcePayload:
    return cast(RandomSourcePayload, validate_json_value(payload))


def _initial_rng_state_payload(lifecycle: GameLifecycle) -> RandomSourcePayload:
    state = lifecycle.state
    if state is None:
        raise ReplayArtifactError("ReplayArtifact initial RNG state requires a started game.")
    manager = DiceRollManager(state.game_id, event_log=lifecycle.decision_controller.event_log)
    return manager.rng.to_payload()


def _validate_decision_record_tuple(
    records: object,
) -> tuple[DecisionRecord, ...]:
    if type(records) is not tuple:
        raise ReplayArtifactError("ReplayArtifact decision_records must be a tuple.")
    validated: list[DecisionRecord] = []
    for record in cast(tuple[object, ...], records):
        if type(record) is not DecisionRecord:
            raise ReplayArtifactError("ReplayArtifact decision_records contain invalid values.")
        validated.append(record)
    return tuple(validated)


def _validate_event_record_tuple(records: object) -> tuple[EventRecord, ...]:
    if type(records) is not tuple:
        raise ReplayArtifactError("ReplayArtifact event_records must be a tuple.")
    validated: list[EventRecord] = []
    for record in cast(tuple[object, ...], records):
        if type(record) is not EventRecord:
            raise ReplayArtifactError("ReplayArtifact event_records contain invalid values.")
        validated.append(record)
    return tuple(validated)


def _validate_projection_checkpoint_tuple(
    checkpoints: object,
) -> tuple[ReplayProjectionCheckpoint, ...]:
    if type(checkpoints) is not tuple:
        raise ReplayArtifactError("ReplayArtifact projection_checkpoints must be a tuple.")
    validated: list[ReplayProjectionCheckpoint] = []
    seen_ids: set[str] = set()
    for checkpoint in cast(tuple[object, ...], checkpoints):
        if type(checkpoint) is not ReplayProjectionCheckpoint:
            raise ReplayArtifactError(
                "ReplayArtifact projection_checkpoints contain invalid values."
            )
        if checkpoint.checkpoint_id in seen_ids:
            raise ReplayArtifactError("ReplayArtifact projection checkpoint IDs must be unique.")
        seen_ids.add(checkpoint.checkpoint_id)
        validated.append(checkpoint)
    return tuple(
        sorted(
            validated,
            key=lambda item: (item.decision_record_index, item.checkpoint_id),
        )
    )


def _validate_tail_record_ids(
    *,
    initial_lifecycle: GameLifecycle,
    decision_records: tuple[DecisionRecord, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    initial_record_count = len(initial_lifecycle.decision_controller.records)
    for offset, record in enumerate(decision_records, start=initial_record_count + 1):
        if record.record_id != f"decision-record-{offset:06d}":
            raise ReplayArtifactError("ReplayArtifact decision record IDs are not sequential.")
    initial_event_count = len(initial_lifecycle.decision_controller.event_log.records)
    for offset, event_record in enumerate(event_records, start=initial_event_count + 1):
        if event_record.event_id != f"event-{offset:06d}":
            raise ReplayArtifactError("ReplayArtifact event record IDs are not sequential.")


def _validate_checkpoints(
    *,
    checkpoints: tuple[ReplayProjectionCheckpoint, ...],
    decision_count: int,
    initial_event_count: int,
) -> None:
    for checkpoint in checkpoints:
        if checkpoint.decision_record_index > decision_count:
            raise ReplayArtifactError("ReplayArtifact checkpoint decision index is out of range.")
        if checkpoint.event_count < initial_event_count:
            raise ReplayArtifactError("ReplayArtifact checkpoint event count predates snapshot.")


def _validate_diagnostic_tuple(
    diagnostics: object,
) -> tuple[ReplayDriftDiagnostic, ...]:
    if type(diagnostics) is not tuple:
        raise ReplayArtifactError("ReplayRunResult diagnostics must be a tuple.")
    validated: list[ReplayDriftDiagnostic] = []
    for diagnostic in cast(tuple[object, ...], diagnostics):
        if type(diagnostic) is not ReplayDriftDiagnostic:
            raise ReplayArtifactError("ReplayRunResult diagnostics contain invalid values.")
        validated.append(diagnostic)
    return tuple(validated)


def _payload_hash(payload: object) -> str:
    encoded = canonical_json(validate_json_value(payload)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_payload(payload: object) -> JsonValue:
    return validate_json_value(payload)


_validate_identifier = IdentifierValidator(ReplayArtifactError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ReplayArtifactError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ReplayArtifactError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ReplayArtifactError(f"{field_name} must be an integer.")
    if value < 0:
        raise ReplayArtifactError(f"{field_name} must not be negative.")
    return value


def _validate_optional_non_negative_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_non_negative_int(field_name, value)


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise ReplayArtifactError(f"{field_name} must be a SHA-256 digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ReplayArtifactError(f"{field_name} must be a lowercase SHA-256 digest.")
    return digest
