# pyright: reportPrivateUsage=false
from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import _SetupReactiveCandidate
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_eligibility import (
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.shooting import (
    shooting_rules_unit_has_legal_declaration_against_targets,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
)
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
)
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
)


def _candidates_for_player_and_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    active_player_id: str,
    trigger_event: EventRecord,
    ability_index: AbilityCatalogIndex,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    reaction_queue: ReactionQueue | None,
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
        CATALOG_SETUP_REACTIVE_CHARGE_OPTION_ID,
        CATALOG_SETUP_REACTIVE_SHOOT_OPTION_ID,
        _clause_has_action,
        _distance_from_model_to_rules_unit,
        _setup_reactive_event_already_recorded,
        _setup_reactive_rule_ir_or_none,
        _SetupReactiveCandidate,
        _single_placed_alive_source_model,
        player_rules_units,
        record_applies_to_rules_unit,
        setup_reactive_range_limit_inches,
        target_player_id_from_event,
        trigger_event_unit_id,
    )

    candidates: list[TimingRuleCandidate] = []
    target_component_unit_id = trigger_event_unit_id(trigger_event)
    target_rules_unit_id = rules_unit_id_for_unit_id(
        armies=tuple(state.army_definitions),
        unit_instance_id=target_component_unit_id,
    )
    if target_rules_unit_id != target_component_unit_id:
        return ()
    for record in ability_index.records_for(TimingTriggerKind.END_PHASE):
        rule_ir = _setup_reactive_rule_ir_or_none(record)
        if rule_ir is None:
            continue
        clause = rule_ir.clauses[0]
        range_limit = setup_reactive_range_limit_inches(clause)
        for source_rules_unit in player_rules_units(state=state, player_id=player_id):
            if _setup_reactive_event_already_recorded(
                decisions=decisions,
                trigger_event_id=trigger_event.event_id,
                catalog_record_id=record.record_id,
                source_unit_instance_id=source_rules_unit.unit_instance_id,
                target_unit_instance_id=target_rules_unit_id,
            ):
                continue
            if not record_applies_to_rules_unit(record=record, rules_unit=source_rules_unit):
                continue
            source_context = _single_placed_alive_source_model(
                state=state,
                rules_unit=source_rules_unit,
            )
            if source_context is None:
                candidates.append(
                    _unsupported_candidate(
                        state=state,
                        decisions=decisions,
                        record=record,
                        rule_ir=rule_ir,
                        clause=clause,
                        source_rules_unit=source_rules_unit,
                        target_unit_instance_id=target_rules_unit_id,
                        trigger_event_id=trigger_event.event_id,
                    )
                )
                continue
            source_component_unit, source_model, source_model_placement = source_context
            if source_component_unit.unit_instance_id != source_rules_unit.unit_instance_id:
                candidates.append(
                    _unsupported_candidate(
                        state=state,
                        decisions=decisions,
                        record=record,
                        rule_ir=rule_ir,
                        clause=clause,
                        source_rules_unit=source_rules_unit,
                        target_unit_instance_id=target_rules_unit_id,
                        trigger_event_id=trigger_event.event_id,
                    )
                )
                continue
            target_player_id = target_player_id_from_event(
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
            can_charge = can_charge and not rules_unit_started_mission_action_this_turn(
                state=state,
                player_id=player_id,
                unit_instance_id=source_rules_unit.unit_instance_id,
            )
            if not can_shoot and not can_charge:
                continue
            candidate = _SetupReactiveCandidate(
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
            candidates.append(
                _rule_candidate(
                    state=state,
                    decisions=decisions,
                    candidate=candidate,
                    reaction_queue=reaction_queue,
                )
            )
    return tuple(candidates)


def setup_reactive_end_candidates(
    context: TurnEndRequestContext,
    *,
    ability_indexes: Mapping[str, AbilityCatalogIndex],
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
        _active_player_id,
        _setup_reactive_rule_ir_or_none,
        setup_trigger_events,
    )

    if context.completed_phase is not BattlePhase.MOVEMENT:
        return ()
    if not any(
        _setup_reactive_rule_ir_or_none(record) is not None
        for index in ability_indexes.values()
        for record in index.records_for(TimingTriggerKind.END_PHASE)
    ):
        return ()
    if context.ruleset_descriptor is None or context.army_catalog is None:
        raise GameLifecycleError(
            "Setup-reactive candidates require their loaded rules and catalog."
        )
    active = _active_player_id(context.state)
    return tuple(
        candidate
        for event in setup_trigger_events(
            state=context.state,
            decisions=context.decisions,
            active_player_id=active,
        )
        for player, index in ability_indexes.items()
        if player != active
        for candidate in _candidates_for_player_and_trigger(
            state=context.state,
            decisions=context.decisions,
            player_id=player,
            active_player_id=active,
            trigger_event=event,
            ability_index=index,
            ruleset_descriptor=context.ruleset_descriptor,
            army_catalog=context.army_catalog,
            reaction_queue=context.reaction_queue,
        )
    )


def _rule_candidate(
    *,
    state: GameState,
    decisions: DecisionController,
    candidate: _SetupReactiveCandidate,
    reaction_queue: ReactionQueue | None,
) -> TimingRuleCandidate:
    from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
        _setup_reactive_timing_window_id,
    )

    return TimingRuleCandidate(
        participant=SequencingParticipant(
            participant_id=_setup_reactive_timing_window_id(candidate),
            player_id=candidate.player_id,
            source_rule_id=candidate.record.definition.source_id,
            requirement=SequencingRequirement.OPTIONAL,
            payload={
                "catalog_record_id": candidate.record.record_id,
                "rule_ir_hash": candidate.rule_ir.ir_hash(),
                "clause_id": candidate.clause.clause_id,
                "source_unit_instance_id": candidate.source_rules_unit.unit_instance_id,
                "source_model_instance_id": candidate.source_model.model_instance_id,
                "target_unit_instance_id": candidate.target_rules_unit_id,
                "trigger_event_id": candidate.trigger_event_id,
            },
        ),
        activate=partial(_activate, state, decisions, reaction_queue, candidate),
    )


def _activate(
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    candidate: _SetupReactiveCandidate,
) -> LifecycleStatus:
    from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
        emit_setup_reactive_request,
    )

    if reaction_queue is None:
        raise GameLifecycleError("Setup-reactive activation requires the engine reaction queue.")
    return emit_setup_reactive_request(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        candidate=candidate,
    )


