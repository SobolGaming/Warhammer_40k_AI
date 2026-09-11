from __future__ import annotations

from functools import partial

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def candidates(context: BattleRoundStartRequestContext) -> tuple[TimingRuleCandidate, ...]:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Blessings of Khorne requires request context.")
    return tuple(
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"{_rules.HOOK_ID}:{army.player_id}",
                player_id=army.player_id,
                source_rule_id=_rules.SOURCE_RULE_ID,
                requirement=SequencingRequirement.MANDATORY,
            ),
            activate=partial(request_for, context, player_id=army.player_id),
        )
        for army in _rules.world_eaters_armies(context.state)
        if not _rules.blessings_selection_recorded_for_player(
            context.state, player_id=army.player_id
        )
        and _rules.eligible_blessings_unit_ids_for_army(army)
    )


def request_for(
    context: BattleRoundStartRequestContext, *, player_id: str
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Blessings of Khorne requires request context.")
    for army in _rules.world_eaters_armies(context.state):
        if army.player_id != player_id:
            continue
        if _rules.blessings_selection_recorded_for_player(context.state, player_id=army.player_id):
            continue
        target_unit_ids = _rules.eligible_blessings_unit_ids_for_army(army)
        if not target_unit_ids:
            continue
        bloodshed_points = _rules.bloodshed_points_available(
            context.state, event_log=context.decisions.event_log, player_id=army.player_id
        )
        dice_count = _rules.BLESSINGS_DICE_COUNT + bloodshed_points
        roll_state = DiceRollManager(
            context.state.game_id, event_log=context.decisions.event_log
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=dice_count, sides=6),
                reason="Blessings of Khorne roll",
                roll_type="world_eaters_blessings_of_khorne",
                actor_id=army.player_id,
            )
        )
        dice_values = tuple(roll_state.current_values)
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "faction_id": _rules.WORLD_EATERS_FACTION_ID,
                    "source_rule_id": _rules.SOURCE_RULE_ID,
                    "hook_id": _rules.HOOK_ID,
                    "effect_kind": _rules.BLESSINGS_OF_KHORNE_EFFECT_KIND,
                    "roll_state": roll_state.to_payload(),
                    "dice_values": list(dice_values),
                    "base_dice_count": _rules.BLESSINGS_DICE_COUNT,
                    "bloodshed_points_spent": bloodshed_points,
                    "target_unit_instance_ids": list(target_unit_ids),
                    "rules_update_sources": [_rules.UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE]
                    if bloodshed_points == 0
                    else [
                        _rules.UNBRIDLED_BLOODLUST_RULE_UPDATE_SOURCE,
                        _rules.ICON_OF_KHORNE_RULE_UPDATE_SOURCE,
                    ],
                }
            ),
            options=_rules.blessings_selection_options(
                player_id=army.player_id,
                battle_round=context.state.battle_round,
                dice_values=dice_values,
                bloodshed_points=bloodshed_points,
            ),
        )
    return None
