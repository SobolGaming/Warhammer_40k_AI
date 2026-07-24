from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "warhammer40k_core"
ENGINE = PACKAGE / "engine"
MFM_PACKAGE = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th" / "mfm_2026_07"
EVENT_PACKAGE = PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th"
JULY_FACTION_PACK_PACKAGE = (
    PACKAGE / "rules" / "source_packages" / "warhammer_40000_11th" / "july_faction_packs_2026_07"
)

_ALLOWED_MFM_LOADER_MODULES = {"__init__.py", "_artifacts.py"}
_FORBIDDEN_ENGINE_IMPORTS = {
    "importlib.resources",
    "warhammer40k_core.rules.source_packages.artifact_loader",
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


def test_july_faction_pack_staging_uses_typed_json_artifacts() -> None:
    python_modules = tuple(sorted(path.name for path in JULY_FACTION_PACK_PACKAGE.glob("*.py")))
    json_artifacts = tuple(
        sorted(path.name for path in (JULY_FACTION_PACK_PACKAGE / "artifacts").glob("*.json"))
    )

    assert python_modules == ("__init__.py", "_artifacts.py", "_runtime_artifacts.py")
    assert json_artifacts == (
        "chaos-daemons-daemonic-manifestation.json",
        "chaos-daemons-runtime-updates.json",
        "datasheet-support-preview.json",
        "datasheets.json",
        "delta-ledger.json",
        "detachments.json",
        "package.json",
        "phase17e-coverage.json",
        "phase17f-execution.json",
        "runtime-scaffolds.json",
        "subrules.json",
    )
    assert _line_count(JULY_FACTION_PACK_PACKAGE / "_artifacts.py") < 1500
    assert _line_count(JULY_FACTION_PACK_PACKAGE / "_runtime_artifacts.py") < 1500


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
