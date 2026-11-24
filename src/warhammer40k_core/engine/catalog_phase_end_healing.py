from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilitySourceKind,
    ability_record_is_active_generic_rule_ir,
)
from warhammer40k_core.engine.ability_presence import active_ability_model_ids_for_unit
from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.catalog_datasheet_rule_extensions import (
    clause_is_phase_end_self_healing,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_PHASE_END_SELF_HEALING_CONSUMER_ID,
)
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import healing_opposing_player_id
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext


def catalog_phase_end_healing_bindings(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[TurnEndHookBinding, ...]:
    sources: list[tuple[str, str, str, str]] = []
    for player_id, index in sorted(ability_indexes_by_player_id.items()):
        for record in index.records_for(TimingTriggerKind.END_PHASE):
            if (
                record.source_kind is not AbilitySourceKind.DATASHEET
                or record.datasheet_id is None
                or not ability_record_is_active_generic_rule_ir(record)
            ):
                continue
            rule = scoped_rule_ir_from_execution_payload(record.definition.replay_payload)
            sources.extend(
                (player_id, record.datasheet_id, rule.source_id, clause.clause_id)
                for clause in rule.clauses
                if clause_is_phase_end_self_healing(clause)
            )
    if not sources:
        return ()
    return (
        TurnEndHookBinding(
            hook_id=CATALOG_IR_PHASE_END_SELF_HEALING_CONSUMER_ID,
            source_id=CATALOG_IR_PHASE_END_SELF_HEALING_CONSUMER_ID,
            trigger_kind=TimingTriggerKind.END_PHASE,
            candidate_handler=partial(_candidates, tuple(sources)),
        ),
    )


def _candidates(
    sources: tuple[tuple[str, str, str, str], ...],
    context: TurnEndRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    state = context.state
    window = boundary_context(state, TimingTriggerKind.END_PHASE).timing_window
    candidates: list[TimingRuleCandidate] = []
    for player_id, datasheet_id, source_rule_id, clause_id in sources:
        army = state.army_definition_for_player(player_id)
        if army is None:
            raise GameLifecycleError("Phase-end healing source requires a current army.")
        for unit in army.units:
            if unit.datasheet_id != datasheet_id:
                continue
            wounded = tuple(
                model
                for model in unit.own_models
                if model.is_alive and model.current_wounds < model.initial_wounds
            )
            if not wounded:
                continue
            active_model_ids = set(active_ability_model_ids_for_unit(state=state, unit=unit))
            heals = tuple(
                (model.model_instance_id, model.initial_wounds - model.current_wounds)
                for model in wounded
                if model.model_instance_id in active_model_ids
            )
            if not heals:
                continue
            rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
            participant_id = f"{window.window_id}:{unit.unit_instance_id}:{clause_id}"
            candidates.append(
                TimingRuleCandidate(
                    participant=SequencingParticipant(
                        participant_id=participant_id,
                        player_id=player_id,
                        source_rule_id=source_rule_id,
                        requirement=SequencingRequirement.MANDATORY,
                        payload={
                            "source_clause_id": clause_id,
                            "source_unit_instance_id": unit.unit_instance_id,
                        },
                    ),
                    activate=partial(
                        _restore_wounds,
                        context,
                        participant_id,
                        player_id,
                        source_rule_id,
                        clause_id,
                        rules_unit.unit_instance_id,
                        heals,
                    ),
                )
            )
    return tuple(candidates)


def _restore_wounds(
    context: TurnEndRequestContext,
    participant_id: str,
    player_id: str,
    source_rule_id: str,
    clause_id: str,
    unit_instance_id: str,
    heals: tuple[tuple[str, int], ...],
) -> None:
    state = context.state
    for model_id, amount in heals:
        resolved, request = resolve_healing_until_blocked(
            state=state,
            decisions=context.decisions,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            effect=HealingEffect(
                effect_id=f"{participant_id}:{model_id}",
                target_unit_instance_id=unit_instance_id,
                amount=amount,
                opposing_player_id=healing_opposing_player_id(state=state, player_id=player_id),
                source_rule_id=source_rule_id,
                source_context={
                    "healing_model_instance_id": model_id,
                    "source_clause_id": clause_id,
                    "timing_participant_id": participant_id,
                },
            ),
        )
        if request is not None or not resolved.is_complete():
            raise GameLifecycleError("Phase-end model healing must resolve immediately.")
