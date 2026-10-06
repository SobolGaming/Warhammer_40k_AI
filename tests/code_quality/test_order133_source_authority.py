from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "data/source_audits/order133/source.audit.json"


def test_selected_number_source_and_original_evidence_remain_exact() -> None:
    audit = json.loads(AUDIT.read_bytes())
    assert audit["selected_source"]["row_id"] == "rule:02:02.05.01:1"
    assert audit["selected_source"]["source_sha256"] == (
        "48df8363e95ed138f1cf0af5f99b0cf159fc9a66d8141bae3c5e87ac2ad899ef"
    )
    assert [row["requirement_id"] for row in audit["requirements"]] == ["02.05.01-obligation-12"]
    assert [block["ordinal"] for block in audit["selected_literal_blocks"]] == [11]
    assert len(audit["selected_source"]["blocks"]) == 11
    for block in audit["selected_source"]["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def test_declared_number_vocabulary_provenance_matches_literal_runtime_table() -> None:
    audit = json.loads(AUDIT.read_bytes())
    module = ast.parse((ROOT / "src/warhammer40k_core/core/keyword_numbers.py").read_text())
    table = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_NUMBER_ALIASES"
            for target in node.targets
        )
    )
    records = audit["declared_number_identities"]
    assert {row["alias"]: row["canonical"] for row in records} == table
    assert table["BEASTS"] == "BEAST"
    assert "CRUSADER" not in table
    assert "CRUSADERS" not in table
    rows = json.loads(
        (
            ROOT
            / (
                "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_keywords.json"
            )
        ).read_bytes()
    )["rows"]
    observed = Counter(row["fields"]["keyword"].upper() for row in rows)
    for record in records:
        assert record["observed_alias_rows"] == observed[record["alias"]]
        assert record["observed_canonical_rows"] == observed[record["canonical"]]
        assert record["canonical_authority"]
        assert record["alias_authority"]


def test_number_identity_is_shared_at_source_and_catalog_owners() -> None:
    owners = {
        "core/datasheet_identity.py": "keyword_number_identity",
        "core/model_keywords.py": "keyword_number_identity",
        "core/keyword_membership.py": "keyword_number_identity",
        "engine/army_mustering.py": "keyword_number_identity",
        "rules/rule_token_normalization.py": "keyword_number_identity",
        "rules/rule_keyword_sequences.py": "keyword_number_spellings",
    }
    for relative, symbol in owners.items():
        module = ast.parse((ROOT / "src/warhammer40k_core" / relative).read_text())
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "warhammer40k_core.core.keyword_numbers"
            and symbol in {alias.name for alias in node.names}
            for node in module.body
        ), relative
    selected = (ROOT / "src/warhammer40k_core/rules/selected_target_parser.py").read_text()
    assert "keyword_sequence_parameter_pairs(" in selected
    assert "def _longest_source_keyword_prefix" not in selected
