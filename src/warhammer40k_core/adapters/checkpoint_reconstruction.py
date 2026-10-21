"""Explicit, operator-only reconstruction of one authenticated legacy checkpoint.

Normal persistence and replay loaders remain strict. This recipe regenerates
new evidence through recorded submissions; it never edits the original stream.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.model_attack_completion import MODEL_COMPLETION_STATE_EVENT
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayArtifactError,
    ReplayArtifactPayload,
    ReplayRunner,
    ReplayRunStatus,
)

PROFILE_ID = "local-checkpoint:legacy-model-completion:2026-10-14"
RECOVERY_SCHEMA = "local-checkpoint-reconstruction-v1"
SOURCE_SHA256 = "55f23684cedb354050605bb796928bea5971acb73d975ffe54ce230ae2db9370"
_SOURCE_BUILD = (
    "warhammer40k-core-v2:runtime-tree-sha256-v1:"
    "3dac52df9bba355343defa9547c58e6b1feb03f8b45e5d6d32031e611075d9bb"
)
_SOURCE_COMMIT = "22a12094cfe3839d8fe8c5296ec0a7e7d32abade"
_AUDIT_PATHS = (
    ("runtime_content_audit",),
    ("psychic_modifier_history_origin", "runtime_content_audit"),
)


class CheckpointReconstructionError(GameLifecycleError):
    """The selected reconstruction is unsupported, inconsistent or incomplete."""


def reconstruct_local_checkpoint(source_bytes: bytes, *, profile_id: str) -> dict[str, JsonValue]:
    """Produce a separate, deterministic checkpoint and explicit provenance.

    This deliberately admits only the retained source digest. Supporting another
    artifact/version requires a separately reviewed recipe, never an inferred
    fallback from a failed ordinary restore.
    """
    if profile_id != PROFILE_ID:
        raise CheckpointReconstructionError("Unsupported checkpoint reconstruction profile.")
    original = _source_payload(source_bytes)
    artifact = ReplayArtifact.from_payload(cast(ReplayArtifactPayload, original["replay_artifact"]))
    try:
        lifecycle = GameLifecycle.from_payload(artifact.initial_lifecycle_payload)
        session = LocalGameSession(lifecycle=lifecycle)
        session.advance_until_decision_or_terminal()
        for index, record in enumerate(artifact.decision_records):
            if len(lifecycle.decision_controller.records) <= index:
                status = session.advance_until_decision_or_terminal()
                if len(lifecycle.decision_controller.records) <= index:
                    if status.decision_request != record.request:
                        raise CheckpointReconstructionError(
                            "Historical decision request does not reproduce exactly."
                        )
                    status = submit_replay_record(session=session, record=record)
                    if status.status_kind in {
                        LifecycleStatusKind.INVALID,
                        LifecycleStatusKind.UNSUPPORTED,
                    }:
                        raise CheckpointReconstructionError(
                            "Historical decision cannot be reconstructed."
                        )
            if lifecycle.decision_controller.records[index] != record:
                raise CheckpointReconstructionError(
                    "Historical automatic decision does not reproduce exactly."
                )
        checkpoint = _object(session.to_persistence_payload())
    except (DecisionError, GameLifecycleError) as exc:
        raise CheckpointReconstructionError(
            "Recorded checkpoint reconstruction failed through the engine."
        ) from exc
    provenance = _validate_mapping(original, checkpoint)
    package: dict[str, JsonValue] = {
        "schema_version": RECOVERY_SCHEMA,
        "profile_id": PROFILE_ID,
        "checkpoint": checkpoint,
        "provenance": provenance,
    }
    package["content_hash"] = _hash(package)
    verify_checkpoint_reconstruction(source_bytes, package)
    return copy.deepcopy(package)


def verify_checkpoint_reconstruction(source_bytes: bytes, package: JsonValue) -> LocalGameSession:
    """Verify the original mapping, then use ordinary strict restore and replay."""
    original = _source_payload(source_bytes)
    value = _object(package)
    if set(value) != {"schema_version", "profile_id", "checkpoint", "provenance", "content_hash"}:
        raise CheckpointReconstructionError("Checkpoint reconstruction fields are invalid.")
    if value["schema_version"] != RECOVERY_SCHEMA or value["profile_id"] != PROFILE_ID:
        raise CheckpointReconstructionError("Checkpoint reconstruction profile drifted.")
    if value["content_hash"] != _hash({k: v for k, v in value.items() if k != "content_hash"}):
        raise CheckpointReconstructionError("Checkpoint reconstruction content hash drifted.")
    checkpoint = _object(value["checkpoint"])
    try:
        expected_provenance = _validate_mapping(original, checkpoint)
    except KeyError as exc:
        raise CheckpointReconstructionError(
            "Reconstructed checkpoint evidence is incomplete."
        ) from exc
    if canonical_json(value["provenance"]) != canonical_json(expected_provenance):
        raise CheckpointReconstructionError("Checkpoint reconstruction provenance drifted.")
    try:
        session = LocalGameSession.from_persistence_payload(checkpoint)
        if canonical_json(session.to_persistence_payload()) != canonical_json(checkpoint):
            raise CheckpointReconstructionError("Reconstructed checkpoint did not restore exactly.")
        replay = ReplayRunner.from_payload(
            cast(ReplayArtifactPayload, checkpoint["replay_artifact"])
        ).run()
    except (GameLifecycleError, ReplayArtifactError) as exc:
        raise CheckpointReconstructionError(
            "Reconstructed checkpoint failed ordinary restore/replay validation."
        ) from exc
    if replay.status is not ReplayRunStatus.REPRODUCED:
        raise CheckpointReconstructionError("Reconstructed checkpoint replay drifted.")
    return session


def _source_payload(source_bytes: bytes) -> dict[str, JsonValue]:
    if type(source_bytes) is not bytes or hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
        raise CheckpointReconstructionError("Unsupported historical checkpoint source digest.")
    try:
        original = _object(validate_json_value(json.loads(source_bytes)))
    except (json.JSONDecodeError, UnicodeDecodeError, EventLogError) as exc:
        raise CheckpointReconstructionError(
            "Historical checkpoint source is not valid JSON."
        ) from exc
    expected = {
        "schema_version",
        "lifecycle",
        "initial_replay_lifecycle",
        "source_identity",
        "rng_state",
        "replay_artifact",
        "lifecycle_hash",
        "decision_records_hash",
        "event_log_hash",
        "rng_state_hash",
        "content_hash",
    }
    if (
        set(original) != expected
        or original["schema_version"] != "local-game-session-persistence-v1"
    ):
        raise CheckpointReconstructionError("Historical checkpoint source schema drifted.")
    lifecycle = _object(original["lifecycle"])
    decisions = _object(lifecycle["decisions"])
    bindings: dict[str, JsonValue] = {
        "lifecycle_hash": lifecycle,
        "decision_records_hash": decisions["records"],
        "event_log_hash": decisions["event_log"],
        "rng_state_hash": original["rng_state"],
        "content_hash": {k: v for k, v in original.items() if k != "content_hash"},
    }
    if any(original[key] != _hash(value) for key, value in bindings.items()):
        raise CheckpointReconstructionError("Historical checkpoint source hash drifted.")
    artifact = _object(original["replay_artifact"])
    initial = _object(original["initial_replay_lifecycle"])
    initial_decisions = _object(initial["decisions"])
    if (
        artifact["initial_lifecycle"] != initial
        or artifact["source_identity"] != original["source_identity"]
        or initial_decisions["records"] != []
        or decisions["records"] != artifact["decision_records"]
        or decisions["event_log"]
        != [*_array(initial_decisions["event_log"]), *_array(artifact["event_records"])]
    ):
        raise CheckpointReconstructionError("Historical checkpoint source evidence is incomplete.")
    return original


def _validate_mapping(
    original: dict[str, JsonValue], checkpoint: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    old = _object(original["lifecycle"])
    new = _object(checkpoint["lifecycle"])
    old_decisions = _object(old["decisions"])
    new_decisions = _object(new["decisions"])
    old_events = [_object(e) for e in _array(old_decisions["event_log"])]
    new_events = [_object(e) for e in _array(new_decisions["event_log"])]
    additions = [e for e in new_events if e["event_type"] == MODEL_COMPLETION_STATE_EVENT]
    retained = [e for e in new_events if e["event_type"] != MODEL_COMPLETION_STATE_EVENT]
    if (
        len(old_events) != 137
        or len(new_events) != 138
        or len(additions) != 1
        or new_events[129] != additions[0]
        or len(_array(old_decisions["records"])) != 18
        or len(retained) != len(old_events)
    ):
        raise CheckpointReconstructionError("Checkpoint reconstruction event inventory drifted.")
    bindings: dict[str, str] = {}
    for before, after in zip(old_events, retained, strict=True):
        before_id, after_id = before["event_id"], after["event_id"]
        if type(before_id) is not str or type(after_id) is not str:
            raise CheckpointReconstructionError(
                "Checkpoint reconstruction event identity is invalid."
            )
        bindings[before_id] = after_id
    if (
        len(bindings) != len(old_events)
        or len(set(bindings.values())) != len(bindings)
        or canonical_json(_rebind(old_decisions["event_log"], bindings)) != canonical_json(retained)
    ):
        raise CheckpointReconstructionError("Checkpoint reconstruction changed an original event.")
    expected = _object(_rebind(old, bindings))
    actual = copy.deepcopy(new)
    _object(actual["decisions"])["event_log"] = cast(list[JsonValue], retained)
    audits: list[JsonValue] = []
    for path in _AUDIT_PATHS:
        before, after = expected, actual
        for key in path[:-1]:
            before, after = _object(before[key]), _object(after[key])
        audits.append(
            {
                "path": "/" + "/".join(path),
                "original_hash": _hash(before[path[-1]]),
                "reconstructed_hash": _hash(after[path[-1]]),
            }
        )
        before[path[-1]] = after[path[-1]]
    if canonical_json(expected) != canonical_json(actual):
        raise CheckpointReconstructionError(
            "Checkpoint reconstruction changed original gameplay state."
        )
    if canonical_json(original["rng_state"]) != canonical_json(checkpoint["rng_state"]) or (
        canonical_json(original["source_identity"]) != canonical_json(checkpoint["source_identity"])
    ):
        raise CheckpointReconstructionError(
            "Checkpoint reconstruction changed original RNG/source."
        )
    initial = _object(original["initial_replay_lifecycle"])
    mapped_initial = copy.deepcopy(initial)
    new_initial = _object(checkpoint["initial_replay_lifecycle"])
    mapped_initial["runtime_content_audit"] = new_initial["runtime_content_audit"]
    if canonical_json(mapped_initial) != canonical_json(new_initial):
        raise CheckpointReconstructionError("Checkpoint reconstruction initial anchor drifted.")
    return {
        "recipe_version": "recorded-decision-reconstruction-v1",
        "source_sha256": SOURCE_SHA256,
        "source_runtime_build_id": _SOURCE_BUILD,
        "source_git_revision": _SOURCE_COMMIT,
        "runtime_provenance": "retained audit profile; source runtime was not silently substituted",
        "destination_runtime_build_id": current_engine_build_id(),
        "reconstructed_checkpoint_hash": _hash(checkpoint),
        "original_event_count": len(old_events),
        "reconstructed_event_count": len(new_events),
        "decision_count": 18,
        "event_id_mapping": cast(dict[str, JsonValue], bindings),
        "engine_regenerated_evidence": cast(list[JsonValue], additions),
        "derived_runtime_audits": audits,
        "original_decisions_rng_and_gameplay_preserved": True,
        "original_byte_replay_claimed": False,
    }


def _rebind(value: JsonValue, bindings: dict[str, str]) -> JsonValue:
    if isinstance(value, str):
        return bindings.get(value, value)
    if isinstance(value, list):
        return [_rebind(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _rebind(item, bindings) for key, item in value.items()}
    return value


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CheckpointReconstructionError("Checkpoint reconstruction requires an object.")
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise CheckpointReconstructionError("Checkpoint reconstruction requires an array.")
    return value


def _hash(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
