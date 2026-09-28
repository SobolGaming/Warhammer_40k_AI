"""Physical selections must survive every immutable attack-executor continuation."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"


def test_external_attack_sequence_copies_preserve_targetless_inventory() -> None:
    for path in ROOT.rglob("*.py"):
        if path.name == "attack_sequence_state.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "AttackSequence"
                and any(
                    kw.arg == "sequence_id" and isinstance(kw.value, ast.Attribute)
                    for kw in node.keywords
                )
            ):
                assert "weapons_without_attacks" in {kw.arg for kw in node.keywords}, path


def test_hazardous_uses_complete_selection_and_shared_validation() -> None:
    for name in ("hazardous_completion.py", "attack_sequence_hazardous.py"):
        assert ".selected_weapons" in (ROOT / name).read_text()
    source = (ROOT / "phases/shooting_declaration_validation.py").read_text()
    assert "validate_targetless_weapon(" in source
    assert "target_unit_instance_id is None" in source
    assert "validate_targetless_weapon_history(" in (ROOT / "model_attack_history.py").read_text()
