from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from tools import generate_faction_rule_ir_bundles as faction_rule_ir_generator
from tools.faction_rule_ir_bundle import (
    datasheet_faction_ids_from_source_snapshot,
    generate_registered_rule_ir_shard,
)

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_pack_rule_ir as runtime_rule_ir_registry,
)

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
PACKAGE = ROOT / "src" / "warhammer40k_core"
ENGINE = PACKAGE / "engine"
MFM_PACKAGE = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th" / "mfm_2026_07"
EVENT_PACKAGE = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th"
EDITION_SOURCE_PACKAGES = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th"
JULY_FACTION_PACK_PACKAGE = (
    PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th" / "july_faction_packs_2026_07"
)
FACTION_PACK_RULE_IR_PACKAGE = EDITION_SOURCE_PACKAGES / "faction_pack_rule_ir"
DATASHEETS_SOURCE_SNAPSHOT = faction_rule_ir_generator.DATASHEETS_SOURCE_PATH
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
    "CSM": "chaos-space-marines",
    "EC": "emperors-children",
    "TS": "thousand-sons",
    "WE": "world-eaters",
}
_EDITION_SOURCE_PACKAGE_CLASSIFICATION = {
    "app_core_rules_hidden_2026_08_09": "official_app_capture",
    "chaos_daemons_roster_2026_07": "official_roster_source",
    "event_companion_2026_06_artifacts": "official_event_source",
    "event_companion_layouts_2026_06": "official_event_source",
    "faction_pack_rule_ir": "datasheet_rule_ir_registry",
    "july_faction_packs_2026_07": "official_faction_pack_source",
    "july_rules_updates_2026_07": "official_rules_update_source",
    "mfm_2026_06": "official_points_source",
    "mfm_2026_07": "official_points_source",
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
        "chaos-space-marines.json",
        "emperors-children.json",
        "thousand-sons.json",
        "world-eaters.json",
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
        "chaos-space-marines",
        "emperors-children",
        "thousand-sons",
        "world-eaters",
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


def test_edition_source_package_directories_are_explicitly_classified() -> None:
    source_package_directories = _source_bearing_package_directory_names(EDITION_SOURCE_PACKAGES)

    assert source_package_directories == tuple(sorted(_EDITION_SOURCE_PACKAGE_CLASSIFICATION))
    assert tuple(
        package_name
        for package_name, package_kind in _EDITION_SOURCE_PACKAGE_CLASSIFICATION.items()
        if package_kind == "datasheet_rule_ir_registry"
    ) == ("faction_pack_rule_ir",)


@pytest.mark.parametrize(
    "relative_artifact_path",
    [
        "artifacts/package.json",
        "artifacts/datasheet-rule-ir.json",
        "deep/runtime/content.json",
        "artifacts/package.toml",
        "deep/runtime/content.bin",
    ],
)
def test_source_package_classification_is_independent_of_artifact_filename(
    tmp_path: Path,
    relative_artifact_path: str,
) -> None:
    artifact_path = tmp_path / "unreviewed_datasheet_batch_2026_08" / relative_artifact_path
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("{}\n", encoding="utf-8")

    assert _source_bearing_package_directory_names(tmp_path) == (
        "unreviewed_datasheet_batch_2026_08",
    )


def test_datasheet_rule_ir_lookup_surface_is_owned_by_the_stable_registry() -> None:
    python_rule_ir_providers = _datasheet_rule_ir_provider_symbols(EDITION_SOURCE_PACKAGES)

    assert python_rule_ir_providers == (
        "faction_pack_rule_ir/__init__.py:datasheet_rule_ir_payload_by_source_row_id",
        "faction_pack_rule_ir/__init__.py:payload_by_source_row_id",
        "faction_pack_rule_ir/_artifacts.py:datasheet_rule_ir_payload_by_source_row_id",
    )


@pytest.mark.parametrize(
    "relative_provider_path",
    [
        "renamed_datasheet_provider.py",
        "mfm_2026_07/nested/renamed_datasheet_provider.py",
    ],
)
def test_datasheet_rule_ir_provider_detection_is_independent_of_symbol_and_nesting(
    tmp_path: Path,
    relative_provider_path: str,
) -> None:
    provider_path = tmp_path / relative_provider_path
    provider_path.parent.mkdir(parents=True, exist_ok=True)
    provider_path.write_text(
        "def lookup(source_row_id: str) -> RuleIRPayload | None:\n"
        "    raise NotImplementedError(source_row_id)\n",
        encoding="utf-8",
    )

    assert _datasheet_rule_ir_provider_symbols(tmp_path) == (f"{relative_provider_path}:lookup",)


def test_source_specific_write_regenerates_complete_shared_provenance_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_paths = _redirect_rule_ir_generator_outputs(monkeypatch, tmp_path)
    publish_order: list[Path] = []

    def recording_replace(source: Path, destination: Path) -> None:
        publish_order.append(Path(destination))
        source.replace(destination)

    monkeypatch.setattr(
        faction_rule_ir_generator,
        "_replace_staged_artifact",
        recording_replace,
    )
    faction_rule_ir_generator.generate_rule_ir_package_artifacts(
        requested_shard_ids=("aeldari",),
        check=False,
    )
    original_shard_bytes = {
        shard_id: output_path.read_bytes() for shard_id, output_path in output_paths.items()
    }

    shared_source_path = tmp_path / "shared-source" / "Datasheets.json"
    shared_source_path.parent.mkdir(parents=True)
    shared_source_path.write_bytes(DATASHEETS_SOURCE_SNAPSHOT.read_bytes() + b"\n")
    monkeypatch.setattr(
        faction_rule_ir_generator,
        "DATASHEETS_SOURCE_PATH",
        shared_source_path,
    )
    drifted_artifacts = faction_rule_ir_generator.generated_rule_ir_artifacts()
    drifted_package_hash = drifted_artifacts[faction_rule_ir_generator.PACKAGE_OUTPUT_PATH][
        "package_hash"
    ]
    assert type(drifted_package_hash) is str
    monkeypatch.setattr(
        runtime_rule_ir_registry,
        "EXPECTED_PACKAGE_HASH",
        drifted_package_hash,
    )
    publish_order.clear()
    faction_rule_ir_generator.generate_rule_ir_package_artifacts(
        requested_shard_ids=("aeldari",),
        check=False,
    )

    assert publish_order == [
        *(output_paths[shard_id] for shard_id in sorted(output_paths)),
        faction_rule_ir_generator.PACKAGE_OUTPUT_PATH,
    ]
    expected_source_sha256 = hashlib.sha256(shared_source_path.read_bytes()).hexdigest()
    for shard_id, output_path in output_paths.items():
        assert output_path.read_bytes() != original_shard_bytes[shard_id]
        shard = json.loads(output_path.read_bytes())
        assert (
            shard["datasheet_faction_ids_provenance"]["source_snapshot_sha256"]
            == expected_source_sha256
        )
    _assert_manifest_references_persisted_shards(faction_rule_ir_generator.PACKAGE_OUTPUT_PATH)


def test_source_specific_write_rolls_back_package_rejected_by_real_loader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_paths = _redirect_rule_ir_generator_outputs(monkeypatch, tmp_path)
    faction_rule_ir_generator.generate_rule_ir_package_artifacts(
        requested_shard_ids=("aeldari",),
        check=False,
    )
    original_bytes = {
        **{output_path: output_path.read_bytes() for output_path in output_paths.values()},
        faction_rule_ir_generator.PACKAGE_OUTPUT_PATH: (
            faction_rule_ir_generator.PACKAGE_OUTPUT_PATH.read_bytes()
        ),
    }
    shared_source_path = tmp_path / "drifted-source" / "Datasheets.json"
    shared_source_path.parent.mkdir(parents=True)
    shared_source_path.write_bytes(DATASHEETS_SOURCE_SNAPSHOT.read_bytes() + b"\n")
    monkeypatch.setattr(
        faction_rule_ir_generator,
        "DATASHEETS_SOURCE_PATH",
        shared_source_path,
    )

    with pytest.raises(
        faction_rule_ir_generator.RuleIrPackageGenerationError,
        match="original artifact set was restored",
    ):
        faction_rule_ir_generator.generate_rule_ir_package_artifacts(
            requested_shard_ids=("aeldari",),
            check=False,
        )

    for output_path, expected_bytes in original_bytes.items():
        assert output_path.read_bytes() == expected_bytes


def test_source_specific_check_rejects_stale_sibling_shard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_paths = _redirect_rule_ir_generator_outputs(monkeypatch, tmp_path)
    faction_rule_ir_generator.generate_rule_ir_package_artifacts(
        requested_shard_ids=("aeldari",),
        check=False,
    )
    stale_sibling_path = output_paths["emperors-children"]
    stale_sibling_path.write_bytes(stale_sibling_path.read_bytes() + b"\n")

    with pytest.raises(SystemExit, match=r"emperors-children\.json"):
        faction_rule_ir_generator.main(("--check", "--shard", "aeldari"))


def test_source_specific_rule_ir_builders_share_complete_package_delegate() -> None:
    source_specific_builders: list[Path] = []
    violations: list[str] = []
    for path in sorted(TOOLS.glob("generate_*_rule_ir.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        function_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        shard_assignments = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "SHARD_ID" for target in node.targets
            )
        ]
        if "generated_artifact_payload" not in function_names or not shard_assignments:
            continue
        source_specific_builders.append(path)
        main_functions = [
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
        ]
        delegate_calls = (
            [
                node
                for node in ast.walk(main_functions[0])
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "generate_registered_rule_ir_shard"
            ]
            if len(main_functions) == 1
            else []
        )
        has_check_option = bool(main_functions) and any(
            isinstance(node, ast.Constant) and node.value == "--check"
            for node in ast.walk(main_functions[0])
        )
        delegates_shard_id = len(delegate_calls) == 1 and any(
            keyword.arg == "shard_id"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "SHARD_ID"
            for keyword in (delegate_calls[0].keywords if delegate_calls else ())
        )
        delegates_check = not has_check_option or (
            len(delegate_calls) == 1
            and any(
                keyword.arg == "check"
                and isinstance(keyword.value, ast.Attribute)
                and isinstance(keyword.value.value, ast.Name)
                and keyword.value.value.id == "args"
                and keyword.value.attr == "check"
                for keyword in delegate_calls[0].keywords
            )
        )
        if not delegates_shard_id or not delegates_check:
            violations.append(path.relative_to(ROOT).as_posix())

    assert len(source_specific_builders) == 16
    assert violations == []


@pytest.mark.parametrize(
    "shard_id",
    [
        "aeldari",
        "chaos-daemons",
        "chaos-space-marines",
        "emperors-children",
        "thousand-sons",
        "world-eaters",
    ],
)
def test_source_specific_checks_preserve_real_loader_compatibility(shard_id: str) -> None:
    generate_registered_rule_ir_shard(shard_id=shard_id, check=True)
    completed = subprocess.run(
        (
            sys.executable,
            "-c",
            (
                "from warhammer40k_core.rules.source_packages.warhammer_40000_11th "
                "import faction_pack_rule_ir as registry; "
                "assert registry.supported_shard_ids() == "
                "('aeldari', 'chaos-daemons', 'chaos-space-marines', "
                "'emperors-children', 'thousand-sons', 'world-eaters')"
            ),
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


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


def _source_bearing_package_directory_names(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            directory.name
            for directory in root.iterdir()
            if directory.is_dir()
            and any(
                candidate.is_file()
                and "__pycache__" not in candidate.parts
                and candidate.suffix != ".pyc"
                for candidate in directory.rglob("*")
            )
        )
    )


def _datasheet_rule_ir_provider_symbols(root: Path) -> tuple[str, ...]:
    providers: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name.startswith("_"):
                continue
            argument_names = {
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
            }
            if "source_row_id" not in argument_names:
                continue
            providers.append(f"{path.relative_to(root).as_posix()}:{node.name}")
    return tuple(sorted(providers))


def _redirect_rule_ir_generator_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> dict[str, Path]:
    shard_directory = tmp_path / "artifacts" / "shards"
    output_paths = {
        shard_id: shard_directory / f"{shard_id}.json"
        for shard_id in (
            "aeldari",
            "chaos-daemons",
            "chaos-space-marines",
            "emperors-children",
            "thousand-sons",
            "world-eaters",
        )
    }
    monkeypatch.setattr(
        faction_rule_ir_generator,
        "_OUTPUT_PATH_BY_SHARD_ID",
        output_paths,
    )
    monkeypatch.setattr(
        faction_rule_ir_generator,
        "PACKAGE_OUTPUT_PATH",
        shard_directory.parent / "package.json",
    )

    def validate_redirected_package() -> None:
        package_output_path = faction_rule_ir_generator.PACKAGE_OUTPUT_PATH
        try:
            runtime_rule_ir_registry.validate_package_artifact_set(
                manifest_bytes=package_output_path.read_bytes(),
                shard_bytes_by_path={
                    output_path.relative_to(package_output_path.parent).as_posix(): (
                        output_path.read_bytes()
                    )
                    for output_path in output_paths.values()
                },
                expected_package_hash=runtime_rule_ir_registry.EXPECTED_PACKAGE_HASH,
            )
        except runtime_rule_ir_registry.FactionPackRuleIrRegistryError as exc:
            raise faction_rule_ir_generator.RuleIrPackageGenerationError(
                "Redirected package failed the real runtime loader contract."
            ) from exc

    monkeypatch.setattr(
        faction_rule_ir_generator,
        "_validate_persisted_package_with_real_loader",
        validate_redirected_package,
    )
    return output_paths


def _assert_manifest_references_persisted_shards(package_output_path: Path) -> None:
    manifest = json.loads(package_output_path.read_bytes())
    for reference in manifest["shard_artifacts"].values():
        shard_path = package_output_path.parent / reference["path"]
        assert shard_path.is_file()
        assert hashlib.sha256(shard_path.read_bytes()).hexdigest() == reference["sha256"]


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
