from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,
    catalog_charge_roll_modifiers_for_unit,
)
from warhammer40k_core.engine.charge_declaration import (
    ChargeRollRequest,
    ChargeRollResult,
    phase15a_charge_roll_payload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    FIGHTS_FIRST_CHARGE_EFFECT_KIND,
)
from warhammer40k_core.engine.phases.shooting import (
    request_out_of_phase_shooting_declaration,
    shooting_rules_unit_has_legal_declaration_against_targets,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE = (
    "select_catalog_setup_reactive_shoot_charge"
)
CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECLINE_OPTION_ID = "decline"
CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID = "shoot"
CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID = "charge"
CATALOG_SETUP_REACTIVE_SOURCE_KIND = "catalog_setup_reactive_shoot_charge"
CATALOG_SETUP_REACTIVE_CHARGE_MOVE_EVENT = "catalog_setup_reactive_charge_move_completed"

_SETUP_REACTIVE_SELECTED_EVENTS = frozenset(
    {
        "catalog_setup_reactive_shoot_charge_declined",
        "catalog_setup_reactive_shoot_requested",
        "catalog_setup_reactive_charge_no_move_possible",
        CATALOG_SETUP_REACTIVE_CHARGE_MOVE_EVENT,
        "catalog_setup_reactive_shoot_charge_unsupported",
    }
)


@dataclass(frozen=True, slots=True)
class _SetupReactiveCandidate:
    player_id: str
    record: AbilityCatalogRecord
    rule_ir: RuleIR
    clause: RuleClause
    source_rules_unit: RulesUnitView
    source_component_unit: UnitInstance
    source_model: ModelInstance
    source_model_placement: ModelPlacement
    target_rules_unit_id: str
    target_component_unit_id: str
    target_player_id: str
    trigger_event_id: str
    distance_inches: float
    range_limit_inches: int
    can_shoot: bool
    can_charge: bool

    @property
    def action_option_ids(self) -> tuple[str, ...]:
        option_ids: list[str] = [CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECLINE_OPTION_ID]
        if self.can_shoot:
            option_ids.append(CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID)
        if self.can_charge:
            option_ids.append(CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID)
        return tuple(option_ids)

    def base_payload(self) -> dict[str, JsonValue]:
        return {
            "submission_kind": SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
            "source_kind": CATALOG_SETUP_REACTIVE_SOURCE_KIND,
            "consumer_id": CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,
            "catalog_record_id": self.record.record_id,
            "ability_id": self.record.definition.ability_id,
            "source_rule_id": self.record.definition.source_id,
            "rule_ir_source_id": self.rule_ir.source_id,
            "rule_ir_hash": self.rule_ir.ir_hash(),
            "clause_id": self.clause.clause_id,
            "source_unit_instance_id": self.source_rules_unit.unit_instance_id,
            "source_component_unit_instance_id": self.source_component_unit.unit_instance_id,
            "source_model_instance_id": self.source_model.model_instance_id,
            "target_unit_instance_id": self.target_rules_unit_id,
            "target_component_unit_instance_id": self.target_component_unit_id,
            "target_player_id": self.target_player_id,
            "trigger_event_id": self.trigger_event_id,
            "distance_inches": self.distance_inches,
            "range_limit_inches": self.range_limit_inches,
            "available_action_option_ids": list(self.action_option_ids),
        }

    def option_payload(self, action: str) -> JsonValue:
        payload = self.base_payload()
        payload["action"] = _validate_action(action)
        return validate_json_value(payload)


def request_catalog_setup_reactive_shoot_charge_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    if reaction_queue is None:
        return None
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Setup-reactive catalog reaction requires decisions.")
    _validate_ability_index_mapping(ability_indexes_by_player_id)
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Setup-reactive catalog reaction requires a RulesetDescriptor.")
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Setup-reactive catalog reaction requires an ArmyCatalog.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Setup-reactive catalog reaction requires runtime modifiers.")
    if type(charge_target_restriction_hooks) is not ChargeTargetRestrictionHookRegistry:
        raise GameLifecycleError(
            "Setup-reactive catalog reaction requires charge target restrictions."
        )
    active_player_id = _active_player_id(state)
    reacting_player_ids = tuple(
        sorted(player for player in state.player_ids if player != active_player_id)
    )
    for trigger_event in _setup_trigger_events(
        state=state,
        decisions=decisions,
        active_player_id=active_player_id,
    ):
        for player_id in reacting_player_ids:
            index = ability_indexes_by_player_id.get(player_id)
            if index is None:
                continue
            candidate = _first_candidate_for_player_and_trigger(
                state=state,
                decisions=decisions,
                player_id=player_id,
                active_player_id=active_player_id,
                trigger_event=trigger_event,
                ability_index=index,
                ruleset_descriptor=ruleset_descriptor,
                army_catalog=army_catalog,
            )
            if candidate is None:
                continue
            return _emit_setup_reactive_request(
                state=state,
                decisions=decisions,
                reaction_queue=reaction_queue,
                candidate=candidate,
            )
    return None


def invalid_catalog_setup_reactive_shoot_charge_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
    if request.decision_type != SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE:
        raise GameLifecycleError("Setup-reactive finite validation received wrong request.")
    try:
        result.validate_for_request(request)
    except DecisionError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Setup-reactive action result is malformed.",
            payload={
                "invalid_reason": "invalid_catalog_setup_reactive_action_result",
                "detail": str(exc),
            },
        )
    payload = _payload_object(result.payload)
    drift_reason = _setup_reactive_payload_drift_reason(
        state=state,
        decisions=decisions,
        payload=payload,
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if drift_reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Setup-reactive action is no longer available.",
        payload={
            "invalid_reason": drift_reason,
            "field": "payload",
        },
    )


