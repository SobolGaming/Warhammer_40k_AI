"""Keyword ownership cannot return to unit-wide stored authority or profile inference."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_runtime_model_assignments_are_required_and_units_have_no_stored_keyword_fields() -> None:
    tree = ast.parse((ENGINE / "unit_factory.py").read_text())
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    unit_fields = {
        node.target.id
        for node in classes["UnitInstance"].body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert not {"keywords", "faction_keywords"}.intersection(unit_fields)
    assignment = next(
        node
        for node in classes["ModelInstance"].body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "keyword_assignment"
    )
    assert assignment.value is None, "Runtime ownership must not infer missing assignments."


def test_model_keyword_consumers_do_not_infer_ownership_from_component_keywords() -> None:
    paths = (
        "catalog_model_scope.py",
        "dice_result_overrides.py",
        "terrain_hidden.py",
        "shooting_terrain_visibility.py",
        "mortal_wound_target_lineage.py",
    )
    violations: list[str] = []
    for name in paths:
        for node in ast.walk(ast.parse((ENGINE / name).read_text())):
            if isinstance(node, ast.Attribute) and node.attr in {"keywords", "faction_keywords"}:
                receiver = ast.unparse(node.value)
                if (
                    receiver in {"attacker_component", "component.unit"}
                    or "component_unit_for_model" in receiver
                ):
                    violations.append(f"{name}:{node.lineno}")
    assert not violations, "Model scope inherited whole-component keywords: " + repr(violations)


def test_current_keyword_gates_use_state_backed_rules_unit_authority() -> None:
    required_calls = {
        "rule_target_resolution.py": {
            "target_spec_keyword_unavailable_reason": "rules_unit_view_by_id",
        },
        "stratagems_targeting.py": {
            "_target_unit_keyword_set": "rules_unit_view_by_id",
            "_target_unit_has_keyword": "_target_unit_keyword_set",
            "_target_unit_satisfies_required_keywords": "_target_unit_keyword_set",
            "_target_unit_satisfies_required_keywords_any": "_target_unit_keyword_set",
            "_target_unit_satisfies_required_faction_keywords": "_target_unit_keyword_set",
            "_target_unit_has_excluded_keywords": "_target_unit_keyword_set",
            "_target_unit_has_excluded_faction_keywords": "_target_unit_keyword_set",
            "_fire_overwatch_target_binding_error": "_target_unit_has_keyword",
        },
        "stratagems_geometry.py": {
            "_heroic_intervention_target_binding_error": "_target_unit_has_keyword",
            "_epic_challenge_context_error": "_target_unit_has_keyword",
        },
        "stratagems_generic_metadata.py": {
            "companion_effect_selections_for_binding": "rules_unit_view_by_id",
            "companion_selection_error": "rules_unit_view_by_id",
            "companion_keywords_match": "unit_keyword_set",
            "unit_has_keyword": "unit_keyword_set",
        },
    }
    for module, gates in required_calls.items():
        functions = {
            node.name: node
            for node in ast.parse((ENGINE / module).read_text()).body
            if isinstance(node, ast.FunctionDef)
        }
        for function, required in gates.items():
            calls = {
                node.func.id
                for node in ast.walk(functions[function])
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            assert required in calls, f"{module}:{function} bypasses current keyword authority"
            assert "_unit_has_keyword" not in calls, f"{module}:{function} uses component keywords"
    metadata = ast.parse((ENGINE / "stratagems_generic_metadata.py").read_text())
    keyword_set = next(
        node
        for node in metadata.body
        if isinstance(node, ast.FunctionDef) and node.name == "unit_keyword_set"
    )
    annotation = keyword_set.args.args[0].annotation
    assert annotation is not None
    assert ast.unparse(annotation) == "RulesUnitView", "Keyword helper must reject physical units"
