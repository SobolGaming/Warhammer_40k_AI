from __future__ import annotations

from dataclasses import replace
from functools import partial

from warhammer40k_core.engine.cult_ambush import (
    RESURGENCE_RESOURCE_KIND,
    SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
    SOURCE_RULE_ID,
    cult_ambush_resurgence_was_resolved,
    genestealer_cults_player_ids,
)
from warhammer40k_core.engine.cult_ambush_resurgence import (
    cult_ambush_return_candidate,
    resurgence_cost,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext


def cult_ambush_resurgence_template(context: UnitDestroyedContext) -> DecisionRequest | None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Cult Ambush destruction hook requires UnitDestroyedContext.")
    if context.destroyed_player_id not in genestealer_cults_player_ids(context.state):
        return None
    if cult_ambush_resurgence_was_resolved(
        decisions=context.decisions,
        model_destroyed_event_id=context.model_destroyed_event_id,
        destroyed_unit_instance_id=context.destroyed_unit_instance_id,
    ):
        return None
    candidate = cult_ambush_return_candidate(
        context.state,
        destroyed_unit_instance_id=context.destroyed_unit_instance_id,
    )
    if candidate is None:
        return None
    unit = candidate.unit
    cost = resurgence_cost(
        unit=unit,
        starting_strength=candidate.starting_strength,
    )
    if cost is None:
        return None
    total = context.state.faction_resource_total(
        player_id=context.destroyed_player_id,
        resource_kind=RESURGENCE_RESOURCE_KIND,
    )
    if total < cost:
        return None
    payload = validate_json_value(
        {
            "source_rule_id": SOURCE_RULE_ID,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
            "destroyed_player_id": context.destroyed_player_id,
            "destroying_player_id": context.destroying_player_id,
            "battle_round": context.state.battle_round,
            "phase": context.completed_phase.value,
            "starting_strength": candidate.starting_strength,
            "resurgence_cost": cost,
            "current_resurgence_points": total,
        }
    )
    return DecisionRequest(
        request_id=context.issue_request_id(),
        decision_type=SELECT_CULT_AMBUSH_RESURGENCE_DECISION_TYPE,
        actor_id=context.destroyed_player_id,
        payload=payload,
        options=(
            DecisionOption(
                option_id=(
                    f"genestealer_cults:cult_ambush:decline:{context.destroyed_unit_instance_id}"
                ),
                label="Decline Cult Ambush",
                payload={
                    "selection": "decline",
                    "source_rule_id": SOURCE_RULE_ID,
                    "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                    "model_destroyed_event_id": context.model_destroyed_event_id,
                },
            ),
            DecisionOption(
                option_id=(
                    f"genestealer_cults:cult_ambush:spend:{context.destroyed_unit_instance_id}"
                ),
                label="Spend Resurgence Points",
                payload={
                    "selection": "spend",
                    "source_rule_id": SOURCE_RULE_ID,
                    "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                    "model_destroyed_event_id": context.model_destroyed_event_id,
                    "resurgence_cost": cost,
                },
            ),
        ),
    )


def activate_cult_ambush_resurgence(
    context: UnitDestroyedContext, template: DecisionRequest
) -> DecisionRequest:
    from dataclasses import replace

    if not isinstance(template.payload, dict):
        raise GameLifecycleError("Cult Ambush template requires an object payload.")
    request = replace(template, request_id=context.state.next_decision_request_id())
    context.decisions.event_log.append(
        "genestealer_cults_cult_ambush_resurgence_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "phase": context.completed_phase.value,
                "player_id": context.destroyed_player_id,
                "request_id": request.request_id,
                "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                "model_destroyed_event_id": context.model_destroyed_event_id,
                "resurgence_cost": template.payload["resurgence_cost"],
                "current_resurgence_points": template.payload["current_resurgence_points"],
                "source_rule_id": SOURCE_RULE_ID,
            }
        ),
    )

    return request


def candidates(context: UnitDestroyedContext) -> tuple[TimingRuleCandidate, ...]:
    template = cult_ambush_resurgence_template(
        replace(context, authoritative_request_id="timing-request-template")
    )
    if template is None:
        return ()
    return (
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"{SOURCE_RULE_ID}:{context.model_destroyed_event_id}:{context.destroyed_unit_instance_id}",
                player_id=context.destroyed_player_id,
                source_rule_id=SOURCE_RULE_ID,
                requirement=SequencingRequirement.OPTIONAL,
            ),
            activate=partial(activate_cult_ambush_resurgence, context, template),
            request_template=template,
        ),
    )
