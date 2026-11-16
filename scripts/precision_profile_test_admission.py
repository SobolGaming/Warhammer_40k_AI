"""Finite test-source successor; retained cutover and foundation records stay unchanged."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)
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
    OWNER as FOUNDATION_OWNER,
)
from scripts.milli_inch_test_admission import (
    SOURCE as FOUNDATION_SOURCE,
)
from scripts.milli_inch_test_admission import (
    SOURCE_SHA256 as FOUNDATION_SOURCE_SHA256,
)

ADDITION = "data/source_audits/ci64_provenance_v1/precision-profile-test-transition-v1.json"
ADDITION_SHA256 = "020dcec99278aa79f2215762a525c0c029231cdb9c64f1e988d4a1719e0fbb74"
RUNTIME = "ae914a56833e43a3bbf086730b354c7a18673ccc15ca93e4b474347b95380f19"
SOURCE = "src/warhammer40k_core/adapters/numerical_policy.py"
OWNER = "tests/infrastructure/adapters/unit/test_numerical_policy.py"


def profile_test_transition(
    root: Path, retained_cutover_sha256: str
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], bytes] | None:
    """Bind exact replacements and additions without rewriting prior selection records."""
    for name in (
        ADDITION,
        MANIFEST,
        SOURCE,
        OWNER,
        FOUNDATION_ADDITION,
        FOUNDATION_SOURCE,
        FOUNDATION_OWNER,
    ):
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
            "Precision-profile test transition requires its retained cutover and runtime."
        )
    if not (root / ADDITION).is_file():
        raise SystemExit("Missing required precision-profile test transition.")
    raw = (root / ADDITION).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ADDITION_SHA256:
        raise SystemExit("Precision-profile test transition bytes differ from the reviewed record.")
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if record != {
        "schema": "finite-precision-profile-test-transition-v1",
        "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
        "retained_foundation_sha256": FOUNDATION_SHA256,
        "runtime_fingerprint": RUNTIME,
        "sources": record["sources"],
        "updated_files": record["updated_files"],
        "added_files": record["added_files"],
        "added_cases": record["added_cases"],
    } or set(record["added_files"]) != {OWNER}:
        raise SystemExit("Precision-profile test transition membership differs.")
    for name, digest in record["sources"].items():
        _selection_no_links(root, root / name)
        if (
            not (root / name).is_file()
            or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
        ):
            raise SystemExit("Precision-profile test transition source differs: " + name)
    if (
        not (root / FOUNDATION_ADDITION).is_file()
        or hashlib.sha256((root / FOUNDATION_ADDITION).read_bytes()).hexdigest()
        != FOUNDATION_SHA256
        or not (root / FOUNDATION_SOURCE).is_file()
        or hashlib.sha256((root / FOUNDATION_SOURCE).read_bytes()).hexdigest()
        != FOUNDATION_SOURCE_SHA256
    ):
        raise SystemExit("Precision-profile transition changed retained foundation bytes.")
    foundation_raw = (root / FOUNDATION_ADDITION).read_bytes()
    foundation = json.loads(foundation_raw, object_pairs_hook=_selection_object)
    retained = _selection_members(foundation["added_files"], root)
    updated = _selection_members(record["updated_files"], root)
    additions = _selection_members(record["added_files"], root)
    if updated.keys() & (retained.keys() | additions.keys()):
        raise SystemExit("Precision-profile test transition source memberships overlap.")
    return updated, {**retained, **additions}, foundation_raw + b"\0" + raw
