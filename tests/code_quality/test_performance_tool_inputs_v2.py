"""Fresh v2 binding rejection controls; synthetic samples are never evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest
from tools import performance_tool_inputs as v1
from tools import performance_tool_inputs_v2 as v2
from tools.performance_policy import POLICY, validate_comparison

ROOT = Path(__file__).resolve().parents[2]


def _spec() -> dict[str, object]:
    return v2.read_role_spec(ROOT)


def _inventories() -> tuple[dict[str, str], dict[str, str]]:
    common = dict.fromkeys(v1.REQUIRED | {"src/real.py", "contracts/README.md"}, "a" * 64)
    return (
        {**common, **dict.fromkeys(v2.DERIVED | (v2.TREATMENT - {v1.INDEX}), "b" * 64)},
        {**common, **dict.fromkeys(v2.TREATMENT | v2.DERIVED | v2.CONTROL, "c" * 64)},
    )


def _binding(base: dict[str, str], head: dict[str, str]) -> dict[str, object]:
    harness = {p: head[p] for p in v2.HARNESS}
    return v2.classify_inputs(
        spec=_spec(),
        base=base,
        head=head,
        base_revision=v1.MEASURED_BASE,
        head_revision="d" * 40,
        head_input_digest="e" * 64,
        harness_base=harness,
        harness_head=harness,
    )


def _generated(binding: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    common = cast(dict[str, str], binding["common"])
    sides = cast(dict[str, dict[str, object]], binding["sides"])
    for side in ("base", "head"):
        derived = cast(dict[str, str], sides[side]["derived_outputs"])
        tree = {
            p.removeprefix("contracts/"): value
            for p, value in (common | derived).items()
            if p.startswith("contracts/")
        }
        result[side] = [dict(tree) for _ in range(3)]
    return result


def _report() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    binding = _binding(*_inventories())
    spec: dict[str, object] = {
        "budget_profile": "current-change-relative-v1",
        "workload_id": v1.WORKLOAD_ID,
        "driver": v1.WORKLOAD,
        "cases": ["orphan-write-independent-check"],
        "samples_per_case": 3,
        "input_binding": {"schema": v2.SCHEMA, "role_specification": v2.SPEC_PATH},
    }
    side: dict[str, object] = {
        "runtime_build_id": "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "a" * 64,
        "host": {
            "cpu": "synthetic",
            "memory_bytes": 1024,
            "logical_cpus": 4,
            "platform": "test",
            "python": "3.14.5",
            "role": "provisional",
        },
        "lock_sha256": "lock",
        "workload_sha256": "workload",
        "fixture_sha256": binding["common_sha256"],
        "samples": {"orphan-write-independent-check": [1.0, 1.0, 1.0]},
        "completed": True,
        "concurrency": 1,
        "coverage": False,
    }
    report: dict[str, object] = {
        "policy": POLICY,
        "family": v1.FAMILY,
        "workload_id": v1.WORKLOAD_ID,
        "base_revision": v1.MEASURED_BASE,
        "head_runtime_build_id": side["runtime_build_id"],
        "head_input_digest": "e" * 64,
        "budget_profile": "current-change-relative-v1",
        "base": copy.deepcopy(side),
        "head": copy.deepcopy(side),
        "historical_failures": [],
        "input_binding": copy.deepcopy(binding),
        "generated_output_binding": _generated(binding),
    }
    return report, spec, binding


def _validate(
    report: dict[str, object], spec: dict[str, object], binding: dict[str, object]
) -> None:
    validate_comparison(
        report,
        base=v1.MEASURED_BASE,
        runtime_id=str(report["head_runtime_build_id"]),
        input_digest="e" * 64,
        family=v1.FAMILY,
        specification=spec,
        base_runtime_id=str(report["head_runtime_build_id"]),
        expected_inputs={
            "lock_sha256": "lock",
            "workload_sha256": "workload",
            "fixture_sha256": str(binding["common_sha256"]),
        },
        expected_binding=binding,
    )


def test_fresh_binding_keeps_runtime_treatment_and_derived_bytes_out_of_controls() -> None:
    report, spec, binding = _report()
    _validate(report, spec, binding)
    for side in cast(dict[str, dict[str, object]], binding["sides"]).values():
        assert v2.RUNTIME in cast(dict[str, object], side["implementation"])
        assert not v2.TREATMENT.intersection(cast(dict[str, object], side["control_plane"]))
        assert set(cast(dict[str, object], side["derived_outputs"])) == v2.DERIVED


@pytest.mark.parametrize(
    "path", ["src/unknown.py", "tools/unknown.py", "contracts/unknown.json", *sorted(v1.REQUIRED)]
)
@pytest.mark.parametrize("action", ["change", "delete"])
def test_fresh_binding_rejects_unknown_changed_or_omitted_common_inputs(
    path: str, action: str
) -> None:
    before, after = _inventories()
    if action == "change":
        after[path] = "f" * 64
    else:
        before.setdefault(path, "a" * 64)
        after.pop(path, None)
    with pytest.raises(ValueError, match=r"common|presence"):
        _binding(before, after)


@pytest.mark.parametrize(
    "role", ["treatment", "derived_outputs", "control_plane", "required_dependencies", "harness"]
)
def test_fresh_spec_rejects_report_supplied_scope_expansion(role: str) -> None:
    spec = _spec()
    if role == "control_plane":
        cast(dict[str, str], spec[role])[v2.RUNTIME] = "Runtime falsely declared as a control"
    else:
        cast(list[str], spec[role]).append("src/unapproved.py")
    with pytest.raises(ValueError, match="scope"):
        v2.validate_spec(spec)


@pytest.mark.parametrize(
    "field", ["schema", "head_input_digest", "sides", "common", "harness", "role_spec_sha256"]
)
def test_fresh_comparison_rejects_stale_or_forged_binding(field: str) -> None:
    report, spec, binding = _report()
    cast(dict[str, object], report["input_binding"])[field] = "stale-v1-or-forged"
    with pytest.raises(ValueError, match="input binding"):
        _validate(report, spec, binding)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "missing_sample", "missing_path", "changed_hash", "extra_path", "swapped_arms"],
)
def test_generated_parity_requires_all_exact_raw_bytes(mutation: str) -> None:
    report, spec, binding = _report()
    parity = cast(dict[str, list[dict[str, str]]], report["generated_output_binding"])
    if mutation == "missing":
        del report["generated_output_binding"]
    elif mutation == "missing_sample":
        parity["head"].pop()
    elif mutation == "missing_path":
        parity["head"][0].pop("manifest.json")
    elif mutation == "changed_hash":
        parity["head"][0]["manifest.json"] = "0" * 64
    elif mutation == "extra_path":
        parity["head"][0]["unapproved.json"] = "0" * 64
    else:
        parity["head"], parity["base"] = parity["base"], parity["head"]
    with pytest.raises((ValueError, TypeError), match=r"parity|object"):
        _validate(report, spec, binding)


@pytest.mark.parametrize(
    ("field", "value"),
    [("samples_per_case", 2), ("cases", ["easier"]), ("budget_profile", "relaxed")],
)
def test_fresh_binding_cannot_change_original_family_work_or_budget(
    field: str, value: object
) -> None:
    report, spec, binding = _report()
    spec[field] = value
    with pytest.raises(ValueError, match="capability"):
        _validate(report, spec, binding)


def test_fresh_binding_cannot_reuse_historical_measurement_revision() -> None:
    before, after = _inventories()
    harness = {p: after[p] for p in v2.HARNESS}
    with pytest.raises(ValueError, match="fresh treatment"):
        v2.classify_inputs(
            spec=_spec(),
            base=before,
            head=after,
            base_revision=v1.MEASURED_BASE,
            head_revision=v1.MEASURED_HEAD,
            head_input_digest="e" * 64,
            harness_base=harness,
            harness_head=harness,
        )


def test_fresh_comparison_still_rejects_relative_budget_failure() -> None:
    report, spec, binding = _report()
    cast(dict[str, object], report["head"])["samples"] = {
        "orphan-write-independent-check": [2.0, 2.0, 2.0]
    }
    with pytest.raises(ValueError, match="budget exceeded"):
        _validate(report, spec, binding)


def test_fresh_spec_and_old_archive_are_distinct_and_authenticated() -> None:
    assert _spec()["schema"] == v2.SCHEMA
    assert v1.read_role_spec(ROOT)["schema"] == v1.SCHEMA
    assert (
        json.loads((ROOT / v1.REPORT_ARCHIVE).read_bytes())["input_binding"]["schema"] == v1.SCHEMA
    )


def test_current_runtime_cannot_inherit_the_old_archival_comparison() -> None:
    from tools.performance_policy import runtime_inputs

    report = json.loads((ROOT / v1.REPORT_ARCHIVE).read_bytes())
    with pytest.raises(ValueError, match="map delta differs"):
        v1.retained_tool_comparison_inputs(
            ROOT, current=runtime_inputs(ROOT), report=report, base=v1.MEASURED_BASE
        )


def test_derived_inventory_rejects_omission_and_actual_file_tampering(tmp_path: Path) -> None:
    import hashlib

    expected: dict[str, str] = {}
    for name in sorted(v2.DERIVED):
        raw = (name + "\n").encode()
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        expected[name] = hashlib.sha256(raw).hexdigest()
    v2.validate_derived_outputs(tmp_path, expected)
    with pytest.raises(ValueError, match="Incomplete"):
        v2.validate_derived_outputs(tmp_path, {})
    (tmp_path / "contracts/manifest.json").write_text("changed identity leaf\n")
    with pytest.raises(ValueError, match="bound source bytes"):
        v2.validate_derived_outputs(tmp_path, expected)
