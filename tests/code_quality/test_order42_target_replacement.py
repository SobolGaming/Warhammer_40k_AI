"""Order 42 shared authority, source reproducibility and retained timing gates."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pending_destruction_phase_uses_each_authenticated_attack_owner() -> None:
    source = (
        ROOT / "src/warhammer40k_core/engine/model_destruction_cause_completion_restore.py"
    ).read_text()
    function = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "validate_pending_model_destruction_cause_inventory"
    )
    body = ast.unparse(function)
    assert "source_phase != source_sequence.source_phase.value" in body
    assert "active_attack_sequence_for_state(state)" in body
    assert "retained_attack_sequence_for_cause(" in body
    non_attack = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and ast.unparse(node.test)
        == "authority.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE"
    )
    assert "state.current_battle_phase.value != source_phase" in ast.unparse(non_attack)
    assert "state.current_battle_phase is None" in body


def test_nested_death_checkpoint_cost_is_comparable_and_bounded() -> None:
    directory = ROOT / "docs/performance/order42"
    budget = json.loads((directory / "phase_binding_budgets.json").read_text())
    for case, prefix in (
        ("nested_death", "phase_binding"),
        ("accepted_defense", "phase_binding_control"),
    ):
        base = json.loads((directory / f"{prefix}_base.json").read_text())
        head = json.loads((directory / f"{prefix}_head.json").read_text())
        assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
        assert base["case"] == head["case"] == case
        for field in (
            "platform",
            "python",
            "cpu",
            "cpu_allocation",
            "memory_bytes",
            "concurrency",
            "model_count",
            "terrain_count",
            "timing_boundary",
            "seed",
            "decision_policy",
        ):
            assert base[field] == head[field]
        for path, digest in base["file_hashes"].items():
            if path != "src/warhammer40k_core/_engine_build_manifest.json":
                assert head["file_hashes"][path] == digest
        assert base["summary"]["measurement_completion_rate"] == 1
        assert head["summary"]["measurement_completion_rate"] == 1
        assert head["summary"]["completion_rate"] == 1
        assert base["summary"]["completion_rate"] == (0 if case == "nested_death" else 1)
        assert (
            base["summary"]["samples"] == head["summary"]["samples"] == budget["samples_per_case"]
        )
        assert {row["outcome"] for row in base["rows"]} == {
            "rejected" if case == "nested_death" else "restored"
        }
        assert {row["outcome"] for row in head["rows"]} == {"restored"}
        if case == budget["relative_budget_case"]:
            assert (
                head["summary"]["mean"]
                <= base["summary"]["mean"] * budget["mean_base_multiplier"]
                + budget["mean_additive_seconds"]
            )
        assert case in budget["absolute_budget_cases"]
        assert head["summary"]["maximum"] <= budget["maximum_seconds"]
    # Preserve the initial failed comparison: base aborts before completing restore.
    initial_base = json.loads((directory / "phase_binding_initial_base.json").read_text())
    initial_head = json.loads((directory / "phase_binding_initial_head.json").read_text())
    assert len(initial_base["rows"]) == len(initial_head["rows"]) == budget["samples_per_case"]
    assert (
        initial_head["summary"]["mean"]
        > initial_base["summary"]["mean"] * budget["mean_base_multiplier"]
        + budget["mean_additive_seconds"]
    )


def test_generic_persisted_identity_producers_and_restore_share_activation_and_slot() -> None:
    """R42-003: emitting and reconstructing a persisted ID share one typed owner."""
    engine = ROOT / "src/warhammer40k_core/engine"
    callers: set[str] = set()
    for path in engine.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "generic_rule_persisting_effect_id"
            ):
                callers.add(path.name)
                assert {keyword.arg for keyword in node.keywords} == {
                    "rule_ir",
                    "clause",
                    "effect_index",
                    "context",
                    "target_unit_instance_ids",
                }
    assert callers == {
        "rule_execution.py",
        "primary_mission_objective_control_source_authority.py",
        "generic_effect_history.py",
    }
    execution = (engine / "rule_execution.py").read_text()
    aura = (engine / "aura_execution.py").read_text()
    assert "for effect_index, effect in enumerate(clause.effects)" in execution
    assert "binding.handler(rule_ir, clause, effect, context, effect_index)" in execution
    assert "for index, effect_spec in enumerate(clause.effects)" in aura
    assert "effect_index=index" in aura


def test_recorded_effect_identity_cost_is_comparable_and_bounded() -> None:
    directory = ROOT / "docs/performance/order42"
    base = json.loads((directory / "effect_identity_base.json").read_text())
    head = json.loads((directory / "effect_identity_head.json").read_text())
    budget = json.loads((directory / "effect_identity_budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for field in (
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
        "seed",
    ):
        assert base[field] == head[field]
    for path, digest in base["file_hashes"].items():
        if path != "src/warhammer40k_core/_engine_build_manifest.json":
            assert head["file_hashes"][path] == digest
    assert base["base_api"] is True
    assert head["base_api"] is False
    assert base["summary"]["completion_rate"] == head["summary"]["completion_rate"] == 1
    assert base["summary"]["samples"] == head["summary"]["samples"] == budget["samples_per_case"]
    assert (
        head["summary"]["mean"]
        <= base["summary"]["mean"] * budget["mean_base_multiplier"]
        + budget["mean_additive_seconds"]
    )
    assert head["summary"]["maximum"] <= budget["maximum_seconds"]
    assert len({row["identity"] for row in head["rows"]}) == 1


def test_out_of_phase_replacement_reaction_cost_is_comparable_and_bounded() -> None:
    directory = ROOT / "docs/performance/order42"
    base = json.loads((directory / "out_of_phase_base.json").read_text())
    head = json.loads((directory / "out_of_phase_head.json").read_text())
    budget = json.loads((directory / "out_of_phase_budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for field in (
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
        "seed",
        "decision_policy",
    ):
        assert base[field] == head[field]
    for path, digest in base["file_hashes"].items():
        if path != "src/warhammer40k_core/_engine_build_manifest.json":
            assert head["file_hashes"][path] == digest
    measured = head["summary"]
    assert measured["completion_rate"] == base["summary"]["completion_rate"] == 1
    assert measured["samples"] == base["summary"]["samples"] == budget["samples_per_case"]
    assert (
        measured["mean"]
        <= base["summary"]["mean"] * budget["mean_base_multiplier"]
        + budget["mean_additive_seconds"]
    )
    assert measured["maximum"] <= budget["maximum_seconds"]
    assert {row["decision_type"] for row in base["rows"]} == {"select_resolve_target_unit"}
    assert {row["decision_type"] for row in head["rows"]} == {"use_stratagem"}
    for row in head["rows"]:
        assert set(row["option_ids"]) == {
            "decline_stratagem_window",
            "use-stratagem:grey-knights-hallowed-conclave-unending-fidelity:target:army-alpha:new",
        }


def test_target_replacement_component_cost_is_comparable_complete_and_bounded() -> None:
    directory = ROOT / "docs/performance/order42"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for field in (
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
    ):
        assert base[field] == head[field]
    for path, digest in base["file_hashes"].items():
        if path != "src/warhammer40k_core/_engine_build_manifest.json":
            assert head["file_hashes"][path] == digest
    assert (
        set(base["summaries"])
        == set(head["summaries"])
        == {"eligible", "moved_target", "no_alternative"}
    )
    for case, measured in head["summaries"].items():
        assert measured["completion_rate"] == 1
        assert measured["samples"] == budget["samples_per_case"]
        assert (
            measured["mean"]
            <= base["summaries"][case]["mean"] * budget["mean_base_multiplier"]
            + budget["mean_additive_seconds"]
        )
        assert measured["max"] <= budget["maximum_seconds"]
    assert {
        (row["decision_type"], row["option_count"])
        for row in head["rows"]
        if row["case"] == "moved_target"
    } == {("select_target_replacement", 2)}
    assert {
        (row["decision_type"], row["option_count"])
        for row in head["rows"]
        if row["case"] == "no_alternative"
    } == {("select_target_replacement", 1)}
    assert {row["decision_type"] for row in head["rows"] if row["case"] == "eligible"} == {
        row["decision_type"] for row in base["rows"] if row["case"] == "eligible"
    }


def test_target_replacement_service_has_no_action_or_hit_resolution_dependencies() -> None:
    source = (ROOT / "src/warhammer40k_core/engine/target_replacement.py").read_text()
    tree = ast.parse(source)
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(
        module
        and any(token in module for token in ("shooting", "charge", "attack_sequence", "geometry"))
        for module in modules
    )
    for filename in ("shooting_target_replacement.py", "target_replacement_dispatch.py"):
        text = (ROOT / "src/warhammer40k_core/engine" / filename).read_text()
        assert "replacement_" in text
        assert "roll_random_characteristic(" not in text
        assert "_roll_hit(" not in text
    redaction = (ROOT / "src/warhammer40k_core/adapters/redaction.py").read_text()
    assert "target_replacement_authority_sha256" in redaction


def test_target_replacement_source_generator_is_reproducible() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_core_target_replacement_source.py"), "--check"],
        check=True,
        cwd=ROOT,
    )


def test_replacement_reactions_and_completion_keep_shared_authority() -> None:
    """R42-001/002: replacement cannot substitute local usage/history policies."""
    engine = ROOT / "src/warhammer40k_core/engine"
    reactions = ast.parse((engine / "selected_target_stratagem_reactions.py").read_text())
    request = next(
        node
        for node in reactions.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "request_after_unit_selected_as_target_stratagem_if_available"
    )
    calls = {
        node.func.id
        for node in ast.walk(request)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "_latest_target_selection",
        "stratagem_window_declined_for_context",
        "stratagem_used_for_context",
        "stratagem_use_options_from_index",
    }.issubset(calls)
    shooting = ast.parse((engine / "phases/shooting_handler.py").read_text())
    advance = next(
        node
        for node in ast.walk(shooting)
        if isinstance(node, ast.FunctionDef)
        and node.name == "advance_out_of_phase_shooting_if_needed"
    )
    advance_calls = {
        node.func.id: node
        for node in ast.walk(advance)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    reaction = advance_calls["request_after_unit_selected_as_target_stratagem_if_available"]
    assert reaction.lineno < advance_calls["resolve_attack_sequence_until_blocked"].lineno
    parent_phase = next(keyword.value for keyword in reaction.keywords if keyword.arg == "phase")
    assert ast.unparse(parent_phase) == "out_of_phase_state.parent_phase"
    completion = ast.parse((engine / "retained_shooting_history.py").read_text())
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "warhammer40k_core.engine.shooting_target_replacement_authority"
        and any(alias.name == "validate_completed_replacement_authority" for alias in node.names)
        for node in ast.walk(completion)
    )
