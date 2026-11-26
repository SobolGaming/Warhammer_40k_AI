"""Byte-bound admission of the Stage 3 ranged profile regression."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)

RECEIPT = "data/source_audits/ci64_provenance_v1/stage3-ranged-profile-test-v1.json"
RECEIPT_SHA256 = "9060d2c1d4f148890cb33154dedb60908bb7f4eaf9350c3b8932b974f63bce92"
BASE = "098847346d8f554323a6417ede02a06eaa2613d6"
SOURCE = "src/warhammer40k_core/ai/ordinary_ranged_profile_policy.py"
OWNER = "tests/infrastructure/adapters/test_ordinary_ranged_profile_policy.py"


class RangedProfileTestAdmission(TypedDict):
    base: str
    retained_counteroffensive_sha256: str
    retained_manifest_sha256: str
    retained_runtime_fingerprint: str
    manifest_sha256: str
    runtime_fingerprint: str
    source_sha256: str
    added_files: dict[str, dict[str, object]]


def ranged_profile_test_addition(
    root: Path,
) -> tuple[RangedProfileTestAdmission, dict[str, dict[str, object]], bytes] | None:
    from scripts.engine_numerical_identity_test_admission import _checked_bytes

    paths = (RECEIPT, SOURCE, OWNER)
    for name in paths:
        _selection_no_links(root, root / name)
    if not any((root / name).exists() for name in paths):
        return None
    raw = _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    record = cast(RangedProfileTestAdmission, json.loads(raw, object_pairs_hook=_selection_object))
    if (
        record.keys() != RangedProfileTestAdmission.__required_keys__
        or record["base"] != BASE
        or record["added_files"].keys() != {OWNER}
    ):
        raise SystemExit("Ranged profile policy test addition inventory differs.")
    _checked_bytes(root, SOURCE, record["source_sha256"])
    return record, _selection_members(record["added_files"], root), raw
