from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOVEMENT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement.py"
MOVEMENT_PHASE_FILES = (
    MOVEMENT_PHASE,
    *sorted(MOVEMENT_PHASE.parent.glob("movement_*.py")),
)
CHARGE_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "charge.py"
FIGHT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "fight.py"
FIGHT_RESOLUTION = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_resolution.py"
LIFECYCLE = ROOT / "src" / "warhammer40k_core" / "engine" / "lifecycle.py"
STRATAGEMS = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems.py"
STRATAGEM_FILES = (STRATAGEMS, *sorted(STRATAGEMS.parent.glob("stratagems_*.py")))
TRIGGERED_MOVEMENT = ROOT / "src" / "warhammer40k_core" / "engine" / "triggered_movement.py"
BATTLE_SHOCK_HOOKS = ROOT / "src" / "warhammer40k_core" / "engine" / "battle_shock_hooks.py"
BATTLE_SHOCK_RESOLUTION = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "battle_shock_resolution.py"
)

LIVE_MOVEMENT_CALLS = (
    (MOVEMENT_PHASE, "_apply_movement_proposal_decision", "resolve_normal_move"),
    (MOVEMENT_PHASE, "_apply_movement_proposal_decision", "resolve_advance_move"),
    (MOVEMENT_PHASE, "_apply_movement_proposal_decision", "resolve_fall_back_move"),
    (CHARGE_PHASE, "_apply_charge_move_proposal_decision", "resolve_charge_move"),
    (FIGHT_PHASE, "_apply_fight_movement_proposal", "resolve_fight_movement"),
    (STRATAGEMS, "apply_heroic_intervention_charge_move", "resolve_charge_move"),
    (TRIGGERED_MOVEMENT, "request_from_state", "resolve_triggered_movement"),
    (TRIGGERED_MOVEMENT, "apply_decision", "resolve_triggered_movement"),
    (TRIGGERED_MOVEMENT, "apply_proposal_decision", "resolve_triggered_movement"),
)
GEOMETRY_KEYWORDS = frozenset(
    ("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")
)
RESOLVER_GEOMETRY_READS = (
    (MOVEMENT_PHASE, "resolve_normal_move"),
    (MOVEMENT_PHASE, "resolve_advance_move"),
    (MOVEMENT_PHASE, "resolve_fall_back_move"),
    (CHARGE_PHASE, "resolve_charge_move"),
    (FIGHT_RESOLUTION, "_validate_fight_paths"),
    (TRIGGERED_MOVEMENT, "resolve_triggered_movement"),
)
SPECIALIZED_PHYSICAL_PROPOSAL_VALIDATORS = (
    "invalid_stratagem_placement_proposal_status",
    "invalid_cult_ambush_placement_status",
    "invalid_destroyed_transport_disembark_proposal_status",
    "invalid_setup_reactive_lifecycle_status",
)


def test_live_movement_callers_do_not_pass_copied_battlefield_geometry() -> None:
    violations: list[str] = []
    for path, function_name, call_name in LIVE_MOVEMENT_CALLS:
        for source_path, tree in _parsed_sources(path):
            if _module_imports_name(tree, "live_battlefield_geometry_for_state"):
                violations.append(f"{source_path.relative_to(ROOT)} imports live geometry helper")
        source_path, function = _function_by_name(path, function_name)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) != call_name:
                continue
            copied_keywords = {
                keyword.arg
                for keyword in node.keywords
                if keyword.arg is not None and keyword.arg in GEOMETRY_KEYWORDS
            }
            if copied_keywords:
                violations.append(
                    f"{source_path.relative_to(ROOT)}:{node.lineno} {call_name} passes "
                    + ", ".join(sorted(copied_keywords))
                )

    assert not violations, (
        "Live movement-family callers must use the manifested BattlefieldRuntimeState "
        "through the resolver scenario instead of copying geometry into each phase:\n"
        + "\n".join(violations)
    )


def test_movement_resolvers_read_manifested_battlefield_geometry() -> None:
    violations: list[str] = []
    for path, function_name in RESOLVER_GEOMETRY_READS:
        source_path, function = _function_by_name(path, function_name)
        source = ast.unparse(function)
        missing: list[str] = []
        if "scenario.battlefield_state.battlefield_width_inches" not in source:
            missing.append("battlefield_width_inches")
        if "scenario.battlefield_state.battlefield_depth_inches" not in source:
            missing.append("battlefield_depth_inches")
        if "scenario.battlefield_state.terrain_features" not in source:
            missing.append("terrain_features")
        if missing:
            violations.append(
                f"{source_path.relative_to(ROOT)}:{function.lineno} {function_name} missing "
                + ", ".join(missing)
            )

    assert not violations, (
        "Movement-family resolvers must read geometry from scenario.battlefield_state:\n"
        + "\n".join(violations)
    )


def test_spatial_context_validation_precedes_specialized_physical_proposal_routing() -> None:
    _source_path, function = _function_by_name(
        LIFECYCLE,
        "_pre_validate_movement_phase_decision",
    )
    call_lines = {
        _call_name(node): node.lineno for node in ast.walk(function) if isinstance(node, ast.Call)
    }
    spatial_validation_line = call_lines["invalid_physical_proposal_spatial_context_status"]

    for validator_name in SPECIALIZED_PHYSICAL_PROPOSAL_VALIDATORS:
        assert spatial_validation_line < call_lines[validator_name], (
            "Physical proposal spatial-context validation must run before specialized "
            f"routing through {validator_name}."
        )


