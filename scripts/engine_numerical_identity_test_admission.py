"""Finite numerical-identity source admission over the retained speedup transition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)
from scripts.canonical_circle_test_admission import ADDITION as CIRCLE_ADDITION
from scripts.canonical_circle_test_admission import ADDITION_SHA256 as CIRCLE_SHA256
from scripts.canonical_polygon_pairs_test_admission import ADDITION as PAIRS_ADDITION
from scripts.canonical_polygon_pairs_test_admission import ADDITION_SHA256 as PAIRS_ADDITION_SHA256
from scripts.canonical_polygon_queries_test_admission import ADDITION as QUERIES_ADDITION
from scripts.canonical_polygon_queries_test_admission import (
    ADDITION_SHA256 as QUERIES_ADDITION_SHA256,
)
from scripts.canonical_polygon_test_admission import ADDITION as POLYGON_ADDITION
from scripts.canonical_polygon_test_admission import ADDITION_SHA256 as POLYGON_SHA256
from scripts.exact_contact_test_admission import ADDITION as CONTACT_ADDITION
from scripts.exact_contact_test_admission import ADDITION_SHA256 as CONTACT_ADDITION_SHA256
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

ADDITION = "data/source_audits/ci64_provenance_v1/engine-numerical-identity-test-transition-v1.json"
ADDITION_SHA256 = "4ab08b326285715c00a3bd10aabca1f6572da4fdfa55958309a2e2a215668bb8"
RUNTIME = "d60a6871e475632bdf930a80251f39e7bae5b5f40c35960b6ed1790750f62fa0"
COORDINATES = "src/warhammer40k_core/geometry/numerical_identity.py"
QUERIES = "src/warhammer40k_core/geometry/milli_inch_polygon_queries.py"
QUERIES_SHA256 = "e46fe8e9738786931c565c5ea5a2dc2921132e3690b420632bfcb8a00c362cc5"
SOURCE = "src/warhammer40k_core/engine/numerical_identity.py"
OWNER = "tests/rules/section01/test_engine_numerical_identity.py"
EXACT_MOVEMENT_ADDITION = (
    "data/source_audits/ci64_provenance_v1/exact-movement-test-transition-v1.json"
)
EXACT_MOVEMENT_SHA256 = "ada2ae25f047f949b9faf3b2c33d7cc590b4c6bc9f22911dc8acb8b5ec5e4b2b"
EXACT_MOVEMENT_OWNER = "tests/rules/section01/test_exact_movement.py"
_EXACT_MOVEMENT_SOURCES = (
    "src/warhammer40k_core/engine/exact_movement.py",
    "src/warhammer40k_core/geometry/exact_path.py",
    "src/warhammer40k_core/geometry/exact_pose.py",
)
CIRCLE_POLYGON_ADDITION = (
    "data/source_audits/ci64_provenance_v1/circle-polygon-test-addition-v1.json"
)
CIRCLE_POLYGON_SHA256 = "617f67340b0d7e5cd8f1d2786faa193a96bbc7f2fa18f3b8b7988bc263458a91"
CIRCLE_POLYGON_OWNER = "tests/rules/section01/test_milli_inch_circle_polygon.py"
_CIRCLE_POLYGON_SOURCE = "src/warhammer40k_core/geometry/milli_inch_circle_polygon.py"

OVAL_POINT_ADDITION = "data/source_audits/ci64_provenance_v1/oval-point-test-addition-v1.json"
OVAL_POINT_SHA256 = "c90a008c3d213364cfa9085b27d864b301543b7a35dabb94175870cb1c42cbd9"
OVAL_POINT_OWNER = "tests/rules/section01/test_milli_inch_oval.py"
_OVAL_POINT_SOURCE = "src/warhammer40k_core/geometry/milli_inch_oval.py"


type TestTransition = tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], bytes]


def _checked_bytes(root: Path, name: str, digest: str) -> bytes:
    _selection_no_links(root, root / name)
    if not (root / name).is_file():
        raise SystemExit("Missing numerical identity test transition source: " + name)
    raw = (root / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit("Numerical identity test transition source bytes differ: " + name)
    return raw


def engine_numerical_identity_test_transition(
    root: Path, retained_cutover_sha256: str
) -> TestTransition | None:
    """Admit one exact owner while retaining every predecessor source inventory."""
    return _identity_test_transition(root, retained_cutover_sha256, runtime=RUNTIME)


def exact_movement_test_transition(
    root: Path, retained_cutover_sha256: str
) -> TestTransition | None:
    """Admit the flat-disk movement cases without modifying predecessor evidence."""
    paths = (EXACT_MOVEMENT_ADDITION, EXACT_MOVEMENT_OWNER, *_EXACT_MOVEMENT_SOURCES)
    for path in paths:
        _selection_no_links(root, root / path)
    successor_paths = (CIRCLE_POLYGON_ADDITION, CIRCLE_POLYGON_OWNER, _CIRCLE_POLYGON_SOURCE)
    for path in successor_paths:
        _selection_no_links(root, root / path)
    has_circle_polygon = any((root / path).exists() for path in successor_paths)
    oval_paths = (OVAL_POINT_ADDITION, OVAL_POINT_OWNER, _OVAL_POINT_SOURCE)
    for path in oval_paths:
        _selection_no_links(root, root / path)
    has_oval_point = any((root / path).exists() for path in oval_paths)
    if has_oval_point and not has_circle_polygon:
        raise SystemExit("Oval point test addition requires its circle-polygon predecessor.")
    if not has_circle_polygon and not any((root / path).exists() for path in paths):
        return None
    raw = _checked_bytes(root, EXACT_MOVEMENT_ADDITION, EXACT_MOVEMENT_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {"schema", "retained_identity_sha256", "runtime_fingerprint", "sources", "added_files"}
        or record["schema"] != "finite-exact-movement-test-transition-v1"
        or record["retained_identity_sha256"] != ADDITION_SHA256
        or set(record["sources"]) != set(_EXACT_MOVEMENT_SOURCES)
        or set(record["added_files"]) != {EXACT_MOVEMENT_OWNER}
    ):
        raise SystemExit("Exact movement test transition membership differs.")
    for name, digest in record["sources"].items():
        _checked_bytes(root, name, digest)
    runtime = record["runtime_fingerprint"]
    additions = _selection_members(record["added_files"], root)
    if has_circle_polygon:
        next_raw = _checked_bytes(root, CIRCLE_POLYGON_ADDITION, CIRCLE_POLYGON_SHA256)
        successor = json.loads(next_raw, object_pairs_hook=_selection_object)
        if (
            successor.keys() != {"schema", "runtime_fingerprint", "source_sha256", "added_files"}
            or successor["schema"] != "finite-circle-polygon-test-addition-v1"
            or set(successor["added_files"]) != {CIRCLE_POLYGON_OWNER}
        ):
            raise SystemExit("Circle-polygon test addition membership differs.")
        _checked_bytes(root, _CIRCLE_POLYGON_SOURCE, successor["source_sha256"])
        additions.update(_selection_members(successor["added_files"], root))
        runtime = successor["runtime_fingerprint"]
        raw += b"\0" + next_raw
    if has_oval_point:
        oval_raw = _checked_bytes(root, OVAL_POINT_ADDITION, OVAL_POINT_SHA256)
        oval = json.loads(oval_raw, object_pairs_hook=_selection_object)
        if (
            oval.keys() != {"schema", "runtime_fingerprint", "source_sha256", "added_files"}
            or oval["schema"] != "finite-oval-point-test-addition-v1"
            or set(oval["added_files"]) != {OVAL_POINT_OWNER}
        ):
            raise SystemExit("Oval point test addition membership differs.")
        _checked_bytes(root, _OVAL_POINT_SOURCE, oval["source_sha256"])
        additions.update(_selection_members(oval["added_files"], root))
        runtime = oval["runtime_fingerprint"]
        raw += b"\0" + oval_raw
    retained = _identity_test_transition(root, retained_cutover_sha256, runtime=runtime)
    if retained is None:
        raise SystemExit(
            "Exact movement test transition requires the numerical identity predecessor."
        )
    updated, added, retained_raw = retained
    if additions.keys() & (updated.keys() | added.keys()):
        raise SystemExit("Exact movement test cases overlap the predecessor selection.")
    return updated, {**added, **additions}, retained_raw + b"\0" + raw


def _identity_test_transition(
    root: Path, retained_cutover_sha256: str, *, runtime: str
) -> TestTransition | None:
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
        and fingerprint != runtime
    ):
        return None
    if retained_cutover_sha256 != RETAINED_CUTOVER_SHA256 or fingerprint != runtime:
        raise SystemExit(
            "Numerical identity test transition requires its retained cutover and runtime."
        )
    raw = _checked_bytes(root, ADDITION, ADDITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record
        != {
            "schema": "finite-engine-numerical-identity-test-transition-v1",
            "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
            "retained_foundation_sha256": FOUNDATION_SHA256,
            "retained_profile_sha256": PROFILE_SHA256,
            "retained_symbolic_sha256": SYMBOLIC_SHA256,
            "retained_polygon_sha256": POLYGON_SHA256,
            "retained_circle_sha256": CIRCLE_SHA256,
            "retained_queries_sha256": QUERIES_ADDITION_SHA256,
            "retained_pairs_sha256": PAIRS_ADDITION_SHA256,
            "retained_contact_sha256": CONTACT_ADDITION_SHA256,
            "runtime_fingerprint": RUNTIME,
            "sources": record["sources"],
            "added_files": record["added_files"],
            "added_cases": record["added_cases"],
            "case_id_successors": record["case_id_successors"],
            "updated_files": record["updated_files"],
        }
        or set(record["added_files"]) != {OWNER}
        or set(record["updated_files"])
        != {
            "tests/rules/section18/test_facade.py",
            "tests/infrastructure/adapters/unit/test_linux_authority.py",
            "tests/infrastructure/adapters/test_canonical_deployment_coverage.py",
        }
    ):
        raise SystemExit("Numerical identity test transition membership differs.")
    for name, digest in record["sources"].items():
        _checked_bytes(root, name, digest)
    contact_raw = _checked_bytes(root, CONTACT_ADDITION, CONTACT_ADDITION_SHA256)
    contact = json.loads(contact_raw, object_pairs_hook=_selection_object)
    for name, digest in contact["sources"].items():
        _checked_bytes(root, name, digest)
    pairs_raw = _checked_bytes(root, PAIRS_ADDITION, PAIRS_ADDITION_SHA256)
    pairs = json.loads(pairs_raw, object_pairs_hook=_selection_object)
    for name, digest in pairs["sources"].items():
        _checked_bytes(root, name, digest)
    queries_raw = _checked_bytes(root, QUERIES_ADDITION, QUERIES_ADDITION_SHA256)
    queries = json.loads(queries_raw, object_pairs_hook=_selection_object)
    # The hash-pinned original transition retains its original point-query source.
    # Only this successor admits the exact private annotation change.
    if pairs["sources"][QUERIES] != QUERIES_SHA256:
        raise SystemExit("Unreviewed point-query internal annotation successor.")
    foundation_raw = _checked_bytes(root, FOUNDATION_ADDITION, FOUNDATION_SHA256)
    profile_raw = _checked_bytes(root, PROFILE_ADDITION, PROFILE_SHA256)
    _checked_bytes(root, FOUNDATION_SOURCE, FOUNDATION_SOURCE_SHA256)
    foundation = json.loads(foundation_raw, object_pairs_hook=_selection_object)
    profile = json.loads(profile_raw, object_pairs_hook=_selection_object)
    symbolic_raw = _checked_bytes(root, SYMBOLIC_ADDITION, SYMBOLIC_SHA256)
    symbolic = json.loads(symbolic_raw, object_pairs_hook=_selection_object)
    polygon_raw = _checked_bytes(root, POLYGON_ADDITION, POLYGON_SHA256)
    polygon = json.loads(polygon_raw, object_pairs_hook=_selection_object)
    circle_raw = _checked_bytes(root, CIRCLE_ADDITION, CIRCLE_SHA256)
    circle = json.loads(circle_raw, object_pairs_hook=_selection_object)
    for name, digest in circle["sources"].items():
        _checked_bytes(root, name, digest)
    for name, digest in polygon["sources"].items():
        _checked_bytes(root, name, digest)
    for name, digest in symbolic["sources"].items():
        _checked_bytes(root, name, digest)
    for name, digest in profile["sources"].items():
        _checked_bytes(root, name, record["sources"].get(name, digest))
    current_updated = _selection_members(record["updated_files"], root)
    updated = _selection_members(profile["updated_files"], root, current=current_updated)
    from scripts.speedup_test_admission import ADDITION as SPEEDUP_ADDITION
    from scripts.speedup_test_admission import ADDITION_SHA256 as SPEEDUP_SHA256

    speedup_raw = _checked_bytes(root, SPEEDUP_ADDITION, SPEEDUP_SHA256)
    speedup = json.loads(speedup_raw, object_pairs_hook=_selection_object)
    if speedup != {
        "schema": "finite-speedup-test-transition-v1",
        "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
        "retained_exact_contact_sha256": CONTACT_ADDITION_SHA256,
        "runtime_fingerprint": contact["runtime_fingerprint"],
        "updated_files": speedup["updated_files"],
    }:
        raise SystemExit("Numerical identity predecessor speedup metadata differs.")
    updated.update(_selection_members(speedup["updated_files"], root, current=current_updated))
    updated.update(current_updated)
    retained = _selection_members(foundation["added_files"], root)
    retained.update(_selection_members(profile["added_files"], root))
    retained.update(_selection_members(symbolic["added_files"], root))
    retained.update(_selection_members(polygon["added_files"], root))
    retained.update(_selection_members(circle["added_files"], root))
    retained.update(_selection_members(queries["added_files"], root))
    retained.update(_selection_members(pairs["added_files"], root))
    retained.update(_selection_members(contact["added_files"], root))
    additions = _selection_members(record["added_files"], root)
    if additions.keys() & (updated.keys() | retained.keys()):
        raise SystemExit("Numerical identity test transition source memberships overlap.")
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
        + circle_raw
        + b"\0"
        + queries_raw
        + b"\0"
        + pairs_raw
        + b"\0"
        + contact_raw
        + b"\0"
        + speedup_raw
        + b"\0"
        + raw,
    )
