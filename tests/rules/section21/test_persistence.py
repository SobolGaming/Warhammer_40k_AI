"""Strict persistence/replay belongs to separate supported Core checkpoints."""

import hashlib
import json
from typing import cast

import pytest

from tests.d09_heavy_helpers import heavy_session, move_heavy_unit
from tests.surge_helpers import SOURCE, TARGET, surge_descriptor, surge_lifecycle, surge_path
from warhammer40k_core.adapters.local_session import (
    LocalGameSession,
    LocalGameSessionPersistenceError,
    LocalGameSessionPersistencePayload,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayArtifactPayload,
    ReplayRunner,
    ReplayRunStatus,
)
from warhammer40k_core.engine.triggered_movement import TriggeredMovementEligibleUnit
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.geometry.pathing import PathWitness


def test_supported_core_flight_checkpoint_restores_and_replays() -> None:
    session = heavy_session(fly=True)
    session.advance_until_decision_or_terminal()
    move_heavy_unit(session, advance=False, distance=2, flying=True)
    final = session.lifecycle.to_payload()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.lifecycle.to_payload() == final
    assert restored.view(viewer_player_id="player-a") == session.view(viewer_player_id="player-a")
    assert restored.view(viewer_player_id="player-b") == session.view(viewer_player_id="player-b")
    artifact = session.replay_artifact(artifact_id="s21:core-flight")
    assert (
        ReplayRunner.from_payload(json.loads(json.dumps(artifact))).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_strict_persistence_rejects_valid_artifact_with_mismatched_metadata_or_tails() -> None:
    session = heavy_session(fly=True)
    session.advance_until_decision_or_terminal()
    move_heavy_unit(session, advance=False, distance=2, flying=True)
    saved = cast(LocalGameSessionPersistencePayload, session.to_persistence_payload())
    artifact = saved["replay_artifact"]
    assert artifact["decision_records"]
    assert artifact["event_records"]

    mismatched_artifacts: tuple[ReplayArtifactPayload, ...] = (
        {**artifact, "artifact_id": "different-artifact"},
        {**artifact, "decision_records": artifact["decision_records"][:-1]},
        {**artifact, "event_records": artifact["event_records"][:-1]},
    )
    for mismatched in mismatched_artifacts:
        ReplayArtifact.from_payload(mismatched)
        payload: dict[str, JsonValue] = {
            key: value
            for key, value in cast(dict[str, JsonValue], saved).items()
            if key != "content_hash"
        }
        payload["replay_artifact"] = cast(JsonValue, mismatched)
        payload["content_hash"] = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()
        with pytest.raises(LocalGameSessionPersistenceError, match="persistence replay"):
            LocalGameSession.from_persistence_payload(payload)


def test_supported_core_surge_wrong_inventory_retry_restore_and_exact_replay() -> None:
    lifecycle = surge_lifecycle()
    state = lifecycle.state
    assert state is not None
    desc = surge_descriptor(lifecycle=lifecycle)
    request = triggered_movement_unit_selection_request(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        descriptor=desc,
        eligible_units=(
            TriggeredMovementEligibleUnit(SOURCE, "s21:core-hook", desc.source_rule_id),
        ),
    )
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:core-select",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    before = session.to_persistence_payload()
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    full = surge_path(lifecycle, (3,) * 5)
    for result_id, path in (
        ("s21:core-missing", PathWitness.for_paths(full.model_paths[:1])),
        ("s21:core-legal", full),
    ):
        payload = MovementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=context.proposal_kind,
            unit_instance_id=SOURCE,
            movement_phase_action="surge_move",
            witness=path,
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(payload.to_payload()),
        )
        if result_id == "s21:core-missing":
            assert status.status_kind is LifecycleStatusKind.INVALID
            assert session.to_persistence_payload() == before
            assert (
                LocalGameSession.from_persistence_payload(
                    json.loads(json.dumps(before))
                ).to_persistence_payload()
                == before
            )
        else:
            assert status.status_kind is not LifecycleStatusKind.INVALID
    final = session.lifecycle.to_payload()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.lifecycle.to_payload() == final
    artifact = session.replay_artifact(artifact_id="s21:core-surge")
    assert (
        ReplayRunner.from_payload(json.loads(json.dumps(artifact))).run().status
        is ReplayRunStatus.REPRODUCED
    )
