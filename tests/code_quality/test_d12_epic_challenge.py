"""Retained source and every original D12 acceptance body remain immutable."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from tools.performance_policy import _d12_smoke_operations

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "data/source_audits/d12"
TEST_PATH = Path("tests/unit/test_phase12c_core_stratagems.py")


def test_d12_retained_complete_source_and_original_acceptance_are_exact() -> None:
    path = AUDIT / "selected-source-and-acceptance.json"
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == (
        "984638eca64e4618a5fc2a7ad6afd0d41248f7ed03ba80487b86f75bce92b721"
    )
    selected = json.loads(data)
    inventory = json.loads(
        (ROOT / "data/source_audits/order135/current-inventory.json").read_bytes()
    )
    sources = {row["row_id"]: row for row in inventory["complete_selected_sources"]}
    assert len(selected["complete_selected_rows"]) == 57
    assert len(selected["complete_original_acceptance_rows"]) == 6
    assert len(selected["complete_corresponding_support_acceptance_rows"]) == 219
    for row in selected["complete_selected_rows"]:
        assert row == sources[row["row_id"]]
    original_requirements = {
        row["original_requirement"]["requirement_id"]: row["original_requirement"]
        for row in inventory["requirements"]
    }
    for row in (
        selected["complete_original_acceptance_rows"]
        + selected["complete_corresponding_support_acceptance_rows"]
    ):
        requirement = row["original_requirement"]
        assert requirement == original_requirements[requirement["requirement_id"]]


def test_d12_all_original_test_branches_assertions_and_decorators_remain_exact() -> None:
    original_data = (AUDIT / "baseline" / TEST_PATH.with_suffix(".py.txt")).read_bytes()
    assert hashlib.sha256(original_data).hexdigest() == (
        "9625abdb3320e6f6698cc9a743ad418ca57d438c34be979e95df3d0b06a82369"
    )
    original = ast.parse(original_data)
    current = ast.parse((ROOT / TEST_PATH).read_bytes())
    added = [
        node
        for node in current.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_d12_")
    ]
    assert added
    imports = (ast.Import, ast.ImportFrom)
    original_body = [ast.dump(node) for node in original.body if not isinstance(node, imports)]
    retained_body = [
        ast.dump(node)
        for node in current.body
        if not isinstance(node, imports) and node not in added
    ]
    assert retained_body == original_body
    original_imports = {ast.dump(node) for node in original.body if isinstance(node, imports)}
    current_imports = {ast.dump(node) for node in current.body if isinstance(node, imports)}
    assert original_imports <= current_imports
    assert len(current_imports - original_imports) == 1
    assert (
        next(
            node.module
            for node in current.body
            if isinstance(node, ast.ImportFrom) and ast.dump(node) not in original_imports
        )
        == "tests.epic_challenge_helpers"
    )


def test_d12_performance_rule_scope_requires_exact_base_category_and_owner_bytes() -> None:
    scope = json.loads((ROOT / "docs/performance/policy-v3/d12-rule-semantics.json").read_bytes())
    operations = {
        "src/warhammer40k_core/engine/fight_model_authority_history.py": (
            "order135-grouped-combat-decoding"
        ),
        "src/warhammer40k_core/engine/stratagems_geometry.py": "order135-visibility-hot-consumers",
    }
    assert scope["smoke_operations"] == {path: [name] for path, name in operations.items()}
    assert set(scope["changes"]) == set(operations)
    for path, name in operations.items():
        change = scope["changes"][path]
        assert _d12_smoke_operations(
            base=scope["base"], path=path, category="rule_semantics", change=change
        ) == frozenset({name})
        for base, category, value in (
            ("wrong-base", "rule_semantics", change),
            (scope["base"], "serialization_or_replay_work", change),
            (scope["base"], "rule_semantics", {**change, "after_sha256": "different"}),
            (scope["base"], "rule_semantics", {**change, "owners": {}}),
        ):
            assert not _d12_smoke_operations(base=base, path=path, category=category, change=value)