def apply_catalog_setup_reactive_shoot_charge_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Setup-reactive apply requires decisions.")
    record = decisions.record_for_result(result)
    invalid_status = invalid_catalog_setup_reactive_shoot_charge_status(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
        ability_indexes_by_player_id={result.actor_id or "": ability_index},
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if invalid_status is not None:
        return invalid_status
    payload = _payload_object(result.payload)
    action = _payload_string(payload, key="action")
    if action == CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECLINE_OPTION_ID:
        decisions.event_log.append(
            "catalog_setup_reactive_shoot_charge_declined",
            _selection_event_payload(state=state, result=result, payload=payload),
        )
        return None
    if action == CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID:
        return _apply_setup_reactive_shoot(
            state=state,
            decisions=decisions,
            result=result,
            payload=payload,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
    if action == CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID:
        return _apply_setup_reactive_charge(
            state=state,
            decisions=decisions,
            result=result,
            payload=payload,
            ruleset_descriptor=ruleset_descriptor,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
        )
    raise GameLifecycleError("Setup-reactive action is unsupported.")


def _emit_setup_reactive_request(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    candidate: _SetupReactiveCandidate,
) -> LifecycleStatus:
    window_id = _setup_reactive_timing_window_id(candidate)
    reaction_window = ReactionWindow(
        timing_window=TimingWindow(
            window_id=window_id,
            descriptor=TimingWindowDescriptor(
                descriptor_id="catalog-setup-reactive-shoot-charge",
                trigger_kind=TimingTriggerKind.END_PHASE,
                source_rule_id=candidate.record.definition.source_id,
                phase=BattlePhase.MOVEMENT,
                source_step="end_movement_phase_reactions",
                metadata=candidate.base_payload(),
            ),
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=_active_player_id(state),
            phase=BattlePhase.MOVEMENT,
        ),
        eligible_player_ids=(candidate.player_id,),
    )
    triggered = reaction_queue.emit_decision_request(
        state=state,
        decisions=decisions,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token=f"{window_id}-resume",
        actor_id=candidate.player_id,
        decision_type=SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
        options=_setup_reactive_options(candidate),
        payload_factory=_setup_reactive_payload_factory(candidate),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=triggered.decision_request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "catalog_setup_reactive_shoot_charge_pending",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "reacting_player_id": candidate.player_id,
            "source_unit_instance_id": candidate.source_rules_unit.unit_instance_id,
            "target_unit_instance_id": candidate.target_rules_unit_id,
            "trigger_event_id": candidate.trigger_event_id,
        },
    )


def _setup_reactive_payload_factory(
    candidate: _SetupReactiveCandidate,
) -> Callable[[str, str, str], JsonValue]:
    def _factory(request_id: str, decision_type: str, actor_id: str) -> JsonValue:
        payload = candidate.base_payload()
        payload["request_id"] = _validate_identifier("request_id", request_id)
        payload["decision_type"] = _validate_identifier("decision_type", decision_type)
        payload["actor_id"] = _validate_identifier("actor_id", actor_id)
        return validate_json_value(payload)

    return _factory


def _setup_reactive_options(candidate: _SetupReactiveCandidate) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id=CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECLINE_OPTION_ID,
            label="decline",
            payload=candidate.option_payload(CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECLINE_OPTION_ID),
        )
    ]
    if candidate.can_shoot:
        options.append(
            DecisionOption(
                option_id=CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID,
                label="shoot",
                payload=candidate.option_payload(CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID),
            )
        )
    if candidate.can_charge:
        options.append(
            DecisionOption(
                option_id=CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID,
                label="charge",
                payload=candidate.option_payload(CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID),
            )
        )
    return tuple(options)


