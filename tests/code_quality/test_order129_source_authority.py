from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]


def test_order129_selected_faq_and_original_source_archives_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order129/source.audit.json").read_bytes())
    assert audit["selected_source"]["row_id"] == "faq:e5941469-5653-49b2-919e-9c9246e811d4"
    assert [row["requirement_id"] for row in audit["requirements"]] == [
        "faq-e5941469-5653-49b2-919e-9c9246e811d4-obligation-01",
    ]
    assert [block["ordinal"] for block in audit["selected_literal_blocks"]] == [2]
    assert audit["selected_literal_blocks"][0]["value"] == "No"
    for block in audit["selected_source"]["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
