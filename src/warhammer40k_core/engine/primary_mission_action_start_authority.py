from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    CharacteristicValuePayload,
)
from warhammer40k_core.core.missions import MissionActionDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    ModelPlacementPayload,
    PlacedArmy,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.mission_action_eligibility import (
    MISSION_ACTION_UNIT_ADVANCED,
    MISSION_ACTION_UNIT_AIRCRAFT,
    MISSION_ACTION_UNIT_ALREADY_SHOT,
    MISSION_ACTION_UNIT_ALREADY_STARTED_ACTION,
    MISSION_ACTION_UNIT_BATTLE_SHOCKED,
    MISSION_ACTION_UNIT_ENGAGED,
    MISSION_ACTION_UNIT_FELL_BACK,
    MISSION_ACTION_UNIT_FORTIFICATION,
    MISSION_ACTION_UNIT_OFF_BATTLEFIELD,
    MISSION_ACTION_UNIT_ZERO_OBJECTIVE_CONTROL,
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    mission_action_policy_descriptors,
)
from warhammer40k_core.engine.mission_terrain import (
    mission_logical_terrain_areas,
    model_intersects_logical_terrain_area,
)
from warhammer40k_core.engine.missions import mission_pack_for_id
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_mission_action_battlefield_evidence import (
    MissionActionBattlefieldBoundaryEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionStartAuthorityEvidence,
    MissionActionStartCandidateUnitEvidence,
    MissionActionSurveilTargetEvidence,
    MissionActionTerrainIntersectionEvidence,
    MissionActionTerrainModelInventoryEvidence,
    PrimaryMissionActionStartEvidence,
    canonical_terrain_intersections,
    canonical_terrain_model_inventory,
)
from warhammer40k_core.engine.primary_mission_action_request_authority import (
    validate_recomputed_primary_mission_action_request_authority,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionMarkerStatus
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_identity_ids,
    rules_unit_is_battle_shocked,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardStatus
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.shooting_terrain_visibility import (
    shooting_terrain_areas_for_state,
    shooting_visibility_cache_key,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def capture_primary_mission_action_start_authority(
    *,
    state: GameState,
    player_id: str,
    authority: MissionActionStartAuthorityEvidence,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> MissionActionStartAuthorityEvidence:
    """Add complete candidate and terrain facts to an independently built request."""

    battlefield = state.battlefield_state
    setup = state.mission_setup
    if battlefield is None or setup is None:
        raise GameLifecycleError("Primary Mission Action authority requires battlefield state.")
    if (
        battlefield.battlefield_width_inches,
        battlefield.battlefield_depth_inches,
        battlefield.terrain_features,
    ) != (
        setup.battlefield_width_inches,
        setup.battlefield_depth_inches,
        setup.terrain_features,
    ):
        raise GameLifecycleError("Primary Mission Action battlefield boundary drifted.")
    if authority.battlefield_boundary != (
        MissionActionBattlefieldBoundaryEvidence.from_battlefield_state(battlefield)
    ):
        raise GameLifecycleError("Primary Mission Action battlefield boundary drifted.")
    views = rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    terrain_inventory = capture_primary_mission_action_terrain_model_inventory(
        state=state,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    option_ids_by_unit = _primary_option_ids_by_unit(authority)
    candidates = tuple(
        _capture_candidate(
            state=state,
            player_id=player_id,
            rules_unit=rules_unit,
            enemy_units=tuple(
                candidate for candidate in views if candidate.owner_player_id != player_id
            ),
            legal_primary_option_ids=option_ids_by_unit.get(rules_unit.unit_instance_id, ()),
            runtime_modifier_registry=runtime_modifier_registry,
        )
        for rules_unit in views
        if rules_unit.owner_player_id == player_id
    )
    return replace(
        authority,
        candidate_units=candidates,
        terrain_model_inventory=terrain_inventory,
        battle_shocked_unit_instance_ids=tuple(state.battle_shocked_unit_ids),
        advanced_unit_instance_ids=tuple(
            row.unit_instance_id
            for row in state.advanced_unit_states
            if row.player_id == player_id and row.battle_round == state.battle_round
        ),
        fell_back_unit_instance_ids=tuple(
            row.unit_instance_id
            for row in state.fell_back_unit_states
            if row.player_id == player_id and row.battle_round == state.battle_round
        ),
        shot_unit_instance_ids=(
            () if state.shooting_phase_state is None else state.shooting_phase_state.shot_unit_ids
        ),
        active_secondary_mission_ids=tuple(
            card.secondary_mission_id
            for card in state.secondary_mission_card_states
            if card.player_id == player_id and card.status is SecondaryMissionCardStatus.ACTIVE
        ),
    )


def validate_primary_mission_action_start_authority(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
) -> None:
    """Re-derive every source-backed Primary option from the complete start facts."""

    authority = evidence.start_authority
    candidate_by_id = {row.unit_instance_id: row for row in authority.candidate_units}
    friendly_component_ids = {
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id == evidence.player_id
        for unit in army.units
    }
    seen_component_ids: set[str] = set()
    if not candidate_by_id:
        raise GameLifecycleError("Primary Mission Action start candidate inventory drifted.")
    _validate_battlefield_boundary(state=state, evidence=evidence)
    validate_primary_mission_action_terrain_model_inventory(
        state=state,
        values=authority.terrain_model_inventory,
    )
    boundary_state = _boundary_game_state(state=state, evidence=evidence)
    for candidate in authority.candidate_units:
        component_ids = set(candidate.component_unit_instance_ids)
        if not component_ids.isdisjoint(seen_component_ids):
            raise GameLifecycleError("Primary Mission Action start candidate inventory drifted.")
        seen_component_ids.update(component_ids)
        _validate_candidate_identity(
            state=state,
            player_id=evidence.player_id,
            candidate=candidate,
        )
        _validate_candidate_boundary_facts(
            state=boundary_state,
            authority=authority,
            candidate=candidate,
        )
    if seen_component_ids != friendly_component_ids:
        raise GameLifecycleError("Primary Mission Action start candidate inventory drifted.")
    candidate_id_by_component = {
        component_id: candidate.unit_instance_id
        for candidate in authority.candidate_units
        for component_id in candidate.component_unit_instance_ids
    }
    if any(
        row.owner_player_id == evidence.player_id
        and candidate_id_by_component.get(row.component_unit_instance_id)
        != row.rules_unit_instance_id
        for row in authority.terrain_model_inventory
    ):
        raise GameLifecycleError("Primary Mission Action start terrain inventory drifted.")

    relevant_actions = _relevant_primary_actions(state=state, evidence=evidence)
    expected_by_unit: dict[str, tuple[str, ...]] = {}
    expected_targets_by_action: dict[str, dict[str, tuple[str, ...]]] = {
        action.mission_action_id: {} for action, _policy in relevant_actions
    }
    for candidate in authority.candidate_units:
        expected_ids: list[str] = []
        for action, policy in relevant_actions:
            targets = _candidate_targets(
                state=state,
                evidence=evidence,
                candidate=candidate,
                policy=policy,
                terrain_inventory=authority.terrain_model_inventory,
            )
            expected_targets_by_action[action.mission_action_id][candidate.unit_instance_id] = (
                targets
            )
            expected_ids.extend(
                f"start:{action.mission_action_id}:{candidate.unit_instance_id}:{target_id}"
                for target_id in targets
            )
        expected_by_unit[candidate.unit_instance_id] = tuple(sorted(expected_ids))
        if candidate.legal_primary_option_ids != expected_by_unit[candidate.unit_instance_id]:
            raise GameLifecycleError(
                "Primary Mission Action start candidate option inventory drifted."
            )

    expected_eligible_by_action = {
        action_id: tuple(sorted(unit_id for unit_id, targets in targets_by_unit.items() if targets))
        for action_id, targets_by_unit in expected_targets_by_action.items()
    }
    validate_recomputed_primary_mission_action_request_authority(
        state=boundary_state,
        evidence=evidence,
    )
    selected_eligible = expected_eligible_by_action.get(evidence.mission_action_id)
    if selected_eligible is None or evidence.eligible_unit_instance_ids != selected_eligible:
        raise GameLifecycleError("Primary Mission Action eligible-unit inventory drifted.")


def capture_primary_mission_action_terrain_model_inventory(
    *, state: GameState, runtime_modifier_registry: RuntimeModifierRegistry
) -> tuple[MissionActionTerrainModelInventoryEvidence, ...]:
    setup = state.mission_setup
    battlefield = state.battlefield_state
    if setup is None or battlefield is None:
        raise GameLifecycleError("Primary Mission Action terrain evidence requires battle state.")
    areas = mission_logical_terrain_areas(setup)
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=battlefield
    )
    rows: list[MissionActionTerrainModelInventoryEvidence] = []
    for army in state.army_definitions:
        for unit in army.units:
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=tuple(state.army_definitions),
                unit_instance_id=unit.unit_instance_id,
            )
            for model in unit.own_models:
                source_oc = model_objective_control_characteristic(model, battle_shocked=False)
                resolved_oc = model_objective_control_characteristic(
                    model,
                    battle_shocked=False,
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    runtime_modifier_registry=runtime_modifier_registry,
                    model_instance_id=model.model_instance_id,
                )
                if resolved_oc.final != source_oc.final and (
                    resolved_oc.applied_modifier_ids == source_oc.applied_modifier_ids
                ):
                    modifier_ids = tuple(
                        binding.modifier_id
                        for binding in runtime_modifier_registry.all_objective_control_bindings()
                    ) or ("generic-objective-control-runtime",)
                    resolved_oc = replace(
                        resolved_oc,
                        applied_modifier_ids=tuple(
                            sorted({*resolved_oc.applied_modifier_ids, *modifier_ids})
                        ),
                    )
                area_ids: tuple[str, ...] = ()
                placement = battlefield.model_placement_or_none(model.model_instance_id)
                if model.is_alive and placement is not None:
                    geometry_model = geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                    area_ids = tuple(
                        area.logical_terrain_area_id
                        for area in areas
                        if model_intersects_logical_terrain_area(geometry_model, area=area)
                    )
                rows.append(
                    MissionActionTerrainModelInventoryEvidence(
                        owner_player_id=army.player_id,
                        rules_unit_instance_id=rules_unit_id,
                        component_unit_instance_id=unit.unit_instance_id,
                        model_instance_id=model.model_instance_id,
                        wounds_remaining_at_boundary=model.wounds_remaining,
                        model_placement_json=(
                            None
                            if placement is None or not model.is_alive
                            else _canonical_json(placement.to_payload())
                        ),
                        source_objective_control_json=_canonical_json(source_oc.to_payload()),
                        resolved_objective_control_json=_canonical_json(resolved_oc.to_payload()),
                        logical_terrain_area_ids=area_ids,
                    )
                )
    return canonical_terrain_model_inventory(tuple(rows))


def terrain_intersections_from_model_inventory(
    values: tuple[MissionActionTerrainModelInventoryEvidence, ...],
) -> tuple[MissionActionTerrainIntersectionEvidence, ...]:
    return canonical_terrain_intersections(
        tuple(
            MissionActionTerrainIntersectionEvidence(
                logical_terrain_area_id=area_id,
                owner_player_id=row.owner_player_id,
                rules_unit_instance_id=row.rules_unit_instance_id,
                component_unit_instance_id=row.component_unit_instance_id,
                model_instance_id=row.model_instance_id,
            )
            for row in values
            for area_id in row.logical_terrain_area_ids
        )
    )


def validate_primary_mission_action_terrain_model_inventory(
    *,
    state: GameState,
    values: tuple[MissionActionTerrainModelInventoryEvidence, ...],
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action terrain evidence requires MissionSetup.")
    expected: dict[str, tuple[str, str, ModelInstance]] = {}
    armies = tuple(state.army_definitions)
    for army in armies:
        for unit in army.units:
            for model in unit.own_models:
                expected[model.model_instance_id] = (
                    army.player_id,
                    unit.unit_instance_id,
                    model,
                )
    if {row.model_instance_id for row in values} != set(expected):
        raise GameLifecycleError("Primary Mission Action terrain-model inventory drifted.")
    area_ids = {area.logical_terrain_area_id for area in mission_logical_terrain_areas(setup)}
    for row in values:
        owner_id, component_id, model = expected[row.model_instance_id]
        source_oc = CharacteristicValue.from_payload(
            cast(
                CharacteristicValuePayload,
                _json_object(row.source_objective_control_json),
            )
        )
        resolved_oc = CharacteristicValue.from_payload(
            cast(
                CharacteristicValuePayload,
                _json_object(row.resolved_objective_control_json),
            )
        )
        expected_source_oc = model_objective_control_characteristic(model, battle_shocked=False)
        placement = (
            None
            if row.model_placement_json is None
            else ModelPlacement.from_payload(
                cast(
                    ModelPlacementPayload,
                    _json_object(row.model_placement_json),
                )
            )
        )
        expected_area_ids: tuple[str, ...] = ()
        if placement is not None:
            geometry_model = geometry_model_for_placement(
                model=model,
                placement=placement,
            )
            expected_area_ids = tuple(
                sorted(
                    area.logical_terrain_area_id
                    for area in mission_logical_terrain_areas(setup)
                    if model_intersects_logical_terrain_area(geometry_model, area=area)
                )
            )
        if (
            (owner_id, component_id) != (row.owner_player_id, row.component_unit_instance_id)
            or row.rules_unit_instance_id
            not in _allowed_rules_unit_ids_for_component(
                state=state,
                player_id=row.owner_player_id,
                component_unit_instance_id=row.component_unit_instance_id,
            )
            or not set(row.logical_terrain_area_ids) <= area_ids
            or row.wounds_remaining_at_boundary > model.starting_wounds
            or (placement is not None and row.wounds_remaining_at_boundary == 0)
            or (
                placement is not None
                and (
                    placement.player_id != row.owner_player_id
                    or placement.unit_instance_id != row.component_unit_instance_id
                    or placement.model_instance_id != row.model_instance_id
                )
            )
            or row.logical_terrain_area_ids != expected_area_ids
            or source_oc != expected_source_oc
            or (
                resolved_oc.characteristic,
                resolved_oc.raw,
                resolved_oc.base,
                resolved_oc.value_kind,
            )
            != (
                source_oc.characteristic,
                source_oc.raw,
                source_oc.base,
                source_oc.value_kind,
            )
            or not set(source_oc.applied_modifier_ids) <= set(resolved_oc.applied_modifier_ids)
            or (
                resolved_oc.final != source_oc.final
                and resolved_oc.applied_modifier_ids == source_oc.applied_modifier_ids
            )
        ):
            raise GameLifecycleError("Primary Mission Action terrain-model inventory drifted.")


def _capture_candidate(
    *,
    state: GameState,
    player_id: str,
    rules_unit: RulesUnitView,
    enemy_units: tuple[RulesUnitView, ...],
    legal_primary_option_ids: tuple[str, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> MissionActionStartCandidateUnitEvidence:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary Mission Action authority requires battlefield state.")
    placed_ids = set(battlefield.placed_model_ids())
    placed_models = tuple(
        (component.unit.unit_instance_id, model)
        for component in rules_unit.components
        for model in component.unit.own_models
        if model.is_alive and model.model_instance_id in placed_ids
    )
    component_ids = tuple(sorted(rules_unit.component_unit_instance_ids))
    state_unit_ids = tuple(sorted({rules_unit.unit_instance_id, *component_ids}))
    shooting_state = state.shooting_phase_state
    return MissionActionStartCandidateUnitEvidence(
        unit_instance_id=rules_unit.unit_instance_id,
        unit_identity_ids=tuple(
            sorted(
                rules_unit_identity_ids(state=state, unit_instance_id=rules_unit.unit_instance_id)
            )
        ),
        component_unit_instance_ids=component_ids,
        alive_model_instance_ids=tuple(
            sorted(model.model_instance_id for model in rules_unit.own_models if model.is_alive)
        ),
        placed_alive_model_instance_ids=tuple(
            sorted(model.model_instance_id for _component_id, model in placed_models)
        ),
        positive_objective_control_model_instance_ids=tuple(
            sorted(
                model.model_instance_id
                for component_id, model in placed_models
                if (
                    characteristic := model_objective_control_characteristic(
                        model,
                        battle_shocked=False,
                        state=state,
                        unit_instance_id=component_id,
                        runtime_modifier_registry=runtime_modifier_registry,
                        model_instance_id=model.model_instance_id,
                    )
                ).is_numeric
                and characteristic.final > 0
            )
        ),
        keyword_tokens=tuple(sorted(_canonical_keyword(value) for value in rules_unit.keywords)),
        battle_shocked=rules_unit_is_battle_shocked(
            state=state, unit_instance_id=rules_unit.unit_instance_id
        ),
        within_enemy_engagement_range=(
            bool(placed_models)
            and unit_within_enemy_engagement_range(
                state=state, unit_instance_id=rules_unit.unit_instance_id
            )
        ),
        advanced_unit_instance_ids=tuple(
            unit_id
            for unit_id in state_unit_ids
            if state.advanced_unit_state_for_unit(
                player_id=player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
            is not None
        ),
        fell_back_unit_instance_ids=tuple(
            unit_id
            for unit_id in state_unit_ids
            if state.fell_back_unit_state_for_unit(
                player_id=player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
            is not None
        ),
        shot_unit_instance_ids=(
            ()
            if state.current_battle_phase is not BattlePhase.SHOOTING or shooting_state is None
            else tuple(sorted(set(state_unit_ids).intersection(shooting_state.shot_unit_ids)))
        ),
        unit_ineligibility_reason=mission_action_unit_ineligibility_reason(
            state=state,
            player_id=player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        objective_proximity_witness=rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        ),
        surveil_target_evidence=tuple(
            _capture_surveil_target(
                state=state,
                observer=rules_unit,
                target=target,
            )
            for target in enemy_units
        ),
        legal_primary_option_ids=legal_primary_option_ids,
    )


def _capture_surveil_target(
    *, state: GameState, observer: RulesUnitView, target: RulesUnitView
) -> MissionActionSurveilTargetEvidence:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Surveil evidence requires battlefield state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=battlefield
    )
    terrain_areas = shooting_terrain_areas_for_state(state)
    range_components: list[str] = []
    los_components: list[str] = []
    for component in observer.components:
        if (
            not any(model.is_alive for model in component.unit.own_models)
            or battlefield.unit_placement_or_none(component.unit.unit_instance_id) is None
        ):
            continue
        if target_within_shooting_selection_range(
            scenario=scenario,
            attacking_unit_instance_id=component.unit.unit_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            max_range_inches=18,
        ):
            range_components.append(component.unit.unit_instance_id)
        if unit_has_line_of_sight_to_target(
            state=state,
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            observing_unit=component.unit,
            target_unit_id=target.unit_instance_id,
            terrain_features=battlefield.terrain_features,
            terrain_areas=terrain_areas,
        ):
            los_components.append(component.unit.unit_instance_id)
    placed_ids = set(battlefield.placed_model_ids())
    return MissionActionSurveilTargetEvidence(
        target_rules_unit_instance_id=target.unit_instance_id,
        target_rules_unit_identity_ids=tuple(
            sorted(rules_unit_identity_ids(state=state, unit_instance_id=target.unit_instance_id))
        ),
        target_owner_player_id=target.owner_player_id,
        placed_alive_target_model_instance_ids=tuple(
            sorted(
                model.model_instance_id
                for model in target.own_models
                if model.is_alive and model.model_instance_id in placed_ids
            )
        ),
        observer_component_unit_instance_ids_within_18=tuple(range_components),
        observer_component_unit_instance_ids_with_line_of_sight=tuple(los_components),
        visibility_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=battlefield.terrain_features,
            terrain_areas=terrain_areas,
        ),
    )


def _validate_candidate_identity(
    *,
    state: GameState,
    player_id: str,
    candidate: MissionActionStartCandidateUnitEvidence,
) -> None:
    units = {
        unit.unit_instance_id: unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
    }
    component_ids = candidate.component_unit_instance_ids
    if not set(component_ids) <= set(units):
        raise GameLifecycleError("Primary Mission Action start candidate inventory drifted.")
    _validate_historical_rules_unit_identity(
        state=state,
        player_id=player_id,
        rules_unit_instance_id=candidate.unit_instance_id,
        component_unit_instance_ids=component_ids,
        unit_identity_ids=candidate.unit_identity_ids,
    )
    model_ids = {
        model.model_instance_id
        for component_id in component_ids
        for model in units[component_id].own_models
    }
    alive_ids = set(candidate.alive_model_instance_ids)
    alive_component_ids = {
        component_id
        for component_id in component_ids
        if any(model.model_instance_id in alive_ids for model in units[component_id].own_models)
    }
    expected_keywords = {
        _canonical_keyword(keyword)
        for component_id in alive_component_ids
        for keyword in units[component_id].keywords
    }
    if (
        not alive_ids <= model_ids
        or not set(candidate.placed_alive_model_instance_ids) <= alive_ids
        or not set(candidate.positive_objective_control_model_instance_ids)
        <= set(candidate.placed_alive_model_instance_ids)
        or set(candidate.keyword_tokens) != expected_keywords
    ):
        raise GameLifecycleError("Primary Mission Action start candidate inventory drifted.")
    witness = candidate.objective_proximity_witness
    if (
        witness.rules_unit_instance_id != candidate.unit_instance_id
        or tuple(sorted(witness.component_unit_instance_ids)) != component_ids
        or any(
            not set(item.model_instance_ids) <= set(candidate.placed_alive_model_instance_ids)
            for item in witness.objective_marker_witnesses
        )
    ):
        raise GameLifecycleError(
            "Primary Mission Action start candidate objective inventory drifted."
        )
    surveil_by_id = {
        row.target_rules_unit_instance_id: row for row in candidate.surveil_target_evidence
    }
    enemy_units = {
        unit.unit_instance_id: (army.player_id, unit)
        for army in state.army_definitions
        if army.player_id != player_id
        for unit in army.units
    }
    seen_enemy_components: set[str] = set()
    for row in surveil_by_id.values():
        target_components = tuple(
            value
            for value in row.target_rules_unit_identity_ids
            if value != row.target_rules_unit_instance_id
        ) or (row.target_rules_unit_instance_id,)
        if not set(target_components).isdisjoint(seen_enemy_components) or not set(
            target_components
        ) <= set(enemy_units):
            raise GameLifecycleError(
                "Primary Mission Action start candidate Surveil inventory drifted."
            )
        seen_enemy_components.update(target_components)
        owners = {enemy_units[component_id][0] for component_id in target_components}
        if len(owners) != 1:
            raise GameLifecycleError(
                "Primary Mission Action start candidate Surveil inventory drifted."
            )
        target_owner = next(iter(owners))
        _validate_historical_rules_unit_identity(
            state=state,
            player_id=target_owner,
            rules_unit_instance_id=row.target_rules_unit_instance_id,
            component_unit_instance_ids=target_components,
            unit_identity_ids=row.target_rules_unit_identity_ids,
        )
        target_model_ids = {
            model.model_instance_id
            for component_id in target_components
            for model in enemy_units[component_id][1].own_models
        }
        if (
            row.target_owner_player_id != target_owner
            or not set(row.placed_alive_target_model_instance_ids) <= target_model_ids
            or not set(row.observer_component_unit_instance_ids_within_18) <= set(component_ids)
            or not set(row.observer_component_unit_instance_ids_with_line_of_sight)
            <= set(component_ids)
        ):
            raise GameLifecycleError(
                "Primary Mission Action start candidate Surveil inventory drifted."
            )
    if seen_enemy_components != set(enemy_units):
        raise GameLifecycleError(
            "Primary Mission Action start candidate Surveil inventory drifted."
        )


def _validate_candidate_boundary_facts(
    *,
    state: GameState,
    authority: MissionActionStartAuthorityEvidence,
    candidate: MissionActionStartCandidateUnitEvidence,
) -> None:
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=candidate.unit_instance_id)
    rows = tuple(
        row
        for row in authority.terrain_model_inventory
        if row.component_unit_instance_id in candidate.component_unit_instance_ids
    )
    alive_ids = tuple(
        sorted(row.model_instance_id for row in rows if row.wounds_remaining_at_boundary > 0)
    )
    placed_ids = tuple(
        sorted(
            row.model_instance_id
            for row in rows
            if row.wounds_remaining_at_boundary > 0 and row.model_placement_json is not None
        )
    )
    positive_ids = tuple(
        sorted(
            row.model_instance_id
            for row in rows
            if row.model_instance_id in placed_ids
            and (
                resolved := CharacteristicValue.from_payload(
                    cast(
                        CharacteristicValuePayload,
                        _json_object(row.resolved_objective_control_json),
                    )
                )
            ).is_numeric
            and resolved.final > 0
        )
    )
    state_unit_ids = {
        candidate.unit_instance_id,
        *candidate.component_unit_instance_ids,
    }
    expected_surveillance = tuple(
        _capture_surveil_target(state=state, observer=rules_unit, target=target)
        for target in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if target.owner_player_id != rules_unit.owner_player_id
    )
    actual = (
        candidate.alive_model_instance_ids,
        candidate.placed_alive_model_instance_ids,
        candidate.positive_objective_control_model_instance_ids,
        candidate.keyword_tokens,
        candidate.battle_shocked,
        candidate.within_enemy_engagement_range,
        candidate.advanced_unit_instance_ids,
        candidate.fell_back_unit_instance_ids,
        candidate.shot_unit_instance_ids,
        candidate.objective_proximity_witness,
        candidate.surveil_target_evidence,
    )
    expected = (
        alive_ids,
        placed_ids,
        positive_ids,
        tuple(sorted(_canonical_keyword(value) for value in rules_unit.keywords)),
        rules_unit_is_battle_shocked(state=state, unit_instance_id=rules_unit.unit_instance_id),
        bool(placed_ids)
        and unit_within_enemy_engagement_range(
            state=state, unit_instance_id=rules_unit.unit_instance_id
        ),
        tuple(sorted(state_unit_ids.intersection(authority.advanced_unit_instance_ids))),
        tuple(sorted(state_unit_ids.intersection(authority.fell_back_unit_instance_ids))),
        tuple(sorted(state_unit_ids.intersection(authority.shot_unit_instance_ids))),
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        ),
        expected_surveillance,
    )
    field_names = (
        "alive models",
        "placed models",
        "positive Objective Control models",
        "keywords",
        "Battle-shock",
        "Engagement Range",
        "Advanced units",
        "Fell Back units",
        "shot units",
        "objective proximity",
        "Surveil targets",
    )
    for field_name, actual_value, expected_value in zip(field_names, actual, expected, strict=True):
        if actual_value != expected_value:
            raise GameLifecycleError(
                f"Primary Mission Action start candidate boundary inventory drifted ({field_name})."
            )


def _boundary_game_state(
    *, state: GameState, evidence: PrimaryMissionActionStartEvidence
) -> GameState:
    authority = evidence.start_authority
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary Mission Action authority requires battlefield state.")
    boundary = authority.battlefield_boundary
    clone = deepcopy(state)
    marker_by_id = {
        marker.marker_id: marker for marker in state.primary_mission_progress_state.markers
    }
    if not set(evidence.active_primary_mission_marker_ids) <= set(marker_by_id):
        raise GameLifecycleError("Primary Mission Action start marker inventory drifted.")
    clone.primary_mission_progress_state = replace(
        clone.primary_mission_progress_state,
        markers=tuple(
            replace(
                marker_by_id[marker_id],
                status=PrimaryMissionMarkerStatus.ACTIVE,
                removed_battle_round=None,
                removed_phase=None,
                removed_active_player_id=None,
                removal_source_id=None,
                removal_event_id=None,
                removal_result_id=None,
                removal_action_id=None,
            )
            for marker_id in evidence.active_primary_mission_marker_ids
        ),
    )
    row_by_model_id = {row.model_instance_id: row for row in authority.terrain_model_inventory}
    groups_by_player: dict[str, list[tuple[str, tuple[str, ...]]]] = {
        player_id: [] for player_id in state.player_ids
    }
    groups_by_player[evidence.player_id].extend(
        (candidate.unit_instance_id, candidate.component_unit_instance_ids)
        for candidate in authority.candidate_units
    )
    opponents = tuple(
        player_id for player_id in state.player_ids if player_id != evidence.player_id
    )
    if len(opponents) != 1 or not authority.candidate_units:
        raise GameLifecycleError("Primary Mission Action authority opponent inventory drifted.")
    groups_by_player[opponents[0]].extend(
        (
            row.target_rules_unit_instance_id,
            tuple(
                value
                for value in row.target_rules_unit_identity_ids
                if value != row.target_rules_unit_instance_id
            )
            or (row.target_rules_unit_instance_id,),
        )
        for row in authority.candidate_units[0].surveil_target_evidence
    )
    acted_ids = {
        *authority.advanced_unit_instance_ids,
        *authority.fell_back_unit_instance_ids,
        *authority.shot_unit_instance_ids,
    }
    acted_component_ids = {
        component_id
        for groups in groups_by_player.values()
        for rules_unit_id, component_ids in groups
        if acted_ids.intersection({rules_unit_id, *component_ids})
        for component_id in component_ids
    }
    rebuilt_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        rebuilt_units = tuple(
            replace(
                unit,
                own_models=tuple(
                    _boundary_model(
                        model=model,
                        row=row_by_model_id[model.model_instance_id],
                        force_zero_objective_control=(unit.unit_instance_id in acted_component_ids),
                    )
                    for model in unit.own_models
                ),
            )
            for unit in army.units
        )
        attached: list[AttachedUnitFormation] = []
        for rules_unit_id, component_ids in groups_by_player[army.player_id]:
            if len(component_ids) == 1:
                continue
            matches = tuple(
                record
                for record in state.starting_attached_unit_records
                if record.player_id == army.player_id
                and record.attached_unit_instance_id == rules_unit_id
                and record.component_unit_instance_ids == component_ids
            )
            if len(matches) != 1:
                raise GameLifecycleError(
                    "Primary Mission Action historical rules-unit inventory drifted."
                )
            record = matches[0]
            attached.append(
                AttachedUnitFormation(
                    attached_unit_instance_id=record.attached_unit_instance_id,
                    bodyguard_unit_instance_id=record.bodyguard_unit_instance_id,
                    leader_unit_instance_ids=record.leader_unit_instance_ids,
                    support_unit_instance_ids=record.support_unit_instance_ids,
                    component_unit_instance_ids=record.component_unit_instance_ids,
                    source_id=record.source_id,
                    attachment_source_ids=(record.source_id,),
                )
            )
        rebuilt_armies.append(replace(army, units=rebuilt_units, attached_units=tuple(attached)))
    clone.army_definitions = rebuilt_armies
    placement_by_unit: dict[tuple[str, str, str], list[ModelPlacement]] = {}
    for row in authority.terrain_model_inventory:
        if row.model_placement_json is None:
            continue
        placement = ModelPlacement.from_payload(
            cast(ModelPlacementPayload, _json_object(row.model_placement_json))
        )
        placement_by_unit.setdefault(
            (placement.army_id, placement.player_id, placement.unit_instance_id), []
        ).append(placement)
    placed_armies: list[PlacedArmy] = []
    for army in rebuilt_armies:
        unit_placements = tuple(
            UnitPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit_id,
                model_placements=tuple(placements),
            )
            for (army_id, player_id, unit_id), placements in sorted(placement_by_unit.items())
            if army_id == army.army_id
        )
        if unit_placements:
            placed_armies.append(
                PlacedArmy(
                    army_id=army.army_id,
                    player_id=army.player_id,
                    unit_placements=unit_placements,
                )
            )
    clone.battlefield_state = BattlefieldRuntimeState(
        battlefield_id=boundary.battlefield_id,
        battlefield_width_inches=boundary.battlefield_width_inches,
        battlefield_depth_inches=boundary.battlefield_depth_inches,
        placed_armies=tuple(placed_armies),
        terrain_features=boundary.terrain_features,
        removed_model_ids=tuple(
            sorted(
                row.model_instance_id
                for row in authority.terrain_model_inventory
                if row.wounds_remaining_at_boundary == 0
            )
        ),
    )
    clone.battle_shocked_unit_ids = list(authority.battle_shocked_unit_instance_ids)
    clone.active_player_id = evidence.active_player_id
    clone.battle_round = evidence.battle_round
    clone.battle_phase_index = clone.battle_phase_sequence.index(BattlePhase.SHOOTING)
    prior_action_ids = {row.action_id for row in evidence.prior_uses}
    clone.mission_action_states = [
        action for action in clone.mission_action_states if action.action_id in prior_action_ids
    ]
    clone.advanced_unit_states = []
    clone.fell_back_unit_states = []
    from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState

    clone.shooting_phase_state = ShootingPhaseState(
        battle_round=evidence.battle_round,
        active_player_id=evidence.active_player_id,
        shot_unit_ids=authority.shot_unit_instance_ids,
    )
    clone.secondary_mission_card_states = [
        (
            replace(
                card,
                status=SecondaryMissionCardStatus.ACTIVE,
                scored_transaction_id=None,
                discarded_result_id=None,
            )
            if card.player_id == evidence.player_id
            else card
        )
        for card in clone.secondary_mission_card_states
        if card.player_id != evidence.player_id
        or card.secondary_mission_id in authority.active_secondary_mission_ids
    ]
    if set(authority.active_secondary_mission_ids) != {
        card.secondary_mission_id
        for card in clone.secondary_mission_card_states
        if card.player_id == evidence.player_id and card.status is SecondaryMissionCardStatus.ACTIVE
    }:
        raise GameLifecycleError("Primary Mission Action secondary-action authority drifted.")
    return clone


def _validate_battlefield_boundary(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
) -> None:
    setup = state.mission_setup
    battlefield = state.battlefield_state
    if setup is None or battlefield is None:
        raise GameLifecycleError("Primary Mission Action battlefield boundary is unavailable.")
    boundary = evidence.start_authority.battlefield_boundary
    boundary_values = (
        boundary.battlefield_id,
        boundary.battlefield_width_inches,
        boundary.battlefield_depth_inches,
        boundary.terrain_features,
    )
    current_values = (
        battlefield.battlefield_id,
        battlefield.battlefield_width_inches,
        battlefield.battlefield_depth_inches,
        battlefield.terrain_features,
    )
    setup_values = (
        setup.battlefield_width_inches,
        setup.battlefield_depth_inches,
        setup.terrain_features,
    )
    if boundary_values != current_values or current_values[1:] != setup_values:
        raise GameLifecycleError("Primary Mission Action battlefield boundary drifted.")


def _boundary_model(
    *,
    model: ModelInstance,
    row: MissionActionTerrainModelInventoryEvidence,
    force_zero_objective_control: bool,
) -> ModelInstance:
    resolved = CharacteristicValue.from_payload(
        cast(
            CharacteristicValuePayload,
            _json_object(row.resolved_objective_control_json),
        )
    )
    if force_zero_objective_control:
        resolved = replace(resolved, final=0)
    return replace(
        model,
        wounds_remaining=row.wounds_remaining_at_boundary,
        characteristics=tuple(
            resolved if value.characteristic is Characteristic.OBJECTIVE_CONTROL else value
            for value in model.characteristics
        ),
    )


def _validate_historical_rules_unit_identity(
    *,
    state: GameState,
    player_id: str,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
    unit_identity_ids: tuple[str, ...],
) -> None:
    components = tuple(sorted(component_unit_instance_ids))
    if len(components) == 1 and rules_unit_instance_id == components[0]:
        valid = True
    else:
        valid = any(
            record.player_id == player_id
            and record.attached_unit_instance_id == rules_unit_instance_id
            and tuple(sorted(record.component_unit_instance_ids)) == components
            for record in state.starting_attached_unit_records
        )
    if not valid or unit_identity_ids != tuple(sorted({rules_unit_instance_id, *components})):
        raise GameLifecycleError("Primary Mission Action historical rules-unit inventory drifted.")


def _allowed_rules_unit_ids_for_component(
    *, state: GameState, player_id: str, component_unit_instance_id: str
) -> frozenset[str]:
    return frozenset(
        {
            component_unit_instance_id,
            *(
                record.attached_unit_instance_id
                for record in state.starting_attached_unit_records
                if record.player_id == player_id
                and component_unit_instance_id in record.component_unit_instance_ids
            ),
        }
    )


def _relevant_primary_actions(
    *, state: GameState, evidence: PrimaryMissionActionStartEvidence
) -> tuple[tuple[MissionActionDefinition, MissionActionPolicyDescriptor], ...]:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action authority requires MissionSetup.")
    policies = {policy.mission_action_id: policy for policy in mission_action_policy_descriptors()}
    pack = mission_pack_for_id(setup.mission_pack_id)
    assigned_id = setup.primary_mission_id_for_player(evidence.player_id)
    available = tuple(
        action
        for action in pack.mission_actions
        if action.mission_kind == "primary"
        and action.mission_id == assigned_id
        and action.mission_action_id in policies
    )
    request = _json_object(evidence.start_authority.request_payload_json)
    if evidence.start_authority.request_kind == "direct":
        requested_id = _required_string(request, "mission_action_id")
        available = tuple(
            action for action in available if action.mission_action_id == requested_id
        )
    if not available or evidence.mission_action_id not in {
        action.mission_action_id for action in available
    }:
        raise GameLifecycleError(
            "Primary Mission Action complete start authority inventory drifted."
        )
    return tuple((action, policies[action.mission_action_id]) for action in available)


def _candidate_targets(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
    candidate: MissionActionStartCandidateUnitEvidence,
    policy: MissionActionPolicyDescriptor,
    terrain_inventory: tuple[MissionActionTerrainModelInventoryEvidence, ...],
) -> tuple[str, ...]:
    if (
        _candidate_ineligibility_reason(candidate=candidate, evidence=evidence)
        != candidate.unit_ineligibility_reason
    ):
        raise GameLifecycleError(
            "Primary Mission Action start candidate eligibility inventory drifted."
        )
    if candidate.unit_ineligibility_reason is not None:
        return ()
    if (
        policy.start_timing == "shooting_phase_action_start_from_battle_round_two"
        and evidence.battle_round < 2
    ):
        return ()
    matching_prior = tuple(
        prior
        for prior in evidence.prior_uses
        if prior.player_id == evidence.player_id
        and prior.mission_action_id == policy.mission_action_id
        and prior.battle_round_started == evidence.battle_round
    )
    if policy.use_limit == "once_per_turn" and matching_prior:
        return ()
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action authority requires MissionSetup.")
    witness_by_objective = {
        item.objective_marker_id: item
        for item in candidate.objective_proximity_witness.objective_marker_witnesses
    }
    positive_ids = set(candidate.positive_objective_control_model_instance_ids)
    proximate_ids = {
        objective_id
        for objective_id, witness in witness_by_objective.items()
        if positive_ids.intersection(witness.model_instance_ids)
    }
    home_ids = set(home_objective_ids(setup, player_id=evidence.player_id))
    central_ids = {
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    }
    terrain_ids = {
        area_id
        for row in terrain_inventory
        if row.rules_unit_instance_id == candidate.unit_instance_id
        and row.component_unit_instance_id in candidate.component_unit_instance_ids
        for area_id in row.logical_terrain_area_ids
    }
    if policy.eligible_unit_policy == "active_player_unit":
        eligible = True
    elif policy.eligible_unit_policy == "active_player_unit_within_range_of_central_objective":
        eligible = bool(proximate_ids.intersection(central_ids))
    elif policy.eligible_unit_policy == "active_player_unit_within_range_of_non_home_objective":
        eligible = bool(proximate_ids - home_ids)
    elif policy.eligible_unit_policy == "active_player_unit_within_terrain_area_in_enemy_territory":
        eligible = bool(terrain_ids.intersection(evidence.enemy_territory_logical_terrain_area_ids))
    else:
        raise GameLifecycleError("Primary Mission Action eligible-unit policy is unsupported.")
    if not eligible:
        return ()
    if policy.target_policy == "terrain_area_in_enemy_territory":
        targets = terrain_ids.intersection(evidence.enemy_territory_logical_terrain_area_ids)
    elif policy.target_policy == "visible_enemy_unit_within_18_not_surveilled_this_turn":
        targets = {
            row.target_rules_unit_instance_id
            for row in candidate.surveil_target_evidence
            if row.placed_alive_target_model_instance_ids
            and row.observer_component_unit_instance_ids_within_18
            and row.observer_component_unit_instance_ids_with_line_of_sight
            and not _surveilled_in_prior_uses(row=row, evidence=evidence)
        }
    else:
        targets = _objective_targets_from_facts(
            state=state,
            evidence=evidence,
            policy=policy,
            proximate_ids=proximate_ids,
            central_ids=central_ids,
            home_ids=home_ids,
        )
    if policy.use_limit == "unlimited_different_objective_per_unit_this_phase":
        targets = {
            target_id
            for target_id in targets
            if not any(
                prior.phase_started == evidence.phase
                and (
                    not set(prior.unit_identity_ids).isdisjoint(candidate.unit_identity_ids)
                    or prior.target_id == target_id
                )
                for prior in matching_prior
            )
        }
    return tuple(sorted(targets))


def _objective_targets_from_facts(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
    policy: MissionActionPolicyDescriptor,
    proximate_ids: set[str],
    central_ids: set[str],
    home_ids: set[str],
) -> set[str]:
    markers = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.marker_id in evidence.active_primary_mission_marker_ids
    )
    if len(markers) != len(evidence.active_primary_mission_marker_ids):
        raise GameLifecycleError("Primary Mission Action start marker inventory drifted.")
    target_policy = policy.target_policy
    if "friendly_operation_marker_requires_more_than_one" in target_policy and (
        sum(
            marker.owner_player_id == evidence.player_id and marker.marker_kind == "operation"
            for marker in markers
        )
        <= 1
    ):
        return set()
    if "opponent_operation_marker_requires_more_than_one" in target_policy and (
        sum(
            marker.owner_player_id != evidence.player_id and marker.marker_kind == "operation"
            for marker in markers
        )
        <= 1
    ):
        return set()
    if target_policy.startswith("central_objective"):
        return proximate_ids.intersection(central_ids)
    targets = proximate_ids - home_ids
    if target_policy == "objective_marker_excluding_home_not_decoy":
        return {
            target_id
            for target_id in targets
            if not any(
                marker.owner_player_id == evidence.player_id
                and marker.mission_id == policy.primary_mission_id
                and marker.objective_marker_id == target_id
                for marker in markers
            )
        }
    if target_policy == "objective_marker_excluding_home_without_friendly_operation_marker":
        return {
            target_id
            for target_id in targets
            if not any(
                marker.owner_player_id == evidence.player_id
                and marker.marker_kind == "operation"
                and marker.objective_marker_id == target_id
                for marker in markers
            )
        }
    if target_policy != "objective_marker_excluding_home":
        raise GameLifecycleError("Primary Mission Action target policy is unsupported.")
    return targets


def _candidate_ineligibility_reason(
    *,
    candidate: MissionActionStartCandidateUnitEvidence,
    evidence: PrimaryMissionActionStartEvidence,
) -> str | None:
    if not candidate.placed_alive_model_instance_ids:
        return MISSION_ACTION_UNIT_OFF_BATTLEFIELD
    if "AIRCRAFT" in candidate.keyword_tokens:
        return MISSION_ACTION_UNIT_AIRCRAFT
    if "FORTIFICATION" in candidate.keyword_tokens:
        return MISSION_ACTION_UNIT_FORTIFICATION
    if candidate.battle_shocked:
        return MISSION_ACTION_UNIT_BATTLE_SHOCKED
    if not candidate.positive_objective_control_model_instance_ids:
        return MISSION_ACTION_UNIT_ZERO_OBJECTIVE_CONTROL
    if candidate.within_enemy_engagement_range and "TITANIC" not in candidate.keyword_tokens:
        return MISSION_ACTION_UNIT_ENGAGED
    if candidate.advanced_unit_instance_ids:
        return MISSION_ACTION_UNIT_ADVANCED
    if candidate.fell_back_unit_instance_ids:
        return MISSION_ACTION_UNIT_FELL_BACK
    if candidate.shot_unit_instance_ids:
        return MISSION_ACTION_UNIT_ALREADY_SHOT
    if any(
        prior.player_id == evidence.player_id
        and prior.battle_round_started == evidence.battle_round
        and not set(prior.unit_identity_ids).isdisjoint(candidate.unit_identity_ids)
        for prior in evidence.prior_uses
    ):
        return MISSION_ACTION_UNIT_ALREADY_STARTED_ACTION
    return None


def _surveilled_in_prior_uses(
    *, row: MissionActionSurveilTargetEvidence, evidence: PrimaryMissionActionStartEvidence
) -> bool:
    return any(
        prior.player_id == evidence.player_id
        and prior.mission_action_id == "surveil-enemy-unit"
        and prior.battle_round_started == evidence.battle_round
        and not set(prior.target_rules_unit_identity_ids).isdisjoint(
            row.target_rules_unit_identity_ids
        )
        for prior in evidence.prior_uses
    )


def _primary_option_ids_by_unit(
    authority: MissionActionStartAuthorityEvidence,
) -> dict[str, tuple[str, ...]]:
    policy_ids = {policy.mission_action_id for policy in mission_action_policy_descriptors()}
    rows: dict[str, list[str]] = {}
    for option in authority.options:
        payload = _json_object(option.payload_json)
        action_id = payload.get("mission_action_id")
        unit_id = payload.get("unit_instance_id")
        if action_id in policy_ids and type(unit_id) is str:
            rows.setdefault(unit_id, []).append(option.option_id)
    return {unit_id: tuple(sorted(option_ids)) for unit_id, option_ids in rows.items()}


def _json_object(value: str) -> dict[str, object]:
    decoded: object = json.loads(value)
    if type(decoded) is not dict:
        raise GameLifecycleError("Primary Mission Action authority payload is invalid.")
    mapping = cast(dict[object, object], decoded)
    if any(type(key) is not str for key in mapping):
        raise GameLifecycleError("Primary Mission Action authority payload is invalid.")
    return cast(dict[str, object], mapping)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(
            "Primary Mission Action complete start authority inventory drifted."
        )
    return value


def _canonical_keyword(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").upper()


__all__ = (
    "capture_primary_mission_action_start_authority",
    "capture_primary_mission_action_terrain_model_inventory",
    "terrain_intersections_from_model_inventory",
    "validate_primary_mission_action_start_authority",
    "validate_primary_mission_action_terrain_model_inventory",
)
