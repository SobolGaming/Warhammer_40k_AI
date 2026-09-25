"""Order 85 source, shared ownership and matched diagnostic evidence gates."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

from tools.build_core_base_contact_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_base_contact_2026_09 import (
    DEEMED_BASE_CONTACT_SOURCE_ID,
    EXPECTED_ARTIFACT_SHA256,
    source_package,
)

ROOT = Path(__file__).resolve().parents[2]


def test_contact_source_and_artifacts_are_pinned_and_reproducible() -> None:
    artifact, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_text()) == artifact
    assert json.loads(AUDIT_PATH.read_text()) == audit
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == EXPECTED_ARTIFACT_SHA256
    assert source_package().evidence_required_source_ids == (DEEMED_BASE_CONTACT_SOURCE_ID,)


def test_contact_consumers_and_movement_producers_use_shared_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in ("fight_geometry.py", "fight_rules_unit_movement.py"):
        text = (engine / name).read_text()
        assert "engine_models_in_base_contact(" in text
        assert "model.range_to(enemy_model) <= base_contact_epsilon" not in text
    for name in (
        "charge_move_resolution.py",
        "fight_movement_paths.py",
        "triggered_movement_resolution.py",
        "phases/movement_resolvers.py",
    ):
        assert "contacts_for_validated_move(" in (engine / name).read_text()
    assert "body_parts=model.body_parts" in (engine / "phases/movement_geometry.py").read_text()


def test_contact_slice_cost_preserves_matched_inputs_and_results() -> None:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    folder = ROOT / "docs/performance/order85"
    base, head = (json.loads((folder / p).read_text()) for p in ("base.json", "head.json"))
    budget = json.loads((folder / "budget.json").read_text())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "cpu",
        "memory_bytes",
        "platform",
        "python",
        "concurrency",
        "hashes",
        "timing_boundary",
        "fixture",
    ):
        assert base[key] == head[key], key
    assert head["workload"] == budget["workload"]
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["case"] == after["case"]
        assert len(after["samples_seconds"]) == len(before["samples_seconds"]) == budget["samples"]
        assert after["mean_seconds"] == statistics.mean(after["samples_seconds"])
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * budget["mean_ratio"] + budget["mean_additive_seconds"]
        )
        assert max(after["samples_seconds"]) <= budget["maximum_submission_seconds"]
        assert max(after["setup_seconds"]) <= budget["maximum_setup_seconds"]
        expected = "waiting_for_decision" if after["case"] == "body-touch" else "invalid"
        assert after["statuses"] == [expected] * budget["samples"]


def test_physical_placement_owners_do_not_reimplement_base_only_collision() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in (
        "deployment_geometry.py",
        "prebattle.py",
        "reserves.py",
        "transport_disembark_geometry.py",
        "return_placement_legality.py",
    ):
        source = (engine / name).read_text()
        assert "models_overlap_physically(" in source
        assert ".base_overlaps(" not in source
    assert (
        "base_crosses_physical_model_footprint("
        in (engine / "phases/movement_geometry.py").read_text()
    )


def test_charge_contact_permissions_have_one_live_and_historical_owner() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in ("charge_move_resolution.py", "base_contact_charge_history.py"):
        assert "charge_model_path_contexts(" in (engine / name).read_text()
    history = (engine / "base_contact_charge_history.py").read_text()
    assert "expected_path != context or expected_terrain != query.terrain_context" in history
    assert "historical_generic_effect_inventory(" in history
    assert "event_index=creation_index" in history
    owner = (engine / "base_contact_history.py").read_text()
    assert owner.index("validate_charge_contact_permissions(") < owner.index(
        "expected_query = charge_endpoint_query("
    )


def test_asymmetric_body_search_has_matched_performance_evidence() -> None:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    folder = ROOT / "docs/performance/order85"
    base, head = (
        json.loads((folder / p).read_text()) for p in ("rotation-base.json", "rotation-head.json")
    )
    budget = json.loads((folder / "budget.json").read_text())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "cpu",
        "memory_bytes",
        "platform",
        "python",
        "concurrency",
        "script_sha256",
    ):
        assert base[key] == head[key], key
    assert (
        head["script_sha256"]
        == hashlib.sha256((ROOT / "scripts/measure_order85_rotation.py").read_bytes()).hexdigest()
    )
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["bearing"] == after["bearing"]
        assert before["statuses"] == ["unresolved"] * budget["samples"]
        assert after["statuses"] == ["reachable"] * budget["samples"]
        assert (
            statistics.mean(after["samples_seconds"])
            <= statistics.mean(before["samples_seconds"]) * budget["mean_ratio"]
            + budget["mean_additive_seconds"]
        )
        assert max(after["samples_seconds"]) <= budget["maximum_submission_seconds"]
