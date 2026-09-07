"""Reconstruct generic Leadership at the test boundary from loaded source events."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationKind,
    PersistingEffect,
    PersistingEffectPayload,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_rule_attack_completion import (
    generic_attack_sequence_expiration_ids,
)
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_characteristic_operations_from_effects,
    generic_matching_unit_effect_applications,
)
from warhammer40k_core.engine.generic_rule_effect_identity import generic_rule_persisting_effect_id
from warhammer40k_core.engine.generic_rule_source_authority import (
    generic_ability_provider_matches,
    generic_execution_context_from_payload,
    generic_stratagem_provider_matches,
    validate_generic_detachment_effect_authority,
    validate_generic_enhancement_effect_authority,
    validated_generic_execution_effect_payload,
)
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_duration_execution import expiration_for_duration
from warhammer40k_core.engine.rule_execution import RuleExecutionContext
from warhammer40k_core.engine.rule_frequency import optional_ability_frequency_condition
from warhammer40k_core.engine.rule_target_resolution import target_unit_instance_ids_for_clause
from warhammer40k_core.engine.rules_unit_effects import (
    rules_unit_effect_applications_from_inventory,
)
from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex
from warhammer40k_core.engine.stratagems_model import (
    StratagemCatalogRecord,
    StratagemUseRecord,
    StratagemUseRecordPayload,
)
from warhammer40k_core.rules.rule_ir import RuleEffectKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle


@dataclass(frozen=True, slots=True)
class _HistoricalDurationContext:
    state: HistoricalBattleShockAuthorityContext
    player_id: str
    battle_round: int
    phase: BattlePhase | None
    active_player_id: str | None


def historical_generic_leadership_operations(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> tuple[Modifier, ...]:
    """Never consult the restored state's current effect inventory."""
    prior_events = historical.event_records[: historical.boundary_event_index]
    if not any(
        isinstance(event.payload, dict)
        and (
            (
                event.event_type == "rule_execution_effect_applied"
                and _is_leadership_payload(event.payload)
            )
            or any(
                _is_leadership_payload(_object(effect.effect_payload, "installed effect"))
                for effect in _installed_effects(event.event_type, event.payload)
            )
        )
        for event in prior_events
    ):
        return ()
    authority = RuntimeRuleIRAuthorityIndex.from_runtime_sources(
        ability_indexes_by_player_id=runtime_content_bundle.ability_indexes_by_player_id,
        stratagem_indexes_by_player_id=runtime_content_bundle.stratagem_indexes_by_player_id,
        faction_rule_execution_registry=runtime_content_bundle.faction_rule_execution_registry,
    )
    effects: dict[str, PersistingEffect] = {}
    for event_index, event in enumerate(prior_events):
        if event.event_type == "generic_rule_attack_sequence_effects_expired":
            for effect_id in _attack_expiration_ids(historical, event_index, effects):
                del effects[effect_id]
            continue
        if isinstance(event.payload, dict):
            for installed in _installed_effects(event.event_type, event.payload):
                payload = _object(installed.effect_payload, "installed effect")
                if not _is_leadership_payload(payload):
                    continue
                execution_payload, family, _rule_ir, _clause = (
                    validated_generic_execution_effect_payload(
                        effect=installed, authority_index=authority
                    )
                )
                if family == "detachment":
                    validate_generic_detachment_effect_authority(
                        armies=historical.armies,
                        effect=installed,
                        event_records=historical.event_records,
                        checkpoint_index=historical.boundary_event_index,
                        faction_rule_execution_registry=runtime_content_bundle.faction_rule_execution_registry,
                        runtime_content_activation=runtime_content_bundle.activation,
                    )
                    if (
                        sum(
                            record.event_type == "rule_execution_effect_applied"
                            and record.payload == execution_payload
                            for record in prior_events
                        )
                        != 1
                    ):
                        raise GameLifecycleError(
                            "Historical generic Leadership installation lacks execution authority."
                        )
                elif family == "enhancement":
                    validate_generic_enhancement_effect_authority(
                        effect=installed,
                        event_records=historical.event_records,
                        checkpoint_index=historical.boundary_event_index,
                        faction_rule_execution_registry=runtime_content_bundle.faction_rule_execution_registry,
                        runtime_content_activation=runtime_content_bundle.activation,
                    )
                else:
                    raise GameLifecycleError(
                        "Historical generic Leadership installation family drifted."
                    )
                effects[installed.effect_id] = installed
        if event.event_type != "rule_execution_effect_applied":
            continue
        payload = _object(event.payload, "execution event")
        if not _is_leadership_payload(payload):
            continue
        context = generic_execution_context_from_payload(_object(payload.get("context"), "context"))
        if not context.record_persisting_effects:
            continue
        effect = _effect_from_execution(
            historical=historical,
            authority=authority,
            payload=payload,
            context=context,
            creation_index=event_index,
        )
        if effect is not None:
            previous = effects.get(effect.effect_id)
            if previous is not None and not _expired_at_context(
                previous.expiration,
                _HistoricalDurationContext(
                    state=historical,
                    player_id=context.player_id,
                    battle_round=context.battle_round,
                    phase=context.phase,
                    active_player_id=context.active_player_id,
                ),
            ):
                raise GameLifecycleError("Historical generic Leadership creation is duplicated.")
            effects[effect.effect_id] = effect
    active = tuple(
        effect
        for _, effect in sorted(effects.items())
        if not _expired_at_test(effect.expiration, historical)
    )
    applications = rules_unit_effect_applications_from_inventory(
        armies=historical.armies,
        effects=active,
        rules_unit=historical.rules_unit(historical.request.unit_instance_id),
    )
    return generic_characteristic_operations_from_effects(
        effects=generic_matching_unit_effect_applications(
            applications=applications, effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC
        ),
        characteristic=Characteristic.LEADERSHIP,
    )


