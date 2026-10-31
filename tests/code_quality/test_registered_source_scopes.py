"""Finite reviewed admission controls; synthetic documents are never measurements."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from tools import performance_tool_inputs as inputs
from tools import performance_tool_inputs_v4 as scopes
from tools import source_scope_provenance as provenance
from tools.performance_policy import validate_comparison

from tests.code_quality import test_performance_tool_inputs_v2 as fixtures
from tests.code_quality import test_phase14a_source_identity as guard

ROOT = Path(__file__).resolve().parents[2]
SCOPE = scopes.registered_scope(scopes.EC_BASE)


def _inventories() -> tuple[dict[str, str], dict[str, str]]:
    common = dict.fromkeys(SCOPE.required | {"src/real.py", "contracts/README.md"}, "a" * 64)
    return (
        common | dict.fromkeys(SCOPE.derived | (SCOPE.treatment - SCOPE.new_treatment), "b" * 64),
        common | dict.fromkeys(SCOPE.derived | SCOPE.treatment | SCOPE.control, "c" * 64),
    )


def _binding(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    return scopes.classify_inputs(
        spec=scopes.read_role_spec(ROOT, scope_base=SCOPE.base),
        base=before,
        head=after,
        base_revision=SCOPE.base,
        head_revision="d" * 40,
        head_input_digest="e" * 64,
        harness_base={p: after[p] for p in SCOPE.harness},
        harness_head={p: after[p] for p in SCOPE.harness},
    )


def _report() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    report, specification, _ = fixtures._report()
    binding = _binding(*_inventories())
    report["base_revision"] = SCOPE.base
    report["input_binding"] = binding
    report["generated_output_binding"] = fixtures._generated(binding)
    for side in ("base", "head"):
        report[side]["fixture_sha256"] = binding["common_sha256"]  # type: ignore[index]
    specification["input_binding"] = {
        "schema": scopes.SCHEMA,
        "role_specification": SCOPE.spec_path,
    }
    return report, specification, binding


def _validate(
    report: dict[str, Any], specification: dict[str, Any], binding: dict[str, Any]
) -> None:
    scopes.validate_scope_binding(str(report["base_revision"]), binding)
    validate_comparison(
        report,
        base=SCOPE.base,
        runtime_id=report["head_runtime_build_id"],
        input_digest="e" * 64,
        family=inputs.FAMILY,
        specification=specification,
        base_runtime_id=report["base"]["runtime_build_id"],
        expected_inputs={
            "lock_sha256": "lock",
            "workload_sha256": "workload",
            "fixture_sha256": binding["common_sha256"],
        },
        expected_binding=binding,
    )


def test_registered_scopes_preserve_original_spec_and_admit_closed_ec_scope() -> None:
    for base in (scopes.BASE, scopes.EC_BASE):
        scope = scopes.registered_scope(base)
        assert scopes.scope_for_specification(scope.spec_path) == scope
        assert (
            hashlib.sha256((ROOT / scope.spec_path).read_bytes()).hexdigest()
            == scope.spec_raw_sha256
        )
        assert (
            inputs.digest(scopes.read_role_spec(ROOT, scope_base=base))
            == scope.spec_canonical_sha256
        )
    assert scopes.registered_scope().base == scopes.BASE
    _validate(*_report())


@pytest.mark.parametrize("drift", ["base", "path", "raw", "role", "digest", "report_scope"])
def test_registered_scope_authentication_rejects_unknown_or_mutated_inputs(
    tmp_path: Path, drift: str
) -> None:
    def attempt() -> None:
        if drift == "base":
            scopes.registered_scope("f" * 40)
        elif drift == "path":
            scopes.scope_for_specification("docs/performance/policy-v3/unreviewed.json")
        elif drift == "raw":
            target = tmp_path / SCOPE.spec_path
            target.parent.mkdir(parents=True)
            target.write_bytes((ROOT / SCOPE.spec_path).read_bytes() + b"\n")
            scopes.read_role_spec(tmp_path, scope_base=SCOPE.base)
        elif drift == "role":
            spec: dict[str, Any] = scopes.read_role_spec(ROOT, scope_base=SCOPE.base)
            spec["control_plane"]["src/real.py"] = "Caller cannot reclassify runtime as a control."
            scopes.validate_spec(spec, scope_base=SCOPE.base)
        else:
            binding = _binding(*_inventories())
            if drift == "digest":
                binding["role_spec_sha256"] = "f" * 64
            scopes.validate_scope_binding(
                scopes.BASE if drift == "report_scope" else SCOPE.base, binding
            )

    with pytest.raises(ValueError, match=r"V4|v4"):
        attempt()


@pytest.mark.parametrize("drift", ["common", "missing", "new_treatment", "unknown", "harness"])
def test_registered_ec_scope_keeps_full_input_boundaries(drift: str) -> None:
    before, after = _inventories()
    if drift == "common":
        after["src/real.py"] = "f" * 64
    elif drift == "missing":
        del after["uv.lock"]
    elif drift == "new_treatment":
        before[next(iter(SCOPE.new_treatment))] = "f" * 64
    elif drift == "unknown":
        after["data/new-unreviewed.json"] = "f" * 64
    else:
        after["tests/timing_plugin.py"] = "f" * 64
    with pytest.raises(ValueError, match=r"V4|True common"):
        _binding(before, after)


@pytest.mark.parametrize(("side", "index"), [(s, n) for s in ("base", "head") for n in range(3)])
@pytest.mark.parametrize("missing", ["tree", "sample"])
def test_registered_scope_requires_every_real_sample_and_complete_tree(
    side: str, index: int, missing: str
) -> None:
    report, specification, binding = _report()
    if missing == "tree":
        report["generated_output_binding"][side][index].popitem()
    else:
        report[side]["samples"]["orphan-write-independent-check"].pop(index)
    with pytest.raises(ValueError, match=r"samples missing|complete exact generated trees"):
        _validate(report, specification, binding)


def test_registered_inventory_scans_ignored_source_and_rejects_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "src/warhammer40k_core"
    package.mkdir(parents=True)
    (package / "ignored.json").write_text("source bytes")
    monkeypatch.setattr(
        "tools.performance_tool_inputs_v4.subprocess.check_output", lambda *_a, **_k: b""
    )
    inventory, blobs = scopes.current_inventory(tmp_path, scope_base=SCOPE.base)
    assert inventory.keys() == blobs.keys() == {"src/warhammer40k_core/ignored.json"}
    (package / "alias.json").symlink_to("ignored.json")
    with pytest.raises(ValueError, match="regular files"):
        scopes.current_inventory(tmp_path, scope_base=SCOPE.base)


def _provenance_report() -> dict[str, Any]:
    """Complete binding fixture models the future six-tree document before measurement."""
    report, _, _ = _report()
    binding = report["input_binding"]
    historical = guard._historical_snapshot_inputs()
    binding["common"].update(historical)
    for side in ("base", "head"):
        binding["sides"][side]["inventory"].update(historical)
    return report


@pytest.mark.parametrize("kind", ["overlay", "spec", "report"])
def test_registered_provenance_projects_only_exact_historical_context(kind: str) -> None:
    path = (
        ROOT
        / {"overlay": provenance.EC_OVERLAY, "spec": SCOPE.spec_path, "report": SCOPE.report_path}[
            kind
        ]
    )
    raw = json.dumps(_provenance_report()).encode() if kind == "report" else path.read_bytes()
    original = bytes(raw)
    text = provenance.registered_provenance_text(ROOT, path, raw, guard._historical_snapshot_inputs)
    assert text is not None
    assert guard._retired_identity_tokens()[0] not in text
    assert raw == original
    assert (
        provenance.registered_provenance_text(
            ROOT, ROOT / "docs/unregistered.json", raw, guard._historical_snapshot_inputs
        )
        is None
    )


@pytest.mark.parametrize("drift", ["base", "binding", "historical_hash", "omission", "adjacent"])
def test_registered_report_provenance_rejects_drift_and_retains_adjacent_identity(
    drift: str,
) -> None:
    report = _provenance_report()
    if drift == "base":
        report["base_revision"] = scopes.BASE
    elif drift == "binding":
        report["input_binding"]["role_spec_sha256"] = "f" * 64
    elif drift in {"historical_hash", "omission"}:
        inventory = report["input_binding"]["common"]
        path = next(iter(guard._historical_snapshot_inputs()))
        if drift == "omission":
            del inventory[path]
        else:
            inventory[path] = "f" * 64
    else:
        report["unreviewed_active_identity"] = guard._retired_identity_tokens()[0]
    raw = json.dumps(report).encode()
    if drift == "adjacent":
        text = provenance.registered_provenance_text(
            ROOT, ROOT / SCOPE.report_path, raw, guard._historical_snapshot_inputs
        )
        assert text is not None
        assert guard._retired_identity_tokens()[0] in text
    else:
        with pytest.raises(ValueError, match=r"V4|Registered"):
            provenance.registered_provenance_text(
                ROOT, ROOT / SCOPE.report_path, raw, guard._historical_snapshot_inputs
            )


@pytest.mark.parametrize("relative", [provenance.EC_OVERLAY, SCOPE.spec_path])
def test_registered_exact_artifacts_reject_any_byte_drift(relative: str) -> None:
    path = ROOT / relative
    with pytest.raises(ValueError, match="exact reviewed bytes"):
        provenance.registered_provenance_text(
            ROOT, path, path.read_bytes() + b"\n", guard._historical_snapshot_inputs
        )


def test_old_scope_binding_is_retained_but_cannot_qualify_new_scope() -> None:
    report, specification, binding = fixtures._v4_report()
    fixtures._validate_v4(copy.deepcopy(report), specification, binding)
    with pytest.raises(ValueError, match="exact registered scope"):
        scopes.validate_scope_binding(SCOPE.base, binding)
