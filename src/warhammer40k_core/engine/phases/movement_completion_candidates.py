from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeDistanceKind,
    MovementEndSurgeGrant,
    MovementEndSurgeHookRegistry,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases import movement_reactions as reactions
from warhammer40k_core.engine.reaction_windows import ReactionWindow as TriggeredReactionWindow
from warhammer40k_core.engine.reaction_windows import ReactionWindowKind
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagem_timing_candidates import stratagem_timing_candidates
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext


def move_reaction_candidates(
    context: UnitMoveCompletedContext,
    *,
    surge_hooks: MovementEndSurgeHookRegistry,
    stratagem_index: StratagemCatalogIndex,
    cost_modifiers: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move reaction candidates require decisions.")
    if context.completed_phase is not BattlePhase.MOVEMENT:
        return ()
    state = context.state
    candidates: list[TimingRuleCandidate] = []
    if context.movement_action == "fall_back":
        stratagem_context = reactions._friendly_unit_fell_back_context_from_event(
            state=state,
            event_id=context.trigger_event_id,
            payload=context.trigger_event_payload,
        )
        candidates.extend(
            stratagem_timing_candidates(
                state=state,
                decisions=decisions,
                index=stratagem_index,
                context=stratagem_context,
                cost_modifiers=cost_modifiers,
                requested_event_type="friendly_unit_fell_back_stratagem_window_opened",
            )
        )
    if context.movement_action not in {"normal_move", "advance", "fall_back"}:
        return tuple(candidates)
    for player_id in state.player_ids:
        if player_id == context.triggering_player_id:
            continue
        surge_context = MovementEndSurgeContext(
            state=state,
            ruleset_descriptor=context.ruleset_descriptor,
            triggering_unit_instance_id=context.triggering_unit_instance_id,
            triggering_player_id=context.triggering_player_id,
            reacting_player_id=player_id,
            trigger_event_id=context.trigger_event_id,
            movement_phase_action=context.movement_action,
            trigger_event_payload=context.trigger_event_payload,
        )
        available_grants = surge_hooks.grants_for(surge_context)
        if not available_grants:
            continue
        for grants in reactions.movement_end_surge_grant_groups(available_grants):
            key = reactions.movement_end_surge_reaction_group_key(grants)
            if reactions._movement_end_surge_event_already_processed(
                decisions=decisions,
                trigger_event_id=context.trigger_event_id,
                reaction_group_key=key,
            ):
                continue
            source_rule = grants[0].descriptor_source_rule_id or grants[0].source_id
            identity: dict[str, JsonValue] = {
                "group": list(key),
                "trigger_event_id": context.trigger_event_id,
            }
            candidates.append(
                TimingRuleCandidate(
                    participant=SequencingParticipant(
                        participant_id="move-surge:" + canonical_payload_sha256(identity),
                        player_id=player_id,
                        source_rule_id=source_rule,
                        requirement=SequencingRequirement.OPTIONAL,
                        payload=validate_json_value(identity),
                    ),
                    activate=partial(_activate_surge, context, player_id, grants),
                )
            )
    return tuple(candidates)


def _activate_surge(
    context: UnitMoveCompletedContext,
    reacting_player_id: str,
    reaction_grants: tuple[MovementEndSurgeGrant, ...],
) -> LifecycleStatus:
    state = context.state
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move reaction activation requires decisions.")
    active_player_id = state.active_player_id
    triggering_unit_id = context.triggering_unit_instance_id
    movement_action = context.movement_action
    reaction_group_key = reactions.movement_end_surge_reaction_group_key(reaction_grants)
    first_grant = reaction_grants[0]
    distance_spec = reactions._movement_end_surge_grant_distance_spec(reaction_grants)
    max_distance_bonus_inches = reactions._movement_end_surge_grant_distance_bonus(reaction_grants)
    descriptor_source_rule_id = first_grant.descriptor_source_rule_id or first_grant.source_id
    roll_state: DiceRollState | None = None
    if distance_spec.kind is MovementEndSurgeDistanceKind.DICE:
        dice_expression = distance_spec.dice_expression
        if dice_expression is None:
            raise GameLifecycleError("Dice movement-end surge distance is missing its expression.")
        roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
            reactions._movement_end_surge_distance_roll_spec(
                source_rule_id=descriptor_source_rule_id,
                player_id=reacting_player_id,
                triggering_unit_instance_id=triggering_unit_id,
                trigger_event_id=context.trigger_event_id,
                distance_expression=dice_expression,
            )
        )
        max_distance_inches = float(roll_state.current_total + max_distance_bonus_inches)
    else:
        fixed_distance_inches = distance_spec.fixed_distance_inches
        if fixed_distance_inches is None:
            raise GameLifecycleError("Fixed movement-end surge distance is missing its value.")
        max_distance_inches = fixed_distance_inches
    distance_resolution = validate_json_value(
        {
            "kind": distance_spec.kind.value,
            "distance_spec": distance_spec.to_payload(),
            "roll_state": (None if roll_state is None else roll_state.to_payload()),
            "bonus_inches": max_distance_bonus_inches,
            "max_distance_inches": max_distance_inches,
        }
    )
    descriptor = TriggeredMovementDescriptor(
        movement_kind=first_grant.movement_kind,
        source_rule_id=descriptor_source_rule_id,
        trigger_timing=TriggeredReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE.value,
            source_event_id=context.trigger_event_id,
        ),
        max_distance_inches=max_distance_inches,
        movement_mode=MovementMode.NORMAL,
        allow_battle_shocked=first_grant.allow_battle_shocked,
        allow_within_engagement_range=False,
        one_per_phase=first_grant.one_per_phase,
        optional=True,
    )
    request = triggered_movement_unit_selection_request(
        state=state,
        player_id=reacting_player_id,
        descriptor=descriptor,
        eligible_units=reactions._eligible_triggered_movement_units_from_grants(
            grants=reaction_grants,
            roll_state=roll_state,
            distance_bonus_inches=max_distance_bonus_inches,
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "movement_end_surge_triggered",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "reacting_player_id": reacting_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "triggering_unit_instance_id": triggering_unit_id,
            "trigger_event_id": context.trigger_event_id,
            "reaction_group_key": list(reaction_group_key),
            "movement_phase_action": movement_action,
            "surge_distance_roll": (None if roll_state is None else roll_state.to_payload()),
            "distance_resolution": distance_resolution,
            "max_distance_bonus_inches": max_distance_bonus_inches,
            "descriptor": descriptor.to_payload(),
            "grants": [grant.to_payload() for grant in reaction_grants],
            "request_id": request.request_id,
            "phase_body_status": "movement_end_surge_pending",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "reacting_player_id": reacting_player_id,
            "triggering_unit_instance_id": triggering_unit_id,
            "decision_type": request.decision_type,
            "phase_body_status": "movement_end_surge_pending",
        },
    )


if TYPE_CHECKING:
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler


def movement_handler_move_candidates(
    handler: MovementPhaseHandler,
    context: UnitMoveCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    return (
        *handler.move_completion_rule_registry.candidates_for(context),
        *move_reaction_candidates(
            context,
            surge_hooks=handler.movement_end_surge_hooks,
            stratagem_index=handler.stratagem_index,
            cost_modifiers=handler.stratagem_cost_modifier_registry,
        ),
    )