def _effect_from_execution(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    authority: RuntimeRuleIRAuthorityIndex,
    payload: dict[str, JsonValue],
    context: RuleExecutionContext,
    creation_index: int,
) -> PersistingEffect | None:
    source_id = _identifier(payload.get("source_id"), "source ID")
    rule_ir = authority.rule_ir_for_player(
        source_id=source_id,
        rule_ir_hash=_identifier(payload.get("rule_ir_hash"), "RuleIR hash"),
        player_id=context.player_id,
    )
    clauses = tuple(
        clause for clause in rule_ir.clauses if clause.clause_id == payload.get("clause_id")
    )
    if len(clauses) != 1:
        raise GameLifecycleError("Historical generic Leadership clause is not loaded.")
    clause = clauses[0]
    index = payload.get("effect_index")
    if type(index) is not int or not 0 <= index < len(clause.effects):
        raise GameLifecycleError("Historical generic Leadership effect slot drifted.")
    target_ids = target_unit_instance_ids_for_clause(
        clause=clause, context=context, target_unit_instance_ids=None
    )
    if (
        context.game_id != historical.game_id
        or context.battle_round > historical.request.battle_round
        or context.player_id not in historical.player_ids
        or payload.get("target_unit_instance_ids") != list(target_ids)
    ):
        raise GameLifecycleError("Historical generic Leadership creation context drifted.")
    _validate_creation_clock(historical, context, creation_index)
    _validate_source_unit(historical, context)
    if optional_ability_frequency_condition(clause) is not None:
        trigger = _object(context.trigger_payload, "activation trigger")
        validate_mutation_decision_closure(
            event_records=historical.event_records,
            decision_records=historical.decision_records,
            mutation_index=creation_index,
            request_id=_identifier(trigger.get("request_id"), "activation request ID"),
            result_id=_identifier(trigger.get("result_id"), "activation result ID"),
        )
    source_units = (
        ()
        if context.source_unit_instance_id is None
        else tuple(
            component.unit
            for component in historical.rules_unit_containing_unit(
                context.source_unit_instance_id
            ).components
        )
    )
    ability_records = authority.ability_records_for_player(
        source_id=source_id, rule_ir_hash=rule_ir.ir_hash(), player_id=context.player_id
    )
    stratagem_records = authority.stratagem_records_for_player(
        source_id=source_id, rule_ir_hash=rule_ir.ir_hash(), player_id=context.player_id
    )
    if not any(
        generic_ability_provider_matches(
            context=context,
            record=record,
            army=historical.army_for_player(context.player_id),
            source_units=source_units,
        )
        for record in ability_records
    ) and not _stratagem_source_applies(
        historical=historical,
        context=context,
        records=stratagem_records,
        creation_index=creation_index,
    ):
        raise GameLifecycleError("Historical generic Leadership lacks source provider authority.")
    if not target_ids or clause.duration is None:
        return None
    expiration = expiration_for_duration(
        duration=clause.duration,
        context=_HistoricalDurationContext(
            state=historical,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
        ),
    )
    if expiration is None:
        return None
    effect = generic_rule_persisting_effect(
        effect_id=generic_rule_persisting_effect_id(
            rule_ir=rule_ir,
            clause=clause,
            effect=clause.effects[index],
            source_unit_instance_id=context.source_unit_instance_id,
            source_model_instance_id=context.source_model_instance_id,
            target_unit_instance_ids=target_ids,
        ),
        source_rule_id=source_id,
        owner_player_id=context.player_id,
        target_unit_instance_ids=target_ids,
        started_battle_round=context.battle_round,
        started_phase=context.phase,
        expiration=expiration,
        effect_payload=payload,
    )
    validated_generic_execution_effect_payload(effect=effect, authority_index=authority)
    _validate_recorded_effect_copies(effect, historical, creation_index)
    return effect


