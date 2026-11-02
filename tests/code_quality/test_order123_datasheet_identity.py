"""Catalog identity and effective consumers retain selected immutable authority."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as daemons,
)

ROOT = Path(__file__).resolve().parents[2]
PRE_DESCRIPTION_COMMIT = "b9d5a54999e9d014cd823a7d2d5c654f05ba2666"
HISTORICAL_CATALOG_SHA256 = "eec0195ebc35da304780ef213f73ffda307121c2a8d0d5c6a74d20d99c127663"
CATALOG_PATH = (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "chaos_daemons_roster_2026_07/artifacts/catalog.json"
)


def _historical_catalog_bytes() -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{PRE_DESCRIPTION_COMMIT}:{CATALOG_PATH}"], cwd=ROOT
    )


def _assert_official_catalog_history(historical_raw: bytes, current_raw: bytes) -> None:
    # Order123 evidence stays byte-exact; current prose has its own strict admission.
    assert hashlib.sha256(historical_raw).hexdigest() == HISTORICAL_CATALOG_SHA256
    historical = CanonicalCatalogPackage.from_payload(
        cast(CanonicalCatalogPackagePayload, json.loads(historical_raw))
    )
    daemons.validate_catalog_against_reconciliation(
        catalog=historical.army_catalog, reconciliation=daemons.reconciliation_manifest()
    )
    current = CanonicalCatalogPackage.from_payload(
        cast(CanonicalCatalogPackagePayload, json.loads(current_raw))
    )
    # Reuse the loader's full package pin, provenance and exact current derivation.
    assert current == daemons.catalog_package()
    daemons.validate_current_catalog_against_reconciliation(
        catalog=current.army_catalog, reconciliation=daemons.reconciliation_manifest()
    )


def test_name_keyword_permission_preserves_exact_source_and_official_admission() -> None:
    audit = json.loads((ROOT / "data/source_audits/order123/source.audit.json").read_bytes())
    raw = (ROOT / audit["selected_sources_path"]).read_bytes()
    selected = {row["row_id"]: row for row in json.loads(raw)}
    assert audit["selected_sources_sha256"] == hashlib.sha256(raw).hexdigest()
    assert audit["selected_core_rows"] == [selected["rule:02:02.01.01:1"]]
    assert audit["requirements"] == ["02.01.01-obligation-01"]
    assert audit["current_faction_admission"] is False
    assert audit["source_admission_unchanged"] is True
    official = audit["official_provider_trace"]
    assert official["catalog_path"] == CATALOG_PATH
    assert official["catalog_sha256"] == HISTORICAL_CATALOG_SHA256
    assert (
        hashlib.sha256((ROOT / official["reconciliation_path"]).read_bytes()).hexdigest()
        == official["reconciliation_sha256"]
    )
    _assert_official_catalog_history(
        _historical_catalog_bytes(), (ROOT / CATALOG_PATH).read_bytes()
    )


@pytest.mark.parametrize("historical_raw", [b"", b"{}"])
def test_official_catalog_history_requires_original_evidence(historical_raw: bytes) -> None:
    with pytest.raises(AssertionError):
        _assert_official_catalog_history(historical_raw, (ROOT / CATALOG_PATH).read_bytes())


@pytest.mark.parametrize("change", ["historical", "description", "parameter", "name"])
def test_official_catalog_history_requires_admitted_current_catalog(change: str) -> None:
    historical_raw = _historical_catalog_bytes()
    if change == "historical":
        current_raw = historical_raw
    else:
        current = daemons.catalog_package()
        datasheet = next(
            row
            for row in current.army_catalog.datasheets
            if any(ability.ability_id == "000008339" for ability in row.abilities)
        )
        ability = next(
            ability for ability in datasheet.abilities if ability.ability_id == "000008339"
        )
        if change == "description":
            changed = replace(ability, effect_description=ability.effect_description + " Changed.")
            datasheet = replace(
                datasheet,
                abilities=tuple(changed if a is ability else a for a in datasheet.abilities),
            )
        elif change == "parameter":
            changed = replace(ability, parameter_tokens=("999",))
            datasheet = replace(
                datasheet,
                abilities=tuple(changed if a is ability else a for a in datasheet.abilities),
            )
        else:
            datasheet = replace(datasheet, name=datasheet.name + " Changed")
        current = replace(
            current,
            army_catalog=replace(
                current.army_catalog,
                datasheets=tuple(
                    datasheet if row.datasheet_id == datasheet.datasheet_id else row
                    for row in current.army_catalog.datasheets
                ),
            ),
        )
        # Recompute the generic package hash; the exact admitted package must still reject it.
        current_raw = json.dumps(current.to_payload()).encode()
    with pytest.raises(AssertionError):
        _assert_official_catalog_history(historical_raw, current_raw)


@pytest.mark.parametrize(
    ("path", "function"),
    [
        ("engine/army_mustering.py", "_datasheet_keyword_set"),
        ("engine/army_mustering.py", "_datasheet_has_any_keyword"),
        ("engine/army_mustering.py", "_transport_capacity_allows_datasheet"),
        ("engine/list_validation.py", "_datasheet_has_any_keyword"),
        ("engine/roster_unit_limits.py", "datasheet_unit_limit"),
    ],
)
def test_catalog_name_queries_consume_shared_effective_identity(path: str, function: str) -> None:
    tree = ast.parse((ROOT / "src/warhammer40k_core" / path).read_text(encoding="utf-8"))
    owner = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function
    )
    attributes = {ast.unparse(node) for node in ast.walk(owner) if isinstance(node, ast.Attribute)}
    assert "datasheet.effective_keywords" in attributes
    assert "datasheet.keywords.keywords" not in attributes


def test_runtime_keyword_owners_do_not_derive_identity_from_display_labels() -> None:
    for path in ("unit_keyword_queries.py", "catalog_model_scope.py", "rule_target_resolution.py"):
        tree = ast.parse((ROOT / "src/warhammer40k_core/engine" / path).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "name" for node in ast.walk(tree)
        )
