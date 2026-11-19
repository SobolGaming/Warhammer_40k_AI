"""Active inner policy and legacy geometry boundaries, using native sessions."""

from __future__ import annotations

import copy
import hashlib
import json
from math import isclose
from typing import cast

import pytest

from tests.d09_heavy_helpers import heavy_session, move_heavy_unit
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameConfigPayload,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.spatial_index_state import SpatialIndexState
from warhammer40k_core.geometry.numerical_identity import (
    CURRENT_NUMERICAL_IDENTITY,
    NumericalIdentity,
)
from warhammer40k_core.geometry.pathing import PathWitness, PathWitnessPayload
from warhammer40k_core.geometry.pose import GeometryError, Pose, PosePayload


def test_inner_identity_survives_ordinary_move_persistence_and_replay() -> None:
    session = heavy_session(fly=True)
    session.advance_until_decision_or_terminal()
    move_heavy_unit(session, advance=False, distance=2.00049, flying=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.model_movement_history
    assert all(
        isclose(row.distance_inches, 2.00049, rel_tol=0, abs_tol=1e-12)
        for row in state.model_movement_history
    )
    payload = session.lifecycle.to_payload()
    assert payload["config"] is not None
    assert payload["state"] is not None
    identity = CURRENT_NUMERICAL_IDENTITY.to_payload()
    assert payload["config"]["numerical_identity"] == identity
    assert payload["state"]["numerical_identity"] == identity
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.lifecycle.to_payload() == payload
    artifact = session.replay_artifact(artifact_id="inner-numerical-identity")
    assert (
        ReplayRunner.from_payload(json.loads(json.dumps(artifact))).run().status
        is ReplayRunStatus.REPRODUCED
    )
    assert restored.view(viewer_player_id="player-a") == session.view(viewer_player_id="player-a")
    assert restored.view(viewer_player_id="player-b") == session.view(viewer_player_id="player-b")


@pytest.mark.parametrize("owner", ["config", "state"])
@pytest.mark.parametrize("change", ["missing", "policy", "coordinates", "version", "extra"])
def test_inner_payload_rejects_unbound_or_incompatible_identity(owner: str, change: str) -> None:
    session = heavy_session()
    payload = session.lifecycle.to_payload()
    source = payload["config"] if owner == "config" else payload["state"]
    assert source is not None
    altered = cast(dict[str, object], copy.deepcopy(source))
    identity = cast(dict[str, object], altered["numerical_identity"])
    if change == "missing":
        del altered["numerical_identity"]
    elif change == "policy":
        identity["numerical_policy_id"] = "legacy-binary-inch-v1"
    elif change == "coordinates":
        identity["coordinate_representation_id"] = "rational-quadratic-coordinate-v1"
    elif change == "version":
        identity["version"] = "unknown"
    else:
        identity["snapped"] = True
    if owner == "config":
        with pytest.raises(GameLifecycleError, match="numerical identity"):
            GameConfig.from_payload(cast(GameConfigPayload, altered))
    else:
        with pytest.raises(GameLifecycleError, match="numerical identity"):
            GameState.from_payload(cast(GameStatePayload, altered))
    assert session.lifecycle.to_payload() == payload


@pytest.mark.parametrize("level", ["pose", "point", "facing", "witness", "model_path"])
def test_legacy_pose_and_path_do_not_drop_precision_labels(level: str) -> None:
    pose = Pose.at(1.0005, 2)
    witness = PathWitness.for_straight_line_endpoints((("model", Pose.at(0, 2), pose),))
    if level in {"pose", "point", "facing"}:
        raw = cast(dict[str, object], json.loads(json.dumps(pose.to_payload())))
        target = (
            raw
            if level == "pose"
            else cast(dict[str, object], raw["position" if level == "point" else "facing"])
        )
        target["coordinate_representation_id"] = "rational-quadratic-coordinate-v1"
        with pytest.raises(GeometryError):
            Pose.from_payload(cast(PosePayload, raw))
    else:
        raw_path = cast(dict[str, object], json.loads(json.dumps(witness.to_payload())))
        target = (
            raw_path
            if level == "witness"
            else cast(list[dict[str, object]], raw_path["model_paths"])[0]
        )
        target["numerical_policy_id"] = "milli-inch-half-away-v1"
        with pytest.raises(GeometryError):
            PathWitness.from_payload(cast(PathWitnessPayload, raw_path))
    assert PathWitness.from_payload(witness.to_payload()) == witness
    assert Pose.from_payload(pose.to_payload()) == pose


def test_current_context_cache_binds_contract_without_changing_legacy_witness_bytes() -> None:
    from dataclasses import replace

    from warhammer40k_core.core.visibility import (
        TerrainVisibilityContext,
        TerrainVisibilityContextPayload,
    )
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    config = heavy_session().lifecycle.config
    assert config is not None
    observer = Model("observer", Pose.at(1, 1), CircularBase(0.5), ModelVolume(1))
    target = Model("target", Pose.at(4, 1), CircularBase(0.5), ModelVolume(1))
    state = SpatialIndexState.empty()
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=config.ruleset_descriptor,
        los_cache_key=state.los_cache_key(),
        observer_model=observer,
        target_models=(target,),
        target_model_keywords=(("target", ()),),
    )
    assert context.numerical_identity == CURRENT_NUMERICAL_IDENTITY
    witness = context.resolve_line_of_sight()
    restored = TerrainVisibilityContext.from_payload(context.to_payload())
    assert restored == context
    assert restored.resolve_line_of_sight() == witness
    payload = context.to_payload()
    assert "numerical_identity" not in payload
    malformed = cast(dict[str, object], copy.deepcopy(payload))
    malformed["numerical_identity"] = CURRENT_NUMERICAL_IDENTITY.to_payload()
    with pytest.raises(GeometryError, match="incompatible"):
        TerrainVisibilityContext.from_payload(cast(TerrainVisibilityContextPayload, malformed))
    with pytest.raises(GeometryError, match="NumericalIdentity"):
        replace(context, numerical_identity=cast(NumericalIdentity, None))
    for namespace, actual in (
        ("los", state.los_cache_key()),
        ("pathing", state.pathing_cache_key()),
    ):
        legacy: dict[str, object] = {
            "namespace": namespace,
            "terrain_revision": 0,
            "model_blocker_revision": 0,
            "terrain_feature_ids": [],
            "terrain_volume_ids": [],
        }
        expected = (
            namespace
            + ":"
            + hashlib.sha256(
                json.dumps(
                    legacy, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                ).encode()
            ).hexdigest()[:16]
        )
        assert actual == expected


