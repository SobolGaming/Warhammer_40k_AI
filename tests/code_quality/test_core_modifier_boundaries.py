from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src/warhammer40k_core"


def _calls(relative_path: str, function_name: str, *, class_name: str | None = None) -> set[str]:
    tree = ast.parse((PACKAGE / relative_path).read_text(encoding="utf-8"))
    scope: ast.AST = tree
    if class_name is not None:
        scope = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    function = next(
        node
        for node in ast.walk(scope)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
    }


def test_modified_dice_and_targeting_ranges_use_the_shared_limits() -> None:
    assert "resolve_roll_modifiers" in _calls("core/modified_dice.py", "from_unmodified")
    assert "resolve_roll_modifiers" in _calls(
        "core/modified_dice.py",
        "__post_init__",
        class_name="ModifiedRollResult",
    )
    assert "resolve_targeting_range" in _calls(
        "engine/hidden_detection.py",
        "hidden_detection_eligible_target_model_ids",
    )
    assert "resolve_targeting_range" in _calls(
        "engine/lone_operative.py", "lone_operative_target_allowed"
    )
    for name in ("_roll_hit", "_roll_wound", "_reroll_wound_for_twin_linked_if_needed"):
        assert "bound_modified_roll" in _calls("engine/attack_sequence_hit_wound.py", name)
    assert "bound_modified_roll" in _calls("engine/saves.py", "_final_roll_for_save_option")


def test_advance_and_charge_never_embed_modifiers_in_raw_dice() -> None:
    for relative_path in ("engine/advance_roll.py", "engine/charge_declaration.py"):
        tree = ast.parse((PACKAGE / relative_path).read_text(encoding="utf-8"))
        expressions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "DiceExpression"
        ]
        assert expressions
        for expression in expressions:
            for keyword in expression.keywords:
                if keyword.arg == "modifier":
                    assert isinstance(keyword.value, ast.Constant)
                    assert keyword.value.value == 0


def test_runtime_characteristic_owners_collect_operations_without_local_clamps() -> None:
    owners = (
        (
            "engine/generic_rule_attack_hooks.py",
            "generic_rule_modified_unit_characteristic",
            "resolve_runtime_characteristic",
        ),
        (
            "engine/runtime_characteristic_modifiers.py",
            "resolve_runtime_characteristic",
            "ModifierStack",
        ),
        (
            "engine/runtime_modifiers.py",
            "modified_unit_characteristic",
            "resolve_runtime_characteristic",
        ),
        ("engine/runtime_modifiers.py", "modified_objective_control", "resolve_objective_control"),
        (
            "engine/generic_rule_objective_control.py",
            "generic_rule_objective_control_trace",
            "resolve_runtime_objective_control",
        ),
        (
            "engine/movement_budget_modifiers.py",
            "_resolve_movement",
            "resolve_characteristic_value",
        ),
        (
            "engine/primary_mission_objective_control_authority.py",
            "resolve_checkpoint_objective_control",
            "resolve_objective_control",
        ),
    )
    for path, function, owner in owners:
        calls = _calls(path, function)
        assert owner in calls
        assert not calls.intersection({"max", "min", "ceil", "round"}), (path, function)


def test_typed_runtime_characteristic_producers_do_not_resolve_numeric_results() -> None:
    producers = 0
    for path in (PACKAGE / "engine").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef) or function.returns is None:
                continue
            if ast.unparse(function.returns) != "tuple[ModifierTerm, ...]":
                continue
            producers += 1
            for statement in ast.walk(function):
                if not isinstance(statement, ast.Return) or statement.value is None:
                    continue
                assert not isinstance(statement.value, ast.BinOp | ast.Constant), (
                    path,
                    function.name,
                )
                if isinstance(statement.value, ast.Call) and isinstance(
                    statement.value.func, ast.Name
                ):
                    assert statement.value.func.id not in {"max", "min", "ceil", "round"}, (
                        path,
                        function.name,
                    )
    assert producers >= 20


def test_checkpoint_authority_reconstructs_the_complete_resolved_characteristic() -> None:
    calls = _calls(
        "engine/primary_mission_boundary_checkpoint.py",
        "_validate_current_checkpoint_oc_resolutions",
    )
    assert {"resolve_checkpoint_objective_control", "canonical_json", "to_payload"} <= calls


def test_historical_leadership_uses_authenticated_generic_inventory_and_shared_resolution() -> None:
    assert {"historical_generic_leadership_operations", "ModifierStack"} <= _calls(
        "engine/battle_shock_event_authority.py", "_validate_historical_request_semantics"
    )
    calls = _calls(
        "engine/battle_shock_generic_leadership_authority.py",
        "historical_generic_leadership_operations",
    )
    assert {
        "rules_unit_effect_applications_from_inventory",
        "generic_matching_unit_effect_applications",
        "generic_characteristic_operations_from_effects",
    } <= calls
    source = (PACKAGE / "engine/battle_shock_generic_leadership_authority.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "persisting_effects"
        for node in ast.walk(tree)
    )
    assert {"expiration_for_duration", "validated_generic_execution_effect_payload"} <= _calls(
        "engine/battle_shock_generic_leadership_authority.py", "_effect_from_execution"
    )


