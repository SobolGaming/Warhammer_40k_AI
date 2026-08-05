from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookBinding,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelPlacementRecord,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_model_materialization_support import (
    CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID,
    MaterializeModelsDescriptor,
    UnitDatasheetReplacementDescriptor,
    materialize_models_descriptor_for_clause,
    unit_datasheet_replacement_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import (
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.return_placement_legality import (
    validate_model_placement_endpoints,
)
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyError,
    rules_unit_coherency_result,
)
from warhammer40k_core.engine.unit_factory import (
    ModelInstance,
    ModelInstancePayload,
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR

SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE = (
    "submit_catalog_model_materialization_placement"
)
CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT = "catalog_model_materialization_roll_resolved"
CATALOG_MODELS_MATERIALIZED_EVENT = "catalog_models_materialized"
CATALOG_UNIT_DATASHEET_REPLACED_EVENT = "catalog_unit_datasheet_replaced"


@dataclass(frozen=True, slots=True)
class CatalogMaterializationSource:
    player_id: str
    record: AbilityCatalogRecord
    source_unit_instance_id: str
    clause: RuleClause
    rule_ir: RuleIR
    materialization: MaterializeModelsDescriptor | None = None
    replacement: UnitDatasheetReplacementDescriptor | None = None

    @property
    def source_rule_id(self) -> str:
        return self.rule_ir.source_id

    @property
    def source_key(self) -> str:
        return f"{self.record.record_id}:{self.source_unit_instance_id}:{self.clause.clause_id}"


@dataclass(frozen=True, slots=True)
class ValidatedCatalogModelMaterialization:
    source_unit_instance_id: str
    source_rule_id: str
    attack_sequence_id: str
    placements: tuple[ModelPlacement, ...]
    models: tuple[ModelInstance, ...]
    hypothetical_armies: tuple[ArmyDefinition, ...]
    hypothetical_battlefield: BattlefieldRuntimeState
    transition_batch: BattlefieldTransitionBatch


@dataclass(frozen=True, slots=True)
class CatalogModelMaterializationRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]
    army_catalog: ArmyCatalog

    def __post_init__(self) -> None:
        indexes = _validate_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("Catalog model materialization requires ArmyCatalog.")
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog model materialization is missing ability indexes.")
        object.__setattr__(self, "ability_indexes_by_player_id", indexes)
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[AttackSequenceCompletedHookBinding, ...]:
        if not self.sources():
            return ()
        return (
            AttackSequenceCompletedHookBinding(
                hook_id=CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID,
                source_id=CATALOG_IR_MODEL_MATERIALIZATION_CONSUMER_ID,
                handler=self.resolve_completed_attack_sequence,
            ),
        )

    def sources(self) -> tuple[CatalogMaterializationSource, ...]:
        sources: list[CatalogMaterializationSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                for unit in army.units:
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=unit.own_model_ids(),
                    ):
                        continue
                    for clause in catalog_rule_clauses_from_record(record):
                        materialization = materialize_models_descriptor_for_clause(clause)
                        replacement = unit_datasheet_replacement_descriptor_for_clause(clause)
                        if materialization is None and replacement is None:
                            continue
                        sources.append(
                            CatalogMaterializationSource(
                                player_id=army.player_id,
                                record=record,
                                source_unit_instance_id=unit.unit_instance_id,
                                clause=clause,
                                rule_ir=rule_ir,
                                materialization=materialization,
                                replacement=replacement,
                            )
                        )
        return tuple(sorted(sources, key=lambda source: source.source_key))

    def resolve_completed_attack_sequence(
        self,
        context: AttackSequenceCompletedContext,
    ) -> LifecycleStatus | None:
        if type(context) is not AttackSequenceCompletedContext:
            raise GameLifecycleError("Catalog materialization requires completion context.")
        destroyed_model_ids = _destroyed_model_ids_for_sequence(context)
        if not destroyed_model_ids:
            return None
        sources = self.sources()
        for source in sources:
            descriptor = source.materialization
            if descriptor is None:
                continue
            source_destroyed_ids = tuple(
                model_id
                for model_id in destroyed_model_ids
                if _destroyed_model_matches_source(
                    state=context.state,
                    source=source,
                    descriptor=descriptor,
                    model_instance_id=model_id,
                )
            )
            if not source_destroyed_ids:
                continue
            rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=source.source_unit_instance_id,
            )
            if not rules_unit.alive_models():
                continue
            for model_id in source_destroyed_ids:
                roll_event = _roll_event_for(
                    decisions=context.decisions,
                    attack_sequence_id=context.attack_sequence.sequence_id,
                    source=source,
                    destroyed_model_instance_id=model_id,
                )
                if roll_event is None:
                    roll = context.dice_manager.roll(
                        DiceRollSpec(
                            expression=DiceExpression(quantity=1, sides=6),
                            reason=f"Model materialization for {model_id}",
                            roll_type="catalog.model_materialization.trigger",
                            actor_id=source.player_id,
                        )
                    )
                    roll_event = context.decisions.event_log.append(
                        CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
                        validate_json_value(
                            {
                                "game_id": context.state.game_id,
                                "battle_round": context.state.battle_round,
                                "phase": context.source_phase.value,
                                "attack_sequence_id": context.attack_sequence.sequence_id,
                                "attack_sequence_completed_event_id": (
                                    context.attack_sequence_completed_event_id
                                ),
                                "catalog_record_id": source.record.record_id,
                                "clause_id": source.clause.clause_id,
                                "source_rule_id": source.source_rule_id,
                                "source_unit_instance_id": source.source_unit_instance_id,
                                "destroyed_model_instance_id": model_id,
                                "success_threshold": descriptor.success_threshold,
                                "roll": roll.to_payload(),
                                "successful": roll.current_total >= descriptor.success_threshold,
                                "result_count": descriptor.result_count,
                            }
                        ),
                    )
                payload = _event_payload(roll_event.payload, "materialization roll")
                if payload.get("successful") is not True:
                    continue
                if (
                    _materialization_event_for_roll(
                        decisions=context.decisions,
                        roll_event_id=roll_event.event_id,
                    )
                    is not None
                ):
                    continue
                request = _materialization_request(
                    state=context.state,
                    decisions=context.decisions,
                    source=source,
                    descriptor=descriptor,
                    attack_sequence_id=context.attack_sequence.sequence_id,
                    roll_event_id=roll_event.event_id,
                    army_catalog=self.army_catalog,
                )
                return LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=request,
                    payload={
                        "game_id": context.state.game_id,
                        "phase": context.source_phase.value,
                        "pending_request_id": request.request_id,
                        "phase_body_status": "catalog_model_materialization_pending",
                    },
                )
        _apply_available_datasheet_replacements(
            state=context.state,
            decisions=context.decisions,
            army_catalog=self.army_catalog,
            sources=sources,
            destroyed_model_ids=destroyed_model_ids,
            attack_sequence_id=context.attack_sequence.sequence_id,
        )
        return None