def test_linux_dispatcher_rejects_inner_policy_without_losing_session() -> None:
    from warhammer40k_core.adapters.execution_profile import PROFILE_SCHEMA
    from warhammer40k_core.adapters.linux_authority_worker import LinuxAuthorityDispatcher
    from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

    dispatcher = LinuxAuthorityDispatcher(
        {
            "schema_version": PROFILE_SCHEMA,
            "numerical_policy_id": "binary-inch-milli-inch-movement-budget-v1",
        }
    )
    created = dispatcher.dispatch(
        {
            "sequence": 1,
            "keep_sessions": [],
            "session_id": None,
            "operation": "create",
            "arguments": {},
        }
    )
    identity = created["result"]
    assert isinstance(identity, str)
    session = heavy_session()
    config = session.lifecycle.to_payload()["config"]
    assert config is not None
    altered = copy.deepcopy(config)
    altered["numerical_identity"]["numerical_policy_id"] = "milli-inch-half-away-v1"
    request: dict[str, JsonValue] = {
        "sequence": 2,
        "keep_sessions": [identity],
        "session_id": identity,
        "operation": "start",
        "arguments": {"config": validate_json_value(altered)},
    }
    rejected = dispatcher.dispatch(request)
    assert rejected["result"] is None
    assert isinstance(rejected["error"], dict)
    assert rejected["error"]["type"] == "GameLifecycleError"
    request["sequence"] = 3
    request["arguments"] = {"config": validate_json_value(config)}
    accepted = dispatcher.dispatch(request)
    assert accepted["error"] is None
    assert accepted["result"] is not None


def test_state_construction_rejects_untyped_binding() -> None:
    from dataclasses import replace

    state = heavy_session().lifecycle.state
    assert state is not None
    with pytest.raises(GameLifecycleError, match="NumericalIdentity"):
        replace(state, numerical_identity=cast(NumericalIdentity, "milli-inch-half-away-v1"))


