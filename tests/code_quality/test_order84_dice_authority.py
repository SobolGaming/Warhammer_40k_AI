"""Keep physical RNG validation separate from source-assigned result semantics."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
from tools.build_core_dice_results_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

from tests.performance_evidence_helpers import (
    assert_historical_report,
    historical_input_bytes,
)
from warhammer40k_core.engine.dice_extremum import SELECT_DICE_EXTREMUM_DECISION_TYPE
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_dice_results_2026_09 import (
    EXPECTED_ARTIFACT_SHA256,
    source_package,
)

ROOT = Path(__file__).resolve().parents[2]


def test_game_dice_never_initialize_from_public_identity() -> None:
    """Every game draw, including prefix reconstruction, uses private authority."""
    paths = [*(ROOT / "src/warhammer40k_core/engine").rglob("*.py")]
    paths.append(ROOT / "src/warhammer40k_core/adapters/local_session.py")
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "DiceRollManager"
            ):
                continue
            assert len(call.args) == 1, (path, call.lineno)
            source = call.args[0]
            if isinstance(source, ast.Constant) and source.value == 0:
                # This pure request-shape builder never draws or exposes RNG.
                owner = parents[call]
                assert isinstance(owner, ast.Attribute)
                assert owner.attr == "build_reroll_request"
                continue
            private_source = (
                isinstance(source, ast.Attribute) and source.attr == "private_rng_seed"
            ) or (isinstance(source, ast.Name) and source.id == "private_rng_seed")
            if not private_source or not any(k.arg == "event_log" for k in call.keywords):
                violations.append(f"{path.relative_to(ROOT)}:{call.lineno}")
    assert not violations, "Public or implicit game RNG source: " + ", ".join(violations)


def test_dice_result_source_artifacts_and_dispatch_remain_authoritative() -> None:
    import json

    package, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_text(encoding="utf-8")) == package
    assert json.loads(AUDIT_PATH.read_text(encoding="utf-8")) == audit
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


def test_dice_result_component_performance_uses_matched_inputs_and_historical_runtime() -> None:
    import json
    import statistics

    folder = ROOT / "docs/performance/order84"
    base, head = (json.loads((folder / name).read_bytes()) for name in ("base.json", "head.json"))
    budget = json.loads((folder / "budget.json").read_bytes())
    assert_historical_report(head)
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
        assert hashlib.sha256(historical_input_bytes(name)).hexdigest() == digest
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


def test_private_rng_smoke_scope_is_exact_and_preserves_serializer_and_cache_gates() -> None:
    from tools import performance_private_randomness as scope

    record = scope._scope()  # pyright: ignore[reportPrivateUsage]
    for path, operations in scope.OPERATIONS.items():
        change = record["changes"][path]
        expected = frozenset(operations)
        recognize = scope.private_randomness_smoke_operations
        assert (
            recognize(base=scope.BASE, path=path, category="rule_semantics", change=change)
            == expected
        )
        assert not any("serialization" in key or "cache" in key for key in expected)
        for base, requested_path, category in (
            ("0" * 40, path, "rule_semantics"),
            (scope.BASE, "unreviewed.py", "rule_semantics"),
            (scope.BASE, path, "cache_policy"),
            (scope.BASE, path, "serialization_or_replay_work"),
        ):
            assert not recognize(base=base, path=requested_path, category=category, change=change)
        for field in ("before_sha256", "after_sha256", "owners"):
            drift = {**change, field: None}
            assert not recognize(
                base=scope.BASE, path=path, category="rule_semantics", change=drift
            )
        owners = dict(change["owners"])
        owners["unreviewed-owner"] = {"before": None, "after": "0" * 64}
        assert not recognize(
            base=scope.BASE,
            path=path,
            category="rule_semantics",
            change={**change, "owners": owners},
        )
    policy = (Path(scope.__file__).with_name("performance_policy.py")).read_bytes()
    predecessor = scope.private_randomness_policy_predecessor(policy)
    assert hashlib.sha256(predecessor).hexdigest() == scope.PRIOR_POLICY_SHA256
    with pytest.raises(ValueError, match="successor drifted"):
        scope.private_randomness_policy_predecessor(policy + b"# unrelated change\n")
