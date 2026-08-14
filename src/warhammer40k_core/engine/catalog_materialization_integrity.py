from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldTransitionBatch,
    ModelPlacementRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
    CATALOG_MODELS_MATERIALIZED_EVENT,
    SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
    CatalogMaterializationSource,
    CatalogModelMaterializationRuntime,
)
from warhammer40k_core.engine.catalog_model_materialization_support import (
    CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID,
    MaterializeModelsDescriptor,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
    MortalWoundDestructionEvidence,
    MortalWoundDestructionEvidencePayload,
)
from warhammer40k_core.engine.movement_proposals import (
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactory, UnitInstance

MaterializedModelPayloadsByUnitId = dict[str, dict[str, dict[str, JsonValue]]]


def authenticated_catalog_materialized_model_payloads_by_unit_id(
    *,
    game_id: str,
    catalog: ArmyCatalog,
    expected_armies: tuple[ArmyDefinition, ...],
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> MaterializedModelPayloadsByUnitId:
    """Return only catalog-created models backed by the complete runtime evidence graph."""

    runtime = _materialization_runtime(catalog=catalog, expected_armies=expected_armies)
    event_index_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_index_by_id) != len(event_records):
        raise GameLifecycleError("Catalog materialization event identities are duplicated.")
    materialized_events = tuple(
        event for event in event_records if event.event_type == CATALOG_MODELS_MATERIALIZED_EVENT
    )
    if materialized_events and not any(
        binding.hook_id == CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID
        and binding.source_id == CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID
        for binding in runtime.bindings()
    ):
        raise GameLifecycleError("Catalog materialization has no active runtime provider binding.")

    payloads_by_unit_id: MaterializedModelPayloadsByUnitId = {}
    consumed_roll_ids: set[str] = set()
    consumed_record_ids: set[str] = set()
    for materialized_event in materialized_events:
        unit_id, model_payloads, roll_id, record_id = _validated_materialization_event(
            game_id=game_id,
            catalog=catalog,
            runtime=runtime,
            expected_armies=expected_armies,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            decision_records=decision_records,
            materialized_event=materialized_event,
        )
        if roll_id in consumed_roll_ids or record_id in consumed_record_ids:
            raise GameLifecycleError("Catalog materialization evidence is reused.")
        consumed_roll_ids.add(roll_id)
        consumed_record_ids.add(record_id)
        stored = payloads_by_unit_id.setdefault(unit_id, {})
        if set(stored).intersection(model_payloads):
            raise GameLifecycleError("Catalog materialization model identity is duplicated.")
        stored.update(model_payloads)
    return payloads_by_unit_id


def _materialization_runtime(
    *,
    catalog: ArmyCatalog,
    expected_armies: tuple[ArmyDefinition, ...],
) -> CatalogModelMaterializationRuntime:
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in expected_armies
    }
    return CatalogModelMaterializationRuntime(
        ability_indexes_by_player_id=indexes,
        armies=expected_armies,
        army_catalog=catalog,
    )