def test_current_authority_checkpoint_envelope_restores_on_same_profile() -> None:
    from warhammer40k_core.adapters.execution_profile import PROFILE_SCHEMA
    from warhammer40k_core.adapters.linux_authority_worker import LinuxAuthorityDispatcher
    from warhammer40k_core.adapters.local_session import (
        LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION,
    )
    from warhammer40k_core.engine.event_log import validate_json_value

    dispatcher = LinuxAuthorityDispatcher(
        {
            "schema_version": PROFILE_SCHEMA,
            "numerical_policy_id": "binary-inch-milli-inch-movement-budget-v1",
        }
    )
    created = dispatcher.dispatch(
        {
            "sequence": 1,
            "keep_sessions": [],
            "session_id": None,
            "operation": "create",
            "arguments": {},
        }
    )
    identity = created["result"]
    assert isinstance(identity, str)
    config = heavy_session().lifecycle.to_payload()["config"]
    assert config is not None
    started = dispatcher.dispatch(
        {
            "sequence": 2,
            "keep_sessions": [identity],
            "session_id": identity,
            "operation": "start",
            "arguments": {"config": validate_json_value(config)},
        }
    )
    assert started["error"] is None
    exported = dispatcher.dispatch(
        {
            "sequence": 3,
            "keep_sessions": [identity],
            "session_id": identity,
            "operation": "to_persistence_payload",
            "arguments": {},
        }
    )
    assert exported["error"] is None
    envelope = exported["result"]
    assert isinstance(envelope, dict)
    assert envelope["payload_schema"] == LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION
    restored = dispatcher.dispatch(
        {
            "sequence": 4,
            "keep_sessions": [identity],
            "session_id": None,
            "operation": "restore",
            "arguments": envelope,
        }
    )
    assert restored["error"] is None
    other = restored["result"]
    assert isinstance(other, str)
    repeated = dispatcher.dispatch(
        {
            "sequence": 5,
            "keep_sessions": [identity, other],
            "session_id": other,
            "operation": "to_persistence_payload",
            "arguments": {},
        }
    )
    assert repeated["result"] == envelope


def test_movement_facade_rejects_precision_labels_before_queue_or_state_mutation() -> None:
    from tests.d09_heavy_helpers import heavy_unit_id
    from tests.movement_submission_helpers import straight_line_witness_for_unit
    from tests.psychic_modifier_helpers import pending_request
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = heavy_session()
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="identity-select-unit",
        option_id=heavy_unit_id(session),
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="identity-select-action", option_id="normal_move"
    )
    request = pending_request(session)
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    valid = MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=context.proposal_kind,
        unit_instance_id=context.unit_instance_id,
        movement_phase_action="normal_move",
        movement_mode="normal",
        witness=straight_line_witness_for_unit(
            session.lifecycle, unit_instance_id=context.unit_instance_id, dy=1
        ),
    ).to_payload()
    malformed = cast(dict[str, object], copy.deepcopy(valid))
    witness = cast(dict[str, object], malformed["witness"])
    witness["numerical_policy_id"] = "milli-inch-half-away-v1"
    before = session.to_persistence_payload()
    rejected = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="identity-invalid-path",
        payload=validate_json_value(malformed),
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    assert pending_request(session) == request
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="identity-valid-path",
        payload=validate_json_value(valid),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID


@pytest.mark.parametrize("change", ["root", "nested", "missing", "provenance"])
def test_numerical_reconstruction_rejects_forged_identity_bindings(change: str) -> None:
    from tests.support.a32_recovery import historical_checkpoint_bytes, recovered_payload
    from warhammer40k_core.adapters.numerical_checkpoint_reconstruction import (
        CheckpointReconstructionError,
        verify_checkpoint_reconstruction,
    )
    from warhammer40k_core.engine.event_log import JsonValue, canonical_json

    package = cast(dict[str, JsonValue], recovered_payload())
    checkpoint = cast(dict[str, JsonValue], package["checkpoint"])
    lifecycle = cast(dict[str, JsonValue], checkpoint["lifecycle"])
    anchor = (
        lifecycle
        if change != "nested"
        else cast(dict[str, JsonValue], lifecycle["modifier_evaluation_history_origin"])
    )
    state = cast(dict[str, JsonValue], anchor["state"])
    if change == "missing":
        del state["numerical_identity"]
    elif change == "provenance":
        provenance = cast(dict[str, JsonValue], package["provenance"])
        provenance["numerical_identity_mapping"] = {}
    else:
        identity = cast(dict[str, JsonValue], state["numerical_identity"])
        identity["numerical_policy_id"] = "milli-inch-half-away-v1"
    package["content_hash"] = hashlib.sha256(
        canonical_json(
            {key: value for key, value in package.items() if key != "content_hash"}
        ).encode()
    ).hexdigest()
    with pytest.raises(CheckpointReconstructionError):
        verify_checkpoint_reconstruction(historical_checkpoint_bytes(), package)