def invalid_catalog_model_materialization_placement_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
    try:
        _validated_materialization_submission(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
    except (
        DecisionError,
        GameLifecycleError,
        GeometryError,
        PlacementError,
        UnitCoherencyError,
        UnitFactoryError,
        KeyError,
        TypeError,
    ) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Catalog model materialization placement is invalid.",
            payload={
                "game_id": state.game_id,
                "request_id": request.request_id,
                "result_id": result.result_id,
                "invalid_reason": f"malformed_or_invalid:{type(exc).__name__}",
            },
        )
    return None


def apply_recorded_catalog_model_materialization_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> tuple[ModelPlacementRecord, ...]:
    decisions.record_for_result(result)
    validated = _validated_materialization_submission(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    state.replace_army_definitions(list(validated.hypothetical_armies))
    state.replace_battlefield_state(validated.hypothetical_battlefield)
    event = decisions.event_log.append(
        CATALOG_MODELS_MATERIALIZED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "attack_sequence_id": validated.attack_sequence_id,
                "source_rule_id": validated.source_rule_id,
                "source_unit_instance_id": validated.source_unit_instance_id,
                "request_id": request.request_id,
                "result_id": result.result_id,
                "model_instance_ids": [model.model_instance_id for model in validated.models],
                "models": [model.to_payload() for model in validated.models],
                "transition_batch": validated.transition_batch.to_payload(),
            }
        ),
    )
    decisions.event_log.append(
        "battlefield_models_placed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "placement_kind": BattlefieldPlacementKind.SPLIT_UNIT.value,
                "placement_trigger_kind": "model_placed_on_battlefield",
                "source_rule_id": validated.source_rule_id,
                "source_event_id": event.event_id,
                "source_unit_instance_id": validated.source_unit_instance_id,
                "model_instance_ids": [model.model_instance_id for model in validated.models],
                "model_placements": [placement.to_payload() for placement in validated.placements],
                "transition_batch": validated.transition_batch.to_payload(),
            }
        ),
    )
    return validated.transition_batch.placements


