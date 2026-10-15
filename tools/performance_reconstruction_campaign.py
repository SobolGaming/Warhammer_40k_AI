"""Admit both reviewed reconstruction pairs without pooling or relabeling runtime."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

BASE = "22a12094cfe3839d8fe8c5296ec0a7e7d32abade"
MEASURED = "1e70b261b30223f3a1b2e64ffd81593414eda2af"
TREE = "a96ee54373b24bc78642fa8987e7bd94aadb980b"
RUNTIME = (
    "warhammer40k-core-v2:runtime-tree-sha256-v1:"
    "65fc8414407ae5d6a8ea779c8e737a22733459094db679a160c60f6e2129f96a"
)
SCHEMA = "matched-reconstruction-abba-v1"
ARCHIVE = "docs/performance/policy-v3/manifest-reconstruction-20261015"
REPORT = "docs/performance/current/manifest-reconstruction-abba-20261015.json"
INVENTORY_SHA = "c1cae68810312f9b356f2606ee374dc187c5fcfb600593e71564a174d40ea3bd"
MEASURED_DIGEST = "6608cd744ddc59083b03f5a54060e691ce123a8b66c1d1dd85bd8e05b1c27592"
REPORT_DIGEST = "e7c453990b5957aa3c5481c4f06a0164f68cd119ca1845207bf0060ca923b399"
REVIEW_SHA = "3d654f11aebc117e776dcd2d1c93e1e92a0d7a468e2a10400f7035522f144e51"
CONTROL_INPUTS = frozenset(
    {
        "tools/performance_reconstruction_campaign.py",
        "tools/performance_policy.py",
        "tools/performance_tool_inputs_v2.py",
        "tools/performance_tool_inputs.py",
        "tests/code_quality/tool_input_history.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_performance_reconstruction_campaign.py",
        "tests/code_quality/test_runtime_manifest_reuse.py",
    }
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Reconstruction evidence requires an object.")
    typed = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in typed):
        raise ValueError("Reconstruction evidence requires string keys.")
    return cast(dict[str, object], typed)


def required(*, base: str, runtime_id: str, family: str) -> bool:
    return (base, runtime_id, family) == (BASE, RUNTIME, "reconstruction")


def verify_archive(root: Path) -> dict[str, str]:
    """Pin original raw reports, profiles, cleanup receipts and independent review."""
    archive = root / ARCHIVE
    if archive.is_symlink():
        raise ValueError("Reconstruction archive cannot be a symbolic link.")
    inventory = archive / "ARCHIVE_INVENTORY.json.txt"
    raw = inventory.read_bytes()
    if inventory.is_symlink() or hashlib.sha256(raw).hexdigest() != INVENTORY_SHA:
        raise ValueError("Reconstruction archive inventory drift.")
    files = _object(json.loads(raw))
    for name, digest in files.items():
        if Path(name).name != name or name in {".", ".."} or not isinstance(digest, str):
            raise ValueError("Invalid reconstruction archive member.")
        path = archive / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Original reconstruction artifact bytes changed: " + name)
    expected = set(files) | {"ARCHIVE_INVENTORY.json.txt", "applicability.json.txt"}
    if {path.name for path in archive.iterdir()} != expected:
        raise ValueError("Unexpected or missing reconstruction archive member.")
    inputs = _object(json.loads((archive / "measured-inputs.json.txt").read_bytes()))
    if not all(isinstance(value, str) for value in inputs.values()):
        raise ValueError("Measured reconstruction input inventory is malformed.")
    if _digest(inputs) != MEASURED_DIGEST:
        raise ValueError("Measured reconstruction input digest changed.")
    return cast(dict[str, str], inputs)


def retained_inputs(
    root: Path,
    *,
    current: dict[str, str],
    report: dict[str, object],
    base: str,
    runtime_id: str,
) -> tuple[dict[str, str], str]:
    """Require exact current hashes; only declared non-workload controls may differ."""
    if not required(base=base, runtime_id=runtime_id, family=str(report.get("family"))):
        raise ValueError("Reconstruction applicability belongs to another cohort.")
    if _digest(report) != REPORT_DIGEST:
        raise ValueError("Reviewed reconstruction report changed.")
    measured = verify_archive(root)
    path = root / ARCHIVE / "applicability.json.txt"
    raw = path.read_bytes()
    if path.is_symlink():
        raise ValueError("Reconstruction applicability cannot be a symbolic link.")
    proof = _object(json.loads(raw))
    expected = {
        "schema": "reconstruction-control-applicability-v1",
        "base": BASE,
        "measured_head": MEASURED,
        "measured_tree": TREE,
        "runtime_build_id": RUNTIME,
        "review_sha256": REVIEW_SHA,
        "report_canonical_sha256": REPORT_DIGEST,
        "measured_input_digest": MEASURED_DIGEST,
        "current_input_digest": _digest(current),
    }
    changes = {
        name: {"before": measured.get(name), "after": current.get(name)}
        for name in measured.keys() | current.keys()
        if measured.get(name) != current.get(name)
    }
    if not changes.keys() <= CONTROL_INPUTS or any(
        row["after"] is None for row in changes.values()
    ):
        raise ValueError("Unreviewed runtime, fixture, dependency, removal or control delta.")
    if proof != {**expected, "changes": changes}:
        raise ValueError("Reconstruction applicability is stale or incomplete.")
    return measured, hashlib.sha256(raw).hexdigest()


def validate_report(
    report: dict[str, object],
    *,
    base: str,
    runtime_id: str,
    input_digest: str,
    family: str,
    specification: dict[str, object],
    base_runtime_id: str,
    expected_inputs: dict[str, str],
    expected_binding: dict[str, object] | None,
    validate_single: Callable[..., list[dict[str, object]]],
) -> list[dict[str, object]]:
    """Both predetermined seven-sample comparisons must pass the original validator."""
    if not required(base=base, runtime_id=runtime_id, family=family):
        raise ValueError("Ordered reconstruction pairs cannot alter another comparison.")
    metadata = {
        "policy",
        "family",
        "workload_id",
        "base_revision",
        "head_runtime_build_id",
        "head_input_digest",
        "budget_profile",
        "historical_failures",
    }
    if report.keys() != metadata | {"schema", "measured_head", "measured_tree", "ordered_pairs"}:
        raise ValueError("Missing or unexpected reconstruction campaign fields.")
    if (report["schema"], report["measured_head"], report["measured_tree"]) != (
        SCHEMA,
        MEASURED,
        TREE,
    ):
        raise ValueError("Reconstruction campaign measurement identity drift.")
    if input_digest != MEASURED_DIGEST or report["historical_failures"] != []:
        raise ValueError("Reconstruction campaign cannot relabel inputs or waive a failed pair.")
    if expected_binding is not None or specification.get("samples_per_case") != 7:
        raise ValueError("Reconstruction campaign requires its original seven-sample workload.")
    pairs = report["ordered_pairs"]
    if not isinstance(pairs, list):
        raise ValueError("Both original reconstruction pairs are required.")
    typed_pairs = cast(list[object], pairs)
    if len(typed_pairs) != 2:
        raise ValueError("Both original reconstruction pairs are required.")
    for value, indices in zip(typed_pairs, ((0, 1), (3, 2)), strict=True):
        pair = _object(value)
        if (
            pair.keys() != {"base_index", "head_index", "base", "head"}
            or type(pair["base_index"]) is not int
            or type(pair["head_index"]) is not int
            or (pair["base_index"], pair["head_index"]) != indices
        ):
            raise ValueError("Reconstruction pairs were duplicated, reordered or selected.")
        single = {key: report[key] for key in metadata}
        single.update(base=pair["base"], head=pair["head"])
        failures = validate_single(
            single,
            base=base,
            runtime_id=runtime_id,
            input_digest=input_digest,
            family=family,
            specification=specification,
            base_runtime_id=base_runtime_id,
            expected_inputs=expected_inputs,
            expected_binding=None,
        )
        if failures:
            raise ValueError("Reconstruction campaign requires every original budget to pass.")
    return []