def _first_candidate_for_player_and_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    active_player_id: str,
    trigger_event: EventRecord,
    ability_index: AbilityCatalogIndex,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> _SetupReactiveCandidate | None:
    target_component_unit_id = _trigger_event_unit_id(trigger_event)
    target_rules_unit_id = rules_unit_id_for_unit_id(
        armies=tuple(state.army_definitions),
        unit_instance_id=target_component_unit_id,
    )
    if target_rules_unit_id != target_component_unit_id:
        return None
    for record in ability_index.records_for(TimingTriggerKind.END_PHASE):
        rule_ir = _setup_reactive_rule_ir_or_none(record)
        if rule_ir is None:
            continue
        clause = rule_ir.clauses[0]
        range_limit = _range_limit_inches(clause)
        for source_rules_unit in _player_rules_units(state=state, player_id=player_id):
            if _setup_reactive_event_already_recorded(
                decisions=decisions,
                trigger_event_id=trigger_event.event_id,
                catalog_record_id=record.record_id,
                source_unit_instance_id=source_rules_unit.unit_instance_id,
                target_unit_instance_id=target_rules_unit_id,
            ):
                continue
            if not _record_applies_to_rules_unit(record=record, rules_unit=source_rules_unit):
                continue
            source_context = _single_placed_alive_source_model(
                state=state,
                rules_unit=source_rules_unit,
            )
            if source_context is None:
                _record_unsupported_source_shape(
                    state=state,
                    decisions=decisions,
                    record=record,
                    rule_ir=rule_ir,
                    clause=clause,
                    source_rules_unit=source_rules_unit,
                    target_unit_instance_id=target_rules_unit_id,
                    trigger_event_id=trigger_event.event_id,
                )
                continue
            source_component_unit, source_model, source_model_placement = source_context
            if source_component_unit.unit_instance_id != source_rules_unit.unit_instance_id:
                _record_unsupported_source_shape(
                    state=state,
                    decisions=decisions,
                    record=record,
                    rule_ir=rule_ir,
                    clause=clause,
                    source_rules_unit=source_rules_unit,
                    target_unit_instance_id=target_rules_unit_id,
                    trigger_event_id=trigger_event.event_id,
                )
                continue
            target_player_id = _target_player_id_from_event(
                trigger_event=trigger_event,
                active_player_id=active_player_id,
            )
            distance = _distance_from_model_to_rules_unit(
                state=state,
                source_model=source_model,
                source_model_placement=source_model_placement,
                target_rules_unit_id=target_rules_unit_id,
            )
            if distance > float(range_limit):
                continue
            can_shoot = _clause_has_action(
                clause=clause,
                action=CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID,
            )
            if can_shoot:
                can_shoot = shooting_rules_unit_has_legal_declaration_against_targets(
                    state=state,
                    rules_unit=source_rules_unit,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                    player_id=player_id,
                    target_unit_ids=(target_rules_unit_id,),
                )
            can_charge = _clause_has_action(
                clause=clause,
                action=CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID,
            )
            if not can_shoot and not can_charge:
                continue
            return _SetupReactiveCandidate(
                player_id=player_id,
                record=record,
                rule_ir=rule_ir,
                clause=clause,
                source_rules_unit=source_rules_unit,
                source_component_unit=source_component_unit,
                source_model=source_model,
                source_model_placement=source_model_placement,
                target_rules_unit_id=target_rules_unit_id,
                target_component_unit_id=target_component_unit_id,
                target_player_id=target_player_id,
                trigger_event_id=trigger_event.event_id,
                distance_inches=distance,
                range_limit_inches=range_limit,
                can_shoot=can_shoot,
                can_charge=can_charge,
            )
    return None


def _apply_setup_reactive_shoot(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: dict[str, JsonValue],
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
    status = request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=result.actor_id or "",
        unit_instance_id=_payload_string(payload, key="source_unit_instance_id"),
        parent_phase=BattlePhase.MOVEMENT,
        source_rule_id=_payload_string(payload, key="source_rule_id"),
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        source_context=validate_json_value(payload),
        target_unit_ids=(_payload_string(payload, key="target_unit_instance_id"),),
    )
    decisions.event_log.append(
        "catalog_setup_reactive_shoot_requested",
        _selection_event_payload(state=state, result=result, payload=payload),
    )
    return status


