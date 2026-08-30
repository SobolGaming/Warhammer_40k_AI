from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aircraft import HoverModeState
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement_geometry import (
    _desperate_escape_requirements_for_fall_back,
)
from warhammer40k_core.engine.phases.movement_model import (
    AdvanceRollResult,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.movement_resolvers import _resolve_unit_move
from warhammer40k_core.engine.phases.movement_state import (
    AdvanceMoveResolution,
    FallBackActionResult,
    NormalMoveResolution,
    _ResolvedUnitMove,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyContext,
    UnitCoherencyResult,
    rules_unit_coherency_result,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)


@dataclass(frozen=True, slots=True)
class _ResolvedRulesUnitMove:
    before: RulesUnitPlacement
    attempted: RulesUnitPlacement
    witness: PathWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    movement_payload: dict[str, JsonValue]
    desperate_escape_auto_pass_model_ids: tuple[str, ...]


def rules_unit_placement_for_movement(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[RulesUnitView, RulesUnitPlacement]:
    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    if rules_unit.unit_instance_id != unit_instance_id:
        raise GameLifecycleError("Movement requires canonical rules-unit identity.")
    placement = RulesUnitPlacement.from_battlefield(
        view=rules_unit,
        battlefield_state=scenario.battlefield_state,
    )
    return rules_unit, placement


def representative_movement_placement(
    rules_unit_placement: RulesUnitPlacement,
) -> UnitPlacement:
    if type(rules_unit_placement) is not RulesUnitPlacement:
        raise GameLifecycleError("Movement representative requires RulesUnitPlacement.")
    return rules_unit_placement.component_unit_placements[0]


def replace_rules_unit_placement(
    *,
    state: GameState,
    placement: RulesUnitPlacement,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rules-unit movement requires battlefield_state.")
    updated = battlefield
    for component in placement.component_unit_placements:
        updated = updated.with_unit_placement(component)
    state.replace_battlefield_state(updated)


def rules_unit_placement_coherency_result(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    placement: UnitPlacement | RulesUnitPlacement,
    rules_unit_instance_id: str,
) -> UnitCoherencyResult:
    model_placements = (
        placement.model_placements if type(placement) in {UnitPlacement, RulesUnitPlacement} else ()
    )
    if not model_placements:
        raise GameLifecycleError("Rules-unit coherency requires surviving model placements.")
    models = (
        placement.geometry_models(scenario)
        if type(placement) is RulesUnitPlacement
        else tuple(
            geometry_model_for_placement(
                model=scenario.model_instance_for_placement(model_placement),
                placement=model_placement,
            )
            for model_placement in placement.model_placements
        )
    )
    return UnitCoherencyContext.from_ruleset_descriptor(
        ruleset_descriptor,
        unit_instance_id=rules_unit_instance_id,
    ).validate_models(models)


def resolve_rules_unit_normal_move(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    before: RulesUnitPlacement,
    witness: PathWitness,
    movement_mode: MovementMode,
    objective_markers: tuple[ObjectiveMarker, ...],
    hover_mode_states: tuple[HoverModeState, ...],
    movement_bonus_inches: int,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_index: AbilityCatalogIndex,
    temporary_movement_keywords: tuple[str, ...],
) -> NormalMoveResolution:
    resolved = _resolve_rules_unit_move(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        before=before,
        witness=witness,
        movement_mode=movement_mode,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        action_label="Normal Move",
        objective_markers=objective_markers,
        hover_mode_states=hover_mode_states,
        movement_bonus_inches=movement_bonus_inches,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_index=ability_index,
        temporary_movement_keywords=temporary_movement_keywords,
    )
    return NormalMoveResolution(
        unit_instance_id=rules_unit.unit_instance_id,
        attempted_placement=resolved.attempted,
        witness=resolved.witness,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=None,
        movement_payload=resolved.movement_payload,
    )


def resolve_rules_unit_advance_move(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    before: RulesUnitPlacement,
    witness: PathWitness,
    advance_roll: AdvanceRollResult,
    movement_mode: MovementMode,
    objective_markers: tuple[ObjectiveMarker, ...],
    hover_mode_states: tuple[HoverModeState, ...],
    movement_bonus_inches: int,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_index: AbilityCatalogIndex,
    temporary_movement_keywords: tuple[str, ...],
    ignores_vertical_distance: bool,
) -> AdvanceMoveResolution:
    if advance_roll.request.unit_instance_id != rules_unit.unit_instance_id:
        raise GameLifecycleError("Rules-unit Advance roll identity drift.")
    resolved = _resolve_rules_unit_move(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        before=before,
        witness=witness,
        movement_mode=movement_mode,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        displacement_kind=ModelDisplacementKind.ADVANCE,
        action_label="Advance",
        objective_markers=objective_markers,
        hover_mode_states=hover_mode_states,
        movement_bonus_inches=advance_roll.value + movement_bonus_inches,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_index=ability_index,
        temporary_movement_keywords=temporary_movement_keywords,
        ignores_vertical_distance=ignores_vertical_distance,
    )
    return AdvanceMoveResolution(
        unit_instance_id=rules_unit.unit_instance_id,
        attempted_placement=resolved.attempted,
        witness=resolved.witness,
        advance_roll=advance_roll,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=None,
        movement_payload={
            **resolved.movement_payload,
            "advance_roll": validate_json_value(advance_roll.to_payload()),
        },
    )


def resolve_rules_unit_fall_back_move(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    before: RulesUnitPlacement,
    witness: PathWitness,
    movement_mode: MovementMode,
    battle_round: int,
    battle_shocked_unit_ids: tuple[str, ...],
    forced_desperate_escape_source_rule_ids: tuple[str, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    hover_mode_states: tuple[HoverModeState, ...],
    movement_bonus_inches: int,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_index: AbilityCatalogIndex,
    temporary_movement_keywords: tuple[str, ...],
) -> FallBackActionResult:
    resolved = _resolve_rules_unit_move(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        before=before,
        witness=witness,
        movement_mode=movement_mode,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        action_label="Fall Back",
        objective_markers=objective_markers,
        hover_mode_states=hover_mode_states,
        movement_bonus_inches=movement_bonus_inches,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_index=ability_index,
        temporary_movement_keywords=temporary_movement_keywords,
    )
    shocked_ids = set(battle_shocked_unit_ids)
    if rules_unit.unit_instance_id in shocked_ids:
        shocked_ids.update(rules_unit.component_unit_instance_ids)
    auto_pass_ids = set(resolved.desperate_escape_auto_pass_model_ids)
    requirements = tuple(
        requirement
        for component in before.component_unit_placements
        for requirement in _desperate_escape_requirements_for_fall_back(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=component,
            witness=_component_witness(witness=witness, component=component),
            battle_round=battle_round,
            battle_shocked_unit_ids=tuple(sorted(shocked_ids)),
            forced_desperate_escape_source_rule_ids=forced_desperate_escape_source_rule_ids,
            overflight_auto_pass_model_ids=tuple(
                sorted(
                    placement.model_instance_id
                    for placement in component.model_placements
                    if placement.model_instance_id in auto_pass_ids
                )
            ),
        )
    )
    movement_payload = {
        **resolved.movement_payload,
        "desperate_escape_requirements": validate_json_value(
            [requirement.to_payload() for requirement in requirements]
        ),
        "desperate_escape_rolls": [],
    }
    if forced_desperate_escape_source_rule_ids:
        movement_payload["forced_desperate_escape_source_rule_ids"] = list(
            forced_desperate_escape_source_rule_ids
        )
    return FallBackActionResult.unresolved(
        unit_instance_id=rules_unit.unit_instance_id,
        attempted_placement=resolved.attempted,
        witness=resolved.witness,
        desperate_escape_requirements=requirements,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=None,
        movement_payload=movement_payload,
    )


def _resolve_rules_unit_move(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    before: RulesUnitPlacement,
    witness: PathWitness,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind,
    displacement_kind: ModelDisplacementKind,
    action_label: str,
    objective_markers: tuple[ObjectiveMarker, ...],
    hover_mode_states: tuple[HoverModeState, ...],
    movement_bonus_inches: int,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_index: AbilityCatalogIndex,
    temporary_movement_keywords: tuple[str, ...],
    ignores_vertical_distance: bool = False,
) -> _ResolvedRulesUnitMove:
    before.validate_for_view(rules_unit)
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in before.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError(f"{action_label} witness must match every rules-unit model.")
    attempted = RulesUnitPlacement(
        rules_unit_instance_id=before.rules_unit_instance_id,
        component_unit_placements=tuple(
            component.with_model_placements(
                tuple(
                    placement.with_pose(witness.final_pose_for_model(placement.model_instance_id))
                    for placement in component.model_placements
                )
            )
            for component in before.component_unit_placements
        ),
    )
    attempted_scenario = _scenario_with_rules_unit_placement(
        scenario=scenario,
        placement=attempted,
    )
    path_results: list[PathValidationResult] = []
    terrain_results: list[TerrainPathLegalityResult] = []
    model_movements: list[JsonValue] = []
    auto_pass_model_ids: list[str] = []
    aircraft_policy_payloads: list[JsonValue] = []
    maximum_movement_inches = 0.0
    attempted_by_component = {
        component.unit_instance_id: component for component in attempted.component_unit_placements
    }
    for before_component in before.component_unit_placements:
        component_scenario = _scenario_with_component_placement(
            scenario=attempted_scenario,
            placement=before_component,
        )
        component_resolution: _ResolvedUnitMove = _resolve_unit_move(
            scenario=component_scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=before_component,
            state=state,
            path_witness=_component_witness(witness=witness, component=before_component),
            battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
            terrain=(),
            terrain_features=scenario.battlefield_state.terrain_features,
            objective_markers=objective_markers,
            movement_bonus_inches=movement_bonus_inches,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action,
            displacement_kind=displacement_kind,
            action_label=action_label,
            rollback_on_endpoint_coherency=False,
            hover_mode_states=hover_mode_states,
            runtime_modifier_registry=runtime_modifier_registry,
            ability_index=ability_index,
            temporary_movement_keywords=temporary_movement_keywords,
            ignores_vertical_distance=ignores_vertical_distance,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        )
        if (
            component_resolution.attempted_placement
            != attempted_by_component[before_component.unit_instance_id]
        ):
            raise GameLifecycleError("Rules-unit movement component resolution drift.")
        path_results.extend(component_resolution.path_validation_results)
        terrain_results.extend(component_resolution.terrain_path_legality_results)
        movements = component_resolution.movement_payload.get("model_movements")
        if not isinstance(movements, list):
            raise GameLifecycleError("Rules-unit movement model payload drift.")
        model_movements.extend(movements)
        movement_inches = component_resolution.movement_payload.get("movement_inches")
        if not isinstance(movement_inches, (int, float)) or isinstance(movement_inches, bool):
            raise GameLifecycleError("Rules-unit movement distance payload drift.")
        maximum_movement_inches = max(maximum_movement_inches, float(movement_inches))
        auto_pass_model_ids.extend(component_resolution.desperate_escape_auto_pass_model_ids)
        aircraft_policy_payload = component_resolution.movement_payload.get(
            "aircraft_movement_policy"
        )
        if aircraft_policy_payload is not None:
            aircraft_policy_payloads.append(aircraft_policy_payload)
    coherency_result = rules_unit_coherency_result(
        scenario=attempted_scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
    )
    movement_payload: dict[str, JsonValue] = {
        "movement_mode": movement_mode.value,
        "movement_inches": maximum_movement_inches,
        "component_unit_instance_ids": list(before.component_unit_instance_ids),
        "model_movements": model_movements,
        "path_validation_results": validate_json_value(
            [result.to_payload() for result in path_results]
        ),
        "terrain_path_legality_results": validate_json_value(
            [result.to_payload() for result in terrain_results]
        ),
        "coherency_result": validate_json_value(coherency_result.to_payload()),
    }
    if len(aircraft_policy_payloads) > 1:
        raise GameLifecycleError("Rules unit contains multiple Aircraft movement policies.")
    if aircraft_policy_payloads:
        movement_payload["aircraft_movement_policy"] = aircraft_policy_payloads[0]
    return _ResolvedRulesUnitMove(
        before=before,
        attempted=attempted,
        witness=witness,
        path_validation_results=tuple(path_results),
        terrain_path_legality_results=tuple(terrain_results),
        coherency_result=coherency_result,
        movement_payload=movement_payload,
        desperate_escape_auto_pass_model_ids=tuple(sorted(auto_pass_model_ids)),
    )


def _component_witness(*, witness: PathWitness, component: UnitPlacement) -> PathWitness:
    return PathWitness.for_paths(
        tuple(
            (
                placement.model_instance_id,
                witness.poses_for_model(placement.model_instance_id),
            )
            for placement in component.model_placements
        )
    )


def _scenario_with_rules_unit_placement(
    *,
    scenario: BattlefieldScenario,
    placement: RulesUnitPlacement,
) -> BattlefieldScenario:
    battlefield = scenario.battlefield_state
    for component in placement.component_unit_placements:
        battlefield = battlefield.with_unit_placement(component)
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=battlefield,
        present_destroyed_model_ids=scenario.present_destroyed_model_ids,
    )


def _scenario_with_component_placement(
    *,
    scenario: BattlefieldScenario,
    placement: UnitPlacement,
) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(placement),
        present_destroyed_model_ids=scenario.present_destroyed_model_ids,
    )
