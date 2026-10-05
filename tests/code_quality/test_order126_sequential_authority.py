"""P03G keeps physical occupancy in one owner and historical source truth intact."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "engine/phases/movement_geometry.py",
        "engine/fight_movement_paths.py",
        "engine/scout_movement_paths.py",
        "engine/triggered_movement_resolution.py",
        "engine/charge_move_geometry.py",
    ],
)
def test_all_physical_occupancy_wrappers_delegate_complete_witness_to_one_owner(path: str) -> None:
    source = ROOT / "src/warhammer40k_core" / path
    tree = ast.parse(source.read_text(encoding="utf-8"))
    name = (
        "_friendly_geometry_models_for_charge_path"
        if "charge" in path
        else "_friendly_geometry_models_for_path"
    )
    owner = next(row for row in tree.body if isinstance(row, ast.FunctionDef) and row.name == name)
    assert len(owner.body) == 1
    returned = owner.body[0]
    assert isinstance(returned, ast.Return)
    assert isinstance(returned.value, ast.Call)
    assert isinstance(returned.value.func, ast.Name)
    assert returned.value.func.id == "sequential_friendly_models"
    witness = next(row.value for row in returned.value.keywords if row.arg == "witness")
    assert isinstance(witness, ast.Name)
    assert witness.id == "witness"


def test_selected_source_pins_and_original_fixture_archives_remain_exact() -> None:
    audit = json.loads((ROOT / "data/source_audits/order126/source.audit.json").read_bytes())
    assert audit["requirement_id"] == "03.01-obligation-03"
    assert audit["selected_block"]["ordinal"] == 2
    actual = fingerprint(audit["selected_block"]["value"])
    assert actual == audit["selected_block"]["sha256"]
    for name, expected in audit["pinned_git_blob_sha256"].items():
        # These four immutable inputs use canonical LF bytes in the repository.
        raw = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == expected
    mapping = json.loads((ROOT / "data/source_audits/order126/historical-inputs.json").read_bytes())
    for row in mapping["files"]:
        raw = (ROOT / row["historical_path"]).read_bytes()
        assert len(raw) == row["bytes"]
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]


@pytest.mark.parametrize("mutation", ["base", "category", "owner", "path"])
@pytest.mark.parametrize(
    "bound_path, operation",
    [
        ("src/warhammer40k_core/geometry/pathing.py", "geometry-search"),
        ("tests/normal_move_occurrence_helpers.py", "fixture-movement"),
    ],
)
def test_order126_smoke_scope_rejects_unbound_inputs(
    mutation: str, bound_path: str, operation: str
) -> None:
    from tools.performance_policy import (
        ORDER126_SCOPE,
        _order126_smoke_operations,  # pyright: ignore[reportPrivateUsage]
        object_value,
        read_object,
    )

    scope = read_object(ROOT / ORDER126_SCOPE)
    base = str(scope["base"])
    path = bound_path
    change = object_value(scope["changes"])[path]
    category = "rule_semantics"
    assert _order126_smoke_operations(
        base=base, path=path, category=category, change=change
    ) == frozenset({operation})
    if mutation == "base":
        base = "0" * 40
    elif mutation == "category":
        category = "algorithm_or_search"
    elif mutation == "owner":
        change = {**object_value(change), "after_sha256": "0" * 64}
    else:
        path = "src/warhammer40k_core/geometry/volume.py"
    assert not _order126_smoke_operations(base=base, path=path, category=category, change=change)
