"""Historical integrity and current applicability are separate required gates."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from scripts.check_performance_policy import validate_current, validate_smoke_report
from scripts.performance_smoke import CASE_LIMIT_SECONDS, CASES, PROCESS_LIMIT_SECONDS, WORKLOAD
from tools.performance_policy import (
    ASSESSMENT,
    MAP,
    POLICY,
    canonical_digest,
    changed_inputs,
    object_value,
    read_object,
    validate_assessment,
    validate_comparison,
    validate_full_game,
)

from tests.performance_evidence_helpers import (
    HISTORICAL_BASE,
    assert_historical_report,
    historical_input_bytes,
    verify_historical_inventory,
)

ROOT = Path(__file__).resolve().parents[2]
BUILD = "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "1" * 64
BASE_BUILD = "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "2" * 64
BASE = "a" * 40


def _assessment(
    path: str,
    *,
    owner: str = "@document",
    category: str = "governance",
    operations: tuple[str, ...] = (),
    selected: tuple[str, ...] = (),
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    mapping = read_object(ROOT / MAP)
    changes: dict[str, object] = {
        path: {
            "before_sha256": "a",
            "after_sha256": "b",
            "owners": {owner: {"before": "a", "after": "b"}},
        }
    }
    result: dict[str, object] = {
        "policy": POLICY,
        "base": BASE,
        "runtime_build_id": BUILD,
        "operation_map_sha256": canonical_digest(mapping),
        "changes": changes,
        "rows": {
            path: {
                "category": category,
                "operations": list(operations),
                "selected_families": list(selected),
                "rationale": "Explicit reviewed operation relevance for this exact changed owner.",
                "source_obligation": (
                    "Source-backed ordinary branch correction with unchanged algorithm."
                ),
                "unchanged_work": (
                    "The bounded branch preserves iteration, cache and reconstruction work."
                ),
            }
        },
        "milestone": "ordinary",
        "comparisons": {name: f"docs/performance/current/{name}.json" for name in selected},
        "full_game": None,
    }
    return result, changes, mapping


def _validate(
    value: dict[str, object], changes: dict[str, object], mapping: dict[str, object]
) -> set[str]:
    return validate_assessment(
        value, base=BASE, changes=changes, runtime_id=BUILD, operation_map=mapping
    )


def test_governance_and_ordinary_rule_changes_do_not_refresh_all_history() -> None:
    value, changes, mapping = _assessment("README.md")
    assert _validate(value, changes, mapping) == set()
    value, changes, mapping = _assessment(
        "src/warhammer40k_core/engine/game_state.py",
        owner="GameState.clear_turn_action_states",
        category="rule_semantics",
        operations=("phase-rule-branch",),
    )
    assert _validate(value, changes, mapping) == set()
    value["runtime_build_id"] = BUILD.replace("1111", "3333")
    with pytest.raises(ValueError, match="actual current"):
        _validate(value, changes, mapping)


@pytest.mark.parametrize(
    "failure",
    [
        "base",
        "changes",
        "map",
        "missing_row",
        "unknown_category",
        "optout",
        "unknown_operation",
        "runtime_governance",
        "source",
        "work",
        "unknown_owner",
    ],
)
def test_assessment_rejects_missing_stale_or_unmapped_claims(failure: str) -> None:
    path = "src/warhammer40k_core/engine/game_state.py"
    value, changes, mapping = _assessment(
        path,
        owner="GameState.clear_turn_action_states",
        category="rule_semantics",
        operations=("phase-rule-branch",),
    )
    row = object_value(object_value(value["rows"])[path])
    if failure == "base":
        value["base"] = "b" * 40
    elif failure == "changes":
        value["changes"] = {}
    elif failure == "map":
        value["operation_map_sha256"] = "old"
    elif failure == "missing_row":
        value["rows"] = {}
    elif failure == "unknown_category":
        row["category"] = "not_performance_relevant"
    elif failure == "optout":
        row["skip"] = True
    elif failure == "unknown_operation":
        row["operations"] = ["unregistered"]
    elif failure == "runtime_governance":
        row.update(category="governance", operations=[])
    elif failure == "source":
        row["source_obligation"] = ""
    elif failure == "work":
        row["unchanged_work"] = ""
    elif failure == "unknown_owner":
        value, changes, mapping = _assessment(
            "src/warhammer40k_core/unknown_owner.py",
            category="rule_semantics",
            operations=("phase-rule-branch",),
        )
    with pytest.raises(ValueError, match=r".+"):
        _validate(value, changes, mapping)


@pytest.mark.parametrize(
    ("path", "owner", "operation", "families"),
    [
        (
            "src/warhammer40k_core/geometry/polygons.py",
            "solve",
            "geometry-search",
            ("visibility", "movement", "setup"),
        ),
        (
            "src/warhammer40k_core/engine/lifecycle.py",
            "GameLifecycle.from_payload",
            "serialization-replay",
            ("reconstruction",),
        ),
        (
            "src/warhammer40k_core/engine/custom.py",
            "build_cache",
            "cache-policy",
            ("visibility", "reconstruction"),
        ),
        ("scripts/measure_order78.py", "main", "workload-visibility", ("visibility",)),
    ],
)
def test_sensitive_operations_cannot_be_downgraded_or_omitted(
    path: str, owner: str, operation: str, families: tuple[str, ...]
) -> None:
    value, changes, mapping = _assessment(
        path, owner=owner, category="rule_semantics", operations=(operation,)
    )
    with pytest.raises(ValueError, match="detailed comparisons"):
        _validate(value, changes, mapping)
    value, changes, mapping = _assessment(
        path,
        owner=owner,
        category="algorithm_or_search",
        operations=(operation,),
        selected=families,
    )
    assert _validate(value, changes, mapping) == set(families)
    object_value(object_value(value["rows"])[path])["operations"] = []
    with pytest.raises(ValueError, match=r".+"):
        _validate(value, changes, mapping)


def test_dependency_assessment_uses_the_reviewed_role_and_preserves_runtime_triggers() -> None:
    value, changes, mapping = _assessment(
        "uv.lock", category="dependency_environment", operations=("development-dependency",)
    )
    assert _validate(value, changes, mapping) == set()
    object_value(object_value(value["rows"])["uv.lock"])["operations"] = ["runtime-dependency"]
    with pytest.raises(ValueError, match="detailed comparisons"):
        _validate(value, changes, mapping)


def _comparison() -> tuple[dict[str, object], dict[str, object]]:
    spec: dict[str, object] = {
        "cases": ["easy", "hard"],
        "samples_per_case": 3,
        "budget_profile": "current-change-relative-v1",
        "workload_id": "test-workload-v1",
    }
    side: dict[str, object] = {
        "runtime_build_id": BUILD,
        "host": {
            "cpu": "declared-host",
            "memory_bytes": 32000000000,
            "logical_cpus": 8,
            "platform": "test-os",
            "python": "3.14.5",
            "role": "provisional",
        },
        "lock_sha256": "lock",
        "workload_sha256": "workload",
        "fixture_sha256": "fixture",
        "completed": True,
        "coverage": False,
        "concurrency": 1,
        "samples": {"easy": [1.0] * 3, "hard": [2.0] * 3},
    }
    before = copy.deepcopy(side)
    before["runtime_build_id"] = BASE_BUILD
    return {
        "policy": POLICY,
        "family": "reconstruction",
        "base_revision": BASE,
        "head_runtime_build_id": BUILD,
        "head_input_digest": "inputs",
        "budget_profile": "current-change-relative-v1",
        "workload_id": "test-workload-v1",
        "base": before,
        "head": side,
        "historical_failures": [],
    }, spec


@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "runtime",
        "base_runtime",
        "base",
        "input",
        "host",
        "workload",
        "missing_case",
        "sample_count",
        "timeout",
        "mean_budget",
        "maximum_budget",
        "coverage",
        "optout",
    ],
)
def test_current_comparison_requires_actual_matched_complete_evidence(failure: str) -> None:
    value, spec = _comparison()
    head = object_value(value["head"])
    samples = object_value(head["samples"])
    if failure == "runtime":
        head["runtime_build_id"] = BASE_BUILD
    elif failure == "base_runtime":
        object_value(value["base"])["runtime_build_id"] = BUILD
    elif failure == "base":
        value["base_revision"] = "old-baseline"
    elif failure == "input":
        value["head_input_digest"] = "stale"
    elif failure in {"host", "workload"}:
        head["host" if failure == "host" else "workload_sha256"] = "different"
    elif failure == "missing_case":
        samples.pop("hard")
    elif failure == "sample_count":
        samples["hard"] = [2.0]
    elif failure == "timeout":
        samples["hard"] = [2.0, 2.0, float("inf")]
    elif failure == "mean_budget":
        samples["hard"] = [2.6] * 3
    elif failure == "maximum_budget":
        samples["hard"] = [1.0, 1.0, 3.2]
    elif failure == "coverage":
        head["coverage"] = True
    elif failure == "optout":
        value["budget_profile"] = "waived"
    if failure == "none":
        validate_comparison(
            value,
            base=BASE,
            runtime_id=BUILD,
            input_digest="inputs",
            family="reconstruction",
            specification=spec,
            base_runtime_id=BASE_BUILD,
            expected_inputs={
                "lock_sha256": "lock",
                "workload_sha256": "workload",
                "fixture_sha256": "fixture",
            },
        )
    else:
        with pytest.raises(ValueError, match=r".+"):
            validate_comparison(
                value,
                base=BASE,
                runtime_id=BUILD,
                input_digest="inputs",
                family="reconstruction",
                specification=spec,
                base_runtime_id=BASE_BUILD,
                expected_inputs={
                    "lock_sha256": "lock",
                    "workload_sha256": "workload",
                    "fixture_sha256": "fixture",
                },
            )


def test_rules_complete_milestone_fails_closed_without_full_game_profiling() -> None:
    value, changes, mapping = _assessment("README.md")
    value["milestone"] = "rules_complete"
    with pytest.raises(ValueError, match="profiling is missing"):
        _validate(value, changes, mapping)
    with pytest.raises(ValueError, match="unavailable/incomplete"):
        validate_full_game(
            {"base_revision": BASE, "runtime_build_id": BUILD, "supported_driver": False},
            base=BASE,
            runtime_id=BUILD,
            input_digest="inputs",
            workload_sha256="workload",
        )


@pytest.mark.parametrize(
    "field",
    [
        "host",
        "workload_sha256",
        "head_input_digest",
        "decision_policy",
        "seeds",
        "rosters",
        "terrain",
        "startup_seconds",
    ],
)
def test_full_game_evidence_rejects_null_qualification_and_stale_workload(field: str) -> None:
    comparison, _ = _comparison()
    full: dict[str, object] = {
        "base_revision": BASE,
        "runtime_build_id": BUILD,
        "policy": POLICY,
        "normal_completion": True,
        "supported_driver": True,
        "head_input_digest": "inputs",
        "workload_sha256": "workload",
        "host": object_value(comparison["head"])["host"],
        "initialization_through_completion_seconds": [10.0, 11.0, 12.0],
        "decision_policy": "legal-recorded-decisions-v1",
        "seeds": [1, 2, 3],
        "rosters": [{"model_count": 20}] * 3,
        "terrain": [{"layout_id": "fixed-layout", "features": 8}] * 3,
        "startup_seconds": [0.1, 0.1, 0.1],
    }
    validate_full_game(
        full, base=BASE, runtime_id=BUILD, input_digest="inputs", workload_sha256="workload"
    )
    full[field] = None
    with pytest.raises(ValueError, match=r".+"):
        validate_full_game(
            full, base=BASE, runtime_id=BUILD, input_digest="inputs", workload_sha256="workload"
        )


def _smoke_receipt() -> dict[str, object]:
    return {
        "status": "passed",
        "workload": WORKLOAD,
        "input_digest": "inputs",
        "case_limit_seconds": CASE_LIMIT_SECONDS,
        "process_limit_seconds": PROCESS_LIMIT_SECONDS,
        "total_seconds": 3.0,
        "cases": [
            {
                "case": case,
                "exit_code": 0,
                "timed_out": False,
                "process_seconds": 1.0,
                "result": {"case": case, "complete": True},
            }
            for case in CASES
        ],
    }


@pytest.mark.parametrize(
    "failure",
    ["none", "stale", "missing", "timeout", "case_limit", "process_limit", "failed", "limits"],
)
def test_smoke_validation_rejects_incomplete_stale_or_slow_attempts(failure: str) -> None:
    value = _smoke_receipt()
    rows = value["cases"]
    assert isinstance(rows, list)
    if failure == "stale":
        value["input_digest"] = "old"
    elif failure == "missing":
        rows.pop()
    elif failure == "timeout":
        rows[0]["timed_out"] = True
    elif failure == "case_limit":
        rows[0]["process_seconds"] = CASE_LIMIT_SECONDS + 1
    elif failure == "process_limit":
        value["total_seconds"] = PROCESS_LIMIT_SECONDS + 1
    elif failure == "failed":
        rows[0]["exit_code"] = 1
    elif failure == "limits":
        value["case_limit_seconds"] = 9999
    if failure == "none":
        validate_smoke_report(value, binding={"input_digest": "inputs"})
    else:
        with pytest.raises(ValueError, match=r".+"):
            validate_smoke_report(value, binding={"input_digest": "inputs"})


def test_diff_binding_includes_untracked_and_deleted_files_and_only_excludes_assessment(
    tmp_path: Path,
) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={tmp_path.as_posix()}",
                "-c",
                "user.name=Performance Test",
                "-c",
                "user.email=performance-test@example.invalid",
                *args,
            ],
            cwd=tmp_path,
            text=True,
        ).strip()

    git("init", "-q")
    (tmp_path / "README.md").write_text("before\n")
    (tmp_path / "removed.txt").write_text("remove\n")
    git("add", ".")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    (tmp_path / "README.md").write_text("after\n")
    (tmp_path / "removed.txt").unlink()
    (tmp_path / "new.py").write_text("def operation():\n    return 1\n")
    assessment = tmp_path / ASSESSMENT
    assessment.parent.mkdir(parents=True)
    assessment.write_text("{}")
    actual_base, changes = changed_inputs(tmp_path, base)
    assert actual_base == base
    assert set(changes) == {"README.md", "removed.txt", "new.py"}
    assert "operation" in object_value(object_value(changes["new.py"])["owners"])
    with pytest.raises(subprocess.CalledProcessError):
        changed_inputs(tmp_path, "f" * 40)


def test_historical_evidence_is_immutable_and_unknown_inputs_never_fall_back() -> None:
    verify_historical_inventory()
    report = json.loads((ROOT / "docs/performance/order101/head.json").read_text())
    assert_historical_report(report)
    report["runtime_build_id"] = BUILD
    with pytest.raises(ValueError, match="Unregistered or modified"):
        assert_historical_report(report)
    with pytest.raises(ValueError, match="Unregistered historical"):
        historical_input_bytes("src/warhammer40k_core/engine/game_state.py")
    assert historical_input_bytes("uv.lock")
    assert len(HISTORICAL_BASE) == 40


def test_required_current_receipt_matches_this_checkout_and_assessment() -> None:
    report = read_object(ROOT / "reports/performance-smoke.json")
    assert report["inputs_unchanged"] is True
    base = report["base_revision"]
    pr_head = report["pull_request_head"]
    assert isinstance(base, str)
    assert pr_head is None or isinstance(pr_head, str)
    validate_smoke_report(report, binding=validate_current(ROOT, base, pr_head=pr_head))


def test_current_smoke_is_in_the_required_serial_ci_lane() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    quality = workflow.split("  code-quality:", 1)[1].split("  semantic-audit-macos:", 1)[0]
    assert "fetch-depth: 0" in quality
    assert quality.index("scripts.check_performance_policy") < quality.index(
        "pytest tests/code_quality"
    )
    assert "--base-ref" in quality
    assert "performance-smoke.json" in quality
    assert "quality-fast" in workflow
    assert "needs: [lint, contract-conformance, code-quality" in workflow


def test_smoke_outputs_do_not_change_assessed_inputs_or_hide_unrelated_reports() -> None:
    from tools.performance_policy import git

    outputs = (
        "reports/performance-smoke.json",
        "reports/performance-attempts/example/result.json",
    )
    assert set(git(ROOT, "check-ignore", *outputs).decode().splitlines()) == set(outputs)
    with pytest.raises(subprocess.CalledProcessError):
        git(ROOT, "check-ignore", "reports/unrelated-source.json")


def test_a_recognized_neighbor_cannot_cover_an_unknown_changed_owner() -> None:
    path = "src/warhammer40k_core/engine/lifecycle.py"
    value, changes, mapping = _assessment(
        path,
        owner="GameLifecycle.to_payload",
        category="serialization_or_replay_work",
        operations=("serialization-replay",),
        selected=("reconstruction",),
    )
    object_value(object_value(changes[path])["owners"])["GameLifecycle._advance_once"] = {
        "before": "a",
        "after": "b",
    }
    with pytest.raises(ValueError, match="Changed owner lacks an explicit operation"):
        _validate(value, changes, mapping)


def test_prior_current_measurements_cannot_be_overwritten_as_fresh_evidence() -> None:
    path = "docs/performance/current/prior-comparison.json"
    value, changes, mapping = _assessment(path)
    with pytest.raises(ValueError, match="Existing measurement records are immutable"):
        _validate(value, changes, mapping)
    object_value(changes[path])["before_sha256"] = None
    with pytest.raises(ValueError, match="not an assessed obligation"):
        _validate(value, changes, mapping)


@pytest.mark.parametrize("field", ["lock_sha256", "workload_sha256", "fixture_sha256"])
def test_equal_stale_measurement_hashes_do_not_authenticate_current_inputs(field: str) -> None:
    value, spec = _comparison()
    object_value(value["base"])[field] = "equal-but-stale"
    object_value(value["head"])[field] = "equal-but-stale"
    with pytest.raises(ValueError, match="actual selected workload"):
        validate_comparison(
            value,
            base=BASE,
            runtime_id=BUILD,
            input_digest="inputs",
            family="reconstruction",
            specification=spec,
            base_runtime_id=BASE_BUILD,
            expected_inputs={
                "lock_sha256": "lock",
                "workload_sha256": "workload",
                "fixture_sha256": "fixture",
            },
        )


def test_comparison_cannot_ignore_a_stricter_family_profile_or_host_qualification() -> None:
    value, spec = _comparison()
    spec["budget_profile"] = "stricter-family-v1"
    with pytest.raises(ValueError, match="declared family budget"):
        validate_comparison(
            value,
            base=BASE,
            runtime_id=BUILD,
            input_digest="inputs",
            family="reconstruction",
            specification=spec,
            base_runtime_id=BASE_BUILD,
            expected_inputs={
                "lock_sha256": "lock",
                "workload_sha256": "workload",
                "fixture_sha256": "fixture",
            },
        )
    value, spec = _comparison()
    object_value(value["base"])["host"] = {"cpu": "only-cpu"}
    object_value(value["head"])["host"] = {"cpu": "only-cpu"}
    with pytest.raises(ValueError, match="Unexpected or missing"):
        validate_comparison(
            value,
            base=BASE,
            runtime_id=BUILD,
            input_digest="inputs",
            family="reconstruction",
            specification=spec,
            base_runtime_id=BASE_BUILD,
            expected_inputs={
                "lock_sha256": "lock",
                "workload_sha256": "workload",
                "fixture_sha256": "fixture",
            },
        )


def test_operation_map_uses_real_driver_and_owner_paths() -> None:
    import fnmatch

    from tools.performance_policy import git

    paths = (
        git(ROOT, "ls-files", "--cached", "--others", "--exclude-standard").decode().splitlines()
    )
    mapping = read_object(ROOT / MAP)
    families = object_value(mapping["families"])
    for raw in families.values():
        family = object_value(raw)
        assert (ROOT / str(family["driver"])).is_file()
        assert (ROOT / str(family["historical_workload_reference"])).is_file()
    for raw in object_value(mapping["operations"]).values():
        operation = object_value(raw)
        patterns = operation["paths"]
        assert isinstance(patterns, list)
        for pattern in cast(list[object], patterns):
            assert isinstance(pattern, str)
            assert any(fnmatch.fnmatchcase(path, pattern) for path in paths), pattern
