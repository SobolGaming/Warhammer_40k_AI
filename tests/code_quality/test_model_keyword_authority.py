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
