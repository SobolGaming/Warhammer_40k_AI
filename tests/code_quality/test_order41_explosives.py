"""Order 41 ownership and comparable component-cost gates."""

import json
from pathlib import Path

from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)

ROOT = Path(__file__).resolve().parents[2]


def test_explosives_uses_model_geometry_and_shared_shooting_restrictions() -> None:
    record = next(
        r
        for r in eleventh_edition_core_stratagem_catalog_records()
        if r.definition.stratagem_id == "explosives"
    )
    assert record.definition.target_spec.enumerable
    assert record.definition.timing.trigger_kind.value == "during_phase"
    engine = ROOT / "src/warhammer40k_core/engine"
    geometry = (engine / "stratagems_geometry.py").read_text()
    query = geometry.split("def _explosives_target_is_visible_and_in_range(")[1].split("\ndef ")[0]
    assert "source_model_instance_id" in query
    assert "component_unit_for_model" in query
    assert "target.alive_models()" in query
    assert "unit_has_line_of_sight_to_target(" in query
    assert ".range_to(" in query
    assert "shooting_target_candidate_for_model(" not in query
    for path in ("stratagems_geometry.py", "phases/shooting_eligibility.py"):
        assert "shooting_state_restriction_reason(" in (engine / path).read_text()
    assert (
        "ExplosivesSelection.from_payload" in (engine / "stratagems_effect_handlers.py").read_text()
    )


def test_explosives_component_cost_is_comparable_complete_and_bounded() -> None:
    directory = ROOT / "docs/performance/order41"
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
        set(base["summaries"])
        == set(head["summaries"])
        == {"grenades", "explosives", "out_of_range"}
    )
    for case, measured in head["summaries"].items():
        assert measured["completion_rate"] == 1
        assert measured["samples"] == budget["samples_per_case"]
        assert (
            measured["mean"]
            <= base["summaries"][case]["mean"] * budget["mean_base_multiplier"]
            + budget["mean_additive_seconds"]
        )
        assert measured["max"] <= budget["maximum_seconds"]
    assert {row["option_count"] for row in head["rows"] if row["case"] != "out_of_range"} == {2}
    assert {row["option_count"] for row in head["rows"] if row["case"] == "out_of_range"} == {0}
