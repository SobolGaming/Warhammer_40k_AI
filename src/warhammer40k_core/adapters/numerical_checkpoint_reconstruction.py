# pyright: reportPrivateUsage=false
# This versioned successor composes the immutable, source-pinned v3 recipe interface.
"""Explicit numerical-identity successor for one authenticated audit checkpoint.

The retained v3 recipe is unchanged. This opt-in v4 recipe maps its same finite
source through ordinary current engine submissions and records every new binding.
"""

from __future__ import annotations

import copy
from typing import cast

from warhammer40k_core.adapters import checkpoint_reconstruction as retained
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import (
    REPLAY_ARTIFACT_SCHEMA_VERSION,
    ReplayArtifact,
    ReplayArtifactError,
    ReplayArtifactPayload,
    ReplayRunner,
    ReplayRunStatus,
)
from warhammer40k_core.geometry.numerical_identity import LEGACY_NUMERICAL_IDENTITY

PROFILE_ID = "local-checkpoint:legacy-model-completion:2026-10-14:numerical-identity-v1"
RECOVERY_SCHEMA = "local-checkpoint-reconstruction-v4-numerical-identity"
RECIPE_VERSION = "recorded-decision-reconstruction-v4-numerical-identity"
CheckpointReconstructionError = retained.CheckpointReconstructionError
# Exact v3 -> v4 setup state hashes, independently observed through the real
# SetupReplayCheckpoint owner. No arbitrary source hash is admitted.
SETUP_HASH_SUCCESSOR = {
    "995d3bcaa86cb70be1ee62e106fd847257cd083718ea31cda4db674ad2a95640": (
        "903922c601f9f3cfbd68e6dec71347318a97f02ba8b28dcbb053047ae4055db1"
    ),
    "30b25e7df9cbf541a5838a49b2bf0cf7dfaed74accd9238060dd726d578f43d6": (
        "9ed1a83f9c0ba23477530791731addb1fa1c7626eff02e003e17d0d145ca93de"
    ),
}


def _setup_hashes(value: JsonValue, *, reverse: bool = False) -> list[JsonValue]:
    events = copy.deepcopy(retained._array(value))
    for raw in events:
        event = retained._object(raw)
        for event_id, field, _original, v3_hash in retained._SETUP_HASH_MAPPINGS:
            if event["event_id"] == event_id:
                checkpoint = retained._object(retained._object(event["payload"])[field])
                v4_hash = SETUP_HASH_SUCCESSOR[v3_hash]
                before, after = (v4_hash, v3_hash) if reverse else (v3_hash, v4_hash)
                if checkpoint["state_hash"] != before:
                    raise CheckpointReconstructionError("Numerical setup state hash drifted.")
                checkpoint["state_hash"] = after
    return events


def _add_identity(value: JsonValue, *, final: bool) -> dict[str, JsonValue]:
    mapped = retained._mapped_rng_anchors(value, final=final)
    for path in retained._FINAL_RNG_ANCHORS if final else retained._INITIAL_RNG_ANCHORS:
        anchor = mapped
        for key in path:
            anchor = retained._object(anchor[key])
        for owner in ("config", "state"):
            target = retained._object(anchor[owner])
            if "numerical_identity" in target:
                raise CheckpointReconstructionError("Historical numerical anchor drifted.")
            target["numerical_identity"] = cast(JsonValue, LEGACY_NUMERICAL_IDENTITY.to_payload())
        decisions = retained._object(anchor["decisions"])
        decisions["event_log"] = _setup_hashes(decisions["event_log"])
    return mapped


def _remove_identity(value: JsonValue, *, final: bool) -> dict[str, JsonValue]:
    """Validate the new bindings before checking retained v3 outcome invariants."""
    mapped = copy.deepcopy(retained._object(value))
    for path in retained._FINAL_RNG_ANCHORS if final else retained._INITIAL_RNG_ANCHORS:
        anchor = mapped
        for key in path:
            anchor = retained._object(anchor[key])
        for owner in ("config", "state"):
            target = retained._object(anchor[owner])
            if target.get("numerical_identity") != LEGACY_NUMERICAL_IDENTITY.to_payload():
                raise CheckpointReconstructionError("Reconstructed numerical identity drifted.")
            del target["numerical_identity"]
        decisions = retained._object(anchor["decisions"])
        decisions["event_log"] = _setup_hashes(decisions["event_log"], reverse=True)
    return mapped


def _source_identity(original: dict[str, JsonValue]) -> dict[str, JsonValue]:
    initial = _add_identity(original["initial_replay_lifecycle"], final=False)
    return {
        **retained._mapped_source_identity(original),
        "game_config_hash": retained._hash(initial["config"]),
    }


