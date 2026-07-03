from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "warhammer40k_core"
PYPROJECT = ROOT / "pyproject.toml"
LEGACY_GEOMETRY_CORE_IMPORTS = frozenset(
    {
        "src/warhammer40k_core/geometry/measurement.py imports warhammer40k_core.core.validation",
        "src/warhammer40k_core/geometry/model_geometry.py imports warhammer40k_core.core.datasheet",
        "src/warhammer40k_core/geometry/model_geometry.py imports "
        "warhammer40k_core.core.model_geometry_catalog",
        "src/warhammer40k_core/geometry/movement_envelope.py imports "
        "warhammer40k_core.core.validation",
        "src/warhammer40k_core/geometry/pathing.py imports "
        "warhammer40k_core.core.ruleset_descriptor",
        "src/warhammer40k_core/geometry/pathing.py imports warhammer40k_core.core.unit_group",
        "src/warhammer40k_core/geometry/pathing.py imports warhammer40k_core.core.validation",
        "src/warhammer40k_core/geometry/shapely_backend.py imports "
        "warhammer40k_core.core.deployment_zones",
        "src/warhammer40k_core/geometry/spatial_index.py imports warhammer40k_core.core.objectives",
        "src/warhammer40k_core/geometry/terrain.py imports "
        "warhammer40k_core.core.ruleset_descriptor",
        "src/warhammer40k_core/geometry/terrain.py imports warhammer40k_core.core.terrain_display",
        "src/warhammer40k_core/geometry/terrain_factory.py imports "
        "warhammer40k_core.core.terrain_display",
        "src/warhammer40k_core/geometry/visibility.py imports "
        "warhammer40k_core.core.ruleset_descriptor",
        "src/warhammer40k_core/geometry/visibility.py imports warhammer40k_core.core.validation",
    }
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)

    return found


def test_engine_does_not_import_adapters() -> None:
    engine = SRC / "engine"
    if not engine.exists():
        return

    violations: list[str] = []
    for path in sorted(engine.rglob("*.py")):
        for module in _imports(path):
            if module.startswith("warhammer40k_core.adapters"):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")

    assert not violations, "Engine must not import adapters:\n" + "\n".join(violations)


def test_core_does_not_import_rules_engine_or_adapters() -> None:
    core = SRC / "core"
    if not core.exists():
        return

    violations: list[str] = []
    forbidden = (
        "warhammer40k_core.engine",
        "warhammer40k_core.adapters",
        "warhammer40k_core.rules",
    )

    for path in sorted(core.rglob("*.py")):
        for module in _imports(path):
            if module.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT).as_posix()} imports {module}")

    assert not violations, "Core import boundary violations:\n" + "\n".join(violations)


def test_geometry_does_not_import_rules_engine_adapters_or_interfaces() -> None:
    geometry = SRC / "geometry"
    if not geometry.exists():
        return

    violations: list[str] = []
    forbidden = (
        "warhammer40k_core.rules",
        "warhammer40k_core.engine",
        "warhammer40k_core.adapters",
        "warhammer40k_core.interfaces",
    )

    for path in sorted(geometry.rglob("*.py")):
        for module in _imports(path):
            if module.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT).as_posix()} imports {module}")

    assert not violations, "Geometry import boundary violations:\n" + "\n".join(violations)


def test_geometry_core_imports_are_legacy_allowlisted() -> None:
    geometry = SRC / "geometry"
    if not geometry.exists():
        return

    violations: set[str] = set()
    for path in sorted(geometry.rglob("*.py")):
        for module in _imports(path):
            if module.startswith("warhammer40k_core.core"):
                violations.add(f"{path.relative_to(ROOT).as_posix()} imports {module}")

    unexpected = sorted(violations - LEGACY_GEOMETRY_CORE_IMPORTS)
    stale_allowlist = sorted(LEGACY_GEOMETRY_CORE_IMPORTS - violations)

    assert not unexpected, "New geometry -> core imports are forbidden:\n" + "\n".join(unexpected)
    assert not stale_allowlist, "Remove stale geometry -> core allowlist entries:\n" + "\n".join(
        stale_allowlist
    )


def test_top_level_packages_are_covered_by_import_linter_contracts() -> None:
    top_level_packages = {
        path.name for path in SRC.iterdir() if path.is_dir() and path.name != "__pycache__"
    }
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    contracts = pyproject["tool"]["importlinter"]["contracts"]
    covered_packages: set[str] = set()

    for contract in contracts:
        for field_name in ("source_modules", "forbidden_modules"):
            for module_name in contract.get(field_name, ()):
                package_name = _top_level_package_name(module_name)
                if package_name is not None:
                    covered_packages.add(package_name)

    missing = sorted(top_level_packages - covered_packages)
    assert not missing, "Top-level packages lack import-linter coverage:\n" + "\n".join(missing)


def _top_level_package_name(module_name: str) -> str | None:
    prefix = "warhammer40k_core."
    if not module_name.startswith(prefix):
        return None
    return module_name[len(prefix) :].split(".", 1)[0]
