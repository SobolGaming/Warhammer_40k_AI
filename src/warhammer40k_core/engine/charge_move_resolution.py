from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aircraft import (
    AircraftMovementPolicy,
    aircraft_model_ids_for_scenario,
)
from warhammer40k_core.engine.aircraft_rules import (
    AIRCRAFT_INGRESS_ONLY,
    aircraft_movement_target_allowed,
    aircraft_rules_unit,
)
from warhammer40k_core.engine.base_contact_authority import contacts_for_validated_move
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_endpoints import (
    ChargeEndpointWitness,
    _charge_endpoint_violation_code,
    _charge_endpoint_witness,
)
from warhammer40k_core.engine.charge_model_endpoints import (
    ChargeModelPathContext,
    charge_endpoint_query,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _charge_move_transition_batch,
    _enemy_geometry_models_for_player,
    _friendly_geometry_models_for_charge_path,
    _friendly_vehicle_monster_model_ids,
    _geometry_models_for_unit_placement,
    _terrain_volumes_for_features,
    _validate_charge_witness_matches_unit,
    _validate_json_object,
    _validate_path_validation_results,
    _validate_terrain_path_legality_results,
)
from warhammer40k_core.engine.charge_movement_source import (
    ChargePlacement,
    charge_attempted_placement,
    charge_movement_placement,
    charge_placement_id,
)
from warhammer40k_core.engine.charge_phase_state import (
    _validate_identifier_tuple,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.charge_rule_effects import (
    charge_path_context_with_rule_effect_permissions,
    enemy_vehicle_monster_model_ids_for_player,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
    scenario_physical_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyContext,
    UnitCoherencyResult,
    resolve_unit_movement_endpoint_coherency,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.terrain import TerrainVolume

_validate_identifier = IdentifierValidator(GameLifecycleError)
CHARGE_MOVE_ACTION = "charge_move"


@dataclass(frozen=True, slots=True)
class ChargeMoveResolution:
    unit_instance_id: str
    selected_target_unit_instance_ids: tuple[str, ...]
    attempted_placement: ChargePlacement
    witness: PathWitness
    endpoint_witness: ChargeEndpointWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]
    endpoint_violation_code: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ChargeMoveResolution unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "selected_target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeMoveResolution selected_target_unit_instance_ids",
                self.selected_target_unit_instance_ids,
            ),
        )
        if type(self.attempted_placement) not in {UnitPlacement, RulesUnitPlacement}:
            raise GameLifecycleError(
                "ChargeMoveResolution attempted_placement must be UnitPlacement."
            )
        if charge_placement_id(self.attempted_placement) != self.unit_instance_id:
            raise GameLifecycleError("ChargeMoveResolution attempted_placement unit drift.")
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("ChargeMoveResolution witness must be a PathWitness.")
        if type(self.endpoint_witness) is not ChargeEndpointWitness:
            raise GameLifecycleError(
                "ChargeMoveResolution endpoint_witness must be ChargeEndpointWitness."
            )
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_results(self.path_validation_results),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_results(self.terrain_path_legality_results),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "ChargeMoveResolution coherency_result must be UnitCoherencyResult."
            )
        if (
            self.rollback_record is not None
            and type(self.rollback_record) is not MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "ChargeMoveResolution rollback_record must be MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object("ChargeMoveResolution movement_payload", self.movement_payload),
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
            and self.coherency_result.is_coherent
            and self.endpoint_violation_code is None
        )

    def transition_batch(self, *, before: ChargePlacement) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Charge Move cannot emit displacement records.")
        return _charge_move_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
        )


