"""Explicit executor binding without changing legacy engine state or replay checks."""

from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.support.cavalcade_v995 import strict_mirror_session
from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    ViewerContext,
    bearer_authorization,
)
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.execution_profile import (
    PROFILE_SCHEMA,
    ExecutionProfileError,
    checkpoint_bytes,
    checkpoint_envelope,
    content_hash,
    validate_executor_profile,
)
from warhammer40k_core.adapters.external_contract import SESSION_CREATE_SCHEMA_VERSION
from warhammer40k_core.adapters.linux_authority_transport import (
    LinuxAuthority,
    read_frame,
    write_frame,
)
from warhammer40k_core.adapters.linux_authority_worker import LinuxAuthorityDispatcher
from warhammer40k_core.adapters.linux_session import viewer_payload
from warhammer40k_core.adapters.local_session import LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION
from warhammer40k_core.adapters.numerical_policy import CURRENT_NUMERICAL_POLICY_ID
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.session_persistence import SQLiteSessionPersistenceStore
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameConfigPayload


def test_profile_envelope_keeps_original_bytes_and_explicit_provenance() -> None:
    raw = b'{ "a": 0.2500000000000031, "b": -0.0 }\n'
    profile: JsonValue = {"registered-runtime": "explicit-test-contract"}
    receipt: JsonValue = {"kind": "verified-producer", "receipt_sha256": "a" * 64}
    envelope = checkpoint_envelope(payload_bytes=raw, profile=profile, provenance=receipt)
    assert checkpoint_bytes(validate_json_value(envelope), profile=profile) == raw
    assert envelope["provenance"] == receipt
    with pytest.raises(ExecutionProfileError, match="different execution profile"):
        checkpoint_bytes(validate_json_value(envelope), profile={"other-runtime": "unknown"})


@pytest.mark.parametrize(
    "field", ["payload_base64", "payload_sha256", "profile_hash", "provenance"]
)
def test_profile_envelope_rejects_binding_drift(field: str) -> None:
    envelope = checkpoint_envelope(
        payload_bytes=b"{}", profile={"runtime": "one"}, provenance={"kind": "explicit-enrollment"}
    )
    envelope[field] = "drift"
    with pytest.raises(ExecutionProfileError, match="content hash drift"):
        checkpoint_bytes(validate_json_value(envelope), profile={"runtime": "one"})


def test_profile_enrollment_requires_a_receipt_and_checks_inner_bytes() -> None:
    with pytest.raises(ExecutionProfileError, match="provenance receipt"):
        checkpoint_envelope(payload_bytes=b"{}", profile={}, provenance={})
    envelope = checkpoint_envelope(payload_bytes=b"{}", profile={}, provenance={"kind": "explicit"})
    envelope["payload_sha256"] = "0" * 64
    envelope["content_hash"] = content_hash(
        {k: v for k, v in envelope.items() if k != "content_hash"}
    )
    with pytest.raises(ExecutionProfileError, match="Inner checkpoint byte hash drift"):
        checkpoint_bytes(validate_json_value(envelope), profile={})


def test_executor_registration_requires_the_registered_profile_and_same_engine() -> None:
    selected: JsonValue = {
        "schema_version": PROFILE_SCHEMA,
        "engine_build_id": "selected-build",
        "numerical_policy_id": CURRENT_NUMERICAL_POLICY_ID,
    }
    validate_executor_profile(selected, expected=selected, engine_build_id="selected-build")
    with pytest.raises(ExecutionProfileError, match="same engine build"):
        validate_executor_profile(selected, expected=selected, engine_build_id="other-build")
    with pytest.raises(ExecutionProfileError, match="has drifted"):
        validate_executor_profile(
            selected, expected={"other": True}, engine_build_id="selected-build"
        )
    with pytest.raises(ExecutionProfileError, match=r"Unsupported.*schema"):
        validate_executor_profile({}, expected={}, engine_build_id="selected-build")


def test_authority_framing_distinguishes_clean_close_from_truncated_json() -> None:
    stream = io.BytesIO()
    write_frame(stream, {"exact": 0.2500000000000031})
    stream.seek(0)
    assert json.loads(read_frame(stream)) == {"exact": 0.2500000000000031}
    assert read_frame(stream, allow_eof=True) == b""
    with pytest.raises(ExecutionProfileError, match="frame boundary"):
        read_frame(io.BytesIO(b'{"truncated":true}'))


