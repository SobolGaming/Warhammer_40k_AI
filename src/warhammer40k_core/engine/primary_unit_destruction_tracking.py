from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.destruction_source_attribution import (
    validate_destruction_source_identity,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    current_primary_rules_unit_turn_start_membership_for_lineage,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState
    from warhammer40k_core.engine.unit_factory import UnitInstance


def build_primary_unit_destruction_state(
    *,
    state: GameState,
    destruction_attribution: ModelDestructionAttribution | None,
    source_model_destroyed_event_id: str | None,
    source_rules_unit_objective_proximity_witness: (RulesUnitObjectiveProximityWitness | None),
    source_battlefield_departure_ids: tuple[str, ...],
    unattributed_cause: PrimaryUnattributedDestructionCause | None,
    source_mutation_id: str | None,
    destroyed_unit_instance_id: str,
    source_id: str,
) -> PrimaryUnitDestructionState:
    """Build one authoritative rules-unit destruction occurrence."""
    if state.mission_setup is None:
        raise GameLifecycleError("Primary unit destruction tracking requires MissionSetup.")
    if state.active_player_id is None:
        raise GameLifecycleError("Primary unit destruction tracking requires an active player.")
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Primary unit destruction tracking requires a battle phase.")
    if destruction_attribution is not None:
        if type(destruction_attribution) is not ModelDestructionAttribution:
            raise GameLifecycleError(
                "Primary unit destruction requires typed destruction attribution."
            )
        requested_destroyer = _validate_identifier(
            "destroying_player_id",
            destruction_attribution.destroying_player_id,
        )
        if requested_destroyer not in state.player_ids:
            raise GameLifecycleError("player_id is not in this game.")
        validate_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=(destruction_attribution.source_rules_unit_instance_id),
            source_model_instance_id=destruction_attribution.source_model_instance_id,
            destroying_player_id=requested_destroyer,
        )
    else:
        requested_destroyer = None
    requested_unit = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    physical_units_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    (
        destroyed_player_id,
        destroyed_component_ids,
        destroyed_starting_model_ids,
    ) = _destruction_identity(
        state=state,
        rules_unit_instance_id=requested_unit,
        physical_units_by_id=physical_units_by_id,
        owner_by_unit_id=owner_by_unit_id,
    )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary unit destruction tracking requires battlefield_state.")
    models_by_id = {
        model.model_instance_id: model
        for unit in physical_units_by_id.values()
        for model in unit.own_models
    }
    removed_model_ids = set(battlefield.removed_model_ids)
    if any(
        models_by_id[model_id].is_alive and model_id not in removed_model_ids
        for model_id in destroyed_starting_model_ids
    ):
        raise GameLifecycleError(
            "Primary unit destruction tracking requires a destroyed rules unit."
        )
    requested_source_id = _validate_identifier("source_id", source_id)
    destruction_id = primary_unit_destruction_id(
        game_id=state.game_id,
        source_id=requested_source_id,
        destroyed_unit_instance_id=requested_unit,
    )
    if any(
        stored.destruction_id == destruction_id for stored in state.primary_unit_destruction_states
    ):
        raise GameLifecycleError("Primary unit destruction already exists for this occurrence.")
    turn_start_membership = current_primary_rules_unit_turn_start_membership_for_lineage(
        state=state,
        rules_unit_instance_id=requested_unit,
        component_unit_instance_ids=destroyed_component_ids,
    )
    destruction = PrimaryUnitDestructionState(
        destruction_id=destruction_id,
        game_id=state.game_id,
        destroying_player_id=requested_destroyer,
        destruction_attribution=destruction_attribution,
        source_model_destroyed_event_id=source_model_destroyed_event_id,
        source_rules_unit_objective_proximity_witness=(
            source_rules_unit_objective_proximity_witness
        ),
        source_battlefield_departure_ids=source_battlefield_departure_ids,
        unattributed_cause=unattributed_cause,
        source_mutation_id=source_mutation_id,
        destroyed_player_id=destroyed_player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=phase.value,
        destroyed_unit_instance_id=requested_unit,
        started_turn_terrain_feature_ids=turn_start_membership.terrain_feature_ids,
        started_turn_objective_marker_ids=turn_start_membership.objective_marker_ids,
        source_id=requested_source_id,
    )
    model_ids_by_unit_id = {
        unit_id: unit.own_model_ids() for unit_id, unit in physical_units_by_id.items()
    }
    owner_by_unit_id.update(
        {
            record.attached_unit_instance_id: record.player_id
            for record in state.starting_attached_unit_records
        }
    )
    validate_primary_unit_destruction_source_witness_identity(
        destruction,
        owner_by_unit_id=owner_by_unit_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        known_rules_unit_components_by_id={
            **{unit_id: (unit_id,) for unit_id in physical_units_by_id},
            **{
                record.attached_unit_instance_id: record.component_unit_instance_ids
                for record in state.starting_attached_unit_records
            },
        },
        known_objective_marker_ids=tuple(
            marker.objective_marker_id for marker in state.mission_setup.objective_markers
        ),
    )
    return destruction


