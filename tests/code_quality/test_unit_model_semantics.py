from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "warhammer40k_core" / "core"
ENGINE = ROOT / "src" / "warhammer40k_core" / "engine"
MOVEMENT_LEGALITY = ROOT / "src" / "warhammer40k_core" / "engine" / "movement_legality.py"
MOVEMENT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement.py"
MOVEMENT_PHASE_FILES = (
    MOVEMENT_PHASE,
    *sorted(MOVEMENT_PHASE.parent.glob("movement_*.py")),
)
PATHING = ROOT / "src" / "warhammer40k_core" / "geometry" / "pathing.py"
DEADLY_DEMISE = ROOT / "src" / "warhammer40k_core" / "engine" / "deadly_demise.py"
RULE_MODEL_DESTRUCTION = ROOT / "src" / "warhammer40k_core" / "engine" / "rule_model_destruction.py"
ATTACHED_UNIT_RECONCILIATION = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "attached_unit_reconciliation.py"
)
CATALOG_SELECTED_TARGET_MORTAL_WOUNDS = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_selected_target_mortal_wounds.py"
)
CATALOG_SELECTED_TARGET_EVENT = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_selected_target_event.py"
)
CATALOG_SELECTED_TARGET_EFFECTS_SUPPORT = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_selected_target_effects_support.py"
)
CULT_AMBUSH_MARKER_REMOVAL = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "cult_ambush_marker_removal.py"
)
PRIMARY_MISSION_STATE_RUNTIME = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "primary_mission_state_runtime.py"
)
FIGHT_RULES_UNIT_MOVEMENT_TYPES = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_rules_unit_movement_types.py"
)
FIGHT_GEOMETRY = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_geometry.py"
FIGHT_RESOLUTION = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_resolution.py"
SHOOTING_TARGETS = ROOT / "src" / "warhammer40k_core" / "engine" / "shooting_targets.py"
STRATAGEMS_GEOMETRY = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems_geometry.py"
UNIT_MODULES = (
    CORE / "unit.py",
    CORE / "attached_unit.py",
    CORE / "unit_group.py",
)


def test_core_unit_modules_do_not_use_ambiguous_models_attribute() -> None:
    violations: list[str] = []

    for path in UNIT_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "models":
                violations.append(f"{path.relative_to(ROOT)} uses .models")
            if isinstance(node, ast.FunctionDef) and node.name == "models":
                violations.append(f"{path.relative_to(ROOT)} defines models()")
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "models"
            ):
                violations.append(f"{path.relative_to(ROOT)} defines models")

    assert not violations, "Use unit.own_models and unit_group.all_models():\n" + "\n".join(
        violations
    )


def test_pathing_uses_alive_group_model_ids_for_movement() -> None:
    tree = ast.parse(PATHING.read_text(encoding="utf-8"), filename=str(PATHING))
    forbidden: list[str] = []
    uses_group_movement_ids = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr == "model_ids_for_movement":
            uses_group_movement_ids = True
        if node.attr in {"all_model_ids", "all_models"}:
            forbidden.append(f"{PATHING.relative_to(ROOT)} uses {node.attr}")

    assert uses_group_movement_ids, "Pathing must use UnitGroup.model_ids_for_movement()."
    assert not forbidden, "Pathing must not move destroyed/all models:\n" + "\n".join(forbidden)


def test_movement_legality_gates_friendly_vehicle_monster_blockers_by_mover() -> None:
    tree = ast.parse(
        MOVEMENT_LEGALITY.read_text(encoding="utf-8"),
        filename=str(MOVEMENT_LEGALITY),
    )
    contexts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "to_path_validation_context"
    ]
    assert len(contexts) == 1, "MovementLegalityContext must own pathing-context conversion."
    context = contexts[0]

    gates_on_mover_keyword = any(
        isinstance(node, ast.Attribute)
        and node.attr == "blocks_friendly_vehicle_monster_pass_through"
        for node in ast.walk(context)
    )
    passes_filtered_blockers = False
    passes_enemy_blockers = False
    for node in ast.walk(context):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "PathValidationContext":
            continue
        for keyword in node.keywords:
            if keyword.arg != "friendly_vehicle_monster_model_ids":
                continue
            if (
                isinstance(keyword.value, ast.Name)
                and keyword.value.id == "friendly_vehicle_monster_blockers"
            ):
                passes_filtered_blockers = True
        for keyword in node.keywords:
            if keyword.arg != "enemy_vehicle_monster_model_ids":
                continue
            if (
                isinstance(keyword.value, ast.Name)
                and keyword.value.id == "enemy_vehicle_monster_blockers"
            ):
                passes_enemy_blockers = True

    assert gates_on_mover_keyword, "Friendly VEHICLE/MONSTER transit blockers must gate on mover."
    assert passes_filtered_blockers, "Pathing must receive the filtered blocker set."
    assert passes_enemy_blockers, "Pathing must receive the filtered enemy blocker set."


