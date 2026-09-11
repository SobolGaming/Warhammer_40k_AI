# pyright: reportPrivateUsage=false
from __future__ import annotations

from warhammer40k_core.engine.cult_ambush import (
    SOURCE_RULE_ID,
    TURN_END_HOOK_ID,
    _active_player_id,
    cult_ambush_unarrived_unit_ids,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
)


def candidates(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Cult Ambush ingress requires TurnEndRequestContext.")
    if context.completed_phase is not BattlePhase.MOVEMENT:
        return tuple(candidates)
    active_player_id = _active_player_id(context.state)
    markers = tuple(
        marker
        for marker in context.state.cult_ambush_markers
        if marker.player_id != active_player_id
        and (not marker.ingress_window_closed)
        and (
            not (
                marker.created_battle_round == context.state.battle_round
                and marker.created_phase is BattlePhase.MOVEMENT
                and (marker.created_active_player_id == active_player_id)
            )
        )
    )
    if not markers:
        return tuple(candidates)
    for marker in sorted(markers, key=lambda value: value.marker_id):
        eligible_unit_ids = cult_ambush_unarrived_unit_ids(
            context.state, player_id=marker.player_id
        )
        if not eligible_unit_ids:
            continue
        payload = validate_json_value(
            {
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": TURN_END_HOOK_ID,
                "selection_kind": "cult_ambush_marker_ingress",
                "marker": marker.to_payload(),
                "eligible_unit_instance_ids": list(eligible_unit_ids),
                "battle_round": context.state.battle_round,
                "phase": context.completed_phase.value,
                "active_player_id": active_player_id,
            }
        )
        options = [
            DecisionOption(
                option_id=f"genestealer_cults:cult_ambush:marker:{marker.marker_id}:decline",
                label="Do Not Use Cult Ambush Marker",
                payload={
                    "selection": "decline",
                    "source_rule_id": SOURCE_RULE_ID,
                    "marker_id": marker.marker_id,
                },
            )
        ]
        for unit_id in eligible_unit_ids:
            options.append(
                DecisionOption(
                    option_id=f"genestealer_cults:cult_ambush:marker:{marker.marker_id}:unit:{unit_id}",
                    label=f"Cult Ambush Ingress: {unit_id}",
                    payload={
                        "selection": "ingress",
                        "source_rule_id": SOURCE_RULE_ID,
                        "marker_id": marker.marker_id,
                        "unit_instance_id": unit_id,
                    },
                )
            )
        candidates.append(
            timing_candidate_for_request(
                template=DecisionRequest(
                    request_id="template:turn-end-rule",
                    decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                    actor_id=marker.player_id,
                    payload=payload,
                    options=tuple(options),
                ),
                participant_id=f"{TURN_END_HOOK_ID}:{marker.marker_id}",
                source_rule_id=SOURCE_RULE_ID,
                requirement=SequencingRequirement.OPTIONAL,
                next_request_id=context.state.next_decision_request_id,
            )
        )
    return tuple(candidates)