def _validate_source_unit(
    historical: HistoricalBattleShockAuthorityContext, context: RuleExecutionContext
) -> None:
    source_id = context.source_unit_instance_id
    if source_id is None:
        if context.source_model_instance_id is not None:
            raise GameLifecycleError("Historical generic Leadership source model lacks a unit.")
        return
    source = historical.rules_unit_containing_unit(source_id)
    if source.owner_player_id != context.player_id:
        raise GameLifecycleError("Historical generic Leadership source owner drifted.")
    if context.source_model_instance_id is not None and context.source_model_instance_id not in {
        model.model_instance_id for model in source.own_models
    }:
        raise GameLifecycleError("Historical generic Leadership source model drifted.")


def _validate_recorded_effect_copies(
    effect: PersistingEffect, historical: HistoricalBattleShockAuthorityContext, creation_index: int
) -> None:
    """Result copies, when emitted by a provider, must agree with its source execution."""

    def visit(value: JsonValue) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            if value.get("effect_id") == effect.effect_id and "expiration" in value:
                recorded = PersistingEffect.from_payload(cast(PersistingEffectPayload, value))
                if recorded != effect:
                    raise GameLifecycleError(
                        "Historical generic Leadership effect evidence drifted."
                    )
            else:
                for child in value.values():
                    visit(child)

    for event in historical.event_records[creation_index + 1 :]:
        if (
            event.event_type == "rule_execution_effect_applied"
            and isinstance(event.payload, dict)
            and isinstance(effect.effect_payload, dict)
            and all(
                event.payload.get(key) == effect.effect_payload.get(key)
                for key in ("source_id", "clause_id", "effect_index")
            )
        ):
            break
        visit(event.payload)


def _installed_effects(
    event_type: str, payload: dict[str, JsonValue]
) -> tuple[PersistingEffect, ...]:
    if event_type == "generic_detachment_rule_effects_applied":
        rows = payload.get("persisting_effects")
    elif event_type == "enhancement_effects_applied":
        grants = payload.get("effects")
        if not isinstance(grants, list):
            raise GameLifecycleError("Historical enhancement effect inventory is invalid.")
        rows = [
            grant.get("persisting_effect")
            for grant in grants
            if isinstance(grant, dict) and grant.get("persisting_effect") is not None
        ]
    else:
        return ()
    if not isinstance(rows, list):
        raise GameLifecycleError("Historical generic effect installation inventory is invalid.")
    return tuple(
        PersistingEffect.from_payload(
            cast(PersistingEffectPayload, _object(row, "installed effect"))
        )
        for row in rows
    )


def _expired_at_test(
    expiration: EffectExpiration, historical: HistoricalBattleShockAuthorityContext
) -> bool:
    return _expired_at_context(
        expiration,
        _HistoricalDurationContext(
            state=historical,
            player_id=historical.request.player_id,
            battle_round=historical.request.battle_round,
            phase=historical.phase,
            active_player_id=historical.active_player_id,
        ),
    )