def _materialization_request(
    *,
    state: GameState,
    decisions: DecisionController,
    source: CatalogMaterializationSource,
    descriptor: MaterializeModelsDescriptor,
    attack_sequence_id: str,
    roll_event_id: str,
    army_catalog: ArmyCatalog,
) -> DecisionRequest:
    source_unit, army = _unit_and_army_for_id(
        armies=tuple(state.army_definitions),
        unit_instance_id=source.source_unit_instance_id,
    )
    models = tuple(
        UnitFactory(army_catalog).instantiate_materialized_model(
            datasheet_id=source_unit.datasheet_id,
            model_profile_id=descriptor.result_model_profile_id,
            model_instance_id=(
                f"{source.source_unit_instance_id}:materialized:{roll_event_id}:{index:02d}"
            ),
            model_name=descriptor.result_model_name,
            wargear_ids=descriptor.result_wargear_ids,
            source_id=source.source_rule_id,
            materialization_descriptor_id=descriptor.result_materialization_descriptor_id,
        )
        for index in range(1, descriptor.result_count + 1)
    )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(
            {
                "submission_kind": (SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE),
                "proposal_kind": ProposalKind.MODEL_MATERIALIZATION.value,
                "placement_kind": BattlefieldPlacementKind.SPLIT_UNIT.value,
                "attack_sequence_id": attack_sequence_id,
                "roll_event_id": roll_event_id,
                "catalog_record_id": source.record.record_id,
                "clause_id": source.clause.clause_id,
                "source_rule_id": source.source_rule_id,
                "materialization_descriptor_id": (descriptor.result_materialization_descriptor_id),
                "source_unit_instance_id": source.source_unit_instance_id,
                "army_id": army.army_id,
                "player_id": army.player_id,
                "models": [model.to_payload() for model in models],
                "model_instance_ids": [model.model_instance_id for model in models],
            }
        ),
        options=(parameterized_decision_option(),),
    )
    decisions.request_decision(request)
    return request


