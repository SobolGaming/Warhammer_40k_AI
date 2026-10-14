"""Fresh actual-byte binding for the exact manifest/source-token treatment.

This version cannot reuse the v1 historical measurements. Runtime treatment and
derived outputs have separate per-side identities, never control-plane aliases.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools import performance_tool_inputs as original

SCHEMA = "tool-input-roles-v2"
SPEC_PATH = "docs/performance/policy-v3/source-token-input-roles-v2.json.txt"
RUNTIME = "src/warhammer40k_core/engine/faction_content/runtime.py"
TREATMENT = original.TREATMENT | {RUNTIME}
DERIVED = frozenset(
    {
        "src/warhammer40k_core/_engine_build_manifest.json",
        "contracts/examples/persistence/session-persistence.json",
        "contracts/examples/sessions/session-command-outcome.json",
        "contracts/examples/sessions/session-command-started.json",
        "contracts/examples/sessions/session-metadata-created.json",
        "contracts/examples/support-profile-player-a-redacted.json",
        "contracts/examples/support-profile-player-b-redacted.json",
        "contracts/examples/support-profile.json",
        "contracts/manifest.json",
    }
)
HARNESS = frozenset(
    "ci/manifest-validation/" + name
    for name in (
        "ci_attribution_supervisor.py",
        "check_ci_attribution_supervisor.py",
        "manifest_campaign.py",
        "reconstruction_worker.py",
        "source_token_arm.py",
        "source_reuse_experiment.py",
    )
)
CONTROL = (
    original.CONTROL
    | HARNESS
    | {
        SPEC_PATH,
        "tools/performance_tool_inputs_v2.py",
        "tests/code_quality/test_performance_tool_inputs_v2.py",
        "tests/code_quality/tool_input_history.py",
        "tests/code_quality/test_runtime_manifest_reuse.py",
    }
)
SELECTED = TREATMENT | DERIVED | CONTROL | original.REQUIRED


def validate_spec(spec: dict[str, object]) -> None:
    expected = {
        "schema",
        "family",
        "workload",
        "treatment",
        "derived_outputs",
        "control_plane",
        "required_dependencies",
        "harness",
    }
    if spec.keys() != expected or (spec["schema"], spec["family"], spec["workload"]) != (
        SCHEMA,
        original.FAMILY,
        original.WORKLOAD,
    ):
        raise ValueError("Unsupported v2 input-role specification.")
    treatment = frozenset(original.input_paths(spec["treatment"]))
    derived = frozenset(original.input_paths(spec["derived_outputs"]))
    controls = original.input_object(spec["control_plane"])
    original.input_paths(list(controls))
    if (
        treatment != TREATMENT
        or derived != DERIVED
        or controls.keys() != CONTROL
        or frozenset(original.input_paths(spec["required_dependencies"])) != original.REQUIRED
        or frozenset(original.input_paths(spec["harness"])) != HARNESS
    ):
        raise ValueError("V2 input roles differ from the exact reviewed scope.")
    if treatment & (derived | controls.keys()) or derived & controls.keys():
        raise ValueError("Overlapping v2 input roles.")
    if any(not isinstance(reason, str) or len(reason.strip()) < 20 for reason in controls.values()):
        raise ValueError("Every v2 control requires an explicit workload-role reason.")


def read_role_spec(root: Path) -> dict[str, object]:
    # The old archived specification is still authenticated independently.
    original.read_role_spec(root)
    path = root / SPEC_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("V2 specification must be a regular reviewed file.")
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
            raise ValueError("Missing actual v2 revision/input digest.")
    if base_revision != original.MEASURED_BASE or head_revision == original.MEASURED_HEAD:
        raise ValueError("V2 requires the actual PR base and fresh treatment evidence.")
    for inventory in (base, head, harness_base, harness_head):
        original.input_paths(list(inventory))
        if any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in inventory.values()
        ):
            raise ValueError("V2 inputs require complete raw-byte SHA256 identities.")
    if not base.keys() >= original.REQUIRED | DERIVED | (TREATMENT - {original.INDEX}):
        raise ValueError("V2 base lacks required common, treatment or derived inputs.")
    if original.INDEX in base or not head.keys() >= SELECTED:
        raise ValueError("V2 treatment/control presence or base-helper absence drifted.")
    common_base = {p: v for p, v in base.items() if p not in TREATMENT | DERIVED | CONTROL}
    common_head = {p: v for p, v in head.items() if p not in TREATMENT | DERIVED | CONTROL}
    if common_base != common_head:
        raise ValueError("True common source/fixture/workload inputs changed.")
    if harness_base.keys() != HARNESS or harness_base != harness_head:
        raise ValueError("V2 external harness must be identical on both arms.")
    if harness_head != {p: head[p] for p in HARNESS}:
        raise ValueError("V2 harness differs from the frozen candidate.")
    sides: dict[str, object] = {}
    for name, inventory, revision in (("base", base, base_revision), ("head", head, head_revision)):
        implementation = {p: inventory.get(p) for p in sorted(TREATMENT)}
        derived = {p: inventory[p] for p in sorted(DERIVED)}
        controls = {p: inventory.get(p) for p in sorted(CONTROL)}
        sides[name] = {
            "revision": revision,
            "implementation": implementation,
            "implementation_sha256": original.digest(implementation),
            "derived_outputs": derived,
            "derived_outputs_sha256": original.digest(derived),
            "control_plane": controls,
            "control_plane_sha256": original.digest(controls),
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


def validate_derived_outputs(root: Path, expected: dict[str, str]) -> None:
    """Require every bound derived byte, never remove identity/hash fields."""
    if expected.keys() != DERIVED:
        raise ValueError("Incomplete derived-output inventory.")
    for name, expected_hash in expected.items():
        path = root / name
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash
        ):
            raise ValueError("Derived output differs from its bound source bytes: " + name)


def validate_generated_evidence(observed: object, binding: dict[str, object]) -> None:
    """All three real regenerated trees per arm must equal the bound raw bytes."""
    records = original.input_object(observed)
    if records.keys() != {"base", "head"} or binding.get("schema") != SCHEMA:
        raise ValueError("Missing v2 generated-output parity evidence.")
    common = original.input_object(binding["common"])
    sides = original.input_object(binding["sides"])
    for side in ("base", "head"):
        derived = original.input_object(original.input_object(sides[side])["derived_outputs"])
        expected = {
            name.removeprefix("contracts/"): value
            for name, value in (common | derived).items()
            if name.startswith("contracts/")
        }
        samples = records[side]
        if (
            not expected
            or not isinstance(samples, list)
            or samples != [expected, expected, expected]
        ):
            raise ValueError("Generated-output parity must bind all three complete exact trees.")