def _unsupported_candidate(
    *,
    state: GameState,
    decisions: DecisionController,
    record: AbilityCatalogRecord,
    rule_ir: RuleIR,
    clause: RuleClause,
    source_rules_unit: RulesUnitView,
    target_unit_instance_id: str,
    trigger_event_id: str,
) -> TimingRuleCandidate:
    from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
    from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
        record_unsupported_source_shape,
    )

    identity: dict[str, JsonValue] = {
        "catalog_record_id": record.record_id,
        "source_unit_instance_id": source_rules_unit.unit_instance_id,
        "target_unit_instance_id": target_unit_instance_id,
        "trigger_event_id": trigger_event_id,
        "unsupported_reason": "model_scoped_action_requires_single_placed_alive_model",
    }

    def activate() -> LifecycleStatus:
        record_unsupported_source_shape(
            state=state,
            decisions=decisions,
            record=record,
            rule_ir=rule_ir,
            clause=clause,
            source_rules_unit=source_rules_unit,
            target_unit_instance_id=target_unit_instance_id,
            trigger_event_id=trigger_event_id,
        )
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Setup-reactive source shape is unsupported.",
            payload=identity,
        )

    return TimingRuleCandidate(
        participant=SequencingParticipant(
            participant_id="setup-reactive-unsupported:" + canonical_payload_sha256(identity),
            player_id=source_rules_unit.owner_player_id,
            source_rule_id=record.definition.source_id,
            requirement=SequencingRequirement.OPTIONAL,
            payload=identity,
        ),
        activate=activate,
    )
