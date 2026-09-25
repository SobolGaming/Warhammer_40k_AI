"""Keep physical RNG validation separate from source-assigned result semantics."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.build_core_dice_results_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from warhammer40k_core.engine.dice_extremum import SELECT_DICE_EXTREMUM_DECISION_TYPE
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_dice_results_2026_09 import (
    EXPECTED_ARTIFACT_SHA256,
    source_package,
)

ROOT = Path(__file__).resolve().parents[2]


def test_dice_result_source_artifacts_and_dispatch_remain_authoritative() -> None:
    import json

    package, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_text()) == package
    assert json.loads(AUDIT_PATH.read_text()) == audit
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == EXPECTED_ARTIFACT_SHA256
    assert source_package().evidence_required_source_ids == (
        "gw-11e-core-dice-results:default-critical-hit",
        "gw-11e-core-dice-results:default-critical-wound",
        "gw-11e-core-dice-results:highest-lowest",
        "gw-11e-core-dice-results:treated-as-set-to",
    )
    lifecycle = GameLifecycle()
    assert SELECT_DICE_EXTREMUM_DECISION_TYPE in {
        contract.decision_type for contract in lifecycle.decision_dispatch_contracts
    }


def test_dice_consumers_share_interpreted_face_validation_and_roll_history() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in ("attack_sequence_model.py", "attack_sequence_validation.py", "saves.py"):
        text = (engine / name).read_text()
        assert "validate_interpreted_d6(" in text
        assert "1 <= self.unmodified_roll <= 6" not in text
    overrides = (engine / "dice_result_overrides.py").read_text()
    assert "latest_roll_state(" in overrides
    assert "def _latest_roll_state" not in overrides
    assert "roll_state.current_total == 6" not in overrides


def test_dice_result_component_performance_uses_matched_inputs_and_current_runtime() -> None:
    import json
    import statistics

    from warhammer40k_core.build_identity import verified_engine_build_identity

    folder = ROOT / "docs/performance/order84"
    base, head = (json.loads((folder / name).read_bytes()) for name in ("base.json", "head.json"))
    budget = json.loads((folder / "budget.json").read_bytes())
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
    assert head["concurrency"] == 1
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    assert [row["case"] for row in head["rows"]] == ["1d6-physical", "2d6-physical", "1d6-assigned"]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["case"] == after["case"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == budget["samples"]
        assert after["mean_seconds"] == statistics.mean(after["samples_seconds"])
        assert after["maximum_seconds"] == max(after["samples_seconds"])
        assert after["mean_seconds"] <= (
            before["mean_seconds"] * budget["mean_ratio"] + budget["mean_additive_seconds"]
        )
        assert after["maximum_seconds"] <= budget["maximum_seconds"]
    assert head["completion_rate"] == base["completion_rate"] == 1
    assert not head["coverage"]
    assert not head["full_game_certified"]
