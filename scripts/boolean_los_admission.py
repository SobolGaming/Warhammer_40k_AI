"""Closed source transition with a fresh complete covered profile; no allocation search."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import cast

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.hosted_timing_calibration import _object, read_json

BASE = "70b1d6ad4b5265fddae30aaf869e4f91471269af"
RUNTIME = "d637f1649b7c3bfee1683c0112ac0ba37233afbf1f9640e6b4f2bbf47fa46c55"
PREVIOUS_RUNTIME = "8d7e3355d9db2c9477ba63b752dc1dfa054b5c00583ea467e3fbbc0e21d5638d"
SCHEMA = "historical-snapshot-fresh-boolean-los-profile-v1"
FILENAME = "current-covered-evidence.json"
MANIFEST_SHA256 = "5d3b31896c265ba5cd152a79d147b8d48cbbecdc1898e8aa593791a7c8eb9312"
RUNTIME_SOURCES = frozenset(
    {
        "src/warhammer40k_core/core/visibility.py",
        "src/warhammer40k_core/engine/shooting_targets.py",
        "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/thousand_sons/army_rule.py",
        "src/warhammer40k_core/geometry/continuous_visibility.py",
        "src/warhammer40k_core/geometry/physical_visibility.py",
    }
)
VISIBILITY_TEST_SHA256 = "5ae3fa685a0d75855d550b78107b4fe6b810e61d518b880b69ffbe8ed1c935ee"
OWNERSHIP_TEST_SHA256 = "7863b5747eb63c3f6d26562da55d93a6b05f1a41e5f7285eaa54448550430f08"
TEST_SOURCES = {
    "tests/rules/section06/test_visibility.py": VISIBILITY_TEST_SHA256,
    "tests/rules/section06/test_visibility_ownership.py": OWNERSHIP_TEST_SHA256,
}
SOURCE_PRODUCER = "33d199058f2e65f544bcc535e41862e2c09207eb"
SUCCESSOR_FILE = "ci/test_shards/native-charge-source-successor.json"
SUCCESSOR_PATHS = frozenset(
    {
        "tests/support/cavalcade_native_charge.py",
        "docs/performance/policy-v3/operation-map.json",
        "scripts/boolean_los_admission.py",
        "tests/code_quality/test_current_shard_compatibility.py",
    }
)


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Hash the complete original measurement inputs without running old code."""
    from tools.performance_policy import MAP

    if producer != SOURCE_PRODUCER:
        raise SystemExit("Unreviewed covered source producer.")
    archive = subprocess.check_output(
        [
            "git",
            "archive",
            producer,
            "src",
            "tests",
            "scripts",
            "tools",
            "contracts/schemas",
            "uv.lock",
            "pyproject.toml",
            MAP,
        ],
        cwd=root,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    inputs = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream:
            if member.isfile():
                source = stream.extractfile(member)
                assert source is not None
                inputs[member.name] = hashlib.sha256(source.read()).hexdigest()
    return dict(sorted(inputs.items()))


def validate_successor(historical: dict[str, str], live: dict[str, str], record: object) -> None:
    """Admit only this finite reviewed delta; reject every other source change."""
    scope = _object(record, {"schema", "producer", "changes"}, "covered source successor")
    if (scope["schema"], scope["producer"]) != (
        "native-charge-source-successor-v1",
        SOURCE_PRODUCER,
    ):
        raise SystemExit("Unreviewed covered source successor.")
    changes = _object(scope["changes"], set(SUCCESSOR_PATHS), "successor changes")
    expected = historical.copy()
    for name, value in changes.items():
        row = _object(value, {"before", "after"}, "successor source hashes")
        after = row["after"]
        if (
            row["before"] != historical.get(name)
            or not isinstance(after, str)
            or len(after) != 64
            or any(c not in "0123456789abcdef" for c in after)
            or after == row["before"]
        ):
            raise SystemExit("Covered source successor hashes differ: " + name)
        expected[name] = after
    # The original producer remains valid for its own evidence. A successor must
    # include every declared new/changed file, with no unlisted source drift.
    if live != historical and live != expected:
        raise SystemExit("Live covered sources differ from the exact reviewed successor.")


def validate_manifest(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise SystemExit("Unreviewed Boolean LOS manifest bytes.")


def validate_transition(root: Path) -> None:
    from warhammer40k_core import build_identity

    validate_manifest((root / MANIFEST).read_bytes())
    package_checkout = Path(build_identity.__file__).resolve().parents[2]
    if package_checkout != root.resolve():
        raise SystemExit("Boolean LOS admission requires its actual runtime checkout.")
    # Rebuild from live resource bytes on every admission. The ordinary cached
    # runtime identity cannot authenticate a supplied root or same-process drift.
    expected = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if expected != (root / MANIFEST).read_bytes():
        raise SystemExit("Boolean LOS live runtime source differs from the reviewed manifest.")
    if (
        fingerprint(root, BASE) != PREVIOUS_RUNTIME
        or json.loads((root / MANIFEST).read_bytes())["fingerprint"] != RUNTIME
    ):
        raise SystemExit("Unreviewed Boolean LOS runtime transition.")
    for name, digest in TEST_SOURCES.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Unreviewed Boolean LOS test source: " + name)


def transitioned_test(root: Path, owner: str, current: bytes, historical: bytes) -> bool:
    if owner not in TEST_SOURCES:
        return False
    validate_transition(root)
    if hashlib.sha256(current).hexdigest() != TEST_SOURCES[owner] or historical != git_bytes(
        root, BASE, owner
    ):
        raise SystemExit("Boolean LOS test transition differs from its exact reviewed sources.")
    return True


def _text(value: object) -> str:
    item = _object(value, {"sha256", "text"}, "fresh covered artifact")
    text = item["text"]
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != item["sha256"]:
        raise SystemExit("Fresh covered artifact digest differs.")
    return text


def fresh_native_role(
    root: Path,
    directory: Path,
    descriptor: dict[str, object],
    baseline: dict[str, object],
    previous: dict[str, object],
) -> tuple[float, dict[str, object]]:
    """Preserve the original Boolean-only transition and complete evidence checks."""
    from tools.performance_policy import runtime_inputs

    from scripts.complete_covered_evidence import verify_complete_covered_profile

    validate_transition(root)
    inputs = producer_inputs(root, str(baseline["source_head"]))
    validate_successor(inputs, runtime_inputs(root), read_json(root / SUCCESSOR_FILE))
    native_seconds = verify_complete_covered_profile(
        root,
        directory,
        descriptor["fresh_evidence"],
        baseline,
        inputs,
        cast(list[str], previous["cases"]),
        filename=FILENAME,
    )
    reference = _object(
        descriptor["fresh_evidence"], {"file", "sha256"}, "fresh evidence reference"
    )
    metadata = dict(previous)
    metadata.update(
        {
            "role": "Fresh combined native phases; historical standalone is inactive",
            "fresh_evidence": reference,
            "with_mirror_native_phase_seconds": native_seconds,
            "selected_current_context": "with_mirror",
            "standalone_role": "Historical only; forbidden for current allocation",
            "selection_rule": "Frozen combined allocation uses fresh with_mirror only",
            "historical_observations": previous["observations"],
            "fresh_source_head": baseline["source_head"],
            "fresh_runtime_fingerprint": RUNTIME,
        }
    )
    return native_seconds, metadata