def _validated_materialization_submission(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> ValidatedCatalogModelMaterialization:
    payload = _request_payload(request)
    result.validate_for_request(request)
    submission = _submission(result)
    if submission.proposal_request_id != request.request_id:
        raise GameLifecycleError("Model materialization proposal request is stale.")
    if submission.proposal_kind is not ProposalKind.MODEL_MATERIALIZATION:
        raise GameLifecycleError("Model materialization proposal kind drift.")
    if submission.placement_kind is not BattlefieldPlacementKind.SPLIT_UNIT:
        raise GameLifecycleError("Model materialization placement kind drift.")
    source_unit_id = _payload_string(payload, "source_unit_instance_id")
    if submission.unit_instance_id != source_unit_id:
        raise GameLifecycleError("Model materialization unit drift.")
    unit_placement = submission.require_unit_placement()
    source_unit, army = _unit_and_army_for_id(
        armies=tuple(state.army_definitions), unit_instance_id=source_unit_id
    )
    if result.actor_id != army.player_id:
        raise GameLifecycleError("Model materialization actor drift.")
    if unit_placement.army_id != army.army_id or unit_placement.player_id != army.player_id:
        raise GameLifecycleError("Model materialization army or player drift.")
    if unit_placement.unit_instance_id != source_unit_id:
        raise GameLifecycleError("Model materialization placement unit drift.")
    if submission.large_model_exceptions or submission.restriction_overrides:
        raise GameLifecycleError("Model materialization does not accept placement exceptions.")
    if (
        submission.transport_unit_instance_id is not None
        or submission.disembark_mode is not None
        or submission.transport_movement_status is not None
    ):
        raise GameLifecycleError("Model materialization does not accept transport context.")
    models_payload = payload.get("models")
    if not isinstance(models_payload, list):
        raise GameLifecycleError("Model materialization request models must be a list.")
    models_list: list[ModelInstance] = []
    for item in models_payload:
        if not isinstance(item, dict):
            raise GameLifecycleError("Model materialization model payload is malformed.")
        models_list.append(ModelInstance.from_payload(cast(ModelInstancePayload, item)))
    models = tuple(models_list)
    expected_model_ids = tuple(sorted(model.model_instance_id for model in models))
    submitted_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if submitted_model_ids != expected_model_ids:
        raise GameLifecycleError("Model materialization model set drift.")
    source_rule_id = _payload_string(payload, "source_rule_id")
    materialization_descriptor_id = _payload_string(
        payload,
        "materialization_descriptor_id",
    )
    for model in models:
        if materialization_descriptor_id not in model.source_ids:
            raise GameLifecycleError("Materialized model descriptor identity drift.")
        expected = UnitFactory(army_catalog).instantiate_materialized_model(
            datasheet_id=source_unit.datasheet_id,
            model_profile_id=model.model_profile_id,
            model_instance_id=model.model_instance_id,
            model_name=model.name,
            wargear_ids=model.wargear_ids,
            source_id=source_rule_id,
            materialization_descriptor_id=materialization_descriptor_id,
        )
        if expected.to_payload() != model.to_payload():
            raise GameLifecycleError("Materialized model template drift.")
    hypothetical_unit = replace(
        source_unit,
        own_models=tuple(
            sorted(
                (*source_unit.own_models, *models),
                key=lambda model: model.model_instance_id,
            )
        ),
    )
    hypothetical_armies = _armies_with_unit(
        armies=tuple(state.army_definitions), updated_unit=hypothetical_unit
    )
    battlefield = _battlefield(state)
    hypothetical_battlefield = _battlefield_with_materialized_placements(
        battlefield=battlefield,
        army=army,
        source_unit_instance_id=source_unit_id,
        placements=unit_placement.model_placements,
    )
    scenario = BattlefieldScenario(
        armies=hypothetical_armies,
        battlefield_state=hypothetical_battlefield,
    )
    validate_model_placement_endpoints(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        placements=unit_placement.model_placements,
        placement_label="Model materialization placement",
    )
    rules_unit = rules_unit_view_from_armies(
        armies=hypothetical_armies,
        unit_instance_id=source_unit_id,
    )
    coherency = rules_unit_coherency_result(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
    )
    if not coherency.is_coherent:
        raise GameLifecycleError("Model materialization placement breaks unit coherency.")
    transition = BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.SPLIT_UNIT,
                pose=placement.pose,
                source_phase=None,
                source_step="after_attacking_unit_finished_attacks",
                source_rule_id=source_rule_id,
                source_event_id=_payload_string(payload, "roll_event_id"),
            )
            for placement in unit_placement.model_placements
        )
    )
    return ValidatedCatalogModelMaterialization(
        source_unit_instance_id=source_unit_id,
        source_rule_id=source_rule_id,
        attack_sequence_id=_payload_string(payload, "attack_sequence_id"),
        placements=unit_placement.model_placements,
        models=models,
        hypothetical_armies=hypothetical_armies,
        hypothetical_battlefield=hypothetical_battlefield,
        transition_batch=transition,
    )


