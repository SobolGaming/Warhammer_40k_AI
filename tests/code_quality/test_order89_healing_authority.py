"""Keep Core healing scope and all producers on one engine decision path."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_modifiers_2026_09

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_order89_source_is_registered_and_reproducible() -> None:
    source = core_modifiers_2026_09
    rule = next(r for r in source.source_rules() if r.source_id == source.HEALING_SOURCE_ID)
    assert rule.section_id == "02.02.04"
    assert "excluding Character models" in rule.source_text
    assert "Any excess regained wounds are lost" in rule.source_text
    assert source.source_package().source_authority_scope == "warhammer_40000_11th_core_rules"
    subprocess.run(
        [sys.executable, "tools/build_core_modifiers_source.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )


def test_healing_does_not_gate_multiple_wounds_by_attachment_or_renormalize_keywords() -> None:
    for name in ("healing.py", "healing_source_context.py", "catalog_model_healing.py"):
        text = (ENGINE / name).read_text()
        assert "allows_multiple_wounded_models" not in text
        assert "_rules_unit_allows_multiple_wounded_healing" not in text
        tree = ast.parse(text)
        assert not [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"upper", "lower", "casefold"}
        ]
    for path in ENGINE.rglob("*.py"):
        assert "multiple_wounded_models_require_decision" not in path.read_text()
        assert "healing cannot target multiple wounded models" not in path.read_text()


def test_model_healing_producers_bind_scope_and_use_shared_mutation() -> None:
    expected = {
        "catalog_model_healing.py": "healing_model_instance_id",
        "catalog_battle_shock_runtime.py": "healing_model_instance_id",
        "catalog_command_restoration_runtime.py": "single_model_heal",
        "stratagems_generic_rule_ir_runtime.py": "single_model_heal",
        (
            "faction_content/warhammer_40000_11th/chaos_daemons/manifestation_healing.py"
        ): "single_model_heal",
    }
    for filename, field in expected.items():
        text = (ENGINE / filename).read_text()
        assert field in text
        assert "resolve_healing_until_blocked(" in text
    text = (ENGINE / "revival_engagement_history.py").read_text()
    assert "healing_model_request(" in text
    assert (
        "healing_selection_actor_player_id(effect, state=state)"
        in (ENGINE / "healing.py").read_text()
    )