@pytest.mark.integration
def test_dispatcher_real_native_roster_restore_fork_viewers_and_exact_replay() -> None:
    original = strict_mirror_session()
    # This is a dispatcher contract test on the host, not a claim that this
    # host's numerical behavior is a registered Linux execution profile.
    profile: dict[str, JsonValue] = {
        "schema_version": PROFILE_SCHEMA,
        "numerical_policy_id": CURRENT_NUMERICAL_POLICY_ID,
        "dispatcher-contract-fixture": "host-native",
    }
    dispatcher = LinuxAuthorityDispatcher(profile)
    sequence = 0
    retained: list[str] = []

    def call(
        identity: str | None, operation: str, arguments: JsonValue, *, expected_error: bool = False
    ) -> JsonValue:
        nonlocal sequence
        sequence += 1
        response = dispatcher.dispatch(
            {
                "sequence": sequence,
                "keep_sessions": validate_json_value(retained),
                "session_id": identity,
                "operation": operation,
                "arguments": arguments,
            }
        )
        if expected_error:
            assert response["result"] is None
            assert response["error"] is not None
            return response["error"]
        assert response["error"] is None, response
        return response["result"]

    raw = json.dumps(original.to_persistence_payload(), indent=2).encode()
    envelope = checkpoint_envelope(
        payload_bytes=raw,
        profile=profile,
        provenance={"kind": "explicit-host-fixture"},
        payload_schema=LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION,
    )
    identity = cast(str, call(None, "restore", validate_json_value(envelope)))
    retained.append(identity)
    assert call(identity, "to_persistence_payload", {}) == envelope
    assert checkpoint_bytes(call(identity, "to_persistence_payload", {}), profile=profile) == raw
    # Mutating caller-owned configuration or a returned profile cannot relabel
    # an existing session or its cached checkpoint.
    exported_profile = cast(dict[str, JsonValue], dispatcher.profile)
    exported_profile["numerical_policy_id"] = "milli-inch-half-away-v1"
    assert dispatcher.profile == profile
    incompatible = checkpoint_envelope(
        payload_bytes=raw,
        profile=exported_profile,
        provenance={"kind": "incompatible-policy-control"},
        payload_schema=LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION,
    )
    rejected = call(None, "restore", validate_json_value(incompatible), expected_error=True)
    assert isinstance(rejected, dict)
    assert "different execution profile" in str(rejected["message"])
    assert call(identity, "to_persistence_payload", {}) == envelope
    assert (
        call(identity, "authoritative_history_payload", {})
        == original.authoritative_history_payload()
    )
    for player in ("player-a", "player-b"):
        assert call(
            identity,
            "view_for_context",
            {"viewer": viewer_payload(ViewerContext.for_player(player))},
        ) == original.view(viewer_player_id=player)
    fork = cast(str, call(identity, "fork", {}))
    retained.append(fork)
    pending = original.view(viewer_player_id="player-a")["pending_decision"]
    assert pending is not None
    option = pending["options"][0]["option_id"]
    arguments: dict[str, JsonValue] = {
        "viewer": viewer_payload(ViewerContext.for_player("player-a")),
        "request_id": pending["request_id"],
        "option_id": option,
        "result_id": "linux-contract-choice",
    }
    expected = original.submit_viewer_option(
        viewer=ViewerContext.for_player("player-a"),
        request_id=pending["request_id"],
        option_id=option,
        result_id="linux-contract-choice",
    )
    assert call(fork, "submit_viewer_option", arguments) == expected.to_payload()
    assert call(fork, "decision_record_count", {}) == original.decision_record_count()
    assert call(identity, "decision_record_count", {}) == original.decision_record_count() - 1
    saved = call(fork, "to_persistence_payload", {})
    assert json.loads(checkpoint_bytes(saved, profile=profile)) == original.to_persistence_payload()
    restored = cast(str, call(None, "restore", saved))
    retained.append(restored)
    assert call(restored, "to_persistence_payload", {}) == saved
    assert (
        call(restored, "authoritative_history_payload", {})
        == original.authoritative_history_payload()
    )
    replay = cast(
        dict[str, JsonValue], call(restored, "verify_replay", {"artifact_id": "linux-contract"})
    )
    assert replay["status"] == "reproduced"
    assert replay["diagnostics"] == []
    profiled_replay = call(restored, "profiled_replay_artifact", {"artifact_id": "linux-contract"})
    assert call(None, "replay", profiled_replay) == replay
    replay_envelope = cast(dict[str, JsonValue], profiled_replay)
    incompatible_replay = checkpoint_envelope(
        payload_bytes=checkpoint_bytes(profiled_replay, profile=profile),
        profile=exported_profile,
        provenance={"kind": "incompatible-policy-control"},
        payload_schema=cast(str, replay_envelope["payload_schema"]),
    )
    rejected = call(None, "replay", validate_json_value(incompatible_replay), expected_error=True)
    assert isinstance(rejected, dict)
    assert "different execution profile" in str(rejected["message"])
    # Releasing one atomic fork cannot release another live proxy's state.
    retained.remove(fork)
    call(identity, "event_record_count", {})
    rejection = call(fork, "event_record_count", {}, expected_error=True)
    assert isinstance(rejection, dict)
    assert rejection["message"] == "Unknown or released authority session."
    assert call(restored, "event_record_count", {}) == original.event_record_count()


