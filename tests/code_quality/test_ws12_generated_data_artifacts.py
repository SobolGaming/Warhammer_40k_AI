from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.faction_rule_ir_bundle import datasheet_faction_ids_from_source_snapshot
from tools.generate_faction_rule_ir_bundles import (
    DATASHEETS_SOURCE_PATH as DATASHEETS_SOURCE_SNAPSHOT,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "warhammer40k_core"
ENGINE = PACKAGE / "engine"
MFM_PACKAGE = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th" / "mfm_2026_07"
EVENT_PACKAGE = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th"
EDITION_SOURCE_PACKAGES = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th"
JULY_FACTION_PACK_PACKAGE = (
    PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th" / "july_faction_packs_2026_07"
)
FACTION_PACK_RULE_IR_PACKAGE = EDITION_SOURCE_PACKAGES / "faction_pack_rule_ir"
DATASHEET_ABILITIES_SOURCE_SNAPSHOT = DATASHEETS_SOURCE_SNAPSHOT.with_name(
    "Datasheets_abilities.json"
)

_ALLOWED_MFM_LOADER_MODULES = {"__init__.py", "_artifacts.py"}
_FORBIDDEN_ENGINE_IMPORTS = {
    "importlib.resources",
    "warhammer40k_core.rules.source_packages.artifact_loader",
}
_CANONICAL_FACTION_ID_BY_SOURCE_ID = {
    "AE": "aeldari",
    "CD": "chaos-daemons",
    "EC": "emperors-children",
    "TS": "thousand-sons",
}


def test_ws12_mfm_generated_payloads_are_json_artifacts_not_python_modules() -> None:
    unexpected_python_modules = tuple(
        sorted(
            path.name
            for path in MFM_PACKAGE.glob("*.py")
            if path.name not in _ALLOWED_MFM_LOADER_MODULES
        )
    )
    faction_artifacts = tuple(sorted((MFM_PACKAGE / "artifacts" / "factions").glob("*.json")))

    assert unexpected_python_modules == ()
    assert (MFM_PACKAGE / "artifacts" / "package.json").is_file()
    assert len(faction_artifacts) == 28


def test_ws12_event_companion_base_sizes_are_json_artifact_backed() -> None:
    loader = EVENT_PACKAGE / "event_companion_base_size_rows.py"
    artifact = EVENT_PACKAGE / "event_companion_base_size_rows.json"

    assert artifact.is_file()
    assert _line_count(loader) < 1500


def test_july_faction_pack_current_source_uses_typed_json_artifacts() -> None:
    python_modules = tuple(sorted(path.name for path in JULY_FACTION_PACK_PACKAGE.glob("*.py")))
    json_artifacts = tuple(
        sorted(path.name for path in (JULY_FACTION_PACK_PACKAGE / "artifacts").glob("*.json"))
    )

    assert python_modules == ("__init__.py", "_artifacts.py", "_runtime_artifacts.py")
    assert json_artifacts == (
        "chaos-daemons-daemonic-manifestation.json",
        "chaos-daemons-runtime-updates.json",
        "chaos-space-marines-defiler.json",
        "current-sources.json",
        "datasheet-support-preview.json",
        "datasheets.json",
        "delta-ledger.json",
        "detachments.json",
        "emperors-children-exalted-patron.json",
        "package.json",
        "phase17e-coverage.json",
        "phase17f-execution.json",
        "runtime-scaffolds.json",
        "subrules.json",
        "thousand-sons-defiler.json",
    )
    assert _line_count(JULY_FACTION_PACK_PACKAGE / "_artifacts.py") < 1500
    assert _line_count(JULY_FACTION_PACK_PACKAGE / "_runtime_artifacts.py") < 1500


def test_datasheet_rule_ir_uses_one_stable_physical_sharded_package() -> None:
    python_modules = tuple(sorted(path.name for path in FACTION_PACK_RULE_IR_PACKAGE.glob("*.py")))
    shard_artifacts = tuple(
        sorted(
            path.name
            for path in (FACTION_PACK_RULE_IR_PACKAGE / "artifacts" / "shards").glob("*.json")
        )
    )

    assert python_modules == ("__init__.py", "_artifacts.py")
    assert (FACTION_PACK_RULE_IR_PACKAGE / "artifacts" / "package.json").is_file()
    assert shard_artifacts == (
        "aeldari.json",
        "chaos-daemons.json",
        "emperors-children.json",
    )


def test_datasheet_rule_ir_shards_record_source_backed_faction_identity() -> None:
    source_raw = DATASHEETS_SOURCE_SNAPSHOT.read_bytes()
    source_payload = json.loads(source_raw)
    source_rows = {row["source_row_id"]: row["fields"] for row in source_payload["rows"]}
    expected_provenance = {
        "source_snapshot_filename": DATASHEETS_SOURCE_SNAPSHOT.name,
        "source_snapshot_sha256": hashlib.sha256(source_raw).hexdigest(),
        "source_artifact_hash": source_payload["artifact_hash"],
    }
    manifest = json.loads(
        (FACTION_PACK_RULE_IR_PACKAGE / "artifacts" / "package.json").read_bytes()
    )

    assert "faction_artifacts" not in manifest
    assert tuple(sorted(manifest["shard_artifacts"])) == (
        "aeldari",
        "chaos-daemons",
        "emperors-children",
    )
    for shard_id, reference in manifest["shard_artifacts"].items():
        assert reference["path"] == f"shards/{shard_id}.json"
        shard = json.loads(
            (FACTION_PACK_RULE_IR_PACKAGE / "artifacts" / reference["path"]).read_bytes()
        )
        datasheet_ids = tuple(reference["datasheet_ids"])
        expected_faction_ids = {
            datasheet_id: _CANONICAL_FACTION_ID_BY_SOURCE_ID[
                source_rows[datasheet_id]["faction_id"]
            ]
            for datasheet_id in datasheet_ids
        }

        assert "faction_id" not in shard
        assert shard["artifact_schema"] == "core-v2-faction-pack-rule-ir-shard-v1"
        assert shard["shard_id"] == shard_id
        assert shard["datasheet_faction_ids"] == expected_faction_ids
        assert shard["datasheet_faction_ids_provenance"] == expected_provenance

    chaos_daemons = json.loads(
        (FACTION_PACK_RULE_IR_PACKAGE / "artifacts" / "shards" / "chaos-daemons.json").read_bytes()
    )
    assert chaos_daemons["datasheet_faction_ids"]["000004127"] == "thousand-sons"
    assert chaos_daemons["datasheet_faction_ids"]["000004128"] == "thousand-sons"
    chaos_component = chaos_daemons["source_packages"]["gw-11e-chaos-daemons-datasheet-ir-2026-27"]
    ability_source_raw = DATASHEET_ABILITIES_SOURCE_SNAPSHOT.read_bytes()
    ability_source_payload = json.loads(ability_source_raw)
    assert chaos_component["source_snapshot_filename"] == "Datasheets_abilities.json"
    assert (
        chaos_component["source_snapshot_sha256"] == hashlib.sha256(ability_source_raw).hexdigest()
    )
    assert chaos_component["source_artifact_hash"] == ability_source_payload["artifact_hash"]
    assert chaos_component["datasheet_source_snapshot_filename"] == "Datasheets.json"
    assert (
        chaos_component["datasheet_source_snapshot_sha256"]
        == hashlib.sha256(source_raw).hexdigest()
    )
    assert chaos_component["datasheet_source_artifact_hash"] == source_payload["artifact_hash"]


def test_datasheet_faction_identity_resolution_is_typed_and_fail_closed(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "Datasheets.json"
    source_payload = {
        "artifact_hash": "a" * 64,
        "rows": [
            {
                "source_row_id": "000000001",
                "fields": {
                    "id": "000000001",
                    "faction_id": "AE",
                },
            }
        ],
    }
    source_raw = json.dumps(source_payload, sort_keys=True).encode("utf-8")
    source_path.write_bytes(source_raw)

    faction_ids, provenance = datasheet_faction_ids_from_source_snapshot(
        source_snapshot_path=source_path,
        datasheet_ids=("000000001",),
        canonical_faction_id_by_source_id=_CANONICAL_FACTION_ID_BY_SOURCE_ID,
    )

    assert faction_ids == {"000000001": "aeldari"}
    assert provenance == {
        "source_snapshot_filename": "Datasheets.json",
        "source_snapshot_sha256": hashlib.sha256(source_raw).hexdigest(),
        "source_artifact_hash": "a" * 64,
    }

    unknown_faction_payload = {
        "artifact_hash": "a" * 64,
        "rows": [
            {
                "source_row_id": "000000001",
                "fields": {
                    "id": "000000001",
                    "faction_id": "UNKNOWN",
                },
            }
        ],
    }
    source_path.write_text(json.dumps(unknown_faction_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown source faction ID"):
        datasheet_faction_ids_from_source_snapshot(
            source_snapshot_path=source_path,
            datasheet_ids=("000000001",),
            canonical_faction_id_by_source_id=_CANONICAL_FACTION_ID_BY_SOURCE_ID,
        )

    with pytest.raises(ValueError, match="missing datasheet IDs"):
        datasheet_faction_ids_from_source_snapshot(
            source_snapshot_path=source_path,
            datasheet_ids=("000000002",),
            canonical_faction_id_by_source_id=_CANONICAL_FACTION_ID_BY_SOURCE_ID,
        )


def test_datasheet_work_batches_cannot_create_top_level_source_packages() -> None:
    legacy_artifact_directories = tuple(
        sorted(
            path.name
            for path in EDITION_SOURCE_PACKAGES.iterdir()
            if path.is_dir() and (path / "artifacts" / "rule_ir.json").is_file()
        )
    )
    python_rule_ir_providers = tuple(
        sorted(
            path.name
            for path in EDITION_SOURCE_PACKAGES.glob("*.py")
            if path.name != "__init__.py"
            and "datasheet_rule_ir_payload_by_source_row_id" in path.read_text(encoding="utf-8")
        )
    )

    assert legacy_artifact_directories == ()
    assert python_rule_ir_providers == ()


def test_ws12_engine_runtime_does_not_read_source_package_json_artifacts_directly() -> None:
    violations: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _FORBIDDEN_ENGINE_IMPORTS:
                        violations.append(f"{rel}:{node.lineno}:import {alias.name}")
                continue
            if isinstance(node, ast.ImportFrom):
                if node.module in _FORBIDDEN_ENGINE_IMPORTS:
                    violations.append(f"{rel}:{node.lineno}:from {node.module}")
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _looks_like_generated_source_json_reference(node.value):
                    violations.append(f"{rel}:{node.lineno}:generated source JSON reference")
                continue
            if isinstance(node, ast.Call) and _call_reads_json_file(node):
                violations.append(f"{rel}:{node.lineno}:direct JSON file read")

    assert not violations, (
        "Engine runtime must consume generated data through typed rules loaders:\n"
        + "\n".join(violations)
    )


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _looks_like_generated_source_json_reference(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return normalized.endswith(".json") and (
        "rules/source_packages" in normalized or "artifacts/" in normalized
    )


def _call_reads_json_file(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name) and node.func.id == "open":
        return _has_json_path_argument(node)
    if isinstance(node.func, ast.Attribute) and node.func.attr in {"read_text", "read_bytes"}:
        return _has_json_path_argument(node)
    return False


def _has_json_path_argument(node: ast.Call) -> bool:
    for arg in node.args:
        if (
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and arg.value.replace("\\", "/").endswith(".json")
        ):
            return True
    return False
