"""The owner approved one retained failed mean, never a general budget bypass."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from tools.performance_order103_exception import (
    APPLICABILITY,
    APPROVAL,
    BASE,
    MEASURED_DIGEST,
    RECOGNITION,
    RUNTIME,
    retained_comparison_inputs,
    validate_owner_recognition,
)
from tools.performance_policy import (
    MAP,
    canonical_digest,
    object_value,
    read_object,
    validate_comparison,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT = "docs/performance/current/order103-dice-sustained.json"


def _validate(report: dict[str, object]) -> list[dict[str, object]]:
    base = object_value(report["base"])
    return validate_comparison(
        report,
        base=BASE,
        runtime_id=RUNTIME,
        input_digest=MEASURED_DIGEST,
        family="dice_sustained",
        specification=object_value(
            object_value(read_object(ROOT / MAP)["families"])["dice_sustained"]
        ),
        base_runtime_id=str(base["runtime_build_id"]),
        expected_inputs={
            key: str(base[key]) for key in ("lock_sha256", "workload_sha256", "fixture_sha256")
        },
    )


def _retained_current() -> dict[str, str]:
    proof = read_object(ROOT / APPLICABILITY)
    current = {key: str(value) for key, value in object_value(proof["measured_inputs"]).items()}
    for path, raw in object_value(proof["changes"]).items():
        row = object_value(raw)
        assert current.get(path) == row["before"]
        assert isinstance(row["after"], str)
        current[path] = row["after"]
    assert canonical_digest(current) == proof["current_input_digest"]
    return current


def test_exact_approved_failure_keeps_original_samples_and_failed_numerical_status() -> None:
    report = read_object(ROOT / REPORT)
    outcomes = _validate(report)
    assert outcomes == [
        {
            **RECOGNITION,
            "family": "dice_sustained",
            "numerical_budget_passed": False,
            "measured_seconds": 2.481014919979498,
            "budget_seconds": 2.262186475022463,
        }
    ]
    report.pop("owner_exception")
    with pytest.raises(ValueError, match="relative budget exceeded"):
        _validate(report)


@pytest.mark.parametrize(
    "mutation",
    [
        "base",
        "runtime",
        "family",
        "workload",
        "digest",
        "profile",
        "mean_sample",
        "max_sample",
        "other_case",
        "case",
        "metric",
        "id",
        "status",
        "extra_field",
        "host",
        "lock",
        "incomplete",
        "sample_count",
        "otherwise_passing",
    ],
)
def test_recognition_cannot_cover_changed_evidence_or_any_other_failure(mutation: str) -> None:
    report = copy.deepcopy(read_object(ROOT / REPORT))
    top = {
        "base": "base_revision",
        "runtime": "head_runtime_build_id",
        "family": "family",
        "workload": "workload_id",
        "digest": "head_input_digest",
        "profile": "budget_profile",
    }
    if mutation in top:
        report[top[mutation]] = "unapproved"
    elif mutation in {"case", "metric", "id", "status"}:
        object_value(report["owner_exception"])[mutation] = "unapproved"
    elif mutation == "extra_field":
        report["skip"] = True
    elif mutation in {"host", "lock", "incomplete"}:
        head = object_value(report["head"])
        if mutation == "host":
            object_value(head["host"])["cpu"] = "another host"
        elif mutation == "lock":
            head["lock_sha256"] = "another lock"
        else:
            head["completed"] = False
    else:
        samples = object_value(object_value(report["head"])["samples"])
        case = "fight/false" if mutation == "other_case" else "shooting/true"
        values = samples[case]
        assert isinstance(values, list)
        if mutation == "sample_count":
            values.pop()
        elif mutation == "otherwise_passing":
            samples[case] = [0.1] * 5
        else:
            values[0] = 100.0 if mutation in {"max_sample", "other_case"} else 2.44
    with pytest.raises(ValueError, match=r".+"):
        _validate(report)


def test_recognition_is_not_accepted_on_a_different_passing_family() -> None:
    report = read_object(ROOT / "docs/performance/current/order103-dice.json")
    report["owner_exception"] = dict(RECOGNITION)
    with pytest.raises(ValueError, match="Unrecognized"):
        validate_owner_recognition(report)


def test_retained_bridge_authenticates_governance_delta_without_relabeling_digest() -> None:
    report = read_object(ROOT / REPORT)
    current = _retained_current()
    measured, proof_sha = retained_comparison_inputs(
        ROOT, current=current, report=report, base=BASE, runtime_id=RUNTIME
    )
    assert canonical_digest(measured) == MEASURED_DIGEST
    assert canonical_digest(current) != MEASURED_DIGEST
    assert isinstance(proof_sha, str)
    assert len(proof_sha) == 64
    assert (
        measured["scripts/check_performance_policy.py"]
        != current["scripts/check_performance_policy.py"]
    )
    for path in ("scripts/benchmark_order96_rerolls.py", "tests/twin_linked_helpers.py", "uv.lock"):
        assert measured[path] == current[path]


@pytest.mark.parametrize(
    "mutation",
    [
        "engine",
        "fixture",
        "driver",
        "lock",
        "governance",
        "extra_path",
        "missing_path",
        "base",
        "runtime",
        "report",
    ],
)
def test_retained_bridge_rejects_unapproved_or_stale_actual_inputs(mutation: str) -> None:
    current = _retained_current()
    report = read_object(ROOT / REPORT)
    paths = {
        "engine": "src/warhammer40k_core/engine/decision.py",
        "fixture": "tests/twin_linked_helpers.py",
        "driver": "scripts/benchmark_order96_rerolls.py",
        "lock": "uv.lock",
        "governance": "tools/performance_policy.py",
        "extra_path": "tools/unknown.py",
    }
    if mutation in paths:
        current[paths[mutation]] = "0" * 64
    elif mutation == "missing_path":
        current.pop("uv.lock")
    elif mutation == "report":
        report["historical_failures"] = []
    with pytest.raises(ValueError, match=r".+"):
        retained_comparison_inputs(
            ROOT,
            current=current,
            report=report,
            base="other" if mutation == "base" else BASE,
            runtime_id="other" if mutation == "runtime" else RUNTIME,
        )


@pytest.mark.parametrize(
    "mutation",
    ["missing_approval", "changed_approval", "missing_proof", "changed_delta", "changed_measured"],
)
def test_missing_or_corrupt_authority_and_applicability_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    approval = tmp_path / APPROVAL
    proof_path = tmp_path / APPLICABILITY
    approval.parent.mkdir(parents=True)
    approval.write_bytes((ROOT / APPROVAL).read_bytes())
    proof = read_object(ROOT / APPLICABILITY)
    if mutation == "missing_approval":
        approval.unlink()
    elif mutation == "changed_approval":
        approval.write_text("{}")
    elif mutation == "changed_delta":
        proof["changes"] = {}
    elif mutation == "changed_measured":
        object_value(proof["measured_inputs"])["uv.lock"] = "unapproved"
    if mutation != "missing_proof":
        proof_path.write_text(json.dumps(proof))
    with pytest.raises((ValueError, OSError)):
        retained_comparison_inputs(
            tmp_path,
            current=_retained_current(),
            report=read_object(ROOT / REPORT),
            base=BASE,
            runtime_id=RUNTIME,
        )


def test_unrelated_matching_inputs_need_no_exception_or_applicability_file(tmp_path: Path) -> None:
    current = {"uv.lock": "ordinary"}
    assert retained_comparison_inputs(
        tmp_path,
        current=current,
        report={"head_input_digest": canonical_digest(current)},
        base="other",
        runtime_id="other",
    ) == (current, None)
