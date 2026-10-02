"""Recognize one approved failed measurement; never widen its numerical budget."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

BASE = "133956de896c0db222158a086e672cc04649c096"
RUNTIME = (
    "warhammer40k-core-v2:runtime-tree-sha256-v1:"
    "81b436feba3835847aef40a9d90e94ad5ced81c6a62cc445583b7ace2f10247e"
)
MEASURED_DIGEST = "03f49ddff44dbaa9f6025082829b520ba8174c912cf301634ce7cc33a2652306"
APPROVAL = "docs/performance/policy-v3/order103-owner-exception.json"
APPROVAL_SHA256 = "9e617d3a728aaaea6998c26ab0e09ed21e6af6ceafd86444332a06b168e3e9cd"
APPLICABILITY = "docs/performance/policy-v3/order103-exception-applicability.json"
RECOGNITION = {
    "id": "order103-sustained-shooting-mean-20261002",
    "case": "shooting/true",
    "metric": "mean",
    "status": "owner_approved_failure",
}
COHORT_FINGERPRINTS = {
    "precision_grouping": "4c23574a7bc7d0126a23bf2987c1eee2b381542281798353cbc30cc2894829fa",
    "dice": "366dca90b1c40274ea6b14453a542d0064d90daafba591a446c4f04216dd590b",
    "dice_sustained": "79d6d9b8916db749e3b6eec3ea7688b39c465dbbd1afdbc395581d40fead06fa",
}
RECOGNITION_INPUTS = frozenset(
    {
        "tools/performance_policy.py",
        "tools/performance_order103_exception.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_performance_order103_exception.py",
    }
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Order103 recognition requires a JSON object.")
    return cast(dict[str, object], value)


def _approval(root: Path) -> None:
    if hashlib.sha256((root / APPROVAL).read_bytes()).hexdigest() != APPROVAL_SHA256:
        raise ValueError("Order103 owner approval is missing or changed.")


def _original_report(report: dict[str, object]) -> dict[str, object]:
    original = dict(report)
    original.pop("owner_exception", None)
    family = original.get("family")
    if (
        not isinstance(family, str)
        or family not in COHORT_FINGERPRINTS
        or _digest(original) != COHORT_FINGERPRINTS[family]
    ):
        raise ValueError("Order103 recognition does not match the original measured report.")
    return original


def validate_owner_recognition(report: dict[str, object]) -> bool:
    """Only an explicit marker on the exact approved failed report is recognized."""
    if "owner_exception" not in report:
        return False
    if report["owner_exception"] != RECOGNITION or report.get("family") != "dice_sustained":
        raise ValueError("Unrecognized owner performance exception.")
    _approval(Path(__file__).resolve().parents[1])
    _original_report(report)
    return True


def retained_comparison_inputs(
    root: Path,
    *,
    current: dict[str, str],
    report: dict[str, object],
    base: str,
    runtime_id: str,
) -> tuple[dict[str, str], str | None]:
    """Authenticate this cohort's four governance edits without excluding inputs."""
    if report.get("head_input_digest") == _digest(current):
        return current, None
    if (base, runtime_id, report.get("head_input_digest")) != (BASE, RUNTIME, MEASURED_DIGEST):
        raise ValueError("Current comparison has stale or unrelated input identities.")
    _approval(root)
    _original_report(report)
    raw = (root / APPLICABILITY).read_bytes()
    proof = _object(json.loads(raw))
    if proof.keys() != {
        "schema",
        "base",
        "runtime_build_id",
        "approval_sha256",
        "measured_input_digest",
        "measured_inputs",
        "current_input_digest",
        "changes",
    }:
        raise ValueError("Unexpected Order103 applicability fields.")
    if (
        proof["schema"],
        proof["base"],
        proof["runtime_build_id"],
        proof["approval_sha256"],
        proof["measured_input_digest"],
        proof["current_input_digest"],
    ) != (
        "order103-governance-applicability-v1",
        BASE,
        RUNTIME,
        APPROVAL_SHA256,
        MEASURED_DIGEST,
        _digest(current),
    ):
        raise ValueError("Order103 applicability identity drift.")
    measured = _object(proof["measured_inputs"])
    if (
        not all(isinstance(value, str) for value in measured.values())
        or _digest(measured) != MEASURED_DIGEST
    ):
        raise ValueError("Order103 measured input inventory drift.")
    changes = {
        path: {"before": measured.get(path), "after": current.get(path)}
        for path in measured.keys() | current.keys()
        if measured.get(path) != current.get(path)
    }
    if changes.keys() != RECOGNITION_INPUTS or changes != proof["changes"]:
        raise ValueError("Order103 applicability contains an unapproved or stale input delta.")
    # Current inputs came from the complete tracked/nonignored inventory. All
    # engine, benchmark, fixture and lock bytes therefore remain exact; the
    # checker script is explicitly bridged, never globally omitted.
    return cast(dict[str, str], measured), hashlib.sha256(raw).hexdigest()