def record_primary_unit_destructions_for_destroyed_models(
    *,
    state: GameState,
    destroyed_model_instance_ids: tuple[str, ...],
    destruction_attribution: ModelDestructionAttribution | None,
    source_model_destroyed_event_id: str | None,
    source_rules_unit_objective_proximity_witness: (RulesUnitObjectiveProximityWitness | None),
    destroyed_rules_unit_objective_proximity_witness: (RulesUnitObjectiveProximityWitness | None),
    unattributed_cause: PrimaryUnattributedDestructionCause | None,
    source_mutation_id: str | None,
    left_battlefield: bool,
    source_id: str,
) -> tuple[PrimaryUnitDestructionState, ...]:
    """Record component edges, then logical completions, for one mutation."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary destruction tracking requires GameState.")
    if state.mission_setup is None:
        return ()
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary destruction tracking requires battlefield_state.")
    destroyed_model_ids = _validate_identifier_tuple(
        "destroyed_model_instance_ids",
        destroyed_model_instance_ids,
    )
    requested_source_id = _validate_identifier("source_id", source_id)
    if type(left_battlefield) is not bool:
        raise GameLifecycleError("Primary destruction battlefield-departure flag must be bool.")
    if destruction_attribution is not None:
        if type(destruction_attribution) is not ModelDestructionAttribution:
            raise GameLifecycleError(
                "Primary destruction tracking requires typed destruction attribution."
            )
        validate_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=(destruction_attribution.source_rules_unit_instance_id),
            source_model_instance_id=destruction_attribution.source_model_instance_id,
            destroying_player_id=destruction_attribution.destroying_player_id,
        )
    known_models = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if any(model_id not in known_models for model_id in destroyed_model_ids):
        raise GameLifecycleError("Primary destruction tracking references an unknown model.")
    physical_units_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    if (
        destroyed_rules_unit_objective_proximity_witness is not None
        and type(destroyed_rules_unit_objective_proximity_witness)
        is not RulesUnitObjectiveProximityWitness
    ):
        raise GameLifecycleError(
            "Primary destruction tracking requires a typed destroyed-unit witness."
        )
    completed_component_ids = _completed_components_touched_by_models(
        state=state,
        destroyed_model_instance_ids=destroyed_model_ids,
        physical_units_by_id=physical_units_by_id,
    )
    if left_battlefield:
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=destroyed_model_ids,
            source_id=requested_source_id,
        )

    scoring_identities: dict[
        str,
        tuple[str, tuple[str, ...], tuple[str, ...]],
    ] = {}
    for component_id in completed_component_ids:
        scoring_unit_id, owner_id, component_ids, starting_model_ids = (
            _scoring_identity_for_component(
                state=state,
                component_unit_instance_id=component_id,
                physical_units_by_id=physical_units_by_id,
                owner_by_unit_id=owner_by_unit_id,
            )
        )
        identity = (owner_id, component_ids, starting_model_ids)
        existing = scoring_identities.get(scoring_unit_id)
        if existing is not None and existing != identity:
            raise GameLifecycleError("Primary destruction scoring identity is ambiguous.")
        scoring_identities[scoring_unit_id] = identity

    records: list[PrimaryUnitDestructionState] = []
    for scoring_unit_id, (_owner_id, _component_ids, _starting_model_ids) in sorted(
        scoring_identities.items()
    ):
        record = record_primary_unit_destruction_for_logical_completion(
            state=state,
            destruction_attribution=destruction_attribution,
            source_model_destroyed_event_id=source_model_destroyed_event_id,
            source_rules_unit_objective_proximity_witness=(
                source_rules_unit_objective_proximity_witness
            ),
            unattributed_cause=unattributed_cause,
            source_mutation_id=source_mutation_id,
            destroyed_unit_instance_id=scoring_unit_id,
            source_id=requested_source_id,
        )
        if record is not None:
            records.append(record)
    return tuple(sorted(records, key=lambda record: record.destruction_id))


def record_primary_destroyed_model_departures(
    *,
    state: GameState,
    destroyed_model_instance_ids: tuple[str, ...],
    source_id: str,
    occurrence_id: str | None = None,
    fully_departed_component_unit_instance_ids: tuple[str, ...] | None = None,
) -> tuple[PrimaryBattlefieldDepartureState, ...]:
    """Record exact model-removal edges for one authoritative occurrence.

    ``affected`` identifies each removed model's physical owner.  A component is
    ``departed`` only when none of its current models remain on the battlefield;
    completing a frozen Attached Unit lineage while a later-added model survives
    therefore does not manufacture a leaves-battlefield occurrence.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary model destruction tracking requires GameState.")
    if state.mission_setup is None:
        return ()
    destroyed_model_ids = _validate_identifier_tuple(
        "destroyed_model_instance_ids",
        destroyed_model_instance_ids,
    )
    requested_source_id = _validate_identifier("source_id", source_id)
    requested_occurrence_id = _validate_identifier(
        "occurrence_id",
        requested_source_id if occurrence_id is None else occurrence_id,
    )
    physical_units_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    component_by_model_id = {
        model.model_instance_id: component_id
        for component_id, unit in physical_units_by_id.items()
        for model in unit.own_models
    }
    unknown_model_ids = tuple(
        model_id for model_id in destroyed_model_ids if model_id not in component_by_model_id
    )
    if unknown_model_ids:
        raise GameLifecycleError("Primary model destruction references an unknown model.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary model destruction requires battlefield_state.")
    if state.active_player_id is None or state.current_battle_phase is None:
        raise GameLifecycleError(
            "Primary model destruction requires active-player battle-phase state."
        )
    placed_model_ids = set(battlefield.placed_model_ids())
    removed_ids_by_component = {
        component_id: tuple(
            sorted(
                model_id
                for model_id in destroyed_model_ids
                if component_by_model_id[model_id] == component_id
            )
        )
        for component_id in sorted(
            {component_by_model_id[model_id] for model_id in destroyed_model_ids}
        )
    }
    affected_component_ids = tuple(removed_ids_by_component)
    if fully_departed_component_unit_instance_ids is None:
        fully_departed_ids = tuple(
            component_id
            for component_id in affected_component_ids
            if not set(physical_units_by_id[component_id].own_model_ids()).intersection(
                placed_model_ids
            )
        )
    else:
        fully_departed_ids = _validate_identifier_tuple_allow_empty(
            "fully_departed_component_unit_instance_ids",
            fully_departed_component_unit_instance_ids,
        )
        if not set(fully_departed_ids) <= set(affected_component_ids):
            raise GameLifecycleError(
                "Fully departed destruction components must be affected by the occurrence."
            )
    records: list[PrimaryBattlefieldDepartureState] = []
    for component_id, exact_removed_model_ids in removed_ids_by_component.items():
        scoring_unit_id, _owner_id, _component_ids, _starting_model_ids = (
            _scoring_identity_for_component(
                state=state,
                component_unit_instance_id=component_id,
                physical_units_by_id=physical_units_by_id,
                owner_by_unit_id=owner_by_unit_id,
            )
        )
        departed_component_ids = (component_id,) if component_id in fully_departed_ids else ()
        edge_source_id = f"{requested_source_id}:{component_id}"
        edge_occurrence_id = f"{requested_occurrence_id}:{component_id}"
        expected_departure_id = primary_battlefield_departure_id(
            game_id=state.game_id,
            rules_unit_instance_id=scoring_unit_id,
            affected_component_unit_instance_ids=(component_id,),
            departed_component_unit_instance_ids=departed_component_ids,
            removed_model_instance_ids=exact_removed_model_ids,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            phase=state.current_battle_phase.value,
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id=edge_occurrence_id,
            source_id=edge_source_id,
        )
        existing = tuple(
            departure
            for departure in state.primary_battlefield_departure_states
            if departure.departure_id == expected_departure_id
        )
        if existing:
            if len(existing) != 1:
                raise GameLifecycleError("Primary model destruction edge identity is ambiguous.")
            expected = existing[0]
            if (
                expected.affected_component_unit_instance_ids != (component_id,)
                or expected.departed_component_unit_instance_ids != departed_component_ids
                or expected.removed_model_instance_ids != exact_removed_model_ids
                or expected.occurrence_id != edge_occurrence_id
                or expected.source_id != edge_source_id
            ):
                raise GameLifecycleError("Primary model destruction edge identity drift.")
            records.append(expected)
            continue
        departure = record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=scoring_unit_id,
            affected_component_unit_instance_ids=(component_id,),
            departed_component_unit_instance_ids=departed_component_ids,
            removed_model_instance_ids=exact_removed_model_ids,
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id=edge_occurrence_id,
            source_id=edge_source_id,
        )
        if departure is None:
            raise GameLifecycleError(
                "Primary model destruction departure unexpectedly produced no edge."
            )
        records.append(departure)
    return tuple(sorted(records, key=lambda departure: departure.departure_id))


