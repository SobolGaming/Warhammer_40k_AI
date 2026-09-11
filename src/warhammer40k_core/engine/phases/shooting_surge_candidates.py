from __future__ import annotations

from functools import partial

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.phases import shooting_reactions as reactions
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindow as TriggeredReactionWindow,
)
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindowKind,
)
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.shooting_end_surge_hooks import (
    ShootingEndSurgeContext,
    ShootingEndSurgeGrant,
    ShootingEndSurgeHookRegistry,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)


def surge_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: ShootingEndSurgeHookRegistry,
    completed_sequence: AttackSequence,
    completed_event_id: str,
) -> tuple[TimingRuleCandidate, ...]:
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return ()
    hit_target_ids = reactions._successful_hit_target_unit_ids_for_sequence(
        decisions=decisions, sequence=completed_sequence
    )
    if not hit_target_ids:
        return ()
    candidates: list[TimingRuleCandidate] = []
    for player_id in state.player_ids:
        if player_id == completed_sequence.attacker_player_id:
            continue
        context = ShootingEndSurgeContext(
            state=state,
            shooting_unit_instance_id=completed_sequence.attacking_unit_instance_id,
            shooting_player_id=completed_sequence.attacker_player_id,
            reacting_player_id=player_id,
            trigger_event_id=completed_event_id,
            hit_target_unit_instance_ids=hit_target_ids,
        )
        grouped: dict[str, list[ShootingEndSurgeGrant]] = {}
        for grant in registry.grants_for(context):
            grouped.setdefault(grant.source_id, []).append(grant)
        for source_id, source_grants in sorted(grouped.items()):
            if _surge_source_requested(decisions, completed_event_id, player_id, source_id):
                continue
            grants = tuple(source_grants)
            candidates.append(
                TimingRuleCandidate(
                    participant=SequencingParticipant(
                        participant_id=f"shooting-end-surge:{player_id}:{source_id}",
                        source_rule_id=source_id,
                        player_id=player_id,
                        requirement=SequencingRequirement.OPTIONAL,
                        payload=validate_json_value(
                            {"source_hook_ids": sorted({grant.hook_id for grant in grants})}
                        ),
                    ),
                    activate=partial(
                        _activate,
                        state=state,
                        decisions=decisions,
                        completed_sequence=completed_sequence,
                        reacting_player_id=player_id,
                        completed_event_id=completed_event_id,
                        grants=grants,
                        hit_target_ids=hit_target_ids,
                    ),
                )
            )
    return tuple(candidates)


def _activate(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_sequence: AttackSequence,
    reacting_player_id: str,
    completed_event_id: str,
    grants: tuple[ShootingEndSurgeGrant, ...],
    hit_target_ids: tuple[str, ...],
) -> LifecycleStatus:
    shooting_player_id = completed_sequence.attacker_player_id
    max_distance_bonus_inches = reactions._shooting_end_surge_grant_distance_bonus(grants)
    roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        reactions._shooting_end_surge_distance_roll_spec(
            source_rule_id=grants[0].source_id,
            player_id=reacting_player_id,
            shooting_unit_instance_id=completed_sequence.attacking_unit_instance_id,
            trigger_event_id=completed_event_id,
        )
    )
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.SURGE,
        source_rule_id=grants[0].source_id,
        trigger_timing=TriggeredReactionWindow(
            phase=BattlePhase.SHOOTING,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="just_after_enemy_unit_has_shot",
            source_event_id=completed_event_id,
        ),
        max_distance_inches=float(roll_state.current_total + max_distance_bonus_inches),
        movement_mode=MovementMode.NORMAL,
        allow_battle_shocked=False,
        allow_within_engagement_range=False,
        one_per_phase=True,
        optional=True,
    )
    request = triggered_movement_unit_selection_request(
        state=state,
        player_id=reacting_player_id,
        descriptor=descriptor,
        eligible_units=reactions._eligible_triggered_movement_units_from_shooting_grants(
            grants=grants, roll_state=roll_state, distance_bonus_inches=max_distance_bonus_inches
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_end_surge_triggered",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "shooting_player_id": shooting_player_id,
                "reacting_player_id": reacting_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                "trigger_event_id": completed_event_id,
                "hit_target_unit_instance_ids": list(hit_target_ids),
                "surge_distance_roll": roll_state.to_payload(),
                "max_distance_bonus_inches": max_distance_bonus_inches,
                "descriptor": descriptor.to_payload(),
                "grants": [grant.to_payload() for grant in grants],
                "request_id": request.request_id,
                "phase_body_status": "shooting_end_surge_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "reacting_player_id": reacting_player_id,
            "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
            "decision_type": request.decision_type,
            "phase_body_status": "shooting_end_surge_pending",
        },
    )


def _surge_source_requested(
    decisions: DecisionController, event_id: str, player_id: str, source_id: str
) -> bool:
    for event in decisions.event_log.records:
        payload = event.payload
        if event.event_type != "shooting_end_surge_triggered" or not isinstance(payload, dict):
            continue
        descriptor = payload.get("descriptor")
        if (
            payload.get("trigger_event_id") == event_id
            and payload.get("reacting_player_id") == player_id
            and isinstance(descriptor, dict)
            and descriptor.get("source_rule_id") == source_id
        ):
            return True
    return False
