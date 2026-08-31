from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PACKAGE = ROOT / "src" / "warhammer40k_core"
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
CATALOG_CONDITIONAL_CHARGE_RUNTIME = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_conditional_charge_runtime.py"
)
CATALOG_DESPERATE_ESCAPE = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_desperate_escape.py"
)
CATALOG_RULE_CONSUMPTION = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_rule_consumption.py"
)
CATALOG_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_RUNTIME = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "engine"
    / "catalog_unit_move_completed_battle_shock_runtime.py"
)
CULT_AMBUSH_MARKER_REMOVAL = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "cult_ambush_marker_removal.py"
)
PRIMARY_MISSION_STATE_RUNTIME = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "primary_mission_state_runtime.py"
)
PRIMARY_MISSION_BOUNDARY_PHYSICAL_AUTHORITY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "primary_mission_boundary_physical_authority.py"
)
FIGHT_RULES_UNIT_MOVEMENT_TYPES = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_rules_unit_movement_types.py"
)
FIGHT_RULES_UNIT_MOVEMENT = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_rules_unit_movement.py"
)
FIGHT_ACTIVATION_HISTORY_INTEGRITY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_activation_history_integrity.py"
)
FIGHT_MODEL_AUTHORITY_HISTORY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_model_authority_history.py"
)
FIGHT_MOVEMENT_TARGET_AUTHORITY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_movement_target_authority.py"
)
FIGHT_MOVEMENT_MODE_AUTHORITY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "fight_movement_mode_authority.py"
)
FIGHT_GEOMETRY = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_geometry.py"
FIGHT_RESOLUTION = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_resolution.py"
PHYSICAL_ENGAGEMENT = ROOT / "src" / "warhammer40k_core" / "engine" / "physical_engagement.py"
CHARGE_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "charge.py"
MOVEMENT_GEOMETRY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement_geometry.py"
)
SHOOTING_TARGETING = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "shooting_targeting.py"
)
SHOOTING_TARGETS = ROOT / "src" / "warhammer40k_core" / "engine" / "shooting_targets.py"
VISIBILITY = ROOT / "src" / "warhammer40k_core" / "geometry" / "visibility.py"
VISIBILITY_QUERY = ROOT / "src" / "warhammer40k_core" / "geometry" / "visibility_query.py"
TERRAIN_AREA_VISIBILITY = (
    ROOT / "src" / "warhammer40k_core" / "geometry" / "terrain_area_visibility.py"
)
STRATAGEMS_GEOMETRY = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems_geometry.py"
AELDARI_ARMY_RULE = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "engine"
    / "faction_content"
    / "warhammer_40000_11th"
    / "aeldari"
    / "army_rule.py"
)
CORSAIR_STRATAGEMS = AELDARI_ARMY_RULE.parent / "detachments" / "corsair_coterie" / "stratagems.py"
CHAOS_DAEMONS_DATASHEETS = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "engine"
    / "faction_content"
    / "warhammer_40000_11th"
    / "chaos_daemons"
    / "datasheets.py"
)
SHADOW_LEGION_ENHANCEMENTS = (
    CHAOS_DAEMONS_DATASHEETS.parent / "detachments" / "shadow_legion" / "enhancements.py"
)
TRIGGERED_MOVEMENT = ROOT / "src" / "warhammer40k_core" / "engine" / "triggered_movement.py"
TRIGGERED_MOVEMENT_PHYSICAL_AUTHORITY = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "triggered_movement_physical_authority.py"
)
TRANSPORTS = ROOT / "src" / "warhammer40k_core" / "engine" / "transports.py"
TURN_START_ENGAGEMENT = ROOT / "src" / "warhammer40k_core" / "engine" / "turn_start_engagement.py"
UNIT_PROXIMITY = ROOT / "src" / "warhammer40k_core" / "engine" / "unit_proximity.py"
UNIT_MODULES = (
    CORE / "unit.py",
    CORE / "attached_unit.py",
    CORE / "unit_group.py",
)

