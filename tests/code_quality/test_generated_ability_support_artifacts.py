from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import cast

import pytest
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

ROOT = Path(__file__).resolve().parents[2]

_GENERATED_ARTIFACTS = (
    "data/generated/ability_coverage/ability_coverage_rows.json",
    "data/generated/ability_coverage/ability_support_category_rows.json",
    "data/generated/ability_coverage/datasheet_support_rows.json",
    "data/generated/ability_coverage/mustering_support_rows.json",
    "data/generated/ability_coverage/runtime_content_semantic_coverage.json",
    "docs/ABILITY_SUPPORT_MATRIX_V2.md",
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
    if relative_path == "docs/ABILITY_SUPPORT_MATRIX_V2.md":
        return support_matrix_markdown(
            ability_coverage_category_rows_payload(_category_rows()),
            ability_rows=ability_coverage_rows_payload(_ability_rows()),
            runtime_semantic_coverage=_runtime_semantic_payload(),
        )
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
