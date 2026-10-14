"""The S25 smoke classification cannot waive unrelated or drifted work."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from tools.performance_policy import validate_assessment
from tools.performance_s25_rule_semantics import BASE, SCOPE, s25_rule_semantics_smoke_operations

ROOT = Path(__file__).resolve().parents[2]


def test_s25_scope_matches_complete_current_source_rows() -> None:
    scope = json.loads((ROOT / SCOPE).read_bytes())
    assessment = json.loads((ROOT / "docs/performance/change-assessment.json").read_bytes())
    assert scope["base"] == assessment["base"] == BASE
    assert set(scope["changes"]) == set(scope["smoke_operations"])
    assert scope["changes"]
    for path, change in scope["changes"].items():
        assert assessment["changes"][path] == change
        expected = frozenset(scope["smoke_operations"][path])
        assert expected
        assert "cache-policy" not in expected
        assert (
            s25_rule_semantics_smoke_operations(
                base=BASE, path=path, category="rule_semantics", change=change
            )
            == expected
        )


def test_s25_scope_rejects_base_category_path_and_hash_drift() -> None:
    scope = json.loads((ROOT / SCOPE).read_bytes())
    for path, change in scope["changes"].items():
        for base, candidate_path, category in (
            ("0" * 40, path, "rule_semantics"),
            (BASE, path, "algorithm_or_search"),
            (BASE, path, "cache_policy"),
            (BASE, path, "serialization_or_replay_work"),
            (BASE, path + ".unreviewed", "rule_semantics"),
        ):
            assert not s25_rule_semantics_smoke_operations(
                base=base, path=candidate_path, category=category, change=change
            )
        for field in ("before_sha256", "after_sha256"):
            drifted = copy.deepcopy(change)
            drifted[field] = "0" * 64
            assert not s25_rule_semantics_smoke_operations(
                base=BASE, path=path, category="rule_semantics", change=drifted
            )
        for owner in change["owners"]:
            for field in ("before", "after"):
                drifted = copy.deepcopy(change)
                drifted["owners"][owner][field] = "0" * 64
                assert not s25_rule_semantics_smoke_operations(
                    base=BASE, path=path, category="rule_semantics", change=drifted
                )


def test_s25_scope_retains_detailed_requirements_for_performance_changes() -> None:
    assessment = json.loads((ROOT / "docs/performance/change-assessment.json").read_bytes())
    scope = json.loads((ROOT / SCOPE).read_bytes())
    operation_map = json.loads(
        (ROOT / "docs/performance/policy-v3/operation-map.json").read_bytes()
    )
    for path in scope["changes"]:
        for category in (
            "algorithm_or_search",
            "cache_policy",
            "serialization_or_replay_work",
            "hot_query_or_data_structure",
        ):
            changed_assessment = copy.deepcopy(assessment)
            changed_assessment["rows"][path]["category"] = category
            with pytest.raises(ValueError, match="Missing required detailed comparisons"):
                validate_assessment(
                    changed_assessment,
                    base=BASE,
                    changes=assessment["changes"],
                    runtime_id=assessment["runtime_build_id"],
                    operation_map=operation_map,
                )
