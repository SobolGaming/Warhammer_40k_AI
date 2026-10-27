"""Exact migration proof cannot exempt arbitrary source or rewrite measurements."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping
from copy import deepcopy
from functools import wraps
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest
from tools import cumulative_preservation as migration
from tools import performance_policy as policy
from tools import performance_preflight as preflight
from tools import performance_qualification_successor as successor
from tools import performance_reconstruction_campaign as reconstruction
from tools import performance_tool_inputs as original
from tools import performance_tool_inputs_v2 as fresh

ROOT = Path(__file__).resolve().parents[2]


def read_archive() -> dict[str, object]:
    return migration.read_archive(ROOT)


def _inputs(archive: dict[str, object], name: str) -> dict[str, str]:
    return cast(dict[str, str], archive[name])


def _controls() -> dict[str, str]:
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in migration.CONTROLS}


def _current(archive: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    return migration.expected_inputs(ROOT)


@pytest.fixture(scope="session", autouse=True)
def private_expected_input_reference() -> Iterator[None]:
    """Reuse only fixed expected test data; all production validation stays fresh."""
    original_current = _current
    reference: tuple[Mapping[str, str], Mapping[str, str]] | None = None

    def reference_inputs(archive: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
        nonlocal reference
        if reference is None:
            current, tools = original_current(archive)
            assert all(
                isinstance(key, str) and isinstance(value, str)
                for values in (current, tools)
                for key, value in values.items()
            )
            reference = MappingProxyType(dict(current)), MappingProxyType(dict(tools))
        return dict(reference[0]), dict(reference[1])

    with pytest.MonkeyPatch.context() as private:
        private.setattr(sys.modules[__name__], "_current", reference_inputs)
        try:
            yield
        finally:
            reference = None


@pytest.fixture(autouse=True)
def private_computation_scope(request: pytest.FixtureRequest) -> Iterator[None]:
    """Restore the temporary validator and callable before outer reporter hooks."""
    node = cast(pytest.Item, cast(Any, request).node)
    if not isinstance(node, pytest.Function):
        yield
        return
    original_test = node.obj
    original_verify = migration.verify_current_inventory

    @wraps(original_test)
    def run_original(*args: Any, **kwargs: Any) -> Any:
        @wraps(original_verify)
        def verify(root: Path, **values: Any) -> None:
            return preflight.ci60_computation(root, lambda: original_verify(root, **values))

        try:
            with pytest.MonkeyPatch.context() as private:
                private.setattr(migration, "verify_current_inventory", verify)
                return original_test(*args, **kwargs)
        finally:
            node.obj = original_test

    node.obj = run_original
    try:
        yield
    finally:
        node.obj = original_test


@pytest.fixture(scope="module")
def copied_migration(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("category-applicability")
    # Copy exact live inputs, including transitive fixtures and the new evidence
    # namespace. A read-only Git pointer retains authenticated object identity.
    shutil.copytree(
        ROOT,
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"
        ),
    )
    git_dir = (
        subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT)
        .decode()
        .strip()
    )
    (root / ".git").write_text("gitdir: " + git_dir + "\n", encoding="utf-8")
    return root


def test_actual_current_and_original_git_inventories_match_finite_cohorts() -> None:
    archive = read_archive()
    assert migration.applies(
        base=migration.BASE, runtime_id=reconstruction.RUNTIME, family="reconstruction"
    )
    current, tools = _current(archive)
    actual_current, actual_tools = migration.assessment_map_inputs(
        ROOT,
        archive=archive,
        current=policy.runtime_inputs(ROOT),
        tools=migration.current_tool_inventory(ROOT),
    )
    assert actual_current == current
    assert actual_tools == tools
    assert (
        migration.measured_snapshot(ROOT, migration.MEASURED)
        == archive["TOOL_MEASURED_INPUTS.json.txt"]
    )
    assert migration.measured_snapshot(ROOT, migration.BASE) == archive["TOOL_BASE_INPUTS.json.txt"]
    migration.verify_current_inventory(
        ROOT, archive=archive, current=current, tools=tools, controls=_controls()
    )
    assert (
        len(migration.verify_external_reads(ROOT, policy.object_value(archive[migration.EXTERNAL])))
        == 64
    )


def test_measured_binding_rebuilds_without_using_report_exclusions() -> None:
    archive = read_archive()
    before = migration.measured_snapshot(ROOT, migration.BASE)
    after = migration.measured_snapshot(ROOT, migration.MEASURED)
    harness = {p: after[p] for p in fresh.HARNESS}
    result = fresh.classify_inputs(
        spec=cast(dict[str, object], archive["MEASURED_ROLE_SPEC.json.txt"]),
        base=before,
        head=after,
        base_revision=migration.BASE,
        head_revision=migration.MEASURED,
        head_input_digest=original.digest(archive["POLICY_MEASURED_INPUTS.json.txt"]),
        harness_base=harness,
        harness_head=harness,
    )
    assert result == archive["MEASURED_BINDING.json.txt"]


def test_original_reconstruction_bridge_remains_separate() -> None:
    archive = read_archive()
    report = policy.read_object(ROOT / reconstruction.REPORT)
    measured, receipt = reconstruction.retained_inputs(
        ROOT,
        current=_inputs(archive, "POLICY_MEASURED_INPUTS.json.txt"),
        report=report,
        base=migration.BASE,
        runtime_id=reconstruction.RUNTIME,
    )
    assert original.digest(measured) == reconstruction.MEASURED_DIGEST
    assert original.digest(report) == reconstruction.REPORT_DIGEST
    assert len(receipt) == 64
    with pytest.raises(ValueError, match="Unreviewed"):
        reconstruction.retained_inputs(
            ROOT,
            current=_current(archive)[0],
            report=report,
            base=migration.BASE,
            runtime_id=reconstruction.RUNTIME,
        )


def test_direct_v2_api_still_rejects_migrated_current_source(tmp_path: Path) -> None:
    # The legacy API requires actual worker ancestry. A deliberately dirty
    # checkout at that genuine historical commit reaches its separate inventory
    # refusal; the cumulative qualification HEAD is never reparented or relabeled.
    root = tmp_path / "historical-dirty-checkout"
    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"
        ),
    )
    shutil.copytree(ROOT / ".git", root / ".git")
    subprocess.run(
        ["git", "update-ref", "--no-deref", "HEAD", migration.MEASURED], cwd=root, check=True
    )
    subprocess.run(["git", "read-tree", migration.MEASURED], cwd=root, check=True)
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
        == migration.MEASURED
    )
    with pytest.raises(ValueError, match="do not equal the current source inventory"):
        original.comparison_inputs(
            root,
            base=migration.BASE,
            family=original.FAMILY,
            head_input_digest=original.digest(policy.runtime_inputs(root)),
            measured_head=migration.MEASURED,
            schema=fresh.SCHEMA,
        )


@pytest.mark.parametrize("inventory", ["policy", "tools"])
@pytest.mark.parametrize("mutation", ["runtime", "lock", "driver", "extra", "remove", "control"])
def test_arbitrary_input_drift_is_not_a_migration(
    copied_migration: Path, inventory: str, mutation: str
) -> None:
    archive = read_archive()
    current, tools = _current(archive)
    target = current if inventory == "policy" else tools
    names = {
        "runtime": fresh.RUNTIME,
        "lock": "uv.lock",
        "driver": "scripts/measure_ingress_reconstruction.py",
        "extra": "tests/unreviewed_source.py",
        "remove": "tests/conftest.py",
        "control": "scripts/check_performance_policy.py",
    }
    if mutation == "remove":
        target.pop(names[mutation])
    else:
        target[names[mutation]] = "f" * 64
    with pytest.raises(ValueError, match="finite migration cohort"):
        migration.verify_current_inventory(
            copied_migration, archive=archive, current=current, tools=tools, controls=_controls()
        )


@pytest.mark.parametrize(
    "kind", ["successor", "archive", "reader", "mapping", "shard", "inventory"]
)
def test_real_file_tampering_is_rejected_after_warm_verification(
    copied_migration: Path, kind: str
) -> None:
    archive = read_archive()
    current, tools = _current(archive)
    files = _inputs(archive, "MIGRATION_FILES.json.txt")
    choices = {
        "successor": next(p for p in files if p.startswith("tests/rules") and "/test_" in p),
        "archive": next(p for p in files if "/baseline/" in p),
        "reader": "tests/category_migration_preservation.py",
        "mapping": "data/source_audits/category_migration/preservation.json",
        "shard": "ci/test_shards/shard-1.txt",
        "inventory": "data/source_audits/order135/current-inventory-category-migration.json",
    }
    migration.verify_current_inventory(
        copied_migration, archive=archive, current=current, tools=tools, controls=_controls()
    )
    path = copied_migration / choices[kind]
    before = path.read_bytes()
    try:
        path.write_bytes(before + b"\n# changed\n")
        with pytest.raises(ValueError, match="Reviewed migration source/data changed"):
            migration.verify_current_inventory(
                copied_migration,
                archive=archive,
                current=current,
                tools=tools,
                controls=_controls(),
            )
    finally:
        path.write_bytes(before)


@pytest.mark.parametrize("mutation", ["omit", "extra", "repin", "member"])
def testread_archive_manifest_cannot_be_rewritten(copied_migration: Path, mutation: str) -> None:
    directory = copied_migration / migration.ARCHIVE
    manifest = directory / "INVENTORY.json.txt"
    target = directory / "EXACT_INPUT_DELTAS.json.txt"
    before_manifest, before_target = manifest.read_bytes(), target.read_bytes()
    extra = directory / "unreviewed.txt"
    try:
        if mutation == "omit":
            target.unlink()
        elif mutation == "extra":
            extra.write_text("unreviewed", encoding="utf-8")
        else:
            target.write_bytes(before_target + b" ")
            if mutation == "repin":
                data = json.loads(before_manifest)
                data[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
                manifest.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match=r"migration|Migration"):
            migration.read_archive(copied_migration)
    finally:
        manifest.write_bytes(before_manifest)
        target.write_bytes(before_target)
        if extra.exists():
            extra.unlink()


@pytest.mark.parametrize("mutation", ["old_collector", "extraread_archive"])
def test_unexpected_membership_cannot_hide_outside_selected_inputs(
    copied_migration: Path, mutation: str
) -> None:
    archive = read_archive()
    current, tools = _current(archive)
    name = (
        "tests/unit/test_lifecycle_hooks.py"
        if mutation == "old_collector"
        else "data/source_audits/category_migration/extra.txt"
    )
    path = copied_migration / name
    assert not path.exists()
    try:
        path.write_text("unreviewed", encoding="utf-8")
        with pytest.raises(ValueError, match=r"reappeared|membership"):
            migration.verify_current_inventory(
                copied_migration,
                archive=archive,
                current=current,
                tools=tools,
                controls=_controls(),
            )
    finally:
        path.unlink()


@pytest.mark.parametrize("mutation", ["omit_delta", "runtime_as_migration", "new_control"])
def test_report_supplied_exemptions_cannot_extend_the_cohort(
    copied_migration: Path, mutation: str
) -> None:
    archive = deepcopy(read_archive())
    current, tools = _current(archive)
    controls = _controls()
    if mutation == "omit_delta":
        cast(dict[str, object], archive["EXACT_INPUT_DELTAS.json.txt"]).popitem()
    elif mutation == "runtime_as_migration":
        _inputs(archive, "POLICY_CURRENT_INPUTS.json.txt")[fresh.RUNTIME] = "f" * 64
    else:
        controls[fresh.RUNTIME] = "f" * 64
    with pytest.raises(ValueError, match=r"Exact296|Exact adapter"):
        migration.verify_current_inventory(
            copied_migration, archive=archive, current=current, tools=tools, controls=controls
        )


def test_unactivated_adapter_cannot_admit_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migration, "SOURCE_COMMIT", None)
    with pytest.raises(ValueError, match="awaits its reviewed source commit"):
        migration.retained_inputs(
            ROOT,
            current=policy.runtime_inputs(ROOT),
            report=policy.read_object(ROOT / reconstruction.REPORT),
            base=migration.BASE,
            runtime_id=reconstruction.RUNTIME,
        )


@pytest.mark.parametrize("mutation", ["base", "runtime", "family"])
def test_other_cohort_cannot_use_migration_applicability(mutation: str) -> None:
    report = policy.read_object(ROOT / reconstruction.REPORT)
    base, runtime = migration.BASE, reconstruction.RUNTIME
    if mutation == "base":
        base = "f" * 40
    elif mutation == "runtime":
        runtime += "-different"
    else:
        report["family"] = "other"
    assert not migration.applies(base=base, runtime_id=runtime, family=str(report["family"]))
    with pytest.raises(ValueError, match="another exact cohort"):
        migration.retained_inputs(ROOT, current={}, report=report, base=base, runtime_id=runtime)


@pytest.fixture
def frozen_controls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Real isolated Git bytes, no substituted Git results or engine objects."""
    root = tmp_path / "source-freeze"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    marker = b"\nSOURCE_COMMIT: str | None = None"
    for name in sorted(migration.CONTROLS | migration.SOURCE_ARCHIVES):
        raw = (ROOT / name).read_bytes()
        if name == migration.SELF and migration.SOURCE_COMMIT is not None:
            raw = raw.replace(
                f'\nSOURCE_COMMIT: str | None = "{migration.SOURCE_COMMIT}"'.encode(), marker, 1
            )
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    subprocess.run(["git", "-c", "core.autocrlf=false", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Isolated test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "Fixture source snapshot",
        ],
        cwd=root,
        check=True,
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    path = root / migration.SELF
    raw = path.read_bytes()
    assert raw.count(marker) == 1
    path.write_bytes(raw.replace(marker, f'\nSOURCE_COMMIT: str | None = "{revision}"'.encode(), 1))
    monkeypatch.setattr(migration, "SOURCE_COMMIT", revision)
    return root


def test_exact_source_freeze_allows_only_the_declared_anchor_literal(frozen_controls: Path) -> None:
    assert migration.reviewed_control_hashes(frozen_controls) == {
        p: hashlib.sha256((frozen_controls / p).read_bytes()).hexdigest()
        for p in migration.CONTROLS
    }


@pytest.mark.parametrize("name", sorted(migration.CONTROLS | migration.SOURCE_ARCHIVES))
def test_any_frozen_control_edit_is_rejected(frozen_controls: Path, name: str) -> None:
    path = frozen_controls / name
    path.write_bytes(path.read_bytes() + b"\n# unauthorized control change\n")
    with pytest.raises(ValueError, match="control bytes changed"):
        migration.reviewed_control_hashes(frozen_controls)


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_exact_compatibility_archive_membership_is_required(
    frozen_controls: Path, mutation: str
) -> None:
    migration.reviewed_control_hashes(frozen_controls)
    member = frozen_controls / sorted(migration.SOURCE_ARCHIVES)[0]
    if mutation == "missing":
        member.unlink()
    else:
        (member.parent / "unreviewed.txt").write_bytes(b"unreviewed")
    with pytest.raises(ValueError, match="compatibility archive membership changed"):
        migration.reviewed_control_hashes(frozen_controls)


def test_anchor_cannot_select_a_missing_revision(
    frozen_controls: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(migration, "SOURCE_COMMIT", "f" * 40)
    with pytest.raises(subprocess.CalledProcessError):
        migration.reviewed_control_hashes(frozen_controls)


@pytest.mark.parametrize("kind", ["catalog", "typescript", "package", "missing", "extra"])
def test_external_read_bytes_and_membership_are_live(copied_migration: Path, kind: str) -> None:
    archive = read_archive()
    proof = policy.object_value(archive[migration.EXTERNAL])
    expected = policy.object_value(proof["measured"])
    assert len(migration.verify_external_reads(copied_migration, proof)) == 64
    names = {
        "catalog": "docs/DECISION_SUBMISSION_CATALOG.md",
        "typescript": next(p for p in expected if p.endswith(".ts")),
        "package": "conformance/typescript/package.json",
        "missing": "docs/DECISION_SUBMISSION_CATALOG.md",
        "extra": "conformance/typescript/src/ignored-but-consumed.ts",
    }
    target = copied_migration / names[kind]
    before = target.read_bytes() if target.exists() else None
    ignore = copied_migration / ".gitignore"
    prior_ignore = ignore.read_bytes() if ignore.exists() else None
    try:
        if kind == "missing":
            target.unlink()
        else:
            target.write_bytes((before or b"") + b"\nchanged external input\n")
        if kind == "extra":
            ignore.write_text(names[kind] + "\n", encoding="utf-8")
            assert (
                subprocess.check_output(["git", "check-ignore", names[kind]], cwd=copied_migration)
                .decode()
                .strip()
                == names[kind]
            )
        with pytest.raises(ValueError, match="External-read current"):
            migration.verify_external_reads(copied_migration, proof)
    finally:
        if before is None:
            target.unlink()
        else:
            target.write_bytes(before)
        if kind == "extra":
            if prior_ignore is None:
                ignore.unlink()
            else:
                ignore.write_bytes(prior_ignore)


@pytest.mark.parametrize(
    "mutation", ["measured_revision", "base_revision", "measured", "base", "current_at_preparation"]
)
def test_external_proof_cannot_relabel_frozen_git_or_current_identities(mutation: str) -> None:
    proof = deepcopy(policy.object_value(read_archive()[migration.EXTERNAL]))
    if mutation.endswith("revision"):
        proof[mutation] = "f" * 40
    else:
        mapping = policy.object_value(proof[mutation])
        mapping[next(iter(mapping))] = "f" * 64
    with pytest.raises(ValueError, match=r"External-read|Frozen external"):
        migration.verify_external_reads(ROOT, proof)


def test_external_proof_is_separately_pinned_without_repinning_old_measurement_maps(
    copied_migration: Path,
) -> None:
    archive = copied_migration / migration.ARCHIVE
    target = archive / migration.EXTERNAL
    before = target.read_bytes()
    inventory = (archive / "INVENTORY.json.txt").read_bytes()
    measured = (archive / "POLICY_MEASURED_INPUTS.json.txt").read_bytes()
    try:
        target.write_bytes(before + b" ")
        with pytest.raises(ValueError, match="Independent external-read proof changed"):
            migration.read_archive(copied_migration)
        assert (archive / "INVENTORY.json.txt").read_bytes() == inventory
        assert (archive / "POLICY_MEASURED_INPUTS.json.txt").read_bytes() == measured
    finally:
        target.write_bytes(before)


@pytest.fixture
def assessment_map_root(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / migration.NAMESPACE, tmp_path / migration.NAMESPACE)
    target = tmp_path / original.MAP_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    # This fixture tests the preceding finite map proof after current extension admission.
    target.write_bytes(successor.prior_operation_map_bytes(ROOT))
    return tmp_path


def _map_inputs(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    digest = hashlib.sha256((root / original.MAP_PATH).read_bytes()).hexdigest()
    values = {original.MAP_PATH: digest, "src/unchanged.py": "a" * 64}
    return values.copy(), values.copy()


def test_assessment_map_proof_preserves_every_nonmap_input_and_caller_dictionary(
    assessment_map_root: Path,
) -> None:
    current, tools = _map_inputs(assessment_map_root)
    before_current, before_tools = current.copy(), tools.copy()
    archive = read_archive()
    old_sha = _inputs(archive, "POLICY_CURRENT_INPUTS.json.txt")[original.MAP_PATH]
    verified_current, verified_tools = migration.assessment_map_inputs(
        assessment_map_root, archive=archive, current=current, tools=tools
    )
    assert verified_current == before_current | {original.MAP_PATH: old_sha}
    assert verified_tools == before_tools | {original.MAP_PATH: old_sha}
    assert current == before_current
    assert tools == before_tools
    assert verified_current is not current
    assert verified_tools is not tools


@pytest.mark.parametrize(
    "mutation",
    ["current", "original", "proof", "missing", "extra", "family", "old_operation", "wildcard"],
)
def test_assessment_map_real_file_drift_rejects_even_with_reported_hashes_updated(
    assessment_map_root: Path, mutation: str
) -> None:
    directory = assessment_map_root / migration.ASSESSMENT_MAP
    live = assessment_map_root / original.MAP_PATH
    if mutation == "current":
        live.write_bytes(live.read_bytes() + b" ")
    elif mutation == "original":
        old = directory / "original-operation-map.json.txt"
        old.write_bytes(old.read_bytes() + b" ")
    elif mutation == "proof":
        proof_path = directory / "assessment-map-additions.json.txt"
        proof_path.write_bytes(proof_path.read_bytes() + b" ")
    elif mutation == "missing":
        (directory / "original-operation-map.json.txt").unlink()
    elif mutation == "extra":
        (directory / "unreviewed.json").write_text("{}", encoding="utf-8")
    else:
        value = policy.read_object(live)
        if mutation == "family":
            policy.object_value(value["families"]).clear()
        elif mutation == "old_operation":
            policy.object_value(value["operations"]).pop("runtime-manifest-build-reuse")
        else:
            operation = next(
                item
                for key, item in policy.object_value(value["operations"]).items()
                if key.startswith("ci-restructure-")
            )
            policy.object_value(operation)["paths"] = ["src/*"]
        live.write_text(json.dumps(value), encoding="utf-8")
        proof_path = directory / "assessment-map-additions.json.txt"
        proof = policy.read_object(proof_path)
        proof["current_sha256"] = hashlib.sha256(live.read_bytes()).hexdigest()
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
    current, tools = _map_inputs(assessment_map_root)
    with pytest.raises(ValueError, match=r"map|operation"):
        migration.assessment_map_inputs(
            assessment_map_root, archive=read_archive(), current=current, tools=tools
        )


@pytest.mark.parametrize("inventory", ["current", "tools"])
@pytest.mark.parametrize("mutation", ["omit", "forge"])
def test_assessment_map_actual_input_hashes_cannot_be_omitted_or_forged(
    assessment_map_root: Path, inventory: str, mutation: str
) -> None:
    current, tools = _map_inputs(assessment_map_root)
    target = current if inventory == "current" else tools
    if mutation == "omit":
        target.pop(original.MAP_PATH)
    else:
        target[original.MAP_PATH] = "f" * 64
    with pytest.raises(ValueError, match="input identities disagree"):
        migration.assessment_map_inputs(
            assessment_map_root, archive=read_archive(), current=current, tools=tools
        )
