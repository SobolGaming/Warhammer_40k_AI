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
from warhammer40k_core.core.secondary_vp_cap_scope import SecondaryVictoryPointCapScope
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
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as _chapter_source,
)

PROFILE_ID = "local-checkpoint:legacy-model-completion:2026-10-14"
RECOVERY_SCHEMA = "local-checkpoint-reconstruction-v3-audit-rng"
_RECIPE_VERSION = "recorded-decision-reconstruction-v3-audit-rng"
_SOURCE_REPLAY_SCHEMA = "replay-artifact-v36-target-aware-attack-groups"
_DESTINATION_REPLAY_SCHEMA = "replay-artifact-v37-private-rng"
_SOURCE_RNG_SEED = "audit-d04-native-emergency-1"
# Public, reproducible audit entropy, calibrated through all 18 recorded choices.
# This reconstruction is not suitable for secret competitive randomness.
_AUDIT_RNG_LABEL = "a32-exact-artifact-reconstruction-v3:3223"
_AUDIT_RNG_SEED = "6ba138bd8d5aeb37661f9d0aa6c6377ef433beefc39b43ed5f8943424e8d16a0"
_INITIAL_RNG_ANCHORS = ((), ("modifier_evaluation_history_origin",))
_FINAL_RNG_ANCHORS = (
    *_INITIAL_RNG_ANCHORS,
    ("psychic_modifier_history_origin",),
    ("psychic_modifier_history_origin", "modifier_evaluation_history_origin"),
)
_SETUP_HASH_MAPPINGS = (
    (
        "event-000038",
        "pre_battle_checkpoint",
        "110cd81f42c70af2cb17d66be61b7801685231760fac812a34cfab094d7ba9b4",
        "995d3bcaa86cb70be1ee62e106fd847257cd083718ea31cda4db674ad2a95640",
    ),
    (
        "event-000039",
        "pre_battle_checkpoint",
        "110cd81f42c70af2cb17d66be61b7801685231760fac812a34cfab094d7ba9b4",
        "995d3bcaa86cb70be1ee62e106fd847257cd083718ea31cda4db674ad2a95640",
    ),
    (
        "event-000039",
        "post_battle_start_checkpoint",
        "1a3d13c716702a6e08ff5e7d34091a9e48b06dcaed9bb40674b9293b2c86f057",
        "30b25e7df9cbf541a5838a49b2bf0cf7dfaed74accd9238060dd726d578f43d6",
    ),
)
_MISSION_PACK_ID = "11e-chapter-approved-2026-27"
_OLD_MISSION_HASH = "009a47e19b7e619f6a9bcd75a5294497ac1becb2aee4c320ffcd0a393c57399d"
_CURRENT_MISSION_HASH = "8f76fcf275397bd2ffabf16d3e127f059fb476e0144654bd54e550f5dd16faa1"
_OLD_SCORING_ROW_HASH = "b408ac7e759b3000d2c1a611624e28ba4ddb8e8f80c2a85589f89cd79927fedf"
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
    replay_input = copy.deepcopy(_object(original["replay_artifact"]))
    if replay_input["schema_version"] != _SOURCE_REPLAY_SCHEMA:
        raise CheckpointReconstructionError("Historical replay schema drifted.")
    replay_input["schema_version"] = _DESTINATION_REPLAY_SCHEMA
    replay_input["initial_lifecycle"] = _mapped_rng_anchors(
        replay_input["initial_lifecycle"], final=False
    )
    replay_input["initial_rng_state"] = _mapped_rng_state(replay_input["initial_rng_state"])
    replay_input["source_identity"] = _mapped_source_identity(original)
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
        checkpoint = _object(session.to_persistence_payload())
    except (DecisionError, GameLifecycleError, ReplayArtifactError) as exc:
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
        or canonical_json(_rebind(_mapped_setup_hashes(old_decisions["event_log"]), bindings))
        != canonical_json(retained)
    ):
        raise CheckpointReconstructionError("Checkpoint reconstruction changed an original event.")
    expected = _mapped_rng_anchors(_rebind(old, bindings), final=True)
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
    if canonical_json(_mapped_rng_state(original["rng_state"])) != canonical_json(
        checkpoint["rng_state"]
    ) or (
        canonical_json(_mapped_source_identity(original))
        != canonical_json(checkpoint["source_identity"])
    ):
        raise CheckpointReconstructionError(
            "Checkpoint reconstruction changed original RNG/source."
        )
    initial = _object(original["initial_replay_lifecycle"])
    mapped_initial = _mapped_rng_anchors(initial, final=False)
    new_initial = _object(checkpoint["initial_replay_lifecycle"])
    mapped_initial["runtime_content_audit"] = new_initial["runtime_content_audit"]
    if canonical_json(mapped_initial) != canonical_json(new_initial):
        raise CheckpointReconstructionError("Checkpoint reconstruction initial anchor drifted.")
    return {
        "recipe_version": _RECIPE_VERSION,
        "rng_metadata_mapping": {
            "original_seed": _SOURCE_RNG_SEED,
            "reconstructed_seed": _AUDIT_RNG_SEED,
            "audit_seed_derivation": f"sha256(utf8({_AUDIT_RNG_LABEL}))",
            "initial_lifecycle_anchor_paths": ["/" + "/".join(p) for p in _INITIAL_RNG_ANCHORS],
            "final_lifecycle_anchor_paths": ["/" + "/".join(p) for p in _FINAL_RNG_ANCHORS],
            "added_seed_paths_at_each_anchor": [
                "/config/private_rng_seed",
                "/state/private_rng_seed",
            ],
            "added_counter_path_at_each_anchor": "/state/tactical_secondary_draw_sequence",
            "tactical_secondary_draw_sequence": 0,
            "rng_history_and_draw_count_preserved": True,
            "preserved_dice_faces": [4, 4, 2, 1, 2],
            "reason": "Known audit entropy preserves this finite recorded sequence only.",
        },
        "replay_schema_mapping": {
            "original": _SOURCE_REPLAY_SCHEMA,
            "reconstructed": _DESTINATION_REPLAY_SCHEMA,
        },
        "game_config_hash_mapping": {
            "path": "/source_identity/game_config_hash",
            "original": _object(original["source_identity"])["game_config_hash"],
            "reconstructed": _object(checkpoint["source_identity"])["game_config_hash"],
            "reason": "Explicit audit seed added to the recorded config.",
        },
        "setup_checkpoint_state_hash_mappings": [
            {
                "event_id": event_id,
                "path": f"/payload/{field}/state_hash",
                "original": before,
                "reconstructed": after,
                "reason": "State gains only private_rng_seed and tactical_secondary_draw_sequence.",
            }
            for event_id, field, before, after in _SETUP_HASH_MAPPINGS
        ],
        "mission_source_identity_mapping": {
            "path": "/source_identity/mission_source_package_hash",
            "mission_pack_id": _MISSION_PACK_ID,
            "original": _OLD_MISSION_HASH,
            "reconstructed": _CURRENT_MISSION_HASH,
            "reason": (
                "Explicit player_turn scope; all other Chapter source scoring fields unchanged."
            ),
            "scoring_row_unchanged_remainder_sha256": _OLD_SCORING_ROW_HASH,
            "added_scoring_field": "secondary_vp_cap_scope",
            "added_scoring_value": SecondaryVictoryPointCapScope.PLAYER_TURN.value,
        },
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
        "original_decisions_and_gameplay_outcomes_preserved": True,
        "original_rng_metadata_preserved": False,
        "secret_competitive_rng_suitable": False,
        "original_byte_replay_claimed": False,
    }


