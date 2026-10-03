"""Keep unit and attached Hazard consumers on one model-aware count authority."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "owner",
    [
        "attack_sequence_hazardous.py",
        "emergency_disembark.py",
        "transports.py",
        "phases/movement_rules_unit_disembark.py",
    ],
)
def test_hazard_consumers_share_model_count_authority(owner: str) -> None:
    tree = ast.parse((ROOT / "src/warhammer40k_core/engine" / owner).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert any(
        isinstance(node.func, ast.Name) and node.func.id == "hazard_mortal_wounds_per_failed_roll"
        for node in calls
    )
