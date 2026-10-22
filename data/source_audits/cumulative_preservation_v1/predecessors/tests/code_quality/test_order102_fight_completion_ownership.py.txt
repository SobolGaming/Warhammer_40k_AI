"""Keep completion consumers on their actual selection or fought authority."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_actual_fought_has_one_shared_conditional_producer() -> None:
    producers: list[str] = []
    for path in ENGINE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "unit_has_fought"
            ):
                producers.append(path.relative_to(ENGINE).as_posix())
    assert producers == ["fight_activation_completion.py"]
    source = (ENGINE / producers[0]).read_text(encoding="utf-8")
    tree = ast.parse(source)
    actual_guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "has_fought"
    ]
    assert len(actual_guards) == 1
    calls = [
        node
        for node in ast.walk(actual_guards[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "actual_fought_payload"
    ]
    assert len(calls) == 1


def test_selection_history_and_actual_fought_effects_keep_distinct_owners() -> None:
    for name in (
        "active_player_boundary_history.py",
        "fight_continuation_checkpoint.py",
        "consolidation_continuation_history.py",
    ):
        source = (ENGINE / name).read_text(encoding="utf-8")
        assert '"fight_selection_completed"' in source
        assert '"unit_has_fought"' not in source
    retained = (ENGINE / "retained_destruction_history.py").read_text(encoding="utf-8")
    assert 'previous.event_type == "unit_has_fought"' in retained
    assert '"fight_selection_completed"' not in retained
    lifecycle = (ENGINE / "lifecycle_state_validation.py").read_text(encoding="utf-8")
    assert "validate_fight_selection_completion_history(" in lifecycle
