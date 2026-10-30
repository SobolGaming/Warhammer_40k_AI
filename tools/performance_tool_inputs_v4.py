"""Fresh source-overlay comparison bound to the exact PR600 base.

Historical v1/v2/v3 specifications and receipts remain separate. The role lists
are closed: every other selected byte must be identical between the two arms.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tools import performance_tool_inputs as original
from tools import performance_tool_inputs_v2 as previous

SCHEMA = "tool-input-roles-v4"
BASE = "bc9acd8419e7b97a2c1260c7e932d2cb9c3fc370"
SPEC_PATH = "docs/performance/policy-v3/vyper-source-input-roles-v4.json"
DRIVER = "scripts/measure_vyper_source_binding.py"
PACKAGE = "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
NEW_TREATMENT = frozenset(
    {
        PACKAGE + "aeldari_vyper_title_2026_10.py",
        PACKAGE + "aeldari_vyper_title_2026_10.overlay-pack.json",
        "tools/generate_vyper_source_overlay.py",
    }
)
TREATMENT = NEW_TREATMENT | {"tools/ability_support_sources.py", "tools/aeldari_support_report.py"}
DERIVED = previous.DERIVED | {
    "data/generated/ability_coverage/ability_coverage_rows.json",
    "data/generated/ability_coverage/ability_support_category_rows.json",
    "data/generated/ability_coverage/datasheet_support_rows.json",
}
CONTROL = frozenset(
    {
        SPEC_PATH,
        original.MAP_PATH,
        DRIVER,
        "tools/performance_tool_inputs.py",
        "tools/performance_tool_inputs_v4.py",
        "tools/performance_policy.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_performance_tool_inputs_v2.py",
        "tests/code_quality/test_current_comparison_routing.py",
        "tests/code_quality/test_ws12_generated_data_artifacts.py",
        "tests/code_quality/test_generated_ability_support_artifacts.py",
        "tests/rules/section25/test_mfm.py",
        "data/source_audits/ci64_provenance_v1/test-cutover.json",
        "data/source_audits/supported_rules_2026_10/vyper-binding.json",
    }
)
HARNESS = frozenset(
    {
        DRIVER,
        "scripts/source_reuse_experiment.py",
        "scripts/ci_attribution_supervisor.py",
        "scripts/check_ci_attribution_supervisor.py",
        original.WORKLOAD,
        "tests/conftest.py",
        "tests/timing_plugin.py",
    }
)
REQUIRED = original.REQUIRED | (HARNESS - {DRIVER})


def selected(path: str) -> bool:
    """Complete code, source-data, schema and copied-output input boundaries.

    Current reports live only under docs/performance/current; neither reports nor
    the assessment recursively hash themselves. The fixed role spec is included.
    """
    return (
        path.startswith(("src/", "tests/", "scripts/", "tools/", "contracts/", "schemas/", "data/"))
        or path in REQUIRED | CONTROL
    )


def validate_spec(spec: dict[str, object]) -> None:
    if spec.keys() != {
        "schema",
        "family",
        "workload",
        "base",
        "treatment",
        "derived_outputs",
        "control_plane",
        "required_dependencies",
        "harness",
    } or (spec["schema"], spec["family"], spec["workload"], spec["base"]) != (
        SCHEMA,
        original.FAMILY,
        original.WORKLOAD,
        BASE,
    ):
        raise ValueError("Unsupported v4 exact-base role specification.")
    control = original.input_object(spec["control_plane"])
    original.input_paths(list(control))
    if (
        frozenset(original.input_paths(spec["treatment"])) != TREATMENT
        or frozenset(original.input_paths(spec["derived_outputs"])) != DERIVED
        or control.keys() != CONTROL
        or frozenset(original.input_paths(spec["required_dependencies"])) != REQUIRED
        or frozenset(original.input_paths(spec["harness"])) != HARNESS
    ):
        raise ValueError("V4 roles differ from the exact reviewed workload scope.")
    if TREATMENT & (DERIVED | CONTROL) or DERIVED & CONTROL:
        raise ValueError("Overlapping v4 roles.")
    if any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in control.values()):
        raise ValueError("Every v4 control requires an explicit workload-role reason.")


def read_role_spec(root: Path) -> dict[str, object]:
    path = root / SPEC_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("V4 specification must be a regular reviewed file.")
    spec = original.input_object(
        json.loads(path.read_bytes(), object_pairs_hook=original.unique_input_object)
    )
    validate_spec(spec)
    return spec


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
    validate_spec(spec)
    for identity, length in ((base_revision, 40), (head_revision, 40), (head_input_digest, 64)):
        if len(identity) != length or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Missing actual v4 revision/input digest.")
    if base_revision != BASE or head_revision == BASE:
        raise ValueError("V4 requires the exact PR600 base and a fresh head.")
    for inventory in (base, head, harness_base, harness_head):
        original.input_paths(list(inventory))
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in inventory.values()
        ):
            raise ValueError("V4 inputs require complete raw-byte SHA256 identities.")
    if (
        not base.keys() >= REQUIRED | DERIVED | (TREATMENT - NEW_TREATMENT)
        or base.keys() & NEW_TREATMENT
    ):
        raise ValueError("V4 base source/dependency presence differs from the reviewed base.")
    if not head.keys() >= REQUIRED | TREATMENT | DERIVED | CONTROL:
        raise ValueError("V4 head lacks required source/dependency inputs.")
    common_base = {p: v for p, v in base.items() if p not in TREATMENT | DERIVED | CONTROL}
    common_head = {p: v for p, v in head.items() if p not in TREATMENT | DERIVED | CONTROL}
    if common_base != common_head:
        raise ValueError("True common source/fixture/workload/dependency inputs changed.")
    if (
        harness_base.keys() != HARNESS
        or harness_base != harness_head
        or harness_head != {p: head[p] for p in HARNESS}
    ):
        raise ValueError("V4 requires the same independently bound harness on both arms.")
    sides: dict[str, object] = {}
    for name, inventory, revision in (("base", base, base_revision), ("head", head, head_revision)):
        sides[name] = {
            "revision": revision,
            "inventory": inventory,
            "inventory_sha256": original.digest(inventory),
            "implementation": {p: inventory.get(p) for p in sorted(TREATMENT)},
            "derived_outputs": {p: inventory[p] for p in sorted(DERIVED)},
            "control_plane": {p: inventory.get(p) for p in sorted(CONTROL)},
        }
    return {
        "schema": SCHEMA,
        "family": original.FAMILY,
        "role_spec_sha256": original.digest(spec),
        "head_input_digest": head_input_digest,
        "common": common_head,
        "common_sha256": original.digest(common_head),
        "sides": sides,
        "harness": {
            "base": harness_base,
            "head": harness_head,
            "sha256": original.digest(harness_head),
        },
    }


def git_inventory(root: Path, revision: str) -> tuple[dict[str, str], dict[str, str]]:
    """Hash independently fetched Git blobs in bounded batches, without checkout."""
    git = ["git", "-c", f"safe.directory={root.as_posix()}"]
    entries = subprocess.check_output([*git, "ls-tree", "-r", "-z", revision], cwd=root)
    objects: dict[str, str] = {}
    for row in entries.decode().split("\0"):
        if row:
            metadata, path = row.split("\t", 1)
            mode, kind, oid = metadata.split()
            if selected(path):
                if kind != "blob" or mode not in {"100644", "100755"}:
                    raise ValueError("V4 inputs must be regular Git blobs.")
                objects[path] = oid
    inventory: dict[str, str] = {}
    paths = sorted(objects)
    for offset in range(0, len(paths), 32):
        batch = paths[offset : offset + 32]
        payload = subprocess.check_output(
            [*git, "cat-file", "--batch"],
            input="".join(objects[p] + "\n" for p in batch).encode(),
            cwd=root,
        )
        cursor = 0
        for path in batch:
            boundary = payload.index(b"\n", cursor)
            oid, kind, length = payload[cursor:boundary].decode().split()
            start, end = boundary + 1, boundary + 1 + int(length)
            if oid != objects[path] or kind != "blob" or payload[end : end + 1] != b"\n":
                raise ValueError("V4 Git input identity or framing drifted.")
            inventory[path] = hashlib.sha256(payload[start:end]).hexdigest()
            cursor = end + 1
        if cursor != len(payload):
            raise ValueError("Unexpected trailing v4 Git input bytes.")
    return inventory, objects


def current_inventory(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    names = set(
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    ) - {""}
    # Both the runtime source scanner and the copied output tree see ignored files.
    names.update(
        p.relative_to(root).as_posix()
        for p in (root / "src").rglob("*")
        if p.is_file()
        and (p.suffix in {".py", ".json"} or p.name == "py.typed")
        and not {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}.intersection(
            p.relative_to(root / "src").parts
        )
    )
    for directory in ("contracts", "data", "schemas"):
        names.update(
            p.relative_to(root).as_posix() for p in (root / directory).rglob("*") if p.is_file()
        )
    inventory: dict[str, str] = {}
    blobs: dict[str, str] = {}
    for name in sorted(names):
        if selected(name):
            path = root / name
            if path.is_symlink():
                raise ValueError("V4 current inputs must be regular files.")
            if path.is_file():
                content = path.read_bytes()
                inventory[name] = hashlib.sha256(content).hexdigest()
                blobs[name] = hashlib.sha1(
                    f"blob {len(content)}\0".encode() + content, usedforsecurity=False
                ).hexdigest()
    return inventory, blobs


def comparison_inputs(
    root: Path, *, base: str, head_input_digest: str, measured_head: str | None
) -> dict[str, object]:
    if base != BASE:
        raise ValueError("V4 requires the exact PR600 base.")
    spec = read_role_spec(root)
    before, _ = git_inventory(root, base)
    after, blobs = current_inventory(root)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    if measured_head is not None:
        if len(measured_head) != 40 or any(c not in "0123456789abcdef" for c in measured_head):
            raise ValueError("Invalid v4 measured revision selector.")
        # Squash-merged main may not descend from the measured branch commit.
        # The retained Git object is a locator; independently equal bytes admit it.
        _, measured_blobs = git_inventory(root, measured_head)
        if measured_blobs != blobs:
            raise ValueError("V4 measured head bytes differ from the current source inventory.")
        revision = measured_head
    harness = {p: after[p] for p in HARNESS}
    return classify_inputs(
        spec=spec,
        base=before,
        head=after,
        base_revision=base,
        head_revision=revision,
        head_input_digest=head_input_digest,
        harness_base=harness,
        harness_head=harness,
    )


def validate_generated_evidence(observed: object, binding: dict[str, object]) -> None:
    records = original.input_object(observed)
    if records.keys() != {"base", "head"} or binding.get("schema") != SCHEMA:
        raise ValueError("Missing v4 generated-output parity evidence.")
    sides = original.input_object(binding["sides"])
    for side in ("base", "head"):
        inventory = original.input_object(original.input_object(sides[side])["inventory"])
        expected = {
            p.removeprefix("contracts/"): value
            for p, value in inventory.items()
            if p.startswith("contracts/")
        }
        if not expected or records[side] != [expected, expected, expected]:
            raise ValueError("V4 requires all three complete exact generated trees per arm.")
