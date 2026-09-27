"""Keep non-spatial returns source-bound and shared across physical histories."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_offboard_and_battlefield_returns_share_source_wounds_without_spatial_fallback() -> None:
    for filename in ("healing_off_battlefield.py", "healing_revival.py"):
        tree = ast.parse((ENGINE / filename).read_text())
        assert any(
            isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Name) and n.func.id == "revival_wounds_remaining")
                or (isinstance(n.func, ast.Attribute) and n.func.attr == "revival_wounds_remaining")
            )
            for n in ast.walk(tree)
        )
    text = (ENGINE / "healing_off_battlefield.py").read_text()
    assert "with_returned_unplaced_model" in text
    assert "request_healing_revival_placement" not in text
    assert "destroy_model_with_rule_reactions" not in text
    assert "revival_location" in (ENGINE / "healing.py").read_text()
    assert "revival_location" in (ENGINE / "revival_phase_start.py").read_text()
    assert "_apply_embarked_revival_step_if_applicable" not in (ENGINE / "healing.py").read_text()


def test_all_restoration_histories_recognize_reserve_returns_and_share_redaction() -> None:
    for filename in (
        "unit_destroyed_hooks.py",
        "fight_model_authority_history.py",
        "primary_mission_boundary_physical_authority.py",
        "faction_content/warhammer_40000_11th/chaos_daemons/battle_shock_outcome_authority.py",
    ):
        assert "REVIVE_MODEL_IN_RESERVES" in (ENGINE / filename).read_text()
    assert "validate_off_battlefield_step" in (ENGINE / "unit_destroyed_hooks.py").read_text()
    assert (
        '"revival_location"' in (ROOT / "src/warhammer40k_core/adapters/redaction.py").read_text()
    )


def test_disembark_choices_and_resolver_share_rules_unit_phase_history() -> None:
    for filename in ("phases/movement_transports.py", "transport_disembark_validation.py"):
        text = (ENGINE / filename).read_text()
        assert "rules_unit_retains_phase_start_cargo(" in text
        assert ".unit_started_phase_embarked(" not in text