def _apply_setup_reactive_charge(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    payload: dict[str, JsonValue],
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    source_unit_id = _payload_string(payload, key="source_unit_instance_id")
    target_unit_id = _payload_string(payload, key="target_unit_instance_id")
    source_unit = _unit_by_id(state=state, unit_instance_id=source_unit_id)
    roll_modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=ability_index,
        unit=source_unit,
        current_model_instance_ids=_current_model_instance_ids_for_unit(
            state=state,
            unit=source_unit,
        ),
    )
    roll_modifiers = runtime_modifier_registry.charge_roll_modifiers(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=source_unit_id,
            current_roll_modifiers=roll_modifiers,
        )
    )
    roll_request = ChargeRollRequest(
        request_id=f"setup-reactive-charge-roll:{result.result_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=result.actor_id or "",
        unit_instance_id=source_unit_id,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        roll_modifiers=roll_modifiers,
    )
    roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        roll_request.spec
    )
    reachable_distances = _target_limited_reachable_charge_distances(
        state=state,
        unit_instance_id=source_unit_id,
        player_id=result.actor_id or "",
        target_unit_instance_id=target_unit_id,
        maximum_distance_inches=roll_state.current_total,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    roll_result = ChargeRollResult.from_roll_state(
        request=roll_request,
        roll_state=roll_state,
        reachable_target_distances_inches=reachable_distances,
    )
    decisions.event_log.append(
        "catalog_setup_reactive_charge_roll_resolved",
        validate_json_value(
            {
                **phase15a_charge_roll_payload(
                    roll_result=roll_result,
                    phase=BattlePhase.MOVEMENT,
                ),
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "request_id": result.request_id,
                "result_id": result.result_id,
                "source_rule_id": _payload_string(payload, key="source_rule_id"),
                "catalog_record_id": _payload_string(payload, key="catalog_record_id"),
                "target_unit_instance_id": target_unit_id,
                "source_context": validate_json_value(payload),
            }
        ),
    )
    if not roll_result.move_available:
        decisions.event_log.append(
            "catalog_setup_reactive_charge_no_move_possible",
            _selection_event_payload(
                state=state,
                result=result,
                payload={
                    **payload,
                    "charge_roll": validate_json_value(roll_result.to_payload()),
                },
            ),
        )
        return None
    actor_id = result.actor_id
    if actor_id is None:
        raise GameLifecycleError("Setup-reactive Charge Move request requires an actor.")
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=source_unit_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context={
            "source_kind": CATALOG_SETUP_REACTIVE_SOURCE_KIND,
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": roll_result.value,
            "reachable_target_unit_instance_ids": list(
                roll_result.reachable_target_distances_inches
            ),
            "reachable_target_distances_inches": dict(
                sorted(roll_result.reachable_target_distances_inches.items())
            ),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: [target_unit_id],
            "target_unit_instance_id": target_unit_id,
            "charge_roll": validate_json_value(roll_result.to_payload()),
            "charge_bonus_suppressed": True,
            "suppressed_charge_bonus": "fights_first",
            "suppressed_charge_bonus_effect_kind": FIGHTS_FIRST_CHARGE_EFFECT_KIND,
            "source_context": validate_json_value(payload),
        },
    )
    request = decisions.request_decision(proposal_request.to_decision_request())
    decisions.event_log.append(
        "catalog_setup_reactive_charge_move_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": source_unit_id,
                "target_unit_instance_id": target_unit_id,
                "movement_phase_action": CHARGE_MOVE_ACTION,
                "movement_mode": MovementMode.CHARGE.value,
                "proposal_kind": ProposalKind.CHARGE_MOVE.value,
                "request_id": request.request_id,
                "source_decision_request_id": result.request_id,
                "source_decision_result_id": result.result_id,
                "maximum_distance_inches": roll_result.value,
                "reachable_target_unit_instance_ids": list(
                    roll_result.reachable_target_distances_inches
                ),
                CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: [target_unit_id],
                "charge_bonus_suppressed": True,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "catalog_setup_reactive_charge_move_proposal_required",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": source_unit_id,
            "target_unit_instance_id": target_unit_id,
            "movement_phase_action": CHARGE_MOVE_ACTION,
            "proposal_kind": ProposalKind.CHARGE_MOVE.value,
            "maximum_distance_inches": roll_result.value,
            "reachable_target_unit_instance_ids": list(
                roll_result.reachable_target_distances_inches
            ),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: [target_unit_id],
        },
    )


