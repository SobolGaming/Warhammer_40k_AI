"""One finite additive test admission; the retained cutover stays byte-identical.

Historical snapshots without the precision foundation retain their own selection.
Any foundation marker requires the complete reviewed addition. This admits test
collection, not scheduling measurements, a runtime profile or passing validation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)

ADDITION = "data/source_audits/ci64_provenance_v1/milli-inch-test-addition-v1.json"
ADDITION_SHA256 = "9ebbf6d4cf39d25a60c78a4312e0a128c5b43b6c79c64ed91fa41e4387366e07"
RETAINED_CUTOVER_SHA256 = "4cd1f0b062fad661e1c71fe27d2e9f8279c3c21d2a9f7bea9e3b053db79afce3"
RUNTIME = "ff4277b5e1024958cc9f3e5464b5e26fc578c84b7a39130bece55d3ad0cf0add"
MANIFEST = "src/warhammer40k_core/_engine_build_manifest.json"
SOURCE = "src/warhammer40k_core/geometry/milli_inch.py"
SOURCE_SHA256 = "692a482b4be1b765ef351a249b928fdc156023086112b11266ba6b06ef8476c4"
OWNER = "tests/rules/section01/test_milli_inch.py"


def precision_test_addition(
    root: Path, retained_cutover_sha256: str
) -> tuple[dict[str, dict[str, object]], bytes] | None:
    """Require the exact source/runtime/test tuple when the addition is present."""
    for name in (ADDITION, MANIFEST, SOURCE, OWNER):
        _selection_no_links(root, root / name)
    manifest_path = root / MANIFEST
    manifest = (
        json.loads(manifest_path.read_bytes(), object_pairs_hook=_selection_object)
        if manifest_path.is_file()
        else None
    )
    fingerprint = manifest.get("fingerprint") if isinstance(manifest, dict) else None
    markers = any((root / name).exists() for name in (ADDITION, SOURCE, OWNER))
    if not markers and fingerprint != RUNTIME:
        return None
    if retained_cutover_sha256 != RETAINED_CUTOVER_SHA256:
        raise SystemExit("Precision test addition changed the retained cutover bytes.")
    if fingerprint != RUNTIME:
        raise SystemExit("Precision test addition requires its reviewed runtime fingerprint.")
    path = root / ADDITION
    if not path.is_file():
        raise SystemExit("Missing required precision test addition.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ADDITION_SHA256:
        raise SystemExit("Precision test addition bytes differ from the reviewed record.")
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if record != {
        "schema": "finite-milli-inch-test-addition-v1",
        "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
        "runtime_fingerprint": RUNTIME,
        "source": {"path": SOURCE, "sha256": SOURCE_SHA256},
        "added_files": record["added_files"],
        "added_cases": 25,
    } or set(record["added_files"]) != {OWNER}:
        raise SystemExit("Precision test addition membership differs from the reviewed record.")
    source_path = root / SOURCE
    if (
        not source_path.is_file()
        or hashlib.sha256(source_path.read_bytes()).hexdigest() != SOURCE_SHA256
    ):
        raise SystemExit("Precision test addition source differs from the reviewed module.")
    return _selection_members(record["added_files"], root), raw
