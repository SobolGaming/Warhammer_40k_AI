"""Finite reviewed admission controls; synthetic documents are never measurements."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
from tools import performance_tool_inputs as inputs
from tools import performance_tool_inputs_v4 as scopes
from tools import source_scope_provenance as provenance
from tools.performance_policy import validate_comparison

ROOT = Path(__file__).resolve().parents[2]
SCOPE = scopes.registered_scope(scopes.EC_BASE)


def _inventories() -> tuple[dict[str, str], dict[str, str]]:
    common = dict.fromkeys(
        SCOPE.required | SCOPE.harness | {"src/real.py", "contracts/README.md"}, "a" * 64
    )
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


def _historical_report() -> dict[str, Any]:
    old = scopes.registered_scope()
    raw = (ROOT / old.report_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "a4e21f5863cc46e33df79f2a03c9cc15a1bd575118e147bf32ebd298074b3f6a"
    )
    return inputs.input_object(json.loads(raw))


def historical_snapshot_inputs() -> dict[str, str]:
    common = _historical_report()["input_binding"]["common"]
    expected = {path: digest for path, digest in common.items() if f"{10}th-edition" in path}
    observed = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in expected}
    assert observed == expected
    assert inputs.digest(observed) == (
        "b877588db3f751f764fb74e9b9d5a1e3c3ab2525480e2954d2598520492b3557"
    )
    return observed


def retired_identity_tokens() -> tuple[str, ...]:
    return (f"warhammer-40000-{10}th", f"{10}th-edition")


def _report() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    binding = _binding(*_inventories())
    specification = json.loads((ROOT / inputs.MAP_PATH).read_bytes())["families"][inputs.FAMILY]
    side = {
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
    generated = {}
    for arm in ("base", "head"):
        tree = {
            path.removeprefix("contracts/"): digest
            for path, digest in binding["sides"][arm]["inventory"].items()
            if path.startswith("contracts/")
        }
        generated[arm] = [dict(tree) for _ in range(3)]
    report: dict[str, Any] = {
        "policy": "rules-engine-performance-v3",
        "family": inputs.FAMILY,
        "workload_id": inputs.WORKLOAD_ID,
        "base_revision": SCOPE.base,
        "head_runtime_build_id": side["runtime_build_id"],
        "head_input_digest": "e" * 64,
        "budget_profile": "current-change-relative-v1",
        "base": copy.deepcopy(side),
        "head": copy.deepcopy(side),
        "historical_failures": [],
        "input_binding": binding,
        "generated_output_binding": generated,
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

    def empty_git(command: list[str], *, cwd: Path) -> bytes:
        assert command[:2] == ["git", "ls-files"]
        assert cwd == tmp_path
        return b""

    monkeypatch.setattr("tools.performance_tool_inputs_v4.subprocess.check_output", empty_git)
    inventory, blobs = scopes.current_inventory(tmp_path, scope_base=SCOPE.base)
    assert inventory.keys() == blobs.keys() == {"src/warhammer40k_core/ignored.json"}
    (package / "alias.json").symlink_to("ignored.json")
    with pytest.raises(ValueError, match="regular files"):
        scopes.current_inventory(tmp_path, scope_base=SCOPE.base)


def _provenance_report() -> dict[str, Any]:
    """Complete binding fixture models the future six-tree document before measurement."""
    report, _, _ = _report()
    binding = report["input_binding"]
    historical = historical_snapshot_inputs()
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
    text = provenance.registered_provenance_text(ROOT, path, raw, historical_snapshot_inputs)
    assert text is not None
    assert not any(token in text for token in retired_identity_tokens())
    assert raw == original
    assert (
        provenance.registered_provenance_text(
            ROOT, ROOT / "docs/unregistered.json", raw, historical_snapshot_inputs
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
        path = next(iter(historical_snapshot_inputs()))
        if drift == "omission":
            del inventory[path]
        else:
            inventory[path] = "f" * 64
    else:
        report["unreviewed_active_identity"] = retired_identity_tokens()[0]
    raw = json.dumps(report).encode()
    if drift == "adjacent":
        text = provenance.registered_provenance_text(
            ROOT, ROOT / SCOPE.report_path, raw, historical_snapshot_inputs
        )
        assert text is not None
        assert retired_identity_tokens()[0] in text
    else:
        with pytest.raises(ValueError, match=r"V4|Registered"):
            provenance.registered_provenance_text(
                ROOT, ROOT / SCOPE.report_path, raw, historical_snapshot_inputs
            )


@pytest.mark.parametrize("relative", [provenance.EC_OVERLAY, SCOPE.spec_path])
def test_registered_exact_artifacts_reject_any_byte_drift(relative: str) -> None:
    path = ROOT / relative
    with pytest.raises(ValueError, match="exact reviewed bytes"):
        provenance.registered_provenance_text(
            ROOT, path, path.read_bytes() + b"\n", historical_snapshot_inputs
        )


def test_old_scope_binding_is_retained_but_cannot_qualify_new_scope() -> None:
    report = _historical_report()
    binding = report["input_binding"]
    specification = json.loads((ROOT / inputs.MAP_PATH).read_bytes())["families"][inputs.FAMILY]
    specification["input_binding"] = {
        "schema": scopes.SCHEMA,
        "role_specification": scopes.SPEC_PATH,
    }
    scopes.validate_scope_binding(scopes.BASE, binding)
    validate_comparison(
        report,
        base=scopes.BASE,
        runtime_id=report["head_runtime_build_id"],
        input_digest=report["head_input_digest"],
        family=inputs.FAMILY,
        specification=specification,
        base_runtime_id=report["base"]["runtime_build_id"],
        expected_inputs={
            key: report["head"][key] for key in ("lock_sha256", "workload_sha256", "fixture_sha256")
        },
        expected_binding=binding,
    )
    with pytest.raises(ValueError, match="exact registered scope"):
        scopes.validate_scope_binding(SCOPE.base, binding)


def test_provenance_registration_is_immutable_and_resolves_all_closed_contexts() -> None:
    record = provenance.PROVENANCE_RECORDS[0]
    for path in (record.overlay_path, SCOPE.spec_path, SCOPE.report_path):
        assert provenance.registered_provenance_context(path) == (record, SCOPE)
    assert provenance.registered_provenance_context("docs/unregistered.json") is None
    with pytest.raises(FrozenInstanceError):
        object.__getattribute__(record, "__setattr__")("scope_base", scopes.BASE)


@pytest.mark.parametrize("collision", ["overlay", "spec", "report", "duplicate"])
def test_provenance_registration_rejects_ambiguous_contexts(
    monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    record = provenance.PROVENANCE_RECORDS[0]
    if collision == "duplicate":
        records = (record, record)
    else:
        other = scopes.registered_scope(scopes.BASE)
        path = {
            "overlay": record.overlay_path,
            "spec": SCOPE.spec_path,
            "report": SCOPE.report_path,
        }[collision]
        records = (record, replace(record, scope_base=other.base, overlay_path=path))
    monkeypatch.setattr(provenance, "PROVENANCE_RECORDS", records)
    with pytest.raises(ValueError, match="contexts must be unique"):
        provenance.registered_provenance_context(record.overlay_path)


def test_provenance_registration_rejects_unknown_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    record = provenance.PROVENANCE_RECORDS[0]
    monkeypatch.setattr(provenance, "PROVENANCE_RECORDS", (replace(record, scope_base="f" * 40),))
    with pytest.raises(ValueError, match="registered"):
        provenance.registered_provenance_context(record.overlay_path)


def _acts_scope(monkeypatch: pytest.MonkeyPatch) -> scopes.ReviewedScope:
    import sys

    scope = scopes.registered_scope(scopes.ACTS_BASE)
    monkeypatch.setattr(sys.modules[__name__], "SCOPE", scope)
    return scope


def test_acts_registered_scope_preserves_real_six_sample_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = _acts_scope(monkeypatch)
    assert scope.base == "2490faab2c41915c54eb26aed04902165fbfc042"
    assert scopes.scope_for_specification(scope.spec_path) == scope
    assert (
        inputs.digest(scopes.read_role_spec(ROOT, scope_base=scope.base))
        == scope.spec_canonical_sha256
    )
    assert scope.harness == scopes.registered_scope(scopes.EC_BASE).harness
    assert scope.required == scopes.registered_scope(scopes.EC_BASE).required
    _validate(*_report())
    for kind in ("spec", "report"):
        path = ROOT / (scope.spec_path if kind == "spec" else scope.report_path)
        raw = path.read_bytes() if kind == "spec" else json.dumps(_provenance_report()).encode()
        text = provenance.registered_provenance_text(ROOT, path, raw, historical_snapshot_inputs)
        assert text is not None
        assert not any(token in text for token in retired_identity_tokens())
    resolved = provenance.registered_provenance_context(scope.spec_path)
    assert resolved is not None
    assert resolved[0].overlay_path == ""
    assert resolved[1] == scope


@pytest.mark.parametrize(
    "drift", ["common", "missing", "new_treatment", "unknown", "harness", "role", "base", "hash"]
)
def test_acts_scope_rejects_input_and_role_drift(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    scope = _acts_scope(monkeypatch)
    before, after = _inventories()

    def attempt() -> None:
        if drift == "role":
            spec: dict[str, Any] = scopes.read_role_spec(ROOT, scope_base=scope.base)
            spec["control_plane"]["src/unreviewed.py"] = (
                "Unreviewed runtime cannot become control plane."
            )
            scopes.validate_spec(spec, scope_base=scope.base)
        elif drift in {"base", "hash"}:
            binding = _binding(before, after)
            if drift == "hash":
                binding["role_spec_sha256"] = "f" * 64
            scopes.validate_scope_binding(
                scopes.EC_BASE if drift == "base" else scope.base, binding
            )
        else:
            if drift == "common":
                after["src/real.py"] = "f" * 64
            elif drift == "missing":
                del after["uv.lock"]
            elif drift == "new_treatment":
                before[next(iter(scope.new_treatment))] = "f" * 64
            elif drift == "unknown":
                after["src/unreviewed.py"] = "f" * 64
            else:
                after["tests/timing_plugin.py"] = "f" * 64
            _binding(before, after)

    with pytest.raises(ValueError, match=r"V4|v4|True common"):
        attempt()


@pytest.mark.parametrize(
    ("side", "index"), [(side, index) for side in ("base", "head") for index in range(3)]
)
@pytest.mark.parametrize("missing", ["tree", "sample"])
def test_acts_scope_requires_all_six_samples_and_output_trees(
    monkeypatch: pytest.MonkeyPatch,
    side: str,
    index: int,
    missing: str,
) -> None:
    _acts_scope(monkeypatch)
    report, specification, binding = _report()
    if missing == "tree":
        report["generated_output_binding"][side][index].popitem()
    else:
        report[side]["samples"]["orphan-write-independent-check"].pop(index)
    with pytest.raises(ValueError, match=r"samples missing|complete exact generated trees"):
        _validate(report, specification, binding)


@pytest.mark.parametrize(
    "drift", ["raw", "binding", "historical_hash", "omission", "adjacent", "duplicate"]
)
def test_acts_comparison_only_provenance_is_exact_and_closed(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    scope = _acts_scope(monkeypatch)
    if drift == "duplicate":
        monkeypatch.setattr(provenance, "COMPARISON_ONLY_SCOPE_BASES", (scope.base, scope.base))
        with pytest.raises(ValueError, match="contexts must be unique"):
            provenance.registered_provenance_context(scope.spec_path)
        return
    if drift == "raw":
        path = ROOT / scope.spec_path
        with pytest.raises(ValueError, match="exact reviewed bytes"):
            provenance.registered_provenance_text(
                ROOT, path, path.read_bytes() + b"\n", historical_snapshot_inputs
            )
        return
    report = _provenance_report()
    if drift == "binding":
        report["input_binding"]["role_spec_sha256"] = "f" * 64
    elif drift in {"historical_hash", "omission"}:
        inventory = report["input_binding"]["common"]
        reference = next(iter(historical_snapshot_inputs()))
        if drift == "omission":
            del inventory[reference]
        else:
            inventory[reference] = "f" * 64
    else:
        report["unreviewed_active_identity"] = retired_identity_tokens()[0]
    raw = json.dumps(report).encode()
    if drift == "adjacent":
        text = provenance.registered_provenance_text(
            ROOT, ROOT / scope.report_path, raw, historical_snapshot_inputs
        )
        assert text is not None
        assert retired_identity_tokens()[0] in text
    else:
        with pytest.raises(ValueError, match=r"V4|Registered"):
            provenance.registered_provenance_text(
                ROOT, ROOT / scope.report_path, raw, historical_snapshot_inputs
            )


def test_defiler_scope_preserves_closed_inputs_provenance_and_six_real_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    scope = scopes.registered_scope(scopes.DEFILER_BASE)
    monkeypatch.setattr(sys.modules[__name__], "SCOPE", scope)
    assert scope.base == "c15bd1564bd62a7c1ba9069a5ee6bbc7a6b94ce8"
    assert scope.new_treatment == frozenset()
    assert scope.harness == scopes.registered_scope(scopes.ACTS_BASE).harness
    assert scope.required == scopes.registered_scope(scopes.ACTS_BASE).required
    assert scopes.scope_for_specification(scope.spec_path) == scope
    assert (
        inputs.digest(scopes.read_role_spec(ROOT, scope_base=scope.base))
        == scope.spec_canonical_sha256
    )
    _validate(*_report())
    for side in ("base", "head"):
        for index in range(3):
            report, specification, binding = _report()
            report[side]["samples"]["orphan-write-independent-check"].pop(index)
            with pytest.raises(ValueError, match="samples missing"):
                _validate(report, specification, binding)
    before, after = _inventories()
    after["src/real.py"] = "f" * 64
    with pytest.raises(ValueError, match=r"True common|V4"):
        _binding(before, after)
    for kind in ("spec", "report"):
        path = ROOT / (scope.spec_path if kind == "spec" else scope.report_path)
        raw = path.read_bytes() if kind == "spec" else json.dumps(_provenance_report()).encode()
        text = provenance.registered_provenance_text(ROOT, path, raw, historical_snapshot_inputs)
        assert text is not None
        assert not any(token in text for token in retired_identity_tokens())
    context = provenance.registered_provenance_context(scope.spec_path)
    assert context is not None
    assert context[0].overlay_path == ""
    assert context[1] == scope


def test_current_ec_overlay_projects_only_exact_historical_base(tmp_path: Path) -> None:
    path = ROOT / provenance.CURRENT_EC_OVERLAY
    raw = path.read_bytes()
    projected = provenance.registered_provenance_text(ROOT, path, raw, historical_snapshot_inputs)
    assert projected is not None
    payload = json.loads(projected)
    assert "version" not in payload["base_source_package_id"]
    assert payload["target_edition"] == "warhammer-40000-11th"
    assert path.read_bytes() == raw
    assert (
        provenance.registered_provenance_text(
            ROOT, ROOT / "other-overlay.json", raw, historical_snapshot_inputs
        )
        is None
    )
    for mutation in ("base_source_package_id", "target_edition", "adjacent_identity"):
        changed = json.loads(raw)
        changed[mutation] = retired_identity_tokens()[0]
        with pytest.raises(ValueError, match="exact reviewed bytes"):
            provenance.registered_provenance_text(
                ROOT, path, json.dumps(changed).encode(), historical_snapshot_inputs
            )
    linked = tmp_path / provenance.CURRENT_EC_OVERLAY
    linked.parent.mkdir(parents=True)
    linked.symlink_to(path)
    with pytest.raises(ValueError, match="exact reviewed bytes"):
        provenance.registered_provenance_text(tmp_path, linked, raw, historical_snapshot_inputs)