def _mapping(
    original: dict[str, JsonValue], checkpoint: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if checkpoint["source_identity"] != _source_identity(original):
        raise CheckpointReconstructionError("Numerical reconstruction source identity drifted.")
    normalized = copy.deepcopy(checkpoint)
    normalized["lifecycle"] = _remove_identity(normalized["lifecycle"], final=True)
    normalized["initial_replay_lifecycle"] = _remove_identity(
        normalized["initial_replay_lifecycle"], final=False
    )
    normalized["source_identity"] = retained._mapped_source_identity(original)
    # This verifies retained events, decisions, RNG and outcomes against the
    # unchanged original recipe. It is not execution or v3 format qualification.
    provenance = retained._validate_mapping(original, normalized)
    provenance.update(
        {
            "recipe_version": RECIPE_VERSION,
            "reconstructed_checkpoint_hash": retained._hash(checkpoint),
            "replay_schema_mapping": {
                "original": retained._SOURCE_REPLAY_SCHEMA,
                "reconstructed": REPLAY_ARTIFACT_SCHEMA_VERSION,
            },
            "numerical_identity_mapping": {
                "identity": cast(JsonValue, LEGACY_NUMERICAL_IDENTITY.to_payload()),
                "initial_anchor_paths": [
                    "/" + "/".join(path) for path in retained._INITIAL_RNG_ANCHORS
                ],
                "final_anchor_paths": [
                    "/" + "/".join(path) for path in retained._FINAL_RNG_ANCHORS
                ],
                "added_fields_at_each_anchor": [
                    "/config/numerical_identity",
                    "/state/numerical_identity",
                ],
                "retained_v3_recipe": retained._RECIPE_VERSION,
                "original_histories_modified": False,
            },
            "game_config_hash_mapping": {
                "path": "/source_identity/game_config_hash",
                "original": retained._object(original["source_identity"])["game_config_hash"],
                "reconstructed": retained._object(checkpoint["source_identity"])[
                    "game_config_hash"
                ],
                "reason": "Explicit audit RNG and numerical identity at authenticated anchors.",
            },
            "setup_checkpoint_state_hash_mappings": [
                {
                    "event_id": event_id,
                    "path": f"/payload/{field}/state_hash",
                    "original": before,
                    "reconstructed": SETUP_HASH_SUCCESSOR[v3_hash],
                    "reason": "Explicit audit RNG and legacy numerical identity.",
                }
                for event_id, field, before, v3_hash in retained._SETUP_HASH_MAPPINGS
            ],
        }
    )
    return provenance


def reconstruct_local_checkpoint(source_bytes: bytes, *, profile_id: str) -> dict[str, JsonValue]:
    if profile_id != PROFILE_ID:
        raise CheckpointReconstructionError(
            "Unsupported numerical checkpoint reconstruction profile."
        )
    original = retained._source_payload(source_bytes)
    replay_input = copy.deepcopy(retained._object(original["replay_artifact"]))
    if replay_input["schema_version"] != retained._SOURCE_REPLAY_SCHEMA:
        raise CheckpointReconstructionError("Historical replay schema drifted.")
    replay_input["schema_version"] = REPLAY_ARTIFACT_SCHEMA_VERSION
    replay_input["initial_lifecycle"] = _add_identity(
        replay_input["initial_lifecycle"], final=False
    )
    replay_input["initial_rng_state"] = retained._mapped_rng_state(
        replay_input["initial_rng_state"]
    )
    replay_input["source_identity"] = _source_identity(original)
    try:
        artifact = ReplayArtifact.from_payload(cast(ReplayArtifactPayload, replay_input))
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
        checkpoint = retained._object(session.to_persistence_payload())
    except (DecisionError, GameLifecycleError, ReplayArtifactError) as exc:
        raise CheckpointReconstructionError(
            "Numerical reconstruction failed through the engine."
        ) from exc
    package: dict[str, JsonValue] = {
        "schema_version": RECOVERY_SCHEMA,
        "profile_id": PROFILE_ID,
        "checkpoint": checkpoint,
        "provenance": _mapping(original, checkpoint),
    }
    package["content_hash"] = retained._hash(package)
    verify_checkpoint_reconstruction(source_bytes, package)
    return copy.deepcopy(package)


def verify_checkpoint_reconstruction(source_bytes: bytes, package: JsonValue) -> LocalGameSession:
    original = retained._source_payload(source_bytes)
    value = retained._object(package)
    if (
        set(value) != {"schema_version", "profile_id", "checkpoint", "provenance", "content_hash"}
        or value["schema_version"] != RECOVERY_SCHEMA
        or value["profile_id"] != PROFILE_ID
    ):
        raise CheckpointReconstructionError(
            "Numerical checkpoint reconstruction fields/profile drifted."
        )
    if value["content_hash"] != retained._hash(
        {key: item for key, item in value.items() if key != "content_hash"}
    ):
        raise CheckpointReconstructionError(
            "Numerical checkpoint reconstruction content hash drifted."
        )
    checkpoint = retained._object(value["checkpoint"])
    try:
        provenance = _mapping(original, checkpoint)
    except KeyError as exc:
        raise CheckpointReconstructionError(
            "Reconstructed numerical evidence is incomplete."
        ) from exc
    if canonical_json(value["provenance"]) != canonical_json(provenance):
        raise CheckpointReconstructionError(
            "Numerical checkpoint reconstruction provenance drifted."
        )
    try:
        session = LocalGameSession.from_persistence_payload(checkpoint)
        if canonical_json(session.to_persistence_payload()) != canonical_json(checkpoint):
            raise CheckpointReconstructionError("Numerical checkpoint did not restore exactly.")
        replay = ReplayRunner.from_payload(
            cast(ReplayArtifactPayload, checkpoint["replay_artifact"])
        ).run()
    except (GameLifecycleError, ReplayArtifactError) as exc:
        raise CheckpointReconstructionError(
            "Numerical checkpoint failed strict restore/replay."
        ) from exc
    if replay.status is not ReplayRunStatus.REPRODUCED:
        raise CheckpointReconstructionError("Numerical checkpoint replay drifted.")
    return session
