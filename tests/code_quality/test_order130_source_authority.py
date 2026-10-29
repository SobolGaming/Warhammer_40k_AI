from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint
from tools.core_rules_order97_history import historical_evidence_path

ROOT = Path(__file__).resolve().parents[2]


def test_order130_selected_faq_and_original_source_archives_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order130/source.audit.json").read_bytes())
    assert audit["selected_source"]["row_id"] == "faq:904b8b36-09f0-4449-a9c3-45892664ef60"
    assert [row["requirement_id"] for row in audit["requirements"]] == [
        "faq-904b8b36-09f0-4449-a9c3-45892664ef60-obligation-01",
    ]
    assert [block["ordinal"] for block in audit["selected_literal_blocks"]] == [2]
    assert audit["selected_literal_blocks"][0]["value"] == "Yes."
    for block in audit["selected_source"]["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        historical = historical_evidence_path(name, root=ROOT)
        path = ROOT / name if historical is None else historical
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_coherency_casualties_use_shared_owner_decisions_and_group_geometry() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    cleanup = (engine / "turn_cleanup.py").read_text(encoding="utf-8")
    decision = (engine / "coherency_cleanup_decisions.py").read_text(encoding="utf-8")
    lifecycle = (engine / "lifecycle.py").read_text(encoding="utf-8")
    assert "_next_cleanup_model_id" not in cleanup
    assert "rules_unit_coherency_result(" in cleanup
    assert "rules_unit_coherency_result(" in decision
    assert "result.model_instance_ids" in decision
    assert "record not in decisions.records" in decision
    assert "destroy_end_turn_coherency_models(state=state, cleanup=cleanup)" in decision
    assert "*_coherency_cleanup.decision_dispatch_handlers(self)" in lifecycle
    assert "_coherency_cleanup.validate_restored_coherency_choices(" in lifecycle
