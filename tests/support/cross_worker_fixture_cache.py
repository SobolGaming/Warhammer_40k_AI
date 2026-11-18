"""Atomic cross-worker fixture checkpoint cache for read-only module fixtures.

Under pytest-xdist with `--dist=worksteal`, tests from a module that declares an
expensive `@pytest.fixture(scope="module")` can be stolen by multiple workers.
Without cross-worker coordination, every thief worker reconstructs that fixture
from scratch.

This helper coordinates construction through a `filelock.FileLock`:
- When running under xdist (`PYTEST_XDIST_TESTRUNUID` is present), entries live
  inside the shared per-testrun temporary root (`basetemp.parent`), so the first
  worker in the current pytest invocation executes the full builder under active
  coverage tracing and sibling workers deserialize the verified JSON payload.
- A covered controller may explicitly supply a fresh root and generation nonce
  for its serial producer and parallel consumers. This scope never crosses runs.
- Standalone non-coverage runs reuse checkpoints only within their current
  pytest invocation's temporary root. A later invocation always rebuilds fixture
  inputs, including imported helper code, source data and numerical dependencies.
- Standalone covered runs build directly under active tracing.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from filelock import FileLock

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import reproduce_canonical_deployment
from warhammer40k_core.ai.canonical_deployment_coverage import CanonicalDeploymentCoverage
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value

SCHEMA = "cross-worker-fixture-checkpoint-v1"
NATIVE_COMMAND_KEY = "cavalcade-native-command-checkpoint-v2"


def _coverage_active() -> bool:
    if any(name.startswith("COV_CORE_") for name in os.environ):
        return True
    try:
        import coverage
    except ImportError:
        return False
    return coverage.Coverage.current() is not None


def _covered_controller_directory() -> Path | None:
    root = os.environ.get("WH40K_COVERED_FIXTURE_CACHE")
    generation = os.environ.get("WH40K_COVERED_FIXTURE_RUN_ID")
    if root is None and generation is None:
        return None
    if (
        not root
        or not Path(root).is_absolute()
        or not generation
        or generation in {".", ".."}
        or not generation.isascii()
        or any(not (character.isalnum() or character in "-_.") for character in generation)
    ):
        raise ValueError(
            "Covered fixture cache requires an absolute root, nonce and active tracing."
        )
    import coverage

    if coverage.Coverage.current() is None:
        raise ValueError("Covered fixture cache requires active tracing, not environment hints.")
    return Path(root) / generation


def _cache_directory(
    *,
    basetemp: Path,
    build_id: str,
) -> Path | None:
    controller = _covered_controller_directory()
    if controller is not None:
        return controller
    testrun_uid = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if testrun_uid:
        shared_root = basetemp.parent if os.environ.get("PYTEST_XDIST_WORKER") else basetemp
        return shared_root / f"xdist-fixture-cache-{testrun_uid}"
    if _coverage_active():
        return None
    build_digest = hashlib.sha256(build_id.encode("utf-8")).hexdigest()[:24]
    return basetemp / "fixture-checkpoints-v1" / build_digest


def rehydrate_payload_receipt[R](cls: type[R], payload: JsonValue) -> R:
    """Restore a frozen `_payload_json`-backed receipt produced by an authoritative worker."""
    validated = validate_json_value(payload)
    instance = object.__new__(cls)
    object.__setattr__(instance, "_payload_json", canonical_json(validated))
    return instance


def load_or_build_json_fixture[T](
    *,
    key: str,
    source_files: tuple[Path, ...],
    tmp_path_factory: pytest.TempPathFactory,
    pytestconfig: pytest.Config,
    build_payload: Callable[[], JsonValue],
    restore_value: Callable[[JsonValue], T],
    require_cached: bool = False,
) -> T:
    """Build a JSON-serializable fixture once per scope and restore it cleanly."""
    build_id = verified_engine_build_identity().build_id
    directory = _cache_directory(
        basetemp=tmp_path_factory.getbasetemp(),
        build_id=build_id,
    )
    if directory is None:
        if require_cached:
            raise ValueError("Required fixture checkpoint has no cache scope.")
        return restore_value(validate_json_value(build_payload()))

    hasher = hashlib.sha256()
    hasher.update(SCHEMA.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(build_id.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(key.encode("utf-8"))
    for source_file in source_files:
        resolved = source_file.resolve(strict=True)
        hasher.update(b"\0")
        hasher.update(resolved.as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(resolved.read_bytes()).digest())
    digest = hasher.hexdigest()

    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}.json"
    lock_path = directory / f"{digest}.lock"
    with FileLock(str(lock_path), timeout=900):
        if target.is_file():
            envelope = validate_json_value(json.loads(target.read_text(encoding="utf-8")))
            if (
                not isinstance(envelope, dict)
                or envelope.get("schema") != SCHEMA
                or envelope.get("build_id") != build_id
                or envelope.get("key") != key
                or "payload" not in envelope
            ):
                raise ValueError(f"Corrupted cross-worker fixture cache entry: {target}")
            return restore_value(validate_json_value(envelope["payload"]))

        if require_cached:
            raise ValueError(f"Required covered fixture checkpoint is missing: {key}")
        payload = validate_json_value(build_payload())
        encoded = canonical_json(
            {
                "schema": SCHEMA,
                "build_id": build_id,
                "key": key,
                "payload": payload,
            }
        )
        temporary = directory / f"{digest}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(encoded + "\n", encoding="utf-8", newline="\n")
        temporary.replace(target)
    return restore_value(payload)


def load_or_measure_canonical_coverage(
    *,
    tmp_path_factory: pytest.TempPathFactory,
    pytestconfig: pytest.Config,
) -> tuple[LocalGameSession, CanonicalDeploymentCoverage]:
    """Share the immutable canonical deployment coverage measurement across workers."""

    def _build() -> JsonValue:
        session, _ = reproduce_canonical_deployment()
        before = canonical_json(session.to_persistence_payload())
        report = CanonicalDeploymentCoverage.measure(session=session)
        assert canonical_json(session.to_persistence_payload()) == before
        return validate_json_value(
            {
                "session": session.to_persistence_payload(),
                "report": report.to_payload(),
            }
        )

    def _restore(raw: JsonValue) -> tuple[LocalGameSession, CanonicalDeploymentCoverage]:
        data = cast(dict[str, JsonValue], raw)
        session = LocalGameSession.from_persistence_payload(data["session"])
        report = rehydrate_payload_receipt(CanonicalDeploymentCoverage, data["report"])
        return session, report

    return load_or_build_json_fixture(
        key="canonical-deployment-coverage-measured-v1",
        source_files=(Path(__file__),),
        tmp_path_factory=tmp_path_factory,
        pytestconfig=pytestconfig,
        build_payload=_build,
        restore_value=_restore,
    )


def _native_command_sources() -> tuple[Path, ...]:
    root = Path(__file__).resolve().parents[2]
    return (
        Path(__file__),
        root / "tests/support/cavalcade_v995.py",
        root / "data/army_lists/cavalcade-shadow-bloodthirster.json",
        root / "tests/factions/chaos_daemons/integration/test_cavalcade_v995_roster.py",
        root / "tests/factions/chaos_daemons/integration/test_cavalcade_native_screen_prefix.py",
        root / "tests/factions/chaos_daemons/integration/fixtures/cavalcade_v995_deployment.json",
    )


def publish_native_command_checkpoint(
    payload: JsonValue,
    *,
    tmp_path_factory: pytest.TempPathFactory,
    pytestconfig: pytest.Config,
) -> None:
    """Publish only the mirror's real payload after all original assertions succeed."""
    observed = load_or_build_json_fixture(
        key=NATIVE_COMMAND_KEY,
        source_files=_native_command_sources(),
        tmp_path_factory=tmp_path_factory,
        pytestconfig=pytestconfig,
        build_payload=lambda: payload,
        restore_value=lambda raw: raw,
    )
    if observed != payload:
        raise ValueError("Published native checkpoint differs from the authentic mirror.")


def load_native_command_checkpoint(
    *,
    tmp_path_factory: pytest.TempPathFactory,
    pytestconfig: pytest.Config,
) -> JsonValue:
    """Covered consumers require the producer; independent ad-hoc runs build normally."""
    from tests.support.cavalcade_v995 import run_mirror_to_command

    def build() -> JsonValue:
        session, _ = run_mirror_to_command()
        return session.to_persistence_payload()

    return load_or_build_json_fixture(
        key=NATIVE_COMMAND_KEY,
        source_files=_native_command_sources(),
        tmp_path_factory=tmp_path_factory,
        pytestconfig=pytestconfig,
        build_payload=build,
        restore_value=lambda raw: raw,
        require_cached=_covered_controller_directory() is not None,
    )
