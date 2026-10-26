"""Historical integrity and current applicability are separate required gates."""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from scripts.check_performance_policy import validate_current, validate_smoke_report
from scripts.performance_smoke import CASE_LIMIT_SECONDS, CASES, PROCESS_LIMIT_SECONDS, WORKLOAD
from tools import quality_runtime_successor as ci54
from tools.performance_policy import (
    ASSESSMENT,
    MAP,
    ORDER108_SCOPE,
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
    value: dict[str, object],
    changes: dict[str, object],
    mapping: dict[str, object],
    *,
    base: str = BASE,
) -> set[str]:
    return validate_assessment(
        value, base=base, changes=changes, runtime_id=BUILD, operation_map=mapping
    )


@pytest.mark.parametrize(
    "path",
    [
        "src/warhammer40k_core/core/visibility.py",
        "src/warhammer40k_core/geometry/pathing.py",
        "src/warhammer40k_core/geometry/terrain.py",
        "src/warhammer40k_core/geometry/terrain_classification.py",
        "src/warhammer40k_core/geometry/terrain_solid.py",
        "src/warhammer40k_core/geometry/terrain_transit.py",
    ],
)
@pytest.mark.parametrize(
    "drift",
    [
        "none",
        "base",
        "path",
        "before_file",
        "after_file",
        "before_owner",
        "after_owner",
        "extra_owner",
        "missing_owner",
        "category",
    ],
)
def test_order108_smoke_scope_authenticates_complete_semantic_rows(path: str, drift: str) -> None:
    scope = read_object(ROOT / ORDER108_SCOPE)
    base = str(scope["base"])
    operation = "visibility-query" if "/core/" in path else "geometry-search"
    value, changes, mapping = _assessment(path, category="rule_semantics", operations=(operation,))
    change = copy.deepcopy(object_value(object_value(scope["changes"])[path]))
    changes[path] = change
    value["base"] = base
    rows = object_value(value["rows"])
    row = object_value(rows[path])
    owners = object_value(change["owners"])
    assert owners
    owner = next(iter(owners))
    if drift == "base":
        base = BASE
        value["base"] = base
    elif drift == "path":
        renamed = path.replace(".py", "_other.py")
        changes[renamed] = changes.pop(path)
        rows[renamed] = rows.pop(path)
    elif drift in {"before_file", "after_file"}:
        change[drift.removesuffix("_file") + "_sha256"] = "0" * 64
    elif drift in {"before_owner", "after_owner"}:
        object_value(owners[owner])[drift.removesuffix("_owner")] = "0" * 64
    elif drift == "extra_owner":
        owners["additional_operation"] = {"before": None, "after": "0" * 64}
    elif drift == "missing_owner":
        owners.pop(owner)
    elif drift == "category":
        row["category"] = "algorithm_or_search"
    if drift == "none":
        assert _validate(value, changes, mapping, base=base) == set()
    else:
        with pytest.raises(ValueError, match="Missing required detailed comparisons"):
            _validate(value, changes, mapping, base=base)


@pytest.mark.parametrize("failure", ["mandatory", "cache", "source", "work"])
def test_order108_scope_preserves_other_assessment_obligations(failure: str) -> None:
    path = "src/warhammer40k_core/geometry/terrain.py"
    scope = read_object(ROOT / ORDER108_SCOPE)
    value, changes, mapping = _assessment(
        path, category="rule_semantics", operations=("geometry-search",)
    )
    value["base"] = scope["base"]
    changes[path] = copy.deepcopy(object_value(scope["changes"])[path])
    row = object_value(object_value(value["rows"])[path])
    if failure == "mandatory":
        row["operations"] = []
        error = "Unknown/missing owner operation mapping"
    elif failure == "cache":
        # Even an authenticated row cannot suppress another sensitive operation.
        object_value(object_value(mapping["operations"])["cache-policy"])["owners"] = ["*"]
        value["operation_map_sha256"] = canonical_digest(mapping)
        row["operations"] = ["geometry-search", "cache-policy"]
        error = "Missing required detailed comparisons"
    else:
        row["source_obligation" if failure == "source" else "unchanged_work"] = ""
        error = "Rule assessment lacks"
    with pytest.raises(ValueError, match=error):
        _validate(value, changes, mapping, base=str(scope["base"]))


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
            ("reconstruction", "dice", "dice_sustained"),
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
    operations: tuple[str, ...] = (operation,)
    if path == "src/warhammer40k_core/engine/lifecycle.py":
        operations += ("order135-gathered-attack-steps",)
    value, changes, mapping = _assessment(
        path, owner=owner, category="rule_semantics", operations=operations
    )
    with pytest.raises(ValueError, match="detailed comparisons"):
        _validate(value, changes, mapping)
    value, changes, mapping = _assessment(
        path,
        owner=owner,
        category="algorithm_or_search",
        operations=operations,
        selected=families,
    )
    assert _validate(value, changes, mapping) == set(families)
    object_value(object_value(value["rows"])[path])["operations"] = []
    with pytest.raises(ValueError, match=r".+"):
        _validate(value, changes, mapping)


