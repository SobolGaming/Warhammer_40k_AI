"""Private local-process transport for an explicitly registered Linux authority."""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Sequence
from queue import Empty, Queue
from threading import RLock, Thread
from types import TracebackType
from typing import IO, TYPE_CHECKING, Self
from weakref import WeakValueDictionary

from warhammer40k_core.adapters.execution_profile import (
    ExecutionProfileError,
    content_hash,
    decode_json,
    object_payload,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

if TYPE_CHECKING:
    from warhammer40k_core.adapters.linux_session import LinuxGameSession

MAX_FRAME_BYTES = 512 * 1024 * 1024


def read_frame(stream: IO[bytes], *, allow_eof: bool = False) -> bytes:
    raw = stream.readline(MAX_FRAME_BYTES + 1)
    if not raw and allow_eof:
        return raw
    if not raw or len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
        raise ExecutionProfileError("Linux authority closed or exceeded the frame boundary.")
    return raw


def write_frame(stream: IO[bytes], payload: JsonValue) -> None:
    raw = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(raw) > MAX_FRAME_BYTES:
        raise ExecutionProfileError("Linux authority request exceeds the frame boundary.")
    stream.write(raw)
    stream.flush()


class LinuxAuthority:
    """One trusted installed Linux process, shared by isolated session proxies.

    ``command`` is operator configuration, never a command from a checkpoint.
    No shell is used. A caller must register the inspected profile explicitly;
    inspection alone does not authorize gameplay or establish legacy provenance.
    """

    def __init__(
        self, command: Sequence[str], *, expected_profile: JsonValue, timeout_seconds: float = 900.0
    ) -> None:
        self._initialize(command, timeout_seconds=timeout_seconds)
        try:
            self._profile = self._receive()
            self._validate_profile(expected_profile)
        except (ExecutionProfileError, OSError) as exc:
            self.close()
            raise ExecutionProfileError("Linux authority registration failed.") from exc
        self._registered = True

    def _validate_profile(self, expected: JsonValue) -> None:
        if self._profile != expected:
            raise ExecutionProfileError("The installed Linux execution profile has drifted.")

    @classmethod
    def inspect(cls, command: Sequence[str], *, timeout_seconds: float = 60.0) -> JsonValue:
        instance = cls.__new__(cls)
        instance._initialize(command, timeout_seconds=timeout_seconds)
        try:
            return instance._receive()
        finally:
            instance.close()

    def _initialize(self, command: Sequence[str], *, timeout_seconds: float) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ExecutionProfileError("An explicit Linux authority command is required.")
        if not 0 < timeout_seconds <= 1800.0:
            raise ExecutionProfileError("Authority timeout must be positive and at most 1800s.")
        self._timeout = timeout_seconds
        self._registered = False
        self._sequence = 0
        self._closed = False
        self._lock = RLock()
        self._close_lock = RLock()
        self._sessions: WeakValueDictionary[str, LinuxGameSession] = WeakValueDictionary()
        self._responses: Queue[bytes | OSError] = Queue()
        self._process = subprocess.Popen(
            list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=False
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise ExecutionProfileError("Linux authority requires private input/output pipes.")
        self._input = self._process.stdin
        self._output = self._process.stdout
        self._reader = Thread(target=self._read_responses, daemon=True)
        self._reader.start()

    @property
    def profile(self) -> JsonValue:
        return copy.deepcopy(self._profile)

    @property
    def profile_hash(self) -> str:
        return content_hash(self._profile)

    def _read_responses(self) -> None:
        try:
            while raw := self._output.readline(MAX_FRAME_BYTES + 1):
                self._responses.put(raw)
                if len(raw) > MAX_FRAME_BYTES:
                    return
        except OSError as exc:
            self._responses.put(exc)
        finally:
            self._responses.put(b"")

    def _receive(self) -> JsonValue:
        try:
            raw = self._responses.get(timeout=self._timeout)
        except Empty as exc:
            raise ExecutionProfileError(
                "Linux authority response timed out; operation outcome is unknown. "
                "Close this authority and restore the last acknowledged checkpoint."
            ) from exc
        if isinstance(raw, OSError):
            raise ExecutionProfileError("Linux authority response pipe failed.") from raw
        if not raw or len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
            raise ExecutionProfileError("Linux authority response stream closed or overflowed.")
        return decode_json(raw)

    def call(self, session_id: str | None, operation: str, arguments: JsonValue) -> JsonValue:
        with self._lock:
            if self._closed or not self._registered:
                raise ExecutionProfileError("Linux authority is closed or unregistered.")
            self._sequence += 1
            request: dict[str, JsonValue] = {
                "sequence": self._sequence,
                "keep_sessions": validate_json_value(sorted(self._sessions)),
                "session_id": session_id,
                "operation": operation,
                "arguments": arguments,
            }
            try:
                write_frame(self._input, request)
                response = object_payload(self._receive(), label="Authority response")
            except (ExecutionProfileError, OSError) as exc:
                self._registered = False
                raise ExecutionProfileError(
                    "Linux authority failed; no host fallback is available."
                ) from exc
            if (
                set(response) != {"sequence", "result", "error"}
                or response["sequence"] != self._sequence
            ):
                self._registered = False
                raise ExecutionProfileError("Linux authority response sequence/schema drift.")
            if response["error"] is not None:
                raise ExecutionProfileError(
                    f"Linux authority rejected {operation}: {response['error']}"
                )
            return response["result"]

    def session(self) -> LinuxGameSession:
        from warhammer40k_core.adapters.linux_session import LinuxGameSession

        with self._lock:
            return LinuxGameSession._from_result(self, self.call(None, "create", {}))

    def restore(self, payload: JsonValue) -> LinuxGameSession:
        from warhammer40k_core.adapters.linux_session import LinuxGameSession

        with self._lock:
            return LinuxGameSession._from_result(self, self.call(None, "restore", payload))

    def enroll_legacy(self, payload_bytes: bytes, *, provenance: JsonValue) -> LinuxGameSession:
        from warhammer40k_core.adapters.execution_profile import checkpoint_envelope

        envelope = checkpoint_envelope(
            payload_bytes=payload_bytes, profile=self._profile, provenance=provenance
        )
        return self.restore(validate_json_value(envelope))

    def replay(self, envelope: JsonValue) -> JsonValue:
        """Run a profile-bound artifact with the unchanged exact replay runner."""
        return self.call(None, "replay", envelope)

    def replay_legacy(self, payload_bytes: bytes, *, provenance: JsonValue) -> JsonValue:
        from warhammer40k_core.adapters.execution_profile import checkpoint_envelope
        from warhammer40k_core.engine.replay import REPLAY_ARTIFACT_SCHEMA_VERSION

        envelope = checkpoint_envelope(
            payload_bytes=payload_bytes,
            profile=self._profile,
            provenance=provenance,
            payload_schema=REPLAY_ARTIFACT_SCHEMA_VERSION,
        )
        return self.replay(validate_json_value(envelope))

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self._registered = False
            self._input.close()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5.0)
            self._output.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
