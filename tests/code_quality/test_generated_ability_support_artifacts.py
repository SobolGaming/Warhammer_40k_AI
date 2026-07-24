from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import cast

import pytest
from tools.cross_source_semantic_equivalence import (
    DEFAULT_DOCS_PATH as DEFAULT_SEMANTIC_EQUIVALENCE_DOCS_PATH,
)
from tools.cross_source_semantic_equivalence import (
    DEFAULT_OUTPUT_PATH as DEFAULT_SEMANTIC_EQUIVALENCE_OUTPUT_PATH,
)
from tools.cross_source_semantic_equivalence import (
    DEFAULT_SOURCE_JSON_DIR as DEFAULT_SEMANTIC_EQUIVALENCE_SOURCE_JSON_DIR,
)
from tools.cross_source_semantic_equivalence import (
    cross_source_semantic_audit,
    semantic_equivalence_markdown,
)
from tools.generate_ability_support_matrix import (
    DatasheetSupportRow,
    MusteringSupportRow,
    RuntimeContentSemanticCoveragePayload,
    ability_support_matrix_rows,
    datasheet_support_rows,
    datasheet_support_rows_payload,
    mustering_support_rows,
    mustering_support_rows_payload,
    runtime_content_semantic_coverage_payload,
    support_matrix_markdown,
)

from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageCategoryRow,
    AbilityCoverageRow,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)
from warhammer40k_core.engine.semantic_equivalence import (
    CrossSourceSemanticAudit,
    SemanticContentKind,
    SemanticEquivalenceError,
    SemanticExecutionStatus,
    SemanticSupportTransfer,
    load_cross_source_semantic_audit,
)

ROOT = Path(__file__).resolve().parents[2]

_GENERATED_ARTIFACTS = (
    "data/generated/ability_coverage/ability_coverage_rows.json",
    "data/generated/ability_coverage/ability_support_category_rows.json",
    "data/generated/ability_coverage/datasheet_support_rows.json",
    "data/generated/ability_coverage/mustering_support_rows.json",
    "data/generated/ability_coverage/runtime_content_semantic_coverage.json",
    "data/generated/ability_coverage/cross_source_semantic_equivalence.json",
    "docs/ABILITY_SUPPORT_MATRIX_V2.md",
    "docs/CROSS_SOURCE_SEMANTIC_EQUIVALENCE.md",
)


@pytest.mark.parametrize("relative_path", _GENERATED_ARTIFACTS)
def test_generated_ability_support_artifacts_are_current(relative_path: str) -> None:
    path = ROOT / relative_path
    expected = (
        cast(object, json.loads(path.read_text(encoding="utf-8")))
        if path.suffix == ".json"
        else path.read_text(encoding="utf-8")
    )

    assert _generated_artifact(relative_path) == expected


def _generated_artifact(relative_path: str) -> object:
    if relative_path.endswith("ability_coverage_rows.json"):
        return ability_coverage_rows_payload(_ability_rows())
    if relative_path.endswith("ability_support_category_rows.json"):
        return ability_coverage_category_rows_payload(_category_rows())
    if relative_path.endswith("datasheet_support_rows.json"):
        return datasheet_support_rows_payload(_datasheet_support_rows())
    if relative_path.endswith("mustering_support_rows.json"):
        return mustering_support_rows_payload(_mustering_support_rows())
    if relative_path.endswith("runtime_content_semantic_coverage.json"):
        return _runtime_semantic_payload()
    if relative_path.endswith("cross_source_semantic_equivalence.json"):
        return _semantic_audit().to_payload()
    if relative_path == "docs/ABILITY_SUPPORT_MATRIX_V2.md":
        return support_matrix_markdown(
            ability_coverage_category_rows_payload(_category_rows()),
            ability_rows=ability_coverage_rows_payload(_ability_rows()),
            runtime_semantic_coverage=_runtime_semantic_payload(),
        )
    if relative_path == "docs/CROSS_SOURCE_SEMANTIC_EQUIVALENCE.md":
        return semantic_equivalence_markdown(_semantic_audit())
    raise AssertionError(f"Unknown generated support artifact: {relative_path}.")


@cache
def _ability_rows() -> tuple[AbilityCoverageRow, ...]:
    return ability_support_matrix_rows()


@cache
def _category_rows() -> tuple[AbilityCoverageCategoryRow, ...]:
    return ability_coverage_category_rows(_ability_rows())