@pytest.mark.parametrize("omitted", ["serialization-replay", "order135-gathered-attack-steps"])
def test_each_lifecycle_sensitive_operation_remains_mandatory(omitted: str) -> None:
    operations = ("serialization-replay", "order135-gathered-attack-steps")
    value, changes, mapping = _assessment(
        "src/warhammer40k_core/engine/lifecycle.py",
        owner="GameLifecycle.from_payload",
        category="algorithm_or_search",
        operations=tuple(operation for operation in operations if operation != omitted),
        selected=("reconstruction", "dice", "dice_sustained"),
    )
    with pytest.raises(ValueError, match="Sensitive owner operation omitted"):
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
    workflow = ci54.previous(
        ROOT, ".github/workflows/ci.yml", (ROOT / ".github/workflows/ci.yml").read_bytes()
    ).decode()
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
        "reports/quality-timing/gw0.json",
        "reports/timing/gw0.json",
        "reports/code-quality.xml",
        "reports/behavior-timing/gw0.json",
        "reports/behavior-shard-1.xml",
        "reports/behavior-shard-12.xml",
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

    from tools import performance_ci60_qualification as ci60

    for historical_path, pin in ci60.SUPERSEDED_REPORTS.items():
        preserved, changes, mapping = _assessment(historical_path)
        preserved["base"] = ci60.PR_BASE
        change = object_value(changes[historical_path])
        change["before_sha256"] = None
        change["after_sha256"] = pin
        assert _validate(preserved, changes, mapping, base=ci60.PR_BASE) == set()
        change["after_sha256"] = "f" * 64
        with pytest.raises(ValueError, match="not an assessed obligation"):
            _validate(preserved, changes, mapping, base=ci60.PR_BASE)
        change["after_sha256"] = pin
        change["before_sha256"] = pin
        with pytest.raises(ValueError, match="Existing measurement records are immutable"):
            _validate(preserved, changes, mapping, base=ci60.PR_BASE)
        change["before_sha256"] = None
        preserved["base"] = BASE
        with pytest.raises(ValueError, match="not an assessed obligation"):
            _validate(preserved, changes, mapping)


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


@pytest.fixture(scope="module")
def ci64_original_policy() -> dict[str, Callable[..., Any]]:
    """Independent native E61 functions, with original validation order intact."""
    import ast

    from tools import performance_policy as policy

    source = subprocess.check_output(
        ["git", "show", "620cbe91ae3ddd356eaf7effa7455b931882a39e:tools/performance_policy.py"],
        cwd=ROOT,
    )
    names = {"owner_hashes", "validate_assessment"}
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in nodes} == names
    for node in nodes:
        node.decorator_list = []
    namespace: dict[str, Any] = dict(vars(policy))
    body: list[ast.stmt] = list(nodes)
    exec(compile(ast.Module(body=body, type_ignores=[]), "<native-E61-policy>", "exec"), namespace)
    return {name: cast(Callable[..., Any], namespace[name]) for name in names}


@pytest.mark.parametrize(
    "source",
    [
        b"class Empty: pass\n",
        b"class Values:\n 'doc'\n value = 1\n class Inner: pass\n",
        b"class Mixed:\n value = 1\n def a(self): pass\n other = 2\n async def b(self): pass\n",
        b"class Duplicate:\n def f(self): return 1\n value = 2\n def f(self): return 3\n",
        (
            b"class Decorated:\n @staticmethod\n def a(): return 1\n"
            b" @classmethod\n async def b(cls): pass\n"
        ),
        (
            b"class Nested:\n class Child:\n  def f(self): pass\n"
            b" def g(self):\n  def local(): pass\n  return local\n"
        ),
        b"async def top(): pass\ndef other(): pass\nconstant = 2\n",
        b"class Many:\n"
        + b"".join(f" def method_{index}(self): return {index}\n".encode() for index in range(64)),
    ],
    ids=[
        "empty",
        "nonmethods",
        "interleaved",
        "duplicate-name",
        "decorated",
        "nested",
        "module",
        "many",
    ],
)
def test_ci64_owner_identity_filter_preserves_native_outputs(
    source: bytes, ci64_original_policy: dict[str, Callable[..., Any]]
) -> None:
    from tools.performance_policy import owner_hashes

    assert owner_hashes("fixture.py", source) == ci64_original_policy["owner_hashes"](
        "fixture.py", source
    )