def _expired_at_context(expiration: EffectExpiration, context: _HistoricalDurationContext) -> bool:
    historical = context.state
    kind = expiration.expiration_kind
    if kind is EffectExpirationKind.END_OF_BATTLE:
        return False
    if expiration.battle_round is None:
        raise GameLifecycleError("Historical effect expiration lacks its round.")
    if expiration.battle_round != context.battle_round:
        return expiration.battle_round < context.battle_round
    if kind is EffectExpirationKind.START_BATTLE_ROUND:
        return True
    if kind is EffectExpirationKind.END_BATTLE_ROUND:
        return False
    if (
        expiration.player_id not in historical.turn_order
        or context.active_player_id not in historical.turn_order
    ):
        raise GameLifecycleError("Historical effect expiration player is invalid.")
    assert expiration.player_id is not None
    assert context.active_player_id is not None
    expired_turn = historical.turn_order.index(expiration.player_id)
    test_turn = historical.turn_order.index(context.active_player_id)
    if expired_turn != test_turn:
        return expired_turn < test_turn
    if kind is EffectExpirationKind.START_TURN:
        return True
    if kind is EffectExpirationKind.END_TURN:
        return False
    if expiration.phase is None or context.phase is None:
        raise GameLifecycleError("Historical phase expiration lacks a phase.")
    expired_phase = historical.battle_phase_sequence.index(expiration.phase)
    test_phase = historical.battle_phase_sequence.index(context.phase)
    return expired_phase < test_phase or (
        expired_phase == test_phase and kind is EffectExpirationKind.START_PHASE
    )


def _is_leadership_payload(payload: dict[str, JsonValue]) -> bool:
    effect = payload.get("effect")
    if (
        not isinstance(effect, dict)
        or effect.get("kind") != RuleEffectKind.MODIFY_CHARACTERISTIC.value
    ):
        return False
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Historical generic characteristic parameters are invalid.")
    return any(
        isinstance(parameter, dict)
        and parameter.get("key") == "characteristic"
        and parameter.get("value") == Characteristic.LEADERSHIP.value
        for parameter in parameters
    )


def _identifier(value: JsonValue, context: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Historical generic Leadership {context} is invalid.")
    return value


def _object(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Historical generic Leadership {context} must be an object.")
    return value


def _stratagem_source_applies(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    context: RuleExecutionContext,
    records: tuple[StratagemCatalogRecord, ...],
    creation_index: int,
) -> bool:
    for index, event in enumerate(historical.event_records[:creation_index]):
        if event.event_type != "stratagem_used":
            continue
        use = StratagemUseRecord.from_payload(
            cast(StratagemUseRecordPayload, _object(event.payload, "Stratagem use"))
        )
        # The use event precedes resolution; its causal decision still owns the effect.
        if not any(
            generic_stratagem_provider_matches(
                context=context, record=record, uses=(replace(use, effects_resolved=True),)
            )
            for record in records
        ):
            continue
        validate_mutation_decision_closure(
            event_records=historical.event_records,
            decision_records=historical.decision_records,
            mutation_index=index,
            request_id=use.request_id,
            result_id=use.result_id,
        )
        return True
    return False


def _validate_creation_clock(
    historical: HistoricalBattleShockAuthorityContext,
    context: RuleExecutionContext,
    creation_index: int,
) -> None:
    expected: tuple[JsonValue, JsonValue, JsonValue] = (
        1,
        historical.turn_order[0],
        historical.battle_phase_sequence[0].value,
    )
    for event in historical.event_records[:creation_index]:
        if event.event_type == "battle_phase_completed":
            payload = _object(event.payload, "phase boundary")
            expected = (
                payload.get("battle_round"),
                payload.get("active_player_id"),
                payload.get("next_phase"),
            )
    if (
        context.battle_round,
        context.active_player_id,
        None if context.phase is None else context.phase.value,
    ) != expected:
        raise GameLifecycleError("Historical generic Leadership creation boundary drifted.")


def _attack_expiration_ids(
    historical: HistoricalBattleShockAuthorityContext,
    index: int,
    effects: dict[str, PersistingEffect],
) -> tuple[str, ...]:
    payload = _object(historical.event_records[index].payload, "attack expiration")
    sequence_id = _identifier(payload.get("attack_sequence_id"), "attack sequence ID")
    expected = generic_attack_sequence_expiration_ids(
        effects=tuple(effects.values()), sequence_id=sequence_id
    )
    observed = payload.get("expired_effect_ids")
    if not isinstance(observed, list) or any(type(value) is not str for value in observed):
        raise GameLifecycleError(
            "Historical generic Leadership attack expiration inventory is invalid."
        )
    if set(expected) != {
        value for value in observed if isinstance(value, str) and value in effects
    }:
        raise GameLifecycleError(
            "Historical generic Leadership attack expiration inventory drifted."
        )
    anchors = tuple(
        event
        for event in historical.event_records[:index]
        if event.event_id == payload.get("attack_sequence_completed_event_id")
        and event.event_type == "attack_sequence_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence_id
    )
    if payload.get("game_id") != historical.game_id or len(anchors) != 1:
        raise GameLifecycleError(
            "Historical generic Leadership attack expiration lacks completion authority."
        )
    return expected