def test_psychic_selection_and_hit_resolution_share_individual_source_owner() -> None:
    for path, function in (
        ("engine/attack_sequence_psychic_modifiers.py", "_psychic_attack_modifier_ignore_request"),
        ("engine/attack_sequence_hit_wound.py", "_roll_hit"),
    ):
        calls = _calls(path, function)
        assert "attack_modifier_snapshots" in calls
        assert not calls.intersection({"_hit_skill_modifier", "_hit_roll_modifier"})
    assert "ModifierStack" in _calls("core/weapon_skill_modifiers.py", "with_weapon_skill_modifier")
    assert "with_weapon_skill_modifier" in _calls(
        "engine/rule_ir_weapon_modifiers.py", "rule_ir_modified_weapon_profile"
    )
    for faction in ("adeptus_mechanicus", "astra_militarum", "tau_empire"):
        source = (
            PACKAGE / f"engine/faction_content/warhammer_40000_11th/{faction}/army_rule.py"
        ).read_text(encoding="utf-8")
        assert "with_weapon_skill_modifier" in source
        assert "def _improve_skill" not in source
    assert "invalid_psychic_modifier_status" in _calls(
        "engine/lifecycle_attack_prevalidation.py", "pre_validate_attack_sequence_decision"
    )
    assert "validate_psychic_modifier_history" in _calls(
        "engine/lifecycle.py", "from_payload", class_name="GameLifecycle"
    )
    assert "capture_psychic_history_origin" in _calls(
        "engine/lifecycle.py", "submit_decision", class_name="GameLifecycle"
    )
    assert "validate_psychic_history_origin" in _calls(
        "engine/lifecycle.py", "from_payload", class_name="GameLifecycle"
    )
    assert {"capture", "ReplayRunner", "run"} <= _calls(
        "engine/psychic_modifier_history_origin.py", "validate_psychic_history_origin"
    )


def test_stratagem_cost_providers_return_operations_without_intermediate_prices() -> None:
    assert "resolve_stratagem_cost" in _calls(
        "engine/stratagem_cost_modifiers.py", "modified_command_point_cost_with_sources"
    )
    owners = (
        ("engine/catalog_command_point_runtime.py", "_stratagem_cost_modifier_handler"),
        (
            "engine/generic_rule_lifecycle_hook_handlers.py",
            "stratagem_cost_modifier_handler_for_descriptor",
        ),
        (
            "engine/generic_rule_ability_registry_warptide_defaults.py",
            "_warptide_soul_hungry_cost_modifier",
        ),
        (
            "engine/faction_content/warhammer_40000_11th/aeldari/detachments/corsair_coterie/enhancements.py",
            "archraider_command_point_cost_modifier",
        ),
        (
            "engine/faction_content/warhammer_40000_11th/emperors_children/detachments/court_of_the_phoenician/rule.py",
            "master_of_the_pageant_command_point_cost_modifier",
        ),
        (
            "engine/faction_content/warhammer_40000_11th/thousand_sons/july_2026_updates.py",
            "_destroyer_of_futures_counteroffensive_cost",
        ),
    )
    for path, function in owners:
        tree = ast.parse((PACKAGE / path).read_text())
        scope = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function
        )
        assert not any(
            isinstance(n, ast.Attribute) and n.attr == "current_command_point_cost"
            for n in ast.walk(scope)
        )
        assert not {"max", "min"} & _calls(path, function)
    assert "_selected_command_point_cost_result" in _calls(
        "engine/stratagems_apply.py", "_apply_stratagem_use"
    )
    assert "_selected_command_point_cost_result" in _calls(
        "engine/stratagems_apply.py", "stratagem_cost_increase_made_use_unaffordable"
    )


def test_stratagem_cost_provider_work_is_bounded_for_real_catalog_consumers() -> None:
    import json
    from typing import cast

    from scripts.measure_stratagem_cost import CASES, sample

    budget = json.loads((ROOT / "docs/performance/order37/budgets.json").read_text())
    for case in CASES:
        row = sample(case, profile=True)
        counts = cast(dict[str, int], row["work_counts"])
        registry_calls = counts["modified_command_point_cost_with_sources"]
        assert 1 <= registry_calls <= budget["maximum_registry_calls_per_use"]
        assert counts["handler"] == (
            registry_calls * budget["provider_calls_per_registry_call"][case]
        )
        assert row["cost"] == (0 if case == "zero" else 2)
        assert row["commitments"] == (6 if case == "zero" else 5)