def test_movement_phase_has_no_public_reinforcements_step_tokens() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in MOVEMENT_PHASE_FILES)
    forbidden_tokens = (
        "reinforcements_step_completed",
        "reinforcements_waiting_for_arrival_choice",
        '"reinforcements_complete"',
        "reinforcements_step_entered",
        '"step": MovementPhaseStepKind.REINFORCEMENTS.value',
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert not violations, "Reserve arrivals must stay inside Move Units:\n" + "\n".join(violations)


def test_deadly_demise_enumerates_canonical_rules_units() -> None:
    function = _function_node(
        path=DEADLY_DEMISE,
        function_name="deadly_demise_target_unit_ids",
    )
    call_names = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "rules_unit_views_from_armies" in call_names


def test_rule_deadly_demise_collateral_uses_shared_destruction_continuation() -> None:
    function = _function_node(
        path=RULE_MODEL_DESTRUCTION,
        function_name="_continue_rule_deadly_demise_secondary_destroyed_models",
    )
    function_source = ast.unparse(function)
    call_names = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert {
        "_continue_rule_deadly_demise_sources",
        "_remove_rule_destroyed_model_and_continue",
    }.issubset(call_names)
    assert "remove_destroyed_model_from_battlefield" not in call_names
    assert "not item.optional" in function_source
    assert "item.reaction_kind is DestructionReactionKind.DEADLY_DEMISE" in function_source


def test_rule_deadly_demise_resolution_uses_context_destruction_provenance() -> None:
    function = _function_node(
        path=RULE_MODEL_DESTRUCTION,
        function_name="_emit_rule_deadly_demise_resolution",
    )
    call_names = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "destruction_provenance_from_rule_context" in call_names


def test_model_loss_hosts_share_attached_unit_reconciliation() -> None:
    for path, function_names in (
        (RULE_MODEL_DESTRUCTION, ("finalize_rule_model_destruction",)),
        (CATALOG_SELECTED_TARGET_EVENT, ("append_selected_target_event",)),
    ):
        for function_name in function_names:
            function = _function_node(path=path, function_name=function_name)
            call_names = {
                node.func.id
                for node in ast.walk(function)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            assert "split_attached_rules_unit_if_required" in call_names

    mortal_wound_source = CATALOG_SELECTED_TARGET_MORTAL_WOUNDS.read_text(encoding="utf-8")
    assert "split_attached_rules_unit_if_required" not in mortal_wound_source

    for path in sorted((ROOT / "src" / "warhammer40k_core" / "engine").rglob("*.py")):
        if path in {
            ATTACHED_UNIT_RECONCILIATION,
            ROOT / "src" / "warhammer40k_core" / "engine" / "game_state.py",
        }:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not any(
            isinstance(node, ast.Attribute)
            and node.attr == "recover_starting_strength_after_attached_unit_split"
            for node in ast.walk(tree)
        ), f"{path.relative_to(ROOT)} bypasses shared Attached Unit reconciliation."


def test_selected_target_canonical_identity_expands_all_current_survivors() -> None:
    function = _function_node(
        path=CATALOG_SELECTED_TARGET_EFFECTS_SUPPORT,
        function_name="canonical_rules_unit_ids",
    )
    call_names = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "current_rules_unit_views_for_identity" in call_names
    assert "current_placed_alive_rules_unit_view_for_identity" not in call_names


def test_completed_fight_move_consumers_use_canonical_identity_and_group_endpoints() -> None:
    for path, function_name in (
        (
            CULT_AMBUSH_MARKER_REMOVAL,
            "resolve_cult_ambush_marker_removal_for_completed_moves",
        ),
        (
            PRIMARY_MISSION_STATE_RUNTIME,
            "resolve_surveil_marker_removal_for_completed_moves",
        ),
    ):
        function = _function_node(path=path, function_name=function_name)
        call_names = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "rules_unit_views_for_completed_move_event" in call_names
        assert "fight_rules_unit_movement_endpoint_from_completed_event" in call_names
        assert "current_rules_unit_views_for_canonical_identity" not in call_names
        assert "current_rules_unit_views_for_identity" not in call_names
        assert "rules_unit_view_by_id" not in call_names
        assert "unit_placement_by_id" not in call_names

    identity_resolver = _function_node(
        path=FIGHT_RULES_UNIT_MOVEMENT_TYPES,
        function_name="rules_unit_views_for_completed_move_event",
    )
    resolver_call_names = {
        node.func.id
        for node in ast.walk(identity_resolver)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "current_rules_unit_views_for_canonical_identity",
        "current_rules_unit_views_for_identity",
    }.issubset(resolver_call_names)


def test_attack_target_geometry_is_living_only_without_weakening_stratagem_presence() -> None:
    shooting_candidate = _function_node(path=SHOOTING_TARGETS, function_name="_target_candidate")
    shooting_calls = {
        node.func.id
        for node in ast.walk(shooting_candidate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_geometry_models_for_target_placements" in shooting_calls

    melee_targets = _function_node(path=FIGHT_RESOLUTION, function_name="melee_target_unit_ids")
    melee_calls = {
        node.func.id
        for node in ast.walk(melee_targets)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_attack_targetable_engaged_enemy_unit_ids" in melee_calls

    fight_target_geometry = _function_node(
        path=FIGHT_GEOMETRY,
        function_name="geometry_models_for_fight_attack_target_unit",
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "is_alive"
        for node in ast.walk(fight_target_geometry)
    )

    stratagem_geometry = _function_node(
        path=STRATAGEMS_GEOMETRY,
        function_name="_geometry_models_for_unit",
    )
    stratagem_calls = {
        node.func.id
        for node in ast.walk(stratagem_geometry)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "model_is_present_on_battlefield" in stratagem_calls
    assert "placed_alive_geometry_models_for_rules_unit" not in stratagem_calls


def test_range_and_los_consumers_declare_living_model_policy_explicitly() -> None:
    physical_los_calls: list[tuple[Path, int]] = []
    range_call_count = 0
    los_call_count = 0

    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            if node.func.id == "target_within_shooting_selection_range":
                range_call_count += 1
                for keyword_name in (
                    "placed_alive_attacker_models_only",
                    "placed_alive_target_models_only",
                ):
                    value = keywords.get(keyword_name)
                    assert isinstance(value, ast.Constant), (
                        f"{path.relative_to(ROOT)}:{node.lineno} must pass {keyword_name}=True"
                    )
                    assert value.value is True, (
                        f"{path.relative_to(ROOT)}:{node.lineno} must pass {keyword_name}=True"
                    )
            if node.func.id == "unit_has_line_of_sight_to_target":
                los_call_count += 1
                value = keywords.get("placed_alive_models_only")
                assert isinstance(value, ast.Constant), (
                    f"{path.relative_to(ROOT)}:{node.lineno} must explicitly pass "
                    "placed_alive_models_only"
                )
                assert type(value.value) is bool, (
                    f"{path.relative_to(ROOT)}:{node.lineno} must explicitly pass "
                    "placed_alive_models_only"
                )
                if value.value is False:
                    physical_los_calls.append((path, node.lineno))

    assert range_call_count > 0
    assert los_call_count > 0
    assert len(physical_los_calls) == 1
    assert physical_los_calls[0][0] == STRATAGEMS_GEOMETRY

    stratagem_visibility = _function_node(
        path=STRATAGEMS_GEOMETRY,
        function_name="_visible_enemy_target_is_visible_and_in_range",
    )
    stratagem_los_calls = tuple(
        node
        for node in ast.walk(stratagem_visibility)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "unit_has_line_of_sight_to_target"
    )
    assert len(stratagem_los_calls) == 1
    stratagem_keywords = {keyword.arg: keyword.value for keyword in stratagem_los_calls[0].keywords}
    explicit_physical = stratagem_keywords.get("placed_alive_models_only")
    assert isinstance(explicit_physical, ast.Constant)
    assert explicit_physical.value is False


def _function_node(*, path: Path, function_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = tuple(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    assert len(matches) == 1, f"Expected exactly one {function_name} in {path}."
    return matches[0]
