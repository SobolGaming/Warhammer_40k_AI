"""Prevent defensive restore from reintroducing individual-pool attack bounds."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_defensive_profiles_share_the_live_gathered_contribution_validator() -> None:
    scope = ast.parse((ENGINE / "random_profile_scope_authority.py").read_text())
    calls = {
        node.func.id
        for node in ast.walk(scope)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "validate_profile_attack_group" in calls
    assert "validate_generated_profile_attack" in calls
    assert not any(
        isinstance(node, ast.Constant) and node.value == "attack_pools" for node in ast.walk(scope)
    )
    group = ast.parse((ENGINE / "random_profile_attack_groups.py").read_text())
    calls = {
        node.func.id
        for node in ast.walk(group)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_validate_gathered_group_matches_attack_pools" in calls
    assert "identical_attack_signature" in calls
    assert "selected_attack_weapon_group_from_result" in calls
