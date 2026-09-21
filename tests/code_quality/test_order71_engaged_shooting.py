"""Keep engaged shooting model scopes, independent sources and costs auditable."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


def test_order71_source_artifact_and_existing_close_quarters_observation() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_actions_2026_09 as close,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_engaged_shooting_2026_09 as target,
    )

    subprocess.run(
        [sys.executable, "tools/build_core_engaged_shooting_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert target.source_package().source_catalog.documents
    row = target.source_rules()[0]
    assert row.section_id == "17.03"
    assert row.load_support_status == "loaded"
    assert row.semantic_execution_status == "executable_engine_runtime"
    existing = next(row for row in close.source_rules() if row.section_id == "10.06")
    assert existing.transcription_sha256 == (
        "c44508145d53b35217bab6049826848d84569409feb52ab41e3644aa94f6dc78"
    )


def test_order71_independent_sources_and_canonical_model_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for file in engine.rglob("*.py"):
        assert "big_guns_never_tire" not in file.read_text(encoding="utf-8")
    for name in ("shooting_targets.py", "shooting_engagement.py"):
        tree = ast.parse((engine / name).read_text(encoding="utf-8"))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in {"lower", "upper", "casefold", "source_text"}
        ]
    source = (engine / "shooting_targets.py").read_text(encoding="utf-8")
    assert "attacker_model_keywords=attacker_model.keywords" in source
    assert "target_keywords=target_rules_unit.keywords" in source
    from warhammer40k_core.engine.attack_hit_modifiers import declaration_hit_modifiers
    from warhammer40k_core.engine.shooting_engagement import (
        CLOSE_QUARTERS_SHOOTING_SOURCE_ID,
        ENGAGED_TARGET_SOURCE_ID,
    )

    modifiers = declaration_hit_modifiers(
        (CLOSE_QUARTERS_SHOOTING_SOURCE_ID, ENGAGED_TARGET_SOURCE_ID)
    )
    assert len(modifiers) == 2
    assert sum(modifier.operand for modifier in modifiers) == -2


def test_order71_matched_candidate_cost() -> None:
    folder = ROOT / "docs/performance/order71"
    base = json.loads((folder / "base.json").read_bytes())
    head = json.loads((folder / "head.json").read_bytes())
    budget = json.loads((folder / "budgets.json").read_bytes())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "hashes",
        "timing_boundary",
    ):
        assert base[key] == head[key], key
    assert head["workload"] == budget["workload"]
    for name, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )
    assert [row["case"] for row in head["rows"]] == [
        "third-party-close",
        "both-causes",
        "mutual-close",
        "attached-third-party",
    ]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert after["legal"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 7
        for metric in ("mean_seconds", "maximum_seconds"):
            assert after[metric] <= before[metric] * budget["ratio"] + budget["additive_seconds"]
