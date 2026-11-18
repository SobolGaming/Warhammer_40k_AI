"""Current actual-base measurements cannot inherit old samples or omit hard outputs."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from tools import performance_policy as policy
from tools import performance_qualification_measurements as measured
from tools import performance_qualification_successor as stage
from tools import performance_tool_inputs_v3 as roles
from tools.performance_preflight_successor import read_frozen_blobs

ROOT = Path(__file__).resolve().parents[2]


def test_current_measurement_route_is_exact_base_and_new_namespace_only() -> None:
    assert measured.applies(
        base=measured.BASE, path="docs/performance/current/qualification40-dice.json"
    )
    assert not measured.applies(
        base="f" * 40, path="docs/performance/current/qualification40-dice.json"
    )
    assert not measured.applies(
        base=measured.BASE, path="docs/performance/current/source-token-reuse-v2.json"
    )


@pytest.mark.parametrize(
    "mutation", ["missing_file", "wrong_digest", "missing_sample", "cross_arm", "missing_arm"]
)
def test_current_source_token_requires_complete_actual_generated_trees(mutation: str) -> None:
    path = ROOT / "docs/performance/current/qualification40-external_contract_source_reuse.json"
    report = policy.read_object(path)
    from tools import performance_ci60_qualification as ci60

    # This is an immutable historical generated-tree assertion, not current credit.
    current = ci60.historical_inputs(ROOT)
    assert policy.canonical_digest(current) == stage.PRODUCING_INPUT_DIGEST
    binding = roles.expected_binding(ROOT, input_digest=policy.canonical_digest(current))
    roles.validate_generated_evidence(report["generated_output_binding"], binding)
    observed = cast(
        dict[str, list[dict[str, str]]], copy.deepcopy(report["generated_output_binding"])
    )
    if mutation == "missing_file":
        observed["head"][0].pop(next(iter(observed["head"][0])))
    elif mutation == "wrong_digest":
        observed["head"][0][next(iter(observed["head"][0]))] = "f" * 64
    elif mutation == "missing_sample":
        observed["head"].pop()
    elif mutation == "cross_arm":
        observed["head"] = observed["base"]
    else:
        observed.pop("base")
    with pytest.raises(ValueError, match="Current source-token"):
        roles.validate_generated_evidence(observed, binding)


def test_current_comparison_samples_equal_every_raw_case_and_original_profile() -> None:
    proof: dict[str, Any] = policy.read_object(
        ROOT / stage.NAMESPACE / "measurement-provenance.json"
    )
    # Bind this immutable cohort to its actual producer, not today's expanded
    # workload. Reading historical specifications creates no current-run credit.
    producing = policy.read_object(ROOT / stage.NAMESPACE / "producing-inputs.json")
    assert policy.canonical_digest(producing) == stage.PRODUCING_INPUT_DIGEST
    original_map = read_frozen_blobs(ROOT, stage.PRODUCING_COMMIT, [policy.MAP])[policy.MAP]
    assert hashlib.sha256(original_map).hexdigest() == producing[policy.MAP]
    mapping: dict[str, Any] = json.loads(original_map)
    for family, row in proof.items():
        assert row["producing_head"] == stage.PRODUCING_COMMIT
        assert row["head_input_digest"] == stage.PRODUCING_INPUT_DIGEST
        comparison: dict[str, Any] = policy.read_object(
            ROOT / ("docs/performance/current/qualification40-" + family + ".json")
        )
        spec = mapping["families"][family]
        assert comparison["base_revision"] == measured.BASE
        for side in ("base", "head"):
            raw = policy.read_object(ROOT / row[side]["path"])
            values = measured.samples_from_raw(family, raw)
            assert values == comparison[side]["samples"]
            assert set(values) == set(spec["cases"])
            assert all(len(v) == spec["samples_per_case"] for v in values.values())
        assert comparison["budget_profile"] == spec["budget_profile"]