def _validated_materialization_event(
    *,
    game_id: str,
    catalog: ArmyCatalog,
    runtime: CatalogModelMaterializationRuntime,
    expected_armies: tuple[ArmyDefinition, ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: Mapping[str, int],
    decision_records: tuple[DecisionRecord, ...],
    materialized_event: EventRecord,
) -> tuple[str, dict[str, dict[str, JsonValue]], str, str]:
    payload = _event_payload(materialized_event, "catalog materialization")
    if payload.get("game_id") != game_id:
        raise GameLifecycleError("Catalog materialization game identity drift.")
    request_id = _required_string(payload, "request_id")
    result_id = _required_string(payload, "result_id")
    record = _exact_decision_record(
        decision_records=decision_records,
        request_id=request_id,
        result_id=result_id,
    )
    request_payload = _request_payload(record)
    source, descriptor = _active_source(runtime=runtime, request_payload=request_payload)
    source_unit, source_army = _unit_and_army(
        armies=expected_armies,
        unit_instance_id=source.source_unit_instance_id,
    )
    roll_event = _exact_event(
        event_records,
        event_id=_required_string(request_payload, "roll_event_id"),
        event_type=CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
        label="Catalog materialization roll",
    )
    _validate_roll(
        source=source,
        descriptor=descriptor,
        source_unit=source_unit,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        roll_event=roll_event,
        request_payload=request_payload,
    )
    expected_models = _expected_models(
        catalog=catalog,
        source=source,
        descriptor=descriptor,
        source_unit=source_unit,
        roll_event_id=roll_event.event_id,
    )
    _validate_request(
        record=record,
        source=source,
        descriptor=descriptor,
        source_army=source_army,
        request_payload=request_payload,
        expected_models=expected_models,
        roll_event_id=roll_event.event_id,
    )
    placement = _validated_result_placement(record=record, source=source, source_army=source_army)
    transition = BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=model_placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.SPLIT_UNIT,
                pose=model_placement.pose,
                source_phase=_required_string(request_payload, "parent_battle_phase"),
                source_step="after_attacking_unit_finished_attacks",
                source_rule_id=source.source_rule_id,
                source_event_id=roll_event.event_id,
            )
            for model_placement in placement.model_placements
        )
    )
    expected_model_payloads = [model.to_payload() for model in expected_models]
    expected_model_ids = [model.model_instance_id for model in expected_models]
    expected_materialized_payload: dict[str, JsonValue] = {
        "game_id": game_id,
        "battle_round": _required_int(
            _event_payload(roll_event, "catalog materialization roll"), "battle_round"
        ),
        "attack_sequence_id": _required_string(request_payload, "attack_sequence_id"),
        "source_phase": _required_string(request_payload, "parent_battle_phase"),
        "action_phase": _required_string(request_payload, "action_phase"),
        "parent_battle_phase": _required_string(request_payload, "parent_battle_phase"),
        "source_rule_id": source.source_rule_id,
        "source_unit_instance_id": source.source_unit_instance_id,
        "request_id": record.request.request_id,
        "result_id": record.result.result_id,
        "model_instance_ids": cast(JsonValue, expected_model_ids),
        "models": cast(JsonValue, expected_model_payloads),
        "transition_batch": cast(JsonValue, transition.to_payload()),
    }
    if payload != expected_materialized_payload:
        raise GameLifecycleError("Catalog materialization completion payload drift.")
    _validate_event_chain(
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        record=record,
        roll_event=roll_event,
        materialized_event=materialized_event,
        source=source,
        source_army=source_army,
        request_payload=request_payload,
        placement_payloads=cast(
            list[JsonValue], [value.to_payload() for value in placement.model_placements]
        ),
        transition=transition,
    )
    return (
        source.source_unit_instance_id,
        {
            model.model_instance_id: cast(dict[str, JsonValue], model.to_payload())
            for model in expected_models
        },
        roll_event.event_id,
        record.record_id,
    )


def _active_source(
    *,
    runtime: CatalogModelMaterializationRuntime,
    request_payload: dict[str, JsonValue],
) -> tuple[CatalogMaterializationSource, MaterializeModelsDescriptor]:
    matches = tuple(
        source
        for source in runtime.sources()
        if source.player_id == request_payload.get("player_id")
        and source.source_unit_instance_id == request_payload.get("source_unit_instance_id")
        and source.record.record_id == request_payload.get("catalog_record_id")
        and source.clause.clause_id == request_payload.get("clause_id")
        and source.source_rule_id == request_payload.get("source_rule_id")
        and source.materialization is not None
        and source.materialization.result_materialization_descriptor_id
        == request_payload.get("materialization_descriptor_id")
    )
    if len(matches) != 1 or matches[0].materialization is None:
        raise GameLifecycleError(
            "Catalog materialization does not resolve to one active source provider."
        )
    return matches[0], matches[0].materialization


def _validate_request(
    *,
    record: DecisionRecord,
    source: CatalogMaterializationSource,
    descriptor: MaterializeModelsDescriptor,
    source_army: ArmyDefinition,
    request_payload: dict[str, JsonValue],
    expected_models: tuple[ModelInstance, ...],
    roll_event_id: str,
) -> None:
    request = record.request
    result = record.result
    if (
        request.decision_type != SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE
        or result.decision_type != request.decision_type
        or request.actor_id != source.player_id
        or result.actor_id != source.player_id
    ):
        raise GameLifecycleError("Catalog materialization decision identity drift.")
    expected_payload: dict[str, JsonValue] = {
        "submission_kind": SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
        "proposal_kind": ProposalKind.MODEL_MATERIALIZATION.value,
        "placement_kind": BattlefieldPlacementKind.SPLIT_UNIT.value,
        "attack_sequence_id": _required_string(request_payload, "attack_sequence_id"),
        "source_phase": _required_string(request_payload, "parent_battle_phase"),
        "action_phase": _required_string(request_payload, "action_phase"),
        "parent_battle_phase": _required_string(request_payload, "parent_battle_phase"),
        "roll_event_id": roll_event_id,
        "catalog_record_id": source.record.record_id,
        "clause_id": source.clause.clause_id,
        "source_rule_id": source.source_rule_id,
        "materialization_descriptor_id": descriptor.result_materialization_descriptor_id,
        "source_unit_instance_id": source.source_unit_instance_id,
        "army_id": source_army.army_id,
        "player_id": source_army.player_id,
        "models": cast(JsonValue, [model.to_payload() for model in expected_models]),
        "model_instance_ids": cast(
            JsonValue, [model.model_instance_id for model in expected_models]
        ),
    }
    if request_payload != expected_payload:
        raise GameLifecycleError("Catalog materialization request payload drift.")


