from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tools.build_core_emergency_disembark_placement_source import (
    ARTIFACT_PATH,
    AUDIT_PATH,
    build_payloads,
)

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_emergency_disembark_placement_2026_09 as source,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"
GEOMETRY = ROOT / "src/warhammer40k_core/geometry"


def test_emergency_disembark_placement_source_is_pinned_reproducible_and_executable() -> None:
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        assert path.read_text(encoding="utf-8") == (
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        )
    assert (
        source.source_package().source_catalog.catalog_sha256()
        == source.source_catalog().catalog_sha256()
    )
    (rule,) = source.source_rules()
    assert source.PLACEMENT_POLICY.source_rule_id == rule.source_id
    assert source.PLACEMENT_POLICY.setup_distance_inches == 6
    assert source.PLACEMENT_POLICY.requires_closest_possible is True
    assert source.PLACEMENT_POLICY.prefers_unengaged is True
    assert source.PLACEMENT_POLICY.allows_engaged_when_unengaged_impossible is True
    assert source.PLACEMENT_POLICY.destroys_only_unplaceable_models is True
    assert source.PLACEMENT_POLICY.closest_tolerance_inches == 0.04
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert "append_emergency_disembark_placement_violations" in rule.runtime_consumer_ids[0]
    with pytest.raises(source.EmergencyDisembarkPlacementSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_emergency_disembark_placement_has_one_proof_owner() -> None:
    owner = (ENGINE / "emergency_disembark_placement.py").read_text(encoding="utf-8")
    geometry = (ENGINE / "transport_disembark_geometry.py").read_text(encoding="utf-8")
    transports = (ENGINE / "transports.py").read_text(encoding="utf-8")
    grouped = (ENGINE / "destroyed_transport_rules_unit_disembark.py").read_text(encoding="utf-8")
    fit = (GEOMETRY / "emergency_setup_proof.py").read_text(encoding="utf-8")
    assert "PLACEMENT_POLICY" in owner
    assert "emergency_setup_pose_exists(" in owner
    assert "terrain_features" in owner
    assert "is_within_engagement_range(" in owner
    assert "append_emergency_disembark_placement_violations(" in transports
    assert "append_emergency_disembark_rules_unit_omission_violations(" in grouped
    assert "DisembarkModeKind.EMERGENCY_DISEMBARK" in geometry
    assert "emergency_setup_pose_is_legal(" in owner
    assert "_terrain_conditions(" in fit
    assert "for floor in terrain.feature.floors" in fit
    assert "rotation = (c * c + s * s).eq(1)" in fit
    assert "formula, names = _plane_formula(query, z)" in fit
    assert "if decide(formula, names):" in fit
    assert "_circular_radius" not in owner
    assert "floor collision and supported-elevation proof" not in owner
    assert not (GEOMETRY / "emergency_disembark_fit.py").exists()
    assert "except Exception" not in owner
    assert "except Exception" not in fit
    assert _emergency_owner_modules() == (
        "destroyed_transport_rules_unit_disembark.py",
        "transports.py",
    )


@pytest.mark.parametrize("evidence_directory", ["", "r60_followup"])
def test_order60_performance_has_matched_inputs_and_passes_declared_budgets(
    evidence_directory: str,
) -> None:
    directory = ROOT / "docs/performance/order60" / evidence_directory
    base, head = (json.loads((directory / f"{name}.json").read_text()) for name in ("base", "head"))
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "timing_boundary",
        "hashes",
        "budgets",
    ):
        assert base[field] == head[field], field
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(sample["complete"] is True for sample in report["samples"])
        assert all(sample["valid"] is True for sample in report["samples"])
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
        + base["budgets"]["mean_additive_seconds"]
    )
    assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]


def _emergency_owner_modules() -> tuple[str, ...]:
    modules: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_is_owner_call(node) for node in ast.walk(tree)):
            modules.append(path.name)
    return tuple(modules)


def _is_owner_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    names = {
        "append_emergency_disembark_placement_violations",
        "append_emergency_disembark_rules_unit_omission_violations",
    }
    if isinstance(func, ast.Name):
        return func.id in names
    return isinstance(func, ast.Attribute) and func.attr in names


def test_order73_geometry_performance_preserves_unresolved_base_and_complete_head() -> None:
    directory = ROOT / "docs/performance/order73"
    for prefix in ("", "geometry-"):
        base, head = (
            json.loads((directory / f"{prefix}{name}.json").read_text(encoding="utf-8"))
            for name in ("base", "head")
        )
        for field in (
            "workload_id",
            "platform",
            "python",
            "cpu",
            "cpu_allocation",
            "memory_bytes",
            "concurrency",
            "timing_boundary",
            "hashes",
        ):
            assert base[field] == head[field], field
        assert head["completion_rate"] == 1
        assert head["full_game_certified"] is False
        assert all(row["complete"] and row["valid"] for row in head["samples"])
        if prefix:
            assert base["completion_rate"] == 0
            assert all(not row["complete"] and row["error"] for row in base["samples"])
            assert len(head["samples"]) == 12
            assert head["budget"] == base["budget"]
            assert (
                head["maximum_attempt_seconds"] <= head["budget"]["head_maximum_submission_seconds"]
            )
        else:
            assert (
                head["mean_seconds"]
                <= base["mean_seconds"] * base["budgets"]["mean_ratio"]
                + base["budgets"]["mean_additive_seconds"]
            )
            assert head["maximum_seconds"] <= base["budgets"]["maximum_seconds"]