@pytest.mark.parametrize(
    "variant",
    [
        "ordinary",
        "shared-values",
        "empty-rows",
        "unmatched-owners",
        "matched-owners",
        "late-path-error",
        "early-owner-error",
        "duplicate-paths",
        "partial-owner-coverage",
        "glob-overlap",
        "mandatory-omission",
    ],
)
def test_ci64_operation_index_matches_native_lazy_validation(
    variant: str, ci64_original_policy: dict[str, Callable[..., Any]]
) -> None:
    operation: dict[str, object] = {
        "paths": ["tests/x.py", "tests/y.py"],
        "owners": ["*"],
        "families": [],
        "mandatory": True,
        "sensitive": False,
    }
    operations: dict[str, object] = {"literal": operation}
    value, changes, mapping = _assessment(
        "tests/x.py", owner="owner", category="measured_workload", operations=("literal",)
    )
    rows = object_value(value["rows"])
    changes["tests/y.py"] = copy.deepcopy(changes["tests/x.py"])
    rows["tests/y.py"] = copy.deepcopy(rows["tests/x.py"])
    mapping = {"operations": operations, "families": {}}
    if variant == "shared-values":
        operations["second"] = operation
        for raw in rows.values():
            object_value(raw)["operations"] = ["literal", "second"]
    elif variant == "empty-rows":
        rows.clear()
        changes.clear()
        operations["unused"] = {"paths": None, "owners": None}
    elif variant == "unmatched-owners":
        operations["unused"] = {"paths": ["unmatched.py"], "owners": None}
    elif variant == "matched-owners":
        operations["bad"] = {"paths": ["tests/y.py"], "owners": None}
    elif variant == "late-path-error":
        operations["bad"] = {"paths": None, "owners": []}
    elif variant == "early-owner-error":
        operation["owners"] = ["owner", "owner"]
        operations["later"] = {"paths": None, "owners": []}
    elif variant == "duplicate-paths":
        operation["paths"] = ["tests/x.py", "tests/x.py"]
    elif variant == "partial-owner-coverage":
        operation["owners"] = ["different"]
    elif variant == "glob-overlap":
        operation["paths"] = ["tests/x.py", "tests/[xy].py", "tests/?.py"]
    elif variant == "mandatory-omission":
        object_value(rows["tests/y.py"])["operations"] = []
    value["operation_map_sha256"] = canonical_digest(mapping)

    def outcome(function: Callable[..., Any]) -> tuple[object, ...]:
        try:
            return (
                "returned",
                function(
                    value, base=BASE, changes=changes, runtime_id=BUILD, operation_map=mapping
                ),
            )
        except (ValueError, TypeError, KeyError) as error:
            return (type(error), str(error))

    assert outcome(validate_assessment) == outcome(ci64_original_policy["validate_assessment"])
    # A separate public call must prepare from the new complete map again.
    operation["owners"] = ["*"]
    operations.pop("bad", None)
    operations.pop("later", None)
    value["operation_map_sha256"] = canonical_digest(mapping)
    assert outcome(validate_assessment) == outcome(ci64_original_policy["validate_assessment"])


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        ("tests/*.py", "tests/nested/x.py"),
        ("tests/[x].py", "tests/x.py"),
        ("tests/?.py", "tests/x.py"),
        ("tests/X.py", "tests/x.py"),
        ("tests/[.py", "tests/[.py"),
        ("tests/ü.py", "tests/ü.py"),
    ],
)
def test_ci64_operation_index_preserves_case_glob_and_literal_paths(
    pattern: str, path: str, ci64_original_policy: dict[str, Callable[..., Any]]
) -> None:
    mapping: dict[str, object]
    value, changes, mapping = _assessment(
        path, category="measured_workload", operations=("candidate",)
    )
    rows = object_value(value["rows"])
    changes["tests/first.py"] = copy.deepcopy(changes[path])
    rows["tests/first.py"] = copy.deepcopy(rows[path])
    # The first inserted row exercises preparation; the second exercises lookup.
    value["rows"] = {"tests/first.py": rows["tests/first.py"], path: rows[path]}
    mapping = {
        "families": {},
        "operations": {
            "candidate": {
                "paths": ["tests/first.py", pattern],
                "owners": ["*"],
                "families": [],
                "mandatory": True,
                "sensitive": False,
            }
        },
    }
    value["operation_map_sha256"] = canonical_digest(mapping)
    expected = ci64_original_policy["validate_assessment"]
    try:
        result = expected(
            value, base=BASE, changes=changes, runtime_id=BUILD, operation_map=mapping
        )
    except ValueError as error:
        with pytest.raises(ValueError, match=str(error)):
            _validate(value, changes, mapping)
    else:
        assert _validate(value, changes, mapping) == result