def _validated_result_placement(
    *,
    record: DecisionRecord,
    source: CatalogMaterializationSource,
    source_army: ArmyDefinition,
) -> UnitPlacement:
    if not isinstance(record.result.payload, dict):
        raise GameLifecycleError("Catalog materialization result payload is malformed.")
    proposal = PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, record.result.payload)
    )
    placement = proposal.attempted_placement
    if (
        proposal.proposal_request_id != record.request.request_id
        or proposal.proposal_kind is not ProposalKind.MODEL_MATERIALIZATION
        or proposal.placement_kind is not BattlefieldPlacementKind.SPLIT_UNIT
        or proposal.unit_instance_id != source.source_unit_instance_id
        or placement is None
        or proposal.attempted_rules_unit_placement is not None
        or proposal.large_model_exceptions
        or proposal.transport_unit_instance_id is not None
        or proposal.disembark_mode is not None
        or proposal.transport_movement_status is not None
        or proposal.restriction_overrides
        or placement.army_id != source_army.army_id
        or placement.player_id != source_army.player_id
        or placement.unit_instance_id != source.source_unit_instance_id
    ):
        raise GameLifecycleError("Catalog materialization accepted placement drift.")
    request_model_ids = _required_string_list(_request_payload(record), "model_instance_ids")
    if tuple(sorted(value.model_instance_id for value in placement.model_placements)) != tuple(
        sorted(request_model_ids)
    ):
        raise GameLifecycleError("Catalog materialization accepted model set drift.")
    return placement


def _validate_roll(
    *,
    source: CatalogMaterializationSource,
    descriptor: MaterializeModelsDescriptor,
    source_unit: UnitInstance,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: Mapping[str, int],
    roll_event: EventRecord,
    request_payload: dict[str, JsonValue],
) -> None:
    payload = _event_payload(roll_event, "catalog materialization roll")
    attack_sequence_id = _required_string(request_payload, "attack_sequence_id")
    exact_fields: tuple[tuple[str, JsonValue], ...] = (
        ("phase", _required_string(request_payload, "parent_battle_phase")),
        ("action_phase", _required_string(request_payload, "action_phase")),
        ("parent_battle_phase", _required_string(request_payload, "parent_battle_phase")),
        ("attack_sequence_id", attack_sequence_id),
        ("catalog_record_id", source.record.record_id),
        ("clause_id", source.clause.clause_id),
        ("source_rule_id", source.source_rule_id),
        ("source_unit_instance_id", source.source_unit_instance_id),
        ("success_threshold", descriptor.success_threshold),
        ("result_count", descriptor.result_count),
        ("successful", True),
    )
    if any(payload.get(key) != expected for key, expected in exact_fields):
        raise GameLifecycleError("Catalog materialization roll context drift.")
    completion = _exact_event(
        event_records,
        event_id=_required_string(payload, "attack_sequence_completed_event_id"),
        event_type="attack_sequence_completed",
        label="Catalog materialization attack completion",
    )
    completion_payload = _event_payload(completion, "catalog materialization attack completion")
    if completion_payload.get("sequence_id") != attack_sequence_id:
        raise GameLifecycleError("Catalog materialization attack completion sequence drift.")
    if event_index_by_id[completion.event_id] >= event_index_by_id[roll_event.event_id]:
        raise GameLifecycleError("Catalog materialization roll precedes its attack completion.")
    destroyed_model_id = _required_string(payload, "destroyed_model_instance_id")
    if not _destroyed_model_matches_descriptor(
        source_unit=source_unit,
        descriptor=descriptor,
        model_instance_id=destroyed_model_id,
    ):
        raise GameLifecycleError("Catalog materialization destroyed model source drift.")
    if destroyed_model_id not in _destroyed_model_ids_for_sequence(
        event_records=event_records,
        attack_sequence_id=attack_sequence_id,
        descriptor=descriptor,
    ):
        raise GameLifecycleError("Catalog materialization destruction evidence drift.")
    raw_roll = payload.get("roll")
    if not isinstance(raw_roll, dict):
        raise GameLifecycleError("Catalog materialization roll payload is malformed.")
    roll = DiceRollState.from_payload(cast(DiceRollStatePayload, raw_roll))
    expected_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Model materialization for {destroyed_model_id}",
        roll_type="catalog.model_materialization.trigger",
        actor_id=source.player_id,
    )
    if roll.original_result.spec != expected_spec:
        raise GameLifecycleError("Catalog materialization roll specification drift.")
    if roll.current_total < descriptor.success_threshold:
        raise GameLifecycleError("Catalog materialization successful roll result drift.")