def _setup_reactive_rule_ir_or_none(record: AbilityCatalogRecord) -> RuleIR | None:
    from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload

    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return None
    rule_ir = scoped_rule_ir_from_execution_payload(record.definition.replay_payload)
    if len(rule_ir.clauses) != 1:
        return None
    clause = rule_ir.clauses[0]
    if _clause_is_setup_reactive_shoot_charge(clause):
        return rule_ir
    return None


def _clause_is_setup_reactive_shoot_charge(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Setup-reactive clause check requires a RuleClause.")
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_params = parameter_payload(trigger.parameters)
    if (
        trigger_params.get("edge") != "end"
        or trigger_params.get("owner") != "opponent"
        or trigger_params.get("phase") != "movement"
        or trigger_params.get("timing_window") != "end_opponent_movement_phase"
    ):
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    return _clause_has_action(
        clause=clause, action=CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID
    ) or _clause_has_action(clause=clause, action=CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID)


def _clause_has_action(*, clause: RuleClause, action: str) -> bool:
    requested_action = _validate_action(action)
    return any(_effect_action(effect) == requested_action for effect in clause.effects)


def _effect_action(effect: RuleEffectSpec) -> str | None:
    if effect.kind is not RuleEffectKind.OUT_OF_PHASE_ACTION:
        return None
    parameters = parameter_payload(effect.parameters)
    if parameters.get("action_group") != "setup_reactive_shoot_charge":
        return None
    action = parameters.get("action")
    if action in {
        CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID,
        CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID,
    }:
        return action
    return None


def _range_limit_inches(clause: RuleClause) -> int:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("predicate") == "within"
            and parameters.get("subject") == "selected_unit"
            and parameters.get("object_kind") == "model"
            and parameters.get("object_reference") == "this"
        ):
            distance = parameters.get("distance_inches")
            if type(distance) is int:
                return distance
    raise GameLifecycleError("Setup-reactive clause requires selected-unit distance.")


def _record_applies_to_rules_unit(
    *,
    record: AbilityCatalogRecord,
    rules_unit: RulesUnitView,
) -> bool:
    if record.datasheet_id is not None and not any(
        component.unit.datasheet_id == record.datasheet_id for component in rules_unit.components
    ):
        return False
    return not (
        record.wargear_id is not None
        and not any(record.wargear_id in model.wargear_ids for model in rules_unit.own_models)
    )


def _single_placed_alive_source_model(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[UnitInstance, ModelInstance, ModelPlacement] | None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Setup-reactive source lookup requires battlefield_state.")
    placed_alive: list[tuple[UnitInstance, ModelInstance, ModelPlacement]] = []
    for component in rules_unit.components:
        for model in component.unit.own_models:
            if not model.is_alive:
                continue
            placement = battlefield_state.model_placement_or_none(model.model_instance_id)
            if placement is None:
                continue
            placed_alive.append((component.unit, model, placement))
    if len(placed_alive) == 1:
        return placed_alive[0]
    return None


def _record_unsupported_source_shape(
    *,
    state: GameState,
    decisions: DecisionController,
    record: AbilityCatalogRecord,
    rule_ir: RuleIR,
    clause: RuleClause,
    source_rules_unit: RulesUnitView,
    target_unit_instance_id: str,
    trigger_event_id: str,
) -> None:
    if _setup_reactive_event_already_recorded(
        decisions=decisions,
        trigger_event_id=trigger_event_id,
        catalog_record_id=record.record_id,
        source_unit_instance_id=source_rules_unit.unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return
    decisions.event_log.append(
        "catalog_setup_reactive_shoot_charge_unsupported",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "active_player_id": _active_player_id(state),
                "player_id": source_rules_unit.owner_player_id,
                "catalog_record_id": record.record_id,
                "source_rule_id": record.definition.source_id,
                "rule_ir_source_id": rule_ir.source_id,
                "rule_ir_hash": rule_ir.ir_hash(),
                "clause_id": clause.clause_id,
                "source_unit_instance_id": source_rules_unit.unit_instance_id,
                "target_unit_instance_id": target_unit_instance_id,
                "trigger_event_id": trigger_event_id,
                "unsupported_reason": "model_scoped_action_requires_single_placed_alive_model",
            }
        ),
    )


