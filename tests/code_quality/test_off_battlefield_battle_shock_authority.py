from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"


def test_battle_shock_live_consumers_share_model_presence_authority() -> None:
    for filename, function_name in (
        ("battle_shock.py", "collect_battle_shock_test_requests"),
        ("battle_shock_test_service.py", "materialize_battle_shock_test_request"),
        ("battle_shock_pending_authority.py", "_expected_live_test_request"),
        ("command_battle_shock_phase_authority.py", "unsupported_candidate_status"),
    ):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        calls = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "battle_shock_model_ids" in calls, filename
        assert "placed_alive_geometry_models_for_rules_unit" not in calls, filename


def test_historical_request_validation_uses_strength_authority_separate_from_geometry() -> None:
    tree = ast.parse((ROOT / "battle_shock_event_authority.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_validate_historical_request_semantics"
    )
    calls = {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "battle_shock_model_ids" in calls
    assert "placed_alive_model_ids" not in calls