@cache
def _datasheet_support_rows() -> tuple[DatasheetSupportRow, ...]:
    return datasheet_support_rows()


@cache
def _mustering_support_rows() -> tuple[MusteringSupportRow, ...]:
    return mustering_support_rows()


@cache
def _runtime_semantic_payload() -> RuntimeContentSemanticCoveragePayload:
    return runtime_content_semantic_coverage_payload()


@cache
def _semantic_audit() -> CrossSourceSemanticAudit:
    return cross_source_semantic_audit()


def test_cross_source_semantic_audit_default_paths_are_platform_neutral() -> None:
    expected_paths = {
        DEFAULT_SEMANTIC_EQUIVALENCE_SOURCE_JSON_DIR: (
            "data/source_snapshots/wahapedia/" + "1" + "0" + "th-edition/2026-06-14/json"
        ),
        DEFAULT_SEMANTIC_EQUIVALENCE_OUTPUT_PATH: (
            "data/generated/ability_coverage/cross_source_semantic_equivalence.json"
        ),
        DEFAULT_SEMANTIC_EQUIVALENCE_DOCS_PATH: "docs/CROSS_SOURCE_SEMANTIC_EQUIVALENCE.md",
    }

    for path, expected_relative_path in expected_paths.items():
        assert path.is_absolute()
        assert path.relative_to(ROOT).as_posix() == expected_relative_path


def test_cross_source_semantic_audit_covers_every_supported_content_surface() -> None:
    audit = _semantic_audit()
    counts = {
        kind: sum(member.content_kind is kind for member in audit.members)
        for kind in SemanticContentKind
    }

    assert {member.content_kind for member in audit.members} == set(SemanticContentKind)
    assert counts == {
        SemanticContentKind.FACTION_RULE: 28,
        SemanticContentKind.DATASHEET_ABILITY: 2049,
        SemanticContentKind.DETACHMENT_RULE: 266,
        SemanticContentKind.ENHANCEMENT: 732,
        SemanticContentKind.STRATAGEM: 1095,
    }
    assert CrossSourceSemanticAudit.from_payload(audit.to_payload()) == audit
    assert (
        load_cross_source_semantic_audit(
            ROOT
            / "data"
            / "generated"
            / "ability_coverage"
            / "cross_source_semantic_equivalence.json"
        )
        == audit
    )
    assert audit.equivalence_groups()
    assert all(
        member.support_transfer is SemanticSupportTransfer.NONE
        for member in audit.members
        if member.semantic_hash is None
    )

    stale_payload = audit.to_payload()
    stale_payload["members"][0]["rule_name"] = "Drifted rule name"
    with pytest.raises(SemanticEquivalenceError, match="payload is stale"):
        CrossSourceSemanticAudit.from_payload(stale_payload)


def test_cross_source_semantic_audit_reports_both_shalaxi_sources_as_engine_consumed() -> None:
    audit = _semantic_audit()
    expected_consumers = {
        "No Prey Can Evade": (
            "catalog-ir:advance-roll-reroll",
            "catalog-ir:charge-roll-reroll",
        ),
        "Monarch of the Hunt": (
            "catalog-ir:tracked-target-destroyed-reselect",
            "catalog-ir:tracked-target-reroll",
            "catalog-ir:tracked-target-selection",
        ),
    }

    for ability_name, consumer_ids in expected_consumers.items():
        chaos_daemons = audit.member(
            content_kind=SemanticContentKind.DATASHEET_ABILITY,
            owner_id="000001648",
            rule_name=ability_name,
        )
        emperors_children = audit.member(
            content_kind=SemanticContentKind.DATASHEET_ABILITY,
            owner_id="000004094",
            rule_name=ability_name,
        )

        assert chaos_daemons.semantic_hash == emperors_children.semantic_hash
        assert chaos_daemons.equivalence_hash == emperors_children.equivalence_hash
        assert chaos_daemons.execution_status is SemanticExecutionStatus.ENGINE_CONSUMED
        assert emperors_children.execution_status is SemanticExecutionStatus.ENGINE_CONSUMED
        assert chaos_daemons.runtime_consumer_ids == consumer_ids
        assert emperors_children.runtime_consumer_ids == consumer_ids
        assert chaos_daemons.support_transfer is SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR
        assert (
            emperors_children.support_transfer is SemanticSupportTransfer.CONTENT_NEUTRAL_GENERIC_IR
        )