def test_retained_recipe_requires_its_original_executor_and_source_stays_unchanged() -> None:
    from tests.support.a32_recovery import historical_checkpoint_bytes
    from warhammer40k_core.adapters.checkpoint_reconstruction import (
        PROFILE_ID,
        CheckpointReconstructionError,
        reconstruct_local_checkpoint,
    )

    raw = historical_checkpoint_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "55f23684cedb354050605bb796928bea5971acb73d975ffe54ce230ae2db9370"
    )
    with pytest.raises(CheckpointReconstructionError):
        reconstruct_local_checkpoint(raw, profile_id=PROFILE_ID)
    assert historical_checkpoint_bytes() == raw


def test_event_delta_projection_reuse_is_request_and_identity_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from tests.shared.category_migration.phase18g_18h_session_security import (
        _create_session,
        _events,
        _projection,
        _string,
        _submit_lifecycle_command,
    )
    from warhammer40k_core.adapters import server_sync
    from warhammer40k_core.adapters.access_control import (
        DEV_PLAYER_A_TOKEN,
        DEV_PLAYER_B_TOKEN,
        DEV_SPECTATOR_TOKEN,
        ViewerContext,
    )
    from warhammer40k_core.adapters.projection import GameViewPayload
    from warhammer40k_core.adapters.server import AdapterGameServer
    from warhammer40k_core.adapters.session_events import CursorValidationError
    from warhammer40k_core.adapters.session_protocol import SessionRevisionSnapshot

    server = AdapterGameServer()
    session_id = _create_session(server, game_id="numerical-request-projection")
    initial = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    cursor = _string(initial, "event_cursor")
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    viewer = ViewerContext.for_player("player-a")
    snapshot = record.snapshot_for_viewer(viewer)
    original = LocalGameSession.view_for_context
    observed: list[LocalGameSession] = []

    def observe(self: LocalGameSession, *, viewer: ViewerContext) -> GameViewPayload:
        observed.append(self)
        return original(self, viewer=viewer)

    monkeypatch.setattr(LocalGameSession, "view_for_context", observe)
    empty = _events(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN, cursor=cursor)
    assert empty["resync_required"] is False
    assert empty["events"] == []
    assert empty["projection_state_hash"] == initial["projection_state_hash"]
    assert len(observed) == 1
    observed.clear()
    assert _events(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN, cursor=cursor) == empty
    assert len(observed) == 1  # No hash survives a request boundary.

    observed.clear()
    memo: list[tuple[SessionRevisionSnapshot, ViewerContext, str]] = []
    project = server_sync._snapshot_projection_hash  # pyright: ignore[reportPrivateUsage]
    expected = project(snapshot, viewer=viewer, memo=memo)
    assert project(snapshot, viewer=viewer, memo=memo) == expected
    assert len(observed) == 1
    equivalent_snapshot = replace(snapshot)
    equivalent_viewer = ViewerContext.for_player("player-a")
    assert equivalent_snapshot is not snapshot
    assert equivalent_viewer is not viewer
    assert project(equivalent_snapshot, viewer=viewer, memo=memo) == expected
    assert project(snapshot, viewer=equivalent_viewer, memo=memo) == expected
    assert len(observed) == 3
    assert len(memo) == 3

    binding = server.cursor_codec.decode(cursor)
    with pytest.raises(CursorValidationError):
        server_sync.validate_cursor_projection_anchor(
            record=record,
            viewer=viewer,
            cursor=replace(binding, projection_state_hash="0" * 64),
            _projection_memo=memo,
        )
    assert len(observed) == 3  # A memo hit still compares the authenticated hash.
    server_sync.validate_cursor_projection_anchor(record=record, viewer=viewer, cursor=binding)
    server_sync.validate_cursor_projection_anchor(record=record, viewer=viewer, cursor=binding)
    assert len(observed) == 5  # Durable callers keep independent fresh validation.

    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="numerical-request-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    current = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    assert current["projection_state_hash"] != initial["projection_state_hash"]
    observed.clear()
    first = _events(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN, cursor=cursor, limit=1)
    assert first["resync_required"] is False
    assert first["has_more"] is True
    assert first["projection_state_hash"] == initial["projection_state_hash"]
    # Target is new; the historical anchor and paginated boundary are the same stored snapshot.
    assert len(observed) == 2
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    assert observed[0] is record.current_snapshot().adapter_session
    assert observed[1] is snapshot.adapter_session
    resumed = _string(first, "next_cursor")
    while True:
        page = _events(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN, cursor=resumed)
        assert page["resync_required"] is False
        resumed = _string(page, "next_cursor")
        if page["has_more"] is False:
            break
    assert resumed == current["event_cursor"]
    assert page["projection_state_hash"] == current["projection_state_hash"]

    # Each viewer keeps its own freshly projected authority, including delayed history.
    for token in (DEV_PLAYER_B_TOKEN, DEV_SPECTATOR_TOKEN):
        own_projection = _projection(server, session_id=session_id, token=token)
        observed.clear()
        own_page = _events(
            server,
            session_id=session_id,
            token=token,
            cursor=_string(own_projection, "event_cursor"),
        )
        assert own_page["resync_required"] is False
        assert own_page["projection_state_hash"] == own_projection["projection_state_hash"]
        assert len(observed) == 1
        wrong_viewer = _events(server, session_id=session_id, token=token, cursor=resumed)
        assert wrong_viewer["resync_required"] is True
    malformed = _events(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN, cursor="forged")
    assert malformed["resync_required"] is True
    assert malformed["resync_reason"] == "malformed"