def _apply_available_datasheet_replacements(
    *,
    state: GameState,
    decisions: DecisionController,
    army_catalog: ArmyCatalog,
    sources: tuple[CatalogMaterializationSource, ...],
    destroyed_model_ids: tuple[str, ...],
    attack_sequence_id: str,
) -> None:
    destroyed_id_set = set(destroyed_model_ids)
    for source in sources:
        descriptor = source.replacement
        if descriptor is None:
            continue
        unit, _army = _unit_and_army_for_id(
            armies=tuple(state.army_definitions),
            unit_instance_id=source.source_unit_instance_id,
        )
        if not destroyed_id_set.intersection(unit.own_model_ids()):
            continue
        if unit.datasheet_id == descriptor.replacement_datasheet_id:
            continue
        if any(
            model.is_alive
            and model.model_profile_id in descriptor.required_absent_model_profile_ids
            for model in unit.own_models
        ):
            continue
        _replace_unit_datasheet(
            state=state,
            decisions=decisions,
            army_catalog=army_catalog,
            source=source,
            descriptor=descriptor,
            attack_sequence_id=attack_sequence_id,
        )


def _replace_unit_datasheet(
    *,
    state: GameState,
    decisions: DecisionController,
    army_catalog: ArmyCatalog,
    source: CatalogMaterializationSource,
    descriptor: UnitDatasheetReplacementDescriptor,
    attack_sequence_id: str,
) -> None:
    unit, _army = _unit_and_army_for_id(
        armies=tuple(state.army_definitions), unit_instance_id=source.source_unit_instance_id
    )
    replacement_datasheet = army_catalog.datasheet_by_id(descriptor.replacement_datasheet_id)
    retained_models = tuple(
        model
        for model in unit.own_models
        if not (
            not model.is_alive and model.model_profile_id in descriptor.pruned_model_profile_ids
        )
    )
    remapped_models: list[ModelInstance] = []
    for model in retained_models:
        matching_variants = tuple(
            variant
            for variant in descriptor.model_variants
            if variant.materialization_descriptor_id in model.source_ids
        )
        if len(matching_variants) != 1:
            raise GameLifecycleError("Datasheet handoff found a model without materialization ID.")
        variant = matching_variants[0]
        template = UnitFactory(army_catalog).instantiate_materialized_model(
            datasheet_id=descriptor.replacement_datasheet_id,
            model_profile_id=descriptor.replacement_model_profile_id,
            model_instance_id=model.model_instance_id,
            model_name=model.name,
            wargear_ids=variant.wargear_ids,
            source_id=source.source_rule_id,
            materialization_descriptor_id=variant.materialization_descriptor_id,
        )
        remapped_models.append(replace(template, wounds_remaining=model.wounds_remaining))
    updated_unit = replace(
        unit,
        datasheet_id=replacement_datasheet.datasheet_id,
        name=replacement_datasheet.name,
        keywords=replacement_datasheet.keywords.keywords,
        faction_keywords=replacement_datasheet.keywords.faction_keywords,
        datasheet_abilities=replacement_datasheet.abilities,
        datasheet_source_ids=replacement_datasheet.source_ids,
        own_models=tuple(sorted(remapped_models, key=lambda model: model.model_instance_id)),
        wargear_selections=(),
        mustering_option_selections=(),
        damaged_effects=replacement_datasheet.damaged_effects,
        starting_resources=(),
    )
    pruned_model_ids = tuple(
        model.model_instance_id for model in unit.own_models if model not in retained_models
    )
    state.replace_army_definitions(
        list(_armies_with_unit(armies=tuple(state.army_definitions), updated_unit=updated_unit))
    )
    if pruned_model_ids:
        state.replace_battlefield_state(
            _battlefield_without_removed_model_ids(
                battlefield=_battlefield(state), model_instance_ids=pruned_model_ids
            )
        )
    decisions.event_log.append(
        CATALOG_UNIT_DATASHEET_REPLACED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "attack_sequence_id": attack_sequence_id,
                "catalog_record_id": source.record.record_id,
                "clause_id": source.clause.clause_id,
                "source_rule_id": source.source_rule_id,
                "unit_instance_id": updated_unit.unit_instance_id,
                "previous_datasheet_id": unit.datasheet_id,
                "replacement_datasheet_id": updated_unit.datasheet_id,
                "retained_model_instance_ids": list(updated_unit.own_model_ids()),
                "pruned_model_instance_ids": list(pruned_model_ids),
                "starting_strength_preserved": True,
            }
        ),
    )