DIRECT_ENGAGEMENT_RANGE_CALL_ALLOWLIST: Counter[tuple[str, str]] = Counter(
    {
        (
            "src/warhammer40k_core/engine/catalog_selected_target_effects_support.py",
            "any_models_satisfy_distance",
        ): 1,
        (
            "src/warhammer40k_core/engine/deployment.py",
            "_append_geometry_violations",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_geometry.py",
            "attack_targetable_engaged_enemy_unit_ids",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_geometry.py",
            "model_engaged_with_any",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_resolution.py",
            "_unit_is_engaged_with_any",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_resolution.py",
            "_engaged_enemy_unit_ids",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_resolution.py",
            "_engaged_model_ids_for_model_and_target_unit_or_empty",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_rules_unit_movement.py",
            "_engaged_enemy_rules_unit_ids",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_rules_unit_movement.py",
            "_rules_unit_engaged_with_targets",
        ): 1,
        (
            "src/warhammer40k_core/engine/fight_rules_unit_movement.py",
            "_model_engaged",
        ): 1,
        (
            "src/warhammer40k_core/engine/healing_geometry.py",
            "healing_phase_start_enemy_engagement_model_ids",
        ): 1,
        (
            "src/warhammer40k_core/engine/healing_revival.py",
            "_validate_revived_model_engagement",
        ): 1,
        (
            "src/warhammer40k_core/engine/phases/charge.py",
            "_model_groups_are_engaged",
        ): 1,
        (
            "src/warhammer40k_core/engine/phases/movement_geometry.py",
            "_enemy_engagement_model_ids_for_unit",
        ): 1,
        (
            "src/warhammer40k_core/engine/physical_engagement.py",
            "geometry_models_are_physically_engaged",
        ): 1,
        (
            "src/warhammer40k_core/engine/prebattle.py",
            "_append_setup_geometry_violations",
        ): 1,
        (
            "src/warhammer40k_core/engine/reserves.py",
            "_append_common_reserve_placement_violations",
        ): 1,
        (
            "src/warhammer40k_core/engine/return_on_death.py",
            "_placement_within_enemy_engagement_range",
        ): 1,
        (
            "src/warhammer40k_core/engine/stratagems_geometry.py",
            "_any_models_within_engagement_range",
        ): 1,
        (
            "src/warhammer40k_core/engine/transports.py",
            "_append_disembark_endpoint_violations",
        ): 1,
        (
            "src/warhammer40k_core/geometry/collision.py",
            "engagement_query",
        ): 1,
        (
            "src/warhammer40k_core/geometry/pathing.py",
            "_models_are_in_enemy_engagement_range",
        ): 1,
    }
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


def test_fight_movement_separates_selectable_targets_from_physical_geometry() -> None:
    target_inventory = _function_node(
        path=FIGHT_RULES_UNIT_MOVEMENT,
        function_name="_enemy_rules_units",
    )
    target_inventory_calls = {
        node.func.id
        for node in ast.walk(target_inventory)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "placed_alive_rules_unit_views" in target_inventory_calls
    assert "fight_present_rules_unit_views" not in target_inventory_calls

    physical_inventory = _function_node(
        path=FIGHT_RULES_UNIT_MOVEMENT,
        function_name="_physical_enemy_rules_units",
    )
    physical_inventory_calls = {
        node.func.id
        for node in ast.walk(physical_inventory)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "fight_present_rules_unit_views" in physical_inventory_calls
    assert "placed_alive_rules_unit_views" not in physical_inventory_calls

    pile_selector = _function_node(
        path=FIGHT_MOVEMENT_MODE_AUTHORITY,
        function_name="legal_pile_in_target_rules_unit_ids",
    )
    consolidation_selector = _function_node(
        path=FIGHT_MOVEMENT_MODE_AUTHORITY,
        function_name="legal_consolidation_modes",
    )
    for selector in (pile_selector, consolidation_selector):
        selector_calls = {
            node.func.id
            for node in ast.walk(selector)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert {
            "_targetable_enemy_rules_units",
            "physical_geometry_models_for_rules_unit",
            "scenario_physically_engaged_enemy_rules_unit_ids",
        }.issubset(selector_calls)

    targetable_inventory = _function_node(
        path=FIGHT_MOVEMENT_MODE_AUTHORITY,
        function_name="_targetable_enemy_rules_units",
    )
    targetable_inventory_calls = {
        node.func.id
        for node in ast.walk(targetable_inventory)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "placed_alive_rules_unit_views" in targetable_inventory_calls

    physical_blockers = _function_node(
        path=FIGHT_RULES_UNIT_MOVEMENT,
        function_name="_enemy_geometry_models",
    )
    physical_blocker_calls = {
        node.func.id
        for node in ast.walk(physical_blockers)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "fight_present_rules_unit_views" in physical_blocker_calls

    measurement_geometry = _function_node(
        path=FIGHT_RULES_UNIT_MOVEMENT,
        function_name="_measurement_target_model_placements",
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "model_is_present_at_placement"
        for node in ast.walk(measurement_geometry)
    )

    standalone_target_inventory = _function_node(
        path=FIGHT_GEOMETRY,
        function_name="enemy_unit_ids_for_fight_placement",
    )
    standalone_target_calls = {
        node.func.id
        for node in ast.walk(standalone_target_inventory)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "rules_unit_view_from_armies",
        "scenario_rules_unit_has_placed_alive_model",
    }.issubset(standalone_target_calls)

    standalone_physical_blockers = _function_node(
        path=FIGHT_GEOMETRY,
        function_name="enemy_geometry_models_for_player",
    )
    standalone_physical_blocker_calls = {
        node.func.id
        for node in ast.walk(standalone_physical_blockers)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "scenario_rules_unit_has_placed_alive_model" not in (standalone_physical_blocker_calls)

    for function_name in ("legal_pile_in_target_unit_ids", "legal_consolidation_modes"):
        selector = _function_node(path=FIGHT_RESOLUTION, function_name=function_name)
        selector_calls = {
            node.func.id
            for node in ast.walk(selector)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert {
            "_enemy_unit_ids_for_placement",
            "scenario_physically_engaged_enemy_rules_unit_ids",
        }.issubset(selector_calls)


def test_physical_engagement_has_one_symmetric_geometry_owner_for_consumers() -> None:
    physical_geometry = _function_node(
        path=PHYSICAL_ENGAGEMENT,
        function_name="physical_geometry_models_for_rules_unit",
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "model_is_present_at_placement"
        for node in ast.walk(physical_geometry)
    )

    physical_engagement = _function_node(
        path=PHYSICAL_ENGAGEMENT,
        function_name="scenario_physically_engaged_enemy_rules_unit_ids",
    )
    physical_engagement_calls = {
        node.func.id
        for node in ast.walk(physical_engagement)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "physical_geometry_models_for_rules_unit",
        "scenario_physical_enemy_rules_unit_ids",
        "geometry_models_are_physically_engaged",
    }.issubset(physical_engagement_calls)

    proximity = _function_node(
        path=UNIT_PROXIMITY,
        function_name="unit_within_enemy_engagement_range",
    )
    proximity_calls = {
        node.func.id
        for node in ast.walk(proximity)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "current_rules_unit_is_physically_engaged" in proximity_calls

    for function_name in ("_locked_in_combat_context", "_target_engagement_context"):
        shooting_context = _function_node(
            path=SHOOTING_TARGETS,
            function_name=function_name,
        )
        shooting_calls = {
            node.func.id
            for node in ast.walk(shooting_context)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "scenario_physically_engaged_enemy_rules_unit_ids" in shooting_calls


def test_direct_engagement_range_geometry_calls_match_reviewed_boundary_inventory() -> None:
    observed: Counter[tuple[str, str]] = Counter()
    for path in sorted(RUNTIME_PACKAGE.rglob("*.py")):
        visitor = _DirectEngagementRangeCallVisitor(path=path)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        observed.update(visitor.calls)

    assert observed == DIRECT_ENGAGEMENT_RANGE_CALL_ALLOWLIST, (
        "Direct Engagement Range geometry changed. Current-state whole-unit consumers must use "
        "physical_engagement; add only reviewed model-specific, historical, or proposed-endpoint "
        "geometry to the allowlist.\n"
        f"Unexpected: {observed - DIRECT_ENGAGEMENT_RANGE_CALL_ALLOWLIST}\n"
        f"Missing: {DIRECT_ENGAGEMENT_RANGE_CALL_ALLOWLIST - observed}"
    )


def test_phase_current_engagement_consumers_use_shared_physical_owner() -> None:
    for path, function_name in (
        (CHARGE_PHASE, "_unit_is_engaged"),
        (MOVEMENT_GEOMETRY, "_enemy_engaged_unit_ids_for_unit_placement"),
        (SHOOTING_TARGETING, "_rules_unit_within_enemy_engagement_range"),
    ):
        consumer = _function_node(path=path, function_name=function_name)
        calls = _direct_call_names(consumer)
        assert "scenario_physically_engaged_enemy_rules_unit_ids" in calls
        assert "is_within_engagement_range" not in ast.unparse(consumer)

    turn_start = _function_node(
        path=TURN_START_ENGAGEMENT,
        function_name="_engaged_unit_pairs",
    )
    turn_start_calls = _direct_call_names(turn_start)
    assert {
        "_canonical_physically_present_rules_unit_ids_for_placements",
        "scenario_rules_units_are_physically_engaged",
    }.issubset(turn_start_calls)
    assert "is_within_engagement_range" not in ast.unparse(turn_start)


def test_catalog_engagement_consumers_require_living_authority_and_shared_geometry() -> None:
    for path, function_name in (
        (CATALOG_CONDITIONAL_CHARGE_RUNTIME, "_models_are_engaged"),
        (CATALOG_DESPERATE_ESCAPE, "_target_within_source_engagement"),
        (CATALOG_RULE_CONSUMPTION, "_unit_move_completed_mortal_wounds_target_candidates"),
        (CATALOG_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_RUNTIME, "_target_candidates"),
    ):
        consumer = _function_node(path=path, function_name=function_name)
        calls = _direct_call_names(consumer)
        assert {
            "rules_unit_has_placed_alive_model",
            "scenario_rules_units_are_physically_engaged",
        }.issubset(calls)
        assert "is_within_engagement_range" not in ast.unparse(consumer)


def test_content_and_stratagem_engagement_consumers_keep_living_authority_separate() -> None:
    opportunity = _function_node(
        path=AELDARI_ARMY_RULE,
        function_name="opportunity_seized_surge_grants",
    )
    opportunity_calls = _direct_call_names(opportunity)
    assert {
        "_scenario_at_triggering_unit_start",
        "rules_unit_has_placed_alive_model",
        "scenario_rules_units_are_physically_engaged",
    }.issubset(opportunity_calls)

    opportunity_scenario = _function_node(
        path=AELDARI_ARMY_RULE,
        function_name="_scenario_at_triggering_unit_start",
    )
    assert "battlefield_scenario_for_state" in _direct_call_names(opportunity_scenario)
    assert "present_destroyed_model_ids" in ast.unparse(opportunity_scenario)

    for path, function_name, physical_call in (
        (
            CHAOS_DAEMONS_DATASHEETS,
            "_enemy_rules_unit_within_source_engagement_range",
            "scenario_rules_units_are_physically_engaged",
        ),
        (
            CHAOS_DAEMONS_DATASHEETS,
            "_enemy_rules_unit_ids_within_source_engagement_range",
            "scenario_physically_engaged_enemy_rules_unit_ids",
        ),
        (
            SHADOW_LEGION_ENHANCEMENTS,
            "_unit_is_enemy_within_mantle_of_gloom",
            "scenario_rules_units_are_physically_engaged",
        ),
        (
            SHADOW_LEGION_ENHANCEMENTS,
            "_enemy_rules_unit_ids_within_engagement_range",
            "scenario_physically_engaged_enemy_rules_unit_ids",
        ),
    ):
        consumer = _function_node(path=path, function_name=function_name)
        calls = _direct_call_names(consumer)
        assert "rules_unit_has_placed_alive_model" in calls
        assert physical_call in calls

    corsair_engagement = _function_node(
        path=CORSAIR_STRATAGEMS,
        function_name="_unit_is_engaged",
    )
    corsair_calls = _direct_call_names(corsair_engagement)
    assert {
        "battlefield_scenario_for_state",
        "physical_geometry_models_for_rules_unit",
        "current_rules_unit_is_physically_engaged",
    }.issubset(corsair_calls)
    assert "is_within_engagement_range" not in ast.unparse(corsair_engagement)

    for function_name, expected_call in (
        ("_units_are_engaged", "current_physically_engaged_enemy_rules_unit_ids"),
        ("_unit_is_within_enemy_engagement_range", "current_rules_unit_is_physically_engaged"),
        (
            "_enemy_unit_is_within_friendly_engagement_range",
            "current_physically_engaged_enemy_rules_unit_ids",
        ),
    ):
        stratagem_consumer = _function_node(
            path=STRATAGEMS_GEOMETRY,
            function_name=function_name,
        )
        assert expected_call in _direct_call_names(stratagem_consumer)
        assert "is_within_engagement_range" not in ast.unparse(stratagem_consumer)


def test_triggered_movement_separates_living_sources_from_retained_physical_bases() -> None:
    resolver = _function_node(
        path=TRIGGERED_MOVEMENT,
        function_name="resolve_triggered_movement",
    )
    resolver_calls = {
        node.func.id
        for node in ast.walk(resolver)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "require_triggered_movement_source_model_placements",
        "validate_triggered_movement_source_witness",
        "merge_triggered_movement_source_endpoints",
        "retained_triggered_movement_blocker_ids",
        "resolve_triggered_movement_source_coherency",
    }.issubset(resolver_calls)

    source_inventory = _function_node(
        path=TRIGGERED_MOVEMENT_PHYSICAL_AUTHORITY,
        function_name="triggered_movement_source_model_placements",
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "is_alive"
        for node in ast.walk(source_inventory)
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "model_is_present_at_placement"
        for node in ast.walk(source_inventory)
    )

    scenario_builder = _function_node(
        path=TRIGGERED_MOVEMENT,
        function_name="_battlefield_scenario",
    )
    scenario_calls = {
        node.func.id
        for node in ast.walk(scenario_builder)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "battlefield_scenario_for_state" in scenario_calls

    restriction_owner = _function_node(
        path=TRIGGERED_MOVEMENT,
        function_name="_triggered_movement_restriction_violations",
    )
    restriction_calls = _direct_call_names(restriction_owner)
    assert "scenario_physically_engaged_enemy_rules_unit_ids" in restriction_calls
    assert "_enemy_engagement_model_ids_for_unit" not in restriction_calls
    assert "is_within_engagement_range" not in ast.unparse(restriction_owner)


def test_combat_disembark_uses_canonical_physical_transport_engagement() -> None:
    current_engagement = _function_node(
        path=TRANSPORTS,
        function_name="_enemy_unit_ids_engaged_with_transport",
    )
    current_engagement_calls = {
        node.func.id
        for node in ast.walk(current_engagement)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "rules_unit_view_from_armies",
        "scenario_physically_engaged_enemy_rules_unit_ids",
    }.issubset(current_engagement_calls)
    assert "_placed_geometry_models" not in current_engagement_calls

    endpoint_validation = _function_node(
        path=TRANSPORTS,
        function_name="_append_disembark_endpoint_violations",
    )
    endpoint_calls = {
        node.func.id
        for node in ast.walk(endpoint_validation)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "rules_unit_view_from_armies" in endpoint_calls


def test_fight_movement_restore_authenticates_target_authority_at_the_right_boundary() -> None:
    pending = _function_node(
        path=FIGHT_ACTIVATION_HISTORY_INTEGRITY,
        function_name="_validate_pending_fight_movement_target_authority",
    )
    pending_calls = {
        node.func.id
        for node in ast.walk(pending)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {
        "legal_rules_unit_pile_in_target_unit_ids",
        "legal_rules_unit_consolidation_modes",
    }.issubset(pending_calls)

    recorded = _function_node(
        path=FIGHT_ACTIVATION_HISTORY_INTEGRITY,
        function_name="_validate_recorded_fight_movement_witnesses",
    )
    recorded_calls = {
        node.func.id
        for node in ast.walk(recorded)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_validate_recorded_fight_movement_target_authority" in recorded_calls
    assert (
        sum(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_validate_recorded_fight_movement_target_authority"
            for node in ast.walk(recorded)
        )
        == 2
    )

    event_boundary = _function_node(
        path=FIGHT_ACTIVATION_HISTORY_INTEGRITY,
        function_name="_validate_recorded_fight_movement_target_authority",
    )
    event_boundary_calls = {
        node.func.id
        for node in ast.walk(event_boundary)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "historical_rules_unit_model_ids" in event_boundary_calls
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "has_placed_living_model_before_event"
        for node in ast.walk(event_boundary)
    )

    history_tree = ast.parse(
        FIGHT_MODEL_AUTHORITY_HISTORY.read_text(encoding="utf-8"),
        filename=str(FIGHT_MODEL_AUTHORITY_HISTORY),
    )
    historical_boundary_matches = tuple(
        node
        for node in ast.walk(history_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "has_placed_living_model_before_event"
    )
    assert len(historical_boundary_matches) == 1
    historical_boundary = historical_boundary_matches[0]
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "bisect_left"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Name)
        and node.args[1].id == "event_index"
        for node in ast.walk(historical_boundary)
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "authority_before"
        for node in ast.walk(historical_boundary)
    )

    emitter = _function_node(
        path=FIGHT_MOVEMENT_TARGET_AUTHORITY,
        function_name="build_fight_movement_target_authority_witness",
    )
    emitter_calls = {
        node.func.id
        for node in ast.walk(emitter)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "current_rules_unit_views_for_canonical_identity" in emitter_calls
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "is_alive" for node in ast.walk(emitter)
    )


def test_battlefield_transition_history_has_one_shared_event_registry() -> None:
    consumer = _function_node(
        path=PRIMARY_MISSION_BOUNDARY_PHYSICAL_AUTHORITY,
        function_name="_physical_authority_by_model",
    )
    consumer_calls = {
        node.func.id
        for node in ast.walk(consumer)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "authoritative_battlefield_transition_batch_or_none" in consumer_calls

    tree = ast.parse(
        PRIMARY_MISSION_BOUNDARY_PHYSICAL_AUTHORITY.read_text(encoding="utf-8"),
        filename=str(PRIMARY_MISSION_BOUNDARY_PHYSICAL_AUTHORITY),
    )
    assert not any(
        isinstance(node, ast.Name) and node.id == "_TRANSITION_EVENT_TYPES"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "_transition_from_event"
        for node in ast.walk(tree)
    )


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


def test_p06a_all_line_of_sight_blockers_use_the_shared_one_millimeter_corridor() -> None:
    visibility_source = VISIBILITY.read_text(encoding="utf-8")
    query_source = VISIBILITY_QUERY.read_text(encoding="utf-8")
    terrain_area_source = TERRAIN_AREA_VISIBILITY.read_text(encoding="utf-8")

    assert "line_of_sight_corridor_intersects_terrain_volume" in query_source
    assert "line_of_sight_corridor_intersects_model" in query_source
    assert "line_of_sight_corridor_bounds" in query_source
    assert "line_of_sight_corridor_intersects_polygon" in visibility_source
    assert "line_of_sight_corridor_intersects_terrain_area" in visibility_source
    assert "line_of_sight_corridor_intersects_polygon_union" in terrain_area_source

    forbidden_zero_width_calls = (
        "blocks_line_segment(",
        "segment_intersects_model_footprint(",
        "segment_intersects_polygon(",
        "segment_intersects_polygon_union(",
        "segment_intersects_terrain_footprint(",
    )
    for path, source in (
        (VISIBILITY, visibility_source),
        (VISIBILITY_QUERY, query_source),
        (TERRAIN_AREA_VISIBILITY, terrain_area_source),
    ):
        assert not any(marker in source for marker in forbidden_zero_width_calls), (
            f"{path.relative_to(ROOT)} bypasses the shared visibility corridor."
        )

    forbidden_engine_geometry_imports = {
        "warhammer40k_core.geometry.shapely_backend",
        "warhammer40k_core.geometry.visibility_corridor",
        "warhammer40k_core.geometry.visibility_query",
    }
    engine_bypasses: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in forbidden_engine_geometry_imports
            ):
                engine_bypasses.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            if isinstance(node, ast.Import):
                for imported in node.names:
                    if imported.name in forbidden_engine_geometry_imports:
                        engine_bypasses.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert engine_bypasses == []


class _DirectEngagementRangeCallVisitor(ast.NodeVisitor):
    def __init__(self, *, path: Path) -> None:
        self._relative_path = path.relative_to(ROOT).as_posix()
        self._function_names: list[str] = []
        self.calls: Counter[tuple[str, str]] = Counter()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_names.append(node.name)
        self.generic_visit(node)
        self._function_names.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_names.append(node.name)
        self.generic_visit(node)
        self._function_names.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == (
            "is_within_engagement_range"
        ):
            function_name = self._function_names[-1] if self._function_names else "<module>"
            self.calls[(self._relative_path, function_name)] += 1
        self.generic_visit(node)


def _direct_call_names(function: ast.FunctionDef) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _function_node(*, path: Path, function_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = tuple(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    assert len(matches) == 1, f"Expected exactly one {function_name} in {path}."
    return matches[0]