def test_projection_envelope_validates_and_detaches_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.shared.category_migration.phase18g_18h_session_security import _create_session
    from warhammer40k_core.adapters import server_sync
    from warhammer40k_core.adapters.access_control import DEV_PLAYER_A_TOKEN, ViewerContext
    from warhammer40k_core.adapters.projection import GameViewPayload
    from warhammer40k_core.adapters.server import AdapterGameServer
    from warhammer40k_core.engine.event_log import EventLogError, JsonValue, validate_json_value

    server = AdapterGameServer()
    session_id = _create_session(server, game_id="numerical-projection-detachment")
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    viewer = ViewerContext.for_player("player-a")
    original_view = LocalGameSession.view_for_context
    raw_views: list[GameViewPayload] = []
    probe: object = {"values": (True, 1, 1.0, -0.0, {"mutable": cast(list[JsonValue], [])})}
    normalizations = 0

    def observed_view(self: LocalGameSession, *, viewer: ViewerContext) -> GameViewPayload:
        view = original_view(self, viewer=viewer)
        # Fault injection retains the complete native view and all engine decisions.
        cast(dict[str, object], cast(object, view))["validation_probe"] = probe
        raw_views.append(view)
        return view

    def observed_validation(value: object) -> JsonValue:
        nonlocal normalizations
        normalizations += 1
        return validate_json_value(value)

    monkeypatch.setattr(LocalGameSession, "view_for_context", observed_view)
    monkeypatch.setattr(server_sync, "validate_json_value", observed_validation)

    def project() -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            server_sync.session_projection_payload(
                record=record,
                viewer=viewer,
                cursor_codec=server.cursor_codec,
                retention_limit=server.event_retention_limit,
            ),
        )

    payload = project()
    assert normalizations == 1  # One full recursive normalization, no discarded clone.
    raw = cast(JsonValue, raw_views[-1])
    assert payload["projection"] == validate_json_value(raw)
    assert payload["session_id"] == session_id
    assert payload["projection_state_hash"] == raw_views[-1]["projection_state_hash"]

    def detached(source: JsonValue, result: JsonValue) -> None:
        if isinstance(source, dict):
            assert type(result) is dict
            assert result is not source
            assert source.keys() == result.keys()
            for key, value in source.items():
                detached(value, result[key])
        elif isinstance(source, (list, tuple)):
            assert type(result) is list
            assert result is not source
            for before, after in zip(source, result, strict=True):
                detached(before, after)
        else:
            assert type(result) is type(source)
            assert result == source

    detached(raw, payload["projection"])
    returned_view = payload["projection"]
    assert isinstance(returned_view, dict)
    returned_view.clear()
    assert raw_views[-1]
    assert project()["projection"] == validate_json_value(cast(JsonValue, raw_views[-1]))
    for invalid in (
        float("nan"),
        float("inf"),
        {1: "bad-key"},
        "<object object at 0x1234>",
        object(),
    ):
        probe = invalid
        with pytest.raises(EventLogError):
            project()

        response = server.handle(
            method="GET",
            path=f"/sessions/{session_id}/projection",
            authorization=f"Bearer {DEV_PLAYER_A_TOKEN}",
        )
        assert response.status_code == 400
        assert "malformed_json_payload" in json.dumps(response.payload)
    # Wrapper-only and combined malformed values retain the same typed public rejection.
    monkeypatch.setattr(record, "game_id", cast(str, object()))
    for wrapper_probe in ({"valid": True}, object()):
        probe = wrapper_probe
        with pytest.raises(EventLogError):
            project()
        response = server.handle(
            method="GET",
            path=f"/sessions/{session_id}/projection",
            authorization=f"Bearer {DEV_PLAYER_A_TOKEN}",
        )
        assert response.status_code == 400
        assert "malformed_json_payload" in json.dumps(response.payload)
