from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING or __package__:
    from tools.aeldari_ability_semantic_descriptions import (
        DESCRIPTION_ARTIFACT_PATH,
        DESCRIPTION_TEXT_PATH,
        GENERATED_BY,
        SCHEMA_VERSION,
        documentation_bucket_for_stage,
    )
    from tools.aeldari_datasheet_semantic_coverage import (
        COVERAGE_PATH,
        aeldari_datasheet_semantic_coverage,
    )
    from tools.aeldari_datasheet_semantic_coverage import (
        SCHEMA_VERSION as COVERAGE_SCHEMA_VERSION,
    )
else:
    from aeldari_ability_semantic_descriptions import (
        DESCRIPTION_ARTIFACT_PATH,
        DESCRIPTION_TEXT_PATH,
        GENERATED_BY,
        SCHEMA_VERSION,
        documentation_bucket_for_stage,
    )
    from aeldari_datasheet_semantic_coverage import (
        COVERAGE_PATH,
        aeldari_datasheet_semantic_coverage,
    )
    from aeldari_datasheet_semantic_coverage import (
        SCHEMA_VERSION as COVERAGE_SCHEMA_VERSION,
    )

DESCRIPTION_TEXT_SCHEMA_VERSION = "1"
_DESCRIPTION_TEXT_ROOT_KEYS = frozenset({"schema_version", "descriptions"})
_DESCRIPTION_TEXT_ROW_KEYS = frozenset({"ability_id", "description"})


def main() -> None:
    payload = generated_aeldari_ability_semantic_descriptions()
    DESCRIPTION_ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DESCRIPTION_ARTIFACT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generated_aeldari_ability_semantic_descriptions() -> dict[str, object]:
    descriptions_by_ability_id = _description_text_by_ability_id()
    coverage = aeldari_datasheet_semantic_coverage()
    abilities_by_id = {
        ability.ability_id: (datasheet, ability)
        for datasheet in coverage.rows
        for ability in datasheet.abilities
    }
    if len(abilities_by_id) != sum(len(row.abilities) for row in coverage.rows):
        raise ValueError("Aeldari reviewed ability IDs must be globally unique.")
    if descriptions_by_ability_id.keys() != abilities_by_id.keys():
        missing = sorted(abilities_by_id.keys() - descriptions_by_ability_id.keys())
        unexpected = sorted(descriptions_by_ability_id.keys() - abilities_by_id.keys())
        raise ValueError(
            "Aeldari semantic-description text does not exactly partition reviewed abilities; "
            f"missing={missing!r}, unexpected={unexpected!r}."
        )
    rows: list[dict[str, object]] = []
    for datasheet in coverage.rows:
        for ability in datasheet.abilities:
            rows.append(
                {
                    "datasheet_id": datasheet.datasheet_id,
                    "datasheet_name": datasheet.datasheet_name,
                    "ability_id": ability.ability_id,
                    "ability_name": ability.ability_name,
                    "source_kind": ability.source_kind.value,
                    "source_row_id": ability.source_row_id,
                    "source_ids": list(ability.source_ids),
                    "raw_text_sha256": ability.raw_text_sha256,
                    "normalized_text_sha256": ability.normalized_text_sha256,
                    "catalog_support": ability.catalog_support.value,
                    "support_stage": ability.support_stage.value,
                    "semantic_consumers": [
                        semantic.to_payload() for semantic in ability.semantic_consumers
                    ],
                    "runtime_consumer_ids": list(ability.runtime_consumer_ids),
                    "diagnostic_reasons": list(ability.diagnostic_reasons),
                    "documentation_bucket": documentation_bucket_for_stage(ability.support_stage),
                    "description": descriptions_by_ability_id[ability.ability_id],
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "coverage_schema_version": COVERAGE_SCHEMA_VERSION,
        "coverage_sha256": _sha256(COVERAGE_PATH),
        "description_text_sha256": _sha256(DESCRIPTION_TEXT_PATH),
        "exact_ability_count": len(rows),
        "descriptions": rows,
    }


def _description_text_by_ability_id() -> dict[str, str]:
    payload = _load_object(DESCRIPTION_TEXT_PATH)
    _require_exact_keys(
        payload,
        _DESCRIPTION_TEXT_ROOT_KEYS,
        "Aeldari semantic-description text manifest",
    )
    if payload["schema_version"] != DESCRIPTION_TEXT_SCHEMA_VERSION:
        raise ValueError("Aeldari semantic-description text schema is unsupported.")
    rows = tuple(
        _object(raw, "Aeldari semantic-description text row")
        for raw in _required_list(payload, "descriptions")
    )
    descriptions: dict[str, str] = {}
    for row in rows:
        _require_exact_keys(
            row,
            _DESCRIPTION_TEXT_ROW_KEYS,
            "Aeldari semantic-description text row",
        )
        ability_id = _required_text(row, "ability_id")
        if ability_id in descriptions:
            raise ValueError("Aeldari semantic-description text contains duplicate ability IDs.")
        descriptions[ability_id] = _required_text(row, "description")
    return descriptions


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}.") from exc
    return _object(value, str(path))


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object.")
    return cast(dict[str, Any], value)


def _require_exact_keys(payload: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(payload)
    if actual != expected:
        raise ValueError(
            f"{label} keys drifted; missing={sorted(expected - actual)!r}, "
            f"unexpected={sorted(actual - expected)!r}."
        )


def _required_list(payload: dict[str, Any], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key!r} must be a JSON list.")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], key: str) -> str:
    if key not in payload:
        raise ValueError(f"Missing required field {key!r}.")
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key!r} must be non-empty text.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
