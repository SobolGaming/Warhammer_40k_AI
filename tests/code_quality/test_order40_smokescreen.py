"""Static ownership and measured-work gates for the Order 40 invariant."""

from __future__ import annotations

import json
from pathlib import Path

from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_smokescreen_uses_generic_execution_and_shared_visibility_authority() -> None:
    row = next(
        row
        for row in eleventh_edition_core_stratagem_catalog_records()
        if row.definition.stratagem_id == "smokescreen"
    )
    assert row.definition.handler_id == "generic:rule-ir"
    assert row.definition.target_spec.enumerable
    assert row.definition.target_spec.target_policy_id == "friendly_smoke_unit"
    assert row.definition.timing.trigger_kind.value == "start_phase"
    query = (ENGINE / "obscuring_model_cover.py").read_text()
    assert "not_fully_visible_because_of(" in query
    assert "battlefield_scenario_for_state(state=state)" in query
    assert "rules_unit_effect_applications" in query
    assert "retained_model_ids" in query
    for name in (
        "attack_modifier_snapshots.py",
        "attack_sequence_hit_wound.py",
        "attack_sequence_damage_resolution.py",
    ):
        assert "obscuring_model_cover_sources" in (ENGINE / name).read_text()
    for name in (
        "core_stratagem_effects.py",
        "attack_modifier_snapshots.py",
        "stratagems_effect_handlers.py",
        "stratagems_core_handlers.py",
    ):
        text = (ENGINE / name).read_text()
        assert "SMOKESCREEN_HIT_ROLL_MODIFIER" not in text
        assert "_apply_smokescreen_handler" not in text
        assert "SMOKESCREEN_EFFECT_KIND" not in text


def test_smokescreen_component_evidence_is_comparable_complete_and_bounded() -> None:
    directory = ROOT / "docs/performance/order40"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for field in (
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
    ):
        assert base[field] == head[field]
    for path, digest in base["file_hashes"].items():
        if path != "src/warhammer40k_core/_engine_build_manifest.json":
            assert head["file_hashes"][path] == digest
    assert (
        set(base["summaries"]) == set(head["summaries"]) == {"plain", "direct", "obscured", "clear"}
    )
    for name, measured in head["summaries"].items():
        assert measured["completion_rate"] == 1
        assert measured["samples"] == budget["samples_per_case"]
        assert (
            measured["mean"]
            <= base["summaries"][name]["mean"] * budget["mean_base_multiplier"]
            + budget["mean_additive_seconds"]
        )
        assert measured["max"] <= budget["maximum_seconds"]
