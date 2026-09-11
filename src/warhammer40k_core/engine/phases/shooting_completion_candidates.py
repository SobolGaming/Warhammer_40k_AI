from __future__ import annotations

from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phases import shooting_reactions as reactions
from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler
from warhammer40k_core.engine.stratagem_timing_candidates import stratagem_timing_candidates
from warhammer40k_core.engine.stratagems import (
    DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    HIT_TARGET_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    StratagemEligibilityContext,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def shooting_completion_candidates(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    completed_event_id: str,
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.phases.shooting_surge_candidates import surge_candidates

    candidates: list[TimingRuleCandidate] = []
    for player_id in state.player_ids:
        friendly = player_id == sequence.attacker_player_id
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player_id,
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT
            if friendly
            else TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
            timing_window_id=reactions._friendly_unit_has_shot_timing_window_id(completed_event_id)
            if friendly
            else reactions._enemy_unit_has_shot_timing_window_id(
                trigger_event_id=completed_event_id,
                player_id=player_id,
            ),
            trigger_payload={
                JUST_SHOT_UNIT_CONTEXT_KEY: sequence.attacking_unit_instance_id,
                HIT_TARGET_UNIT_CONTEXT_KEY: list(
                    reactions._successful_hit_target_unit_ids_for_sequence(
                        decisions=decisions, sequence=sequence
                    )
                ),
                DESTROYED_TARGET_UNIT_CONTEXT_KEY: list(
                    reactions._destroyed_target_unit_ids_for_sequence(
                        decisions=decisions, sequence=sequence
                    )
                ),
                DESTROYED_ENEMY_UNIT_CONTEXT_KEY: list(
                    reactions._destroyed_enemy_unit_ids_for_sequence(
                        state=state, decisions=decisions, sequence=sequence
                    )
                ),
                "attack_sequence_id": sequence.sequence_id,
                "attack_sequence_completed_event_id": completed_event_id,
                **({} if friendly else {"shooting_player_id": sequence.attacker_player_id}),
            },
        )
        candidates.extend(
            stratagem_timing_candidates(
                state=state,
                decisions=decisions,
                index=handler.stratagem_index,
                context=context,
                cost_modifiers=handler.stratagem_cost_modifier_registry,
                requested_event_type="friendly_unit_has_shot_stratagem_window_opened"
                if friendly
                else "enemy_unit_has_shot_stratagem_window_opened",
            )
        )
    candidates.extend(
        surge_candidates(
            state=state,
            decisions=decisions,
            registry=handler.shooting_end_surge_hooks,
            completed_sequence=sequence,
            completed_event_id=completed_event_id,
        )
    )
    return tuple(candidates)
