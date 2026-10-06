"""Preserve selected source authority and the explicit open certification boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_order134_source_and_historical_pins_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order134/source.audit.json").read_bytes())
    selected = audit["selected_source"]
    assert selected["row_id"] == "rule:03:03.02.02:1"
    assert selected["source_sha256"] == (
        "910af631243255d6f41c6eb1c64fabad2de8e7999528fbcf837883fcce10d169"
    )
    assert len(selected["blocks"]) == 10
    for block in selected["blocks"]:
        raw = json.dumps(block["value"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        assert hashlib.sha256(raw.encode()).hexdigest() == block["sha256"]
    assert {row["requirement_id"] for row in audit["requirements"]} == {
        "03.02.02-obligation-02",
        "03.02.02-obligation-03",
    }
    assert audit["gameplay_certification"].startswith("OPEN:")
    assert audit["scope_revision_authorization"]["user_answer"] == (
        "yes, implement and test the conditional restriction now"
    )
    for path, expected in audit["pinned_canonical_bytes_sha256"].items():
        actual = audit["preserved_input_mapping"].get(path, path)
        assert hashlib.sha256((ROOT / actual).read_bytes()).hexdigest() == expected
