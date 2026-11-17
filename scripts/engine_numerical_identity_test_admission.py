"""Finite additive polygon query selection; prior transition bytes retain their meaning."""

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
ADDITION_SHA256 = "518f0e1f92177fe2fe0f218fcecdacac7445cb500fa22942e28c89351af54912"
RUNTIME = "db8c8f733112410866770bcd2d3231a9e2a348e2de0514f5fc0b5ffe95b7b9cd"
COORDINATES = "src/warhammer40k_core/geometry/numerical_identity.py"
QUERIES = "src/warhammer40k_core/geometry/milli_inch_polygon_queries.py"
QUERIES_SHA256 = "e46fe8e9738786931c565c5ea5a2dc2921132e3690b420632bfcb8a00c362cc5"
SOURCE = "src/warhammer40k_core/engine/numerical_identity.py"
OWNER = "tests/rules/section01/test_engine_numerical_identity.py"


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
            "Numerical identity test transition requires its retained cutover and runtime."
        )
    # Retained cutover-only CLI probes do not activate this runtime profile.
    # Import its full evidence validators only after exact current-profile admission.
    from scripts.engine_numerical_identity_shard_admission import (
        SOURCE_HASHES,
        UPDATED_TEST_HASHES,
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
            "updated_files": record["updated_files"],
        }
        or set(record["added_files"]) != {OWNER}
        or record["sources"] != SOURCE_HASHES
        or set(record["updated_files"]) != set(UPDATED_TEST_HASHES)
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
        _checked_bytes(root, name, SOURCE_HASHES.get(name, digest))
    current_updated = _selection_members(record["updated_files"], root)
    updated = _selection_members(profile["updated_files"], root, current=current_updated)
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
        + raw,
    )