def _validate_event_chain(
    *,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: Mapping[str, int],
    record: DecisionRecord,
    roll_event: EventRecord,
    materialized_event: EventRecord,
    source: CatalogMaterializationSource,
    source_army: ArmyDefinition,
    request_payload: dict[str, JsonValue],
    placement_payloads: list[JsonValue],
    transition: BattlefieldTransitionBatch,
) -> None:
    requested = _exact_payload_event(
        event_records,
        event_type="decision_requested",
        payload=cast(dict[str, JsonValue], record.request.to_payload()),
        label="Catalog materialization decision request",
    )
    recorded = _exact_payload_event(
        event_records,
        event_type="decision_recorded",
        payload=cast(dict[str, JsonValue], record.to_payload()),
        label="Catalog materialization decision record",
    )
    materialized_index = event_index_by_id[materialized_event.event_id]
    if not (
        event_index_by_id[roll_event.event_id]
        < event_index_by_id[requested.event_id]
        < event_index_by_id[recorded.event_id]
        < materialized_index
    ):
        raise GameLifecycleError("Catalog materialization evidence order drift.")
    terminal_index = materialized_index + 1
    if terminal_index >= len(event_records):
        raise GameLifecycleError("Catalog materialization lacks its placement terminal event.")
    terminal = event_records[terminal_index]
    expected_terminal_payload: dict[str, JsonValue] = {
        "game_id": _required_string(
            _event_payload(materialized_event, "catalog materialization"), "game_id"
        ),
        "battle_round": _required_int(
            _event_payload(materialized_event, "catalog materialization"), "battle_round"
        ),
        "source_phase": _required_string(request_payload, "parent_battle_phase"),
        "action_phase": _required_string(request_payload, "action_phase"),
        "parent_battle_phase": _required_string(request_payload, "parent_battle_phase"),
        "placement_kind": BattlefieldPlacementKind.SPLIT_UNIT.value,
        "placement_trigger_kind": "model_placed_on_battlefield",
        "source_rule_id": source.source_rule_id,
        "source_event_id": materialized_event.event_id,
        "source_unit_instance_id": source.source_unit_instance_id,
        "model_instance_ids": cast(
            JsonValue, list(_required_string_list(request_payload, "model_instance_ids"))
        ),
        "model_placements": cast(JsonValue, placement_payloads),
        "transition_batch": cast(JsonValue, transition.to_payload()),
    }
    if (
        terminal.event_type != "battlefield_models_placed"
        or terminal.payload != expected_terminal_payload
    ):
        raise GameLifecycleError("Catalog materialization placement terminal payload drift.")
    if source_army.player_id != record.request.actor_id:
        raise GameLifecycleError("Catalog materialization placement terminal owner drift.")


def _expected_models(
    *,
    catalog: ArmyCatalog,
    source: CatalogMaterializationSource,
    descriptor: MaterializeModelsDescriptor,
    source_unit: UnitInstance,
    roll_event_id: str,
) -> tuple[ModelInstance, ...]:
    return tuple(
        UnitFactory(catalog).instantiate_materialized_model(
            datasheet_id=source_unit.datasheet_id,
            model_profile_id=descriptor.result_model_profile_id,
            model_instance_id=f"{source.source_unit_instance_id}:materialized:{roll_event_id}:{index:02d}",
            model_name=descriptor.result_model_name,
            wargear_ids=descriptor.result_wargear_ids,
            source_id=source.source_rule_id,
            materialization_descriptor_id=descriptor.result_materialization_descriptor_id,
        )
        for index in range(1, descriptor.result_count + 1)
    )


def _destroyed_model_matches_descriptor(
    *,
    source_unit: UnitInstance,
    descriptor: MaterializeModelsDescriptor,
    model_instance_id: str,
) -> bool:
    model = next(
        (value for value in source_unit.own_models if value.model_instance_id == model_instance_id),
        None,
    )
    if model is None or model.model_profile_id not in descriptor.destroyed_model_profile_ids:
        return False
    if (
        descriptor.required_materialization_descriptor_id is not None
        and descriptor.required_materialization_descriptor_id not in model.source_ids
    ):
        return False
    return not set(descriptor.excluded_materialization_descriptor_ids).intersection(
        model.source_ids
    )