def record_primary_unit_destruction_for_logical_completion(
    *,
    state: GameState,
    destruction_attribution: ModelDestructionAttribution | None,
    source_model_destroyed_event_id: str | None,
    source_rules_unit_objective_proximity_witness: RulesUnitObjectiveProximityWitness | None,
    unattributed_cause: PrimaryUnattributedDestructionCause | None,
    source_mutation_id: str | None,
    destroyed_unit_instance_id: str,
    source_id: str,
) -> PrimaryUnitDestructionState | None:
    """Bind fresh component edges to one canonical rules-unit completion."""
    requested_unit_id = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    requested_source_id = _validate_identifier("source_id", source_id)
    physical_units_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    _owner_id, component_ids, starting_model_ids = _destruction_identity(
        state=state,
        rules_unit_instance_id=requested_unit_id,
        physical_units_by_id=physical_units_by_id,
        owner_by_unit_id=owner_by_unit_id,
    )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary logical destruction requires battlefield_state.")
    removed_model_ids = set(battlefield.removed_model_ids)
    models_by_id = {
        model.model_instance_id: model
        for unit in physical_units_by_id.values()
        for model in unit.own_models
    }
    if any(
        models_by_id[model_id].is_alive and model_id not in removed_model_ids
        for model_id in starting_model_ids
    ):
        return None
    occurrence_source_id = f"{requested_source_id}:{requested_unit_id}"
    if any(
        destruction.destroyed_unit_instance_id == requested_unit_id
        and destruction.source_id == occurrence_source_id
        for destruction in state.primary_unit_destruction_states
    ):
        return None
    used_departure_ids = {
        departure_id
        for destruction in state.primary_unit_destruction_states
        for departure_id in destruction.source_battlefield_departure_ids
    }
    source_departures = (
        ()
        if unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
        else _unconsumed_destroyed_departures_for_components(
            state=state,
            component_unit_instance_ids=component_ids,
            starting_model_instance_ids=starting_model_ids,
            used_departure_ids=used_departure_ids,
        )
    )
    prior_occurrences = tuple(
        destruction
        for destruction in state.primary_unit_destruction_states
        if destruction.destroyed_unit_instance_id == requested_unit_id
    )
    if unattributed_cause is not PrimaryUnattributedDestructionCause.RESERVE_DEADLINE:
        if not source_departures:
            raise GameLifecycleError(
                "Primary logical destruction requires a fresh battlefield-departure edge."
            )
        if not prior_occurrences:
            covered_starting_model_ids = {
                model_id
                for departure in source_departures
                for model_id in departure.removed_model_instance_ids
                if model_id in starting_model_ids
            }
            if covered_starting_model_ids != set(starting_model_ids):
                raise GameLifecycleError(
                    "Primary logical destruction departure edges do not cover its starting unit."
                )
    return state.record_primary_unit_destruction(
        destruction_attribution=destruction_attribution,
        source_model_destroyed_event_id=source_model_destroyed_event_id,
        source_rules_unit_objective_proximity_witness=(
            source_rules_unit_objective_proximity_witness
        ),
        source_battlefield_departure_ids=tuple(
            departure.departure_id for departure in source_departures
        ),
        unattributed_cause=unattributed_cause,
        source_mutation_id=source_mutation_id,
        destroyed_unit_instance_id=requested_unit_id,
        source_id=occurrence_source_id,
    )