def _destroyed_model_ids_for_sequence(
    context: AttackSequenceCompletedContext,
) -> tuple[str, ...]:
    destroyed_ids: set[str] = set()
    for record in context.decisions.event_log.records:
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if record.event_type == "model_destroyed" and payload.get("sequence_id") == (
            context.attack_sequence.sequence_id
        ):
            destroyed_ids.add(_payload_string(payload, "model_instance_id"))
        if (
            record.event_type != "hazardous_mortal_wounds_applied"
            or payload.get("sequence_id") != context.attack_sequence.sequence_id
        ):
            continue
        application = payload.get("mortal_wound_application")
        if not isinstance(application, dict):
            raise GameLifecycleError("Hazardous materialization application is malformed.")
        damage_applications = application.get("applications")
        if not isinstance(damage_applications, list):
            raise GameLifecycleError("Hazardous materialization damage list is malformed.")
        for damage in damage_applications:
            if not isinstance(damage, dict):
                raise GameLifecycleError("Hazardous materialization damage is malformed.")
            if damage.get("destroyed") is True:
                destroyed_ids.add(_payload_string(damage, "model_instance_id"))
    return tuple(sorted(destroyed_ids))


def _destroyed_model_matches_source(
    *,
    state: GameState,
    source: CatalogMaterializationSource,
    descriptor: MaterializeModelsDescriptor,
    model_instance_id: str,
) -> bool:
    unit, _army = _unit_and_army_for_id(
        armies=tuple(state.army_definitions), unit_instance_id=source.source_unit_instance_id
    )
    model = next(
        (model for model in unit.own_models if model.model_instance_id == model_instance_id),
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


def _roll_event_for(
    *,
    decisions: DecisionController,
    attack_sequence_id: str,
    source: CatalogMaterializationSource,
    destroyed_model_instance_id: str,
) -> EventRecord | None:
    for record in decisions.event_log.records:
        if record.event_type != CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT:
            continue
        payload = _event_payload(record.payload, "materialization roll")
        if (
            payload.get("attack_sequence_id") == attack_sequence_id
            and payload.get("catalog_record_id") == source.record.record_id
            and payload.get("clause_id") == source.clause.clause_id
            and payload.get("source_unit_instance_id") == source.source_unit_instance_id
            and payload.get("destroyed_model_instance_id") == destroyed_model_instance_id
        ):
            return record
    return None


def _materialization_event_for_roll(
    *, decisions: DecisionController, roll_event_id: str
) -> EventRecord | None:
    for record in decisions.event_log.records:
        if record.event_type != CATALOG_MODELS_MATERIALIZED_EVENT:
            continue
        payload = _event_payload(record.payload, "models materialized")
        transition = payload.get("transition_batch")
        if not isinstance(transition, dict):
            raise GameLifecycleError("Materialization transition batch is malformed.")
        placements = transition.get("placements")
        if not isinstance(placements, list):
            raise GameLifecycleError("Materialization placement records are malformed.")
        if any(
            isinstance(placement, dict) and placement.get("source_event_id") == roll_event_id
            for placement in placements
        ):
            return record
    return None


def _battlefield_with_materialized_placements(
    *,
    battlefield: BattlefieldRuntimeState,
    army: ArmyDefinition,
    source_unit_instance_id: str,
    placements: tuple[ModelPlacement, ...],
) -> BattlefieldRuntimeState:
    existing = battlefield.unit_placement_or_none(source_unit_instance_id)
    if existing is not None:
        return battlefield.with_unit_placement(
            existing.with_model_placements(
                tuple(
                    sorted(
                        (*existing.model_placements, *placements),
                        key=lambda item: item.model_instance_id,
                    )
                )
            )
        )
    if not any(placed_army.army_id == army.army_id for placed_army in battlefield.placed_armies):
        raise GameLifecycleError("Model materialization army is not on the battlefield.")
    return battlefield.with_added_unit_placement(
        UnitPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=source_unit_instance_id,
            model_placements=placements,
        )
    )


