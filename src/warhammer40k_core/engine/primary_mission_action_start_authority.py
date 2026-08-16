from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import (
    CharacteristicValue,
    CharacteristicValuePayload,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    ModelPlacementPayload,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.mission_terrain import (
    mission_logical_terrain_areas,
    model_intersects_logical_terrain_area,
)
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_identity_authority import (
    allowed_rules_unit_ids_for_component,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionTerrainIntersectionEvidence,
    MissionActionTerrainModelInventoryEvidence,
    PrimaryMissionActionStartEvidence,
    canonical_terrain_intersections,
    canonical_terrain_model_inventory,
)
from warhammer40k_core.engine.primary_mission_objective_control_authority import (
    resolve_checkpoint_objective_control,
)
from warhammer40k_core.engine.rules_units import rules_unit_id_for_unit_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_factory import ModelInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_primary_mission_action_start_authority(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
) -> None:
    """Validate the request against its authenticated boundary checkpoint."""

    from warhammer40k_core.engine.primary_mission_boundary_state import (
        validate_checkpoint_backed_primary_mission_action_start_authority,
    )

    validate_checkpoint_backed_primary_mission_action_start_authority(
        state=state,
        evidence=evidence,
    )


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
                resolved_oc = resolve_checkpoint_objective_control(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    model=model,
                    runtime_modifier_registry=runtime_modifier_registry,
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
            not in allowed_rules_unit_ids_for_component(
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


__all__ = (
    "capture_primary_mission_action_terrain_model_inventory",
    "terrain_intersections_from_model_inventory",
    "validate_primary_mission_action_start_authority",
    "validate_primary_mission_action_terrain_model_inventory",
)
