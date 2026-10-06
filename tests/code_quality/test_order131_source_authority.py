from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.build_objective_movement_consumer import PATH, build
from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]


def test_selected_objective_source_and_archives_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order131/source.audit.json").read_bytes())
    assert audit["selected_source"]["row_id"] == "rule:01:01.04.03:1"
    assert [row["requirement_id"] for row in audit["requirements"]] == [
        "01.04.03-obligation-06",
    ]
    assert [block["ordinal"] for block in audit["selected_literal_blocks"]] == [3]
    for block in audit["selected_source"]["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    assert PATH.read_bytes() == (json.dumps(build(), ensure_ascii=False, indent=2) + "\n").encode()