def test_desperate_escape_mode_requires_exact_selected_model_inventory() -> None:
    _source_path, requirement_function = _function_by_name(
        MOVEMENT_PHASE,
        "_desperate_escape_requirements_for_fall_back",
    )
    requirement_source = ast.unparse(requirement_function)
    assert "fall_back_mode" in {argument.arg for argument in requirement_function.args.kwonlyargs}
    assert "fall_back_mode is FallBackModeKind.DESPERATE_ESCAPE" in requirement_source
    assert "DesperateEscapeRequirementReason.SELECTED_MODE" in requirement_source

    _source_path, validation_function = _function_by_name(
        MOVEMENT_PHASE,
        "_fall_back_mode_violation_code",
    )
    validation_source = ast.unparse(validation_function)
    assert "DesperateEscapeRequirementReason.SELECTED_MODE" in validation_source
    assert "resolution.witness.model_ids()" in validation_source
    assert "desperate_escape_requirement_inventory_incomplete" in validation_source
    assert "desperate_escape_has_no_requirements" not in validation_source


def test_desperate_escape_battle_shock_preserves_nested_outcome_status() -> None:
    _source_path, registry_function = _function_by_name(
        BATTLE_SHOCK_HOOKS,
        "resolve_outcomes",
    )
    registry_source = ast.unparse(registry_function)
    assert "pending_status = status" in registry_source
    assert "queue_after[0] != pending_status.decision_request" in registry_source
    assert "return pending_status" in registry_source

    _source_path, resolution_function = _function_by_name(
        BATTLE_SHOCK_RESOLUTION,
        "record_precomputed_battle_shock_result_and_outcome_events",
    )
    resolution_source = ast.unparse(resolution_function)
    assert "pending_status = battle_shock_hooks.resolve_outcomes" in resolution_source
    assert "BattleShockResolutionResult" in resolution_source
    assert "pending_status=pending_status" in resolution_source

    _source_path, movement_function = _function_by_name(
        MOVEMENT_PHASE,
        "_resolve_desperate_escape_battle_shock_after_move",
    )
    movement_source = ast.unparse(movement_function)
    assert "record_desperate_escape_battle_shock_resolution" in movement_source
    assert "execution.resolution.pending_status" not in movement_source


def test_fight_witness_shapes_share_one_validation_owner() -> None:
    engine = FIGHT_RESOLUTION.parent
    owners = (
        (FIGHT_RESOLUTION, "fight_movement_resolution_violation"),
        (engine / "fight_rules_unit_movement.py", "fight_rules_unit_movement_resolution_violation"),
    )
    for path, function_name in owners:
        _source, function = _function_by_name(path, function_name)
        calls = {_call_name(node) for node in ast.walk(function) if isinstance(node, ast.Call)}
        assert "fight_movement_path_violation" in calls
    for name in ("fight_resolution.py", "fight_rules_unit_movement_types.py"):
        tree = ast.parse((engine / name).read_text(encoding="utf-8"))
        assert _module_imports_name(tree, "closed_loop_fight_model_id")


def test_forced_fight_live_and_historical_actors_share_canonical_ownership() -> None:
    engine = FIGHT_RESOLUTION.parent
    for name in (
        "consolidation_fight_queue.py",
        "consolidation_fight_history.py",
        "fight_historical_eligibility.py",
    ):
        tree = ast.parse((engine / name).read_text(encoding="utf-8"))
        assert _module_imports_name(tree, "forced_fight_selecting_player_id")


def test_historical_fight_builders_use_frozen_time_and_effect_context() -> None:
    engine = FIGHT_RESOLUTION.parent
    for name, functions in (
        (
            "fight_activation_requests.py",
            (
                "build_fight_activation_request",
                "fight_activation_selection_requested_payload",
                "request_fight_activation",
            ),
        ),
        ("fight_order.py", ("fight_activation_option_payload", "eligible_pass_option_payload")),
    ):
        for function_name in functions:
            _path, function = _function_by_name(engine / name, function_name)
            current_round_reads = tuple(
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Attribute)
                and node.attr == "battle_round"
                and isinstance(node.value, ast.Name)
                and node.value.id == "state"
            )
            assert not current_round_reads, function_name
    for name in ("fight_historical_eligibility.py", "lifecycle_state_validation.py"):
        tree = ast.parse((engine / name).read_text(encoding="utf-8"))
        assert "FightsFirstRegistry.from_state" not in ast.unparse(tree)


def _function_by_name(path: Path, name: str) -> tuple[Path, ast.FunctionDef]:
    for source_path, tree in _parsed_sources(path):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return source_path, node
    raise AssertionError(f"Missing function: {name}")


def _parsed_sources(path: Path) -> tuple[tuple[Path, ast.AST], ...]:
    return tuple(
        (source_path, ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path)))
        for source_path in _source_paths(path)
    )


def _source_paths(path: Path) -> tuple[Path, ...]:
    if path == MOVEMENT_PHASE:
        return MOVEMENT_PHASE_FILES
    if path == STRATAGEMS:
        return STRATAGEM_FILES
    return (path,)


def _module_imports_name(tree: ast.AST, imported_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == imported_name or alias.asname == imported_name:
                    return True
    return False


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""
