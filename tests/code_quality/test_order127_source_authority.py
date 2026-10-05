"""Order127 retains immutable source and diagnostic identities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]


def test_order127_selected_obligation_and_original_pins_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order127/source.audit.json").read_bytes())
    assert audit["requirement_id"] == "03.02.03-obligation-03"
    assert audit["selected_source"]["row_id"] == "rule:03:03.02.03:1"
    assert audit["selected_block"]["ordinal"] == 1
    assert fingerprint(audit["selected_block"]["value"]) == audit["selected_block"]["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
