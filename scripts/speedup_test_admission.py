"""Finite speedup test-source transition; retained predecessor records stay intact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)
from scripts.exact_contact_test_admission import (
    ADDITION_SHA256 as EXACT_CONTACT_SHA256,
)
from scripts.exact_contact_test_admission import (
    RUNTIME,
    exact_contact_test_transition,
)
from scripts.milli_inch_test_admission import RETAINED_CUTOVER_SHA256

ADDITION = "data/source_audits/ci64_provenance_v1/speedup-test-transition-v1.json"
ADDITION_SHA256 = "42fab552f9d14cf7f17d45060c0f3363a840575948969e6e77d165f276801ed1"


def speedup_test_transition(
    root: Path, retained_cutover_sha256: str
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], bytes] | None:
    """Admit reviewed fixture/checkpoint speedups without altering historical snapshots."""
    target = root / ADDITION
    _selection_no_links(root, target)
    if not target.exists():
        return None
    base_transition = exact_contact_test_transition(root, retained_cutover_sha256)
    if base_transition is None:
        raise SystemExit(
            "Speedup test transition requires its exact-contact predecessor transition."
        )
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ADDITION_SHA256:
        raise SystemExit("Speedup test transition bytes differ from the reviewed record.")
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if record != {
        "schema": "finite-speedup-test-transition-v1",
        "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
        "retained_exact_contact_sha256": EXACT_CONTACT_SHA256,
        "runtime_fingerprint": RUNTIME,
        "updated_files": record.get("updated_files"),
    }:
        raise SystemExit("Speedup test transition membership or metadata differs.")
    prior_updated, retained_additions, prior_raw = base_transition
    speedup_updated = _selection_members(record["updated_files"], root)
    if speedup_updated.keys() & retained_additions.keys():
        raise SystemExit("Speedup test transition overlaps added-file memberships.")
    merged_updated = {**prior_updated, **speedup_updated}
    return merged_updated, retained_additions, prior_raw + b"\0" + raw
