"""Bind recorded per-model Charge endpoint evidence to physical event history."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aircraft import AircraftMovementPolicy
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.battlefield_transition_history import (
    authoritative_battlefield_transition_batch_or_none,
)
from warhammer40k_core.engine.charge_model_endpoints import (
    ChargeModelEndpointWitness,
    charge_model_endpoint_witness,
    validate_charge_model_endpoint_inventory,
)
from warhammer40k_core.engine.charge_move_geometry import _hover_mode_state_for_unit
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.fight_model_authority_history import historical_rules_unit_model_ids
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    PhysicalModelAuthority,
    physical_model_authority_before_event,
)
from warhammer40k_core.geometry.movement_reachability import MovementGoal
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance

_CHARGE_COMPLETIONS = frozenset(
    {
        "charge_move_completed",
        "catalog_setup_reactive_charge_move_completed",
    }
)


def validate_charge_endpoint_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    ability_index_for_player: Callable[[str], AbilityCatalogIndex],
) -> None:
    ruleset = state.runtime_ruleset_descriptor()
    identities = {
        model.model_instance_id: (army, unit, model)
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    for index, event in enumerate(event_records):
        if event.event_type not in _CHARGE_COMPLETIONS:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Charge completion requires an object payload.")
        source_id = payload.get("unit_instance_id")
        endpoint = payload.get("endpoint_witness")
        budget = payload.get("maximum_distance_inches")
        if (
            not isinstance(source_id, str)
            or not isinstance(endpoint, dict)
            or type(budget) not in {int, float}
        ):
            raise GameLifecycleError("Charge endpoint historical context is incomplete.")
        selected = endpoint.get("selected_target_unit_instance_ids")
        if (
            not isinstance(selected, list)
            or not selected
            or any(type(t) is not str for t in selected)
        ):
            raise GameLifecycleError("Charge endpoint historical targets are invalid.")
        selected_ids = tuple(cast(list[str], selected))
        transition = authoritative_battlefield_transition_batch_or_none(event=event)
        if transition is None or not transition.displacements:
            raise GameLifecycleError("Charge endpoint history requires physical displacements.")
        paths: list[tuple[str, tuple[Pose, ...]]] = []
        for displacement in transition.displacements:
            if displacement.path_witness is None:
                raise GameLifecycleError("Charge endpoint history requires complete paths.")
            model_id = displacement.model_instance_id
            paths.append((model_id, displacement.path_witness.poses_for_model(model_id)))
        witness = PathWitness.for_paths(tuple(paths))
        rows = validate_charge_model_endpoint_inventory(
            value=endpoint.get("model_endpoints"),
            witness=witness,
            selected_ids=selected_ids,
            ruleset=ruleset,
            maximum_distance_inches=cast(float, budget),
        )
        physical = physical_model_authority_before_event(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            event_index=index,
        )
        geometry: dict[str, Model] = {}
        living: set[str] = set()
        for physical_row in physical:
            if physical_row.presence not in {"battlefield", "retained_destroyed"}:
                continue
            if physical_row.pose is None or physical_row.model_instance_id not in identities:
                raise GameLifecycleError("Charge historical geometry is incomplete.")
            army, unit, model = identities[physical_row.model_instance_id]
            geometry[model.model_instance_id] = geometry_model_for_placement(
                model=model,
                placement=ModelPlacement(
                    army_id=army.army_id,
                    player_id=army.player_id,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=physical_row.pose,
                    split_origin=unit.split_origin,
                ),
            )
            if physical_row.presence == "battlefield":
                living.add(model.model_instance_id)
        source_ids = (
            historical_rules_unit_model_ids(
                state=state,
                event_records=event_records,
                unit_instance_id=source_id,
            )
            & living
        )
        if source_ids != frozenset(witness.model_ids()):
            raise GameLifecycleError("Charge historical living-model inventory drifted.")
        targets = {
            target: tuple(
                geometry[model_id]
                for model_id in sorted(
                    historical_rules_unit_model_ids(
                        state=state,
                        event_records=event_records,
                        unit_instance_id=target,
                    )
                    & geometry.keys()
                )
            )
            for target in selected_ids
        }
        if any(not models for models in targets.values()):
            raise GameLifecycleError("Charge historical target geometry is absent.")
        for row in rows:
            start = geometry[row.model_instance_id]
            if start.pose != witness.poses_for_model(row.model_instance_id)[0]:
                raise GameLifecycleError("Charge historical path start drifted.")
            component_id = identities[row.model_instance_id][1].unit_instance_id
            expected = charge_model_endpoint_witness(
                start=start,
                end=replace(start, pose=witness.final_pose_for_model(start.model_id)),
                targets=targets,
                ruleset=ruleset,
                context=None,
                component_unit_instance_id=component_id,
            )
            if (
                row.component_unit_instance_id != component_id
                or row.target_distances_before_inches != expected.target_distances_before_inches
                or row.target_distances_after_inches != expected.target_distances_after_inches
                or row.engaged_target_unit_instance_ids != expected.engaged_target_unit_instance_ids
                or row.preferred_distance_target_unit_instance_ids
                != expected.preferred_distance_target_unit_instance_ids
            ):
                raise GameLifecycleError("Charge historical per-model endpoint geometry drifted.")
            if not any(
                evidence.status == "unreachable"
                for evidence in (row.preferred_reachability, row.engagement_reachability)
            ):
                continue
            army, unit, _ = identities[row.model_instance_id]
            unit_at_charge = charge_component_at_physical_boundary(unit=unit, physical=physical)
            aircraft = AircraftMovementPolicy.from_unit(
                unit=unit_at_charge,
                ruleset_descriptor=ruleset,
                hover_mode_state=_hover_mode_state_for_unit(
                    hover_mode_states=tuple(state.hover_mode_states),
                    unit_instance_id=component_id,
                ),
            )
            capabilities = MovementCapabilitySet.from_keywords(
                keywords=aircraft.effective_keywords,
                ruleset_descriptor=ruleset,
                ability_index=ability_index_for_player(army.player_id),
                movement_mode=MovementMode.CHARGE,
                unit=unit_at_charge,
                model_instance_id=row.model_instance_id,
                current_model_instance_ids=tuple(
                    model_id
                    for model_id in sorted(source_ids)
                    if identities[model_id][1].unit_instance_id == component_id
                ),
            )
            validate_charge_model_reachability_bounds(
                row=row,
                start=start,
                targets=targets,
                ruleset=ruleset,
                capabilities=capabilities,
            )


def charge_component_at_physical_boundary(
    *, unit: UnitInstance, physical: tuple[PhysicalModelAuthority, ...]
) -> UnitInstance:
    """Recover the component's event-bound living keyword and catalog-source inventory.

    Keyword assignments are immutable source data, but UnitInstance unions only
    living models. Use authenticated historical wounds; neither current casualties
    nor models materialized after the event may change the earlier capabilities.
    This snapshot is never installed in authoritative game state.
    """
    by_model_id = {row.model_instance_id: row for row in physical}
    models = tuple(
        replace(model, wounds_remaining=by_model_id[model.model_instance_id].wounds_remaining)
        for model in unit.own_models
        if model.model_instance_id in by_model_id
    )
    if not models:
        raise GameLifecycleError("Charge historical component has no model authority.")
    return replace(unit, own_models=models)


def validate_charge_model_reachability_bounds(
    *,
    row: ChargeModelEndpointWitness,
    start: Model,
    targets: dict[str, tuple[Model, ...]],
    ruleset: RulesetDescriptor,
    capabilities: MovementCapabilitySet,
) -> None:
    # Recompute accepted impossibility proofs with the source-backed movement
    # metric. A flying model cannot claim a larger ground-movement bound.
    target_models = tuple(model for group in targets.values() for model in group)
    for evidence, goal in (
        (
            row.preferred_reachability,
            MovementGoal(
                models=target_models,
                range_inches=ruleset.charge_policy.preferred_target_distance_inches,
            ),
        ),
        (
            row.engagement_reachability,
            MovementGoal(
                models=target_models,
                horizontal_inches=ruleset.engagement_policy.horizontal_inches,
                vertical_inches=ruleset.engagement_policy.vertical_inches,
            ),
        ),
    ):
        if (
            evidence.status == "unreachable"
            and evidence.distance_lower_bound_inches
            != goal.distance_lower_bound(
                start, ignores_vertical_distance=capabilities.ignores_vertical_distance
            )
        ):
            raise GameLifecycleError("Charge historical reachability bound drifted.")
