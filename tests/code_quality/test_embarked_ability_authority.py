from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "src" / "warhammer40k_core" / "engine"


def _calls(path: str) -> set[str]:
    tree = ast.parse((ENGINE / path).read_text(encoding="utf-8"))
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
    }


def test_nonspatial_ability_sources_use_shared_presence_authority() -> None:
    modules = (
        "catalog_any_phase_once_per_battle.py",
        "catalog_once_per_battle_runtime.py",
        "catalog_shadow_form_runtime.py",
        "catalog_tracked_target_runtime.py",
        "catalog_conditional_leading_runtime.py",
        "catalog_command_point_runtime.py",
        "catalog_selected_target_effects.py",
        "catalog_movement_end_selected_target_effects.py",
        "catalog_post_fight_selected_target_runtime.py",
        "catalog_command_restoration_runtime.py",
    )
    forbidden = {
        "catalog_rule_current_placed_alive_model_instance_ids_for_unit",
        "placed_alive_models_for_component_unit",
    }
    for module in modules:
        calls = _calls(module)
        assert "active_ability_model_ids_for_unit" in calls, module
        assert not calls & forbidden, module


def test_live_and_historical_spatial_consumers_share_self_and_off_battlefield_policy() -> None:
    for module in (
        "rule_aura_resolution.py",
        "unit_proximity.py",
        "catalog_selected_target_effects_support.py",
        "catalog_attack_context_rule_runtime.py",
        "catalog_command_point_runtime.py",
        "catalog_command_restoration_runtime.py",
        "catalog_battle_shock_runtime.py",
        "catalog_datasheet_rule_runtime.py",
    ):
        assert "ability_spatial_relationship" in _calls(module), module
    calls = _calls("battle_shock_historical_authority.py")
    assert {
        "ability_presence_from_model_ids",
        "ability_spatial_relationship_from_presence",
    } <= calls
    assert "ability_battlefield_conditions_apply" in _calls("catalog_command_point_runtime.py")