def resolve_charge_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: ChargePlacement,
    selected_target_unit_instance_ids: tuple[str, ...],
    maximum_distance_inches: float,
    path_witness: PathWitness,
    terrain: tuple[TerrainVolume, ...] = (),
    unit_persisting_effects: tuple[PersistingEffect, ...] = (),
    ability_index: AbilityCatalogIndex | None = None,
    take_to_the_skies: bool = False,
) -> ChargeMoveResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Charge Move requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Charge Move requires a RulesetDescriptor.")
    if type(unit_placement) not in {UnitPlacement, RulesUnitPlacement}:
        raise GameLifecycleError("Charge Move unit_placement must be a UnitPlacement.")
    if type(path_witness) is not PathWitness:
        raise GameLifecycleError("Charge Move requires a PathWitness.")
    if (
        type(maximum_distance_inches) not in {int, float}
        or not isfinite(maximum_distance_inches)
        or maximum_distance_inches < 0
    ):
        raise GameLifecycleError("Charge Move maximum distance must be finite and nonnegative.")
    target_ids = _validate_identifier_tuple(
        "selected_target_unit_instance_ids",
        selected_target_unit_instance_ids,
    )
    _validate_charge_witness_matches_unit(
        witness=path_witness,
        unit_placement=unit_placement,
    )
    unit_id = charge_placement_id(unit_placement)
    canonical = charge_movement_placement(scenario=scenario, unit_instance_id=unit_id)
    if canonical != unit_placement:
        raise GameLifecycleError(
            "Charge Move source placement drifted from current living rules unit."
        )
    enemy_ids = scenario_physical_enemy_rules_unit_ids(scenario=scenario, unit_instance_id=unit_id)
    if not set(target_ids) <= set(enemy_ids):
        raise GameLifecycleError("Charge targets require canonical battlefield enemy identities.")
    charging_unit = aircraft_rules_unit(scenario, unit_id)
    if "AIRCRAFT" in charging_unit.keywords:
        raise GameLifecycleError(AIRCRAFT_INGRESS_ONLY)
    if any(
        not aircraft_movement_target_allowed(charging_unit, aircraft_rules_unit(scenario, target))
        for target in target_ids
    ):
        raise GameLifecycleError("aircraft_charge_target_requires_fly")
    for placement in unit_placement.model_placements:
        if path_witness.poses_for_model(placement.model_instance_id)[0] != placement.pose:
            raise GameLifecycleError("Charge Move witness start drifted from current placement.")
    attempted_placement = charge_attempted_placement(unit_placement, path_witness)
    targets = {
        target_id: physical_geometry_models_for_rules_unit(
            scenario=scenario, unit_instance_id=target_id
        )
        for target_id in target_ids
    }
    non_targets = tuple(
        physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=target_id)
        for target_id in scenario_physical_enemy_rules_unit_ids(
            scenario=scenario, unit_instance_id=unit_id
        )
        if target_id not in target_ids
    )
    after_models = _geometry_models_for_unit_placement(
        scenario=scenario, unit_placement=attempted_placement
    )
    model_contexts: dict[str, ChargeModelPathContext] = {}
    aircraft_policies: list[AircraftMovementPolicy] = []
    terrain_features = scenario.battlefield_state.terrain_features
    terrain_volumes = (*terrain, *_terrain_volumes_for_features(terrain_features))
    path_validation_results: list[PathValidationResult] = []
    terrain_path_legality_results: list[TerrainPathLegalityResult] = []
    model_movements: list[JsonValue] = []
    enemy_vehicle_monster_model_ids = enemy_vehicle_monster_model_ids_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    for placement in unit_placement.model_placements:
        unit = scenario.army_by_id(placement.army_id).unit_by_id(placement.unit_instance_id)
        aircraft_policy = AircraftMovementPolicy.from_unit(
            unit=unit,
            ruleset_descriptor=ruleset_descriptor,
        )
        aircraft_policies.append(aircraft_policy)
        model = scenario.model_instance_for_placement(placement)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            (
                (
                    placement.model_instance_id,
                    path_witness.poses_for_model(placement.model_instance_id),
                ),
            )
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=aircraft_policy.effective_keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=MovementMode.CHARGE,
            take_to_the_skies=take_to_the_skies,
            movement_phase_action=None,
            displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
            ability_index=ability_index,
            unit=unit,
            model_instance_id=placement.model_instance_id,
            current_model_instance_ids=tuple(
                model_placement.model_instance_id
                for model_placement in unit_placement.model_placements
                if model_placement.unit_instance_id == placement.unit_instance_id
            ),
            unit_persisting_effects=unit_persisting_effects,
            owner_player_id=unit_placement.player_id,
        )
        path_context = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_charge_path(
                scenario=scenario,
                unit_placement=unit_placement,
                attempted_placement=attempted_placement,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            terrain=(),
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=unit_placement.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_vehicle_monster_model_ids=enemy_vehicle_monster_model_ids,
            aircraft_model_ids=tuple(
                mid
                for mid in aircraft_model_ids_for_scenario(scenario)
                if mid != placement.model_instance_id
            ),
            movement_distance_budget_inches=float(maximum_distance_inches),
        )
        path_context = charge_path_context_with_rule_effect_permissions(
            path_context,
            unit_persisting_effects=unit_persisting_effects,
            owner_player_id=unit_placement.player_id,
            enemy_vehicle_monster_model_ids=enemy_vehicle_monster_model_ids,
        )
        path_result = path_context.validate()
        terrain_context = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain_volumes,
            terrain_features=terrain_features,
        )
        terrain_result = terrain_context.validate()
        if target_ids:
            model_contexts[placement.model_instance_id] = ChargeModelPathContext(
                component_unit_instance_id=placement.unit_instance_id,
                query=charge_endpoint_query(
                    path_context=path_context,
                    terrain_context=terrain_context,
                    peers=tuple(
                        m for m in after_models if m.model_id != placement.model_instance_id
                    ),
                    targets=targets,
                    non_targets=non_targets,
                    ruleset=ruleset_descriptor,
                ),
            )
        path_result = contacts_for_validated_move(
            path_context=path_context,
            terrain_context=terrain_context,
            path_result=path_result,
            terrain_result=terrain_result,
            query=model_contexts[placement.model_instance_id].query if target_ids else None,
        )
        path_validation_results.append(path_result)
        terrain_path_legality_results.append(terrain_result)
        model_movements.append(
            validate_json_value(
                {
                    "model_instance_id": placement.model_instance_id,
                    "movement_mode": MovementMode.CHARGE.value,
                    "maximum_distance_inches": maximum_distance_inches,
                    "start_pose": placement.pose.to_payload(),
                    "end_pose": path_witness.final_pose_for_model(
                        placement.model_instance_id
                    ).to_payload(),
                    "movement_distance_witness": (
                        None
                        if path_result.movement_distance_witness is None
                        else path_result.movement_distance_witness.to_payload()
                    ),
                    "path_validation_result": path_result.to_payload(),
                    "terrain_path_legality_result": terrain_result.to_payload(),
                }
            )
        )
    rollback_record: MovementRollbackRecord | None = None
    if isinstance(unit_placement, UnitPlacement) and isinstance(attempted_placement, UnitPlacement):
        _, coherency_result, rollback_record = resolve_unit_movement_endpoint_coherency(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            before=unit_placement,
            attempted=attempted_placement,
            displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
        )
    else:
        coherency_result = UnitCoherencyContext.from_ruleset_descriptor(
            ruleset_descriptor, unit_instance_id=unit_id
        ).validate_models(after_models)
    physical_valid = (
        all(result.is_valid for result in path_validation_results)
        and all(result.is_valid for result in terrain_path_legality_results)
        and coherency_result.is_coherent
    )
    endpoint_witness = _charge_endpoint_witness(
        scenario=scenario,
        before=unit_placement,
        after=attempted_placement,
        selected_target_unit_instance_ids=target_ids,
        ruleset_descriptor=ruleset_descriptor,
        model_contexts=model_contexts if physical_valid else {},
    )
    endpoint_violation = _charge_endpoint_violation_code(
        endpoint_witness=endpoint_witness,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=maximum_distance_inches,
    )
    movement_payload = _validate_json_object(
        "ChargeMoveResolution movement_payload",
        {
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": maximum_distance_inches,
            "selected_target_unit_instance_ids": list(target_ids),
            "model_movements": model_movements,
            "path_validation_results": [result.to_payload() for result in path_validation_results],
            "terrain_path_legality_results": [
                result.to_payload() for result in terrain_path_legality_results
            ],
            "coherency_result": coherency_result.to_payload(),
            "endpoint_witness": endpoint_witness.to_payload(),
            "fly_charge_policy": {
                "take_to_the_skies": take_to_the_skies,
                "has_fly": any("FLY" in p.effective_keywords for p in aircraft_policies),
                "uses_aircraft_rules": any(p.uses_aircraft_rules for p in aircraft_policies),
                "can_declare_charge": all(p.can_declare_charge for p in aircraft_policies),
            },
        },
    )
    if rollback_record is not None:
        movement_payload["rollback_record"] = validate_json_value(rollback_record.to_payload())
    return ChargeMoveResolution(
        unit_instance_id=unit_id,
        selected_target_unit_instance_ids=target_ids,
        attempted_placement=attempted_placement,
        witness=path_witness,
        endpoint_witness=endpoint_witness,
        path_validation_results=tuple(path_validation_results),
        terrain_path_legality_results=tuple(terrain_path_legality_results),
        coherency_result=coherency_result,
        rollback_record=rollback_record,
        movement_payload=movement_payload,
        endpoint_violation_code=endpoint_violation,
    )