def _distance_from_model_to_rules_unit(
    *,
    state: GameState,
    source_model: ModelInstance,
    source_model_placement: ModelPlacement,
    target_rules_unit_id: str,
) -> float:
    source_geometry = geometry_model_for_placement(
        model=source_model,
        placement=source_model_placement,
    )
    target_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_rules_unit_id)
    target_geometries = _geometry_models_for_rules_unit(state=state, rules_unit=target_rules_unit)
    if not target_geometries:
        raise GameLifecycleError("Setup-reactive target rules unit has no placed alive models.")
    return min(
        DistanceMeasurementContext.from_models(
            source_geometry, target_geometry
        ).closest_distance_inches()
        for target_geometry in target_geometries
    )


def _geometry_models_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Setup-reactive geometry lookup requires battlefield_state.")
    models: list[GeometryModel] = []
    for component in rules_unit.components:
        for model in component.unit.own_models:
            if not model.is_alive:
                continue
            placement = battlefield_state.model_placement_or_none(model.model_instance_id)
            if placement is None:
                continue
            models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def _setup_trigger_events(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
) -> tuple[EventRecord, ...]:
    triggers: list[EventRecord] = []
    for record in decisions.event_log.records:
        if record.event_type != "reinforcement_unit_arrived":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("phase") != BattlePhase.MOVEMENT.value:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        _payload_string(payload, key="unit_instance_id")
        triggers.append(record)
    return tuple(triggers)


def _setup_reactive_event_already_recorded(
    *,
    decisions: DecisionController,
    trigger_event_id: str,
    catalog_record_id: str,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
) -> bool:
    for record in decisions.event_log.records:
        if record.event_type not in _SETUP_REACTIVE_SELECTED_EVENTS:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("trigger_event_id") != trigger_event_id:
            continue
        if payload.get("catalog_record_id") != catalog_record_id:
            continue
        if payload.get("source_unit_instance_id") != source_unit_instance_id:
            continue
        if payload.get("target_unit_instance_id") == target_unit_instance_id:
            return True
    return False


def _setup_reactive_payload_drift_reason(
    *,
    state: GameState,
    decisions: DecisionController | None,
    payload: dict[str, JsonValue],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> str | None:
    player_id = _payload_string(payload, key="target_player_id")
    if player_id != _active_player_id(state):
        return "setup_reactive_target_player_drift"
    actor_id = _payload_string(payload, key="actor_id") if "actor_id" in payload else None
    if actor_id is None:
        source_unit_id = _payload_string(payload, key="source_unit_instance_id")
        actor_id = rules_unit_view_by_id(
            state=state,
            unit_instance_id=source_unit_id,
        ).owner_player_id
    index = ability_indexes_by_player_id.get(actor_id)
    if index is None:
        return "setup_reactive_ability_index_missing"
    record_id = _payload_string(payload, key="catalog_record_id")
    record = _record_by_id_or_none(index=index, record_id=record_id)
    if record is None:
        return "setup_reactive_catalog_record_missing"
    rule_ir = _setup_reactive_rule_ir_or_none(record)
    if rule_ir is None:
        return "setup_reactive_rule_ir_missing"
    if rule_ir.ir_hash() != _payload_string(payload, key="rule_ir_hash"):
        return "setup_reactive_rule_ir_hash_drift"
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_payload_string(payload, key="source_unit_instance_id"),
    )
    source_context = _single_placed_alive_source_model(state=state, rules_unit=source_rules_unit)
    if source_context is None:
        return "setup_reactive_source_model_shape_drift"
    source_component_unit, source_model, source_model_placement = source_context
    if source_component_unit.unit_instance_id != _payload_string(
        payload,
        key="source_component_unit_instance_id",
    ):
        return "setup_reactive_source_component_drift"
    if source_model.model_instance_id != _payload_string(
        payload,
        key="source_model_instance_id",
    ):
        return "setup_reactive_source_model_drift"
    target_unit_id = _payload_string(payload, key="target_unit_instance_id")
    target_component_id = _payload_string(payload, key="target_component_unit_instance_id")
    current_target_rules_id = rules_unit_id_for_unit_id(
        armies=tuple(state.army_definitions),
        unit_instance_id=target_component_id,
    )
    if current_target_rules_id != target_unit_id:
        return "setup_reactive_target_rules_unit_drift"
    trigger_event_id = _payload_string(payload, key="trigger_event_id")
    if decisions is not None and not any(
        record.event_id == trigger_event_id for record in decisions.event_log.records
    ):
        return "setup_reactive_trigger_event_missing"
    distance = _distance_from_model_to_rules_unit(
        state=state,
        source_model=source_model,
        source_model_placement=source_model_placement,
        target_rules_unit_id=target_unit_id,
    )
    if distance > float(_payload_int(payload, key="range_limit_inches")):
        return "setup_reactive_distance_drift"
    action = _payload_string(payload, key="action")
    shoot_target_is_eligible = shooting_rules_unit_has_legal_declaration_against_targets(
        state=state,
        rules_unit=source_rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=actor_id,
        target_unit_ids=(target_unit_id,),
    )
    if action == CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID and not shoot_target_is_eligible:
        return "setup_reactive_shoot_target_eligibility_drift"
    return None