def _destroyed_model_ids_for_sequence(
    *,
    event_records: tuple[EventRecord, ...],
    attack_sequence_id: str,
    descriptor: MaterializeModelsDescriptor,
) -> set[str]:
    destroyed_ids: set[str] = set()
    for event in event_records:
        if event.event_type == "model_destroyed":
            payload = _event_payload(event, "model destroyed")
            if payload.get("sequence_id") != attack_sequence_id:
                continue
            attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
            if (
                attribution.destruction_provenance.destruction_source_kind
                in descriptor.destruction_source_kinds
            ):
                destroyed_ids.add(_required_string(payload, "model_instance_id"))
            continue
        if event.event_type == "hazardous_mortal_wounds_applied":
            if DestructionSourceKind.HAZARDOUS not in descriptor.destruction_source_kinds:
                continue
            payload = _event_payload(event, "hazardous mortal wounds applied")
            if payload.get("sequence_id") != attack_sequence_id:
                continue
            application = payload.get("mortal_wound_application")
            if not isinstance(application, dict):
                raise GameLifecycleError("Catalog materialization Hazardous evidence is malformed.")
            raw_applications = application.get("applications")
            if not isinstance(raw_applications, list):
                raise GameLifecycleError("Catalog materialization Hazardous evidence is malformed.")
            for raw_application in raw_applications:
                if not isinstance(raw_application, dict):
                    raise GameLifecycleError(
                        "Catalog materialization Hazardous evidence is malformed."
                    )
                if raw_application.get("destroyed") is True:
                    destroyed_ids.add(_required_string(raw_application, "model_instance_id"))
            continue
        if event.event_type != MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT:
            continue
        payload = _event_payload(event, "mortal wound destructions finalized")
        source_context = payload.get("source_context")
        raw_evidence = payload.get("destruction_evidence")
        if not isinstance(source_context, dict) or not isinstance(raw_evidence, dict):
            raise GameLifecycleError("Catalog materialization mortal-wound evidence is malformed.")
        if source_context.get("sequence_id") != attack_sequence_id:
            continue
        evidence = MortalWoundDestructionEvidence.from_payload(
            cast(MortalWoundDestructionEvidencePayload, raw_evidence)
        )
        if evidence.destruction_source_kind in descriptor.destruction_source_kinds:
            destroyed_ids.update(_required_string_list(payload, "destroyed_model_instance_ids"))
    return destroyed_ids


def _unit_and_army(
    *, armies: tuple[ArmyDefinition, ...], unit_instance_id: str
) -> tuple[UnitInstance, ArmyDefinition]:
    matches = tuple(
        (unit, army)
        for army in armies
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Catalog materialization source unit lookup drift.")
    return matches[0]


def _exact_decision_record(
    *, decision_records: tuple[DecisionRecord, ...], request_id: str, result_id: str
) -> DecisionRecord:
    matches = tuple(
        record
        for record in decision_records
        if record.request.request_id == request_id and record.result.result_id == result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Catalog materialization lacks one accepted decision record.")
    return matches[0]


def _exact_event(
    events: tuple[EventRecord, ...], *, event_id: str, event_type: str, label: str
) -> EventRecord:
    matches = tuple(event for event in events if event.event_id == event_id)
    if len(matches) != 1 or matches[0].event_type != event_type:
        raise GameLifecycleError(f"{label} identity drift.")
    return matches[0]


def _exact_payload_event(
    events: tuple[EventRecord, ...], *, event_type: str, payload: dict[str, JsonValue], label: str
) -> EventRecord:
    matches = tuple(
        event for event in events if event.event_type == event_type and event.payload == payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(f"{label} provenance drift.")
    return matches[0]


def _request_payload(record: DecisionRecord) -> dict[str, JsonValue]:
    payload = record.request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog materialization request payload is malformed.")
    return payload


def _event_payload(event: EventRecord, label: str) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError(f"{label} event payload is malformed.")
    return event.payload


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog materialization {key} must be a string.")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog materialization {key} must be an integer.")
    return value


def _required_string_list(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Catalog materialization {key} must be a string list.")
    raw_items = cast(list[object], value)
    if any(type(item) is not str or not item for item in raw_items):
        raise GameLifecycleError(f"Catalog materialization {key} must be a string list.")
    result = tuple(cast(str, item) for item in raw_items)
    if len(set(result)) != len(result):
        raise GameLifecycleError(f"Catalog materialization {key} contains duplicates.")
    return result


__all__ = (
    "MaterializedModelPayloadsByUnitId",
    "authenticated_catalog_materialized_model_payloads_by_unit_id",
)
