"""Versioned actual-byte input roles for one external-contract tool workload."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import cast

FAMILY = "external_contract_source_reuse"
SCHEMA = "tool-input-roles-v1"
WORKLOAD = "tests/code_quality/test_phase18m_conformance_boundary.py"
WORKLOAD_ID = "external-contract-orphan-write-independent-check-v1"
SPEC_PATH = "docs/performance/policy-v3/source-token-input-roles.json"
SPEC_ARCHIVE = SPEC_PATH + ".txt"
REPORT_ARCHIVE = "docs/performance/current/source-token-reuse-v1.json.txt"
SPEC_SHA256 = "0a980b4370c0bc6284cb87e9bc257a52e8d46096b650b2f807163104cfffe563"
REPORT_SHA256 = "24bd1ebd1890a3b8b15bcc6a9a8b1c07e0d520875fad37338f1e77910e9659fb"
MEASURED_HEAD = "1009fd82e077239abf854e9179d87b0affe8186e"
MEASURED_BASE = "22a12094cfe3839d8fe8c5296ec0a7e7d32abade"
MEASURED_INPUT_DIGEST = "78464b628eea4fbff3aa8edabe299bd1a24ab8ef253f5635c5bde0db2307bd80"
APPLICABILITY = "docs/performance/policy-v3/source-token-provenance-applicability.json"
PROVENANCE_CONTROLS = frozenset(
    {
        "tools/performance_tool_inputs.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_performance_tool_inputs.py",
    }
)
MAP_PATH = "docs/performance/policy-v3/operation-map.json"
BUILDER = "scripts/build_external_contract.py"
INDEX = "scripts/proposal_source_index.py"
TREATMENT = frozenset({BUILDER, INDEX})
DIAGNOSTICS = frozenset(
    {
        "scripts/check_ci_attribution_commands.py",
        "scripts/check_ci_attribution_supervisor.py",
        "scripts/ci_attribution.py",
        "scripts/ci_attribution_plugin.py",
        "scripts/ci_attribution_profile.py",
        "scripts/ci_attribution_supervisor.py",
    }
)
HARNESS = frozenset(
    {
        "scripts/source_reuse_experiment.py",
        "scripts/ci_attribution_supervisor.py",
        "scripts/check_ci_attribution_supervisor.py",
        ".github/workflows/source-reuse.yml",
    }
)
CONTROL = (
    DIAGNOSTICS
    | HARNESS
    | frozenset(
        {
            "scripts/check_performance_policy.py",
            "tools/performance_policy.py",
            "tools/performance_tool_inputs.py",
            "tests/code_quality/d02_assessment_history.py",
            "tests/code_quality/test_d02_performance_assessment.py",
            "tests/code_quality/test_proposal_source_index.py",
            "tests/code_quality/test_performance_tool_inputs.py",
            MAP_PATH,
            SPEC_PATH,
        }
    )
)
AUDIT_MANIFEST = "docs/source_rules/tacoma-open-2026-source-package.json"
AUDIT_PDF = "docs/source_rules/faq-warhammer-open-tacoma-2026-dtb3ingprd-cvcl2agtfd.pdf"
AUDIT_INPUTS = frozenset(
    {AUDIT_MANIFEST, AUDIT_PDF}
    | {
        "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/" + name + ".json"
        for name in (
            "Datasheets",
            "Abilities",
            "Datasheets_abilities",
            "Datasheets_leader",
            "Datasheets_keywords",
        )
    }
)
REQUIRED = AUDIT_INPUTS | frozenset(
    {WORKLOAD, "tests/conftest.py", "tests/timing_plugin.py", "uv.lock", "pyproject.toml"}
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("Expected input-role object.")
    return cast(dict[str, object], value)


def _paths(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TypeError("Expected input-role path list.")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str) or not item or "\\" in item or ":" in item:
            raise ValueError("Invalid input-role path.")
        path = PurePosixPath(item)
        if not path.parts or path.is_absolute() or ".." in path.parts or path.as_posix() != item:
            raise ValueError("Input-role paths must be normalized repository-relative paths.")
        result.append(item)
    if len(result) != len(set(result)):
        raise ValueError("Duplicate input-role path.")
    return result


def validate_spec(spec: dict[str, object]) -> None:
    if spec.keys() != {
        "schema",
        "family",
        "workload",
        "treatment",
        "control_plane",
        "required_dependencies",
        "harness",
    } or (spec["schema"], spec["family"], spec["workload"]) != (SCHEMA, FAMILY, WORKLOAD):
        raise ValueError("Unsupported input-role specification.")
    treatment = set(_paths(spec["treatment"]))
    control = _object(spec["control_plane"])
    _paths(list(control))
    required = set(_paths(spec["required_dependencies"]))
    harness = set(_paths(spec["harness"]))
    if (
        treatment != TREATMENT
        or set(control) != CONTROL
        or required != REQUIRED
        or harness != HARNESS
    ):
        raise ValueError("Input-role paths differ from the exact reviewed family scope.")
    if treatment & control.keys() or required & (treatment | control.keys()):
        raise ValueError("Overlapping roles or used fixture classified as control plane.")
    if any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in control.values()):
        raise ValueError("Every control-plane path needs an explicit workload-role reason.")


def binding_enabled(family: str, specification: dict[str, object]) -> bool:
    declaration = specification.get("input_binding")
    expected = {"schema": SCHEMA, "role_specification": SPEC_PATH}
    if family == FAMILY:
        if (
            declaration != expected
            or specification.get("workload_id") != WORKLOAD_ID
            or specification.get("driver") != WORKLOAD
            or specification.get("cases") != ["orphan-write-independent-check"]
            or specification.get("samples_per_case") != 3
        ):
            raise ValueError("Tool family requires its exact input-binding capability.")
        return True
    if declaration is not None:
        raise ValueError("Input-binding capability is unsupported for this family.")
    return False


def classify_inputs(
    *,
    spec: dict[str, object],
    base: dict[str, str],
    head: dict[str, str],
    base_revision: str,
    head_revision: str,
    head_input_digest: str,
    harness_base: dict[str, str],
    harness_head: dict[str, str],
) -> dict[str, object]:
    """Complete independent inventories; never report-supplied exclusions."""
    validate_spec(spec)
    for revision in (base_revision, head_revision):
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("Actual checkout revision identity is missing.")
    for inventory in (base, head, harness_base, harness_head):
        _paths(list(inventory))
        if any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in inventory.values()
        ):
            raise ValueError("Tool inputs require raw-byte SHA256 identities.")
    if not base.keys() >= REQUIRED or not head.keys() >= REQUIRED:
        raise ValueError("Tool comparison lacks required common workload inputs.")
    if BUILDER not in base or INDEX in base or not head.keys() >= TREATMENT | CONTROL:
        raise ValueError("Treatment/control presence or verified base-helper absence drifted.")
    common_base = {p: v for p, v in base.items() if p not in TREATMENT | CONTROL}
    common_head = {p: v for p, v in head.items() if p not in TREATMENT | CONTROL}
    if common_base != common_head:
        raise ValueError("True common source/fixture/workload inputs changed.")
    if harness_base.keys() != HARNESS or harness_base != harness_head:
        raise ValueError("External harness must have identical exact manifests on both arms.")
    if harness_head != {path: head[path] for path in HARNESS}:
        raise ValueError("External harness bytes differ from the frozen candidate.")
    sides: dict[str, object] = {}
    for name, inventory, revision in (("base", base, base_revision), ("head", head, head_revision)):
        implementation = {p: inventory.get(p) for p in sorted(TREATMENT)}
        control = {p: inventory.get(p) for p in sorted(CONTROL)}
        sides[name] = {
            "revision": revision,
            "implementation": implementation,
            "implementation_sha256": digest(implementation),
            "control_plane": control,
            "control_plane_sha256": digest(control),
        }
    return {
        "schema": SCHEMA,
        "family": FAMILY,
        "role_spec_sha256": digest(spec),
        "head_input_digest": head_input_digest,
        "common": common_head,
        "common_sha256": digest(common_head),
        "sides": sides,
        "harness": {"base": harness_base, "head": harness_head, "sha256": digest(harness_head)},
    }


def _selected(path: str) -> bool:
    # Full runtime_inputs union plus complete copied contracts and explicit role/workload files.
    return path in CONTROL | REQUIRED or path.startswith(
        ("src/", "tests/", "scripts/", "tools/", "contracts/")
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate role specification key.")
        result[key] = value
    return result


def validate_audit_manifest(content: bytes) -> None:
    manifest = _object(json.loads(content, object_pairs_hook=_unique_object))
    if manifest.get("source_pdf_filename") != PurePosixPath(AUDIT_PDF).name:
        raise ValueError("Audit manifest must reference the exact required common PDF")


def read_role_spec(root: Path) -> dict[str, object]:
    original, archive = root / SPEC_PATH, root / SPEC_ARCHIVE
    if archive.exists():
        if original.exists() or archive.is_symlink():
            raise ValueError("Ambiguous or aliased archived role specification.")
        content = archive.read_bytes()
        if hashlib.sha256(content).hexdigest() != SPEC_SHA256:
            raise ValueError("Archived role specification bytes changed.")
    else:
        content = original.read_bytes()
    spec = _object(json.loads(content, object_pairs_hook=_unique_object))
    validate_spec(spec)
    return spec


def retained_tool_comparison_inputs(
    root: Path, *, current: dict[str, str], report: dict[str, object], base: str
) -> tuple[dict[str, str], str | None]:
    """Bridge only three explicitly hashed provenance controls, never measured work."""
    if not (root / SPEC_ARCHIVE).exists():
        return current, None
    read_role_spec(root)
    archive = root / REPORT_ARCHIVE
    raw_report = archive.read_bytes()
    if (
        archive.is_symlink()
        or hashlib.sha256(raw_report).hexdigest() != REPORT_SHA256
        or json.loads(raw_report) != report
        or base != MEASURED_BASE
        or report.get("head_input_digest") != MEASURED_INPUT_DIGEST
    ):
        raise ValueError("Archived comparison identity drift.")
    raw = (root / APPLICABILITY).read_bytes()
    proof = _object(json.loads(raw, object_pairs_hook=_unique_object))
    if proof.keys() != {"schema", "measured_head", "current_input_digest", "changes"} or (
        proof["schema"],
        proof["measured_head"],
        proof["current_input_digest"],
    ) != ("source-token-provenance-applicability-v1", MEASURED_HEAD, digest(current)):
        raise ValueError("Provenance applicability identity drift.")
    changes = _object(proof["changes"])
    if changes.keys() != PROVENANCE_CONTROLS:
        raise ValueError("Provenance applicability scope drift.")
    measured = dict(current)
    for path in sorted(PROVENANCE_CONTROLS):
        # The immutable measured Git revision supplies before bytes independently.
        before = subprocess.check_output(["git", "show", f"{MEASURED_HEAD}:{path}"], cwd=root)
        before_sha = hashlib.sha256(before).hexdigest()
        if changes[path] != {"before": before_sha, "after": current.get(path)}:
            raise ValueError("Provenance applicability control bytes drift.")
        measured[path] = before_sha
    if digest(measured) != MEASURED_INPUT_DIGEST:
        raise ValueError("Unapproved measured input change outside provenance controls.")
    return measured, hashlib.sha256(raw).hexdigest()


def comparison_inputs(
    root: Path, *, base: str, family: str, head_input_digest: str, measured_head: str | None = None
) -> dict[str, object]:
    """Hash actual base Git bytes and every current selected file independently."""
    if family != FAMILY:
        raise ValueError("Tool input roles are restricted to the declared family.")
    spec = read_role_spec(root)
    git = ["git", "-c", f"safe.directory={root.as_posix()}"]
    entries = subprocess.check_output([*git, "ls-tree", "-r", "-z", base], cwd=root)
    objects: dict[str, str] = {}
    for row in entries.decode().split("\0"):
        if row:
            metadata, path = row.split("\t", 1)
            mode, kind, oid = metadata.split()
            if _selected(path):
                if kind != "blob" or mode not in {"100644", "100755"}:
                    raise ValueError("Tool comparison requires regular source files.")
                objects[path] = oid
    paths = sorted(objects)
    payload = subprocess.check_output(
        [*git, "cat-file", "--batch"],
        input="".join(f"{objects[p]}\n" for p in paths).encode(),
        cwd=root,
    )
    base_inputs: dict[str, str] = {}
    offset = 0
    for path in paths:
        boundary = payload.index(b"\n", offset)
        oid, kind, length = payload[offset:boundary].decode().split()
        if oid != objects[path] or kind != "blob":
            raise ValueError("Base tool input Git object identity drifted.")
        start, end = boundary + 1, boundary + 1 + int(length)
        if payload[end : end + 1] != b"\n":
            raise ValueError("Truncated base tool input bytes.")
        base_inputs[path] = hashlib.sha256(payload[start:end]).hexdigest()
        if path == AUDIT_MANIFEST:
            validate_audit_manifest(payload[start:end])
        offset = end + 1
    if offset != len(payload):
        raise ValueError("Unexpected trailing base tool input bytes.")
    current = subprocess.check_output(
        [*git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    head_inputs: dict[str, str] = {}
    head_git_blobs: dict[str, str] = {}
    current_paths = set(current.decode().split("\0")) - {""}
    # The scanner and copied contract tree see files even when Git ignores them.
    current_paths.update(
        path.relative_to(root).as_posix() for path in (root / "src").rglob("*.py") if path.is_file()
    )
    current_paths.update(
        path.relative_to(root).as_posix()
        for path in (root / "contracts").rglob("*")
        if path.is_file()
    )
    if (root / SPEC_ARCHIVE).exists():
        current_paths.add(SPEC_PATH)
    for path in sorted(current_paths):
        if _selected(path):
            source = root / (
                SPEC_ARCHIVE if path == SPEC_PATH and (root / SPEC_ARCHIVE).exists() else path
            )
            if source.is_symlink():
                raise ValueError("Tool comparison requires regular source files.")
            if source.is_file():
                content = source.read_bytes()
                if path == AUDIT_MANIFEST:
                    validate_audit_manifest(content)
                head_inputs[path] = hashlib.sha256(content).hexdigest()
                head_git_blobs[path] = hashlib.sha1(
                    f"blob {len(content)}\0".encode() + content, usedforsecurity=False
                ).hexdigest()
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], cwd=root).decode().strip()
    if measured_head is not None:
        if len(measured_head) != 40 or any(c not in "0123456789abcdef" for c in measured_head):
            raise ValueError("Invalid measured checkout revision selector.")
        subprocess.check_call(
            [*git, "merge-base", "--is-ancestor", measured_head, "HEAD"], cwd=root
        )
        measured_tree = subprocess.check_output(
            [*git, "ls-tree", "-r", "-z", measured_head], cwd=root
        )
        measured_blobs = {}
        for row in measured_tree.decode().split("\0"):
            if row:
                metadata, path = row.split("\t", 1)
                if _selected(path):
                    mode, kind, oid = metadata.split()
                    if kind != "blob" or mode not in {"100644", "100755"}:
                        raise ValueError("Measured tool inputs must be regular Git blobs.")
                    measured_blobs[path] = oid
        # A report's revision is an untrusted locator, never an expected hash source.
        # Authenticate its actual Git bytes against independently read current bytes.
        # This permits evidence-only descendant commits without a self-reference cycle.
        if (root / SPEC_ARCHIVE).exists():
            from tools.performance_policy import runtime_inputs

            archived_report = _object(json.loads((root / REPORT_ARCHIVE).read_bytes()))
            measured_inputs, _ = retained_tool_comparison_inputs(
                root, current=runtime_inputs(root), report=archived_report, base=base
            )
            if measured_head != MEASURED_HEAD or head_input_digest != digest(measured_inputs):
                raise ValueError("Archived comparison measured revision or inventory drift.")
            for path in sorted(PROVENANCE_CONTROLS):
                before = subprocess.check_output(
                    [*git, "show", f"{MEASURED_HEAD}:{path}"], cwd=root
                )
                head_inputs[path] = hashlib.sha256(before).hexdigest()
                head_git_blobs[path] = hashlib.sha1(
                    f"blob {len(before)}\0".encode() + before, usedforsecurity=False
                ).hexdigest()
        if measured_blobs != head_git_blobs:
            raise ValueError("Measured head Git inputs do not equal the current source inventory.")
        revision = measured_head
    harness = {path: head_inputs[path] for path in HARNESS}
    return classify_inputs(
        spec=spec,
        base=base_inputs,
        head=head_inputs,
        base_revision=base,
        head_revision=revision,
        head_input_digest=head_input_digest,
        harness_base=harness,
        harness_head=harness,
    )


def validate_binding(*, observed: object, expected: dict[str, object] | None) -> None:
    if expected is None or observed != expected:
        raise ValueError("Missing, stale or unrelated actual-base/head input binding.")
