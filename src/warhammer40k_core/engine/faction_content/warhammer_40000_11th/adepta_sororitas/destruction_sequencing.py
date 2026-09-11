from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
    army_rule as rules,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext


def candidates(context: UnitDestroyedContext) -> tuple[TimingRuleCandidate, ...]:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Unit-destroyed candidate discovery requires context.")
    army = rules.adepta_sororitas_army_for_player(
        context.state, player_id=context.destroyed_player_id
    )
    if army is None:
        return ()
    unit = rules.unit_by_id(army, unit_instance_id=context.destroyed_unit_instance_id)
    if unit is None:
        raise GameLifecycleError("Destroyed Adepta Sororitas unit was not found in its army.")
    if not rules.is_adepta_sororitas_unit(unit):
        return ()
    if rules.gain_source_exists(
        context.state,
        player_id=army.player_id,
        source_id=rules.unit_destroyed_source_id(
            player_id=army.player_id, model_destroyed_event_id=context.model_destroyed_event_id
        ),
    ):
        return ()
    return (
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"{rules.SOURCE_RULE_ID}:{context.model_destroyed_event_id}:{context.destroyed_player_id}",
                player_id=context.destroyed_player_id,
                source_rule_id=rules.SOURCE_RULE_ID,
                requirement=SequencingRequirement.MANDATORY,
            ),
            activate=partial(resolve_adepta_sororitas_unit_destroyed, context),
        ),
    )


def resolve_adepta_sororitas_unit_destroyed(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Acts of Faith unit-destroyed hook requires context.")
    army = rules.adepta_sororitas_army_for_player(
        context.state, player_id=context.destroyed_player_id
    )
    if army is None:
        return
    destroyed_unit = rules.unit_by_id(army, unit_instance_id=context.destroyed_unit_instance_id)
    if destroyed_unit is None:
        raise GameLifecycleError("Destroyed Adepta Sororitas unit was not found in its army.")
    if not rules.is_adepta_sororitas_unit(destroyed_unit):
        return
    rules.gain_miracle_die(
        context.state,
        context.decisions,
        player_id=context.destroyed_player_id,
        trigger=rules.UNIT_DESTROYED_TRIGGER,
        source_id=rules.unit_destroyed_source_id(
            player_id=context.destroyed_player_id,
            model_destroyed_event_id=context.model_destroyed_event_id,
        ),
        source_context={
            "completed_phase": context.completed_phase.value,
            "destroying_player_id": context.destroying_player_id,
            "destroyed_player_id": context.destroyed_player_id,
            "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "model_destroyed_payload": validate_json_value(context.model_destroyed_payload),
        },
    )