@pytest.mark.integration
@pytest.mark.skipif(
    sys.platform != "linux", reason="The registered worker requires Linux; Windows uses WSL."
)
def test_selected_linux_process_implements_adapter_session_and_roundtrips(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-B",
        "-X",
        "pycache_prefix=/dev/null",
        "-m",
        "warhammer40k_core.adapters.linux_authority_worker",
    ]
    profile = LinuxAuthority.inspect(command)
    with pytest.raises(ExecutionProfileError, match=r"Unsupported.*schema"):
        LinuxAuthority(command, expected_profile={"wrong-registered-executor": True})
    original = strict_mirror_session()
    config = GameConfig.from_payload(
        cast(GameConfigPayload, original.lifecycle.to_payload()["config"])
    )
    with LinuxAuthority(command, expected_profile=profile) as authority:
        assert authority.numerical_policy.numerical_policy_id == CURRENT_NUMERICAL_POLICY_ID
        session = authority.session()
        assert session.numerical_policy == authority.numerical_policy
        assert isinstance(session, AdapterGameSession)
        session.start(config)
        session.advance_until_decision_or_terminal()
        assert session.authoritative_history_payload() == original.authoritative_history_payload()
        checkpoint = session.to_persistence_payload()
        bare = json.dumps(original.to_persistence_payload(), indent=2).encode()
        enrolled = authority.enroll_legacy(
            bare, provenance={"kind": "current-native-checkpoint-enrollment"}
        )
        enrolled_checkpoint = enrolled.to_persistence_payload()
        assert isinstance(enrolled_checkpoint, dict)
        assert (
            enrolled_checkpoint["payload_schema"] == LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION
        )
        assert checkpoint_bytes(enrolled_checkpoint, profile=profile) == bare
        assert enrolled.authoritative_history_payload() == original.authoritative_history_payload()
        for player in ("player-a", "player-b"):
            assert enrolled.view(viewer_player_id=player) == original.view(viewer_player_id=player)
        assert enrolled.verify_replay(artifact_id="enrolled") == session.verify_replay(
            artifact_id="enrolled"
        )
        obsolete = copy.deepcopy(original.to_persistence_payload())
        assert isinstance(obsolete, dict)
        obsolete["schema_version"] = "local-game-session-persistence-v2-private-rng"
        with pytest.raises(ExecutionProfileError, match="schema"):
            authority.enroll_legacy(
                json.dumps(obsolete).encode(), provenance={"kind": "obsolete-format-control"}
            )
        assert enrolled.event_record_count() == original.event_record_count()
        recovered = authority.restore(copy.deepcopy(checkpoint))
        assert recovered.to_persistence_payload() == checkpoint
        assert recovered.view(viewer_player_id="player-a") == session.view(
            viewer_player_id="player-a"
        )
        assert recovered.verify_replay(artifact_id="linux-subprocess") == session.verify_replay(
            artifact_id="linux-subprocess"
        )
        assert authority.replay(
            session.profiled_replay_artifact(artifact_id="linux-subprocess")
        ) == (session.verify_replay(artifact_id="linux-subprocess"))
        store = SQLiteSessionPersistenceStore(tmp_path / "linux-authority.sqlite")
        server = AdapterGameServer(
            session_factory=authority.session,
            session_recovery_factory=authority.restore,
        )
        server.initialize_persistence(store)
        created = server.handle(
            method="POST",
            path="/sessions",
            query={},
            body={
                "schema_version": SESSION_CREATE_SCHEMA_VERSION,
                "config": validate_json_value(config.to_payload()),
            },
            authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        )
        assert created.status_code == 201, created.payload
        advanced = server.handle(
            method="POST",
            path=f"/games/{config.game_id}/advance",
            query={},
            body=None,
            authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        )
        assert advanced.status_code == 200, advanced.payload
        before_recovery = server.persistence_payload()
        recovered_server = AdapterGameServer(
            session_factory=authority.session,
            session_recovery_factory=authority.restore,
            persistence_store=store,
        )
        assert recovered_server.persistence_payload() == before_recovery
    with pytest.raises(ExecutionProfileError, match="closed or unregistered"):
        session.event_record_count()
