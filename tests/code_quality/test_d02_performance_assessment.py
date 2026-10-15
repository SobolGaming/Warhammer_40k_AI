"""D02 exact-bound rule semantics preserve detailed performance requirements."""

import copy
from pathlib import Path

import pytest
from tools.performance_policy import (
    D02_SCOPE,
    d02_rule_semantics_smoke_operations,
    object_value,
    read_object,
    validate_assessment,
)

from tests.code_quality.d02_assessment_history import ASSESSMENT, MAP, verify_d02_history

ROOT = Path(__file__).resolve().parents[2]
verify_d02_history(ROOT)


def test_d02_save_scope_binds_exact_owner_and_rejects_unrelated_work() -> None:
    scope = read_object(ROOT / D02_SCOPE)
    base = str(scope["base"])
    changes = object_value(scope["changes"])
    assert set(changes) == {"src/warhammer40k_core/engine/attack_sequence_grouped_allocation.py"}
    for path, change in changes.items():
        assert d02_rule_semantics_smoke_operations(
            base=base, path=path, category="rule_semantics", change=change
        ) == frozenset({"order135-gathered-attack-steps"})
        for candidate_base, candidate_path, category in (
            ("0" * 40, path, "rule_semantics"),
            (base, path + ".unreviewed", "rule_semantics"),
            (base, path, "algorithm_or_search"),
            (base, path, "cache_policy"),
            (base, path, "serialization_or_replay_work"),
        ):
            assert not d02_rule_semantics_smoke_operations(
                base=candidate_base, path=candidate_path, category=category, change=change
            )
        for field in ("before_sha256", "after_sha256"):
            drifted = copy.deepcopy(object_value(change))
            drifted[field] = "0" * 64
            assert not d02_rule_semantics_smoke_operations(
                base=base, path=path, category="rule_semantics", change=drifted
            )
        drifted = copy.deepcopy(object_value(change))
        drifted["owners"] = {}
        assert not d02_rule_semantics_smoke_operations(
            base=base, path=path, category="rule_semantics", change=drifted
        )


def test_d02_assessment_keeps_sensitive_performance_categories_blocking() -> None:
    assessment = read_object(ROOT / ASSESSMENT)
    mapping = read_object(ROOT / MAP)
    scope = read_object(ROOT / D02_SCOPE)
    for path in object_value(scope["changes"]):
        for category in ("algorithm_or_search", "cache_policy", "hot_query_or_data_structure"):
            candidate = copy.deepcopy(assessment)
            object_value(object_value(candidate["rows"])[path])["category"] = category
            with pytest.raises(ValueError, match="Missing required detailed comparisons"):
                validate_assessment(
                    candidate,
                    base=str(scope["base"]),
                    changes=object_value(assessment["changes"]),
                    runtime_id=str(assessment["runtime_build_id"]),
                    operation_map=mapping,
                )
