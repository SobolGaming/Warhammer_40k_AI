"""Fresh reports use current admission without relabeling retained measurements."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts import check_performance_policy as checker
from scripts.quality_evidence import EvidenceError
from tools.performance_policy import (
    ASSESSMENT,
    MAP,
    POLICY,
    canonical_digest,
    changed_inputs,
    git,
    object_value,
    read_object,
    runtime_inputs,
)

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]
FAMILY = "session_command_fork"
REPORT = "docs/performance/current/fresh.json"
DRIVER = "scripts/measure_fixture.py"


def _write(root: Path, name: str, value: object) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def _commit(root: Path) -> str:
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    return git(root, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def current_checkout(tmp_path: Path) -> tuple[Path, str]:
    """A real clean Git checkout and complete generic evidence for checker tests."""
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    runtime_id = verified_engine_build_identity().build_id
    _write(root, "src/warhammer40k_core/_engine_build_manifest.json", {"build_id": runtime_id})
    (root / "uv.lock").write_text("fixture lock\n")
    (root / "scripts").mkdir()
    (root / DRIVER).write_text("VALUE = 0\n")
    specification = object_value(read_object(ROOT / MAP)["families"])[FAMILY]
    specification = {**object_value(specification), "driver": DRIVER}
    mapping = {
        "policy": POLICY,
        "schema": "reviewed-operation-map-v1",
        "families": {FAMILY: specification},
        "full_game_profiles": {},
        "operations": {
            "fixture": {
                "paths": [DRIVER],
                "owners": ["@module"],
                "families": [FAMILY],
                "sensitive": True,
                "mandatory": True,
            }
        },
    }
    _write(root, MAP, mapping)
    base = _commit(root)
    (root / DRIVER).write_text("VALUE = 1\n")
    inputs = runtime_inputs(root)
    report = read_object(ROOT / "docs/performance/current/issue590-command-fork.json")
    report.update(
        base_revision=base,
        head_runtime_build_id=runtime_id,
        head_input_digest=canonical_digest(inputs),
    )
    fixture_digest = canonical_digest(
        {name: value for name, value in inputs.items() if name.startswith(("tests/", "scripts/"))}
    )
    for side in ("base", "head"):
        object_value(report[side]).update(
            runtime_build_id=runtime_id,
            lock_sha256=inputs["uv.lock"],
            workload_sha256=inputs[DRIVER],
            fixture_sha256=fixture_digest,
        )
    _write(root, REPORT, report)
    _, changes = changed_inputs(root, base)
    rows = {
        name: {
            "category": "measured_workload" if name == DRIVER else "governance",
            "operations": ["fixture"] if name == DRIVER else [],
            "selected_families": [FAMILY] if name == DRIVER else [],
            "rationale": "A complete generic comparison for the actual changed fixture driver.",
            "source_obligation": None,
            "unchanged_work": None,
        }
        for name in changes
    }
    _write(
        root,
        ASSESSMENT,
        {
            "policy": POLICY,
            "base": base,
            "runtime_build_id": runtime_id,
            "operation_map_sha256": canonical_digest(mapping),
            "changes": changes,
            "rows": rows,
            "milestone": "ordinary",
            "comparisons": {FAMILY: REPORT},
            "full_game": None,
        },
    )
    _commit(root)
    return root, base


def _classify(root: Path, base: str) -> bool:
    return checker._uses_fresh_current_comparisons(root, read_object(root / ASSESSMENT), base)  # pyright: ignore[reportPrivateUsage]


def test_fresh_comparisons_reach_full_current_source_and_budget_validation(
    current_checkout: tuple[Path, str],
) -> None:
    root, base = current_checkout
    assert _classify(root, base)
    result = checker.validate_current(root, base, pr_head=None)
    assert result["base_revision"] == base
    assert result["selected_families"] == [FAMILY]
    assert result["retained_measurement_applicability"] == {}
    assert "current_source_identity" in result
    assert "dependency_identity" in result
    assert "history_snapshot_digest" not in result


@pytest.mark.parametrize("field", ["base_revision", "head_runtime_build_id", "head_input_digest"])
def test_stale_generic_comparisons_fail_before_historical_routing(
    current_checkout: tuple[Path, str],
    field: str,
) -> None:
    root, base = current_checkout
    report = read_object(root / REPORT)
    report[field] = "stale"
    _write(root, REPORT, report)
    with pytest.raises(ValueError, match="Fresh comparison has stale"):
        _classify(root, base)


@pytest.mark.parametrize(
    "path",
    [
        "docs/performance/current/../fresh.json",
        "docs/performance/current//fresh.json",
        "docs/performance/current/./fresh.json",
        "docs/performance/current/fresh.txt",
        "docs/performance/current/fresh\\other.json",
        "/tmp/fresh.json",
    ],
)
def test_fresh_report_paths_are_canonical_current_json(
    current_checkout: tuple[Path, str],
    path: str,
) -> None:
    root, base = current_checkout
    assessment = read_object(root / ASSESSMENT)
    assessment["comparisons"] = {FAMILY: path}
    with pytest.raises(ValueError, match="canonical current JSON"):
        checker._uses_fresh_current_comparisons(root, assessment, base)  # pyright: ignore[reportPrivateUsage]


def test_fresh_report_symlink_and_reused_base_member_are_rejected(
    current_checkout: tuple[Path, str],
) -> None:
    root, base = current_checkout
    path = root / REPORT
    actual = path.with_name("actual.json")
    path.rename(actual)
    path.symlink_to(actual.name)
    with pytest.raises(ValueError, match="symlink aliases"):
        _classify(root, base)
    path.unlink()
    actual.rename(path)
    assessment = read_object(root / ASSESSMENT)
    report = read_object(path)
    with pytest.raises(ValueError, match="newly added"):
        checker._fresh_comparison_metadata(  # pyright: ignore[reportPrivateUsage]
            assessment,
            {FAMILY: report},
            base=base,
            runtime_id=str(report["head_runtime_build_id"]),
            input_digest=str(report["head_input_digest"]),
            base_paths={REPORT},
            input_bound_families=set(),
        )


@pytest.mark.parametrize("drift", ["budget", "missing_case", "sample_count", "workload"])
def test_current_route_preserves_full_comparison_failures(
    current_checkout: tuple[Path, str],
    drift: str,
) -> None:
    root, base = current_checkout
    report = read_object(root / REPORT)
    samples = object_value(object_value(report["head"])["samples"])
    case = next(iter(samples))
    if drift == "budget":
        samples[case] = [1000.0] * 3
    elif drift == "missing_case":
        samples.pop(case)
    elif drift == "sample_count":
        samples[case] = [1.0]
    else:
        object_value(report["head"])["workload_sha256"] = "stale"
    _write(root, REPORT, report)
    assessment = read_object(root / ASSESSMENT)
    _, changes = changed_inputs(root, base)
    assessment["changes"] = changes
    _write(root, ASSESSMENT, assessment)
    assert _classify(root, base)
    with pytest.raises(
        ValueError, match=r"budget exceeded|cases were omitted|samples missing|Unmatched"
    ):
        checker._validate_current(root, base, pr_head=None)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize("marker", ["owner_exception", "input_binding", "ordered_pairs", "schema"])
def test_retained_markers_preserve_route_and_cannot_mix_with_fresh(
    current_checkout: tuple[Path, str],
    marker: str,
) -> None:
    root, base = current_checkout
    assessment = read_object(root / ASSESSMENT)
    report = read_object(root / REPORT)
    retained = copy.deepcopy(report)
    retained[marker] = "matched-reconstruction-abba-v1" if marker == "schema" else {}
    assert not checker._fresh_comparison_metadata(  # pyright: ignore[reportPrivateUsage]
        assessment,
        {FAMILY: retained},
        base=base,
        runtime_id=str(report["head_runtime_build_id"]),
        input_digest=str(report["head_input_digest"]),
        base_paths=set(),
        input_bound_families=set(),
    )
    assessment["comparisons"] = {FAMILY: REPORT, "retained": "docs/performance/current/old.json"}
    with pytest.raises(ValueError, match="cannot be mixed"):
        checker._fresh_comparison_metadata(  # pyright: ignore[reportPrivateUsage]
            assessment,
            {FAMILY: report, "retained": retained},
            base=base,
            runtime_id=str(report["head_runtime_build_id"]),
            input_digest=str(report["head_input_digest"]),
            base_paths=set(),
            input_bound_families=set(),
        )


def test_current_transaction_rechecks_source_after_full_validation(
    current_checkout: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, base = current_checkout
    real_validate = checker._validate_current  # pyright: ignore[reportPrivateUsage]

    def change_after_validation(
        checkout: Path,
        base_ref: str,
        *,
        pr_head: str | None,
    ) -> dict[str, object]:
        result = real_validate(checkout, base_ref, pr_head=pr_head)
        (checkout / DRIVER).write_text("VALUE = 2\n")
        return result

    monkeypatch.setattr(checker, "_validate_current", change_after_validation)
    with pytest.raises((ValueError, EvidenceError), match=r"Source bytes differ|changed during"):
        checker.validate_current(root, base, pr_head=None)


def test_retained_base_keeps_original_phase_dispatch() -> None:
    from tools import performance_ci60_qualification as ci60
    from tools import performance_order103_exception as order103
    from tools import performance_reconstruction_campaign as reconstruction

    for base in (ci60.PR_BASE, order103.BASE, reconstruction.BASE):
        assert not checker._uses_fresh_current_comparisons(ROOT, {"milestone": "ordinary"}, base)  # pyright: ignore[reportPrivateUsage]


def test_existing_report_cannot_be_relabelled_fresh_against_real_git_base(
    current_checkout: tuple[Path, str],
) -> None:
    root, _ = current_checkout
    base = git(root, "rev-parse", "HEAD").decode().strip()
    report = read_object(root / REPORT)
    report["base_revision"] = base
    _write(root, REPORT, report)
    assessment = read_object(root / ASSESSMENT)
    assessment["base"] = base
    _write(root, ASSESSMENT, assessment)
    with pytest.raises(ValueError, match="newly added"):
        _classify(root, base)


@pytest.mark.parametrize("field", ["unexpected", "schema", "generated_output_binding"])
def test_malformed_generic_report_cannot_fall_back_to_history(
    current_checkout: tuple[Path, str],
    field: str,
) -> None:
    root, base = current_checkout
    report = read_object(root / REPORT)
    report[field] = "unrecognized"
    _write(root, REPORT, report)
    with pytest.raises(ValueError, match="closed generic report"):
        _classify(root, base)


@pytest.mark.parametrize("field", ["base", "runtime_build_id"])
def test_fresh_assessment_requires_actual_base_and_runtime(
    current_checkout: tuple[Path, str],
    field: str,
) -> None:
    root, base = current_checkout
    assessment = read_object(root / ASSESSMENT)
    assessment[field] = "stale"
    with pytest.raises(ValueError, match="assessment has stale"):
        checker._uses_fresh_current_comparisons(root, assessment, base)  # pyright: ignore[reportPrivateUsage]


def test_independent_postflight_rejects_changed_current_inputs(
    current_checkout: tuple[Path, str],
) -> None:
    root, base = current_checkout
    before = checker.validate_current(root, base, pr_head=None)
    assert before["selected_families"] == [FAMILY]
    (root / DRIVER).write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="Fresh comparison has stale"):
        checker.validate_current(root, base, pr_head=None)