def _selection_event_payload(
    *,
    state: GameState,
    result: DecisionResult,
    payload: Mapping[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "player_id": result.actor_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "selected_option_id": result.selected_option_id,
            "catalog_record_id": _payload_string(payload, key="catalog_record_id"),
            "source_rule_id": _payload_string(payload, key="source_rule_id"),
            "rule_ir_hash": _payload_string(payload, key="rule_ir_hash"),
            "clause_id": _payload_string(payload, key="clause_id"),
            "source_unit_instance_id": _payload_string(
                payload,
                key="source_unit_instance_id",
            ),
            "source_component_unit_instance_id": _payload_string(
                payload,
                key="source_component_unit_instance_id",
            ),
            "source_model_instance_id": _payload_string(
                payload,
                key="source_model_instance_id",
            ),
            "target_unit_instance_id": _payload_string(payload, key="target_unit_instance_id"),
            "target_component_unit_instance_id": _payload_string(
                payload,
                key="target_component_unit_instance_id",
            ),
            "trigger_event_id": _payload_string(payload, key="trigger_event_id"),
            "action": _payload_string(payload, key="action"),
            "source_context": validate_json_value(dict(payload)),
        }
    )


def _target_limited_reachable_charge_distances(
    *,
    state: GameState,
    unit_instance_id: str,
    player_id: str,
    target_unit_instance_id: str,
    maximum_distance_inches: int,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> dict[str, float]:
    if type(charge_target_restriction_hooks) is not ChargeTargetRestrictionHookRegistry:
        raise GameLifecycleError(
            "Setup-reactive charge reachability requires charge target restrictions."
        )
    actor_id = _validate_identifier("player_id", player_id)
    source_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    target_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    if source_rules_unit.owner_player_id != actor_id:
        raise GameLifecycleError("Setup-reactive charge source unit owner drifted.")
    if target_rules_unit.owner_player_id == actor_id:
        return {}
    distance = _distance_between_rules_units(
        state=state,
        source_rules_unit=source_rules_unit,
        target_rules_unit=target_rules_unit,
    )
    max_declaration_range = ruleset_descriptor.charge_policy.max_declaration_range_inches
    if distance > max_declaration_range or distance > maximum_distance_inches:
        return {}
    restrictions = charge_target_restriction_hooks.restrictions_for(
        ChargeTargetRestrictionContext(
            state=state,
            player_id=actor_id,
            battle_round=state.battle_round,
            charging_unit_instance_id=unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
        )
    )
    if restrictions:
        return {}
    return {target_unit_instance_id: distance}


def _distance_between_rules_units(
    *,
    state: GameState,
    source_rules_unit: RulesUnitView,
    target_rules_unit: RulesUnitView,
) -> float:
    source_geometries = _geometry_models_for_rules_unit(state=state, rules_unit=source_rules_unit)
    target_geometries = _geometry_models_for_rules_unit(state=state, rules_unit=target_rules_unit)
    if not source_geometries or not target_geometries:
        raise GameLifecycleError("Setup-reactive charge distance requires placed alive models.")
    return min(
        DistanceMeasurementContext.from_models(
            source_geometry, target_geometry
        ).closest_distance_inches()
        for source_geometry in source_geometries
        for target_geometry in target_geometries
    )


def _current_model_instance_ids_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Setup-reactive current model lookup requires battlefield_state.")
    placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    known_model_ids = {model.model_instance_id for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        if model_placement.model_instance_id not in known_model_ids:
            raise GameLifecycleError("Setup-reactive unit placement contains unknown models.")
        current_ids.append(model_placement.model_instance_id)
    if not current_ids:
        raise GameLifecycleError("Setup-reactive current model lookup must not be empty.")
    return tuple(sorted(current_ids))


def _player_rules_units(*, state: GameState, player_id: str) -> tuple[RulesUnitView, ...]:
    army = _army_for_player(state=state, player_id=player_id)
    attached_component_ids = {
        component_id
        for attached_unit in army.attached_units
        for component_id in attached_unit.component_unit_instance_ids
    }
    rules_units: list[RulesUnitView] = []
    for attached_unit in army.attached_units:
        rules_units.append(
            rules_unit_view_by_id(
                state=state,
                unit_instance_id=attached_unit.attached_unit_instance_id,
            )
        )
    for unit in army.units:
        if unit.unit_instance_id in attached_component_ids:
            continue
        rules_units.append(
            rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
        )
    return tuple(sorted(rules_units, key=lambda view: view.unit_instance_id))


def _setup_reactive_timing_window_id(candidate: _SetupReactiveCandidate) -> str:
    return (
        f"catalog-setup-reactive-round-{candidate.source_rules_unit.unit_instance_id}-"
        f"{candidate.target_rules_unit_id}-{candidate.trigger_event_id}"
    )


def _trigger_event_unit_id(trigger_event: EventRecord) -> str:
    if not isinstance(trigger_event.payload, dict):
        raise GameLifecycleError("Setup-reactive trigger event payload must be an object.")
    return _payload_string(
        trigger_event.payload,
        key="unit_instance_id",
    )


def _target_player_id_from_event(*, trigger_event: EventRecord, active_player_id: str) -> str:
    if not isinstance(trigger_event.payload, dict):
        raise GameLifecycleError("Setup-reactive trigger event payload must be an object.")
    value = trigger_event.payload.get("active_player_id")
    if type(value) is not str:
        return active_player_id
    return value


def _record_by_id_or_none(
    *,
    index: AbilityCatalogIndex,
    record_id: str,
) -> AbilityCatalogRecord | None:
    requested_id = _validate_identifier("record_id", record_id)
    for record in index.all_records():
        if record.record_id == requested_id:
            return record
    return None


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Setup-reactive unit_instance_id is unknown.")


def _army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_id:
            return army
    raise GameLifecycleError("Setup-reactive player has no army.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Setup-reactive charge requires battlefield_state.")
    return BattlefieldScenario(
        battlefield_state=battlefield_state,
        armies=tuple(state.army_definitions),
    )


def _proposal_context(proposal_request: MovementProposalRequest) -> dict[str, JsonValue]:
    context = proposal_request.context
    if not isinstance(context, dict):
        raise GameLifecycleError("Setup-reactive proposal request requires context.")
    return context


def _proposal_context_string_or_none(
    proposal_request: MovementProposalRequest,
    *,
    key: str,
) -> str | None:
    context = proposal_request.context
    if not isinstance(context, dict):
        return None
    value = context.get(key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError("Setup-reactive proposal context string drift.")
    return value


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Setup-reactive payload must be an object.")
    return value


def _payload_string(payload: Mapping[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Setup-reactive payload requires {key}.")
    return _validate_identifier(key, value)


def _payload_int(payload: Mapping[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Setup-reactive payload requires integer {key}.")
    return value


def _payload_distance_map(payload: Mapping[str, JsonValue], *, key: str) -> dict[str, float]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Setup-reactive payload requires distance map {key}.")
    distances: dict[str, float] = {}
    for raw_target_id, raw_distance in value.items():
        if type(raw_target_id) is not str:
            raise GameLifecycleError("Setup-reactive distance map target must be a string.")
        if type(raw_distance) is int:
            distance = float(raw_distance)
        elif type(raw_distance) is float:
            distance = raw_distance
        else:
            raise GameLifecycleError("Setup-reactive distance map value must be numeric.")
        distances[_validate_identifier("target_unit_instance_id", raw_target_id)] = distance
    return dict(sorted(distances.items()))


def _validate_action(action: str) -> str:
    value = _validate_identifier("setup-reactive action", action)
    if value not in {
        CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECLINE_OPTION_ID,
        CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID,
        CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID,
    }:
        raise GameLifecycleError("Setup-reactive action is unsupported.")
    return value


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Setup-reactive reaction requires an active player.")
    return active_player_id


def _validate_ability_index_mapping(value: object) -> None:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Setup-reactive ability indexes must be a mapping.")
    mapped = cast(Mapping[object, object], value)
    for player_id, index in mapped.items():
        _validate_identifier("player_id", player_id)
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Setup-reactive ability index mapping contained drift.")


_validate_identifier = IdentifierValidator(GameLifecycleError)

setup_reactive_active_player_id = _active_player_id
setup_reactive_battlefield_scenario = _battlefield_scenario
setup_reactive_payload_distance_map = _payload_distance_map
setup_reactive_payload_int = _payload_int
setup_reactive_payload_object = _payload_object
setup_reactive_payload_string = _payload_string
setup_reactive_proposal_context = _proposal_context
setup_reactive_proposal_context_string_or_none = _proposal_context_string_or_none
setup_reactive_target_limited_reachable_charge_distances = (
    _target_limited_reachable_charge_distances
)
