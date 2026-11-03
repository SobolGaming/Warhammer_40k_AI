"""Exact bounded Starfang/Deep Strike source-only smoke admission controls."""

from __future__ import annotations

import copy
import fnmatch
import subprocess
from pathlib import Path
from typing import cast

import pytest
from tools import performance_policy as policy
from tools.performance_policy import object_value, read_object

ROOT = Path(__file__).resolve().parents[2]
BASE = "79a27e4a26e180a28457712818d47e274df7c99a"
SCOPE = ROOT / "docs/performance/policy-v3/starfang-deep-strike-smoke-scope.json"


def test_starfang_source_smoke_binding_and_predecessor_are_exact() -> None:
    scope = read_object(SCOPE)
    bindings = object_value(scope["changes"])
    operations = object_value(scope["smoke_operations"])
    for path, change in bindings.items():
        expected = cast(list[str], operations[path])
        assert policy.starfang_deep_strike_smoke_operations(
            base=BASE, path=path, category="rule_semantics", change=change
        ) == frozenset(expected)
        for base, selected_path, category in (
            ("a" * 40, path, "rule_semantics"),
            (BASE, "tools/unreviewed.py", "rule_semantics"),
            (BASE, path, "algorithm_or_search"),
            (BASE, path, "cache_policy"),
            (BASE, path, "serialization_or_replay_work"),
        ):
            assert not policy.starfang_deep_strike_smoke_operations(
                base=base, path=selected_path, category=category, change=change
            )
        for part in ("file", "owner"):
            changed = copy.deepcopy(object_value(change))
            if part == "file":
                changed["after_sha256"] = "0" * 64
            else:
                object_value(next(iter(object_value(changed["owners"]).values())))["after"] = (
                    "0" * 64
                )
            assert not policy.starfang_deep_strike_smoke_operations(
                base=BASE, path=path, category="rule_semantics", change=changed
            )
    raw = (ROOT / "tools/performance_policy.py").read_bytes()
    prior = subprocess.check_output(
        ["git", "show", BASE + ":tools/performance_policy.py"], cwd=ROOT
    )
    assert policy.starfang_deep_strike_policy_predecessor(raw) == prior
    assert policy.starfang_deep_strike_policy_predecessor(prior) == prior
    for altered in (b"", raw + b"\n", raw.replace(b"category !=", b"category ==", 1)):
        with pytest.raises(ValueError, match="Starfang/Deep Strike"):
            policy.starfang_deep_strike_policy_predecessor(altered)
    mapping = read_object(ROOT / "docs/performance/policy-v3/operation-map.json")
    old_mapping = read_object_from_git("docs/performance/policy-v3/operation-map.json")
    old_operations = object_value(old_mapping["operations"])
    for name, operation in old_operations.items():
        assert object_value(mapping["operations"])[name] == operation


def read_object_from_git(path: str) -> dict[str, object]:
    import json

    return cast(
        dict[str, object],
        json.loads(subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT)),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-owner",
        "extra-owner",
        "file-hash",
        "owner-hash",
        "existing-owner-null",
        "operation",
        "extra-binding",
        "extra-field",
        "proof-after",
        "proof-before",
        "proof-block",
        "proof-call",
        "proof-predecessor",
        "proof-field",
    ],
)
def test_starfang_source_smoke_rejects_unbounded_declarations(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    scope = read_object(SCOPE)
    path = "tools/generate_ability_support_matrix.py"
    change = object_value(scope["changes"])[path]
    altered = copy.deepcopy(scope)
    bindings = object_value(altered["changes"])
    binding = object_value(bindings[path])
    owners = object_value(binding["owners"])
    proof = object_value(altered["policy_successor"])
    if mutation == "missing-owner":
        owners.pop("_ability_support_catalog_package")
    elif mutation == "extra-owner":
        owners["unreviewed"] = {"before": "1" * 64, "after": "2" * 64}
    elif mutation == "file-hash":
        binding["after_sha256"] = "not-a-hash"
    elif mutation == "owner-hash":
        object_value(owners["_ability_support_catalog_package"])["after"] = "not-a-hash"
    elif mutation == "existing-owner-null":
        object_value(owners["_ability_support_catalog_package"])["before"] = None
    elif mutation == "operation":
        object_value(altered["smoke_operations"])[path] = ["cache-policy"]
    elif mutation == "extra-binding":
        bindings["unreviewed.py"] = copy.deepcopy(binding)
    elif mutation.startswith("proof-"):
        proof[
            {
                "proof-after": "after_sha256",
                "proof-before": "before_sha256",
                "proof-block": "function_block_sha256",
                "proof-call": "union_call_sha256",
                "proof-predecessor": "predecessor_call_sha256",
                "proof-field": "unreviewed",
            }[mutation]
        ] = "0" * 64
    else:
        altered["unreviewed"] = True

    def altered_scope(_selected: Path) -> dict[str, object]:
        return altered

    monkeypatch.setattr(policy, "read_object", altered_scope)
    with pytest.raises(ValueError, match=r"Starfang/Deep Strike|Unexpected"):
        policy.starfang_deep_strike_smoke_operations(
            base=BASE, path=path, category="rule_semantics", change=change
        )


def test_starfang_assessment_requires_mandatory_operations_and_detailed_categories() -> None:
    scope = read_object(SCOPE)
    changes = object_value(scope["changes"])
    mapping = read_object(ROOT / policy.MAP)
    operations: dict[str, list[str]] = {
        path: [
            name
            for name, raw in object_value(mapping["operations"]).items()
            if any(
                fnmatch.fnmatchcase(path, pattern)
                for pattern in cast(list[str], object_value(raw)["paths"])
            )
            and any(
                fnmatch.fnmatchcase(owner, pattern)
                for owner in object_value(object_value(change)["owners"])
                for pattern in cast(list[str], object_value(raw)["owners"])
            )
        ]
        for path, change in changes.items()
    }
    build = "warhammer40k-core-v2:runtime-tree-sha256-v1:" + "1" * 64
    rows: dict[str, object] = {
        path: {
            "category": "rule_semantics",
            "operations": selected,
            "selected_families": [],
            "rationale": scope["source_obligation"],
            "source_obligation": scope["source_obligation"],
            "unchanged_work": scope["unchanged_work"],
        }
        for path, selected in operations.items()
    }
    assessment: dict[str, object] = {
        "policy": policy.POLICY,
        "base": BASE,
        "runtime_build_id": build,
        "operation_map_sha256": policy.canonical_digest(mapping),
        "changes": changes,
        "rows": rows,
        "milestone": "ordinary",
        "comparisons": {},
        "full_game": None,
    }
    assert (
        policy.validate_assessment(
            assessment, base=BASE, changes=changes, runtime_id=build, operation_map=mapping
        )
        == set()
    )
    for path, selected in operations.items():
        for omitted in selected:
            altered = copy.deepcopy(assessment)
            object_value(object_value(altered["rows"])[path])["operations"] = [
                name for name in selected if name != omitted
            ]
            with pytest.raises(ValueError, match="operation"):
                policy.validate_assessment(
                    altered,
                    base=BASE,
                    changes=changes,
                    runtime_id=build,
                    operation_map=mapping,
                )
        for category in ("algorithm_or_search", "cache_policy", "serialization_or_replay_work"):
            altered = copy.deepcopy(assessment)
            object_value(object_value(altered["rows"])[path])["category"] = category
            with pytest.raises(ValueError, match="detailed"):
                policy.validate_assessment(
                    altered,
                    base=BASE,
                    changes=changes,
                    runtime_id=build,
                    operation_map=mapping,
                )
