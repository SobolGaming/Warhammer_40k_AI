from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint
from tools.core_rules_order97_history import historical_evidence_path

ROOT = Path(__file__).resolve().parents[2]


def test_selected_disembark_source_and_original_evidence_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order132/source.audit.json").read_bytes())
    assert audit["selected_source"]["row_id"] == "rule:18:18.04:1"
    assert (
        audit["selected_source"]["source_sha256"]
        == "ed5ace0412d4f87e7f436e64eb56f5081325cbc6b3c0a1dda347562c890144b9"
    )
    assert [row["requirement_id"] for row in audit["requirements"]] == [
        "18.04-rapid-tactical-distance"
    ]
    assert [block["ordinal"] for block in audit["selected_literal_blocks"]] == [7, 15]
    for block in audit["selected_source"]["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        historical = historical_evidence_path(name, root=ROOT)
        path = ROOT / name if historical is None else historical
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