def _mapped_rng_anchors(value: JsonValue, *, final: bool) -> dict[str, JsonValue]:
    """Add RNG metadata only at this authenticated artifact's declared anchors."""
    mapped = copy.deepcopy(_object(value))
    for path in _FINAL_RNG_ANCHORS if final else _INITIAL_RNG_ANCHORS:
        anchor = mapped
        for key in path:
            anchor = _object(anchor[key])
        config, state = _object(anchor["config"]), _object(anchor["state"])
        if (
            config["game_id"] != _SOURCE_RNG_SEED
            or state["game_id"] != _SOURCE_RNG_SEED
            or "private_rng_seed" in config
            or "private_rng_seed" in state
            or "tactical_secondary_draw_sequence" in state
        ):
            raise CheckpointReconstructionError("Historical RNG anchor drifted.")
        config["private_rng_seed"] = _AUDIT_RNG_SEED
        state["private_rng_seed"] = _AUDIT_RNG_SEED
        state["tactical_secondary_draw_sequence"] = 0
        decisions = _object(anchor["decisions"])
        decisions["event_log"] = _mapped_setup_hashes(decisions["event_log"])
    return mapped


def _mapped_setup_hashes(value: JsonValue) -> list[JsonValue]:
    events = copy.deepcopy(_array(value))
    for event_value in events:
        event = _object(event_value)
        for event_id, field, before, after in _SETUP_HASH_MAPPINGS:
            if event["event_id"] == event_id:
                checkpoint = _object(_object(event["payload"])[field])
                if checkpoint["state_hash"] != before:
                    raise CheckpointReconstructionError("Historical setup state hash drifted.")
                checkpoint["state_hash"] = after
    return events


def _mapped_rng_state(value: JsonValue) -> dict[str, JsonValue]:
    rng = _object(value)
    if rng["seed"] != _SOURCE_RNG_SEED:
        raise CheckpointReconstructionError("Historical RNG seed drifted.")
    return {**rng, "seed": _AUDIT_RNG_SEED}


def _mapped_source_identity(original: dict[str, JsonValue]) -> dict[str, JsonValue]:
    initial = _mapped_rng_anchors(original["initial_replay_lifecycle"], final=False)
    return {
        **_mapped_mission_source_identity(original["source_identity"]),
        "game_config_hash": _hash(initial["config"]),
    }


def _mapped_mission_source_identity(value: JsonValue) -> dict[str, JsonValue]:
    """One authenticated original's finite, scoring-neutral Chapter identity transition."""
    identity = _object(value)
    row = _chapter_source.mission_pack_scoring_row()
    current_hash = _chapter_source.source_package_definition().source_commit_or_import_hash
    scoring = _object(validate_json_value(row.to_payload()))
    if (
        identity["mission_pack_id"] != _MISSION_PACK_ID
        or identity["mission_source_package_hash"] != _OLD_MISSION_HASH
        or current_hash != _CURRENT_MISSION_HASH
        or row.secondary_vp_cap_scope is not SecondaryVictoryPointCapScope.PLAYER_TURN
        or scoring.pop("secondary_vp_cap_scope") != "player_turn"
        or _hash(scoring) != _OLD_SCORING_ROW_HASH
    ):
        raise CheckpointReconstructionError("Unregistered Chapter mission source transition.")
    return {**identity, "mission_source_package_hash": _CURRENT_MISSION_HASH}


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