def _battlefield_without_removed_model_ids(
    *, battlefield: BattlefieldRuntimeState, model_instance_ids: tuple[str, ...]
) -> BattlefieldRuntimeState:
    removed_ids = set(model_instance_ids)
    return BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        terrain_features=battlefield.terrain_features,
        placed_armies=battlefield.placed_armies,
        removed_model_ids=tuple(
            model_id for model_id in battlefield.removed_model_ids if model_id not in removed_ids
        ),
    )


def _armies_with_unit(
    *, armies: tuple[ArmyDefinition, ...], updated_unit: UnitInstance
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    did_replace = False
    for army in armies:
        if not any(unit.unit_instance_id == updated_unit.unit_instance_id for unit in army.units):
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
        did_replace = True
    if not did_replace:
        raise GameLifecycleError("Model materialization unit is not in an army.")
    return tuple(updated_armies)


def _unit_and_army_for_id(
    *, armies: tuple[ArmyDefinition, ...], unit_instance_id: str
) -> tuple[UnitInstance, ArmyDefinition]:
    matches = tuple(
        (unit, army)
        for army in armies
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Model materialization unit lookup must resolve exactly once.")
    return matches[0]


def _battlefield(state: GameState) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise GameLifecycleError("Model materialization requires battlefield_state.")
    return state.battlefield_state


def _request_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    if request.decision_type != SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Model materialization decision_type drift.")
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Model materialization request payload must be an object.")
    if payload.get("submission_kind") != request.decision_type:
        raise GameLifecycleError("Model materialization submission kind drift.")
    if payload.get("proposal_kind") != ProposalKind.MODEL_MATERIALIZATION.value:
        raise GameLifecycleError("Model materialization request proposal kind drift.")
    return payload


def _submission(result: DecisionResult) -> PlacementProposalPayload:
    if not isinstance(result.payload, dict):
        raise GameLifecycleError("Model materialization result payload must be an object.")
    return PlacementProposalPayload.from_payload(
        cast(PlacementProposalPayloadPayload, result.payload)
    )


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Model materialization {key} must be a string.")
    return value


def _event_payload(payload: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"Catalog {label} event payload must be an object.")
    return payload


def _validate_indexes(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog model materialization indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog model materialization index entry is invalid.")
        indexes[player_id] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple or not all(
        type(army) is ArmyDefinition for army in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Catalog model materialization armies must be a tuple.")
    return cast(tuple[ArmyDefinition, ...], value)


__all__ = (
    "CATALOG_MODELS_MATERIALIZED_EVENT",
    "CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT",
    "CATALOG_UNIT_DATASHEET_REPLACED_EVENT",
    "SUBMIT_CATALOG_MODEL_MATERIALIZATION_PLACEMENT_DECISION_TYPE",
    "CatalogModelMaterializationRuntime",
    "apply_recorded_catalog_model_materialization_placement",
    "invalid_catalog_model_materialization_placement_status",
)