def record_primary_unit_destructions_for_end_turn_cleanup(
    *,
    state: GameState,
    cleanup: EndTurnCleanupState,
) -> tuple[PrimaryUnitDestructionState, ...]:
    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState

    if type(cleanup) is not EndTurnCleanupState:
        raise GameLifecycleError("Primary destruction cleanup tracking requires cleanup state.")
    if not cleanup.removed_model_instance_ids:
        return ()
    return record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=cleanup.removed_model_instance_ids,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        destroyed_rules_unit_objective_proximity_witness=None,
        unattributed_cause=PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
        source_mutation_id=cleanup.cleanup_id,
        left_battlefield=True,
        source_id=cleanup.cleanup_id,
    )


def _completed_components_touched_by_models(
    *,
    state: GameState,
    destroyed_model_instance_ids: tuple[str, ...],
    physical_units_by_id: dict[str, UnitInstance],
) -> tuple[str, ...]:
    destroyed_model_ids = set(destroyed_model_instance_ids)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary component completion requires battlefield_state.")
    removed_model_ids = set(battlefield.removed_model_ids)
    historical_by_component = {
        component_id: record
        for record in state.starting_attached_unit_records
        for component_id in record.component_unit_instance_ids
    }
    completed: list[str] = []
    for component_id, unit in physical_units_by_id.items():
        historical = historical_by_component.get(component_id)
        completion_model_ids = (
            set(unit.own_model_ids())
            if historical is None
            else set(historical.starting_model_instance_ids_for_component(component_id))
        )
        if not completion_model_ids.intersection(destroyed_model_ids):
            continue
        models_by_id = {
            model.model_instance_id: model
            for model in unit.own_models
            if model.model_instance_id in completion_model_ids
        }
        if set(models_by_id) != completion_model_ids:
            raise GameLifecycleError("Primary component completion lost a starting model.")
        if any(
            model.is_alive and model_id not in removed_model_ids
            for model_id, model in models_by_id.items()
        ):
            continue
        completed.append(component_id)
    return tuple(sorted(completed))


