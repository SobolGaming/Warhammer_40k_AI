"""Finite additive canonical circle selection; prior transition bytes retain their meaning."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)
from scripts.canonical_polygon_test_admission import ADDITION as POLYGON_ADDITION
from scripts.canonical_polygon_test_admission import ADDITION_SHA256 as POLYGON_SHA256
from scripts.milli_inch_test_admission import (
    ADDITION as FOUNDATION_ADDITION,
)
from scripts.milli_inch_test_admission import (
    ADDITION_SHA256 as FOUNDATION_SHA256,
)
from scripts.milli_inch_test_admission import (
    MANIFEST,
    RETAINED_CUTOVER_SHA256,
)
from scripts.milli_inch_test_admission import (
    SOURCE as FOUNDATION_SOURCE,
)
from scripts.milli_inch_test_admission import (
    SOURCE_SHA256 as FOUNDATION_SOURCE_SHA256,
)
from scripts.precision_profile_test_admission import ADDITION as PROFILE_ADDITION
from scripts.precision_profile_test_admission import ADDITION_SHA256 as PROFILE_SHA256
from scripts.symbolic_milli_inch_test_admission import ADDITION as SYMBOLIC_ADDITION
from scripts.symbolic_milli_inch_test_admission import ADDITION_SHA256 as SYMBOLIC_SHA256

ADDITION = "data/source_audits/ci64_provenance_v1/canonical-circle-test-transition-v1.json"
ADDITION_SHA256 = "a82643598fb01025704bd9d222643fce81e9f772d938a968f1b6568bd9542f19"
RUNTIME = "9155e14c9c2ebf6932f47fff50f573bb7ee02b6573d76779ae538bedc8f33137"
SOURCE = "src/warhammer40k_core/geometry/milli_inch_circle.py"
OWNER = "tests/rules/section01/test_milli_inch_circle.py"


def _checked_bytes(root: Path, name: str, digest: str) -> bytes:
    _selection_no_links(root, root / name)
    if not (root / name).is_file():
        raise SystemExit("Missing canonical circle test transition source: " + name)
    raw = (root / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit("Canonical circle test transition source bytes differ: " + name)
    return raw


def circle_test_transition(
    root: Path, retained_cutover_sha256: str
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], bytes] | None:
    """Admit one exact owner while retaining every predecessor source inventory."""
    for name in (ADDITION, MANIFEST, SOURCE, OWNER):
        _selection_no_links(root, root / name)
    manifest = (
        json.loads((root / MANIFEST).read_bytes(), object_pairs_hook=_selection_object)
        if (root / MANIFEST).is_file()
        else None
    )
    fingerprint = manifest.get("fingerprint") if isinstance(manifest, dict) else None
    if (
        not any((root / name).exists() for name in (ADDITION, SOURCE, OWNER))
        and fingerprint != RUNTIME
    ):
        return None
    if retained_cutover_sha256 != RETAINED_CUTOVER_SHA256 or fingerprint != RUNTIME:
        raise SystemExit(
            "Canonical circle test transition requires its retained cutover and runtime."
        )
    raw = _checked_bytes(root, ADDITION, ADDITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record
        != {
            "schema": "finite-canonical-circle-test-transition-v1",
            "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
            "retained_foundation_sha256": FOUNDATION_SHA256,
            "retained_profile_sha256": PROFILE_SHA256,
            "retained_symbolic_sha256": SYMBOLIC_SHA256,
            "retained_polygon_sha256": POLYGON_SHA256,
            "runtime_fingerprint": RUNTIME,
            "sources": record["sources"],
            "added_files": record["added_files"],
            "added_cases": record["added_cases"],
        }
        or set(record["added_files"]) != {OWNER}
        or set(record["sources"]) != {SOURCE}
    ):
        raise SystemExit("Canonical circle test transition membership differs.")
    for name, digest in record["sources"].items():
        _checked_bytes(root, name, digest)
    foundation_raw = _checked_bytes(root, FOUNDATION_ADDITION, FOUNDATION_SHA256)
    profile_raw = _checked_bytes(root, PROFILE_ADDITION, PROFILE_SHA256)
    _checked_bytes(root, FOUNDATION_SOURCE, FOUNDATION_SOURCE_SHA256)
    foundation = json.loads(foundation_raw, object_pairs_hook=_selection_object)
    profile = json.loads(profile_raw, object_pairs_hook=_selection_object)
    symbolic_raw = _checked_bytes(root, SYMBOLIC_ADDITION, SYMBOLIC_SHA256)
    symbolic = json.loads(symbolic_raw, object_pairs_hook=_selection_object)
    polygon_raw = _checked_bytes(root, POLYGON_ADDITION, POLYGON_SHA256)
    polygon = json.loads(polygon_raw, object_pairs_hook=_selection_object)
    for name, digest in polygon["sources"].items():
        _checked_bytes(root, name, digest)
    for name, digest in symbolic["sources"].items():
        _checked_bytes(root, name, digest)
    for name, digest in profile["sources"].items():
        _checked_bytes(root, name, digest)
    updated = _selection_members(profile["updated_files"], root)
    retained = _selection_members(foundation["added_files"], root)
    retained.update(_selection_members(profile["added_files"], root))
    retained.update(_selection_members(symbolic["added_files"], root))
    retained.update(_selection_members(polygon["added_files"], root))
    additions = _selection_members(record["added_files"], root)
    if additions.keys() & (updated.keys() | retained.keys()):
        raise SystemExit("Canonical circle test transition source memberships overlap.")
    return (
        updated,
        {**retained, **additions},
        foundation_raw
        + b"\0"
        + profile_raw
        + b"\0"
        + symbolic_raw
        + b"\0"
        + polygon_raw
        + b"\0"
        + raw,
    )
