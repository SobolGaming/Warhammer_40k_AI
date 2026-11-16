"""Linux-only process entry point: python -B -X pycache_prefix=/dev/null -m ..."""

from __future__ import annotations

import copy
import os
import signal
import sys
from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import cast

from warhammer40k_core.adapters.access_control import (
    AccessControlError,
    PrincipalRole,
    RolePolicy,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.execution_profile import (
    ExecutionProfileError,
    checkpoint_bytes,
    checkpoint_envelope,
    decode_json,
    linux_execution_profile,
    object_payload,
    string_field,
)
from warhammer40k_core.adapters.linux_authority_transport import read_frame, write_frame
from warhammer40k_core.adapters.local_session import (
    LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION,
    LocalGameSession,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameConfigPayload
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusPayload,
)
from warhammer40k_core.engine.replay import (
    REPLAY_ARTIFACT_SCHEMA_VERSION,
    ReplayArtifactError,
    ReplayArtifactPayload,
    ReplayRunner,
)

_ARGUMENTS: dict[str, set[str]] = {
    "fork": set(),
    "to_persistence_payload": set(),
    "authoritative_identity_payload": set(),
    "authoritative_history_payload": set(),
    "start": {"config"},
    "advance_until_decision_or_terminal": set(),
    "view": {"viewer_player_id"},
    "view_for_context": {"viewer"},
    "rules_catalog_view": set(),
    "events_since": {"cursor", "viewer_player_id"},
    "events_since_for_context": {"cursor", "viewer"},
    "event_page_for_context": {"cursor", "viewer", "visible_limit"},
    "authoritative_event_page_for_context": {"cursor", "viewer", "visible_limit"},
    "visible_event_count_for_context": {"cursor", "viewer"},
    "authoritative_visible_event_prefix_counts": {"viewer"},
    "event_record_count": set(),
    "decision_record_count": set(),
    "status_for_context": {"status", "viewer"},
    "submit_option": {"request_id", "option_id", "result_id"},
    "submit_parameterized_payload": {"request_id", "payload", "result_id"},
    "submit_viewer_option": {"viewer", "request_id", "option_id", "result_id"},
    "submit_viewer_parameterized_payload": {"viewer", "request_id", "payload", "result_id"},
    "replay_artifact": {"artifact_id"},
    "support_profile": set(),
    "verify_replay": {"artifact_id"},
    "profiled_replay_artifact": {"artifact_id"},
}


@dataclass(slots=True)
class _OwnedSession:
    session: LocalGameSession
    provenance: JsonValue
    checkpoint: JsonValue = None
    inner_checkpoint_hash: str | None = None


class LinuxAuthorityDispatcher:
    def __init__(self, profile: JsonValue) -> None:
        self.profile = copy.deepcopy(profile)
        self._sessions: dict[str, _OwnedSession] = {}
        self._next_session = 0
        self._sequence = 0

    def dispatch(self, request: JsonValue) -> dict[str, JsonValue]:
        value = object_payload(request, label="Authority request")
        if set(value) != {"sequence", "keep_sessions", "session_id", "operation", "arguments"}:
            raise ExecutionProfileError("Authority request schema drift.")
        if type(value["sequence"]) is not int or value["sequence"] != self._sequence + 1:
            raise ExecutionProfileError("Authority request sequence drift.")
        self._sequence += 1
        retained = value["keep_sessions"]
        if not isinstance(retained, list) or any(
            not isinstance(item, str) or item not in self._sessions for item in retained
        ):
            raise ExecutionProfileError("Authority retained session identities drifted.")
        # Atomic server forks must not retain every obsolete full game forever.
        # The trusted client supplies the IDs of its still-live proxy objects.
        self._sessions = {key: owned for key, owned in self._sessions.items() if key in retained}
        operation = string_field(value, "operation")
        arguments = object_payload(value["arguments"], label="Authority arguments")
        try:
            result = self._execute(value["session_id"], operation, arguments)
        except (GameLifecycleError, AccessControlError, ReplayArtifactError) as exc:
            return {
                "sequence": self._sequence,
                "result": None,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        return {"sequence": self._sequence, "result": validate_json_value(result), "error": None}

    def _register(self, owned: _OwnedSession) -> str:
        self._next_session += 1
        identity = f"linux-session-{self._next_session}"
        self._sessions[identity] = owned
        return identity

    def _execute(
        self, identity: JsonValue, operation: str, args: dict[str, JsonValue]
    ) -> JsonValue:
        if identity is None:
            if operation == "create" and not args:
                return self._register(
                    _OwnedSession(LocalGameSession(), {"kind": "produced-by-registered-executor"})
                )
            if operation == "restore":
                if args["payload_schema"] != LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION:
                    raise ExecutionProfileError("Restore requires a local-session checkpoint.")
                raw = checkpoint_bytes(args, profile=self.profile)
                inner = object_payload(decode_json(raw), label="Inner session checkpoint")
                restored = LocalGameSession.from_persistence_payload(inner)
                return self._register(
                    _OwnedSession(
                        restored,
                        copy.deepcopy(args["provenance"]),
                        copy.deepcopy(args),
                        string_field(inner, "content_hash"),
                    )
                )
            if operation == "replay":
                if args["payload_schema"] != REPLAY_ARTIFACT_SCHEMA_VERSION:
                    raise ExecutionProfileError("Replay requires a replay artifact.")
                raw = checkpoint_bytes(args, profile=self.profile)
                return validate_json_value(
                    ReplayRunner.from_payload(cast(ReplayArtifactPayload, decode_json(raw)))
                    .run()
                    .to_payload()
                )
            raise ExecutionProfileError("Unknown authority creation/recovery operation.")
        if not isinstance(identity, str) or identity not in self._sessions:
            raise ExecutionProfileError("Unknown or released authority session.")
        if operation not in _ARGUMENTS or set(args) != _ARGUMENTS[operation]:
            raise ExecutionProfileError("Unknown authority operation or argument schema drift.")
        owned = self._sessions[identity]
        session = owned.session
        if operation == "fork":
            return self._register(
                _OwnedSession(
                    session.fork(),
                    copy.deepcopy(owned.provenance),
                    copy.deepcopy(owned.checkpoint),
                    owned.inner_checkpoint_hash,
                )
            )
        if operation == "to_persistence_payload":
            inner = object_payload(
                session.to_persistence_payload(), label="Inner session checkpoint"
            )
            inner_hash = string_field(inner, "content_hash")
            if owned.checkpoint is None or owned.inner_checkpoint_hash != inner_hash:
                owned.checkpoint = checkpoint_envelope(
                    payload_bytes=canonical_json(inner).encode("utf-8"),
                    profile=self.profile,
                    provenance=owned.provenance,
                )
                owned.inner_checkpoint_hash = inner_hash
            return copy.deepcopy(owned.checkpoint)
        if operation == "authoritative_identity_payload":
            return validate_json_value(session.authoritative_identity_payload())
        if operation == "authoritative_history_payload":
            return validate_json_value(session.authoritative_history_payload())
        if operation == "start":
            return validate_json_value(
                session.start(
                    GameConfig.from_payload(cast(GameConfigPayload, args["config"]))
                ).to_payload()
            )
        if operation == "advance_until_decision_or_terminal":
            return validate_json_value(session.advance_until_decision_or_terminal().to_payload())
        if operation == "view":
            return validate_json_value(
                session.view(viewer_player_id=string_field(args, "viewer_player_id"))
            )
        if operation == "view_for_context":
            return validate_json_value(session.view_for_context(viewer=_viewer(args)))
        if operation == "rules_catalog_view":
            return validate_json_value(session.rules_catalog_view())
        if operation == "events_since":
            return validate_json_value(
                session.events_since(
                    _cursor(args), viewer_player_id=string_field(args, "viewer_player_id")
                )
            )
        if operation == "events_since_for_context":
            return validate_json_value(
                session.events_since_for_context(_cursor(args), viewer=_viewer(args))
            )
        if operation == "event_page_for_context":
            return validate_json_value(
                session.event_page_for_context(
                    _cursor(args),
                    viewer=_viewer(args),
                    visible_limit=_integer(args, "visible_limit"),
                )
            )
        if operation == "authoritative_event_page_for_context":
            return validate_json_value(
                session.authoritative_event_page_for_context(
                    _cursor(args),
                    viewer=_viewer(args),
                    visible_limit=_integer(args, "visible_limit"),
                )
            )
        if operation == "visible_event_count_for_context":
            return session.visible_event_count_for_context(_cursor(args), viewer=_viewer(args))
        if operation == "authoritative_visible_event_prefix_counts":
            return list(session.authoritative_visible_event_prefix_counts(viewer=_viewer(args)))
        if operation == "event_record_count":
            return session.event_record_count()
        if operation == "decision_record_count":
            return session.decision_record_count()
        if operation == "status_for_context":
            return session.status_for_context(
                LifecycleStatus.from_payload(cast(LifecycleStatusPayload, args["status"])),
                viewer=_viewer(args),
            )
        if operation == "submit_option":
            return validate_json_value(
                session.submit_option(
                    request_id=string_field(args, "request_id"),
                    option_id=string_field(args, "option_id"),
                    result_id=string_field(args, "result_id"),
                ).to_payload()
            )
        if operation == "submit_parameterized_payload":
            return validate_json_value(
                session.submit_parameterized_payload(
                    request_id=string_field(args, "request_id"),
                    payload=args["payload"],
                    result_id=string_field(args, "result_id"),
                ).to_payload()
            )
        if operation == "submit_viewer_option":
            return validate_json_value(
                session.submit_viewer_option(
                    viewer=_viewer(args),
                    request_id=string_field(args, "request_id"),
                    option_id=string_field(args, "option_id"),
                    result_id=string_field(args, "result_id"),
                ).to_payload()
            )
        if operation == "submit_viewer_parameterized_payload":
            return validate_json_value(
                session.submit_viewer_parameterized_payload(
                    viewer=_viewer(args),
                    request_id=string_field(args, "request_id"),
                    payload=args["payload"],
                    result_id=string_field(args, "result_id"),
                ).to_payload()
            )
        if operation == "replay_artifact":
            return validate_json_value(
                session.replay_artifact(artifact_id=string_field(args, "artifact_id"))
            )
        if operation == "verify_replay":
            return validate_json_value(
                ReplayRunner.from_payload(
                    session.replay_artifact(artifact_id=string_field(args, "artifact_id"))
                )
                .run()
                .to_payload()
            )
        if operation == "profiled_replay_artifact":
            artifact = session.replay_artifact(artifact_id=string_field(args, "artifact_id"))
            return checkpoint_envelope(
                payload_bytes=canonical_json(validate_json_value(artifact)).encode("utf-8"),
                profile=self.profile,
                provenance=owned.provenance,
                payload_schema=REPLAY_ARTIFACT_SCHEMA_VERSION,
            )
        if operation == "support_profile":
            return validate_json_value(session.support_profile())
        raise ExecutionProfileError("Unimplemented authority operation.")


def _integer(args: dict[str, JsonValue], key: str) -> int:
    value = args[key]
    if type(value) is not int:
        raise ExecutionProfileError(f"{key} must be an integer.")
    return value


def _cursor(args: dict[str, JsonValue]) -> EventStreamCursor:
    return EventStreamCursor(_integer(args, "cursor"))


def _viewer(args: dict[str, JsonValue]) -> ViewerContext:
    value = object_payload(args["viewer"], label="Authority viewer")
    policy = object_payload(value["policy"], label="Authority role policy")
    role_policy = RolePolicy(
        role=PrincipalRole(string_field(policy, "role")),
        may_create_session=cast(bool, policy["may_create_session"]),
        may_mutate_lifecycle=cast(bool, policy["may_mutate_lifecycle"]),
        may_submit_decision=cast(bool, policy["may_submit_decision"]),
        may_view_live=cast(bool, policy["may_view_live"]),
        may_view_catalog=cast(bool, policy["may_view_catalog"]),
        may_view_support=cast(bool, policy["may_view_support"]),
        may_export_replay=cast(bool, policy["may_export_replay"]),
        omniscient=cast(bool, policy["omniscient"]),
        delay_revisions=_integer(policy, "delay_revisions"),
    )
    return ViewerContext(
        principal_id=string_field(value, "principal_id"),
        role=PrincipalRole(string_field(value, "role")),
        viewer_player_id=cast(str | None, value["viewer_player_id"]),
        policy=role_policy,
        authorization_epoch=_integer(value, "authorization_epoch"),
    )


def main() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    profile = linux_execution_profile()
    dispatcher = LinuxAuthorityDispatcher(profile)
    write_frame(sys.stdout.buffer, profile)
    requests: Queue[bytes | ExecutionProfileError] = Queue()
    Thread(target=_read_owned_input, args=(requests,), daemon=True).start()
    while True:
        raw = requests.get()
        if isinstance(raw, ExecutionProfileError):
            raise raw
        request = decode_json(raw)
        write_frame(sys.stdout.buffer, dispatcher.dispatch(request))


def _read_owned_input(requests: Queue[bytes | ExecutionProfileError]) -> None:
    """Release a WSL process even if its Windows owner closes during engine work."""
    try:
        while raw := read_frame(sys.stdin.buffer, allow_eof=True):
            requests.put(raw)
    except (ExecutionProfileError, OSError) as exc:
        requests.put(ExecutionProfileError(f"Linux authority input failed: {exc}"))
        return
    # SIGTERM has the default kernel action; it also stops active native calls.
    # No response or completed game operation is claimed after owner disconnect.
    os.kill(os.getpid(), signal.SIGTERM)


if __name__ == "__main__":
    main()
