from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_geometry_catalog import ModelGeometryCatalogRecord
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusteringError,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.catalog_materialization_integrity import (
    MaterializedModelPayloadsByUnitId,
    authenticated_catalog_materialized_model_payloads_by_unit_id,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.starting_attached_units import (
    StartingAttachedUnitRecord,
    starting_attached_unit_records_for_army,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_resource_state import (
    unit_resource_initializations_for_army,
)
from warhammer40k_core.engine.unit_resources import UnitResourceTransactionKind


def validate_mustered_army_consistency(
    *,
    state: GameState,
    catalog: ArmyCatalog,
    muster_requests: tuple[ArmyMusterRequest, ...],
    model_geometries: tuple[ModelGeometryCatalogRecord, ...] | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if not state.army_definitions and not _state_requires_mustered_armies(state):
        return
    try:
        expected_armies = tuple(
            sorted(
                (
                    muster_army(
                        catalog=catalog,
                        request=request,
                        model_geometries=model_geometries,
                    )
                    for request in muster_requests
                ),
                key=lambda army: army.player_id,
            )
        )
    except ArmyMusteringError as exc:
        raise GameLifecycleError("Lifecycle config army muster requests are invalid.") from exc
    state_armies = tuple(state.army_definitions)
    _validate_starting_attached_mappings_against_muster(
        state=state,
        expected_armies=expected_armies,
    )
    materialized_model_payloads_by_unit_id = (
        authenticated_catalog_materialized_model_payloads_by_unit_id(
            game_id=state.game_id,
            catalog=catalog,
            expected_armies=expected_armies,
            event_records=event_records,
            decision_records=decision_records,
        )
    )
    if _state_requires_mustered_armies(state) and not state_armies:
        raise GameLifecycleError("Lifecycle state is missing mustered army definitions.")
    if state_armies and not _armies_match_muster_runtime_state(
        state=state,
        state_armies=state_armies,
        expected_armies=expected_armies,
        materialized_model_payloads_by_unit_id=(materialized_model_payloads_by_unit_id),
    ):
        raise GameLifecycleError("Lifecycle state army definitions do not match config.")
    if state_armies:
        _validate_unit_resource_initialization_consistency(
            state=state,
            expected_armies=expected_armies,
        )


def _validate_starting_attached_mappings_against_muster(
    *,
    state: GameState,
    expected_armies: tuple[ArmyDefinition, ...],
) -> None:
    expected_by_id = {
        record.attached_unit_instance_id: record
        for army in expected_armies
        for record in starting_attached_unit_records_for_army(army)
    }
    actual_by_id = {
        record.attached_unit_instance_id: record for record in state.starting_attached_unit_records
    }
    if set(actual_by_id) != set(expected_by_id):
        raise GameLifecycleError("Starting Attached Unit muster mapping identity drift.")
    for attached_unit_id, expected in expected_by_id.items():
        actual = actual_by_id[attached_unit_id]
        if _starting_attached_frozen_mapping(actual) != _starting_attached_frozen_mapping(expected):
            raise GameLifecycleError("Starting Attached Unit muster mapping drift.")


def _starting_attached_frozen_mapping(
    record: StartingAttachedUnitRecord,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return record.starting_model_instance_ids_by_component


def _armies_match_muster_runtime_state(
    *,
    state: GameState,
    state_armies: tuple[ArmyDefinition, ...],
    expected_armies: tuple[ArmyDefinition, ...],
    materialized_model_payloads_by_unit_id: MaterializedModelPayloadsByUnitId,
) -> bool:
    if len(state_armies) != len(expected_armies):
        return False
    for state_army, expected_army in zip(state_armies, expected_armies, strict=True):
        if state.stage not in {
            GameLifecycleStage.BATTLE,
            GameLifecycleStage.COMPLETE,
        }:
            if state_army != expected_army:
                return False
            continue
        if state_army.attached_units != expected_army.attached_units:
            return False
        normalized_state_army = replace(
            state_army,
            units=_units_with_expected_muster_wounds(
                state_army=state_army,
                expected_army=expected_army,
                materialized_model_payloads_by_unit_id=(materialized_model_payloads_by_unit_id),
            ),
        )
        if normalized_state_army != expected_army:
            return False
    return True


def _units_with_expected_muster_wounds(
    *,
    state_army: ArmyDefinition,
    expected_army: ArmyDefinition,
    materialized_model_payloads_by_unit_id: MaterializedModelPayloadsByUnitId,
) -> tuple[UnitInstance, ...]:
    expected_units_by_id = {unit.unit_instance_id: unit for unit in expected_army.units}
    if {unit.unit_instance_id for unit in state_army.units} != set(expected_units_by_id):
        return state_army.units
    normalized_units: list[UnitInstance] = []
    for state_unit in state_army.units:
        expected_unit = expected_units_by_id[state_unit.unit_instance_id]
        expected_models_by_id = {
            model.model_instance_id: model for model in expected_unit.own_models
        }
        state_models_by_id = {model.model_instance_id: model for model in state_unit.own_models}
        state_model_ids = set(state_models_by_id)
        expected_model_ids = set(expected_models_by_id)
        if not expected_model_ids <= state_model_ids:
            return state_army.units
        extra_model_ids = state_model_ids.difference(expected_model_ids)
        materialized_payloads = materialized_model_payloads_by_unit_id.get(
            state_unit.unit_instance_id,
            {},
        )
        if not extra_model_ids <= set(materialized_payloads) or any(
            not _runtime_model_matches_materialization_event(
                model=state_models_by_id[model_id],
                event_payload=materialized_payloads[model_id],
            )
            for model_id in extra_model_ids
        ):
            return state_army.units
        normalized_units.append(
            replace(
                state_unit,
                own_models=tuple(
                    replace(
                        state_models_by_id[model_id],
                        wounds_remaining=expected_models_by_id[model_id].wounds_remaining,
                    )
                    for model_id in expected_unit.own_model_ids()
                ),
            )
        )
    return tuple(normalized_units)


def _runtime_model_matches_materialization_event(
    *,
    model: ModelInstance,
    event_payload: dict[str, JsonValue],
) -> bool:
    runtime_payload = model.to_payload()
    if set(runtime_payload) != set(event_payload):
        return False
    event_wounds_remaining = event_payload.get("wounds_remaining")
    if type(event_wounds_remaining) is not int:
        return False
    runtime_payload["wounds_remaining"] = event_wounds_remaining
    return bool(runtime_payload == event_payload)


def _validate_unit_resource_initialization_consistency(
    *,
    state: GameState,
    expected_armies: tuple[ArmyDefinition, ...],
) -> None:
    expected: dict[tuple[str, str, str], tuple[int, str]] = {}
    for army in expected_armies:
        for initialization in unit_resource_initializations_for_army(army):
            key = (
                army.player_id,
                initialization.unit_instance_id,
                initialization.resource_kind,
            )
            if key in expected:
                raise GameLifecycleError("Mustered unit resource initialization is duplicated.")
            expected[key] = (initialization.amount, initialization.source_rule_id)
    actual: dict[tuple[str, str, str], tuple[int, str]] = {}
    for ledger in state.unit_resource_ledgers:
        for transaction in ledger.transactions:
            if transaction.transaction_kind is not UnitResourceTransactionKind.INITIALIZE:
                continue
            key = (ledger.player_id, ledger.unit_instance_id, transaction.resource_kind)
            if key in actual:
                raise GameLifecycleError("Unit resource ledger initialization is duplicated.")
            actual[key] = (transaction.amount, transaction.source_rule_id)
    if actual != expected:
        raise GameLifecycleError(
            "Lifecycle unit resource initializations do not match source-backed roster choices."
        )


def _state_requires_mustered_armies(state: GameState) -> bool:
    if state.stage is not GameLifecycleStage.SETUP:
        return True
    if state.setup_step_index is None:
        return True
    muster_step_index = _setup_step_index_or_none(state, SetupStep.MUSTER_ARMIES)
    if muster_step_index is None:
        raise GameLifecycleError("Lifecycle state setup sequence must include MUSTER_ARMIES.")
    return state.setup_step_index > muster_step_index


def _setup_step_index_or_none(state: GameState, step: SetupStep) -> int | None:
    for index, candidate in enumerate(state.setup_sequence):
        if candidate is step:
            return index
    return None
