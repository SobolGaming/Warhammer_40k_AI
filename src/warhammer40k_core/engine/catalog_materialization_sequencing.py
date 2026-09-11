from __future__ import annotations

from functools import partial

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
)
from warhammer40k_core.engine import catalog_model_materialization_runtime as _materialization
from warhammer40k_core.engine.attack_completion_sequencing import (
    resolve_attack_completion_candidates,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def candidates(
    runtime: _materialization.CatalogModelMaterializationRuntime,
    context: AttackSequenceCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    grouped: dict[tuple[str, str, str], list[_materialization.CatalogMaterializationSource]] = {}
    for source in runtime.sources(armies=tuple(context.state.army_definitions)):
        key = (source.record.record_id, source.source_unit_instance_id, source.source_rule_id)
        grouped.setdefault(key, []).append(source)
    entries: list[TimingRuleCandidate] = []
    affected = _materialization.model_state_changed_unit_ids_for_sequence(context)
    for key, values in sorted(grouped.items()):
        sources = tuple(values)
        if not any(
            _has_pending_materialization(context, source)
            or _materialization.datasheet_replacement_is_eligible(
                state=context.state,
                source=source,
                affected_unit_instance_ids=affected,
            )
            for source in sources
        ):
            continue
        source = sources[0]
        entries.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"materialization:{key[0]}:{key[1]}",
                    player_id=source.player_id,
                    source_rule_id=source.source_rule_id,
                    requirement=SequencingRequirement.MANDATORY,
                    payload={
                        "source_unit_instance_id": source.source_unit_instance_id,
                        "clause_ids": [item.clause.clause_id for item in sources],
                    },
                    label=source.record.definition.name,
                ),
                activate=partial(_activate, runtime, context, sources),
            )
        )
    return tuple(entries)


def _has_pending_materialization(
    context: AttackSequenceCompletedContext, source: _materialization.CatalogMaterializationSource
) -> bool:
    descriptor = source.materialization
    if descriptor is None:
        return False
    rules_unit = rules_unit_view_by_id(
        state=context.state, unit_instance_id=source.source_unit_instance_id
    )
    if not rules_unit.alive_models():
        return False
    for model_id in _materialization.destroyed_model_ids_for_sequence(
        context, descriptor=descriptor
    ):
        if not _materialization.destroyed_model_matches_source(
            state=context.state, source=source, descriptor=descriptor, model_instance_id=model_id
        ):
            continue
        roll = _materialization.roll_event_for(
            decisions=context.decisions,
            attack_sequence_id=context.attack_sequence.sequence_id,
            source=source,
            destroyed_model_instance_id=model_id,
        )
        if roll is None:
            return True
        payload = _materialization.event_payload(roll.payload, "materialization roll")
        if (
            payload.get("successful") is True
            and _materialization.materialization_event_for_roll(
                decisions=context.decisions, roll_event_id=roll.event_id
            )
            is None
        ):
            return True
    return False


def resolve(
    runtime: _materialization.CatalogModelMaterializationRuntime,
    context: AttackSequenceCompletedContext,
) -> LifecycleStatus | None:
    return resolve_attack_completion_candidates(context, partial(candidates, runtime, context))


def _activate(
    runtime: _materialization.CatalogModelMaterializationRuntime,
    context: AttackSequenceCompletedContext,
    sources: tuple[_materialization.CatalogMaterializationSource, ...],
) -> LifecycleStatus | None:
    if type(context) is not AttackSequenceCompletedContext:
        raise GameLifecycleError("Catalog materialization requires completion context.")
    action_phase = context.source_phase
    if context.attack_sequence.source_phase is not action_phase:
        raise GameLifecycleError("Materialization attack action phase drift.")
    parent_battle_phase = context.state.current_battle_phase
    if parent_battle_phase is None:
        raise GameLifecycleError("Materialization requires a current parent battle phase.")
    for source in sources:
        descriptor = source.materialization
        if descriptor is None:
            continue
        destroyed_model_ids = _materialization.destroyed_model_ids_for_sequence(
            context, descriptor=descriptor
        )
        source_destroyed_ids = tuple(
            model_id
            for model_id in destroyed_model_ids
            if _materialization.destroyed_model_matches_source(
                state=context.state,
                source=source,
                descriptor=descriptor,
                model_instance_id=model_id,
            )
        )
        if not source_destroyed_ids:
            continue
        rules_unit = rules_unit_view_by_id(
            state=context.state, unit_instance_id=source.source_unit_instance_id
        )
        if not rules_unit.alive_models():
            continue
        for model_id in source_destroyed_ids:
            roll_event = _materialization.roll_event_for(
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
                    _materialization.CATALOG_MODEL_MATERIALIZATION_ROLL_EVENT,
                    validate_json_value(
                        {
                            "game_id": context.state.game_id,
                            "battle_round": context.state.battle_round,
                            "phase": parent_battle_phase.value,
                            "action_phase": action_phase.value,
                            "parent_battle_phase": parent_battle_phase.value,
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
            payload = _materialization.event_payload(roll_event.payload, "materialization roll")
            if payload.get("successful") is not True:
                continue
            if (
                _materialization.materialization_event_for_roll(
                    decisions=context.decisions, roll_event_id=roll_event.event_id
                )
                is not None
            ):
                continue
            request = _materialization.materialization_request(
                state=context.state,
                decisions=context.decisions,
                source=source,
                descriptor=descriptor,
                attack_sequence_id=context.attack_sequence.sequence_id,
                action_phase=action_phase,
                parent_battle_phase=parent_battle_phase,
                roll_event_id=roll_event.event_id,
                army_catalog=runtime.army_catalog,
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "game_id": context.state.game_id,
                    "phase": parent_battle_phase.value,
                    "action_phase": action_phase.value,
                    "parent_battle_phase": parent_battle_phase.value,
                    "pending_request_id": request.request_id,
                    "phase_body_status": "catalog_model_materialization_pending",
                },
            )
    _materialization.apply_available_datasheet_replacements(
        state=context.state,
        decisions=context.decisions,
        army_catalog=runtime.army_catalog,
        sources=sources,
        affected_unit_instance_ids=_materialization.model_state_changed_unit_ids_for_sequence(
            context
        ),
        attack_sequence_id=context.attack_sequence.sequence_id,
        action_phase=action_phase,
        parent_battle_phase=parent_battle_phase,
        source_step="after_attacking_unit_finished_attacks",
        source_event_id=context.attack_sequence_completed_event_id,
    )
    return None
