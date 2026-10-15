"""Both reconstruction pairs and every later input delta remain fail closed."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from tools import performance_policy as policy
from tools import performance_reconstruction_campaign as campaign

ROOT = Path(__file__).resolve().parents[2]
BASE_RUNTIME = (
    "warhammer40k-core-v2:runtime-tree-sha256-v1:"
    "3dac52df9bba355343defa9547c58e6b1feb03f8b45e5d6d32031e611075d9bb"
)


def _report() -> dict[str, object]:
    return policy.read_object(ROOT / campaign.REPORT)


def _measured() -> dict[str, str]:
    return cast(
        dict[str, str], policy.read_object(ROOT / campaign.ARCHIVE / "measured-inputs.json.txt")
    )


def _pairs(report: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], report["ordered_pairs"])


def _validate(report: dict[str, object]) -> list[dict[str, object]]:
    inputs = _measured()
    fixture = policy.canonical_digest(
        {
            name: value
            for name, value in inputs.items()
            if name.startswith(("tests/", "scripts/"))
            and not name.startswith("tests/code_quality/")
        }
    )
    return policy.validate_comparison(
        report,
        base=campaign.BASE,
        runtime_id=campaign.RUNTIME,
        input_digest=campaign.MEASURED_DIGEST,
        family="reconstruction",
        specification=policy.object_value(
            policy.object_value(policy.read_object(ROOT / policy.MAP)["families"])["reconstruction"]
        ),
        base_runtime_id=BASE_RUNTIME,
        expected_inputs={
            "lock_sha256": inputs["uv.lock"],
            "workload_sha256": inputs["scripts/measure_ingress_reconstruction.py"],
            "fixture_sha256": fixture,
        },
    )


def _write_proof(root: Path, current: dict[str, str]) -> None:
    measured = _measured()
    proof = {
        "schema": "reconstruction-control-applicability-v1",
        "base": campaign.BASE,
        "measured_head": campaign.MEASURED,
        "measured_tree": campaign.TREE,
        "runtime_build_id": campaign.RUNTIME,
        "review_sha256": campaign.REVIEW_SHA,
        "report_canonical_sha256": campaign.REPORT_DIGEST,
        "measured_input_digest": campaign.MEASURED_DIGEST,
        "current_input_digest": policy.canonical_digest(current),
        "changes": {
            name: {"before": measured.get(name), "after": current.get(name)}
            for name in measured.keys() | current.keys()
            if measured.get(name) != current.get(name)
        },
    }
    (root / campaign.ARCHIVE / "applicability.json.txt").write_text(json.dumps(proof) + "\n")


@pytest.fixture
def archived_root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / campaign.ARCHIVE, tmp_path / campaign.ARCHIVE)
    return tmp_path


def test_both_original_seven_sample_pairs_pass_without_pooling() -> None:
    report = _report()
    assert [(p["base_index"], p["head_index"]) for p in _pairs(report)] == [(0, 1), (3, 2)]
    assert _validate(report) == []


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("metric", ["mean", "maximum"])
def test_either_pair_budget_failure_remains_blocking(index: int, metric: str) -> None:
    report = _report()
    pair = _pairs(report)[index]
    before = policy.object_value(policy.object_value(pair["base"])["samples"])
    after = policy.object_value(policy.object_value(pair["head"])["samples"])
    case = next(iter(after))
    values = cast(list[float], before[case])
    mean = sum(values) / len(values)
    after[case] = (
        [1.25 * mean + 0.06] * 7 if metric == "mean" else [0.01] * 6 + [1.5 * max(values) + 0.11]
    )
    with pytest.raises(ValueError, match="relative budget exceeded"):
        _validate(report)


@pytest.mark.parametrize(
    "mutation",
    [
        "omit",
        "duplicate",
        "reorder",
        "pooled",
        "missing_sample",
        "missing_case",
        "waiver",
        "measured_head",
        "unexpected_field",
    ],
)
def test_campaign_shape_cannot_drop_select_pool_or_relabel(mutation: str) -> None:
    report = _report()
    pairs = _pairs(report)
    samples = policy.object_value(policy.object_value(pairs[0]["head"])["samples"])
    case = next(iter(samples))
    if mutation == "omit":
        pairs.pop()
    elif mutation == "duplicate":
        pairs[1] = deepcopy(pairs[0])
    elif mutation == "reorder":
        pairs.reverse()
    elif mutation == "pooled":
        samples[case] = cast(list[float], samples[case]) * 2
    elif mutation == "missing_sample":
        cast(list[float], samples[case]).pop()
    elif mutation == "missing_case":
        samples.pop(case)
    elif mutation == "waiver":
        report["historical_failures"] = [{"allowed": True}]
    elif mutation == "measured_head":
        report["measured_head"] = "f" * 40
    else:
        report["ignored_field"] = True
    messages = {
        "omit": "Both original reconstruction pairs",
        "duplicate": "pairs were duplicated",
        "reorder": "pairs were duplicated",
        "pooled": "Required samples missing",
        "missing_sample": "Required samples missing",
        "missing_case": "Hard comparison cases",
        "waiver": "cannot relabel inputs or waive",
        "measured_head": "measurement identity drift",
        "unexpected_field": "campaign fields",
    }
    with pytest.raises(ValueError, match=messages[mutation]):
        _validate(report)


def test_primary_pair_alone_cannot_fall_back_to_legacy_admission() -> None:
    report = _report()
    pair = _pairs(report)[0]
    for name in ("schema", "measured_head", "measured_tree", "ordered_pairs"):
        report.pop(name)
    report.update(base=pair["base"], head=pair["head"])
    with pytest.raises(ValueError, match="campaign fields"):
        _validate(report)


def test_declared_control_delta_keeps_original_measured_input_identity(archived_root: Path) -> None:
    measured = _measured()
    current = dict(measured)
    current["tests/code_quality/test_runtime_manifest_reuse.py"] = "f" * 64
    _write_proof(archived_root, current)
    returned, receipt = campaign.retained_inputs(
        archived_root,
        current=current,
        report=_report(),
        base=campaign.BASE,
        runtime_id=campaign.RUNTIME,
    )
    assert returned == measured
    assert len(receipt) == 64
    assert policy.canonical_digest(current) != campaign.MEASURED_DIGEST
    assert policy.canonical_digest(returned) == campaign.MEASURED_DIGEST


@pytest.mark.parametrize(
    "path",
    [
        "src/warhammer40k_core/engine/faction_content/runtime.py",
        "tests/order63_reserve_transport_helpers.py",
        "scripts/measure_ingress_reconstruction.py",
        "uv.lock",
        "pyproject.toml",
        "tools/unreviewed_control.py",
    ],
)
def test_other_input_drift_is_rejected_even_with_updated_proof(
    archived_root: Path, path: str
) -> None:
    current = dict(_measured())
    current[path] = "f" * 64
    _write_proof(archived_root, current)
    with pytest.raises(ValueError, match="Unreviewed"):
        campaign.retained_inputs(
            archived_root,
            current=current,
            report=_report(),
            base=campaign.BASE,
            runtime_id=campaign.RUNTIME,
        )


def test_control_removal_is_not_an_allowed_input_exclusion(archived_root: Path) -> None:
    current = dict(_measured())
    current.pop("tests/code_quality/test_runtime_manifest_reuse.py")
    _write_proof(archived_root, current)
    with pytest.raises(ValueError, match="removal"):
        campaign.retained_inputs(
            archived_root,
            current=current,
            report=_report(),
            base=campaign.BASE,
            runtime_id=campaign.RUNTIME,
        )


@pytest.mark.parametrize("mutation", ["artifact", "extra", "missing", "stale_proof", "report"])
def test_archived_artifacts_and_applicability_are_authenticated(
    archived_root: Path, mutation: str
) -> None:
    current = dict(_measured())
    _write_proof(archived_root, current)
    report = _report()
    archive = archived_root / campaign.ARCHIVE
    target = archive / "child-0-base-raw.json.txt"
    if mutation == "artifact":
        target.write_bytes(target.read_bytes() + b" ")
    elif mutation == "extra":
        (archive / "unexpected.txt").write_text("extra")
    elif mutation == "missing":
        target.unlink()
    elif mutation == "stale_proof":
        current["tests/code_quality/test_runtime_manifest_reuse.py"] = "f" * 64
    else:
        samples = policy.object_value(policy.object_value(_pairs(report)[0]["head"])["samples"])
        samples[next(iter(samples))] = [0.01] * 7
        assert _validate(report) == []
    with pytest.raises((ValueError, FileNotFoundError)):
        campaign.retained_inputs(
            archived_root,
            current=current,
            report=report,
            base=campaign.BASE,
            runtime_id=campaign.RUNTIME,
        )
