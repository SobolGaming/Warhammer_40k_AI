"""Cheap role/schema controls; synthetic numbers are never production evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from scripts.source_reuse_experiment import (
    optional_metadata,
    pytest_command,
    retained_contract_tree,
    validate_paths,
    validate_test_command,
)
from tools.performance_policy import POLICY, runtime_inputs, validate_comparison
from tools.performance_tool_inputs import (
    APPLICABILITY,
    AUDIT_INPUTS,
    AUDIT_MANIFEST,
    AUDIT_PDF,
    BUILDER,
    CONTROL,
    DIAGNOSTICS,
    FAMILY,
    HARNESS,
    INDEX,
    REPORT_ARCHIVE,
    REQUIRED,
    SCHEMA,
    SPEC_ARCHIVE,
    SPEC_PATH,
    TREATMENT,
    WORKLOAD,
    WORKLOAD_ID,
    binding_enabled,
    classify_inputs,
    comparison_inputs,
    digest,
    read_role_spec,
    retained_tool_comparison_inputs,
    validate_audit_manifest,
    validate_spec,
)

BASE = "a" * 40
HEAD = "b" * 40
BUILD = "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "1" * 64
BASE_BUILD = "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "2" * 64


def _spec() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "workload": WORKLOAD,
        "treatment": sorted(TREATMENT),
        "control_plane": dict.fromkeys(CONTROL, "Synthetic declared non-workload control"),
        "required_dependencies": sorted(REQUIRED),
        "harness": sorted(HARNESS),
    }


def _inventories() -> tuple[dict[str, str], dict[str, str]]:
    common = dict.fromkeys(
        REQUIRED | {"tests/shared.py", "src/rules.json", "contracts/examples/view.json"}, "a" * 64
    )
    return {**common, BUILDER: "1" * 64}, {**common, **dict.fromkeys(TREATMENT | CONTROL, "2" * 64)}


def _binding(before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    harness = {p: after[p] for p in HARNESS}
    return classify_inputs(
        spec=_spec(),
        base=before,
        head=after,
        base_revision=BASE,
        head_revision=HEAD,
        head_input_digest="inputs",
        harness_base=harness,
        harness_head=harness,
    )


def _report(binding: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    side: dict[str, object] = {
        "runtime_build_id": BUILD,
        "host": {
            "cpu": "synthetic fixture",
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
    before = copy.deepcopy(side)
    before["runtime_build_id"] = BASE_BUILD
    spec: dict[str, object] = {
        "budget_profile": "current-change-relative-v1",
        "workload_id": WORKLOAD_ID,
        "driver": WORKLOAD,
        "cases": ["orphan-write-independent-check"],
        "samples_per_case": 3,
        "input_binding": {"schema": SCHEMA, "role_specification": SPEC_PATH},
    }
    report: dict[str, object] = {
        "policy": POLICY,
        "family": FAMILY,
        "workload_id": WORKLOAD_ID,
        "base_revision": BASE,
        "head_runtime_build_id": BUILD,
        "head_input_digest": "inputs",
        "budget_profile": "current-change-relative-v1",
        "base": before,
        "head": side,
        "historical_failures": [],
        "input_binding": copy.deepcopy(binding),
    }
    return report, spec


def _validate(
    report: dict[str, object],
    spec: dict[str, object],
    binding: dict[str, object] | None,
    *,
    family: str = FAMILY,
) -> list[dict[str, object]]:
    return validate_comparison(
        report,
        base=BASE,
        runtime_id=BUILD,
        input_digest="inputs",
        family=family,
        specification=spec,
        base_runtime_id=BASE_BUILD,
        expected_inputs={
            "lock_sha256": "lock",
            "workload_sha256": "workload",
            "fixture_sha256": cast(str, cast(dict[str, object], report["head"])["fixture_sha256"]),
        },
        expected_binding=binding,
    )


def test_truthful_treatment_and_six_diagnostics_keep_independent_identity() -> None:
    before, after = _inventories()
    binding = _binding(before, after)
    sides = cast(dict[str, dict[str, object]], binding["sides"])
    assert cast(dict[str, object], sides["base"]["implementation"])[INDEX] is None
    assert cast(dict[str, object], sides["base"]["implementation"])[BUILDER] == "1" * 64
    assert cast(dict[str, object], sides["head"]["implementation"])[BUILDER] == "2" * 64
    assert set(cast(dict[str, object], sides["head"]["control_plane"])) >= DIAGNOSTICS
    report, spec = _report(binding)
    assert _validate(report, spec, binding) == []


@pytest.mark.parametrize(
    "path",
    [
        WORKLOAD,
        "tests/shared.py",
        "src/rules.json",
        "contracts/examples/view.json",
        "uv.lock",
        "scripts/unknown.py",
        "tools/unknown.py",
        *sorted(AUDIT_INPUTS),
    ],
)
@pytest.mark.parametrize("operation", ["change", "delete"])
def test_true_common_change_or_unknown_dependency_rejected(path: str, operation: str) -> None:
    before, after = _inventories()
    if operation == "delete":
        before.setdefault(path, "a" * 64)
        after.pop(path, None)
    else:
        after[path] = "9" * 64
    with pytest.raises(ValueError, match=r"common|lacks"):
        _binding(before, after)


@pytest.mark.parametrize(
    "mutation", ["builder_missing", "head_helper_missing", "base_helper_present"]
)
def test_only_verified_base_helper_absence_is_accepted(mutation: str) -> None:
    before, after = _inventories()
    if mutation == "builder_missing":
        del before[BUILDER]
    elif mutation == "head_helper_missing":
        del after[INDEX]
    else:
        before[INDEX] = "3" * 64
    with pytest.raises(ValueError, match="absence"):
        _binding(before, after)


@pytest.mark.parametrize(
    "mutation",
    ["absolute", "traversal", "duplicate", "overlap", "used_fixture", "schema", "extra_key"],
)
def test_role_specification_rejects_unreviewed_or_ambiguous_exclusions(mutation: str) -> None:
    spec = _spec()
    if mutation in {"absolute", "traversal", "duplicate"}:
        cast(list[str], spec["treatment"]).append(
            {"absolute": "/tmp/x", "traversal": "../x", "duplicate": BUILDER}[mutation]
        )
    elif mutation in {"overlap", "used_fixture"}:
        cast(dict[str, str], spec["control_plane"])[
            BUILDER if mutation == "overlap" else WORKLOAD
        ] = "Incorrectly classified actual workload"
    else:
        spec[mutation] = "invalid"
    with pytest.raises(ValueError, match=r"role|specification"):
        validate_spec(spec)


@pytest.mark.parametrize(
    "field", ["sides", "common", "harness", "role_spec_sha256", "head_input_digest"]
)
def test_stale_swapped_or_omitted_binding_is_rejected(field: str) -> None:
    binding = _binding(*_inventories())
    report, spec = _report(binding)
    observed = cast(dict[str, object], report["input_binding"])
    if field == "sides":
        sides = cast(dict[str, object], observed[field])
        sides["base"], sides["head"] = sides["head"], sides["base"]
    elif field == "common":
        del cast(dict[str, object], observed[field])[WORKLOAD]
    else:
        observed[field] = "stale"
    with pytest.raises(ValueError, match="input binding"):
        _validate(report, spec, binding)
    with pytest.raises(ValueError, match="input binding"):
        _validate(report, spec, None)


def test_external_harness_must_match_both_arms_and_actual_candidate() -> None:
    before, after = _inventories()
    harness = {p: after[p] for p in HARNESS}
    wrong = {**harness, next(iter(HARNESS)): "9" * 64}
    for left, right in ((harness, wrong), (wrong, wrong)):
        with pytest.raises(ValueError, match=r"harness|Harness"):
            classify_inputs(
                spec=_spec(),
                base=before,
                head=after,
                base_revision=BASE,
                head_revision=HEAD,
                head_input_digest="inputs",
                harness_base=left,
                harness_head=right,
            )


def test_legacy_schema_and_numeric_budget_remain_strict() -> None:
    binding = _binding(*_inventories())
    report, spec = _report(binding)
    with pytest.raises(ValueError, match="unsupported"):
        _validate(report, spec, binding, family="reconstruction")
    del spec["input_binding"]
    with pytest.raises(ValueError, match="unrelated"):
        _validate(report, spec, binding, family="reconstruction")
    with pytest.raises(ValueError, match="Unexpected or missing"):
        _validate(report, spec, None, family="reconstruction")
    assert not binding_enabled("reconstruction", spec)
    report, spec = _report(binding)
    samples = cast(dict[str, list[float]], cast(dict[str, object], report["head"])["samples"])
    samples["orphan-write-independent-check"] = [2.0, 2.0, 2.0]
    with pytest.raises(ValueError, match="budget exceeded"):
        _validate(report, spec, binding)
    samples["orphan-write-independent-check"] = [1.0, 1.0]
    with pytest.raises(ValueError, match="samples missing"):
        _validate(report, spec, binding)


def test_external_command_preflight_rejects_changed_node_workers_and_coverage(
    tmp_path: Path,
) -> None:
    root, output = tmp_path / "head", tmp_path / "results"
    command = pytest_command(root, output)
    validate_test_command(command, root, output, cheap=False)
    for old, new in (("0", "4"), ("--no-cov", "--cov"), ("pytest", "other")):
        changed = [new if part == old else part for part in command]
        with pytest.raises(ValueError, match="exact"):
            validate_test_command(changed, root, output, cheap=False)
    with pytest.raises(ValueError, match="exact"):
        validate_test_command([*command, "--maxfail=1"], root, output, cheap=False)


def test_external_paths_require_owned_exact_destinations(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    base = tmp_path / "reuse-base"
    harness = tmp_path / "reuse-harness"
    output = tmp_path / "source-reuse-output"
    validate_paths(base, workspace, harness, output, tmp_path, workspace)
    for wrong in (workspace, base, tmp_path.parent, tmp_path / "other"):
        with pytest.raises(ValueError, match="isolated"):
            validate_paths(base, workspace, harness, wrong, tmp_path, workspace)


def test_actual_git_binding_rejects_stale_source_but_allows_evidence_only_descendant(
    tmp_path: Path,
) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "user.name=Role Test", "-c", "user.email=test@example.invalid", *args],
            cwd=tmp_path,
            text=True,
        ).strip()

    def write(path: str, content: bytes = b"common fixture\n") -> None:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    git("init", "--quiet")
    git("config", "core.autocrlf", "false")
    for path in REQUIRED | {BUILDER, "src/corpus.py", "contracts/README.md"}:
        write(path)
    write(AUDIT_MANIFEST, json.dumps({"source_pdf_filename": Path(AUDIT_PDF).name}).encode())
    git("add", ".")
    git("commit", "--quiet", "-m", "base")
    base = git("rev-parse", "HEAD")
    for path in CONTROL | TREATMENT:
        write(path, b"head implementation or control\n")
    write(SPEC_PATH, json.dumps(_spec()).encode())
    git("add", ".")
    git("commit", "--quiet", "-m", "measured head")
    head = git("rev-parse", "HEAD")
    first = comparison_inputs(
        tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=head
    )
    write("docs/performance/current/evidence.json", b"evidence-only descendant\n")
    git("add", ".")
    git("commit", "--quiet", "-m", "evidence")
    assert (
        comparison_inputs(
            tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=head
        )
        == first
    )
    with pytest.raises(ValueError, match="Measured head"):
        comparison_inputs(
            tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=base
        )
    for path in sorted(AUDIT_INPUTS):
        previous = (tmp_path / path).read_bytes()
        write(path, previous + b" ")
        with pytest.raises(ValueError, match="Measured head"):
            comparison_inputs(
                tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=head
            )
        (tmp_path / path).unlink()
        with pytest.raises(ValueError, match="Measured head"):
            comparison_inputs(
                tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=head
            )
        write(path, previous)
    write("src/corpus.py", b"changed true source\n")
    with pytest.raises(ValueError, match="Measured head"):
        comparison_inputs(
            tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=head
        )
    write("src/corpus.py")
    write(".gitignore", b"src/ignored.py\n")
    git("add", ".gitignore")
    git("commit", "--quiet", "-m", "ignore metadata")
    write("src/ignored.py", b"unexpected source corpus member\n")
    with pytest.raises(ValueError, match="Measured head"):
        comparison_inputs(
            tmp_path, base=base, family=FAMILY, head_input_digest="inputs", measured_head=head
        )


def test_optional_host_metadata_preserves_value_and_observed_missing_files(tmp_path: Path) -> None:
    for name in ("cpu.max", "memory.max"):
        path = tmp_path / name
        result = optional_metadata(path)
        assert result["value"] is None
        assert result["status"] == "unavailable"
        assert result["path"] == str(path)
        assert result["error"] == "FileNotFoundError"
        assert result["reason"]
        path.write_text("100000 100000\n")
        assert optional_metadata(path) == {
            "path": str(path),
            "status": "available",
            "value": "100000 100000\n",
            "error": None,
            "reason": None,
        }


def test_optional_host_metadata_records_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_path: Path) -> str:
        raise PermissionError("permission denied by synthetic metadata fixture")

    monkeypatch.setattr(Path, "read_text", denied)
    result = optional_metadata(tmp_path / "cpu.max")
    assert result["value"] is None
    assert result["status"] == "unavailable"
    assert result["error"] == "PermissionError"
    assert result["reason"] == "permission denied by synthetic metadata fixture"


def _directory_alias(link: Path, target: Path) -> None:
    if os.name == "nt":
        # Windows directory junctions exercise real canonical aliases without symlink privilege.
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True
        )
    else:
        link.symlink_to(target, target_is_directory=True)


def test_retained_output_accepts_numbered_directory_and_current_alias(tmp_path: Path) -> None:
    owned = tmp_path / "tmp"
    numbered = owned / "test_external0"
    contract = numbered / "write-mode-output/contracts"
    contract.mkdir(parents=True)
    _directory_alias(owned / "test_externalcurrent", numbered)
    assert retained_contract_tree(owned) == contract.resolve()
    (owned / "test_external1/write-mode-output/contracts").mkdir(parents=True)
    with pytest.raises(ValueError, match="one distinct"):
        retained_contract_tree(owned)


def test_retained_output_rejects_escaping_and_missing_targets(tmp_path: Path) -> None:
    owned = tmp_path / "tmp"
    contract = owned / "test_external0/write-mode-output/contracts"
    contract.mkdir(parents=True)
    outside = tmp_path / "outside/write-mode-output/contracts"
    outside.mkdir(parents=True)
    alias = owned / "test_externalcurrent"
    _directory_alias(alias, tmp_path / "outside")
    with pytest.raises(ValueError, match="inside the owned"):
        retained_contract_tree(owned)
    if os.name == "nt":
        alias.rmdir()
    else:
        alias.unlink()
    broken = owned / "test_external1/write-mode-output/contracts"
    broken.parent.mkdir(parents=True)
    _directory_alias(broken, tmp_path / "missing")
    with pytest.raises(FileNotFoundError):
        retained_contract_tree(owned)


@pytest.mark.parametrize("reference", ["../outside.pdf", "/tmp/outside.pdf", "different.pdf", None])
def test_audit_manifest_rejects_unpinned_pdf_reference(reference: str | None) -> None:
    with pytest.raises(ValueError, match="exact required common PDF"):
        validate_audit_manifest(json.dumps({"source_pdf_filename": reference}).encode())
    validate_audit_manifest(json.dumps({"source_pdf_filename": Path(AUDIT_PDF).name}).encode())


def _archival_fixture(tmp_path: Path) -> tuple[dict[str, str], dict[str, object]]:
    root = Path(__file__).resolve().parents[2]
    for name in (SPEC_ARCHIVE, REPORT_ARCHIVE, APPLICABILITY):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    # Read-only access to immutable Git objects; this fixture performs no Git mutations.
    (tmp_path / ".git").write_text(f"gitdir: {(root / '.git').as_posix()}\n")
    return runtime_inputs(root), json.loads((root / REPORT_ARCHIVE).read_bytes())


def test_archival_provenance_preserves_exact_measured_inventory(tmp_path: Path) -> None:
    from tools.performance_tool_inputs import MEASURED_BASE, MEASURED_INPUT_DIGEST

    current, report = _archival_fixture(tmp_path)
    measured, proof_sha = retained_tool_comparison_inputs(
        tmp_path, current=current, report=report, base=MEASURED_BASE
    )
    assert digest(measured) == MEASURED_INPUT_DIGEST
    assert proof_sha == hashlib.sha256((tmp_path / APPLICABILITY).read_bytes()).hexdigest()
    assert read_role_spec(tmp_path)["required_dependencies"] == sorted(REQUIRED)


@pytest.mark.parametrize(
    "path", ["src/unapproved.py", BUILDER, WORKLOAD, "scripts/ci_attribution_supervisor.py"]
)
def test_archival_provenance_rejects_changed_measured_inputs(tmp_path: Path, path: str) -> None:
    from tools.performance_tool_inputs import MEASURED_BASE

    current, report = _archival_fixture(tmp_path)
    current[path] = "f" * 64
    proof_path = tmp_path / APPLICABILITY
    proof = json.loads(proof_path.read_bytes())
    proof["current_input_digest"] = digest(current)
    proof_path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="Unapproved measured input"):
        retained_tool_comparison_inputs(
            tmp_path, current=current, report=report, base=MEASURED_BASE
        )


@pytest.mark.parametrize(
    "mutation", ["spec", "report", "proof", "before", "after", "scope", "base"]
)
def test_archival_provenance_rejects_identity_drift(tmp_path: Path, mutation: str) -> None:
    from tools.performance_tool_inputs import MEASURED_BASE

    current, report = _archival_fixture(tmp_path)
    base = MEASURED_BASE
    if mutation in {"spec", "report"}:
        target = tmp_path / (SPEC_ARCHIVE if mutation == "spec" else REPORT_ARCHIVE)
        target.write_bytes(target.read_bytes() + b" ")
    elif mutation == "base":
        base = "a" * 40
    else:
        target = tmp_path / APPLICABILITY
        proof = json.loads(target.read_bytes())
        if mutation == "proof":
            proof["current_input_digest"] = "f" * 64
        elif mutation == "scope":
            proof["changes"]["src/unapproved.py"] = {"before": None, "after": "f" * 64}
        else:
            proof["changes"]["tools/performance_tool_inputs.py"][mutation] = "f" * 64
        target.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match=r"changed|drift"):
        retained_tool_comparison_inputs(tmp_path, current=current, report=report, base=base)


def test_archival_role_layout_rejects_ambiguous_original(tmp_path: Path) -> None:
    _archival_fixture(tmp_path)
    (tmp_path / SPEC_PATH).write_bytes((tmp_path / SPEC_ARCHIVE).read_bytes())
    with pytest.raises(ValueError, match="Ambiguous"):
        read_role_spec(tmp_path)


@pytest.mark.parametrize("active", [None, "historical-json", "active-source", "active-json"])
def test_original_edition_assertion_preserves_active_reference_boundary(
    tmp_path: Path, active: str | None
) -> None:
    root = Path(__file__).resolve().parents[2]
    original = "tests/code_quality/test_phase14a_source_identity.py"
    target = tmp_path / original
    target.parent.mkdir(parents=True)
    target.write_bytes((root / original).read_bytes())
    for name in (SPEC_ARCHIVE, REPORT_ARCHIVE):
        archived = tmp_path / name
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes((root / name).read_bytes())
        if active == "historical-json":
            archived.with_suffix("").write_bytes(archived.read_bytes())
    if active in {"active-source", "active-json"}:
        target = tmp_path / (
            "src/obsolete.py" if active == "active-source" else "docs/obsolete.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps("warhammer_40000_" + "1" + "0" + "th"))
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-c",
            str(config),
            original + "::test_active_code_tests_and_docs_do_not_reference_retired_edition_ids",
            "-q",
            "-n",
            "0",
            "--no-cov",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == (0 if active is None else 1), result.stdout + result.stderr
    if active is not None:
        assert "AssertionError" in result.stdout
