"""Keep engaged shooting model scopes, independent sources and costs auditable."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import msgspec

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


class ClauseProof(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    clause_id: str
    runtime_consumer_ids: tuple[str, ...]
    regression_ids: tuple[str, ...]


class SourceProof(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    source_artifact_path: str
    source_artifact_sha256: str
    transcription_sha256: str
    observation_sha256: str
    clauses: tuple[ClauseProof, ...]


class ConsumerProof(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    proof_id: str
    scope: str
    sources: tuple[SourceProof, ...]


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


def test_order71_declaration_exclusivity_does_not_promote_physical_unit_keywords() -> None:
    phase_path = ROOT / "src/warhammer40k_core/engine/phases"
    for path in phase_path.glob("shooting_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_unit_has_vehicle_or_monster_keyword"
        ], path
    tree = ast.parse(
        (phase_path / "shooting_declaration_validation.py").read_text(encoding="utf-8")
    )
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_model_pistol_exclusivity"
    )
    guards = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "is_monster_or_vehicle"
    ]
    assert len(guards) == 1
    assert ast.unparse(guards[0].args[0]) == "source_model.keywords"
    assert "source_model = source_unit.own_model_by_id(source_model_id)" in ast.unparse(function)


def test_order71_clause_consumer_proof_preserves_authenticated_observations() -> None:
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_actions_2026_09 as close,
    )
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_engaged_shooting_2026_09 as target,
    )

    raw = (ROOT / "data/source_audits/order71-runtime-consumer-proof-v1.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "8cf6c6cbe36ed768d88402ffeca855cf058dc5c6456b1cf617ffc00f870d0f8d"
    )
    proof = msgspec.json.decode(raw, type=ConsumerProof)
    assert proof.artifact_schema == "order71-runtime-consumer-proof-v1"
    assert proof.proof_id == "order71:shooting-clause-consumers:v1"
    packages = (close, target)
    assert len(proof.sources) == len(packages)
    clause_ids: set[str] = set()
    for source, package in zip(proof.sources, packages, strict=True):
        assert hashlib.sha256((ROOT / source.source_artifact_path).read_bytes()).hexdigest() == (
            source.source_artifact_sha256
        )
        rule = next(row for row in package.source_rules() if row.source_id == source.source_id)
        assert rule.transcription_sha256 == source.transcription_sha256
        mirror = next(
            row
            for row in package.source_evidence_records()
            if row.rule_source_id == source.source_id and row.evidence_kind == "third_party_mirror"
        )
        assert mirror.observation_sha256 == source.observation_sha256
        for clause in source.clauses:
            assert clause.clause_id not in clause_ids
            clause_ids.add(clause.clause_id)
            assert clause.runtime_consumer_ids
            assert clause.regression_ids
            for symbol in (*clause.runtime_consumer_ids, *clause.regression_ids):
                module, name = symbol.split(":")
                path = (
                    ROOT / "src" / (module.replace(".", "/") + ".py")
                    if module.startswith("warhammer40k_core.")
                    else ROOT / module
                )
                tree = ast.parse(path.read_text(encoding="utf-8"))
                assert name in {
                    node.name for node in tree.body if isinstance(node, ast.FunctionDef)
                }
    assert clause_ids == {
        "10.06:model-weapon-and-target-permission",
        "10.06:attacking-model-penalty-and-target-specific-exemption",
        "10.06:blast-against-own-engaged-target",
        "17.03:engaged-target-unit-selection",
        "17.03:blast-target-exclusion",
        "17.03:target-unit-penalty-and-target-specific-exemption",
    }
    # The source artifact's older partial 10.06 execution record is not upgraded.
    assert close.source_rules()[3].semantic_execution_status == "partial_engine_runtime"
    tree = ast.parse(
        (ROOT / "src/warhammer40k_core/engine/shooting_targets.py").read_text(encoding="utf-8")
    )
    candidate = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_target_candidate"
    )
    calls = {
        node.func.id
        for node in ast.walk(candidate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "_locked_in_combat_validation",
        "_target_engagement_validation",
        "_blast_engaged_target_validation",
        "engaged_shooting_penalty_sources",
    } <= calls


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
