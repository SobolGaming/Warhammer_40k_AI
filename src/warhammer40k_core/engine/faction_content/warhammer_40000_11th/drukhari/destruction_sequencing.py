from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari import (
    army_rule as rules,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari.power_from_pain import (
    PAIN_TOKEN_RESOURCE_KIND,
    SOURCE_RULE_ID,
)
from warhammer40k_core.engine.faction_resources import FactionResourceStatus
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext


def candidates(context: UnitDestroyedContext) -> tuple[TimingRuleCandidate, ...]:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Unit-destroyed candidate discovery requires context.")
    army = rules.drukhari_army_for_player(
        context.state.army_definitions, player_id=context.destroying_player_id
    )
    if army is None:
        return ()
    source_id = (
        f"{SOURCE_RULE_ID}:enemy-unit-destroyed:"
        f"{context.model_destroyed_event_id}:player-{army.player_id}"
    )
    if rules.pain_token_gain_event_exists(context.decisions.event_log.records, source_id=source_id):
        return ()
    return (
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"{SOURCE_RULE_ID}:{context.model_destroyed_event_id}:{context.destroying_player_id}",
                player_id=context.destroying_player_id,
                source_rule_id=SOURCE_RULE_ID,
                requirement=SequencingRequirement.MANDATORY,
            ),
            activate=partial(resolve_enemy_unit_destroyed, context),
        ),
    )


def resolve_enemy_unit_destroyed(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Power from Pain unit-destroyed hook requires context.")
    army = rules.drukhari_army_for_player(
        context.state.army_definitions, player_id=context.destroying_player_id
    )
    if army is None:
        return
    source_id = (
        f"{SOURCE_RULE_ID}:enemy-unit-destroyed:"
        f"{context.model_destroyed_event_id}:player-{army.player_id}"
    )
    if rules.pain_token_gain_event_exists(context.decisions.event_log.records, source_id=source_id):
        return
    gain = context.state.gain_faction_resource(
        player_id=army.player_id,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id=source_id,
    )
    if gain.status is not FactionResourceStatus.APPLIED:
        raise GameLifecycleError("Power from Pain enemy-unit-destroyed token gain failed.")
    context.decisions.event_log.append(
        "drukhari_pain_token_gained",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.completed_phase.value,
            "player_id": army.player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": f"{rules.HOOK_ID}:enemy-unit-destroyed",
            "trigger": "enemy_unit_destroyed",
            "enemy_player_id": context.destroyed_player_id,
            "enemy_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "faction_resource_result": validate_json_value(gain.to_payload()),
        },
    )
