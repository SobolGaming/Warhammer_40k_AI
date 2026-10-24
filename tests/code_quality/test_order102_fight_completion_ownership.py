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


def test_sf04_declaration_does_not_produce_shot_completion() -> None:
    tree = ast.parse((ENGINE / "phases/shooting_model.py").read_text(encoding="utf-8"))
    declaration = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "with_declaration"
    )
    assignments = [
        node.value
        for node in ast.walk(declaration)
        if isinstance(node, ast.keyword) and node.arg == "shot_unit_ids"
    ]
    assert len(assignments) == 1
    assert ast.unparse(assignments[0]) == "self.shot_unit_ids"
    dispatch = (ENGINE / "attack_sequence_dispatch.py").read_text(encoding="utf-8")
    assert dispatch.index("_apply_deferred_mortal_wounds(\n") < dispatch.rindex(
        "record_models_attacked(state=state, decisions=decisions, sequence=current)"
    )
    assert (
        "record_models_attacked(state=state, decisions=decisions, sequence=current)"
        in dispatch[
            dispatch.index("while not current.is_complete:") : dispatch.index(
                "before_gathering(current)"
            )
        ]
    )


def test_sf04_restore_binds_incremental_models_and_unit_completion() -> None:
    history = (ENGINE / "model_attack_history.py").read_text(encoding="utf-8")
    assert "model_completion_evidence(" in history
    assert "validate_shot_unit_inventory(state=state, events=event_records)" in history
    completion = (ENGINE / "model_attack_completion.py").read_text(encoding="utf-8")
    for required in (
        "current_gathered_group",
        "pending_grouped_damage",
        "pending_destroyed_transport_disembark",
        "deferred_mortal_wounds",
        "validate_recorded_sequence_authority(",
    ):
        assert required in completion


def test_sf04_state_receipt_keeps_existing_internal_evidence_policies() -> None:
    event = "attack_sequence_model_completion_state_recorded"
    decision = ast.parse((ENGINE / "decision.py").read_text(encoding="utf-8"))
    policy = next(
        node
        for node in decision.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_RNG_HISTORY_NEUTRAL_EVENT_TYPES"
            for target in node.targets
        )
    )
    assert event in {node.value for node in ast.walk(policy) if isinstance(node, ast.Constant)}
    redaction = ast.parse(
        (ROOT / "src/warhammer40k_core/adapters/redaction.py").read_text(encoding="utf-8")
    )
    owner = next(
        node
        for node in redaction.body
        if isinstance(node, ast.FunctionDef) and node.name == "_event_record_hidden_from_context"
    )
    assert event in {node.value for node in ast.walk(owner) if isinstance(node, ast.Constant)}


def test_sf04_physical_completion_has_shared_execution_and_history_owners() -> None:
    producers: set[str] = set()
    for path in ENGINE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_models_attacked"
            for node in ast.walk(tree)
        ):
            producers.add(path.name)
    assert producers == {
        "attack_sequence_dispatch.py",
        "attack_sequence_grouped_allocation.py",
        "gathered_attack_dice.py",
    }
    authority = (ENGINE / "model_attack_completion.py").read_text(encoding="utf-8")
    assert "def resolved_model_ids(" in authority
    assert "event_records=event_records[: index - 1]" in authority
    phase = ast.parse((ENGINE / "phases/shooting_model.py").read_text(encoding="utf-8"))
    update = next(
        node
        for node in ast.walk(phase)
        if isinstance(node, ast.FunctionDef) and node.name == "with_attack_sequence_update"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "all_attacks_resolved"
        for node in ast.walk(update)
    )