def _destruction_identity(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    physical_units_by_id: dict[str, UnitInstance],
    owner_by_unit_id: dict[str, str],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    requested_id = _validate_identifier(
        "destroyed_unit_instance_id",
        rules_unit_instance_id,
    )
    historical = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == requested_id
    )
    if len(historical) > 1:
        raise GameLifecycleError("Primary destruction historical Attached Unit is ambiguous.")
    if historical:
        record = historical[0]
        return (
            record.player_id,
            record.component_unit_instance_ids,
            tuple(
                sorted(
                    model_id
                    for _component_id, model_ids in (
                        record.starting_model_instance_ids_by_component
                    )
                    for model_id in model_ids
                )
            ),
        )
    unit = physical_units_by_id.get(requested_id)
    if unit is None:
        raise GameLifecycleError("Primary unit destruction references an unknown unit.")
    owner_id = owner_by_unit_id.get(requested_id)
    if owner_id is None:
        raise GameLifecycleError("Primary unit destruction references an unowned unit.")
    own_model_ids = unit.own_model_ids()
    return owner_id, (requested_id,), tuple(sorted(own_model_ids))


def _scoring_identity_for_component(
    *,
    state: GameState,
    component_unit_instance_id: str,
    physical_units_by_id: dict[str, UnitInstance],
    owner_by_unit_id: dict[str, str],
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    requested_component_id = _validate_identifier(
        "component_unit_instance_id",
        component_unit_instance_id,
    )
    historical = tuple(
        record
        for record in state.starting_attached_unit_records
        if requested_component_id in record.component_unit_instance_ids
    )
    if len(historical) > 1:
        raise GameLifecycleError("Primary destruction Attached Unit lineage is ambiguous.")
    if historical:
        record = historical[0]
        starting_model_ids = tuple(
            sorted(
                model_id
                for _component_id, model_ids in record.starting_model_instance_ids_by_component
                for model_id in model_ids
            )
        )
        return (
            record.attached_unit_instance_id,
            record.player_id,
            record.component_unit_instance_ids,
            starting_model_ids,
        )
    owner_id, component_ids, starting_model_ids = _destruction_identity(
        state=state,
        rules_unit_instance_id=requested_component_id,
        physical_units_by_id=physical_units_by_id,
        owner_by_unit_id=owner_by_unit_id,
    )
    return requested_component_id, owner_id, component_ids, starting_model_ids


def _unconsumed_destroyed_departures_for_components(
    *,
    state: GameState,
    component_unit_instance_ids: tuple[str, ...],
    starting_model_instance_ids: tuple[str, ...],
    used_departure_ids: set[str],
) -> tuple[PrimaryBattlefieldDepartureState, ...]:
    requested_components = set(component_unit_instance_ids)
    requested_starting_models = set(starting_model_instance_ids)
    return tuple(
        sorted(
            (
                departure
                for departure in state.primary_battlefield_departure_states
                if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
                and departure.departure_id not in used_departure_ids
                and set(departure.affected_component_unit_instance_ids) <= requested_components
                and bool(
                    set(departure.removed_model_instance_ids).intersection(
                        requested_starting_models
                    )
                )
            ),
            key=lambda departure: departure.departure_id,
        )
    )


def primary_unit_destruction_id(
    *,
    game_id: str,
    source_id: str,
    destroyed_unit_instance_id: str,
) -> str:
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    requested_unit_id = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    occurrence_hash = canonical_payload_sha256(
        {
            "game_id": requested_game_id,
            "source_id": requested_source_id,
            "destroyed_unit_instance_id": requested_unit_id,
        }
    )
    return f"primary-unit-destruction:{occurrence_hash}"


def validate_primary_unit_destruction_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    known_rules_unit_components_by_id: dict[str, tuple[str, ...]],
    known_objective_marker_ids: tuple[str, ...],
) -> list[PrimaryUnitDestructionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary unit destruction states must be a list.")
    validated: list[PrimaryUnitDestructionState] = []
    seen_ids: set[str] = set()
    seen_occurrences: set[tuple[str, str]] = set()
    for state in cast(list[object], states):
        if type(state) is not PrimaryUnitDestructionState:
            raise GameLifecycleError(
                "GameState primary unit destruction states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryUnitDestructionState game_id drift.")
        if (
            state.destroying_player_id not in {None, *player_ids}
            or state.destroyed_player_id not in player_ids
            or state.active_player_id not in player_ids
        ):
            raise GameLifecycleError("PrimaryUnitDestructionState player_id is not in this game.")
        if state.destruction_attribution is not None and (
            state.destruction_attribution.destroying_player_id not in player_ids
        ):
            raise GameLifecycleError(
                "PrimaryUnitDestructionState attribution player is not in this game."
            )
        validate_primary_unit_destruction_source_witness_identity(
            state,
            owner_by_unit_id=owner_by_unit_id,
            model_ids_by_unit_id=model_ids_by_unit_id,
            known_rules_unit_components_by_id=known_rules_unit_components_by_id,
            known_objective_marker_ids=known_objective_marker_ids,
        )
        destroyed_unit_id = state.destroyed_unit_instance_id
        if destroyed_unit_id not in owner_by_unit_id:
            raise GameLifecycleError(
                "PrimaryUnitDestructionState references an unknown destroyed unit."
            )
        if state.destroyed_player_id != owner_by_unit_id[destroyed_unit_id]:
            raise GameLifecycleError("PrimaryUnitDestructionState destroyed player drift.")
        expected_destruction_id = primary_unit_destruction_id(
            game_id=game_id,
            source_id=state.source_id,
            destroyed_unit_instance_id=destroyed_unit_id,
        )
        if state.destruction_id != expected_destruction_id:
            raise GameLifecycleError("PrimaryUnitDestructionState destruction_id drift.")
        if state.destruction_id in seen_ids:
            raise GameLifecycleError("GameState primary unit destruction states must be unique.")
        occurrence = (destroyed_unit_id, state.source_id)
        if occurrence in seen_occurrences:
            raise GameLifecycleError(
                "GameState primary unit destruction states must be unique per occurrence."
            )
        seen_ids.add(state.destruction_id)
        seen_occurrences.add(occurrence)
        validated.append(state)
    return sorted(validated, key=lambda state: state.destruction_id)


def validate_primary_unit_destruction_source_witness_identity(
    state: PrimaryUnitDestructionState,
    *,
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    known_rules_unit_components_by_id: dict[str, tuple[str, ...]],
    known_objective_marker_ids: tuple[str, ...],
) -> None:
    attribution = state.destruction_attribution
    witness = state.source_rules_unit_objective_proximity_witness
    if attribution is None or witness is None:
        return
    source_rules_unit_id = attribution.source_rules_unit_instance_id
    if source_rules_unit_id is None:
        raise GameLifecycleError(
            "Primary destruction source witness requires an attributed source rules unit."
        )
    expected_components = known_rules_unit_components_by_id.get(source_rules_unit_id)
    if expected_components is None:
        raise GameLifecycleError(
            "Primary destruction source witness references an unknown rules unit."
        )
    if witness.component_unit_instance_ids != tuple(sorted(expected_components)):
        raise GameLifecycleError("Primary destruction source witness component identity drift.")
    if any(
        owner_by_unit_id.get(component_id) != attribution.destroying_player_id
        for component_id in expected_components
    ):
        raise GameLifecycleError(
            "Primary destruction source rules unit must belong to the destroying player."
        )
    source_model_id = attribution.source_model_instance_id
    if source_model_id is not None and all(
        source_model_id not in model_ids_by_unit_id.get(component_id, ())
        for component_id in expected_components
    ):
        raise GameLifecycleError(
            "Primary destruction source model is not in the source rules unit."
        )
    known_marker_ids = set(known_objective_marker_ids)
    known_source_model_ids = {
        model_id
        for component_id in expected_components
        for model_id in model_ids_by_unit_id.get(component_id, ())
    }
    for marker_witness in witness.objective_marker_witnesses:
        if marker_witness.objective_marker_id not in known_marker_ids:
            raise GameLifecycleError(
                "Primary destruction source witness references an unknown objective marker."
            )
        if any(
            model_id not in known_source_model_ids for model_id in marker_witness.model_instance_ids
        ):
            raise GameLifecycleError(
                "Primary destruction source witness references a model outside its rules unit."
            )


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _validate_identifier_tuple_allow_empty(
    field_name: str,
    value: object,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "build_primary_unit_destruction_state",
    "primary_unit_destruction_id",
    "record_primary_destroyed_model_departures",
    "record_primary_unit_destructions_for_destroyed_models",
    "record_primary_unit_destructions_for_end_turn_cleanup",
    "validate_primary_unit_destruction_source_witness_identity",
    "validate_primary_unit_destruction_states",
)
