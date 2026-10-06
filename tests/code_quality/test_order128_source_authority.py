from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]


def test_order128_selected_blocks_and_original_source_archives_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order128/source.audit.json").read_bytes())
    assert audit["selected_source"]["row_id"] == "rule:03:03.02.02:1"
    assert [row["requirement_id"] for row in audit["requirements"]] == [
        "03.02.02-obligation-04",
        "03.02.02-obligation-09",
    ]
    assert [block["ordinal"] for block in audit["selected_literal_blocks"]] == [5, 9]
    for block in audit["selected_literal_blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
