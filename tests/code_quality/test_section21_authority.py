"""Shared Section21 authorities stay explicit and source-neutral."""

import ast
from pathlib import Path


def test_reactive_inventory_prevalidation_and_resolver_share_one_predicate() -> None:
    root = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"
    for filename, function in (
        ("triggered_movement.py", "invalid_triggered_movement_proposal_status"),
        ("triggered_movement_physical_authority.py", "validate_triggered_movement_source_witness"),
    ):
        tree = ast.parse((root / filename).read_text(encoding="utf8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
        assert any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "triggered_movement_witness_matches_source"
            for n in ast.walk(fn)
        )


def test_all_terrain_transit_is_derived_from_selected_physical_flight() -> None:
    root = Path(__file__).resolve().parents[2] / "src/warhammer40k_core"
    engine = (root / "engine/movement_legality.py").read_text(encoding="utf8")
    geometry = (root / "geometry/pathing.py").read_text(encoding="utf8")
    assert (
        "can_transit_all_terrain=flying and descriptor.fly_policy.may_move_through_terrain"
        in engine
    )
    assert "can_transit_all_terrain=self.capabilities.can_transit_all_terrain" in engine
    assert "if self.can_transit_all_terrain:" in geometry
    assert "classified_feature_transit_permission(" in geometry
