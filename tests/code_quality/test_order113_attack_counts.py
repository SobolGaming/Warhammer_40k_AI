"""Source and shared-owner audit for the bounded Blast/Cleave count repair."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]


def test_order113_pinned_selected_clauses_keep_literal_hashes() -> None:
    rows = json.loads(
        (ROOT / "data/source_audits/order97/selected-sources.json").read_text(encoding="utf-8")
    )
    by_id = {row["row_id"]: row for row in rows}
    expected = {
        "rule:24:24.05:1": (
            "0769f92c46c103e89c71fec090feaadc1dacb07e70c4d3c935b03c0bd2c71cb6",
            (
                "61214fbb343e699625f5145f1745e3c09519a804ee3d265a3d52078d0438aaa6",
                "ffd5e93f1dd55f008ed3a7893d83d6707b1f1c7b13fd799ab9c530fde9f16e70",
                "b86450e5848426479e3f35843496649303d4e524180851aaa82a8dc7968a280e",
            ),
        ),
        "rule:24:24.06:1": (
            "d030ed1f70e3e30f848b22c8a38f552906392d88838d8eeca88385d67c0f0bcc",
            (
                "dbca1b5f9130938d9deb8e6ff9931006d425cec3ccaa294cae44f02458e50038",
                "d308825a5a98b8550601053622a521bb4bcb4b7e93e6d933f98cd00bb7fd2fe7",
            ),
        ),
    }
    for row_id, (source_hash, block_hashes) in expected.items():
        row = by_id[row_id]
        assert row["source_sha256"] == source_hash
        assert tuple(block["sha256"] for block in row["blocks"]) == block_hashes
        for block in row["blocks"]:
            assert fingerprint(block["value"]) == block["sha256"]


def test_order113_shared_consumers_do_not_fix_blast_x_to_one() -> None:
    package = ROOT / "src/warhammer40k_core"
    tree = ast.parse(
        (package / "engine/phases/shooting_declaration_validation.py").read_text(encoding="utf-8")
    )
    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "blast_attack_bonus_for_profile" in calls
    assert "blast_attack_bonus" not in calls
    abilities = ast.parse((package / "engine/weapon_abilities.py").read_text(encoding="utf-8"))
    for name in ("blast_attack_bonus", "cleave_attack_bonus"):
        owner = next(
            node
            for node in abilities.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_attack_bonus_per_five"
            for node in ast.walk(owner)
        )
